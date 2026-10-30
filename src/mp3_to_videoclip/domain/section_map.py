"""The owner's corrected sections, kept apart from the measured analysis.

`work/music.json` is the measurement and sits at the root of the approval chain, so
it is never touched. This file is a layer over it: moved edges, added or joined
sections and their names. Reset simply stops using the layer, which is why nothing
done here needs re-measuring to undo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mp3_to_videoclip.domain import lyric_timing, music_notes
from mp3_to_videoclip.storage import project_lock, read_optional, state_lock, write_json

FILE = "work/section-map.json"
MIN_SECTION_SECONDS = 2.0
SNAP_BEFORE_SECONDS = 5.0


def read(root: Path) -> list[dict[str, Any]] | None:
    """The saved sections, or None when the measured sections are in use."""
    value = read_optional(Path(root) / FILE)
    sections = value.get("sections") if isinstance(value, dict) else None
    if not isinstance(sections, list) or not sections:
        return None
    return [item for item in sections if isinstance(item, dict)]


def _energy(music: dict, start: float, end: float) -> float:
    points = [
        float(point.get("energy") or 0)
        for point in music.get("energy_curve") or []
        if isinstance(point, dict) and start <= float(point.get("time") or 0) < end
    ]
    return sum(points) / len(points) if points else 0.0


def apply(root: Path, music: dict | None) -> dict | None:
    """A display copy of the analysis with the sections the owner is working with."""
    if not isinstance(music, dict):
        return music
    saved = read(root)
    if saved is None:
        return music_notes.apply_names(music, music_notes.read(root))
    duration = float(music.get("duration") or saved[-1]["start"] + MIN_SECTION_SECONDS)
    sections = []
    for index, item in enumerate(saved):
        start = float(item["start"])
        end = float(saved[index + 1]["start"]) if index + 1 < len(saved) else duration
        sections.append(
            {
                "start": start,
                "end": end,
                "energy": _energy(music, start, end),
                "label": "section",
                "name": item["name"],
            }
        )
    return {**music, "sections": sections}


def names_by_start(root: Path) -> dict[float, str]:
    """Every name the owner has given, measured or corrected, by its start."""
    names = music_notes.names_by_start(root)
    for item in read(root) or []:
        names[round(float(item["start"]), 3)] = item["name"]
    return names


def _measured_starts(root: Path) -> list[float]:
    music = read_optional(Path(root) / "work" / "music.json")
    if not isinstance(music, dict) or not isinstance(music.get("sections"), list):
        raise ValueError("measure the song before changing its sections")
    return [round(float(item["start"]), 3) for item in music["sections"] if isinstance(item, dict)]


def save(root: Path, payload: dict, duration: float) -> dict[str, Any]:
    """Replace the corrected sections with a complete, ordered list."""
    if not isinstance(payload, dict) or set(payload) - {"sections"}:
        raise ValueError("the section map must contain a sections list")
    sections = payload.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("the section map must contain a sections list")
    if len(sections) > music_notes.MAX_SECTIONS:
        raise ValueError(f"keep the song under {music_notes.MAX_SECTIONS} sections")
    _measured_starts(root)
    result = []
    for item in sections:
        if not isinstance(item, dict) or set(item) - {"start", "name"}:
            raise ValueError("each section needs a start and a name")
        start = item.get("start")
        name = item.get("name")
        if isinstance(start, bool) or not isinstance(start, (int, float)):
            raise ValueError("each section needs a start in seconds")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= music_notes.MAX_NAME:
            raise ValueError(f"a section name must be 1–{music_notes.MAX_NAME} characters")
        result.append({"start": round(float(start), 3), "name": name.strip()})
    if result[0]["start"] != 0:
        raise ValueError("the first section must start at the beginning of the song")
    ends = [item["start"] for item in result[1:]] + [duration]
    for item, end in zip(result, ends, strict=True):
        if end - item["start"] < MIN_SECTION_SECONDS:
            raise ValueError(f"a section must be at least {MIN_SECTION_SECONDS:.0f} seconds long")
    with project_lock(Path(root)), state_lock(Path(root)):
        write_json(Path(root) / FILE, {"sections": result})
    return {"sections": result}


def _detected_edges(root: Path) -> list[float]:
    edges = set(_measured_starts(root))
    deep = read_optional(Path(root) / "work" / "music-deep.json")
    for item in deep.get("sections") or [] if isinstance(deep, dict) else []:
        value = item.get("time") if isinstance(item, dict) else item
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            edges.add(round(float(value), 3))
    return sorted(edges)


def propose(root: Path, duration: float) -> list[dict[str, Any]]:
    """Sections from the song's own tags and line times, for the owner to accept.

    A sung part starts at its first word and an instrumental part where the last
    word before it ends. Each then moves to a detected edge just before it, because
    the music often turns first, but never back across a sung word. A tag with no
    time around it is left out.
    """
    rows = lyric_timing.view(root)["lines"]
    if not any(row["tag"] for row in rows):
        raise ValueError("these lyrics have no [Verse] or [Hook] style names")
    if not any(row["start"] is not None for row in rows):
        raise ValueError("put the words on the song first")
    edges = _detected_edges(root)
    proposed: list[dict[str, Any]] = []
    for position, row in enumerate(rows):
        if not row["tag"]:
            continue
        following = rows[position + 1] if position + 1 < len(rows) else None
        start = following["start"] if following and not following["tag"] else None
        earlier = [
            item.get("end") or item["start"]
            for item in rows[:position]
            if item["start"] is not None
        ]
        sung_until = earlier[-1] if earlier else 0.0
        if start is None:
            start = earlier[-1] if earlier else None
        if start is None:
            continue
        # An edge may only pull a start back as far as the last sung word.
        candidates = [
            edge
            for edge in edges
            if 0 <= start - edge <= SNAP_BEFORE_SECONDS and edge >= sung_until
        ]
        proposed.append(
            {"start": candidates[-1] if candidates else round(start, 3), "name": row["tag"]}
        )
    sections: list[dict[str, Any]] = []
    for item in proposed:
        last = sections[-1]["start"] if sections else None
        if item["start"] <= (last if last is not None else -1) + MIN_SECTION_SECONDS:
            continue
        if duration - item["start"] < MIN_SECTION_SECONDS:
            continue
        sections.append(item)
    if not sections:
        raise ValueError("the lyric tags couldn't be placed on the song")
    if sections[0]["start"] < MIN_SECTION_SECONDS:
        sections[0]["start"] = 0.0
    else:
        sections.insert(0, {"start": 0.0, "name": music_notes.default_name(0)})
    return sections


def reset(root: Path) -> None:
    """Back to the detected sections, keeping names of the ones that still exist."""
    measured = set(_measured_starts(root))
    saved = read(root) or []
    kept = {
        round(float(item["start"]), 3): item["name"]
        for item in saved
        if round(float(item["start"]), 3) in measured
    }
    if kept:
        names = {**music_notes.names_by_start(root), **kept}
        music_notes.save(
            root,
            {
                "sections": [
                    {
                        "start": start,
                        "name": names.get(start) or music_notes.default_name(index),
                    }
                    for index, start in enumerate(sorted(measured))
                ]
            },
        )
    with project_lock(Path(root)), state_lock(Path(root)):
        write_json(Path(root) / FILE, {"sections": None})
