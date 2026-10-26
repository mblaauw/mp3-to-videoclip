"""Human section names, kept apart from the measured analysis.

`work/music.json` remains the measurement. This file is the Studio's naming
layer, so renaming a section never rewrites a single measured sample or changes
an approval hash that binds the analysis bytes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mp3_to_videoclip.storage import project_lock, read_optional, write_json

FILE = "work/music-notes.json"
MAX_SECTIONS = 64
MAX_NAME = 80


def default_name(index: int) -> str:
    return f"Section {index + 1}"


def read(root: Path) -> dict[str, list[dict[str, Any]]]:
    """Return only usable saved names, in section order."""
    value = read_optional(Path(root) / FILE)
    sections: list[dict[str, Any]] = []
    if isinstance(value, dict) and isinstance(value.get("sections"), list):
        for item in value["sections"][:MAX_SECTIONS]:
            if not isinstance(item, dict):
                continue
            start = item.get("start")
            name = item.get("name")
            if isinstance(start, bool) or not isinstance(start, (int, float)):
                continue
            if not isinstance(name, str) or not name.strip():
                continue
            sections.append({"start": round(float(start), 3), "name": name.strip()[:MAX_NAME]})
    return {"sections": sections}


def names_by_start(root: Path) -> dict[float, str]:
    return {round(float(item["start"]), 3): item["name"] for item in read(root)["sections"]}


def apply_names(music: dict | None, notes: dict) -> dict | None:
    """Return a display-only copy with `name` added to every measured section."""
    if not isinstance(music, dict):
        return music
    names = {round(float(item["start"]), 3): item["name"] for item in notes["sections"]}
    sections = []
    for index, item in enumerate(music.get("sections") or []):
        if not isinstance(item, dict):
            sections.append(item)
            continue
        start = item.get("start")
        key = round(float(start), 3) if isinstance(start, (int, float)) else None
        name = names.get(key) if key is not None else None
        sections.append({**item, "name": name or default_name(index)})
    return {**music, "sections": sections}


def _measured_sections(root: Path) -> dict[float, dict]:
    music = read_optional(Path(root) / "work" / "music.json")
    if not isinstance(music, dict) or not isinstance(music.get("sections"), list):
        raise ValueError("measure the song before naming its sections")
    measured: dict[float, dict] = {}
    for item in music["sections"]:
        if not isinstance(item, dict) or not isinstance(item.get("start"), (int, float)):
            continue
        measured[round(float(item["start"]), 3)] = item
    if not measured:
        raise ValueError("measure the song before naming its sections")
    return measured


def save(root: Path, payload: dict) -> dict:
    """Replace all names at once; every start must be a measured section."""
    if not isinstance(payload, dict) or set(payload) - {"sections"}:
        raise ValueError("music notes must contain a sections list")
    measured = _measured_sections(root)
    sections = payload.get("sections")
    if not isinstance(sections, list):
        raise ValueError("sections must be a list")
    if len(sections) != len(measured):
        raise ValueError("name every measured section exactly once")
    result: list[dict[str, Any]] = []
    seen: set[float] = set()
    for item in sections:
        if not isinstance(item, dict) or set(item) - {"start", "name"}:
            raise ValueError("each section needs a start and a name")
        start = item.get("start")
        name = item.get("name")
        if isinstance(start, bool) or not isinstance(start, (int, float)):
            raise ValueError("each section needs a measured start")
        key = round(float(start), 3)
        if key not in measured:
            raise ValueError("section starts must match the measured sections")
        if key in seen:
            raise ValueError("a section start may only be named once")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= MAX_NAME:
            raise ValueError(f"a section name must be 1–{MAX_NAME} characters")
        seen.add(key)
        result.append({"start": key, "name": name.strip()})
    result.sort(key=lambda item: item["start"])
    with project_lock(Path(root)):
        write_json(Path(root) / FILE, {"sections": result})
    return {"sections": result}
