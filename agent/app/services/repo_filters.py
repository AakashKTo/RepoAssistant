from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


DEFAULT_IGNORE_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".idea",
    ".vscode",
}

# Keep this conservative so we don’t accidentally skip useful code.
DEFAULT_MINIFIED_GLOBS = [
    "*.min.js",
    "*.min.css",
    "*.bundle.js",
    "*.chunk.js",
    "*.map",
]

# Common binary-ish extensions we should not feed into analysis/indexing.
BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp",
    ".zip", ".gz", ".tgz", ".tar", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib",
    ".class", ".jar", ".war", ".ear",
    ".mp3", ".mp4", ".mov", ".avi", ".mkv",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".sqlite", ".db",
    ".npy", ".npz",
    ".pkl",
}

# Explicitly supported document formats that might be binary/large but have dedicated loaders (e.g., PyPDF, Notebook)
DOCUMENT_EXTS = {
    ".pdf",
    ".ipynb",
}

DEFAULT_MAX_FILE_BYTES = 10_000_000  # 10MB


def _rel_posix(path: Path, repo_dir: Path) -> str:
    return path.relative_to(repo_dir).as_posix()


def _matches_any_glob(name_or_path: str, globs: Iterable[str]) -> bool:
    for g in globs:
        if fnmatch.fnmatch(name_or_path, g):
            return True
    return False


def _is_probably_binary_content(path: Path, sample_size: int = 8192) -> bool:
    # Simple and safe heuristic: presence of NUL bytes in the first chunk.
    try:
        data = path.read_bytes()[:sample_size]
    except Exception:
        # If we cannot read it, treat as non-analyzable.
        return True
    return b"\x00" in data


def classify_file(
    path: Path,
    repo_dir: Path,
    *,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    minified_globs: Iterable[str] = DEFAULT_MINIFIED_GLOBS,
) -> tuple[bool, Optional[str]]:
    """
    Returns (is_candidate, skip_reason).
    skip_reason is None if candidate.
    """
    try:
        if path.is_symlink():
            return False, "symlink"
    except Exception:
        # If OS blocks symlink checks, don’t risk it.
        return False, "symlink_check_failed"

    try:
        size = path.stat().st_size
    except Exception:
        return False, "stat_failed"

    if size > max_file_bytes:
        return False, "too_large"

    suffix = path.suffix.lower()
    if suffix in BINARY_EXTS:
        return False, "binary_ext"

    name = path.name.lower()
    rel = _rel_posix(path, repo_dir)

    if _matches_any_glob(name, minified_globs) or _matches_any_glob(rel, minified_globs):
        return False, "minified_or_map"

    # Bypass the binary safety heuristic for explicitly supported document formats
    if suffix in DOCUMENT_EXTS:
        return True, None

    if _is_probably_binary_content(path):
        return False, "binary_content"

    return True, None


def collect_analyzable_files(
    repo_dir: Path,
    *,
    ignore_dirs: Iterable[str] = DEFAULT_IGNORE_DIRS,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    minified_globs: Iterable[str] = DEFAULT_MINIFIED_GLOBS,
    collect_paths: bool = False,
    max_paths: int = 20000,
) -> dict[str, Any]:
    """
    Walks the repo and returns:
    - stats (counts + skipped reasons)
    - optionally the list of analyzable relative paths (posix style)
    """
    ignore_dirs_set = set(ignore_dirs)

    stats: dict[str, Any] = {
        "files_seen": 0,
        "candidates": 0,
        "skipped": {},
    }
    paths: list[str] = []

    for root, dirs, files in os.walk(repo_dir):
        # prune ignored dirs early (performance + correctness)
        pruned = [d for d in dirs if d in ignore_dirs_set]
        if pruned:
            stats["skipped"]["ignored_dir"] = stats["skipped"].get("ignored_dir", 0) + len(pruned)
        dirs[:] = [d for d in dirs if d not in ignore_dirs_set]

        for f in files:
            p = Path(root) / f
            stats["files_seen"] += 1

            ok, reason = classify_file(
                p,
                repo_dir,
                max_file_bytes=max_file_bytes,
                minified_globs=minified_globs,
            )
            if ok:
                stats["candidates"] += 1
                if collect_paths and len(paths) < max_paths:
                    paths.append(_rel_posix(p, repo_dir))
            else:
                if reason:
                    stats["skipped"][reason] = stats["skipped"].get(reason, 0) + 1

    return {
        "max_file_bytes": max_file_bytes,
        "ignore_dirs": sorted(list(ignore_dirs_set)),
        "minified_globs": list(minified_globs),
        "paths": paths,
        "stats": stats,
    }