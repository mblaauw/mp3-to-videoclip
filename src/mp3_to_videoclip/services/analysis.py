"""Local music analysis: one entry point for the app and the director."""

from __future__ import annotations

import logging
from pathlib import Path

from mp3_to_videoclip import operations
from mp3_to_videoclip.storage import read_json, write_json

logger = logging.getLogger(__name__)


def analyze_project(root: Path, *, force: bool = False) -> dict:
    """Run the local measurement pass and persist work/music.json."""
    from mp3_to_videoclip import production as P
    from mp3_to_videoclip.analysis import analyze as _analyze

    path = root / "work" / "music.json"
    if path.is_file() and not force:
        return {"analysis": str(path), "reused": True, **read_json(path)}
    project = P.load_project(root)
    audio = P.render_audio(root, project)
    operations.phase("measuring-the-song")
    data = _analyze(audio, project.duration)
    write_json(path, data)
    # The quick result is on Track from here; the song map upgrades when this lands.
    operations.phase("finding-bars-and-sections")
    try:
        deep_analyze_project(root)
    except Exception:  # A failed refinement must not lose the measurement it refines.
        logger.exception("the deep pass failed for %s", root.name)
    return {"analysis": str(path), "reused": False, **data}


def deep_analyze_project(root: Path) -> dict:
    from mp3_to_videoclip import production as P
    from mp3_to_videoclip.deep_analysis import deep_analyze
    from mp3_to_videoclip.storage import write_json

    project = P.load_project(root)
    data = deep_analyze(P.render_audio(root, project), project.duration)
    write_json(root / "work" / "music-deep.json", data)
    return data
