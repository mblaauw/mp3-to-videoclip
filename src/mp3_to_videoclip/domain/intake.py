"""Create a schema 3 production from an uploaded MP3.

The engine owns the intake contract (probe, copy, defaults, brand, empty event
map); this module adds the app's slug rule, the schema 3 migration and the first
budget entry. No stage is approved on the user's behalf.
"""

from __future__ import annotations

import json
import re
import shutil
import unicodedata
from pathlib import Path

from . import budget as app_budget
from .migrate import migrate

MAX_SOURCE_BYTES = 25_000_000
MAX_TITLE_LENGTH = 120


def _slug_base(title: str) -> str:
    normalized = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", normalized.casefold()).strip("-")[:64].rstrip("-")
    if not base:
        raise ValueError("the title needs at least one letter or digit")
    return base


def slug_for(title: str, projects_dir: Path) -> str:
    """The next free slug without creating anything (read-only helper)."""
    base = _slug_base(title)
    candidate = base
    counter = 2
    while (projects_dir / candidate).exists():
        suffix = f"-{counter}"
        candidate = base[: 64 - len(suffix)].rstrip("-") + suffix
        counter += 1
        if counter > 100:
            raise ValueError("too many productions share this title")
    return candidate


def reserve_slug(title: str, projects_dir: Path) -> tuple[str, Path]:
    """Atomically reserve one production folder and return its slug and root.

    ``mkdir`` is the reservation: two concurrent uploads with the same title can
    never both own one folder, so a failed intake cannot delete the other's work.
    """
    base = _slug_base(title)
    for counter in range(1, 101):
        suffix = "" if counter == 1 else f"-{counter}"
        candidate = base[: 64 - len(suffix)].rstrip("-") + suffix
        root = projects_dir / candidate
        try:
            root.mkdir()
        except FileExistsError:
            continue
        return candidate, root
    raise ValueError("too many productions share this title")


def create_from_upload(
    projects_dir: Path,
    source: Path,
    *,
    title: str,
    aspect: str = "16:9",
    music_mode: str = "vocal",
    budget: str = "5.00",
    kind: str = "music_video",
    intent: dict | None = None,
    style_preset: str | None = None,
    length_seconds: float | None = None,
    window_start: float = 0.0,
    fade_in: float = 0.0,
    fade_out: float = 0.0,
) -> dict:
    """Copy, probe and migrate one MP3 into a new production folder."""
    title = title.strip()
    if not title:
        raise ValueError("give the film a title")
    if len(title) > MAX_TITLE_LENGTH:
        raise ValueError(f"keep the title under {MAX_TITLE_LENGTH} characters")
    if aspect not in ("16:9", "9:16"):
        raise ValueError("aspect must be 16:9 or 9:16")
    if music_mode not in ("vocal", "instrumental"):
        raise ValueError("music mode must be vocal or instrumental")
    from mp3_to_videoclip import kinds
    from mp3_to_videoclip.models import Intent

    profile = kinds.get(kind)
    try:
        intent_value = Intent.model_validate(intent or {})
    except ValueError as exc:
        raise ValueError(f"intake intent is invalid: {exc}") from exc
    if profile.id == "advert":
        missing = [
            label
            for label, field in (
                ("objective", intent_value.objective),
                ("message", intent_value.message),
                ("call to action", intent_value.cta.text if intent_value.cta else ""),
            )
            if not field.strip()
        ]
        if missing:
            raise ValueError("an advert needs " + ", ".join(missing))
        if length_seconds is None and intent_value.length_seconds is None:
            raise ValueError("an advert needs a target length")
    if not source.is_file():
        raise ValueError("the upload is empty")
    if source.suffix.lower() != ".mp3":
        raise ValueError("the source must be an MP3")
    if source.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("the MP3 is larger than the 25 MB local intake limit")
    cap = app_budget.money(budget)
    if cap <= 0:
        raise ValueError("the starting budget must be a positive USD amount")

    projects_dir.mkdir(parents=True, exist_ok=True)
    slug, root = reserve_slug(title, projects_dir)
    from mp3_to_videoclip import production as P

    # The reserved empty folder is ours alone. Clean up only this root on failure;
    # a concurrent upload owns a different slug.
    try:
        try:
            P.init_project(
                root,
                source,
                slug,
                aspect=aspect,
                fps=24,
                music_mode=music_mode,
                title=title,
                kind=profile.id,
                intent=intent_value.model_dump(),
                style_preset=style_preset,
                length_seconds=length_seconds or intent_value.length_seconds,
                window_start=window_start,
                fade_in=fade_in,
                fade_out=fade_out,
            )
        except (RuntimeError, OSError, json.JSONDecodeError) as exc:
            raise ValueError("the file is not a readable MP3") from exc
        migrate(root)
        app_budget.add_budget(root, cap, "initial production budget")
    except BaseException:
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        raise
    return {"slug": slug, "root": root, "title": title}
