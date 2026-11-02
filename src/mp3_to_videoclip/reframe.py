"""How a picture sits on a canvas of another shape. Pure arithmetic over normalised positions.

A still always covers its frame; a reframe only chooses which part stays. The cut's own motion
anchor says where to look, so a vertical version comes from the same cut, not a new edit.
"""

from __future__ import annotations

ASPECTS = ("9:16", "1:1")
#: Past this a still is being enlarged enough to look soft at full screen.
SOFT_SCALE = 1.5


def canvas_for(width: int, height: int, aspect: str) -> tuple[int, int]:
    """The new canvas at the film's own short side, so text stays the size it was."""
    short = min(width, height)
    if aspect == "1:1":
        return short, short
    if aspect == "9:16":
        return short, (round(short * 16 / 9) + 1) // 2 * 2
    raise ValueError("a version comes in 9:16 or 1:1")


def _axis(anchor: float, kept: float) -> float:
    """``object-position`` percent that puts ``anchor`` as near the middle as the edge allows."""
    if kept >= 1:
        return 50.0
    left = min(max(anchor - kept / 2, 0.0), 1.0 - kept)
    return round(left / (1.0 - kept) * 100, 3)


def position(
    anchor: tuple[float, float] | list[float],
    source: tuple[int, int],
    canvas: tuple[int, int],
) -> dict:
    """Where the picture sits, and how much of it stays, for this anchor on this canvas."""
    source_ratio, canvas_ratio = source[0] / source[1], canvas[0] / canvas[1]
    kept_x = min(1.0, canvas_ratio / source_ratio)
    kept_y = min(1.0, source_ratio / canvas_ratio)
    return {
        "x": _axis(float(anchor[0]), kept_x),
        "y": _axis(float(anchor[1]), kept_y),
        "kept": round(kept_x * kept_y, 3),
    }


def is_soft(source: tuple[int, int], canvas: tuple[int, int]) -> bool:
    return max(canvas[0] / source[0], canvas[1] / source[1]) > SOFT_SCALE
