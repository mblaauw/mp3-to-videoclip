"""Cheap dependency fingerprints: an artifact is *outdated* when the fingerprint
it was made from differs from the current one. This drives badges and
"Regenerate affected" only; it never blocks an action.

Fingerprints are sha256 of canonical JSON (sorted keys, no NaN). They are
computed on demand and are cheap enough to never cache by mtime.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from mp3_to_videoclip.storage import read_json


def fingerprint(value: Any) -> str:
    """Deterministic hash of any JSON-serialisable value."""
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str
        ).encode()
    ).hexdigest()


def file_fingerprint(path: Path) -> str | None:
    """Fingerprint a JSON artifact file, or None when it is missing or unreadable."""
    if not path.is_file():
        return None
    try:
        return fingerprint(read_json(path))
    except (OSError, ValueError):
        return None


def outdated(made_from: str | None, current: str | None) -> bool:
    """True when an artifact was made from a different fingerprint than the current one."""
    return made_from is not None and current is not None and made_from != current
