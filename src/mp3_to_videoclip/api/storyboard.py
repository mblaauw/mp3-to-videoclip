"""Storyboard stage: shots, timing, skeleton, split/merge."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from mp3_to_videoclip import production as P
from mp3_to_videoclip.api._helpers import project_root
from mp3_to_videoclip.read_snapshots import read_endpoint
from mp3_to_videoclip.storage import digest

router = APIRouter(prefix="/api/projects/{slug}", tags=["storyboard"])


@router.get("/storyboard")
@read_endpoint
def get_storyboard(slug: str, request: Request, response: Response):
    root = project_root(request, slug)
    if not (root / "work" / "storyboard.json").is_file():
        return {"available": False}
    board = P.load_board(root)
    value = board.model_dump()
    response.headers["ETag"] = f'"{digest(value)}"'
    return {**value, "placeholder_shot_ids": P.placeholder_shot_ids(board)}


@router.patch("/storyboard/shots")
async def update_shots(slug: str, request: Request, payload: dict, response: Response):
    root = project_root(request, slug)
    changes = payload.get("changes", [])
    if not isinstance(changes, list):
        raise HTTPException(status_code=400, detail="changes must be a list")
    board, _changed = P.update_shots(root, changes, expected_hash=request.headers.get("if-match"))
    value = board.model_dump()
    response.headers["ETag"] = f'"{digest(value)}"'
    return {**value, "placeholder_shot_ids": P.placeholder_shot_ids(board)}


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
    from mp3_to_videoclip import promptlog

    promptlog.record(root, "storyboard-skeleton")
    return {**board.model_dump(), "placeholder_shot_ids": P.placeholder_shot_ids(board)}
