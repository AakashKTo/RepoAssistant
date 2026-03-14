from __future__ import annotations

import json
import platform
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.app.config import settings
from agent.app.database import SessionLocal, Snapshot


@dataclass(frozen=True)
class SnapshotPaths:
    snapshot_id: str
    root_dir: Path
    repo_dir: Path
    meta_path: Path
    results_path: Path


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_data_dir() -> Path:
    p = Path(settings.data_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def create_snapshot(owner: str, repo: str, repo_url: str, ref: str | None) -> SnapshotPaths:
    base = ensure_data_dir() / "snapshots"
    base.mkdir(parents=True, exist_ok=True)

    snapshot_id = uuid4().hex
    root_dir = base / snapshot_id
    root_dir.mkdir(parents=True, exist_ok=False)

    repo_dir = root_dir / "repo"  # do NOT create this directory; git clone will create it
    meta_path = root_dir / "meta.json"
    results_path = root_dir / "results.json"

    # DB insertion instead of JSON files
    with SessionLocal() as db:
        snap = Snapshot(
            snapshot_id=snapshot_id,
            owner=owner,
            repo=repo,
            repo_url=repo_url,
            ref=ref,
            host=platform.node() or None,
            results={}
        )
        db.add(snap)
        db.commit()

    return SnapshotPaths(
        snapshot_id=snapshot_id,
        root_dir=root_dir,
        repo_dir=repo_dir,
        meta_path=meta_path,
        results_path=results_path,
    )


def read_snapshot_meta(snapshot_id: str) -> dict:
    with SessionLocal() as db:
        snap = db.query(Snapshot).filter(Snapshot.snapshot_id == snapshot_id).first()
        if not snap:
            return {}
        return {
            "snapshot_id": snap.snapshot_id,
            "owner": snap.owner,
            "repo": snap.repo,
            "repo_url": snap.repo_url,
            "ref": snap.ref,
            "commit_sha": snap.commit_sha,
            "created_at": snap.created_at.isoformat() if hasattr(snap.created_at, 'isoformat') else str(snap.created_at),
            "analysis_version": snap.analysis_version,
            "host": snap.host,
        }

def read_snapshot_results(snapshot_id: str) -> dict:
    with SessionLocal() as db:
        snap = db.query(Snapshot).filter(Snapshot.snapshot_id == snapshot_id).first()
        if not snap or not snap.results:
            return {}
        return snap.results
