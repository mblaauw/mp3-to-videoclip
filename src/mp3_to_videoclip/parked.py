"""Films the owner has set aside: a list beside the settings, never inside a production.

Parking only changes where the library shows a film, so it writes nothing in the
film's folder and can always be undone.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import config
from .storage import write_json


def _path() -> Path:
    return config.settings_path().parent / "parked.json"


def read() -> set[str]:
    """The parked slugs; a missing or unreadable list means nothing is parked."""
    try:
        value = json.loads(_path().read_text())
    except (OSError, ValueError):
        return set()
    if not isinstance(value, list):
        return set()
    return {slug for slug in value if isinstance(slug, str)}


def set_parked(slug: str, parked: bool) -> None:
    slugs = read()
    if parked:
        slugs.add(slug)
    else:
        slugs.discard(slug)
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, sorted(slugs))
