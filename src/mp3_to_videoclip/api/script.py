"""A story film's Script stage: the words, the beats, the takes and the soundtrack."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from mp3_to_videoclip import narration, narration_timing, structures, voices
from mp3_to_videoclip import production as P
from mp3_to_videoclip.api._helpers import project_root
from mp3_to_videoclip.api.errors import ApiError
from mp3_to_videoclip.domain import budget
from mp3_to_videoclip.generation import authorize, read_quote
from mp3_to_videoclip.lyric_tools import status as lyric_status
from mp3_to_videoclip.production import script as scripts
from mp3_to_videoclip.production import soundtrack
from mp3_to_videoclip.storage import inside, project_lock

router = APIRouter(prefix="/api/projects/{slug}", tags=["script"])

MAX_TAKE_BYTES = 50 * 1024 * 1024
_MEDIA = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".flac": "audio/flac", ".ogg": "audio/ogg", ".m4a": "audio/mp4", ".aiff": "audio/aiff"}  # fmt: skip


def _story_film(request: Request, slug: str) -> Path:
    root = project_root(request, slug)
    if P.load_project(root, verify_source=False).spine != "soundtrack":
        raise HTTPException(status_code=409, detail="only a story film has a script")
    return root


def _payload(root: Path) -> dict:
    script = scripts.load_script(root)
    built = soundtrack.built(root)
    project = P.load_project(root, verify_source=False)
    brief = P.load_brief(root)
    structure = (brief.intent.structure if brief.intent else None) or structures.DEFAULT
    return {
        "script": script.model_dump() if script else None,
        "beats": scripts.read_beats(root) or structures.instance(structure, project.duration),
        "structures": structures.public(),
        "timing": narration_timing.read(root),
        "soundtrack": {
            "built": built is not None,
            "receipt": soundtrack.receipt(root),
            "url": f"/api/projects/{root.name}/audio?v={soundtrack.key(root)}" if built else None,
            "mix": soundtrack.read_spec(root),
        },
        "narration": narration.view(root),
        "voices": voices.catalogue(),
        "report": scripts.script_report(root),
        "alignment": lyric_status(),
        "duration": project.duration,
        "fictional": bool(brief.intent and brief.intent.fictional),
    }


@router.get("/script")
def get_script(slug: str, request: Request):
    return _payload(_story_film(request, slug))


@router.put("/script")
def put_script(slug: str, request: Request, payload: dict):
    root = _story_film(request, slug)
    with project_lock(root):
        scripts.write_script(root, payload)
    return _payload(root)


@router.post("/soundtrack")
async def build_soundtrack(slug: str, request: Request):
    """Hear a draft: the takes there are, silence of the estimated length for the rest."""
    root = _story_film(request, slug)

    def run():
        with project_lock(root):
            return soundtrack.build(root)

    await asyncio.to_thread(run)
    return _payload(root)


@router.post("/soundtrack/mix")
def set_mix(slug: str, request: Request, payload: dict):
    """The bed, the ambience and the fades. Nothing is heard until the next build."""
    root = _story_film(request, slug)
    with project_lock(root):
        soundtrack.set_mix(root, payload)
    return _payload(root)


@router.post("/soundtrack/sound")
async def add_sound(slug: str, request: Request, filename: str):
    """An owned recording for the bed or an ambience. Its path goes in the mix next."""
    root = _story_film(request, slug)
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="the upload is empty")
    if len(data) > MAX_TAKE_BYTES:
        raise HTTPException(status_code=413, detail="that sound is too large")
    with tempfile.TemporaryDirectory(prefix="film-sound-") as temp:
        source = Path(temp) / f"sound{Path(filename).suffix.lower()}"
        source.write_bytes(data)
        with project_lock(root):
            return {"path": soundtrack.add_sound(root, source)}


@router.get("/narration/{line_id}/{version}")
def get_take(slug: str, line_id: str, version: int, request: Request):
    root = _story_film(request, slug)
    entry = narration.read_index(root)["lines"].get(line_id, {})
    take = next((v for v in entry.get("versions", []) if v["version"] == version), None)
    if take is None:
        raise HTTPException(status_code=404, detail="that take does not exist")
    path = inside(root, take["path"])
    return FileResponse(
        path,
        media_type=_MEDIA.get(path.suffix.lower(), "application/octet-stream"),
        content_disposition_type="inline",
    )


@router.post("/narration/voice")
def choose_voice(slug: str, request: Request, payload: dict):
    root = _story_film(request, slug)
    with project_lock(root):
        narration.lock_voice(root, payload.get("voice"))
    return _payload(root)


@router.post("/narration/keep")
def keep_take(slug: str, request: Request, payload: dict):
    root = _story_film(request, slug)
    with project_lock(root):
        narration.keep(root, str(payload.get("line_id")), int(payload.get("version")))
    return _payload(root)


@router.post("/narration/unkeep")
def unkeep_take(slug: str, request: Request, payload: dict):
    root = _story_film(request, slug)
    with project_lock(root):
        narration.unkeep(root, str(payload.get("line_id")))
    return _payload(root)


@router.post("/narration/upload")
async def upload_take(slug: str, request: Request, line_id: str, filename: str):
    """The owner's own recording as a take. Nothing is charged."""
    root = _story_film(request, slug)
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="the upload is empty")
    if len(data) > MAX_TAKE_BYTES:
        raise HTTPException(status_code=413, detail="that take is too large")
    suffix = Path(filename).suffix.lower()
    with tempfile.TemporaryDirectory(prefix="narration-take-") as temp:
        source = Path(temp) / f"take{suffix}"
        source.write_bytes(data)
        with project_lock(root):
            narration.import_take(root, line_id, source)
    return _payload(root)


