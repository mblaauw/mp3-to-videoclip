"""Human thumbs on Writer/Editor artifacts, bound to prompt and artifact bytes.

Ratings are an evaluation signal, never an approval. The store is append-only so
a later rating cannot rewrite what the owner said about an earlier revision.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from . import promptlog
from .storage import file_hash

RATINGS = "work/ratings.jsonl"
ARTIFACTS = {
    "brief": "brief.json",
    "treatments": "work/treatments.json",
    "storyboard": "work/storyboard.json",
    "edit": "work/edit.json",
}
LABELS = {
    "brief": "Brief",
    "treatments": "Concepts",
    "storyboard": "Storyboard",
    "edit": "Edit",
}
RATINGS_CHOICES = ("up", "down")


def now() -> str:
    return datetime.now(UTC).isoformat()


def artifact_path(root: Path, artifact: str) -> Path:
    if artifact not in ARTIFACTS:
        raise ValueError(f"unknown artifact {artifact!r}; choose from {', '.join(ARTIFACTS)}")
    return root / ARTIFACTS[artifact]


def _prompt_meta(root: Path, artifact: str) -> dict | None:
    value = promptlog.latest(root, artifact)
    if value is None:
        value = promptlog.current(root)
    return value


def _entry(root: Path, artifact: str, rating: str, note: str) -> dict:
    if artifact not in ARTIFACTS:
        raise ValueError(f"unknown artifact {artifact!r}; choose from {', '.join(ARTIFACTS)}")
    if rating not in RATINGS_CHOICES:
        raise ValueError("rating must be up or down")
    note = note.strip()
    if len(note) > 1000:
        raise ValueError("rating note must be at most 1000 characters")
    path = artifact_path(root, artifact)
    if not path.is_file():
        raise ValueError(f"{LABELS[artifact]} does not exist yet")
    prompt = _prompt_meta(root, artifact) or {}
    return {
        "artifact": artifact,
        "label": LABELS[artifact],
        "rating": rating,
        "note": note,
        "artifact_hash": file_hash(path),
        "prompt_hash": prompt.get("hash"),
        "prompt_files": prompt.get("files") or [],
        "prompt_role": prompt.get("role"),
        "prompt_task": prompt.get("task"),
        "prompt_words": prompt.get("words"),
        "at": now(),
    }


def add(root: Path, artifact: str, rating: str, note: str = "") -> dict:
    """Append one rating; never replace an earlier one."""
    entry = _entry(root, artifact, rating, note)
    path = root / RATINGS
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def load(root: Path, artifact: str | None = None) -> list[dict]:
    path = root / RATINGS
    if not path.is_file():
        return []
    values: list[dict] = []
    for line in path.read_text().splitlines():
        try:
            entry = json.loads(line)
        except (TypeError, ValueError):
            continue
        if not isinstance(entry, dict) or entry.get("artifact") not in ARTIFACTS:
            continue
        if artifact is not None and entry.get("artifact") != artifact:
            continue
        values.append(entry)
    return values


def summary(root: Path, artifact: str) -> dict:
    if artifact not in ARTIFACTS:
        raise ValueError(f"unknown artifact {artifact!r}; choose from {', '.join(ARTIFACTS)}")
    path = artifact_path(root, artifact)
    entries = load(root, artifact)
    latest = entries[-1] if entries else None
    artifact_hash = file_hash(path) if path.is_file() else None
    prompt = _prompt_meta(root, artifact) or {}
    return {
        "artifact": artifact,
        "label": LABELS[artifact],
        "available": path.is_file(),
        "artifact_hash": artifact_hash,
        "prompt": {
            "hash": prompt.get("hash"),
            "files": prompt.get("files") or [],
            "role": prompt.get("role"),
            "task": prompt.get("task"),
            "words": prompt.get("words"),
        },
        "latest": latest,
        "stale": bool(latest and artifact_hash and latest.get("artifact_hash") != artifact_hash),
        "history": entries,
    }


def all_summary(root: Path) -> list[dict]:
    return [summary(root, artifact) for artifact in ARTIFACTS]


def prompt_versions(root: Path) -> dict[str, dict]:
    """Ratings grouped by prompt hash for the eval report."""
    grouped: dict[str, dict] = {}
    for entry in load(root):
        key = entry.get("prompt_hash") or "unbound"
        bucket = grouped.setdefault(
            key,
            {"prompt_hash": key, "files": entry.get("prompt_files") or [], "ratings": []},
        )
        bucket["ratings"].append(entry)
    return grouped
