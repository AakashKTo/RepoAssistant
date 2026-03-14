from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

import yaml


def _safe_read_text(path: Path, max_bytes: int = 2_000_000) -> str:
    data = path.read_bytes()
    if len(data) > max_bytes:
        data = data[:max_bytes]
    return data.decode("utf-8", errors="replace")


def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(_safe_read_text(path))
    except Exception:
        return None


def _read_toml(path: Path) -> Optional[dict]:
    try:
        import tomllib  # Python 3.11+
    except Exception:
        return None
    try:
        return tomllib.loads(_safe_read_text(path))
    except Exception:
        return None


def _parse_requirements_txt(text: str) -> list[str]:
    pkgs: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-r ") or line.startswith("--requirement "):
            continue
        if line.startswith("-e ") or line.startswith("--editable "):
            continue
        m = re.match(r"^([A-Za-z0-9_.-]+)", line)
        if m:
            pkgs.append(m.group(1).lower())
    return sorted(set(pkgs))


def _detect_node(repo_dir: Path) -> dict[str, Any]:
    pkg_path = repo_dir / "package.json"
    if not pkg_path.exists():
        return {"present": False}

    pkg = _read_json(pkg_path) or {}
    deps = (pkg.get("dependencies") or {})
    dev_deps = (pkg.get("devDependencies") or {})
    all_deps = {**deps, **dev_deps}
    dep_names = {k.lower() for k in all_deps.keys()}

    frameworks: list[str] = []
    if "express" in dep_names:
        frameworks.append("Express")
    if "fastify" in dep_names:
        frameworks.append("Fastify")
    if "@nestjs/core" in dep_names:
        frameworks.append("NestJS")
    if "next" in dep_names:
        frameworks.append("Next.js")
    if "react" in dep_names:
        frameworks.append("React")
    if "vue" in dep_names:
        frameworks.append("Vue")
    if "@angular/core" in dep_names:
        frameworks.append("Angular")

    typescript = ("typescript" in dep_names) or (repo_dir / "tsconfig.json").exists()

    pm = None
    if (repo_dir / "pnpm-lock.yaml").exists():
        pm = "pnpm"
    elif (repo_dir / "yarn.lock").exists():
        pm = "yarn"
    elif (repo_dir / "package-lock.json").exists():
        pm = "npm"

    scripts = sorted((pkg.get("scripts") or {}).keys())

    evidence = ["package.json"]
    for f in ["pnpm-lock.yaml", "yarn.lock", "package-lock.json", "tsconfig.json"]:
        if (repo_dir / f).exists():
            evidence.append(f)

    return {
        "present": True,
        "package_manager": pm,
        "typescript": bool(typescript),
        "frameworks": frameworks,
        "scripts": scripts,
        "dependencies_count": len(deps),
        "dev_dependencies_count": len(dev_deps),
        "evidence": evidence,
    }


def _detect_python(repo_dir: Path) -> dict[str, Any]:
    req_path = repo_dir / "requirements.txt"
    pyproject_path = repo_dir / "pyproject.toml"

    req_pkgs: list[str] = []
    if req_path.exists():
        req_pkgs = _parse_requirements_txt(_safe_read_text(req_path))

    pyproject = _read_toml(pyproject_path) if pyproject_path.exists() else None

    pyproject_deps: list[str] = []
    if pyproject:
        proj = pyproject.get("project") or {}
        deps = proj.get("dependencies") or []
        for d in deps:
            m = re.match(r"^([A-Za-z0-9_.-]+)", str(d).strip())
            if m:
                pyproject_deps.append(m.group(1).lower())

        tool = pyproject.get("tool") or {}
        poetry = tool.get("poetry") or {}
        pdeps = poetry.get("dependencies") or {}
        for k in pdeps.keys():
            if k.lower() != "python":
                pyproject_deps.append(k.lower())

    all_pkgs = sorted(set(req_pkgs + pyproject_deps))
    names = set(all_pkgs)

    frameworks: list[str] = []
    if "django" in names:
        frameworks.append("Django")
    if "fastapi" in names:
        frameworks.append("FastAPI")
    if "flask" in names:
        frameworks.append("Flask")

    present = bool(req_path.exists() or pyproject_path.exists())
    evidence: list[str] = []
    if req_path.exists():
        evidence.append("requirements.txt")
    if pyproject_path.exists():
        evidence.append("pyproject.toml")

    return {
        "present": present,
        "frameworks": frameworks,
        "packages_count": len(all_pkgs),
        "evidence": evidence,
    }


