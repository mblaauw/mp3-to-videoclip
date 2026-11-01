"""Artifact history: list snapshots and restore the previous value."""

from __future__ import annotations

from fastapi import APIRouter, Request

from mp3_to_videoclip.api._helpers import project_root
from mp3_to_videoclip.domain import history

router = APIRouter(prefix="/api/projects/{slug}/history", tags=["history"])


@router.get("/{artifact}")
async def get_history(slug: str, artifact: str, request: Request):
    root = project_root(request, slug)
    return {"artifact": artifact, "snapshots": history.snapshots(root, artifact)}


@router.post("/{artifact}/restore")
async def restore_history(slug: str, artifact: str, request: Request):
    root = project_root(request, slug)
    return history.restore(root, artifact)
