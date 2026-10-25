"""Storyboard stage: shots, timing, skeleton, split/merge."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from mp3_to_videoclip import production as P
from mp3_to_videoclip.api._helpers import project_root

router = APIRouter(prefix="/api/projects/{slug}", tags=["storyboard"])


@router.get("/storyboard")
async def get_storyboard(slug: str, request: Request):
    root = project_root(request, slug)
    if not (root / "work" / "storyboard.json").is_file():
        return {"available": False}
    board = P.load_board(root)
    return board.model_dump()


@router.patch("/storyboard/shots")
async def update_shots(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    changes = payload.get("changes", [])
    if not isinstance(changes, list):
        return {"error": "changes must be a list"}
    try:
        board, _changed = P.update_shots(root, changes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return board.model_dump()


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
