"""Jobs: list, get, cancel."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
async def list_jobs(request: Request, project: str | None = None):
    runner = request.app.state.runner
    jobs = runner.list_jobs(project=project)
    return [
        {
            "id": j.id,
            "kind": j.kind,
            "project": j.project,
            "status": j.status,
            "progress": j.progress,
            "cost_usd": j.cost_usd,
            "error": j.error,
            "started_at": j.started_at,
            "finished_at": j.finished_at,
        }
        for j in jobs
    ]


@router.get("/{job_id}")
async def get_job(job_id: str, request: Request):
    runner = request.app.state.runner
    job = runner.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return {
        "id": job.id,
        "kind": job.kind,
        "project": job.project,
        "status": job.status,
        "progress": job.progress,
        "cost_usd": job.cost_usd,
        "log": job.log,
        "error": job.error,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str, request: Request):
    runner = request.app.state.runner
    if not runner.cancel(job_id):
        raise HTTPException(status_code=404, detail="job not found or already finished")
    return {"cancelled": True}
