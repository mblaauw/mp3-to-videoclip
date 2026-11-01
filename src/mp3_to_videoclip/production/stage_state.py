"""Exact approval state for the library, remembered until a file it depends on moves.

A small file beside the settings holds whether each decision's recorded hash still
matches, and a fingerprint of the metadata those hashes read. Stills and source audio
are immutable by rule and their selection lives in that metadata, so a listing recomputes
a film only when something really changed. It is a view: no gate ever reads it, and
opening the library writes nothing into a film's folder.
"""

from __future__ import annotations

from pathlib import Path

from .. import config
from ..storage import digest, read_optional, write_json
from .approvals import stage_hash

#: The decisions the library reports on.
STAGES = ("brief", "storyboard", "proof", "stills")
#: Written by views and by the record of a conversation, never read by a stage hash.
DERIVED = frozenset({"song-map.json", "prompt-current.json"})


def state_path(root: Path) -> Path:
    name = digest(str(Path(root).resolve()))[:32]
    return config.settings_path().parent / "stage-state" / f"{name}.json"


def fingerprint(root: Path) -> dict[str, list[int]]:
    paths = [root / "project.json", root / "brief.json", *sorted((root / "work").glob("*.json"))]
    prints = {}
    for path in paths:
        if path.name in DERIVED:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        prints[path.relative_to(root).as_posix()] = [stat.st_size, stat.st_mtime_ns]
    return prints


def stale(root: Path, approvals: dict) -> dict[str, bool]:
    """For each recorded decision, whether its artifacts no longer match it."""
    current = fingerprint(root)
    path = state_path(root)
    saved = read_optional(path)
    if isinstance(saved, dict) and saved.get("fingerprint") == current:
        return saved.get("stale") or {}
    result = {}
    for stage in STAGES:
        record = approvals.get(stage)
        if not isinstance(record, dict):
            continue
        try:
            result[stage] = stage_hash(root, stage) != record.get("hash")
        except (OSError, ValueError, KeyError):
            result[stage] = True
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, {"fingerprint": current, "stale": result})
    except OSError:
        pass  # Listed all the same, just recomputed next time.
    return result
