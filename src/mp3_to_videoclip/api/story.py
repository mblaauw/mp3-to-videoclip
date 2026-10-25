"""Story stage: brief and treatments."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from mp3_to_videoclip import production as P
from mp3_to_videoclip.api._helpers import project_root

router = APIRouter(prefix="/api/projects/{slug}", tags=["story"])


@router.get("/brief")
async def get_brief(slug: str, request: Request):
    root = project_root(request, slug)
    brief = P.load_brief(root)
    return brief.model_dump()


@router.patch("/brief")
async def update_brief(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    try:
        brief = P.update_brief(root, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return brief.model_dump()


@router.post("/proof-shots")
async def set_proof_shots(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    try:
        shot_ids = P.set_proof_ids(root, payload.get("shot_ids"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"proof_shot_ids": shot_ids}


@router.get("/treatments")
async def get_treatments(slug: str, request: Request):
    root = project_root(request, slug)
    path = root / "work" / "treatments.json"
    if not path.is_file():
        return {"treatments": []}
    import json

    return json.loads(path.read_text())
