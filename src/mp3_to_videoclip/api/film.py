"""Film stage: graphics spec/review, preview/base/final render, exports."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from mp3_to_videoclip import production as P
from mp3_to_videoclip.api._helpers import project_root, valid_slug
from mp3_to_videoclip.domain import archive
from mp3_to_videoclip.storage import inside, read_json

router = APIRouter(prefix="/api/projects/{slug}", tags=["film"])

KINDS = ("preview", "base", "final")


@router.get("/graphics")
async def get_graphics(slug: str, request: Request):
    root = project_root(request, slug)
    path = root / "work" / "graphics-spec.json"
    if not path.is_file():
        return {"available": False}
    return {"available": True, "spec": read_json(path)}


@router.get("/graphics-review")
async def get_graphics_review(slug: str, request: Request):
    """The preflight samples the graphics approval must inspect."""
    root = project_root(request, slug)
    path = root / P.STAGE_FILES["graphics"]
    if not path.is_file():
        return {"available": False}
    review = read_json(path)
    samples = []
    for relative in sorted(review.get("samples", {})):
        target = root / relative
        if not target.is_file():
            continue
        name = target.name
        samples.append(
            {
                "name": name,
                "url": f"/api/projects/{slug}/graphics-review/{name}",
                "sha256": review["samples"][relative],
            }
        )
    current = True
    reason = None
    try:
        from mp3_to_videoclip.signature import validate_review

        validate_review(root, P.load_project(root))
    except OSError:
        current = False
        reason = "the graphics review is incomplete; render a current base and review it"
    except (ValueError, KeyError) as exc:
        current = False
        reason = str(exc)
    return {
        "available": True,
        "current": current,
        "reason": reason,
        "warning": review.get("warning"),
        "base": review.get("base"),
        "samples": samples,
    }


@router.get("/graphics-review/{name}")
async def get_graphics_sample(slug: str, name: str, request: Request):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.png", name):
        raise HTTPException(status_code=404, detail="unknown graphics sample")
    root = project_root(request, slug)
    path = root / P.STAGE_FILES["graphics"]
    if not path.is_file():
        raise HTTPException(status_code=404, detail="graphics review is missing")
    matches = [rel for rel in read_json(path).get("samples", {}) if Path(rel).name == name]
    if len(matches) != 1:
        raise HTTPException(status_code=404, detail="unknown graphics sample")
    try:
        target = inside(root, matches[0])
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="unknown graphics sample") from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail="graphics sample is missing")
    return FileResponse(target, media_type="image/png")


@router.get("/edit")
async def get_edit(slug: str, request: Request):
    """The edit list plus the report computed from the current board."""
    from mp3_to_videoclip import edits

    root = project_root(request, slug)
    try:
        return edits.summary(root)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/edit/seed")
async def seed_edit(slug: str, request: Request):
    """Move timing ownership from the storyboard to a first edit list."""
    from mp3_to_videoclip import edits

    root = project_root(request, slug)
    try:
        edit = edits.seed_edit(root)
        return edits.summary(root, edit)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/edit")
async def put_edit(slug: str, request: Request, payload: dict):
    """Save the whole edit and return the report the Editor must read."""
    from mp3_to_videoclip import edits

    root = project_root(request, slug)
    value = payload.get("edit", payload)
    try:
        edit = edits.save_edit(root, value)
        return edits.summary(root, edit)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
    if kind not in KINDS:
        raise HTTPException(status_code=400, detail="kind must be preview, base or final")
    if kind in ("base", "final"):
        try:
            P.require_approval(root, "stills")
            if kind == "final" and P.requires_signature(root):
                P.require_approval(root, "graphics")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    runner = getattr(request.app.state, "runner", None)
    if runner is None:
        return {"error": "job runner unavailable"}
    import asyncio

    from mp3_to_videoclip import services

    async def work():
        fn = {
            "preview": services.render.render_preview,
            "base": services.render.render_base,
            "final": services.render.render_final,
        }[kind]
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


def _archive_root(request: Request, slug: str) -> Path:
    root = Path(getattr(request.app.state, "projects_dir", "projects")) / slug
    if not valid_slug(slug) or not root.is_dir() or not archive.is_archived(root):
        raise HTTPException(status_code=404, detail="archived film not found")
    return root


@router.get("/archive/render")
async def play_archive_render(slug: str, request: Request):
    """The delivered render, served read-only without exposing its path."""
    root = _archive_root(request, slug)
    film = archive.read(root)
    if film.render is None or not film.render.is_file():
        raise HTTPException(status_code=404, detail="archived render is missing")
    if not film.render.resolve().is_relative_to(root.resolve()):
        raise HTTPException(status_code=404, detail="archived render is missing")
    return FileResponse(
        film.render,
        media_type="video/mp4",
        filename=film.render.name,
        content_disposition_type="inline",
    )


@router.get("/archive/stills/{index}")
async def play_archive_still(slug: str, index: int, request: Request):
    """One preserved still by position; never a caller-supplied path."""
    root = _archive_root(request, slug)
    film = archive.read(root)
    if index < 0 or index >= len(film.stills):
        raise HTTPException(status_code=404, detail="archived still not found")
    target = film.stills[index]
    if not target.is_file() or not target.resolve().is_relative_to(root.resolve()):
        raise HTTPException(status_code=404, detail="archived still is missing")
    return FileResponse(target, content_disposition_type="inline")


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
