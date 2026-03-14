from __future__ import annotations

import json
from pathlib import Path

from agent.app.services.git_ops import git_clone, git_get_head_sha
from agent.app.services.route_map_fastapi import extract_fastapi_route_map
from agent.app.services.scanner import basic_repo_scan
from agent.app.services.startup import detect_startup_workflow
from agent.app.services.tech_stack import detect_tech_stack
from agent.app.database import SessionLocal, Snapshot


def analyze_snapshot(repo_dir: Path, clone_url: str, ref: str | None) -> dict:
    git_clone(clone_url=clone_url, dest_dir=repo_dir, ref=ref)
    head_sha = git_get_head_sha(repo_dir)

    scan = basic_repo_scan(repo_dir)
    tech_stack = detect_tech_stack(repo_dir)
    startup = detect_startup_workflow(repo_dir, tech_stack=tech_stack)

    # framework-specific route mapping (best-effort)
    fastapi_routes = extract_fastapi_route_map(repo_dir)

    return {
        "commit_sha": head_sha,
        "scan": scan,
        "tech_stack": tech_stack,
        "startup": startup,
        "routes": {
            "fastapi": fastapi_routes,
        },
    }


def write_results(snapshot_id: str, results: dict) -> None:
    with SessionLocal() as db:
        snap = db.query(Snapshot).filter(Snapshot.snapshot_id == snapshot_id).first()
        if snap:
            snap.commit_sha = results.get("commit_sha")
            snap.results = results
            db.commit()