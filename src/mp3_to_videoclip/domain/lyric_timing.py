"""When each lyric line starts, kept apart from the words.

`work/lyrics.json` sits in the approval chain, so putting times in it would
un-approve every story. This file is a layer beside it: lines are matched back to
the words by their text, and a line whose words changed simply has no time until
it gets a new one. A time is never guessed.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from mp3_to_videoclip.storage import project_lock, read_optional, state_lock, write_json

FILE = "work/lyric-timing.json"
SOURCES = ("tapped", "auto")
_TAG = re.compile(r"^\[([^\[\]]+)\]$")
_LRC = "lrc"


def tag_of(text: str) -> str | None:
    """The name inside a `[Spoken Hook]` line: a heading of the song, not a sung line."""
    match = _TAG.match(text.strip())
    return match.group(1).strip() if match else None


def word_lines(lyrics: dict | None) -> list[dict[str, Any]]:
    """Every line of the words in order, with an LRC line's own start if it has one."""
    if not isinstance(lyrics, dict):
        return []
    rows: list[dict[str, Any]] = []
    if lyrics.get("lines"):
        rows = [{"text": str(text), "start": None} for text in lyrics["lines"]]
    else:
        for segment in lyrics.get("segments") or []:
            parts = [part for part in str(segment.get("text", "")).splitlines() if part.strip()]
            # A multi-line segment is a container: its start is not any one line's start.
            start = float(segment["start"]) if len(parts) == 1 else None
            rows.extend({"text": part, "start": start} for part in parts)
    return [
        {"index": index, "text": row["text"], "tag": tag_of(row["text"]), "start": row["start"]}
        for index, row in enumerate(rows)
    ]


def _saved(root: Path) -> list[dict[str, Any]]:
    value = read_optional(Path(root) / FILE)
    lines = value.get("lines") if isinstance(value, dict) else None
    return [item for item in lines or [] if isinstance(item, dict) and "text" in item]


def view(root: Path) -> dict[str, Any]:
    """The words as they are now, each with the time saved for that same text."""
    rows = word_lines(read_optional(Path(root) / "work" / "lyrics.json"))
    sung = [row for row in rows if not row["tag"]]
    saved = _saved(root)
    matcher = SequenceMatcher(
        None,
        [str(item["text"]) for item in saved],
        [row["text"] for row in sung],
        autojunk=False,
    )
    found: dict[int, dict[str, Any]] = {}
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            found[sung[block.b + offset]["index"]] = saved[block.a + offset]
    lines = []
    for row in rows:
        item = found.get(row["index"]) or {}
        start = item.get("start")
        source = item.get("source") if start is not None else None
        if start is None and row["start"] is not None:
            start, source = row["start"], _LRC
        lines.append(
            {
                "index": row["index"],
                "text": row["text"],
                "tag": row["tag"],
                "start": start,
                "end": item.get("end") if source in SOURCES else None,
                "source": source,
            }
        )
    return {"lines": lines}


def _number(value: Any, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{what} must be a number of seconds")
    return float(value)


def save(root: Path, payload: dict, duration: float) -> dict[str, Any]:
    """Replace the times. Lines are named by position, so the words can't be altered here."""
    if not isinstance(payload, dict) or set(payload) - {"lines"}:
        raise ValueError("lyric timing must contain a lines list")
    items = payload.get("lines")
    if not isinstance(items, list):
        raise ValueError("lyric timing must contain a lines list")
    rows = word_lines(read_optional(Path(root) / "work" / "lyrics.json"))
    by_index = {row["index"]: row for row in rows}
    timed: dict[int, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict) or set(item) - {"index", "start", "end", "source"}:
            raise ValueError("each line needs an index, a start and a source")
        row = by_index.get(item.get("index"))
        if row is None:
            raise ValueError("that line is not in the lyrics")
        if row["tag"]:
            raise ValueError("a section name in brackets is not sung, so it has no time")
        if item.get("source") not in SOURCES:
            raise ValueError("a line's source must be tapped or auto")
        start = _number(item.get("start"), "a line's start")
        if not 0 <= start < duration:
            raise ValueError("a line's start must be inside the song")
        end = item.get("end")
        if end is not None:
            end = _number(end, "a line's end")
            if not start < end <= duration:
                raise ValueError("a line's end must follow its start, inside the song")
        if row["index"] in timed:
            raise ValueError("a line may only be timed once")
        timed[row["index"]] = {"start": start, "end": end, "source": item["source"]}
    ordered = [timed[index]["start"] for index in sorted(timed)]
    if any(later < earlier for earlier, later in zip(ordered, ordered[1:], strict=False)):
        raise ValueError("lyric lines must stay in order")
    lines = [
        {"text": row["text"], **timed.get(row["index"], {"start": None})}
        for row in rows
        if not row["tag"]
    ]
    with project_lock(Path(root)), state_lock(Path(root)):
        write_json(Path(root) / FILE, {"lines": lines})
    return view(root)
