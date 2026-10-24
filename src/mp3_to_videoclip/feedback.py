"""Durable user revision requests for the guided Studio flow.

This is not an approval and it never spends. A person records what should change
in the workspace; the agent reads the request, revises the canonical artifacts,
and records a short reply. Keeping it a file makes the loop survive a reload and
keeps the GUI honest about what has and has not happened yet.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .storage import read_json, write_json

FILE = "work/feedback.json"
STAGES = ("track", "story", "style", "images", "finish")
SCOPES = ("whole", "section", "shot")
STATUSES = ("open", "resolved")
MAX_REQUESTS = 200
MAX_MESSAGE = 4000
MAX_STYLE = 20000


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _read(root: Path) -> list[dict]:
    value = read_json(Path(root) / FILE) if (Path(root) / FILE).is_file() else []
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError("feedback record is invalid; inspect work/feedback.json locally")
    return value


def _clean(value, name: str, limit: int, *, required=True) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    text = value.strip()
    if required and not text:
        raise ValueError(f"{name} must not be empty")
    if len(text) > limit:
        raise ValueError(f"{name} is too long (max {limit} characters)")
    return text


def record(
    root: Path,
    *,
    stage: str,
    message: str,
    scope: str = "whole",
    target: str | None = None,
    style: str | None = None,
    author: str = "studio",
) -> dict:
    if stage not in STAGES:
        raise ValueError(f"stage must be one of {', '.join(STAGES)}")
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {', '.join(SCOPES)}")
    if scope == "whole" and target:
        raise ValueError("a whole-step request has no shot/section target")
    if scope != "whole":
        target = _clean(target, "target", 120)
    request = {
        "id": f"fb-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:6]}",
        "stage": stage,
        "scope": scope,
        "target": target or None,
        "message": _clean(message, "message", MAX_MESSAGE),
        "style": _clean(style, "style", MAX_STYLE, required=False),
        "author": _clean(author, "author", 80),
        "status": "open",
        "created_at": _now(),
        "resolved_at": None,
        "reply": None,
    }
    requests = _read(Path(root))
    requests.append(request)
    if len(requests) > MAX_REQUESTS:
        raise ValueError(
            "feedback history is full; resolve or archive older requests before adding another"
        )
    write_json(Path(root) / FILE, requests)
    return request


def requests(root: Path, *, stage: str | None = None, status: str | None = None) -> list[dict]:
    if stage is not None and stage not in STAGES:
        raise ValueError(f"stage must be one of {', '.join(STAGES)}")
    if status is not None and status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}")
    rows = _read(Path(root))
    if stage is not None:
        rows = [row for row in rows if row.get("stage") == stage]
    if status is not None:
        rows = [row for row in rows if row.get("status") == status]
    return rows


def resolve(root: Path, request_id: str, *, reply: str, author: str = "agent") -> dict:
    reply = _clean(reply, "reply", MAX_MESSAGE)
    author = _clean(author, "author", 80)
    rows = _read(Path(root))
    match = next((row for row in rows if row.get("id") == request_id), None)
    if match is None:
        raise ValueError(f"unknown feedback request {request_id!r}")
    if match.get("status") == "resolved":
        raise ValueError("this feedback request is already resolved")
    match.update(
        status="resolved",
        reply=reply,
        resolved_by=author,
        resolved_at=_now(),
    )
    write_json(Path(root) / FILE, rows)
    return match
