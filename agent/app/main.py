from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from sse_starlette.sse import EventSourceResponse

from agent.app.config import settings
from agent.app.models import AnalyzeRequest, AnalyzeResponse, JobInfo, SnapshotSummary, ChatRequest
from agent.app.services.analyzer import analyze_snapshot, write_results
from agent.app.services.github_url import parse_github_repo_url
from agent.app.services.jobs import jobs_manager
from agent.app.storage import create_snapshot, read_snapshot_meta, read_snapshot_results
from agent.app.services.rag import ingest_snapshot, stream_question
from agent.app.database import init_db, SessionLocal, Snapshot

# Initialize database schemas
init_db()

app = FastAPI(title="Repo Understanding Assistant (Local Agent)", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.allow_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _utcnow():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/healthz")
def healthz():
    return {"ok": True, "ts": _utcnow().isoformat()}


# ---------------------------------------------------------------------------
# Config / capabilities (used by frontend to display active model name)
# ---------------------------------------------------------------------------

@app.get("/api/config")
def get_config():
    """Return non-sensitive runtime config the frontend cares about."""
    return {
        "ollama_model": settings.ollama_model,
        "ollama_embed_model": settings.ollama_embed_model,
        "ollama_base_url": settings.ollama_base_url,
    }


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest):
    try:
        ref_info = parse_github_repo_url(req.repo_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    import urllib.request
    import urllib.error

    # Validate that the repository is public and actually exists
    try:
        check_url = f"https://github.com/{ref_info.owner}/{ref_info.repo}"
        req_check = urllib.request.Request(check_url, method="HEAD")
        with urllib.request.urlopen(req_check):
            pass
    except urllib.error.HTTPError as e:
        if e.code in (404, 401, 403):
            raise HTTPException(status_code=400, detail="Repository is private or does not exist.")
        raise HTTPException(status_code=400, detail=f"Failed to access repository: {e.reason}")
    except urllib.error.URLError:
        raise HTTPException(status_code=400, detail="Could not reach GitHub to verify repository access.")

    ref = req.ref or ref_info.ref

    snapshot = create_snapshot(
        owner=ref_info.owner,
        repo=ref_info.repo,
        repo_url=req.repo_url,
        ref=ref,
    )

    job = jobs_manager.create(snapshot_id=snapshot.snapshot_id, stage="queued", message="Queued analysis")

    from agent.app.worker import run_analysis_task
    run_analysis_task.delay(
        job_id=job.job_id,
        snapshot_id=snapshot.snapshot_id,
        repo_dir_str=str(snapshot.repo_dir),
        clone_url=ref_info.clone_url,
        ref=ref,
    )

    return AnalyzeResponse(job_id=job.job_id, snapshot_id=snapshot.snapshot_id)


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

@app.get("/api/jobs/{job_id}", response_model=JobInfo)
def get_job(job_id: str):
    job = jobs_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/jobs/{job_id}/stream")
async def stream_job(job_id: str):
    """Server-Sent Events stream: pushes job state on every stage change."""
    async def event_generator():
        last_stage = None
        while True:
            job = jobs_manager.get(job_id)
            if not job:
                yield {"event": "error", "data": "Job not found"}
                break

            if job.stage != last_stage or job.status in ("done", "error"):
                last_stage = job.stage
                yield {"event": "message", "data": job.model_dump_json()}

            if job.status in ("done", "error"):
                break

            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------

@app.get("/api/snapshots")
def list_snapshots(limit: int = 20, offset: int = 0):
    """Return the most recent snapshots (used for the home page history panel)."""
    with SessionLocal() as db:
        rows = (
            db.query(Snapshot)
            .order_by(Snapshot.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [
            {
                "snapshot_id": r.snapshot_id,
                "owner": r.owner,
                "repo": r.repo,
                "repo_url": r.repo_url,
                "ref": r.ref,
                "created_at": r.created_at.isoformat() if hasattr(r.created_at, "isoformat") else str(r.created_at),
            }
            for r in rows
        ]


@app.get("/api/snapshots/{snapshot_id}", response_model=SnapshotSummary)
def get_snapshot(snapshot_id: str):
    meta = read_snapshot_meta(snapshot_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    results = read_snapshot_results(snapshot_id)

    return SnapshotSummary(
        snapshot_id=snapshot_id,
        repo_url=meta["repo_url"],
        owner=meta["owner"],
        repo=meta["repo"],
        ref=meta.get("ref"),
        commit_sha=results.get("commit_sha"),
        created_at=datetime.fromisoformat(meta["created_at"]),
        results=results,
    )


@app.get("/api/snapshots/{snapshot_id}/files/{file_path:path}")
def get_file_content(snapshot_id: str, file_path: str):
    """
    Return the raw content of a file inside a cloned snapshot's repository.
    Used by the source-code drawer in the dashboard.
    """
    meta = read_snapshot_meta(snapshot_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    data_dir = Path(settings.data_dir) / "snapshots" / snapshot_id / "repo"

    # Resolve and guard against path traversal
    try:
        target = (data_dir / file_path).resolve()
        data_dir_resolved = data_dir.resolve()
        if not str(target).startswith(str(data_dir_resolved)):
            raise HTTPException(status_code=400, detail="Invalid file path")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid file path")

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found in snapshot")

    # Cap at 500 KB — no one needs to stream a minified bundle in the drawer
    max_bytes = 500 * 1024
    try:
        with target.open("rb") as fh:
            content = fh.read(max_bytes)
        text = content.decode("utf-8", errors="replace")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not read file: {e}")

    return PlainTextResponse(content=text)


# ---------------------------------------------------------------------------
# Chat (RAG)
# ---------------------------------------------------------------------------

@app.post("/api/chat/{snapshot_id}")
async def chat(snapshot_id: str, req: ChatRequest):
    from fastapi.responses import StreamingResponse
    try:
        history = [msg.model_dump() for msg in req.history] if req.history else []
        return StreamingResponse(
            stream_question(snapshot_id, req.question, history=history),
            media_type="application/x-ndjson",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
