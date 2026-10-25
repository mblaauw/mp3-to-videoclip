"""Track stage: music analysis, lyrics, transcription."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from mp3_to_videoclip import production as P
from mp3_to_videoclip.api._helpers import project_root
from mp3_to_videoclip.storage import inside

router = APIRouter(prefix="/api/projects/{slug}", tags=["track"])


@router.get("/audio")
async def get_audio(slug: str, request: Request):
    """The source recording, for the in-app player and waveform."""
    root = project_root(request, slug)
    project = P.load_project(root)
    try:
        target = inside(root, project.source)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="audio is missing") from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail="audio is missing")
    return FileResponse(target, media_type="audio/mpeg", content_disposition_type="inline")


@router.get("/track")
async def get_track(slug: str, request: Request):
    root = project_root(request, slug)
    music = None
    music_path = root / "work" / "music.json"
    if music_path.is_file():
        music = __import__("json").loads(music_path.read_text())
    lyrics = None
    lyrics_path = root / "work" / "lyrics.json"
    if lyrics_path.is_file():
        lyrics = __import__("json").loads(lyrics_path.read_text())
    return {"music": music, "lyrics": lyrics, "music_mode": P.load_project(root).music_mode}


@router.post("/analyze")
async def analyze(slug: str, request: Request):
    from mp3_to_videoclip.analysis import analyze as run_analysis
    from mp3_to_videoclip.storage import inside, write_json

    root = project_root(request, slug)
    path = root / "work" / "music.json"
    (root / "work").mkdir(parents=True, exist_ok=True)
    project = P.load_project(root)
    # Local DSP is CPU-bound; keep the event loop free for SSE and job progress.
    data = await asyncio.to_thread(run_analysis, inside(root, project.source), project.duration)
    write_json(path, data)
    return {
        "status": "done",
        "analysis": str(path),
        "duration": data["duration"],
        "estimated_tempo_bpm": data["estimated_tempo_bpm"],
        "sections": data["sections"],
        "warnings": data["warnings"],
    }


@router.put("/lyrics")
async def update_lyrics(slug: str, request: Request, payload: dict):
    from mp3_to_videoclip.domain.lyrics import parse_lrc, save_lyrics
    from mp3_to_videoclip.models import Lyrics

    root = project_root(request, slug)
    if "lrc" in payload:
        if not isinstance(payload["lrc"], str) or len(payload["lrc"]) > 200_000:
            return {"error": "paste a reasonable amount of lyrics"}
        try:
            lyrics = parse_lrc(payload["lrc"], P.load_project(root).duration)
        except ValueError as exc:
            return {"error": str(exc)}
    else:
        try:
            lyrics = Lyrics.model_validate(payload)
        except ValueError as exc:
            return {"error": str(exc)}
    save_lyrics(root, lyrics)
    return {"status": "saved", "segments": len(lyrics.segments)}
