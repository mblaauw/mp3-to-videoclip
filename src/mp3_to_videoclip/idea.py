"""Your own idea: kept exactly as pasted, then sorted without changing a word.

``work/idea.jsonl`` is append-only. A paste is saved whole as the treatment at
once, so a failed Writer turn loses nothing. A sort may only say which of your
sentences are story, style, rules or things to avoid: every fragment must be
found in the paste, no words may be left over, and what reaches the brief is the
paste's own text, not the Writer's copy of it.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from . import production as P
from . import verbatim
from .storage import state_mutation

LOG = "work/idea.jsonl"
PARTS = ("story", "style", "rules", "avoid")
MAX_PASTE = 24_000
MAX_AVOID = P.PROFILE_MAX_AVOID


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _records(root: Path) -> list[dict]:
    path = root / LOG
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _append(root: Path, record: dict) -> None:
    path = root / LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def latest(root: Path) -> dict | None:
    """The newest paste and how it is sorted now, or None if there has never been one."""
    records = _records(root)
    paste = next((item for item in reversed(records) if item["kind"] == "paste"), None)
    if paste is None:
        return None
    sort = next(
        (
            item
            for item in reversed(records)
            if item["kind"] == "sort" and item["paste_id"] == paste["id"]
        ),
        None,
    )
    brief = P.load_brief(root)
    return {
        "id": paste["id"],
        "at": paste["at"],
        "text": paste["text"],
        "sorted": {part: sort[part] for part in PARTS} if sort else None,
        "sorted_by": sort["by"] if sort else None,
        "current": _fields(brief) == _expected(paste, sort),
    }


def _fields(brief) -> dict:
    return {
        "treatment": brief.treatment,
        "style": brief.style,
        "direction": brief.direction,
        "avoid": brief.avoid,
    }


def _compose(paste: dict, parts: dict[str, list[str]], story: str) -> dict:
    base = paste["base"]
    return {
        "treatment": story,
        "style": " ".join(parts["style"]) or base["style"],
        "direction": " ".join(parts["rules"]) or base["direction"],
        "avoid": base["avoid"] + [item for item in parts["avoid"] if item not in base["avoid"]],
    }


def _expected(paste: dict, sort: dict | None) -> dict:
    if sort is None:
        return {
            "treatment": paste["text"],
            "style": paste["base"]["style"],
            "direction": paste["base"]["direction"],
            "avoid": paste["base"]["avoid"],
        }
    return _compose(paste, sort, sort["treatment"])


def slice_paste(paste: str, parts: dict) -> tuple[dict[str, list[str]], str]:
    """Return each part as the paste's own text, and the story with its paragraphs.

    Refuses a fragment that is not in the paste, one used twice, and any word left
    unassigned, which would otherwise disappear without anyone noticing.
    """
    unknown = set(parts) - set(PARTS)
    if unknown:
        raise ValueError(f"unknown parts: {', '.join(sorted(unknown))}")
    taken = [False] * len(paste)
    spans: dict[str, list[tuple[int, int]]] = {part: [] for part in PARTS}
    for part in PARTS:
        fragments = parts.get(part) or []
        if not isinstance(fragments, list):
            raise ValueError(f"{part} must be a list of text")
        for fragment in fragments:
            if not isinstance(fragment, str) or not fragment.strip():
                raise ValueError(f"{part} has an empty entry")
            for match in verbatim.pattern(fragment).finditer(paste):
                if not any(taken[match.start() : match.end()]):
                    taken[match.start() : match.end()] = [True] * (match.end() - match.start())
                    spans[part].append(match.span())
                    break
            else:
                raise ValueError(
                    f"this is not word for word in the paste, or is used twice: {fragment[:120]!r}"
                )
    left = "".join(char if not taken[index] else "\0" for index, char in enumerate(paste))
    missing = [piece.strip() for piece in left.split("\0") if any(char.isalnum() for char in piece)]
    if missing:
        raise ValueError(f"these words were not assigned to any part: {missing[0][:120]!r}")
    for part in PARTS:
        spans[part].sort()
    if len(spans["avoid"]) > MAX_AVOID:
        raise ValueError(
            f"keep at most {MAX_AVOID} things to avoid; put the others under rules instead"
        )
    return (
        {part: [paste[start:end] for start, end in spans[part]] for part in PARTS},
        _story_text(paste, spans["story"]),
    )


def _story_text(paste: str, spans: list[tuple[int, int]]) -> str:
    story = ""
    for index, (start, end) in enumerate(spans):
        if index:
            gap = paste[spans[index - 1][1] : start]
            story += "\n\n" if re.search(r"\n\s*\n", gap) else " "
        story += paste[start:end]
    return story


@state_mutation
def keep_paste(root: Path, text: str) -> dict:
    """Keep a new paste and make it the whole story until it is sorted."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("paste your idea first")
    if len(text) > MAX_PASTE:
        raise ValueError(f"keep the idea under {MAX_PASTE:,} characters")
    text = text.strip()
    brief = P.load_brief(root)
    previous = latest(root)
    # Starting over on your own last sort must not make its sorted fields the new base.
    base = (
        _base_of(root, previous["id"])
        if previous and previous["current"]
        else {"style": brief.style, "direction": brief.direction, "avoid": brief.avoid}
    )
    record = {
        "kind": "paste",
        "id": uuid.uuid4().hex[:12],
        "at": _now(),
        "text": text,
        "base": base,
    }
    P.update_brief(root, {"treatment": text, "script": [], **base})
    _append(root, record)
    return latest(root)


def _base_of(root: Path, paste_id: str) -> dict:
    return next(
        item["base"]
        for item in _records(root)
        if item["kind"] == "paste" and item["id"] == paste_id
    )


@state_mutation
def apply_sort(root: Path, parts: dict, *, by: str) -> dict:
    """Sort the newest paste into the brief, unless the brief has moved on since."""
    records = _records(root)
    paste = next((item for item in reversed(records) if item["kind"] == "paste"), None)
    if paste is None:
        raise ValueError("there is no idea to sort; paste one on the Start tab first")
    if not isinstance(parts, dict):
        raise ValueError("the sorted idea must be a JSON object")
    sorted_parts, story = slice_paste(paste["text"], parts)
    previous = next(
        (
            item
            for item in reversed(records)
            if item["kind"] == "sort" and item["paste_id"] == paste["id"]
        ),
        None,
    )
    if _fields(P.load_brief(root)) != _expected(paste, previous):
        raise ValueError(
            "the story, style or rules were edited after this idea was pasted, so sorting "
            "it again would overwrite those edits; change the text directly instead"
        )
    P.update_brief(root, _compose(paste, sorted_parts, story))
    _append(
        root,
        {
            "kind": "sort",
            "paste_id": paste["id"],
            "at": _now(),
            "by": by,
            "treatment": story,
            **sorted_parts,
        },
    )
    return latest(root)
