"""Read-only view of productions frozen before schema version 3.

The two finished films are never migrated and never written again. This reader
answers the only questions the library needs about them — title, duration, the
newest render and the selected stills — and tolerates missing or malformed
metadata instead of failing a whole listing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = 3
_VERSIONED = re.compile(r"-v(\d+)\.mp4$")


@dataclass(frozen=True)
class ArchivedFilm:
    """One frozen production as the library shows it."""

    slug: str
    root: Path
    title: str
    duration: float | None
    render: Path | None
    stills: tuple[Path, ...]


def _read_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def is_archived(root: Path) -> bool:
    """True for a production folder this reader owns: no schema_version 3."""
    project = _read_json(Path(root) / "project.json")
    if project is None:
        return False
    return project.get("schema_version") != SCHEMA_VERSION


def _assets(root: Path) -> dict:
    data = _read_json(root / "work" / "assets.json") or {}
    shots = data.get("shots")
    return shots if isinstance(shots, dict) else data


def selected_stills(root: Path) -> tuple[Path, ...]:
    """The selected version of every shot, in asset-file order; missing files are skipped."""
    stills: list[Path] = []
    for entry in _assets(root).values():
        if not isinstance(entry, dict):
            continue
        versions = [v for v in entry.get("versions") or [] if isinstance(v, dict)]
        if not versions:
            continue
        selected = next((v for v in versions if v.get("version") == entry.get("selected")), None)
        chosen = selected or versions[-1]
        stored = chosen.get("path")
        if not isinstance(stored, str) or not stored:
            continue
        path = (root / stored).resolve()
        if path.is_file():
            stills.append(path)
    return tuple(stills)


def newest_render(root: Path) -> Path | None:
    """The newest finished render, preferring ``*-final-*`` over intermediate bases."""
    renders = [p for p in (root / "renders").glob("*.mp4") if p.is_file()]
    if not renders:
        return None
    finals = [p for p in renders if "-final-" in p.name]
    pool = finals or renders

    def rank(path: Path) -> tuple[int, float]:
        match = _VERSIONED.search(path.name)
        return (int(match.group(1)) if match else 0, path.stat().st_mtime)

    return max(pool, key=rank).resolve()


def read(root: Path) -> ArchivedFilm:
    """Describe one frozen production; never writes, never validates its artifacts."""
    root = Path(root).resolve()
    project = _read_json(root / "project.json") or {}
    brief = _read_json(root / "brief.json") or {}
    title = project.get("title") or brief.get("title") or root.name
    duration = project.get("duration")
    return ArchivedFilm(
        slug=root.name,
        root=root,
        title=str(title),
        duration=float(duration) if isinstance(duration, (int, float)) else None,
        render=newest_render(root),
        stills=selected_stills(root),
    )


def scan(projects_dir: Path) -> list[ArchivedFilm]:
    """Every archived production under ``projects_dir``, sorted by slug."""
    projects_dir = Path(projects_dir)
    if not projects_dir.is_dir():
        return []
    roots = [p for p in sorted(projects_dir.iterdir()) if p.is_dir() and is_archived(p)]
    return [read(root) for root in roots]
