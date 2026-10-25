"""Track stage: music analysis, lyrics, transcription."""

from __future__ import annotations

from fastapi import APIRouter, Request

from mp3_to_videoclip import production as P
from mp3_to_videoclip.api._helpers import project_root

router = APIRouter(prefix="/api/projects/{slug}", tags=["track"])


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
    return {"music": music, "lyrics": lyrics}


@router.post("/analyze")
async def analyze(slug: str, request: Request):
    from mp3_to_videoclip.analysis import analyze as run_analysis
    from mp3_to_videoclip.storage import inside, write_json

    root = project_root(request, slug)
    path = root / "work" / "music.json"
    (root / "work").mkdir(parents=True, exist_ok=True)
    data = run_analysis(inside(root, P.load_project(root).source), P.load_project(root).duration)
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
    root = project_root(request, slug)
    import json as _json

    (root / "work").mkdir(parents=True, exist_ok=True)
    (root / "work" / "lyrics.json").write_text(_json.dumps(payload, indent=2) + "\n")
    return {"status": "saved"}
