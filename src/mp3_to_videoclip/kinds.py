"""Production kinds: the code table the app and the Writer both read.

The prose lives in ``director/prompts/kinds/<kind>.md``; this module is the
authoritative table for lengths, defaults, signature package and style choices.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from .models import Kind

PROMPTS = Path(__file__).resolve().parent / "director" / "prompts" / "kinds"


@dataclass(frozen=True)
class KindProfile:
    id: Kind
    label: str
    purpose: str
    lengths: tuple[int, ...]
    default_length: int | None
    allows_full_track: bool
    structures: tuple[str, ...]
    shot_mix: str
    text_density: str
    pacing: str
    opening_closing: str
    signature_required: bool
    style_presets: tuple[str, ...]
    default_style: str

    def public(self) -> dict:
        return asdict(self) | {"lengths": list(self.lengths), "structures": list(self.structures)}


KINDS: dict[Kind, KindProfile] = {
    "music_video": KindProfile(
        id="music_video",
        label="Music video",
        purpose="A visual performance of the song, led by its sections and mood.",
        lengths=(),
        default_length=None,
        allows_full_track=True,
        structures=(
            "Narrative",
            "Performance",
            "Concept / symbolic",
            "Process",
            "Lyric-led",
            "Abstract",
        ),
        shot_mix="Mostly generated scenes; a few title or lyric cards",
        text_density="Rare: title and selected lyric hits only",
        pacing="Follows the song's sections; holds are earned by the music",
        opening_closing="25 s opening + 40 s credits (editable settings default)",
        signature_required=True,
        style_presets=(
            "photographic-painted-v2",
            "clean-photographic-v1",
            "product-studio-v1",
            "brand-graphic-v1",
        ),
        default_style="photographic-painted-v2",
    ),
    "promo": KindProfile(
        id="promo",
        label="Promo",
        purpose="Show what something is and why it matters: artist, release, event, place or line.",
        lengths=(30, 60, 90, 120),
        default_length=60,
        allows_full_track=True,
        structures=(
            "Mood film",
            "Story-led (situation → change)",
            "Feature tour",
            "Event teaser",
            "Release teaser",
        ),
        shot_mix="Scenes, product/place stills and message cards",
        text_density="Supers on key beats; short and concrete",
        pacing="Medium; builds to the reveal without inventing a second idea",
        opening_closing="Short title and end card; credits optional",
        signature_required=False,
        style_presets=("clean-photographic-v1", "product-studio-v1", "brand-graphic-v1"),
        default_style="clean-photographic-v1",
    ),
    "advert": KindProfile(
        id="advert",
        label="Advert",
        purpose="Make one audience do one thing.",
        lengths=(6, 15, 20, 30, 60),
        default_length=30,
        allows_full_track=False,
        structures=(
            "Problem → solution",
            "Demonstration",
            "Before / after",
            "Hero product",
            "Three reasons",
            "Mini-story with a twist",
            "Testimonial-style quote card",
        ),
        shot_mix="Scenes, product hero, supers, logo and CTA end card",
        text_density="Supers carry the argument; at most about seven words each",
        pacing="Brand visible in the first 5 s; tight; end card holds at least 3 s",
        opening_closing="Logo lockup and CTA end card; no credits roll",
        signature_required=False,
        style_presets=("clean-photographic-v1", "product-studio-v1", "brand-graphic-v1"),
        default_style="clean-photographic-v1",
    ),
}


def get(kind: str | None) -> KindProfile:
    """Return the profile for ``kind``; a missing kind means legacy music video."""
    if kind is None:
        return KINDS["music_video"]
    try:
        return KINDS[kind]  # type: ignore[index]
    except KeyError as exc:
        raise ValueError(f"unknown production kind {kind!r}") from exc


def public_kinds() -> list[dict]:
    return [profile.public() for profile in KINDS.values()]


def prompt(kind: str | None) -> str:
    """The kind's prose block, or an empty string when the file is absent."""
    profile = get(kind)
    path = PROMPTS / f"{profile.id}.md"
    return path.read_text() if path.is_file() else ""
