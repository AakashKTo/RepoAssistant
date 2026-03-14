import traceback
from pathlib import Path
from celery import Celery
from agent.app.config import settings

celery_app = Celery(
    "repo_assistant",
    broker=settings.redis_url,
    backend=settings.redis_url
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

from celery.schedules import crontab
import time
import shutil

celery_app.conf.beat_schedule = {
    'cleanup-old-repos-every-hour': {
        'task': 'agent.app.worker.cleanup_old_repos_task',
        'schedule': crontab(minute=0, hour='*'), # Run at the top of every hour
    },
}

@celery_app.task
def cleanup_old_repos_task():
    """Removes repository clones older than 2 hours to free up disk space."""
    repos_dir = Path(settings.data_dir) / "repos"
    if not repos_dir.exists():
        return "No repos directory found"
    
    deleted_count = 0
    now = time.time()
    threshold = 2 * 3600 # 2 hours in seconds
    
    for repo_path in repos_dir.iterdir():
        if repo_path.is_dir():
            try:
                # Use modification time to determine age
                mtime = repo_path.stat().st_mtime
                if (now - mtime) > threshold:
                    shutil.rmtree(repo_path, ignore_errors=True)
                    deleted_count += 1
            except Exception as e:
                print(f"Failed to delete {repo_path}: {e}")
                
    return f"Deleted {deleted_count} old repositories"

@celery_app.task
def embed_batch_task(snapshot_id: str, repo_dir_str: str, rel_paths: list[str]) -> int:
    """Subtask that embeds a batch of files, preventing local LLM overload."""
    from agent.app.services.rag import process_file_batch
    try:
        return process_file_batch(snapshot_id, Path(repo_dir_str), rel_paths)
    except Exception as e:
        print(f"Failed to embed batch: {e}")
        return 0

@celery_app.task
def finalize_analysis_task(chunk_counts, job_id: str, snapshot_id: str, result: dict):
    from agent.app.services.analyzer import write_results
    from agent.app.services.jobs import jobs_manager
    
    try:
        num_chunks = sum(chunk_counts) if chunk_counts else 0
        result["rag_chunks_indexed"] = num_chunks
        
        jobs_manager.update(job_id, stage="writing_results", message="Writing results")
        write_results(snapshot_id, result)
        
        jobs_manager.update(job_id, status="done", stage="done", message="Job finished successfully")
    except Exception as e:
        tb = traceback.format_exc()
        jobs_manager.update(job_id, status="error", stage="error", message=str(e), error=tb)

@celery_app.task
def run_analysis_task(job_id: str, snapshot_id: str, repo_dir_str: str, clone_url: str, ref: str):
    from agent.app.services.analyzer import analyze_snapshot, write_results
    from agent.app.services.rag import ingest_snapshot
    from agent.app.services.jobs import jobs_manager
    
    repo_dir = Path(repo_dir_str)
    
    try:
        jobs_manager.update(job_id, status="running", stage="cloning", message="Cloning repository")
        
        result = analyze_snapshot(
            repo_dir=repo_dir,
            clone_url=clone_url,
            ref=ref,
        )
        
        jobs_manager.update(job_id, stage="embedding", message="Generating embeddings for code concurrently")
        try:
            from celery import chord
            from agent.app.services.repo_filters import collect_analyzable_files
            
            candidates = collect_analyzable_files(repo_dir, collect_paths=True)
            paths = candidates.get("paths", [])
            
            # Expose file list in results so the UI can render a file tree
            result["scanned_files"] = paths
            
            # Batch the file paths to prevent overwhelming local Ollama API
            BATCH_SIZE = 20
            batched_paths = [paths[i:i + BATCH_SIZE] for i in range(0, len(paths), BATCH_SIZE)]
            
            header = [embed_batch_task.s(snapshot_id, repo_dir_str, batch) for batch in batched_paths]
            callback = finalize_analysis_task.s(job_id, snapshot_id, result)
            
            # Fire and forget: the chord executes the header in parallel, then the callback
            chord(header)(callback)
            
        except Exception as e:
            tb = traceback.format_exc()
            jobs_manager.update(job_id, status="error", stage="error", message=str(e), error=tb)
            
    except Exception as e:
        tb = traceback.format_exc()
        jobs_manager.update(job_id, status="error", stage="error", message=str(e), error=tb)
