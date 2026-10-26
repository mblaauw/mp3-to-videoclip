"""The prompt revision that produced a chat turn or an artifact write.

The assembled prompt hash and every file version are written before a turn
starts. Tool/API artifact writes append the same record, so a bad output can be
traced to the exact prompt that produced it without changing the artifact
schema or its approval hash.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .storage import read_optional, write_json

CURRENT = "work/prompt-current.json"
HISTORY = "work/prompt-artifacts.jsonl"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def remember(root: Path, meta: dict) -> None:
    write_json(root / CURRENT, {**meta, "at": _now()})


def current(root: Path) -> dict | None:
    value = read_optional(root / CURRENT)
    return value if isinstance(value, dict) else None


def latest(root: Path, artifact: str) -> dict | None:
    """Prompt metadata of the last write to one artifact, if it was recorded.

    Artifact writes can happen after a later chat turn, so the current prompt is
    not necessarily the one that produced the file. The append-only history is
    the authoritative provenance; readers fall back to ``current`` only when
    there is no artifact record at all.
    """
    path = root / HISTORY
    if not path.is_file():
        return None
    found = None
    for line in path.read_text().splitlines():
        try:
            entry = json.loads(line)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(entry, dict) and entry.get("artifact") == artifact:
            found = entry
    if found is None:
        return None
    return {key: value for key, value in found.items() if key not in ("artifact", "at", "detail")}


def record(root: Path, artifact: str, detail: dict | None = None) -> None:
    meta = current(root)
    if meta is None:
        return
    entry = {**meta, "artifact": artifact, "at": _now()}
    if detail:
        entry["detail"] = detail
    path = root / HISTORY
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
