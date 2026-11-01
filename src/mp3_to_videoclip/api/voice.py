"""Voiceover: lines and takes, their quote and run, and what a film sounds like."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from mp3_to_videoclip import production as P
from mp3_to_videoclip import voice
from mp3_to_videoclip.api._helpers import project_root
from mp3_to_videoclip.api.errors import ApiError
from mp3_to_videoclip.domain import budget
from mp3_to_videoclip.generation import authorize, read_quote
from mp3_to_videoclip.storage import inside, project_lock

router = APIRouter(prefix="/api/projects/{slug}", tags=["voice"])

MAX_TAKE_BYTES = 50 * 1024 * 1024
_MEDIA = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".flac": "audio/flac", ".ogg": "audio/ogg"}


def _payload(root: Path) -> dict:
    project = P.load_project(root)
    index = voice.read_index(root)
    fps = project.fps
    rows = []
    lines = voice.lines(root)
    for position, line in enumerate(lines):
        entry = index["lines"].get(line.id, {"selected": None, "versions": []})
        take = voice._selected(root, index, line.id)
        current = voice.is_current(line, take)
        next_line = lines[position + 1] if position + 1 < len(lines) else None
        end = line.start_frame / fps + take["seconds"] if current else None
        rows.append(
            {
                "id": line.id,
                "text": line.text,
                "start_frame": line.start_frame,
                "gain_db": line.gain_db,
                "selected": entry.get("selected"),
                "current": current,
                "end_seconds": end,
                "runs_into_next": bool(
                    next_line is not None and end is not None and end > next_line.start_frame / fps
                ),
                "runs_past_end": bool(end is not None and end > project.duration),
                "takes": [
                    {
                        "version": item["version"],
                        "source": item["source"],
                        "seconds": item["seconds"],
                        "text": item["text"],
                    }
                    for item in entry.get("versions", [])
                ],
            }
        )
    return {"voice": index.get("voice") or voice.DEFAULT_VOICE, "lines": rows}


@router.get("/voice")
def get_voice(slug: str, request: Request):
    return _payload(project_root(request, slug))


@router.get("/film-audio")
def get_film_audio(slug: str, request: Request):
    """What the film sounds like right now, for the Player on the Film stage."""
    root = project_root(request, slug)
    try:
        target = P.film_audio(root, P.load_project(root))
    except (OSError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return FileResponse(
        target,
        media_type=_MEDIA.get(target.suffix.lower(), "application/octet-stream"),
        content_disposition_type="inline",
    )


@router.get("/voice/{line_id}/{version}")
def get_take(slug: str, line_id: str, version: int, request: Request):
    root = project_root(request, slug)
    entry = voice.read_index(root)["lines"].get(line_id, {})
    take = next((v for v in entry.get("versions", []) if v["version"] == version), None)
    if take is None:
        raise HTTPException(status_code=404, detail="that take does not exist")
    path = inside(root, take["path"])
    return FileResponse(
        path,
        media_type=_MEDIA.get(path.suffix.lower(), "application/octet-stream"),
        content_disposition_type="inline",
    )


@router.post("/voice/estimate")
async def estimate_voice(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    with project_lock(root):
        quote = voice.quote_voice(
            root,
            payload.get("line_ids") or None,
            regenerate=bool(payload.get("regenerate")),
        )
    return {
        "quote_id": quote["id"],
        "voice": quote["voice"],
        "tasks": len(quote["tasks"]),
        "characters": sum(len(task["text"]) for task in quote["tasks"]),
        "reserve_usd": quote["reserve_total_usd"],
        "pricing": quote.get("published_pricing"),
        "decision": budget.check(root, quote["reserve_total_usd"]),
    }


@router.post("/voice/generate")
async def generate_voice(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    quote_id = payload.get("quote_id")
    if not quote_id:
        raise HTTPException(status_code=400, detail="estimate the lines first")
    try:
        quote = read_quote(root, quote_id)
    except FileNotFoundError as exc:
        raise ApiError(
            404, "That quote is no longer there. Estimate again.", "quote_missing"
        ) from exc
    if quote.get("kind") != "voice":
        raise HTTPException(status_code=400, detail="this quote is not for voiceover")
    decision = budget.check(root, quote["reserve_total_usd"])
    if not decision["ok"]:
        return {"needs_budget": True, "decision": decision}
    runner = getattr(request.app.state, "runner", None)
    if runner is None:
        raise HTTPException(status_code=503, detail="job runner unavailable")
    with project_lock(root):
        authorize(
            root,
            quote_id,
            quote["reserve_total_usd"],
            payload.get("note") or "user confirmed in Studio",
            via="studio",
            review_confirmed=True,
        )

    async def work():
        def run():
            with project_lock(root):
                return voice.generate_voice(root, quote_id)

        return await asyncio.to_thread(run)

    job_id = runner.submit("voice", slug, work, blocking=True)
    return {"job_id": job_id, "quote_id": quote_id, "reserve_usd": quote["reserve_total_usd"]}


@router.post("/voice/select")
async def select_take(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    try:
        voice.select_take(root, str(payload.get("line_id")), int(payload.get("version")))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _payload(root)


@router.post("/voice/upload")
async def upload_take(slug: str, line_id: str, filename: str, request: Request):
    """The owner's own recording becomes a new take of a line."""
    root = project_root(request, slug)
    suffix = Path(filename).suffix.lower()
    if suffix not in voice.AUDIO_SUFFIXES:
        raise HTTPException(status_code=400, detail="upload an audio file")
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="the upload is empty")
    if len(data) > MAX_TAKE_BYTES:
        raise HTTPException(status_code=413, detail="that recording is too large")
    with tempfile.TemporaryDirectory(prefix="voice-take-") as temp:
        source = Path(temp) / f"take{suffix}"
        source.write_bytes(data)
        voice.import_take(root, line_id, source)
    return _payload(root)