@router.post("/narration/estimate")
def estimate_lines(slug: str, request: Request, payload: dict):
    root = _story_film(request, slug)
    with project_lock(root):
        quote = narration.quote_lines(
            root,
            payload.get("line_ids") or None,
            voice_id=payload.get("voice") or None,
            regenerate=bool(payload.get("regenerate")),
        )
    return {
        "quote_id": quote["id"],
        "voice": quote["voice"],
        "tasks": len(quote["tasks"]),
        "characters": quote["characters"],
        "reserve_usd": quote["reserve_total_usd"],
        "pricing": quote.get("published_pricing"),
        "decision": budget.check(root, quote["reserve_total_usd"]),
    }


@router.post("/narration/generate")
async def generate_lines(slug: str, request: Request, payload: dict):
    """The owner's click on the shown price: authorize exactly that quote, then run it."""
    root = _story_film(request, slug)
    quote_id = payload.get("quote_id")
    if not quote_id:
        raise HTTPException(status_code=400, detail="estimate the lines first")
    try:
        quote = read_quote(root, quote_id)
    except FileNotFoundError as exc:
        raise ApiError(
            404, "That quote is no longer there. Estimate again.", "quote_missing"
        ) from exc
    if quote.get("kind") != "narration":
        raise HTTPException(status_code=400, detail="this quote is not for narration")
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
                return narration.generate(root, quote_id)

        return await asyncio.to_thread(run)

    job_id = runner.submit("narration", slug, work, blocking=True)
    return {"job_id": job_id, "quote_id": quote_id, "reserve_usd": quote["reserve_total_usd"]}


@router.post("/narration/align")
async def align_takes(slug: str, request: Request):
    """Word times from the kept takes, where the tools run on this computer. Free."""
    root = _story_film(request, slug)
    runner = getattr(request.app.state, "runner", None)
    if runner is None:
        raise HTTPException(status_code=503, detail="job runner unavailable")

    async def work():
        def run():
            with project_lock(root):
                return narration_timing.align(root)

        return await asyncio.to_thread(run)

    return {"job_id": runner.submit("narration-align", slug, work, blocking=True)}
