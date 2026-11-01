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

__all__ = [
    "PacingError",
    "density_plan",
    "grid_tiers",
    "plan_boundaries",
    "snap_joins",
    "split_points",
]

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


def snap_joins(
    joins: list[int],
    *,
    total_frames: int,
    min_frames: int,
    reach: int,
    tiers: Iterable[Iterable[int]],
) -> list[int]:
    """Move existing joins onto better frames, keeping their order and every shot's minimum.

    ``joins`` are the interior frames between shots. ``tiers`` go from strongest to
    weakest evidence; a join takes the closest candidate of the first tier within
    ``reach`` that leaves both neighbouring shots at least ``min_frames``, and
    otherwise stays where it is. Pure arithmetic, deterministic, and it never adds
    or removes a join.
    """
    total = _positive_frames(total_frames, "total_frames")
    shortest = _positive_frames(min_frames, "min_frames")
    reach = _integer(reach, "reach")
    marked = [sorted(_marked_frames(tier, "tier", total)) for tier in tiers]
    result = [_integer(join, "join") for join in joins]
    for index, join in enumerate(result):
        low = (result[index - 1] if index else 0) + shortest
        high = (result[index + 1] if index + 1 < len(result) else total) - shortest
        for frames in marked:
            options = [
                frame for frame in frames if abs(frame - join) <= reach and low <= frame <= high
            ]
            if options:
                result[index] = min(options, key=lambda frame: (abs(frame - join), frame))
                break
    return result


#: Cuts per bar for each energy word, and per 10 s when no bar was measured. A full
#: section tops out at one a bar, because that is what cutting on bar lines can reach.
_CUTS_PER_BAR = {"quiet": 0.25, "middle": 0.5, "full": 1.0}
_CUTS_PER_10S = {"quiet": 1.5, "middle": 3.0, "full": 5.0}
#: The shortest shot a density may ask for.
_MIN_CUT_SECONDS = 1.5


def density_plan(
    energy_words: Iterable[str], beats_per_bar: int | None, bpm: float | None
) -> list[float]:
    """A target in cuts per 10 s for each section, from its energy word and the bar."""
    targets = []
    bar_seconds = beats_per_bar * 60 / bpm if beats_per_bar and bpm else None
    for word in energy_words:
        if bar_seconds:
            target = _CUTS_PER_BAR[word] / bar_seconds * 10
        else:
            target = _CUTS_PER_10S[word]
        targets.append(round(min(target, 10 / _MIN_CUT_SECONDS), 2))
    return targets


def grid_tiers(
    downbeats: Iterable[int], beats: Iterable[int], lead: int = 1
) -> tuple[list[int], list[int]]:
    """Downbeats and beats led by a frame, so the picture is there when the hit lands."""
    return (
        sorted({max(0, frame - lead) for frame in downbeats}),
        sorted({max(0, frame - lead) for frame in beats}),
    )


def split_points(
    start: int, end: int, bars: Iterable[int], every: int, min_frames: int
) -> list[int]:
    """Bar lines to cut on inside one shot, at least ``every`` frames apart.

    Each part keeps at least ``min_frames``, including the last. Pure, and it adds a
    framing change, never a new picture.
    """
    points: list[int] = []
    last = start
    for frame in sorted(set(bars)):
        if frame - last >= max(every, min_frames) and end - frame >= min_frames:
            points.append(frame)
            last = frame
    return points


def line_starts(lines: Iterable[tuple[int, int]], *, total_frames: int, lead: int = 0) -> list[int]:
    """Where each group of spoken lines takes the picture, in order, from frame 0.

    ``lines`` holds each group's first spoken frame and how far ahead of it the picture
    comes. Strictly increasing and inside the film, so the shots cover every frame.
    """
    total = _positive_frames(total_frames, "total_frames")
    starts: list[int] = []
    for index, (frame, ahead) in enumerate(lines):
        start = (
            0 if index == 0 else max(_integer(frame, "frame") - _integer(ahead, "ahead") - lead, 0)
        )
        if starts and start <= starts[-1]:
            start = starts[-1] + 1
        if start >= total:
            raise ValueError("spoken lines run past the end of the film")
        starts.append(start)
    return starts
