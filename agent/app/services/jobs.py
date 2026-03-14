from __future__ import annotations

import traceback
from datetime import datetime, timezone
from typing import Callable, Dict, Optional
from uuid import uuid4

from agent.app.models import JobInfo
from agent.app.database import SessionLocal, Job as DBJob


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobManager:
    def create(self, snapshot_id: str, stage: str = "queued", message: str = "Job created") -> JobInfo:
        job_id = uuid4().hex
        with SessionLocal() as db:
            db_job = DBJob(
                job_id=job_id,
                snapshot_id=snapshot_id,
                status="queued",
                stage=stage,
                message=message
            )
            db.add(db_job)
            db.commit()
            
        return self.get(job_id)

    def get(self, job_id: str) -> Optional[JobInfo]:
        with SessionLocal() as db:
            db_job = db.query(DBJob).filter(DBJob.job_id == job_id).first()
            if not db_job:
                return None
            return JobInfo(
                job_id=db_job.job_id,
                snapshot_id=db_job.snapshot_id,
                status=db_job.status,
                stage=db_job.stage,
                message=db_job.message,
                created_at=db_job.created_at,
                updated_at=db_job.updated_at,
                error=db_job.error,
            )

    def update(self, job_id: str, **kwargs) -> None:
        with SessionLocal() as db:
            db_job = db.query(DBJob).filter(DBJob.job_id == job_id).first()
            if db_job:
                for k, v in kwargs.items():
                    setattr(db_job, k, v)
                db.commit()

# Singleton instance for backward compatibility
jobs_manager = JobManager()
