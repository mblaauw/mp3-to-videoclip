"""Track stage: music analysis, section names, lyrics, music mode."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from mp3_to_videoclip import lyric_tools
from mp3_to_videoclip import production as P
from mp3_to_videoclip.api._helpers import project_root
from mp3_to_videoclip.domain import lyric_timing, music_notes, section_map
from mp3_to_videoclip.storage import (
    inside,
    project_lock,
    read_json,
    read_optional,
    state_lock,
    write_json,
)

router = APIRouter(prefix="/api/projects/{slug}", tags=["track"])

MAX_LYRICS_BYTES = 200_000


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


@router.get("/audio-excerpt")
async def get_excerpt(slug: str, request: Request):
    """The derived window audio; music videos keep the original /audio route."""
    root = project_root(request, slug)
    project = P.load_project(root)
    if project.audio_window is None:
        raise HTTPException(status_code=404, detail="this production uses the whole track")
    target = P.render_audio(root, project)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="excerpt audio is missing")
    return FileResponse(target, media_type="audio/wav", content_disposition_type="inline")


@router.get("/track")
async def get_track(slug: str, request: Request):
    root = project_root(request, slug)
    music = read_optional(root / "work" / "music.json")
    notes = music_notes.read(root)
    if isinstance(music, dict):
        music = section_map.apply(root, music)
    lyrics = read_optional(root / "work" / "lyrics.json")
    project = P.load_project(root)
    return {
        "music": music,
        "lyrics": lyrics,
        "music_mode": project.music_mode,
        "kind": project.kind or "music_video",
        "duration": project.duration,
        "source_duration": project.source_duration or project.duration,
        "section_names": notes["sections"],
        "section_map": section_map.read(root) is not None,
    }


@router.get("/music-notes")
async def get_music_notes(slug: str, request: Request):
    return music_notes.read(project_root(request, slug))


@router.put("/music-notes")
async def put_music_notes(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    try:
        return music_notes.save(root, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/lyric-tools")
async def get_lyric_tools(slug: str, request: Request):
    project_root(request, slug)
    return lyric_tools.status()


def _submit_lyric_job(request: Request, kind: str, slug: str, work_fn) -> dict:
    runner = getattr(request.app.state, "runner", None)
    if runner is None:
        raise HTTPException(status_code=503, detail="job runner unavailable")

    async def work():
        return await asyncio.to_thread(work_fn)

    return {"job_id": runner.submit(kind, slug, work, blocking=True), "status": "queued"}


@router.post("/lyric-tools/setup")
async def setup_lyric_tools(slug: str, request: Request):
    project_root(request, slug)
    state = lyric_tools.status()
    if not state["supported"]:
        raise HTTPException(status_code=400, detail=state["reason"])
    return _submit_lyric_job(request, "lyric_tools", slug, lyric_tools.install)


@router.get("/lyric-draft")
async def get_lyric_draft(slug: str, request: Request):
    return lyric_tools.read_draft(project_root(request, slug))


@router.post("/lyric-draft/run")
async def run_lyric_draft(slug: str, request: Request):
    root = project_root(request, slug)
    if not lyric_tools.status()["ready"]:
        raise HTTPException(status_code=409, detail="set up the lyric tools first")
    return _submit_lyric_job(request, "lyric_draft", slug, lambda: lyric_tools.draft_words(root))


@router.post("/lyric-timing/run")
async def run_lyric_timing(slug: str, request: Request):
    root = project_root(request, slug)
    if not lyric_tools.status()["ready"]:
        raise HTTPException(status_code=409, detail="set up the lyric tools first")
    return _submit_lyric_job(request, "lyric_timing", slug, lambda: lyric_tools.time_lyrics(root))


@router.get("/lyric-timing")
async def get_lyric_timing(slug: str, request: Request):
    return lyric_timing.view(project_root(request, slug))


@router.put("/lyric-timing")
async def put_lyric_timing(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    try:
        return lyric_timing.save(root, payload, P.load_project(root).duration)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/section-map")
async def put_section_map(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    try:
        return section_map.save(root, payload, P.load_project(root).duration)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/section-map/propose")
async def propose_section_map(slug: str, request: Request):
    from mp3_to_videoclip import services

    root = project_root(request, slug)
    if not (root / "work" / "music-deep.json").is_file() and (root / "work/music.json").is_file():
        # Local and free: a finer set of edges for the tags to land on.
        await asyncio.to_thread(services.analysis.deep_analyze_project, root)
    try:
        return {"sections": section_map.propose(root, P.load_project(root).duration)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/section-map/reset")
async def reset_section_map(slug: str, request: Request):
    root = project_root(request, slug)
    try:
        section_map.reset(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "reset"}


@router.put("/music-mode")
async def set_music_mode(slug: str, request: Request, payload: dict):
    """Record whether the track has leading vocals.

    The mode changes which gate the brief depends on, so it is locked once a
    story exists rather than silently keeping a stale approval alive.
    """
    if not isinstance(payload, dict) or set(payload) - {"music_mode"}:
        raise HTTPException(status_code=400, detail="music mode must be a JSON object")
    mode = payload.get("music_mode")
    if mode not in ("vocal", "instrumental"):
        raise HTTPException(status_code=400, detail="music mode must be vocal or instrumental")
    root = project_root(request, slug)
    with project_lock(root), state_lock(root):
        project = P.load_project(root)
        records = read_json(root / "work" / "approvals.json")
        if isinstance(records, dict) and isinstance(records.get("brief"), dict):
            raise HTTPException(
                status_code=409,
                detail="the story is already approved; start a new film to change the music mode",
            )
        if project.music_mode == mode:
            return {"music_mode": mode}
        project = project.model_copy(update={"music_mode": mode})
        write_json(root / "project.json", project.model_dump())
    return {"music_mode": mode}


@router.post("/analyze")
async def analyze(slug: str, request: Request):
    from mp3_to_videoclip import services

    root = project_root(request, slug)
    # Local DSP is CPU-bound; keep the event loop free for SSE and job progress.
    data = await asyncio.to_thread(services.analysis.analyze_project, root, force=True)
    return {
        "status": "done",
        "analysis": data["analysis"],
        "duration": data["duration"],
        "estimated_tempo_bpm": data["estimated_tempo_bpm"],
        "sections": data["sections"],
        "warnings": data["warnings"],
    }


@router.put("/lyrics")
async def update_lyrics(slug: str, request: Request, payload: dict):
    from mp3_to_videoclip.domain.lyrics import parse_lrc, parse_lyrics_text, save_lyrics
    from mp3_to_videoclip.models import Lyrics

    root = project_root(request, slug)
    project = P.load_project(root)
    if project.kind not in (None, "music_video"):
        raise HTTPException(status_code=400, detail="lyrics are a music-video intake")
    if "text" in payload:
        raw = payload["text"]
        if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_LYRICS_BYTES:
            raise HTTPException(status_code=400, detail="paste a reasonable amount of lyrics")
        try:
            lyrics = parse_lyrics_text(raw, project.duration)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    elif "lrc" in payload:
        if (
            not isinstance(payload["lrc"], str)
            or len(payload["lrc"].encode("utf-8")) > MAX_LYRICS_BYTES
        ):
            return {"error": "paste a reasonable amount of lyrics"}
        try:
            lyrics = parse_lrc(payload["lrc"], project.duration)
        except ValueError as exc:
            return {"error": str(exc)}
    else:
        try:
            lyrics = Lyrics.model_validate(payload)
        except ValueError as exc:
            return {"error": str(exc)}
    save_lyrics(root, lyrics)
    result = {"status": "saved", "segments": len(lyrics.segments)}
    if lyrics.lines:
        result["lines"] = len(lyrics.lines)
    return result
