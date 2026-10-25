"""Film stage: graphics spec, preview/final render, exports."""

from __future__ import annotations

from fastapi import APIRouter, Request

from mp3_to_videoclip.api._helpers import project_root

router = APIRouter(prefix="/api/projects/{slug}", tags=["film"])


@router.get("/graphics")
async def get_graphics(slug: str, request: Request):
    root = project_root(request, slug)
    path = root / "work" / "graphics-spec.json"
    if not path.is_file():
        return {"available": False}
    from mp3_to_videoclip.storage import read_json

    return {"available": True, "spec": read_json(path)}


@router.get("/exports")
async def list_exports(slug: str, request: Request):
    root = project_root(request, slug)
    renders = root / "renders"
    if not renders.is_dir():
        return {"exports": []}
    return {"exports": [p.name for p in sorted(renders.glob("*.mp4"))]}
