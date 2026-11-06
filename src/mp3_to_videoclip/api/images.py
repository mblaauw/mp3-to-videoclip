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
from mp3_to_videoclip.providers import runware_api_key
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
        from mp3_to_videoclip import clips

        proposed = clips.proposed_motion(root)
        for shot in board.shots:
            owner = shot.asset_shot_id or shot.id
            entry = assets.get(owner, {})
            local = shotkinds.is_local(shot)
            motion_why = proposed.get(shot.id)
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
                    # Named only when there are some, so this answer is as it was until then.
                    **(
                        {
                            "clips": [
                                {
                                    **clip,
                                    "current": clip["still_root"] == P.still_root(chosen),
                                }
                                for clip in entry["clips"]
                            ],
                            "clip": entry.get("clip"),
                        }
                        if entry.get("clips") and chosen is not None and not shot.asset_shot_id
                        else {}
                    ),
                    "review": review,
                    "stale": stale,
                    **({"motion_why": motion_why} if motion_why else {}),
                }
            )
    return {"shots": shots}


@router.get("/plates/{shot_id}")
@read_endpoint
def get_plate(slug: str, shot_id: str, request: Request, aspect: str | None = None):
    from mp3_to_videoclip import reframe

    root = project_root(request, slug)
    try:
        canvas = None
        if aspect is not None:
            project = P.load_project(root, verify_source=False)
            canvas = reframe.canvas_for(project.width, project.height, aspect)
        target = P.local_plate_path(root, shot_id, canvas)
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


@router.get("/clips/{owner}/{version}")
async def get_clip_file(slug: str, owner: str, version: int, request: Request):
    root = project_root(request, slug)
    path = root / "work" / "assets.json"
    assets = json.loads(path.read_text()) if path.is_file() else {}
    clips = (assets.get(owner) or {}).get("clips", [])
    chosen = next((clip for clip in clips if clip["version"] == version), None)
    if not chosen:
        raise HTTPException(status_code=404, detail="unknown clip")
    target = inside(root, chosen["path"])
    if not target.is_file():
        raise HTTPException(status_code=404, detail="clip file is missing")
    return FileResponse(target, media_type="video/mp4")


@router.get("/images/clips/models")
async def clip_models(slug: str, request: Request):
    """The catalogue's video models with their prices; Settings' choice first. Free."""
    from mp3_to_videoclip import catalog
    from mp3_to_videoclip.config import effective_settings

    project_root(request, slug)
    chosen = effective_settings().pictures.video_model
    rows = [
        {
            "id": model.id,
            "label": model.label or model.id,
            "price": model.price.model_dump() if model.price else None,
            "price_note": model.price_note,
            "price_checked": model.price_checked,
            "chosen": model.id == chosen,
        }
        for model in catalog.load().models
        if "video" in model.capabilities
    ]
    rows.sort(key=lambda row: not row["chosen"])
    return {"models": rows}


