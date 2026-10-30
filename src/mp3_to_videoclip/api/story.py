"""Story stage: brief and treatments."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response

from mp3_to_videoclip import idea, story_beats
from mp3_to_videoclip import production as P
from mp3_to_videoclip.api._helpers import project_root
from mp3_to_videoclip.storage import RevisionConflict, digest

router = APIRouter(prefix="/api/projects/{slug}", tags=["story"])


@router.get("/brief")
async def get_brief(slug: str, request: Request, response: Response):
    root = project_root(request, slug)
    brief = P.load_brief(root)
    value = brief.model_dump()
    response.headers["ETag"] = f'"{digest(value)}"'
    return value


@router.patch("/brief")
async def update_brief(slug: str, request: Request, payload: dict, response: Response):
    root = project_root(request, slug)
    try:
        brief = P.update_brief(
            root, payload, expected_hash=request.headers.get("if-match"), owner=True
        )
    except RevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    value = brief.model_dump()
    response.headers["ETag"] = f'"{digest(value)}"'
    return value


@router.post("/proof-shots")
async def set_proof_shots(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    try:
        shot_ids = P.set_proof_ids(root, payload.get("shot_ids"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"proof_shot_ids": shot_ids}


@router.get("/treatments")
async def get_treatments(slug: str, request: Request):
    root = project_root(request, slug)
    path = root / "work" / "treatments.json"
    if not path.is_file():
        return {"treatments": []}
    import json

    value = json.loads(path.read_text())
    if "concepts" in value:
        treatments = P.load_treatments(root)
        assert treatments is not None
        concepts = [concept.model_dump() for concept in treatments.concepts]
        return {
            "treatments": concepts,
            "concepts": concepts,
            "chosen_id": treatments.chosen_id,
        }
    return value


@router.put("/treatments")
async def put_treatments(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    try:
        treatments = P.update_treatments(root, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return treatments.model_dump()


@router.get("/idea")
async def get_idea(slug: str, request: Request):
    return {"idea": idea.latest(project_root(request, slug))}


@router.post("/idea")
async def post_idea(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    try:
        return {"idea": idea.keep_paste(root, payload.get("text"))}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/idea/sorted")
async def put_idea_sorted(slug: str, request: Request, payload: dict):
    """Moving a sentence between parts: the same rule that binds the Writer binds this."""
    root = project_root(request, slug)
    try:
        return {"idea": idea.apply_sort(root, payload, by="owner")}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/story-passages")
async def get_story_passages(slug: str, request: Request):
    return {"passages": story_beats.passages(project_root(request, slug))}


def _intake_payload(root: Path, *, analysis_needed: bool = False) -> dict:
    from mp3_to_videoclip import audio, kinds, styles
    from mp3_to_videoclip.storage import inside

    project = P.load_project(root, verify_source=False)
    brief = P.load_brief(root)
    source = inside(root, project.source)
    peaks = []
    if source.is_file():
        peaks = audio.cached_peaks(
            source,
            project.source_sha256,
            root / "work" / "audio-peaks.json",
        )
    return {
        "title": project.title,
        "kind": project.kind or "music_video",
        "intent": brief.intent.model_dump() if brief.intent is not None else None,
        "brief": brief.model_dump(),
        "prompt_version": project.prompt_version,
        "style_preset": project.style_preset,
        "style_presets": styles.public_presets(),
        "kinds": kinds.public_kinds(),
        "source_duration": project.source_duration or project.duration,
        "duration": project.duration,
        "audio_window": (
            project.audio_window.model_dump() if project.audio_window is not None else None
        ),
        "peaks": peaks,
        "analysis_needed": analysis_needed,
    }


@router.get("/intake")
async def get_intake(slug: str, request: Request, response: Response):
    value = _intake_payload(project_root(request, slug))
    # The nested brief is a valid editing base for PATCH /brief.
    response.headers["ETag"] = f'"{digest(value["brief"])}"'
    return value


@router.put("/intake")
async def update_intake(slug: str, request: Request, payload: dict, response: Response):
    root = project_root(request, slug)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="intake must be a JSON object")
    try:
        result = P.apply_intake(
            root,
            intent=payload.get("intent"),
            style_preset=payload.get("style_preset"),
            audio_window=payload.get("audio_window"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    value = _intake_payload(root, analysis_needed=result["analysis_needed"])
    response.headers["ETag"] = f'"{digest(value["brief"])}"'
    return value
