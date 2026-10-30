"""The story on the song: when each passage of the treatment plays.

Timings live in ``work/story-beats.json``, outside the brief, so placing them never
un-approves the story. The treatment stays the only copy of the words: a passage
counts as placed only while its text is still in the treatment, so an edited
passage reads as not on the song rather than showing a time that no longer fits.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import production as P
from . import verbatim
from .models import StoryPlacement
from .storage import digest, read_json, read_optional, state_mutation, write_json

PATH = "work/story-beats.json"


@state_mutation
def place_story(root: Path, payload: dict) -> StoryPlacement:
    """Save the timings, refusing any change to the words or a time outside the film."""
    if not isinstance(payload, dict):
        raise ValueError("the placement must be a JSON object")
    try:
        placement = StoryPlacement.model_validate(payload)
    except ValueError as exc:
        raise ValueError(f"the placement is invalid: {exc}") from exc
    treatment = P.load_brief(root).treatment
    placed = [word for item in placement.passages for word in verbatim.words(item.text)]
    if placed != verbatim.words(treatment):
        raise ValueError(
            "the passages must hold every word of brief.treatment, unchanged and in order"
        )
    duration = P.load_project(root, verify_source=False).duration
    last = placement.passages[-1].end
    if last > duration + 0.5:
        raise ValueError(f"a passage ends at {last:.1f} s, but the film is {duration:.1f} s")
    value = placement.model_dump()
    path = root / PATH
    previous = read_optional(path)
    if previous == value:
        return placement
    if isinstance(previous, dict):
        _keep(root, previous)
    write_json(path, value)
    return placement


def _keep(root: Path, value: dict) -> None:
    history = root / f"work/story-beats-history/{digest(value)}.json"
    if not history.exists():
        write_json(history, value)


@state_mutation
def set_aside(root: Path) -> None:
    """The excerpt moved, so the times point at other music: history keeps them, unplaced."""
    path = root / PATH
    if path.is_file():
        _keep(root, read_json(path))
        path.unlink()


def _untimed(treatment: str, start: int, end: int) -> list[dict]:
    pieces = []
    for match in re.finditer(r"\S(?:.*?\S)??(?=\s*\n\s*\n|\s*\Z)", treatment[start:end], re.S):
        pieces.append(
            {
                "text": match.group(),
                "start": None,
                "end": None,
                "from": start + match.start(),
                "to": start + match.end(),
            }
        )
    return pieces


def passages(root: Path) -> list[dict]:
    """The treatment in order: placed passages with times, the rest by paragraph without."""
    treatment = P.load_brief(root).treatment
    path = root / PATH
    placed = read_json(path).get("passages", []) if path.is_file() else []
    result: list[dict] = []
    cursor = 0
    for item in placed:
        match = verbatim.pattern(item["text"]).search(treatment, cursor)
        if match is None:
            continue
        result += _untimed(treatment, cursor, match.start())
        result.append(
            {
                "text": match.group(),
                "start": item["start"],
                "end": item["end"],
                "from": match.start(),
                "to": match.end(),
            }
        )
        cursor = match.end()
    return result + _untimed(treatment, cursor, len(treatment))
