from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    repo_url: str = Field(..., description="GitHub repo URL (https or ssh)")
    ref: Optional[str] = Field(None, description="Branch/tag/commit (optional)")


class AnalyzeResponse(BaseModel):
    job_id: str
    snapshot_id: str


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    question: str = Field(..., description="The user's question about the repository")
    history: Optional[list[ChatMessage]] = Field(default_factory=list, description="Previous conversation context")


class SourceInfo(BaseModel):
    file_path: str


class ChatResponse(BaseModel):
    answer: str = Field(..., description="The AI's answer")
    sources: Optional[list[SourceInfo]] = Field(default_factory=list, description="Files referenced to answer the question")


JobStatus = Literal["queued", "running", "done", "error"]


class JobInfo(BaseModel):
    job_id: str
    snapshot_id: str
    status: JobStatus
    stage: str
    message: str
    created_at: datetime
    updated_at: datetime
    error: Optional[str] = None


class SnapshotSummary(BaseModel):
    snapshot_id: str
    repo_url: str
    owner: str
    repo: str
    ref: Optional[str]
    commit_sha: Optional[str]
    created_at: datetime
    results: dict[str, Any]
