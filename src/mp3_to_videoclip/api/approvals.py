"""Approval status and typed human approvals for the Studio stages.

The state is computed from the saved hash and the current artifacts: approved
only when the recorded decision still binds exactly this content. Approving is
the existing typed human action, so the expected hash and a note are mandatory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from mp3_to_videoclip import production as P
from mp3_to_videoclip.api._helpers import project_root
from mp3_to_videoclip.api.errors import error_response
from mp3_to_videoclip.domain import approvals
from mp3_to_videoclip.storage import read_json

router = APIRouter(prefix="/api/projects/{slug}", tags=["approvals"])


class ApprovalStateOut(BaseModel):
    stage: str
    state: Literal["approved", "stale", "missing", "unavailable"]
    expected_hash: str | None = None
    at: str | None = None
    note: str | None = None
    error: str | None = None
    blocking_stage: str | None = None


class ApprovalsOut(BaseModel):
    stages: list[ApprovalStateOut]


class ApprovalOut(BaseModel):
    approved: str
    record: dict[str, Any] = Field(default_factory=dict)
    generated: bool = False


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


def _missing_stage(root: Path, exc: FileNotFoundError, stage: str) -> str:
    """Name the artifact that actually failed, not the stage being inspected."""
    filename = getattr(exc, "filename", None)
    if filename:
        try:
            relative = Path(str(filename)).resolve().relative_to(root.resolve()).as_posix()
        except (OSError, ValueError):
            relative = None
        if relative:
            for name, stored in P.STAGE_FILES.items():
                if stored == relative:
                    return name
    try:
        return P.effective_upstream(root, stage) or stage
    except Exception:  # noqa: BLE001 - keep the approval state readable
        return stage


def _approval(root, stage: str) -> dict:
    record = read_json(root / "work" / "approvals.json").get(stage)
    try:
        current = P.stage_hash(root, stage)
    except FileNotFoundError as exc:
        blocking = "graphics" if stage == "graphics" else _missing_stage(root, exc, stage)
        message = (
            "graphics review has not been prepared; render a current base and record the review"
            if stage == "graphics"
            else f"{blocking} is missing; its artifact has not been created"
        )
        return {
            "stage": stage,
            "state": "unavailable",
            "error": message,
            "blocking_stage": blocking,
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


@router.get("/approvals", response_model=ApprovalsOut)
async def get_approvals(slug: str, request: Request, stages: str | None = None):
    root = project_root(request, slug)
    wanted = STAGES
    if stages:
        wanted = tuple(stage for stage in stages.split(",") if stage in STAGES)
    return {"stages": [_approval(root, stage) for stage in wanted]}


@router.post("/approvals/{stage}", response_model=ApprovalOut)
async def approve_stage(slug: str, stage: str, request: Request, payload: dict):
    root = project_root(request, slug)
    try:
        return approvals.approve_stage(root, stage, payload)
    except approvals.ApprovalError as exc:
        code = {
            404: "approval_not_found",
            409: "approval_stale",
        }.get(exc.status, "approval_invalid")
        return error_response(str(exc), code, exc.status)
    except ValueError as exc:
        return error_response(str(exc), "approval_invalid", 400)
