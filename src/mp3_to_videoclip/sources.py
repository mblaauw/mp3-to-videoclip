"""Read-only source browser over a local Suno export.

Liked, real tracks only by default: no stems, no uploads, no voice tests. The scan
never copies, converts or uploads anything; a chosen source is passed to `clip init`
which copies it byte-identically into the production.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

AUDIO = {".mp3", ".wav", ".m4a", ".flac"}
EXCLUDE = re.compile(r"(vocal[-_ ]?test|voice[-_ ]?test|recording|intro|outro|stem)", re.I)


def scan(root: Path, *, liked_only=True, limit=400, query=None, min_seconds=None, max_seconds=None):
    root = Path(root).expanduser()
    if not root.is_dir():
        raise ValueError(f"source directory not found: {root}")
    rows = []
    for path in root.rglob("*.json"):
        if len(rows) >= limit:
            break
        if "VOICES" in path.parts:
            continue
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        if liked_only and data.get("isLiked") is not True:
            continue
        if data.get("isUpload") or data.get("isStem"):
            continue
        meta = data.get("metadata") or {}
        if str(meta.get("type", "")).lower() == "upload":
            continue
        title = data.get("title") or path.stem
        if EXCLUDE.search(title) or EXCLUDE.search(path.stem):
            continue
        duration = meta.get("duration")
        if not isinstance(duration, (int, float)) or duration <= 0:
            continue
        if min_seconds is not None and duration < min_seconds:
            continue
        if max_seconds is not None and duration > max_seconds:
            continue
        if query and query.lower() not in f"{title} {meta.get('tags', '')}".lower():
            continue
        audio = next(
            (
                q
                for q in path.parent.iterdir()
                if q.is_file() and q.suffix.lower() in AUDIO and q.stem == path.stem
            ),
            None,
        )
        if audio is None:
            continue
        rows.append(
            {
                "title": title,
                "seconds": round(float(duration), 2),
                "tags": str(meta.get("tags", ""))[:160],
                "model": meta.get("model") or meta.get("type") or "gen",
                "audio": str(audio),
                "json": str(path),
                "folder": path.parent.name,
            }
        )
    rows.sort(key=lambda row: row["seconds"])
    return {"root": str(root), "count": len(rows), "tracks": rows}
