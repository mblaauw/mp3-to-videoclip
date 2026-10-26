"""Artifact rating endpoints: thumbs are evaluation signals, not approvals."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from mp3_to_videoclip import ratings
from mp3_to_videoclip.api._helpers import project_root

router = APIRouter(prefix="/api/projects/{slug}", tags=["ratings"])


@router.get("/ratings")
async def get_ratings(slug: str, request: Request, artifact: str | None = None):
    root = project_root(request, slug)
    try:
        if artifact is None:
            return {"artifacts": ratings.all_summary(root)}
        return ratings.summary(root, artifact)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/ratings")
async def post_rating(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    artifact = payload.get("artifact")
    rating = payload.get("rating")
    note = payload.get("note", "")
    if not isinstance(artifact, str):
        raise HTTPException(status_code=400, detail="artifact is required")
    if not isinstance(rating, str):
        raise HTTPException(status_code=400, detail="rating is required")
    if not isinstance(note, str):
        raise HTTPException(status_code=400, detail="note must be text")
    try:
        entry = ratings.add(root, artifact, rating, note)
        return {"entry": entry, "summary": ratings.summary(root, artifact)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
