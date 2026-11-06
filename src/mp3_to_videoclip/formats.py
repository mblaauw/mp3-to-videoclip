"""Production formats: the New film form's presets, one row per kind of job.

A format fills the form and nothing else: the film keeps the answers, never the format's
id, so a format can be renamed or retuned without moving a film. Each row only uses
what the engine already offers, and ``check`` proves it against the kind, structure,
titles, publish and look tables.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

#: The whole song, as a length.
WHOLE_TRACK = 0


@dataclass(frozen=True)
class Format:
    id: str
    kind: str
    label: str
    blurb: str
    length: int
    aspect: str
    titles: str
    destinations: tuple[str, ...]
    look: str
    #: A story film's template id, or one of another kind's structures; None lets the Writer propose.
    structure: str | None = None

    def public(self) -> dict:
        return asdict(self) | {"destinations": list(self.destinations)}


FORMATS: tuple[Format, ...] = (
    Format(
        "music-video",
        "music_video",
        "Music video",
        "The whole song, widescreen, opened and closed by your brand kit.",
        WHOLE_TRACK,
        "16:9",
        "joint-v1",
        ("youtube",),
        "photographic-painted-v2",
    ),
    Format(
        "vertical-video",
        "music_video",
        "Vertical video",
        "The whole song for phones: a short title, then the picture fills the screen.",
        WHOLE_TRACK,
        "9:16",
        "title-v1",
        ("shorts", "reels"),
        "photographic-painted-v2",
    ),
    Format(
        "lyric-video",
        "music_video",
        "Lyric video",
        "The words carry it: lyric cards on the beats that matter.",
        WHOLE_TRACK,
        "16:9",
        "title-v1",
        ("youtube",),
        "brand-graphic-v1",
        "Lyric-led",
    ),
    Format(
        "release-teaser",
        "promo",
        "Release teaser",
        "Thirty seconds of the song for phones, ending on the release.",
        30,
        "9:16",
        "title-v1",
        ("shorts", "reels"),
        "clean-photographic-v1",
        "Release teaser",
    ),
    Format(
        "event-teaser",
        "promo",
        "Event teaser",
        "Where, when and why to come, on a short excerpt.",
        30,
        "9:16",
        "title-v1",
        ("reels", "shorts"),
        "clean-photographic-v1",
        "Event teaser",
    ),
    Format(
        "artist-promo",
        "promo",
        "Artist promo",
        "A minute that shows who this is and why it matters.",
        60,
        "16:9",
        "title-v1",
        ("youtube",),
        "clean-photographic-v1",
        "Mood film",
    ),
    Format(
        "bumper",
        "advert",
        "Six-second bumper",
        "One image, one line, the brand. Made to be unskippable.",
        6,
        "16:9",
        "none",
        ("youtube",),
        "product-studio-v1",
        "Hero product",
    ),
    Format(
        "social-ad",
        "advert",
        "Social ad",
        "Fifteen seconds for phones: the problem, the answer, the action.",
        15,
        "9:16",
        "none",
        ("reels", "shorts"),
        "clean-photographic-v1",
        "Problem → solution",
    ),
    Format(
        "spot",
        "advert",
        "Thirty-second spot",
        "A small story with a twist that lands on the call to action.",
        30,
        "16:9",
        "none",
        ("youtube",),
        "clean-photographic-v1",
        "Mini-story with a twist",
    ),
    Format(
        "story-short",
        "narrative",
        "Story short",
        "Two minutes, five beats, a narrator leading.",
        120,
        "16:9",
        "title-v1",
        ("youtube",),
        "painted-documentary-v1",
        "five-beat-2m",
    ),
    Format(
        "place-across-time",
        "narrative",
        "One place across time",
        "The camera stays while the years change the place.",
        120,
        "16:9",
        "title-v1",
        ("youtube",),
        "painted-documentary-v1",
        "place-across-time",
    ),
    Format(
        "video-essay",
        "narrative",
        "Video essay",
        "Three minutes: a question, the evidence, a turn, an answer.",
        180,
        "16:9",
        "title-v1",
        ("youtube",),
        "archival-v1",
        "essay",
    ),
    Format(
        "vertical-story",
        "narrative",
        "Vertical story",
        "A one-minute fable for phones.",
        60,
        "9:16",
        "title-v1",
        ("shorts", "reels"),
        "illustrated-v1",
        "fable",
    ),
)


def public_formats() -> list[dict]:
    return [item.public() for item in FORMATS]


def structure_ids(kind: str) -> tuple[str, ...]:
    """What a film of this kind may name as its structure."""
    from . import kinds, structures

    if kind == "narrative":
        return tuple(structures.STRUCTURES)
    return kinds.get(kind).structures


def check() -> list[str]:
    """Every way a format could promise what the engine can't make."""
    from . import kinds, publish, signature, styles

    problems = []
    ids = [item.id for item in FORMATS]
    if len(set(ids)) != len(ids):
        problems.append("format ids repeat")
    looks = {preset.id for preset in styles.presets()}
    for item in FORMATS:
        profile = kinds.get(item.kind)
        if item.length == WHOLE_TRACK and not profile.allows_full_track:
            problems.append(f"{item.id}: a {profile.label.lower()} can't use the whole track")
        if item.length != WHOLE_TRACK and item.length not in profile.lengths:
            problems.append(f"{item.id}: {item.length} s isn't a {profile.label.lower()} length")
        package = signature.PACKAGES.get(item.titles)
        if package is None or item.aspect not in package.aspects:
            problems.append(f"{item.id}: titles {item.titles} can't be {item.aspect}")
        for destination in item.destinations:
            if destination not in publish.PRESETS:
                problems.append(f"{item.id}: no destination {destination}")
            elif publish.PRESETS[destination]["aspect"] not in (item.aspect, "1:1"):
                problems.append(f"{item.id}: {destination} wants another shape")
        if item.look not in looks or item.look not in profile.style_presets:
            problems.append(f"{item.id}: {item.look} isn't a {profile.label.lower()} look")
        if item.structure is not None and item.structure not in structure_ids(item.kind):
            problems.append(
                f"{item.id}: {item.structure} isn't a {profile.label.lower()} structure"
            )
    return problems
