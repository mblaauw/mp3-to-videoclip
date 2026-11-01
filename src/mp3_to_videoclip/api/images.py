"""Images stage: status, estimate, generate, select, keep/redo."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from mp3_to_videoclip import budget as correction_cycles
from mp3_to_videoclip import production as P
from mp3_to_videoclip import reviews, services, shotkinds
from mp3_to_videoclip.api._helpers import project_root
from mp3_to_videoclip.api.errors import ApiError
from mp3_to_videoclip.domain import budget
from mp3_to_videoclip.read_snapshots import read_endpoint
from mp3_to_videoclip.storage import digest, inside, read_json

router = APIRouter(prefix="/api/projects/{slug}", tags=["images"])


def _decisions(root, reserve_usd):
    return budget.check(root, reserve_usd)


@router.get("/images")
@read_endpoint
def get_images(slug: str, request: Request):
    root = project_root(request, slug)
    assets_path = root / "work" / "assets.json"
    assets = {}
    if assets_path.is_file():
        assets = read_json(assets_path)
    board = P.load_board(root) if (root / "work" / "storyboard.json").is_file() else None
    shots = []
    if board is not None:
        for shot in board.shots:
            owner = shot.asset_shot_id or shot.id
            entry = assets.get(owner, {})
            local = shotkinds.is_local(shot)
            local_plate = local and shot.asset_shot_id is None
            try:
                review = None if local_plate else reviews.verdict_for(root, shot.id)
            except (OSError, ValueError):
                review = None
            selected = None if local_plate else entry.get("selected")
            chosen = next(
                (
                    version
                    for version in entry.get("versions", [])
                    if version.get("version") == selected
                ),
                None,
            )
            stale = False
            if chosen is not None and not local:
                try:
                    stale = chosen.get("input_hash") != digest(P.image_spec(root, shot))
                except (OSError, ValueError):
                    stale = False
            shots.append(
                {
                    "id": shot.id,
                    "owner": owner,
                    "kind": shot.kind,
                    "paid": shotkinds.is_paid(shot),
                    "local": local,
                    "plate": (f"/api/projects/{slug}/plates/{shot.id}" if local_plate else None),
                    "message": shot.message,
                    "text": shot.text,
                    "selected": selected,
                    "versions": [] if local_plate else entry.get("versions", []),
                    "review": review,
                    "stale": stale,
                }
            )
    return {"shots": shots}


@router.get("/plates/{shot_id}")
@read_endpoint
def get_plate(slug: str, shot_id: str, request: Request):
    root = project_root(request, slug)
    try:
        target = P.local_plate_path(root, shot_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="local plate is missing") from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail="local plate is missing")
    return FileResponse(target)


@router.get("/images/{owner}/{version}")
async def get_image_file(slug: str, owner: str, version: int, request: Request):
    root = project_root(request, slug)
    path = root / "work" / "assets.json"
    assets = json.loads(path.read_text()) if path.is_file() else {}
    entry = assets.get(owner) or {}
    chosen = next((v for v in entry.get("versions", []) if v["version"] == version), None)
    if not chosen:
        raise HTTPException(status_code=404, detail="unknown image version")
    target = inside(root, chosen["path"])
    if not target.is_file():
        raise HTTPException(status_code=404, detail="image file is missing")
    return FileResponse(target)


@router.post("/images/review")
async def review_image(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    shot_id = payload.get("shot_id")
    version = payload.get("version")
    verdict = payload.get("verdict")
    note = payload.get("note")
    inspected = payload.get("inspected")
    if not isinstance(shot_id, str) or not shot_id:
        raise HTTPException(status_code=400, detail="choose a shot")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise HTTPException(status_code=400, detail="choose a valid image version")
    if verdict not in ("accept", "reject", "uncertain"):
        raise HTTPException(status_code=400, detail="verdict must be accept, reject or uncertain")
    if note is None:
        note = ""
    if not isinstance(note, str) or len(note.strip()) > 2000:
        raise HTTPException(status_code=400, detail="a review note may be at most 2000 characters")
    if inspected is not True:
        raise HTTPException(
            status_code=400, detail="confirm that you inspected the exact image bytes"
        )
    record = reviews.record_review(
        root,
        shot_id,
        version,
        verdict,
        note=note.strip() or None,
        reviewer="studio",
        inspected=True,
    )
    return {"review": record}


@router.post("/images/estimate")
async def estimate_images(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    shot_ids = payload.get("shot_ids") or []
    if not shot_ids:
        raise HTTPException(status_code=400, detail="select at least one shot")
    # Say so plainly while the owner can still act, instead of a refused quote.
    board = P.load_board(root)
    owners = {shot.id: shot.asset_shot_id or shot.id for shot in board.shots}
    named = list(dict.fromkeys(owners.get(shot_id, shot_id) for shot_id in shot_ids))
    used_up = correction_cycles.used_up_corrections(root, named)
    if used_up:
        return {"needs_new_round": used_up}
    estimate = services.generation.estimate(
        root,
        shot_ids,
        scope=payload.get("scope", "stills"),
        reserve=str(payload.get("reserve_usd", "0.05")),
        regenerate=bool(payload.get("regenerate")),
    )
    if not estimate["tasks"]:
        raise HTTPException(
            status_code=400,
            detail="every selected shot already has this exact image; use regenerate",
        )
    return {
        "estimate": estimate,
        "decision": _decisions(root, estimate["reserve_usd"]),
        "budget": _budget_card(root),
    }


@router.post("/images/new-round")
async def start_new_round(slug: str, request: Request, payload: dict):
    """The owner's reasoned decision to go past a shot's correction limit. Spends nothing."""
    root = project_root(request, slug)
    correction_cycles.authorize_restaging(
        root, payload.get("shot_ids") or [], payload.get("note") or ""
    )
    return {"started": payload.get("shot_ids")}


@router.post("/images/generate")
async def generate_images(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    quote_id = payload.get("quote_id")
    if not quote_id:
        raise HTTPException(status_code=400, detail="estimate the selection first")
    try:
        quote = services.generation.quote(root, quote_id)
    except FileNotFoundError as exc:
        raise ApiError(
            404, "That quote is no longer there. Estimate again.", "quote_missing"
        ) from exc
    decision = _decisions(root, quote["reserve_total_usd"])
    if not decision["ok"]:
        return {"needs_budget": True, "decision": decision, "budget": _budget_card(root)}
    if services.generation.uploads_required(quote) and not payload.get("uploads_confirmed"):
        raise HTTPException(
            status_code=400, detail="reference images will be uploaded; confirm that explicitly"
        )
    runner = getattr(request.app.state, "runner", None)
    if runner is None:
        raise HTTPException(status_code=503, detail="job runner unavailable")
    services.generation.authorize(
        root,
        quote_id,
        note=payload.get("note") or "user confirmed in Studio",
        uploads_confirmed=bool(payload.get("uploads_confirmed")),
    )

    async def work():
        return await asyncio.to_thread(services.generation.run, root, quote_id)

    job_id = runner.submit("images", slug, work, blocking=True)
    return {
        "job_id": job_id,
        "quote_id": quote_id,
        "reserve_usd": quote["reserve_total_usd"],
        "tasks": len(quote["tasks"]),
        "status": "queued",
        "budget": _budget_card(root),
    }


@router.post("/images/select")
async def select_version(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    shot_id = payload.get("shot_id")
    version = payload.get("version")
    if shot_id is None or version is None:
        raise HTTPException(status_code=400, detail="shot_id and version required")
    P.select_asset(root, shot_id, version)
    return {"selected": shot_id, "version": version}


def _budget_card(root) -> dict:
    cap = budget.cap(root)
    committed = budget.committed(root)
    remaining = budget.remaining(root)
    return {
        "cap_usd": budget.fmt(cap) if cap is not None else None,
        "committed_usd": budget.fmt(committed),
        "remaining_usd": budget.fmt(remaining) if remaining is not None else None,
    }
