"""Film stage: graphics spec, preview/final render, exports."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from mp3_to_videoclip import production as P
from mp3_to_videoclip.api._helpers import project_root
from mp3_to_videoclip.storage import inside

router = APIRouter(prefix="/api/projects/{slug}", tags=["film"])


@router.get("/graphics")
async def get_graphics(slug: str, request: Request):
    root = project_root(request, slug)
    path = root / "work" / "graphics-spec.json"
    if not path.is_file():
        return {"available": False}
    from mp3_to_videoclip.storage import read_json

    return {"available": True, "spec": read_json(path)}


@router.get("/preview")
async def preview_input(slug: str, request: Request):
    """The live Player payload: the renderer's shot fields plus local URLs."""
    from mp3_to_videoclip import services

    root = project_root(request, slug)
    try:
        return services.preview.player_input(root, slug)
    except (OSError, ValueError) as exc:
        return {"available": False, "reason": str(exc)}


@router.post("/render")
async def render(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    kind = payload.get("kind", "preview")
    if kind not in ("preview", "final"):
        raise HTTPException(status_code=400, detail="kind must be preview or final")
    if kind == "final":
        try:
            P.require_approval(root, "stills")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    runner = getattr(request.app.state, "runner", None)
    if runner is None:
        return {"error": "job runner unavailable"}
    import asyncio

    from mp3_to_videoclip import services

    async def work():
        fn = services.render.render_final if kind == "final" else services.render.render_preview
        return await asyncio.to_thread(fn, root)

    job_id = runner.submit("render", slug, work)
    return {"job_id": job_id, "kind": kind, "status": "queued"}


def _films(directory: Path) -> list[str]:
    if not directory.is_dir():
        return []
    return [
        path.name
        for path in sorted(
            directory.glob("*.mp4"), key=lambda path: path.stat().st_mtime, reverse=True
        )
    ]


@router.get("/exports")
async def list_exports(slug: str, request: Request):
    root = project_root(request, slug)
    return {
        "exports": _films(root / "renders"),
        "previews": _films(root / "previews"),
    }


@router.get("/film/{kind}/{name}")
async def play_film(slug: str, kind: str, name: str, request: Request):
    if kind not in ("renders", "previews"):
        raise HTTPException(status_code=404, detail="unknown film kind")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.mp4", name):
        raise HTTPException(status_code=404, detail="unknown film")
    root = project_root(request, slug)
    try:
        target = inside(root, f"{kind}/{name}")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="unknown film") from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail="film is missing")
    return FileResponse(
        target,
        media_type="video/mp4",
        filename=name,
        content_disposition_type="inline",
    )