@router.get("/images/clips/options")
async def clip_options(slug: str, request: Request, model: str):
    """What one video model lets the owner choose, read from its public schema. Free."""
    from mp3_to_videoclip import services

    project_root(request, slug)
    try:
        return await asyncio.to_thread(services.generation.clip_options, model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # the provider's schema could not be read; say so plainly
        raise HTTPException(status_code=502, detail=f"the model's schema could not be read: {exc}") from exc  # fmt: skip


@router.post("/images/clips/estimate")
async def estimate_clips(slug: str, request: Request, payload: dict):
    from mp3_to_videoclip import services

    root = project_root(request, slug)
    shot_ids = payload.get("shot_ids") or []
    if not shot_ids:
        raise HTTPException(status_code=400, detail="select at least one shot")
    choices = {}
    seconds = payload.get("seconds")
    if seconds is not None:
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or seconds <= 0:
            raise HTTPException(status_code=400, detail="seconds is a number above zero")
        choices["seconds"] = seconds
    for key in ("model", "resolution", "prompt"):
        value = payload.get(key)
        if value is not None:
            if not isinstance(value, str) or not value.strip():
                raise HTTPException(status_code=400, detail=f"{key} is text")
            choices[key] = value.strip()
    if payload.get("audio") is not None:
        choices["audio"] = bool(payload["audio"])
    try:
        estimate = services.generation.estimate_clips(root, shot_ids, **choices)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Still before a price is shown: nothing can be bought without the key.
    runware_api_key()
    return {
        "estimate": estimate,
        "decision": _decisions(root, estimate["reserve_usd"]),
        "budget": _budget_card(root),
    }


@router.post("/images/clips")
async def generate_clips(slug: str, request: Request, payload: dict):
    """The owner's click on the shown price: authorize exactly that quote, then run it."""
    from mp3_to_videoclip import services

    root = project_root(request, slug)
    quote_id = payload.get("quote_id")
    if not quote_id:
        raise HTTPException(status_code=400, detail="estimate the clip first")
    try:
        quote = services.generation.quote(root, quote_id)
    except FileNotFoundError as exc:
        raise ApiError(
            404, "That quote is no longer there. Estimate again.", "quote_missing"
        ) from exc
    if quote.get("kind") != "clip":
        raise HTTPException(status_code=400, detail="this quote is not for clips")
    decision = _decisions(root, quote["reserve_total_usd"])
    if not decision["ok"]:
        return {"needs_budget": True, "decision": decision, "budget": _budget_card(root)}
    runner = getattr(request.app.state, "runner", None)
    if runner is None:
        raise HTTPException(status_code=503, detail="job runner unavailable")
    services.generation.authorize(
        root, quote_id, note=payload.get("note") or "user confirmed in Studio"
    )

    async def work():
        return await asyncio.to_thread(services.generation.run_clips, root, quote_id)

    job_id = runner.submit("images", slug, work, blocking=True)
    return {
        "job_id": job_id,
        "quote_id": quote_id,
        "reserve_usd": quote["reserve_total_usd"],
        "tasks": len(quote["tasks"]),
        "status": "queued",
        "budget": _budget_card(root),
    }


@router.post("/images/clips/select")
async def select_clip(slug: str, request: Request, payload: dict):
    """Use this clip, or ``version: null`` to go back to the still."""
    from mp3_to_videoclip import clips

    root = project_root(request, slug)
    shot_id = payload.get("shot_id")
    if not isinstance(shot_id, str) or not shot_id:
        raise HTTPException(status_code=400, detail="name the shot")
    try:
        clips.select_clip(root, shot_id, payload.get("version"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"shot_id": shot_id, "clip": payload.get("version")}


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
        edit_from=payload.get("edit_from"),
        edit_note=str(payload.get("edit_note") or ""),
    )
    if not estimate["tasks"]:
        raise HTTPException(
            status_code=400,
            detail="every selected shot already has this exact image; use regenerate",
        )
    # Last, so a shot that needs no key is not told to go and get one. Still before
    # a price is shown: nothing can be bought without the key.
    runware_api_key()
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


@router.get("/depth")
def get_depth(slug: str, request: Request):
    from mp3_to_videoclip import depth

    return depth.coverage(project_root(request, slug))


def _depth_job(request: Request, slug: str, work_fn) -> dict:
    runner = getattr(request.app.state, "runner", None)
    if runner is None:
        raise HTTPException(status_code=503, detail="job runner unavailable")

    async def work():
        return await asyncio.to_thread(work_fn)

    return {"job_id": runner.submit("depth", slug, work, blocking=True)}


@router.post("/depth/setup")
async def setup_depth(slug: str, request: Request):
    """On the owner's click: downloads the tools and the model. Nothing is charged."""
    from mp3_to_videoclip import depth

    project_root(request, slug)
    state = depth.status()
    if not state["supported"]:
        raise HTTPException(status_code=400, detail=state["reason"])
    return _depth_job(request, slug, depth.install)


@router.post("/depth/run")
async def run_depth(slug: str, request: Request):
    from mp3_to_videoclip import depth

    root = project_root(request, slug)
    if not depth.status()["ready"]:
        raise ApiError(409, "Set up the depth tools first.", "depth_tools_missing")
    return _depth_job(request, slug, lambda: depth.run(root))


@router.get("/depth/{key}/{layer}")
def get_depth_layer(slug: str, key: str, layer: str, request: Request):
    """One layer for the Player, named by the still and the tools that made it."""
    from mp3_to_videoclip import depth

    root = project_root(request, slug)
    if layer not in depth.LAYERS or not key.replace("-", "").isalnum():
        raise HTTPException(status_code=404, detail="no such layer")
    path = inside(root, f"work/depth/{key}/{layer}.png")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="no such layer")
    return FileResponse(path, media_type="image/png")


