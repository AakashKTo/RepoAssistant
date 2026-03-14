from __future__ import annotations

import os
import subprocess
from pathlib import Path


def git_clone(clone_url: str, dest_dir: Path, ref: str | None = None) -> None:
    # Ensure dest_dir does not already exist (git clone can fail otherwise)
    if dest_dir.exists():
        # If it's empty, remove it
        try:
            next(dest_dir.iterdir())
            raise RuntimeError(f"Destination already exists and is not empty: {dest_dir}")
        except StopIteration:
            dest_dir.rmdir()

    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"  # don't hang waiting for credentials

    cmd = ["git", "clone", "--depth", "1"]
    if ref:
        cmd += ["--branch", ref]
    cmd += [clone_url, str(dest_dir)]

    subprocess.run(cmd, check=True, capture_output=True, text=True, env=env)


def git_get_head_sha(repo_dir: Path) -> str:
    cmd = ["git", "-C", str(repo_dir), "rev-parse", "HEAD"]
    res = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return res.stdout.strip()
