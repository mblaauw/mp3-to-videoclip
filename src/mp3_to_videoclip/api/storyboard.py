"""Storyboard stage: shots, timing, skeleton, split/merge."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from mp3_to_videoclip import production as P
from mp3_to_videoclip.api._helpers import project_root

router = APIRouter(prefix="/api/projects/{slug}", tags=["storyboard"])


@router.get("/storyboard")
async def get_storyboard(slug: str, request: Request):
    root = project_root(request, slug)
    board = P.load_board(root)
    return board.model_dump()


@router.patch("/storyboard/shots")
async def update_shots(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    board = P.load_board(root)
    changes = payload.get("changes", [])
    if not isinstance(changes, list):
        return {"error": "changes must be a list"}
    by_id = {s.id: s for s in board.shots}
    for change in changes:
        if not isinstance(change, dict):
            return {"error": "each change must be an object"}
        shot_id = change.get("id")
        if shot_id not in by_id:
            continue
        shot = by_id[shot_id]
        for key, value in change.items():
            if key == "id":
                continue
            if hasattr(shot, key):
                setattr(shot, key, value)
    from mp3_to_videoclip.models import Storyboard
    from mp3_to_videoclip.storage import write_json

    # Re-validate the whole board: a partially applied change must never reach disk.
    try:
        updated = Storyboard.model_validate(board.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    write_json(root / "work" / "storyboard.json", updated.model_dump())
    return updated.model_dump()


@router.post("/storyboard/skeleton")
async def create_skeleton(slug: str, request: Request, payload: dict | None = None):
    root = project_root(request, slug)
    payload = payload or {}
    board = P.skeleton(
        root,
        payload.get("seconds"),
        payload.get("timing"),
        min_seconds=payload.get("min_seconds"),
        max_seconds=payload.get("max_seconds"),
    )
    from mp3_to_videoclip.storage import write_json

    write_json(root / "work" / "storyboard.json", board.model_dump())
    return board.model_dump()