def _normalize_on_key(workflow: dict) -> Any:
    # YAML 1.1 can parse "on:" as boolean True in some parsers
    if "on" in workflow:
        return workflow.get("on")
    if True in workflow:
        return workflow.get(True)
    return None


def _detect_github_actions(repo_dir: Path) -> dict[str, Any]:
    workflows_dir = repo_dir / ".github" / "workflows"
    if not workflows_dir.exists():
        return {"present": False, "workflows": [], "evidence": []}

    workflows: list[dict[str, Any]] = []
    evidence: list[str] = []

    files = sorted(list(workflows_dir.glob("*.yml")) + list(workflows_dir.glob("*.yaml")))
    for path in files:
        evidence.append(str(path.relative_to(repo_dir)))
        raw = _safe_read_text(path)
        try:
            wf = yaml.safe_load(raw) or {}
        except Exception:
            wf = {}

        name = wf.get("name") or path.name
        on_section = _normalize_on_key(wf)

        triggers: list[str] = []
        if isinstance(on_section, list):
            triggers = [str(x) for x in on_section]
        elif isinstance(on_section, dict):
            triggers = [str(k) for k in on_section.keys()]
        elif on_section is not None:
            triggers = [str(on_section)]

        jobs = wf.get("jobs") or {}
        jobs_out: list[dict[str, Any]] = []
        if isinstance(jobs, dict):
            for job_id, job in jobs.items():
                if not isinstance(job, dict):
                    continue
                steps_out: list[dict[str, Any]] = []
                for step in job.get("steps") or []:
                    if not isinstance(step, dict):
                        continue
                    steps_out.append(
                        {"name": step.get("name"), "uses": step.get("uses"), "run": step.get("run")}
                    )
                jobs_out.append(
                    {"job_id": str(job_id), "runs_on": job.get("runs-on"), "steps": steps_out}
                )

        workflows.append(
            {"file": str(path.relative_to(repo_dir)), "name": name, "triggers": triggers, "jobs": jobs_out}
        )

    return {"present": True, "workflows": workflows, "evidence": evidence}


def _detect_infra(repo_dir: Path) -> dict[str, Any]:
    evidence: list[str] = []

    dockerfile = (repo_dir / "Dockerfile").exists()
    if dockerfile:
        evidence.append("Dockerfile")

    compose = (repo_dir / "docker-compose.yml").exists() or (repo_dir / "docker-compose.yaml").exists()
    if (repo_dir / "docker-compose.yml").exists():
        evidence.append("docker-compose.yml")
    if (repo_dir / "docker-compose.yaml").exists():
        evidence.append("docker-compose.yaml")

    terraform = (repo_dir / "terraform").exists() or any(repo_dir.rglob("*.tf"))
    if (repo_dir / "terraform").exists():
        evidence.append("terraform/")

    k8s = (repo_dir / "k8s").exists() or (repo_dir / "kubernetes").exists()
    if (repo_dir / "k8s").exists():
        evidence.append("k8s/")
    if (repo_dir / "kubernetes").exists():
        evidence.append("kubernetes/")

    return {
        "dockerfile": bool(dockerfile),
        "docker_compose": bool(compose),
        "terraform": bool(terraform),
        "kubernetes": bool(k8s),
        "evidence": evidence,
    }


def _detect_jupyter(repo_dir: Path) -> dict[str, Any]:
    notebooks = list(repo_dir.rglob("*.ipynb"))
    return {
        "present": len(notebooks) > 0,
        "count": len(notebooks),
        "evidence": [str(n.relative_to(repo_dir)) for n in notebooks[:5]]
    }


def detect_tech_stack(repo_dir: Path) -> dict[str, Any]:
    node = _detect_node(repo_dir)
    python = _detect_python(repo_dir)
    jupyter = _detect_jupyter(repo_dir)
    gha = _detect_github_actions(repo_dir)
    infra = _detect_infra(repo_dir)

    languages: list[str] = []
    if node.get("present"):
        languages.append("JavaScript/TypeScript")
    if python.get("present") or jupyter.get("present"):
        languages.append("Python")
    if jupyter.get("present"):
        languages.append("Jupyter Notebook")

    return {
        "languages": languages,
        "node": node,
        "python": python,
        "ci": {"github_actions": gha},
        "infra": infra,
    }