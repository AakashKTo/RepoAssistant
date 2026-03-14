from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

import yaml

IGNORE_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
}


def _safe_read_text(path: Path, max_bytes: int = 500_000) -> str:
    data = path.read_bytes()
    if len(data) > max_bytes:
        data = data[:max_bytes]
    return data.decode("utf-8", errors="replace")


def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(_safe_read_text(path))
    except Exception:
        return None


def _detect_node_pm(repo_dir: Path) -> Optional[str]:
    # lockfile-based detection
    if (repo_dir / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (repo_dir / "yarn.lock").exists():
        return "yarn"
    if (repo_dir / "package-lock.json").exists():
        return "npm"
    # packageManager field in package.json
    pkg = repo_dir / "package.json"
    if pkg.exists():
        data = _read_json(pkg) or {}
        pm = data.get("packageManager")
        if isinstance(pm, str):
            # examples: "pnpm@8.15.0"
            if pm.startswith("pnpm"):
                return "pnpm"
            if pm.startswith("yarn"):
                return "yarn"
            if pm.startswith("npm"):
                return "npm"
    return None


def _node_install_cmd(pm: Optional[str]) -> str:
    if pm == "pnpm":
        return "pnpm install"
    if pm == "yarn":
        return "yarn install"
    return "npm install"


def _node_run_script(pm: Optional[str], script: str) -> str:
    if pm == "pnpm":
        return f"pnpm run {script}"
    if pm == "yarn":
        return f"yarn {script}"
    return f"npm run {script}"


def _choose_first_script(scripts: dict, candidates: list[str]) -> Optional[str]:
    for name in candidates:
        if name in scripts:
            return name
    return None


def _detect_node_startup(repo_dir: Path) -> dict[str, Any]:
    pkg_path = repo_dir / "package.json"
    if not pkg_path.exists():
        return {"present": False}

    pkg = _read_json(pkg_path) or {}
    scripts = pkg.get("scripts") or {}
    if not isinstance(scripts, dict):
        scripts = {}

    pm = _detect_node_pm(repo_dir)

    dev_script = _choose_first_script(
        scripts,
        ["dev", "start:dev", "develop", "serve", "preview"],
    )
    start_script = _choose_first_script(
        scripts,
        ["start", "start:prod", "production"],
    )
    test_script = _choose_first_script(
        scripts,
        ["test", "test:unit", "test:ci"],
    )
    build_script = _choose_first_script(
        scripts,
        ["build"],
    )

    recs: list[dict[str, Any]] = []
    recs.append(
        {
            "title": "Install Node dependencies",
            "commands": [_node_install_cmd(pm)],
            "evidence": ["package.json"],
        }
    )

    if dev_script:
        recs.append(
            {
                "title": "Run Node dev server",
                "commands": [_node_run_script(pm, dev_script)],
                "evidence": ["package.json"],
            }
        )
    if start_script and start_script != dev_script:
        recs.append(
            {
                "title": "Run Node server",
                "commands": [_node_run_script(pm, start_script)],
                "evidence": ["package.json"],
            }
        )
    if build_script:
        recs.append(
            {
                "title": "Build Node project",
                "commands": [_node_run_script(pm, build_script)],
                "evidence": ["package.json"],
            }
        )
    if test_script:
        recs.append(
            {
                "title": "Run Node tests",
                "commands": [_node_run_script(pm, test_script)],
                "evidence": ["package.json"],
            }
        )

    return {
        "present": True,
        "package_manager": pm,
        "scripts": sorted(list(scripts.keys())),
        "recommendations": recs,
        "evidence": ["package.json"],
    }


def _iter_python_files(repo_dir: Path, limit: int = 200):
    count = 0
    for p in repo_dir.rglob("*.py"):
        if any(part in IGNORE_DIRS for part in p.parts):
            continue
        yield p
        count += 1
        if count >= limit:
            return


def _py_module_from_relpath(rel: Path) -> str:
    # convert "src/app.py" -> "src.app"
    return ".".join(rel.with_suffix("").parts)


def _detect_fastapi_app(repo_dir: Path) -> Optional[str]:
    # Find "app = FastAPI(" in likely files
    pattern = re.compile(r"^\s*app\s*=\s*FastAPI\s*\(", re.M)

    # common candidates first
    candidates = [
        repo_dir / "main.py",
        repo_dir / "app.py",
        repo_dir / "server.py",
        repo_dir / "src" / "main.py",
        repo_dir / "src" / "app.py",
    ]
    checked: set[Path] = set()
    for p in candidates:
        if p.exists():
            checked.add(p)
            text = _safe_read_text(p)
            if "FastAPI" in text and pattern.search(text):
                rel = p.relative_to(repo_dir)
                return f"{_py_module_from_relpath(rel)}:app"

    # fallback: scan limited number of python files
    for p in _iter_python_files(repo_dir, limit=200):
        if p in checked:
            continue
        text = _safe_read_text(p)
        if "FastAPI" in text and pattern.search(text):
            rel = p.relative_to(repo_dir)
            return f"{_py_module_from_relpath(rel)}:app"

    return None


def _detect_flask_app(repo_dir: Path) -> Optional[str]:
    pattern = re.compile(r"^\s*app\s*=\s*Flask\s*\(", re.M)

    candidates = [
        repo_dir / "app.py",
        repo_dir / "main.py",
        repo_dir / "wsgi.py",
        repo_dir / "src" / "app.py",
    ]
    checked: set[Path] = set()
    for p in candidates:
        if p.exists():
            checked.add(p)
            text = _safe_read_text(p)
            if "Flask" in text and pattern.search(text):
                rel = p.relative_to(repo_dir)
                return f"{_py_module_from_relpath(rel)}"

    for p in _iter_python_files(repo_dir, limit=200):
        if p in checked:
            continue
        text = _safe_read_text(p)
        if "Flask" in text and pattern.search(text):
            rel = p.relative_to(repo_dir)
            return f"{_py_module_from_relpath(rel)}"

    return None


def _detect_python_startup(repo_dir: Path, python_frameworks: list[str]) -> dict[str, Any]:
    req = repo_dir / "requirements.txt"
    pyproject = repo_dir / "pyproject.toml"
    manage = repo_dir / "manage.py"

    present = req.exists() or pyproject.exists() or manage.exists()
    if not present:
        return {"present": False}

    # install command
    if pyproject.exists():
        # if it's poetry, suggest poetry install; else pip may still be used
        text = _safe_read_text(pyproject)
        if "[tool.poetry]" in text:
            install_cmd = "poetry install"
            runner_prefix = "poetry run "
            evidence = ["pyproject.toml"]
        else:
            install_cmd = "pip install -r requirements.txt" if req.exists() else "pip install -e ."
            runner_prefix = ""
            evidence = ["pyproject.toml"] + (["requirements.txt"] if req.exists() else [])
    else:
        install_cmd = "pip install -r requirements.txt"
        runner_prefix = ""
        evidence = ["requirements.txt"]

    recs: list[dict[str, Any]] = [
        {"title": "Install Python dependencies", "commands": [install_cmd], "evidence": evidence}
    ]

    # run commands
    if "Django" in python_frameworks and manage.exists():
        recs.append(
            {
                "title": "Run Django dev server",
                "commands": [f"{runner_prefix}python manage.py runserver".strip()],
                "evidence": ["manage.py"],
            }
        )

    if "FastAPI" in python_frameworks:
        target = _detect_fastapi_app(repo_dir)
        if target:
            recs.append(
                {
                    "title": "Run FastAPI dev server (uvicorn)",
                    "commands": [f"{runner_prefix}uvicorn {target} --reload".strip()],
                    "evidence": ["requirements.txt", "pyproject.toml"],
                }
            )
        else:
            recs.append(
                {
                    "title": "Run FastAPI dev server (uvicorn)",
                    "commands": ["uvicorn <module>:app --reload"],
                    "evidence": ["requirements.txt", "pyproject.toml"],
                }
            )

    if "Flask" in python_frameworks:
        mod = _detect_flask_app(repo_dir)
        if mod:
            recs.append(
                {
                    "title": "Run Flask dev server",
                    "commands": [f"{runner_prefix}flask --app {mod} run --debug".strip()],
                    "evidence": ["requirements.txt", "pyproject.toml"],
                }
            )
        else:
            recs.append(
                {
                    "title": "Run Flask dev server",
                    "commands": ["flask run --debug  # may require FLASK_APP env var"],
                    "evidence": ["requirements.txt", "pyproject.toml"],
                }
            )

    return {
        "present": True,
        "frameworks": python_frameworks,
        "recommendations": recs,
        "evidence": evidence,
    }


def _detect_docker_startup(repo_dir: Path) -> dict[str, Any]:
    compose_files = []
    if (repo_dir / "docker-compose.yml").exists():
        compose_files.append("docker-compose.yml")
    if (repo_dir / "docker-compose.yaml").exists():
        compose_files.append("docker-compose.yaml")

    dockerfile = (repo_dir / "Dockerfile").exists()

    recs: list[dict[str, Any]] = []
    detected: dict[str, Any] = {"dockerfile": dockerfile, "compose_files": compose_files}

    if compose_files:
        # optionally parse services for info (best-effort)
        services = []
        try:
            cf = repo_dir / compose_files[0]
            doc = yaml.safe_load(_safe_read_text(cf)) or {}
            if isinstance(doc, dict):
                sv = doc.get("services") or {}
                if isinstance(sv, dict):
                    services = sorted(list(sv.keys()))
        except Exception:
            services = []

        detected["compose_services"] = services
        recs.append(
            {
                "title": "Run with Docker Compose",
                "commands": ["docker compose up --build"],
                "evidence": compose_files,
            }
        )

    elif dockerfile:
        recs.append(
            {
                "title": "Build Docker image",
                "commands": ["docker build -t <image-name> ."],
                "evidence": ["Dockerfile"],
            }
        )

    present = bool(compose_files or dockerfile)

    return {
        "present": present,
        "detected": detected,
        "recommendations": recs,
        "evidence": (compose_files + (["Dockerfile"] if dockerfile else [])),
    }


def detect_startup_workflow(repo_dir: Path, tech_stack: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """
    Deterministic startup guidance (no AI).
    Output is intended to help users run the repo locally.
    """
    tech_stack = tech_stack or {}

    node = _detect_node_startup(repo_dir)

    py_frameworks: list[str] = []
    try:
        py_frameworks = (tech_stack.get("python") or {}).get("frameworks") or []
    except Exception:
        py_frameworks = []

    python = _detect_python_startup(repo_dir, py_frameworks)
    docker = _detect_docker_startup(repo_dir)

    recommendations: list[dict[str, Any]] = []
    notes: list[str] = []

    if node.get("present"):
        recommendations.extend(node.get("recommendations", []))
    if python.get("present"):
        recommendations.extend(python.get("recommendations", []))
    if docker.get("present"):
        recommendations.extend(docker.get("recommendations", []))

    if not recommendations:
        notes.append("No deterministic startup commands found yet. Repo may require manual setup or docs parsing.")

    return {
        "recommendations": recommendations,
        "detected": {
            "node": node,
            "python": python,
            "docker": docker,
        },
        "notes": notes,
    }