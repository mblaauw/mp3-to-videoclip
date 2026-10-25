"""Story stage: brief and treatments."""

from __future__ import annotations

from fastapi import APIRouter, Request

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
    brief = P.load_brief(root)
    # JSON merge patch: shallow merge at top level.
    merged = brief.model_dump()
    merged.update(payload)
    from mp3_to_videoclip.models import Brief

    new_brief = Brief.model_validate(merged)
    from mp3_to_videoclip.storage import write_json

    write_json(root / "brief.json", new_brief.model_dump())
    return new_brief.model_dump()


@router.get("/treatments")
async def get_treatments(slug: str, request: Request):
    root = project_root(request, slug)
    path = root / "work" / "treatments.json"
    if not path.is_file():
        return {"treatments": []}
    import json

    return json.loads(path.read_text())
