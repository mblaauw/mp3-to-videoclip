"""Jobs: list, get, cancel."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from mp3_to_videoclip.api.errors import ApiError

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class JobProgress(BaseModel):
    done: int = 0
    total: int = 0
    unit: str = ""
    phase: str = ""
    message: str | None = None


class JobOut(BaseModel):
    id: str
    kind: str
    project: str
    status: str
    progress: JobProgress
    cost_usd: float
    error: str | None = None
    queued_at: float | None = None
    started_at: float | None = None
    finished_at: float | None = None
    historical: bool = False
    blocking: bool = False


class JobDetailOut(JobOut):
    log: list[str] = Field(default_factory=list)


class CancelOut(BaseModel):
    cancelled: bool
    status: str


@router.get("", response_model=list[JobOut])
async def list_jobs(request: Request, project: str | None = None):
    runner = request.app.state.runner
    return runner.list_jobs(project=project)


@router.get("/{job_id}", response_model=JobDetailOut)
async def get_job(job_id: str, request: Request):
    runner = request.app.state.runner
    job = runner.get(job_id)
    if job is None:
        raise ApiError(404, "job not found", "job_not_found")
    return job


@router.post("/{job_id}/cancel", response_model=CancelOut)
async def cancel_job(job_id: str, request: Request):
    runner = request.app.state.runner
    if not runner.cancel(job_id):
        raise ApiError(404, "job not found or already finished", "job_not_found")
    return {"cancelled": True, "status": runner.get(job_id).status}
