"""Images stage: status, estimate, generate, select, keep/redo."""

from __future__ import annotations

from fastapi import APIRouter, Request

from mp3_to_videoclip import production as P
from mp3_to_videoclip.api._helpers import project_root

router = APIRouter(prefix="/api/projects/{slug}", tags=["images"])


@router.get("/images")
async def get_images(slug: str, request: Request):
    root = project_root(request, slug)
    return P.status(root)


@router.post("/images/estimate")
async def estimate_images(slug: str, request: Request, payload: dict):
    project_root(request, slug)
    shot_ids = payload.get("shot_ids", [])
    # Return a simple estimate based on the number of shots.
    return {"shot_ids": shot_ids, "estimated_count": len(shot_ids)}


@router.post("/images/select")
async def select_version(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    shot_id = payload.get("shot_id")
    version = payload.get("version")
    if shot_id is None or version is None:
        return {"error": "shot_id and version required"}
    P.select_asset(root, shot_id, version)
    return {"selected": shot_id, "version": version}
