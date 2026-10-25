"""Approval status and typed human approvals for the Studio stages.

The state is computed from the saved hash and the current artifacts: approved
only when the recorded decision still binds exactly this content. Approving is
the existing typed human action, so the expected hash and a note are mandatory.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from mp3_to_videoclip import production as P
from mp3_to_videoclip.api._helpers import project_root
from mp3_to_videoclip.domain import approvals
from mp3_to_videoclip.storage import read_json

router = APIRouter(prefix="/api/projects/{slug}", tags=["approvals"])

STAGES = (
    "analysis",
    "lyrics",
    "brief",
    "storyboard",
    "proof",
    "preview",
    "stills",
    "graphics",
)


def _approval(root, stage: str) -> dict:
    record = read_json(root / "work" / "approvals.json").get(stage)
    try:
        current = P.stage_hash(root, stage)
    except FileNotFoundError:
        message = (
            "graphics review has not been prepared; render a current base and record the review"
            if stage == "graphics"
            else f"{stage} is not ready; its artifact has not been created"
        )
        return {
            "stage": stage,
            "state": "unavailable",
            "error": message,
            "at": (record or {}).get("at"),
            "note": (record or {}).get("note"),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "stage": stage,
            "state": "unavailable",
            "error": str(exc),
            "at": (record or {}).get("at"),
            "note": (record or {}).get("note"),
        }
    if record is None:
        state = "missing"
    elif record.get("hash") != current:
        state = "stale"
    else:
        state = "approved"
    return {
        "stage": stage,
        "state": state,
        "expected_hash": current,
        "at": (record or {}).get("at"),
        "note": (record or {}).get("note"),
    }


@router.get("/approvals")
async def get_approvals(slug: str, request: Request, stages: str | None = None):
    root = project_root(request, slug)
    wanted = STAGES
    if stages:
        wanted = tuple(stage for stage in stages.split(",") if stage in STAGES)
    return {"stages": [_approval(root, stage) for stage in wanted]}


@router.post("/approvals/{stage}")
async def approve_stage(slug: str, stage: str, request: Request, payload: dict):
    root = project_root(request, slug)
    try:
        return approvals.approve_stage(root, stage, payload)
    except approvals.ApprovalError as exc:
        return JSONResponse({"error": str(exc)}, status_code=exc.status)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
