"""Typed local approval decisions with exact content hashes and notes.

This is the decision contract the Studio API uses. It is deliberately small:
stage name validation, the note/hash/confirmation body, the stage-specific
attestations, and one locked write through ``production.approve``.
"""

from __future__ import annotations

import re
from pathlib import Path

from mp3_to_videoclip import production as P
from mp3_to_videoclip.storage import project_lock, read_json


class ApprovalError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def stage_name(stage: str) -> str:
    if stage not in P.UPSTREAM:
        raise ApprovalError("unknown approval stage", 404)
    return stage


def _body(body, allowed, hash_key):
    if not isinstance(body, dict) or set(body) - allowed:
        raise ApprovalError("unexpected decision fields")
    if body.get("confirmed") is not True:
        raise ApprovalError("explicit review confirmation is required")
    note = body.get("note")
    if note is None:
        note = ""
    if not isinstance(note, str) or len(note.strip()) > 2000:
        raise ApprovalError("a decision note may be at most 2000 characters")
    if not isinstance(body.get(hash_key), str) or not re.fullmatch(r"[0-9a-f]{64}", body[hash_key]):
        raise ApprovalError("the reviewed content hash is required")
    return note.strip()


def approve_stage(root: Path, stage: str, body: dict):
    stage_name(stage)
    note = _body(
        body,
        {
            "note",
            "expected_hash",
            "confirmed",
            "acknowledge_uncertain",
            "inspected",
            "preview_watched",
        },
        "expected_hash",
    )
    for flag, applicable in (
        ("inspected", "graphics"),
        ("acknowledge_uncertain", "lyrics"),
        ("preview_watched", "preview"),
    ):
        if flag in body and (type(body[flag]) is not bool or stage != applicable):
            raise ApprovalError(f"{flag} is only valid for {applicable}")
    if stage == "preview" and body.get("preview_watched") is not True:
        raise ApprovalError("confirm continuous preview playback with the actual music")
    with project_lock(root):
        saved = read_json(root / "work/approvals.json")
        if not isinstance(saved, dict) or any(
            not isinstance(item, dict) for item in saved.values()
        ):
            raise ApprovalError("saved approval records are invalid; inspect them locally")
        if P.stage_hash(root, stage) != body["expected_hash"]:
            raise ApprovalError(
                "Stage changed. Inspect the current artifacts before deciding.", 409
            )
        P.approve(
            root,
            stage,
            note,
            body.get("acknowledge_uncertain", False),
            inspected=body.get("inspected", False),
            expected_hash=body["expected_hash"],
            via="studio",
            preview_watched=body.get("preview_watched", False),
            review_confirmed=True,
        )
        record = read_json(root / "work/approvals.json")[stage]
    return {"approved": stage, "record": record, "generated": False}
