"""The Sound stage: cues, their sounds, the quote and run, and what the ear reports."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from mp3_to_videoclip import audio, catalog, sound
from mp3_to_videoclip import budget as engine_budget
from mp3_to_videoclip import production as P
from mp3_to_videoclip.api._helpers import project_root
from mp3_to_videoclip.api.errors import ApiError
from mp3_to_videoclip.config import effective_settings
from mp3_to_videoclip.domain import budget
from mp3_to_videoclip.generation import authorize, read_quote
from mp3_to_videoclip.providers import runware_api_key
from mp3_to_videoclip.storage import inside, project_lock

router = APIRouter(prefix="/api/projects/{slug}", tags=["sound"])

MAX_SOUND_BYTES = 50 * 1024 * 1024
_MEDIA = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".flac": "audio/flac", ".ogg": "audio/ogg", ".m4a": "audio/mp4", ".aiff": "audio/aiff"}  # fmt: skip


def _models() -> list[dict]:
    settings = effective_settings()
    chosen = {settings.sounds.music_model: "music", settings.sounds.effects_model: "effects"}
    rows = []
    for model in catalog.load().models:
        wanted = [c for c in model.capabilities if c in ("music", "effects")]
        if not wanted:
            continue
        rows.append(
            {
                "id": model.id,
                "label": model.label,
                "for": wanted[0],
                "price": model.price.model_dump() if model.price else None,
                "price_note": model.price_note,
                "chosen": chosen.get(model.id) == wanted[0],
            }
        )
    return rows


def _stills(root: Path) -> dict[str, str]:
    """Each shot's chosen still, for the spine's tiles; a shot without one has none."""
    from mp3_to_videoclip.storage import read_optional

    assets = read_optional(root / "work/assets.json")
    if not isinstance(assets, dict):
        return {}
    try:
        board = P.load_board(root)
    except (OSError, ValueError):
        return {}
    stills = {}
    for shot in board.shots:
        owner = shot.asset_shot_id or shot.id
        entry = assets.get(owner)
        selected = entry.get("selected") if isinstance(entry, dict) else None
        if selected is not None:
            stills[shot.id] = f"/api/projects/{root.name}/images/{owner}/{selected}"
    return stills


def _speech(root: Path, project) -> list[dict]:
    """Where someone speaks, in seconds: the voice a cue ducks under, for the stage's map."""
    try:
        spans = sound.speech_spans(root, project)
    except (OSError, ValueError):
        return []
    return [
        {"start": round(first / audio.SAMPLE_RATE, 3), "end": round(last / audio.SAMPLE_RATE, 3)}
        for first, last in spans
    ]


def _payload(root: Path, *, measure: bool = False) -> dict:
    project = P.load_project(root, verify_source=False)
    spec = sound.read(root)
    found = sound.sources(root, project)
    stills = _stills(root)
    cues = []
    for cue in spec["cues"]:
        try:
            start, end = sound.span_seconds(project, cue, found)
        except ValueError:
            start = end = None
        end = min(end, project.duration) if end is not None else None
        times = sound.place_times(project, cue, found, start, end) if start is not None and end is not None else None  # fmt: skip
        cues.append({**cue, "start_seconds": start, "end_seconds": end, "places_seconds": times})
    return {
        "cues": cues,
        "duration": project.duration,
        "fps": project.fps,
        "story_film": project.spine == "soundtrack",
        "lines": [
            {"id": row["id"], "start": row["start"], "end": row["end"] + row["pause_after"]}
            for row in found["rows"]
        ],  # fmt: skip
        "shots": [
            {"id": shot_id, "start": start, "end": end, "still": stills.get(shot_id)}
            for shot_id, (start, end) in found["shots"].items()
        ],
        "beats": [
            {"id": beat_id, "start": start, "end": end}
            for beat_id, (start, end) in found["beats"].items()
        ],  # fmt: skip
        "speech": _speech(root, project),
        "models": _models(),
        "report": sound.report(root, project) if measure else None,
        "suggestions": len(sound.suggest(root)),
    }


@router.get("/sound")
def get_sound(slug: str, request: Request, measure: bool = False):
    return _payload(project_root(request, slug), measure=measure)


@router.get("/sound/report")
def get_sound_report(slug: str, request: Request):
    root = project_root(request, slug)
    return sound.report(root)