@router.get("/sheets")
def get_sheets(slug: str, request: Request):
    from mp3_to_videoclip import sheets

    return {"sheets": sheets.view(project_root(request, slug))}


@router.post("/sheets/generate")
async def generate_sheet(slug: str, request: Request, payload: dict):
    """The owner's click on the shown price: authorize exactly that quote, then run it."""
    from mp3_to_videoclip import services

    root = project_root(request, slug)
    quote_id = payload.get("quote_id")
    if not quote_id:
        raise HTTPException(status_code=400, detail="estimate the sheet first")
    try:
        quote = services.generation.quote(root, quote_id)
    except FileNotFoundError as exc:
        raise ApiError(
            404, "That quote is no longer there. Estimate again.", "quote_missing"
        ) from exc
    if quote.get("kind") != "sheet":
        raise HTTPException(status_code=400, detail="this quote is not for a sheet")
    decision = _decisions(root, quote["reserve_total_usd"])
    if not decision["ok"]:
        return {"needs_budget": True, "decision": decision, "budget": _budget_card(root)}
    runner = getattr(request.app.state, "runner", None)
    if runner is None:
        raise HTTPException(status_code=503, detail="job runner unavailable")
    services.generation.authorize(
        root, quote_id, note=payload.get("note") or "user confirmed in Studio"
    )

    async def work():
        return await asyncio.to_thread(services.generation.run_sheet, root, quote_id)

    job_id = runner.submit("images", slug, work, blocking=True)
    return {"job_id": job_id, "quote_id": quote_id, "reserve_usd": quote["reserve_total_usd"]}


@router.post("/sheets/{entry_id}/estimate")
async def estimate_sheet(slug: str, entry_id: str, request: Request):
    from mp3_to_videoclip import services

    root = project_root(request, slug)
    estimate = services.generation.estimate_sheet(root, entry_id)
    # Still before a price is shown: nothing can be bought without the key.
    runware_api_key()
    return {"estimate": estimate, "decision": _decisions(root, estimate["reserve_usd"])}


@router.post("/sheets/{entry_id}/use")
async def use_sheet(slug: str, entry_id: str, request: Request, payload: dict):
    """The owner's click. The brief changes, so the story asks to be approved again."""
    from mp3_to_videoclip import sheets

    root = project_root(request, slug)
    try:
        return sheets.use_as_reference(root, entry_id, int(payload.get("version"))).model_dump()
    except (OSError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/images/upscale/estimate")
async def estimate_upscale(slug: str, request: Request, payload: dict):
    from mp3_to_videoclip import services

    root = project_root(request, slug)
    shot_ids = payload.get("shot_ids") or []
    if not shot_ids:
        raise HTTPException(status_code=400, detail="select at least one still")
    estimate = services.generation.estimate_upscale(
        root, shot_ids, reserve=payload.get("reserve_usd")
    )
    # Still before a price is shown: nothing can be bought without the key.
    runware_api_key()
    return {
        "estimate": estimate,
        "decision": _decisions(root, estimate["reserve_usd"]),
        "budget": _budget_card(root),
    }


@router.post("/images/upscale")
async def generate_upscale(slug: str, request: Request, payload: dict):
    """The owner's click on the shown price: authorize exactly that quote, then run it."""
    from mp3_to_videoclip import services

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
    if quote.get("kind") != "upscale":
        raise HTTPException(status_code=400, detail="this quote is not for sharper stills")
    decision = _decisions(root, quote["reserve_total_usd"])
    if not decision["ok"]:
        return {"needs_budget": True, "decision": decision, "budget": _budget_card(root)}
    runner = getattr(request.app.state, "runner", None)
    if runner is None:
        raise HTTPException(status_code=503, detail="job runner unavailable")
    services.generation.authorize(
        root, quote_id, note=payload.get("note") or "user confirmed in Studio"
    )

    async def work():
        return await asyncio.to_thread(services.generation.run_upscale, root, quote_id)

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
