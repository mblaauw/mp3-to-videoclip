"""Why each write happened: one line per change, beside the artifacts it changed.

Evidence only. No approval reads this, so a reason can never un-approve anything. The changed
fields are worked out from the artifact itself, before and after, so they can't disagree with it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..storage import read_optional

FILE = "work/decisions.jsonl"
MAX_REASON = 300
#: Enough to read a change in Details, without a long prompt filling the file.
MAX_VALUE = 400
MAX_DIFF_FIELDS = 40

ARTIFACTS = {
    "update_edit_shots": "work/edit.json",
    "update_voice_lines": "work/edit.json",
    "update_edit": "work/edit.json",
    "set_captions": "work/edit.json",
    "update_treatments": "work/treatments.json",
    "sort_idea": "work/idea.json",
    "place_story": "work/story-passages.json",
    "write_script": "work/script.json",
    "update_lines": "work/script.json",
    "update_brief": "brief.json",
    "set_creative_profile": "brief.json",
    "set_proof_shots": "brief.json",
    "update_shots": "work/storyboard.json",
    "write_storyboard": "work/storyboard.json",
    "create_storyboard": "work/storyboard.json",
    "batch_update_prompts": "work/storyboard.json",
    "propose_motion": "work/motion-proposals.json",
    "write_sound_cues": "work/sound.json",
}
WRITE_TOOLS = frozenset(ARTIFACTS)


def snapshot(root: Path, tool: str) -> Any:
    return read_optional(Path(root) / ARTIFACTS[tool])


def _keyed(items: list) -> dict | None:
    """Lists of things with ids diff by id, so one insert doesn't look like every item moved."""
    keys = ("id", "shot_id")
    for key in keys:
        if items and all(isinstance(item, dict) and key in item for item in items):
            return {str(item[key]): item for item in items}
    return None


def diff(before: Any, after: Any, prefix: str = "") -> dict[str, tuple[Any, Any]]:
    """Every field that differs, named like ``shots.s004.image_prompt``."""
    if before == after:
        return {}
    if isinstance(before, dict) and isinstance(after, dict):
        found: dict[str, tuple[Any, Any]] = {}
        for key in sorted({*before, *after}):
            path = f"{prefix}.{key}" if prefix else str(key)
            found.update(diff(before.get(key), after.get(key), path))
        return found
    if isinstance(before, list) and isinstance(after, list):
        old, new = _keyed(before), _keyed(after)
        if old is not None and new is not None:
            return diff(old, new, prefix)
        if len(before) == len(after):
            found = {}
            for index, (a, b) in enumerate(zip(before, after, strict=True)):
                found.update(diff(a, b, f"{prefix}[{index}]"))
            return found
    return {prefix: (before, after)}


def _short(value: Any) -> Any:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return value if len(text) <= MAX_VALUE else text[: MAX_VALUE - 1] + "…"


def record(
    root: Path,
    *,
    turn_id: str | None,
    role: str | None,
    tool: str,
    reason: str,
    changes: dict[str, tuple[Any, Any]],
    prompt_hash: str | None = None,
) -> str:
    identifier = uuid4().hex
    entry = {
        "id": identifier,
        "at": datetime.now(UTC).isoformat(),
        "turn_id": turn_id,
        "role": role,
        "tool": tool,
        "artifact": ARTIFACTS.get(tool),
        "reason": reason,
        "changed_fields": sorted(changes),
        "before_after": {
            field: {"before": _short(a), "after": _short(b)}
            for field, (a, b) in sorted(changes.items())[:MAX_DIFF_FIELDS]
        },
        "prompt_hash": prompt_hash,
    }
    path = Path(root) / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return identifier


def read(root: Path) -> list[dict]:
    path = Path(root) / FILE
    rows = []
    for line in path.read_text().splitlines() if path.is_file() else []:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def find(root: Path, identifier: str) -> dict | None:
    return next((row for row in read(root) if row.get("id") == identifier), None)


def recent_reasons(root: Path, limit: int = 12) -> list[str]:
    """The newest reasons, oldest first, for a summary of what a long film has done."""
    return [
        f"{row.get('tool')}: {row.get('reason')}"
        for row in read(root)[-limit:]
        if row.get("reason")
    ]


OTHER = {"writer": "editor", "editor": "writer"}
ANSWER_LIMIT = 400


def handoff(root: Path, role: str | None) -> str:
    """What the other role said and why, so neither one works blind. Not the whole thread."""
    from .conversation import load_messages

    other = OTHER.get(role or "")
    if other is None:
        return ""
    answers = [
        " ".join(message["content"].split())[:ANSWER_LIMIT]
        for message in load_messages(root, other)
        if message.get("role") == "assistant"
        and isinstance(message.get("content"), str)
        and message["content"].strip()
        and not message.get("with_tools")
    ][-3:]
    reasons = [row for row in read(root) if row.get("role") == other and row.get("reason")][-6:]
    if not answers and not reasons:
        return ""
    lines = [f"## From the {other.capitalize()}"]
    lines += [f"- Said: {answer}" for answer in answers]
    lines += [
        f"- Changed {', '.join(row.get('changed_fields', [])[:4]) or row.get('tool')}: {row['reason']}"
        for row in reasons
    ]
    return "\n".join(lines)
