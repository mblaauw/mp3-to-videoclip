"""Pure, deterministic adaptive shot-timing planner for the 4-12 second mode.

This module implements the timing half of the new-film skeleton defaults
(item 5): a small adaptive mode that targets roughly eight seconds per shot, may
shorten or lengthen a shot to land on a *reviewed* musical event, and always
covers the exact source frame count. It is pure arithmetic over caller-supplied
integer frames: nothing here reads a project, probes a file, calls ffmpeg, a
provider or a paid tool, and nothing is inferred about meter, tempo, BPM, genre,
language or emotion. Every evidence class is a plain list of integer frame
positions handed in by the caller, whose provenance is the caller's problem:

``event_frames``
    Reviewed (``manual``) musical-event boundaries: the intended structure.
``change_frames``
    Locally measured opportunities (for example onset/energy or section
    changes). Measurement, so it is offered, not imperative.
``beat_frames``
    Local beat estimates. The weakest evidence, and deliberately not a licence to
    cut once per beat.

Selection rule (deterministic, no hashing, no randomness, no floating-point
comparison of candidate order):

1. The next cut must land inside a window that keeps every shot within
   ``min_seconds..max_seconds`` (integer frames from ``ceil(min * fps)`` and
   ``floor(max * fps)``) *and* leave a remainder that can still be covered
   exactly, so no tiny accidental final tail survives:
   ``ceil(remaining / max_frames) <= floor(remaining / min_frames)``, or a
   remainder of zero.
2. Inside that window the candidate with the lowest tier wins: event, then
   change, then beat, then an unmarked frame. Reviewed structure therefore
   outranks a locally measured change, which outranks a near beat; an
   unmarked frame is always available so the window is never empty. A tier only
   decides relative to the *same* window, so an event cannot stretch a shot
   outside the duration bounds and is never forced when the remainder it would
   leave is not coverable.
3. Ties inside a tier break on the smallest distance from the target
   (``target_seconds`` clamped into the duration bounds), then on the earliest
   frame. Input order is irrelevant and duplicate frames collapse, so repeated
   identical inputs produce identical outputs.

A track shorter than one minimum shot is returned as the single explicit shot
``[0, total_frames]``, even though that shot is shorter than ``min_seconds``;
the caller (the CLI) is expected to surface that as a note rather than as an
error. There is no default anywhere else in the package: this module is inert
until a caller asks for it.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from fractions import Fraction
from typing import Any

__all__ = ["PacingError", "plan_boundaries"]

# Candidate tiers; the lowest wins inside a feasible window.
_EVENT_TIER = 0
_CHANGE_TIER = 1
_BEAT_TIER = 2
_UNMARKED_TIER = 3


class PacingError(ValueError):
    """Invalid track size, frame rate, duration bound or candidate frame."""


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PacingError(f"{label} must be an integer, got {value!r}")
    return value


def _positive_frames(value: Any, label: str) -> int:
    frames = _integer(value, label)
    if frames <= 0:
        raise PacingError(f"{label} must be positive, got {value!r}")
    return frames


def _seconds(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PacingError(f"{label} must be a real number, got {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise PacingError(f"{label} must be finite, got {value!r}")
    return number


def _scaled(seconds: float, fps: int) -> Fraction:
    """``seconds * fps`` as an exact rational, so bounds never round by accident."""
    return Fraction(seconds) * fps


def _marked_frames(frames: Iterable[int], label: str, total_frames: int) -> set[int]:
    """Validated, deduplicated interior candidate frames.

    Candidate frames must be integers (bools and floats are refused, including
    ``nan``/``inf``). A negative frame is refused outright: it is outside the
    track's own frame domain. ``0`` and anything at or past the final frame are
    dropped instead, because the returned boundary list already carries both
    endpoints exactly once (reviewed event *ends* legitimately sit on the final
    frame), so such candidates can never add a spurious boundary.
    """
    try:
        candidates = list(frames)
    except TypeError as error:
        raise PacingError(f"{label} must be an iterable of integer frames") from error
    marked: set[int] = set()
    for candidate in candidates:
        frame = _integer(candidate, f"{label} candidate")
        if frame < 0:
            raise PacingError(f"{label} candidate {frame} is before the start of the track")
        if 0 < frame < total_frames:
            marked.add(frame)
    return marked


def _tail_ok(remaining: int, min_frames: int, max_frames: int) -> bool:
    """True when ``remaining`` frames are exactly coverable without a tiny tail."""
    if remaining == 0:
        return True
    if remaining < min_frames:
        return False
    return math.ceil(remaining / max_frames) <= remaining // min_frames


def plan_boundaries(
    total_frames: int,
    fps: int,
    *,
    target_seconds: float = 8,
    min_seconds: float = 4,
    max_seconds: float = 12,
    event_frames: Iterable[int] = (),
    change_frames: Iterable[int] = (),
    beat_frames: Iterable[int] = (),
) -> list[int]:
    """Plan exact shot boundaries for one track; see the module docstring.

    ``total_frames`` and ``fps`` are positive integers (production uses 24 or 30
    fps; any positive rate is accepted). ``target_seconds``, ``min_seconds`` and
    ``max_seconds`` are finite positive reals with ``min_seconds <=
    max_seconds``; the bounds are the hard contract and a target outside them is
    clamped into them. Shot durations are ``ceil(min_seconds * fps)`` to
    ``floor(max_seconds * fps)`` frames, except for one explicit short shot when
    the whole track is shorter than the minimum.

    The result starts at ``0``, ends at ``total_frames``, is strictly increasing
    and therefore covers every source frame exactly once. It is a *plan*: the
    caller owns shot IDs, content and approval.
    """
    total = _positive_frames(total_frames, "total_frames")
    fps = _positive_frames(fps, "fps")
    target = _seconds(target_seconds, "target_seconds")
    shortest = _seconds(min_seconds, "min_seconds")
    longest = _seconds(max_seconds, "max_seconds")
    if target <= 0:
        raise PacingError(f"target_seconds must be positive, got {target_seconds!r}")
    if shortest <= 0:
        raise PacingError(f"min_seconds must be positive, got {min_seconds!r}")
    if longest < shortest:
        raise PacingError(
            f"max_seconds {max_seconds!r} is shorter than min_seconds {min_seconds!r}"
        )
    min_frames = math.ceil(_scaled(shortest, fps))
    max_frames = math.floor(_scaled(longest, fps))
    if max_frames < min_frames:
        raise PacingError(
            f"{fps} fps cannot express a {min_seconds!r}..{max_seconds!r}s shot range "
            f"({min_frames}..{max_frames} frames)"
        )
    # Nearest frame to the target, tie rounded up, then clamped into the bounds.
    target_frames = math.floor(_scaled(target, fps) + Fraction(1, 2))
    target_frames = min(max(target_frames, min_frames), max_frames)

    marked: dict[int, int] = {}
    for frames, tier, label in (
        (event_frames, _EVENT_TIER, "event_frames"),
        (change_frames, _CHANGE_TIER, "change_frames"),
        (beat_frames, _BEAT_TIER, "beat_frames"),
    ):
        for frame in _marked_frames(frames, label, total):
            if tier < marked.get(frame, _UNMARKED_TIER):
                marked[frame] = tier

    # A track shorter than one minimum shot is one explicit short shot. There is
    # nothing to adapt; the caller reports it instead of pretending it fits.
    if total < min_frames:
        return [0, total]
    if not _tail_ok(total, min_frames, max_frames):
        raise PacingError(
            f"cannot cover {total} frames exactly with shots of {min_frames}..{max_frames} frames; "
            "widen --min-seconds/--max-seconds or explicitly choose different timing"
        )

    boundaries = [0]
    cursor = 0
    while total - cursor > max_frames:
        ideal = cursor + target_frames
        window = range(cursor + min_frames, min(cursor + max_frames, total) + 1)
        feasible = [frame for frame in window if _tail_ok(total - frame, min_frames, max_frames)]
        if not feasible:  # Defensive: every admitted remainder must remain coverable.
            raise PacingError(
                f"no cut after frame {cursor} can cover the remaining "
                f"{total - cursor} frames at {min_frames}..{max_frames} frames per shot"
            )
        cursor = min(
            feasible,
            key=lambda frame: (marked.get(frame, _UNMARKED_TIER), abs(frame - ideal), frame),
        )
        boundaries.append(cursor)
    boundaries.append(total)
    return boundaries
