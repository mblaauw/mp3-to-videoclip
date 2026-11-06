"""The Publish stage and the measured listening behind its first gate."""

from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from mp3_to_videoclip import publish, watched
from mp3_to_videoclip.api._helpers import project_root
from mp3_to_videoclip.storage import inside, project_lock

router = APIRouter(prefix="/api/projects/{slug}", tags=["publish"])

_THUMB = re.compile(r"[a-z0-9][a-z0-9-]*\.thumb-f\d+-\d\.jpg")


@router.post("/watched")
def post_watched(slug: str, request: Request, payload: dict):
    """Seconds the browser played with the sound on, unioned into the film's record."""
    root = project_root(request, slug)
    total = payload.get("total")
    if total is not None and (isinstance(total, bool) or not isinstance(total, int)):
        raise HTTPException(status_code=400, detail="total is a whole number of seconds")
    with project_lock(root):
        return watched.record(
            root,
            str(payload.get("media") or ""),
            payload.get("seconds") or [],
            sha256=payload.get("sha256"),
            total=total,  # fmt: skip
        )


@router.get("/watched")
def get_watched(slug: str, request: Request, media: str, total: int | None = None):
    return watched.coverage(project_root(request, slug), media, total=total)


@router.get("/publish")
def get_publish(slug: str, request: Request):
    return publish.view(project_root(request, slug))


@router.put("/publish/copy")
def put_copy(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    with project_lock(root):
        publish.set_copy(root, payload)
    return publish.view(root)


@router.post("/publish/check")
def check_copy(slug: str, request: Request, payload: dict):
    """What would stop this copy, without saving it."""
    root = project_root(request, slug)
    return {"problems": publish.check_copy(root, payload if isinstance(payload, dict) else {})}


@router.put("/publish/presets")
def put_presets(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    with project_lock(root):
        publish.set_presets(root, payload.get("presets") or [])
    return publish.view(root)


@router.post("/publish/thumbnails")
async def make_thumbnails(slug: str, request: Request, payload: dict):
    """Three candidates beside the current final, drawn here. Spends nothing."""
    root = project_root(request, slug)
    final = publish.current_final(root)
    if final is None:
        raise HTTPException(status_code=409, detail="render a final first")
    title = payload.get("title")
    if title is not None and not isinstance(title, str):
        raise HTTPException(status_code=400, detail="title is text")

    def run():
        with project_lock(root):
            return publish.thumbnails(root, final, title=title or None)

    await asyncio.to_thread(run)
    return publish.view(root)


@router.post("/publish/choose")
def choose(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    final = publish.current_final(root)
    if final is None:
        raise HTTPException(status_code=409, detail="render a final first")
    with project_lock(root):
        publish.choose_thumbnail(root, final, str(payload.get("name") or ""))
    return publish.view(root)


@router.get("/publish/thumb/{name}")
def get_thumbnail(slug: str, name: str, request: Request):
    if not _THUMB.fullmatch(name):
        raise HTTPException(status_code=404, detail="unknown thumbnail")
    path = inside(project_root(request, slug), f"renders/{name}")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="thumbnail is missing")
    return FileResponse(path, media_type="image/jpeg")


@router.post("/publish/release")
def release(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    with project_lock(root):
        manifest = publish.release(root, note=str(payload.get("note") or ""))
    return {"manifest": manifest, **publish.view(root)}
