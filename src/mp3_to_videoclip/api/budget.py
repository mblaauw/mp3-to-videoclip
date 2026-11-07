"""Budget: read the cap and history, add a top-up."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request

from mp3_to_videoclip import budget as engine_budget
from mp3_to_videoclip.api._helpers import project_root
from mp3_to_videoclip.api.errors import ApiError
from mp3_to_videoclip.domain import budget

router = APIRouter(prefix="/api/projects/{slug}", tags=["budget"])


@router.get("/budget")
async def get_budget(slug: str, request: Request):
    root = project_root(request, slug)
    cap = budget.cap(root)
    spent, reserved, paid_stills = budget.split_commitment(root)
    committed = spent + reserved
    remaining = budget.remaining(root)
    return {
        "cap_usd": budget.fmt(cap) if cap is not None else None,
        "committed_usd": budget.fmt(committed),
        "spent_usd": budget.fmt(spent),
        "reserved_usd": budget.fmt(reserved),
        "paid_stills": paid_stills,
        "remaining_usd": budget.fmt(remaining) if remaining is not None else None,
        "history": budget.history(root),
        "unresolved": engine_budget.unresolved_tasks(root),
    }


@router.post("/budget")
async def add_budget(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    entry = budget.add_budget(root, payload.get("amount"), payload.get("reason", ""))
    return {"entry": entry, "cap_usd": budget.fmt(budget.cap(root))}


def _unresolved(root, task_id: str) -> None:
    if not any(row["id"] == task_id for row in engine_budget.unresolved_tasks(root)):
        raise HTTPException(status_code=404, detail="that task is not waiting on anything")


@router.post("/tasks/{task_id}/recover")
async def recover_task(slug: str, task_id: str, request: Request):
    """Ask the provider once whether a paid task finished. Free, and never submits again."""
    from mp3_to_videoclip import generation
    from mp3_to_videoclip.providers import ProviderError
    from mp3_to_videoclip.storage import project_lock

    root = project_root(request, slug)
    _unresolved(root, task_id)

    def run():
        with project_lock(root):
            return generation.recover(root, task_id)

    try:
        recovered = await asyncio.to_thread(run)
    except ProviderError as exc:
        if exc.code == "task_failed":
            # The provider's last word: it ended in error and will not come back. Settling stays the owner's.
            return {"recovered": False, "answered": True, "failed": True}
        # A provider's bad day is the expected answer here, not a fault in the Studio.
        return {"recovered": False, "answered": False}
    return {"recovered": bool(recovered), "answered": True}


@router.post("/tasks/{task_id}/resolve")
async def resolve_task(slug: str, task_id: str, request: Request, payload: dict):
    """The owner's word on what the provider billed, from its billing page. Frees the film."""
    from mp3_to_videoclip import generation
    from mp3_to_videoclip.storage import project_lock

    root = project_root(request, slug)
    _unresolved(root, task_id)
    note = str(payload.get("note") or "").strip()
    if not note:
        raise ApiError(400, "Say what the billing page showed.", "resolve_note_required")
    try:
        with project_lock(root):
            generation.resolve_task(root, task_id, str(payload.get("cost")), note)
    except ValueError as exc:
        raise ApiError(
            400, "Enter the billed amount in dollars, 0 if nothing was charged.", "resolve_invalid"
        ) from exc
    return {"resolved": task_id}
