"""Budget: read the cap and history, add a top-up."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from mp3_to_videoclip.api._helpers import project_root
from mp3_to_videoclip.domain import budget

router = APIRouter(prefix="/api/projects/{slug}", tags=["budget"])


@router.get("/budget")
async def get_budget(slug: str, request: Request):
    root = project_root(request, slug)
    cap = budget.cap(root)
    committed = budget.committed(root)
    remaining = budget.remaining(root)
    return {
        "cap_usd": budget.fmt(cap) if cap is not None else None,
        "committed_usd": budget.fmt(committed),
        "remaining_usd": budget.fmt(remaining) if remaining is not None else None,
        "history": budget.history(root),
    }


@router.post("/budget")
async def add_budget(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    try:
        entry = budget.add_budget(root, payload.get("amount"), payload.get("reason", ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"entry": entry, "cap_usd": budget.fmt(budget.cap(root))}
