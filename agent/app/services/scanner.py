from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
from typing import Any

from agent.app.services.repo_filters import DEFAULT_IGNORE_DIRS, collect_analyzable_files


KEY_FILES = [
    "README.md",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
]

EXT_TO_LANG = {
    ".py": "Python",
    ".ipynb": "Jupyter",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".go": "Go",
    ".rb": "Ruby",
    ".cs": "C#",
    ".php": "PHP",
    ".rs": "Rust",
    ".kt": "Kotlin",
    ".swift": "Swift",
    ".c": "C",
    ".h": "C/C++ Header",
    ".cpp": "C++",
    ".hpp": "C++ Header",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".md": "Markdown",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".json": "JSON",
    ".toml": "TOML",
    ".sql": "SQL",
    ".sh": "Shell",
    ".ps1": "PowerShell",
    ".tf": "Terraform",
}


def basic_repo_scan(repo_dir: Path) -> dict[str, Any]:
    ext_counts: Counter[str] = Counter()
    lang_counts: Counter[str] = Counter()
    total_files = 0

    present_key_files: list[str] = []
    present_workflows: list[str] = []

    for k in KEY_FILES:
        if (repo_dir / k).exists():
            present_key_files.append(k)

    workflows_dir = repo_dir / ".github" / "workflows"
    if workflows_dir.exists():
        for p in workflows_dir.glob("*.yml"):
            present_workflows.append(str(p.relative_to(repo_dir)))
        for p in workflows_dir.glob("*.yaml"):
            present_workflows.append(str(p.relative_to(repo_dir)))

    ignore_dirs = set(DEFAULT_IGNORE_DIRS)

    for root, dirs, files in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        for f in files:
            total_files += 1
            p = Path(root) / f
            suffix = p.suffix.lower() if p.suffix else "<noext>"
            ext_counts[suffix] += 1

            lang = EXT_TO_LANG.get(p.suffix.lower())
            if lang:
                lang_counts[lang] += 1

    top_ext = [{"ext": k, "count": v} for k, v in ext_counts.most_common(25)]
    top_lang = [{"language": k, "count": v} for k, v in lang_counts.most_common(20)]

    candidates = collect_analyzable_files(repo_dir, collect_paths=False)

    return {
        "total_files": total_files,
        "top_languages": top_lang,
        "top_extensions": top_ext,
        "analysis_candidates": {
            "files_seen": candidates["stats"]["files_seen"],
            "candidates": candidates["stats"]["candidates"],
            "skipped": candidates["stats"]["skipped"],
            "max_file_bytes": candidates["max_file_bytes"],
            "ignore_dirs": candidates["ignore_dirs"],
            "minified_globs": candidates["minified_globs"],
        },
        "key_files_present": present_key_files,
        "github_workflows": sorted(present_workflows),
        "notes": [
            "analysis_candidates is the filtered set we will later index for Q&A and workflow extraction.",
        ],
    }