@router.put("/sound")
def put_sound(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    with project_lock(root):
        sound.set_cues(root, payload.get("cues") if isinstance(payload, dict) else payload)
    return _payload(root)


@router.post("/sound/suggest")
def suggest_sound(slug: str, request: Request):
    """A cue list with no model; replaces the list and keeps every sound already made."""
    root = project_root(request, slug)
    with project_lock(root):
        cues = sound.suggest(root)
        if not cues:
            raise ApiError(400, "This film is led by its song; add a cue yourself.", "no_suggestion")  # fmt: skip
        sound.set_cues(root, cues)
    return _payload(root)


@router.post("/sound/select")
def select_sound(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    cue_id = payload.get("cue_id")
    if not isinstance(cue_id, str) or not cue_id:
        raise HTTPException(status_code=400, detail="name the cue")
    version = payload.get("version")
    if version is not None and (isinstance(version, bool) or not isinstance(version, int)):
        raise HTTPException(status_code=400, detail="version is a whole number or null")
    with project_lock(root):
        sound.select(root, cue_id, version)
    return _payload(root)


@router.post("/sound/upload")
async def upload_sound(slug: str, cue_id: str, filename: str, request: Request):
    """The owner's own file as a version of a cue; nothing is charged."""
    root = project_root(request, slug)
    suffix = Path(filename).suffix.lower()
    if suffix not in sound.soundtrack_suffixes():
        raise HTTPException(status_code=400, detail="upload an audio file")
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="the upload is empty")
    if len(data) > MAX_SOUND_BYTES:
        raise HTTPException(status_code=413, detail="that sound is too large")
    with tempfile.TemporaryDirectory(prefix="film-cue-") as temp:
        source = Path(temp) / f"sound{suffix}"
        source.write_bytes(data)
        with project_lock(root):
            sound.import_sound(root, cue_id, source)
    return _payload(root)


@router.get("/sound/{cue_id}/{version}")
def get_cue_sound(slug: str, cue_id: str, version: int, request: Request):
    root = project_root(request, slug)
    cue = next((c for c in sound.read(root)["cues"] if c["id"] == cue_id), None)
    row = next((v for v in (cue or {}).get("versions", []) if v["version"] == version), None)
    if row is None:
        raise HTTPException(status_code=404, detail="that sound does not exist")
    path = inside(root, row["path"])
    return FileResponse(path, media_type=_MEDIA.get(path.suffix.lower(), "application/octet-stream"), content_disposition_type="inline")  # fmt: skip


@router.post("/sound/estimate")
async def estimate_sound(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    cue_ids = payload.get("cue_ids")
    if cue_ids is not None and (not isinstance(cue_ids, list) or not all(isinstance(c, str) for c in cue_ids)):  # fmt: skip
        raise HTTPException(status_code=400, detail="cue_ids is a list of cue ids")
    engine_budget.require_reconciled(
        root
    )  # Before a price: a held film can buy nothing at any price.
    with project_lock(root):
        quote = sound.quote_cues(root, cue_ids, model=payload.get("model") or None)
    runware_api_key()  # Still before a price is shown: nothing can be bought without the key.
    label = next((row["label"] for row in _models() if row["id"] == quote["model"]), quote["model"])
    return {
        "quote_id": quote["id"],
        "model": quote["model"],
        "model_label": label,
        "tasks": [
            {"cue_id": t["cue_id"], "seconds": t["seconds"], "reserve_usd": t["reserve_usd"]}
            for t in quote["tasks"]
        ],  # fmt: skip
        "reserve_usd": quote["reserve_total_usd"],
        "pricing": quote.get("published_pricing"),
        "decision": budget.check(root, quote["reserve_total_usd"]),
    }


@router.post("/sound/generate")
async def generate_sound(slug: str, request: Request, payload: dict):
    """The owner's click on the shown price: authorize exactly that quote, then run it."""
    root = project_root(request, slug)
    quote_id = payload.get("quote_id")
    if not quote_id:
        raise HTTPException(status_code=400, detail="estimate the cues first")
    try:
        quote = read_quote(root, quote_id)
    except FileNotFoundError as exc:
        raise ApiError(404, "That quote is no longer there. Estimate again.", "quote_missing") from exc  # fmt: skip
    if quote.get("kind") != "sound":
        raise HTTPException(status_code=400, detail="this quote is not for sound")
    decision = budget.check(root, quote["reserve_total_usd"])
    if not decision["ok"]:
        return {"needs_budget": True, "decision": decision}
    runner = getattr(request.app.state, "runner", None)
    if runner is None:
        raise HTTPException(status_code=503, detail="job runner unavailable")
    with project_lock(root):
        authorize(root, quote_id, quote["reserve_total_usd"], payload.get("note") or "user confirmed in Studio", via="studio", review_confirmed=True)  # fmt: skip

    async def work():
        def run():
            with project_lock(root):
                return sound.generate_cues(root, quote_id)

        return await asyncio.to_thread(run)

    job_id = runner.submit("sound", slug, work, blocking=True)
    return {"job_id": job_id, "quote_id": quote_id, "reserve_usd": quote["reserve_total_usd"]}
