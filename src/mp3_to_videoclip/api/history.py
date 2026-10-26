"""Artifact history: list snapshots and restore the previous value."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from mp3_to_videoclip.api._helpers import project_root
from mp3_to_videoclip.domain import history

router = APIRouter(prefix="/api/projects/{slug}/history", tags=["history"])


@router.get("/{artifact}")
async def get_history(slug: str, artifact: str, request: Request):
    root = project_root(request, slug)
    try:
        return {"artifact": artifact, "snapshots": history.snapshots(root, artifact)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{artifact}/restore")
async def restore_history(slug: str, artifact: str, request: Request):
    root = project_root(request, slug)
    try:
        return history.restore(root, artifact)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
