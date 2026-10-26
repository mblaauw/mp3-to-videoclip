"""Explain a changed Studio decision from the snapshot it approved.

Approval hashing stays exactly as strict as before. These helpers only compare
the current brief (or storyboard) with the copy recorded at approval time and
return human words for the changed banner; they never decide a gate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mp3_to_videoclip.storage import read_json, read_optional


def _snapshot(root: Path, stage: str, digest: str) -> dict | None:
    value = read_optional(root / "work" / "approval-snapshots" / f"{stage}-{digest}.json")
    return value if isinstance(value, dict) else None


def _short(value: Any, limit: int = 280) -> str:
    if isinstance(value, str):
        text = value
    elif value is None:
        text = "(empty)"
    elif value == []:
        text = "(empty)"
    elif value == {}:
        text = "(empty)"
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    text = " ".join(text.split())
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _human_list(items: list[str]) -> str:
    if not items:
        return "nothing"
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} and {items[-1]}"


def _compare(
    previous: Any,
    current: Any,
    label: str,
    reason: str,
    changes: list[dict[str, str]],
    *,
    limit: int = 12,
) -> str | None:
    if previous == current:
        return None
    if len(changes) < limit:
        changes.append({"field": label, "before": _short(previous), "after": _short(current)})
    return reason


def brief_changes(root: Path, record: dict | None) -> dict:
    """Return `{available, reason, changes}` for the last approved brief."""
    digest = (record or {}).get("hash") if isinstance(record, dict) else None
    if not isinstance(digest, str):
        return {"available": False, "reason": None, "changes": []}
    saved = _snapshot(root, "brief", digest)
    artifact = (saved or {}).get("artifact")
    if not isinstance(artifact, dict):
        return {
            "available": False,
            "reason": "The story changed since you approved it.",
            "changes": [],
        }
    try:
        current = read_json(root / "brief.json")
    except OSError:
        current = {}
    if not isinstance(current, dict):
        current = {}

    changes: list[dict[str, str]] = []
    reason: str | None = None

    before_intent = artifact.get("intent") if isinstance(artifact.get("intent"), dict) else {}
    after_intent = current.get("intent") if isinstance(current.get("intent"), dict) else {}
    intent_labels = (
        ("objective", "Objective"),
        ("message", "Message"),
        ("audience", "Audience"),
        ("reasons", "Reasons"),
        ("tone", "Tone"),
        ("mandatories", "Must-haves"),
        ("avoid", "Avoid"),
        ("cta", "Call to action"),
        ("length_seconds", "Target length"),
    )
    for key, label in intent_labels:
        reason = (
            _compare(
                before_intent.get(key),
                after_intent.get(key),
                label,
                "The brief changed.",
                changes,
            )
            or reason
        )

    for key, label in (
        ("treatment", "Treatment"),
        ("direction", "Direction"),
        ("style", "Style"),
    ):
        reason = (
            _compare(
                artifact.get(key),
                current.get(key),
                label,
                f"The {label.lower()} changed.",
                changes,
            )
            or reason
        )

    before_creative = artifact.get("creative") if isinstance(artifact.get("creative"), dict) else {}
    after_creative = current.get("creative") if isinstance(current.get("creative"), dict) else {}
    for key, label in (
        ("look", "Look"),
        ("image_rules", "Look rules"),
        ("scenes", "Scenes"),
        ("references", "References"),
        ("world", "World"),
    ):
        reason = (
            _compare(
                before_creative.get(key),
                after_creative.get(key),
                label,
                "The look changed." if key in ("look", "image_rules") else "The story changed.",
                changes,
            )
            or reason
        )

    before_proof = before_creative.get("proof_shot_ids") or []
    after_proof = after_creative.get("proof_shot_ids") or []
    proof_reason = None
    if before_proof != after_proof:
        if isinstance(after_proof, list) and after_proof:
            proof_reason = (
                f"The style-check shots moved to {_human_list([str(v) for v in after_proof])}."
            )
        else:
            proof_reason = "The style-check shots were cleared."
        if len(changes) < 12:
            changes.append(
                {
                    "field": "Style-check shots",
                    "before": _short(before_proof),
                    "after": _short(after_proof),
                }
            )

    for key, label in (
        ("characters", "Characters"),
        ("visual_rules", "Visual rules"),
        ("avoid", "Avoid"),
        ("script", "Script"),
    ):
        reason = (
            _compare(
                artifact.get(key),
                current.get(key),
                label,
                "The characters changed." if key == "characters" else "The story changed.",
                changes,
            )
            or reason
        )

    reason = proof_reason or reason

    if not changes:
        return {
            "available": True,
            "reason": "The story's supporting files changed since you approved it.",
            "changes": [],
        }
    return {
        "available": True,
        "reason": reason or "The story changed since you approved it.",
        "changes": changes,
    }


def storyboard_changes(root: Path, record: dict | None) -> dict:
    """A compact shot-level diff for a stale storyboard decision."""
    digest = (record or {}).get("hash") if isinstance(record, dict) else None
    if not isinstance(digest, str):
        return {"available": False, "reason": None, "changes": []}
    saved = _snapshot(root, "storyboard", digest)
    artifact = (saved or {}).get("artifact")
    if not isinstance(artifact, dict):
        return {
            "available": False,
            "reason": "The storyboard changed since you approved it.",
            "changes": [],
        }
    try:
        current = read_json(root / "work" / "storyboard.json")
    except OSError:
        current = {}
    before = {
        shot.get("id"): shot
        for shot in artifact.get("shots", [])
        if isinstance(shot, dict) and isinstance(shot.get("id"), str)
    }
    after = {
        shot.get("id"): shot
        for shot in current.get("shots", [])
        if isinstance(shot, dict) and isinstance(shot.get("id"), str)
    }
    changes: list[dict[str, str]] = []
    for shot_id in before.keys() | after.keys():
        old = before.get(shot_id)
        new = after.get(shot_id)
        if old == new:
            continue
        if len(changes) < 12:
            changes.append(
                {
                    "field": shot_id,
                    "before": _short(old or "(removed)"),
                    "after": _short(new or "(removed)"),
                }
            )
    if not changes:
        return {"available": True, "reason": "The storyboard's timing changed.", "changes": []}
    return {
        "available": True,
        "reason": f"{len(changes)} shot{'s' if len(changes) != 1 else ''} changed since you approved the storyboard.",
        "changes": changes,
    }


def for_stage(root: Path, stage: str, record: dict | None) -> dict:
    if stage == "brief":
        return brief_changes(root, record)
    if stage == "storyboard":
        return storyboard_changes(root, record)
    digest = (record or {}).get("hash") if isinstance(record, dict) else None
    if not isinstance(digest, str):
        return {"available": False, "reason": None, "changes": []}
    return {"available": False, "reason": None, "changes": []}
