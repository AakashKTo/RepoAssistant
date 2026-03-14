import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import create_engine, Column, String, Integer, DateTime, JSON, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker
from agent.app.config import settings

engine = create_engine(settings.database_url, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class Snapshot(Base):
    __tablename__ = "snapshots"
    
    snapshot_id = Column(String, primary_key=True, index=True)
    owner = Column(String, nullable=False)
    repo = Column(String, nullable=False)
    repo_url = Column(String, nullable=False)
    ref = Column(String, nullable=True)
    commit_sha = Column(String, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    analysis_version = Column(Integer, default=1)
    host = Column(String, nullable=True)
    
    # Store complete JSON results here
    results = Column(JSON, default=dict)

class Job(Base):
    __tablename__ = "jobs"
    
    job_id = Column(String, primary_key=True, index=True)
    snapshot_id = Column(String, ForeignKey("snapshots.snapshot_id"), index=True)
    status = Column(String, nullable=False, default="queued")
    stage = Column(String, nullable=False, default="queued")
    message = Column(String, nullable=False, default="Job created")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    error = Column(String, nullable=True)

from sqlalchemy import text

def init_db():
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(bind=engine)
