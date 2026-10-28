"""Delivery checklist: exactly the gates ``POST /render final`` applies.

The Studio must never offer *Render final* for a film the backend would refuse,
and must never hide a gate the backend enforces. This module asks the engine the
same questions the render service asks, so the answer cannot drift from the
renderer.
"""

from __future__ import annotations

from pathlib import Path

from mp3_to_videoclip import production as P
from mp3_to_videoclip import reviews, shotkinds
from mp3_to_videoclip.read_snapshots import read_operation
from mp3_to_videoclip.storage import digest


def _gate(root: Path, stage: str) -> tuple[bool, str | None, str | None]:
    """(accepted, reason, expected hash) for one stage, including its parents."""
    try:
        P.require_approval(root, stage)
        accepted = True
        reason = None
    except (OSError, ValueError) as exc:
        accepted = False
        reason = str(exc)
    try:
        expected = P.stage_hash(root, stage)
    except (OSError, ValueError, FileNotFoundError):
        expected = None
    return accepted, reason, expected


def stills_progress(root: Path) -> dict:
    """Paid stills and how many have an accepted review of the current prompt."""
    shots = P.load_board(root).shots if (root / "work" / "storyboard.json").is_file() else []
    paid = [shot for shot in shots if shotkinds.is_paid(shot)]
    kept = 0
    for shot in paid:
        try:
            verdict = reviews.verdict_for(root, shot.id)
            current = digest(P.image_spec(root, shot))
        except (OSError, ValueError):
            continue
        if (
            verdict
            and verdict.get("verdict") == "accept"
            and verdict.get("inspected") is True
            and verdict.get("input_hash") == current
        ):
            kept += 1
    return {"kept": kept, "total": len(paid)}


def _human_reason(reason: str | None, stage: str) -> str | None:
    """Turn the engine's approval prose into a sentence the owner can act on."""
    if not reason:
        return None
    names = {
        "analysis": "The music analysis",
        "lyrics": "The lyrics",
        "brief": "The story",
        "storyboard": "The storyboard",
        "proof": "The style check",
        "preview": "The preview",
        "stills": "The still set",
        "graphics": "The titles",
    }
    if reason.endswith("needs current user approval"):
        parent = reason[: -len(" needs current user approval")]
        return f"{names.get(parent, parent)} needs your approval."
    if "no current selected still" in reason and reason.startswith("shot "):
        return f"{reason.split(' ', 2)[1]} has no picture yet."
    if reason.endswith("is missing; its artifact has not been created"):
        parent = reason[: -len(" is missing; its artifact has not been created")]
        return f"{names.get(parent, parent)} has not been made yet."
    if reason.endswith("review artifact is missing; recreate and obtain current user approval"):
        return f"The {stage} review is missing; make it again."
    return reason


def _line(
    identifier: str,
    label: str,
    stage: str,
    accepted: bool,
    reason: str | None,
    expected: str | None,
    detail: str,
    *,
    required: bool = True,
) -> dict:
    if not required:
        state = "optional"
    elif accepted:
        state = "done"
    elif expected:
        state = "you"
    else:
        state = "blocked"
    return {
        "id": identifier,
        "label": label,
        "stage": stage,
        "state": state,
        "required": required,
        "detail": detail,
        "reason": _human_reason(reason, stage),
        "expected_hash": expected,
    }


@read_operation
def build(root: Path) -> dict:
    root = Path(root)
    project = P.load_project(root, verify_source=False)
    signature = P.requires_signature(root, project)
    try:
        preview_required = P.effective_upstream(root, "stills") == "preview"
    except (OSError, ValueError):
        preview_required = False

    story_ok, story_reason, story_hash = _gate(root, "brief")
    board_ok, board_reason, board_hash = _gate(root, "storyboard")
    if preview_required:
        preview_ok, preview_reason, preview_hash = _gate(root, "preview")
    else:
        preview_ok, preview_reason, preview_hash = True, None, None
    stills_ok, stills_reason, stills_hash = _gate(root, "stills")
    graphics_ok, graphics_reason, graphics_hash = (
        _gate(root, "graphics") if signature else (True, None, None)
    )
    progress = stills_progress(root)

    lines = [
        _line(
            "story",
            "Story approved",
            "story",
            story_ok,
            story_reason,
            story_hash,
            "The brief is signed off." if story_ok else "Approve the story first.",
        ),
        _line(
            "storyboard",
            "Storyboard approved",
            "storyboard",
            board_ok,
            board_reason,
            board_hash,
            "Timing and shot content are signed off." if board_ok else "Approve the storyboard.",
        ),
    ]
    if preview_required:
        lines.append(
            _line(
                "preview",
                "Watched the preview with sound",
                "film",
                preview_ok,
                preview_reason,
                preview_hash,
                "The reviewed preview is approved."
                if preview_ok
                else "Watch a preview with the music, then confirm it.",
            )
        )
    detail = (
        f"All {progress['total']} paid stills are kept."
        if stills_ok
        else f"{progress['kept']} of {progress['total']} paid stills kept."
    )
    lines.append(
        _line(
            "stills",
            "Every still kept and approved",
            "images",
            stills_ok,
            stills_reason,
            stills_hash,
            detail,
        )
    )
    lines.append(
        _line(
            "titles",
            "Titles checked on real frames",
            "film",
            graphics_ok,
            graphics_reason,
            graphics_hash,
            (
                "This film has no separate graphics pass."
                if not signature
                else (
                    "The composited titles are approved."
                    if graphics_ok
                    else "Render a base and inspect the real frames."
                )
            ),
            required=signature,
        )
    )

    can_final = stills_ok and (graphics_ok if signature else True)
    required = [line for line in lines if line["required"]]
    outstanding = [line["label"] for line in required if line["state"] != "done"]
    return {
        "signature_required": signature,
        "preview_required": preview_required,
        "can_final": can_final,
        "lines": lines,
        "stills": progress,
        "outstanding": outstanding,
    }
