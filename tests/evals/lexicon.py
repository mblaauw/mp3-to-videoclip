"""How much of a film's writing leans on stock images, counted, and how varied its shots are.

Stems, so "neons" and "neon-lit" both count. A count is a smell, not a verdict: the number goes on
the page next to the reference runs, and ``--strict`` fails only far past them.
"""

from __future__ import annotations

import math
import re
from collections import Counter

#: The fifteen from shared/craft.md, then the rest of the usual suspects.
CLICHES = (
    "rain on a window",
    "rain-streaked",
    "lone figure",
    "rooftop",
    "neon reflection",
    "neon",
    "puddle",
    "hand on glass",
    "hand against glass",
    "record spinning",
    "spinning record",
    "city at night",
    "city lights",
    "skyline",
    "road at dawn",
    "empty road",
    "match struck",
    "striking a match",
    "hair flick",
    "phones up",
    "mirror split",
    "split mirror",
    "hourglass",
    "bird taking off",
    "birds take flight",
    "candle blown",
    "flickering candle",
    "page turned",
    "turning page",
    "broken mirror",
    "shattered glass",
    "falling petals",
    "falling feathers",
    "silhouette",
    "golden hour",
    "lens flare",
    "slow motion",
    "dust motes",
    "dust in the light",
    "smoke curling",
    "cigarette smoke",
    "empty chair",
    "empty swing",
    "old photograph",
    "faded photograph",
    "train window",
    "last train",
    "ticking clock",
    "clock ticking",
    "ocean waves",
    "crashing waves",
    "stormy sky",
    "tear rolling",
    "single tear",
    "footprints in",
)
#: Failing lines. The reference runs sit at zero; a real film may use one or two on purpose.
MAX_PER_THOUSAND = 8.0
MIN_SHOT_ENTROPY = 1.0


def words_of(treatments: dict, board: dict) -> str:
    parts: list[str] = []
    for concept in treatments.get("concepts", []) or []:
        parts += [str(concept.get("title", "")), str(concept.get("logline", ""))]
        parts += [str(beat.get("text", "")) for beat in concept.get("beats", []) or []]
    for shot in board.get("shots", []) or []:
        parts += [str(shot.get(key, "")) for key in ("purpose", "message", "image_prompt")]
    return " ".join(parts)


def cliche_report(text: str) -> dict:
    lowered = text.casefold()
    words = max(1, len(re.findall(r"[\w'-]+", lowered)))
    found = {stem: lowered.count(stem) for stem in CLICHES if stem in lowered}
    total = sum(found.values())
    density = round(total / words * 1000, 2)
    return {
        "words": words,
        "hits": found,
        "per_thousand": density,
        "ok": density <= MAX_PER_THOUSAND,
    }


def _entropy(values: list[str]) -> float:
    if not values:
        return 0.0
    counts = Counter(values)
    return -sum((n / len(values)) * math.log2(n / len(values)) for n in counts.values())


def entropy_report(board: dict) -> dict:
    """Bits of variety across framing, kind and scene, over the whole board."""
    shots = board.get("shots", []) or []
    values = {
        field: round(_entropy([str(shot.get(field) or "none") for shot in shots]), 3)
        for field in ("framing", "kind", "scene_id")
    }
    total = round(sum(values.values()), 3)
    return {**values, "total": total, "ok": total >= MIN_SHOT_ENTROPY}
