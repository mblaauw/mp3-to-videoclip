"""Read-only, integer-frame timeline resolution against the storyboard contract.

The storyboard (``work/storyboard.json``) owns the production's exact shot
timeline: shots are contiguous integer frames, a shot's ``start_frame`` is
inclusive and ``start_frame + duration_frames`` is exclusive. Everything here is
a pure function over an already-validated
:class:`~mp3_to_videoclip.models.Storyboard`; nothing reads or writes project
files, calls ffmpeg or a provider, and no board is ever mutated.

Captions may be declared either the legacy way (absolute ``start``/``end``
seconds, returned verbatim) or bound to a shot (``shot_id`` plus an
``offset_frames``/``duration_frames`` window). The shot-bound form is resolved to
frame-accurate seconds so an overlay can never land in the wrong shot by
rounding, and it is refused when it would cross a shot or timeline boundary:
nothing is stretched or clamped to make a caption fit.

Note on seconds: ``floor(seconds * fps)`` is the frame rule, but a value written
back as ``frame / fps`` can re-multiply to just below ``frame`` in binary
floating point. :func:`frame_number` therefore snaps a scaled value to the
nearest integer when it is within representation error, which keeps a
frame-exact time inside its own frame instead of the previous one.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from .models import Shot, Storyboard

__all__ = [
    "SHOT_BOUND_KEYS",
    "TimelineError",
    "frame_at_seconds",
    "frame_number",
    "is_shot_bound",
    "label_at_frame",
    "label_at_seconds",
    "resolve_caption",
    "resolve_captions",
    "shot_at_frame",
    "shot_at_seconds",
]

#: A caption carrying any of these keys is a shot-bound caption.
SHOT_BOUND_KEYS = ("shot_id", "offset_frames", "duration_frames")

#: Representation error allowance, in ULPs of the scaled frame value. A value
#: rewritten as ``frame / fps`` may re-multiply a couple of ULPs away from the
#: exact frame, and only that is absorbed; a genuinely fractional time is floored.
_ULP_TOLERANCE = 4


class TimelineError(ValueError):
    """Invalid frame, second or caption binding; nothing is resolved."""


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TimelineError(f"{label} must be a real number, got {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise TimelineError(f"{label} must be finite, got {value!r}")
    return number


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TimelineError(f"{label} must be an integer, got {value!r}")
    return value


def _board(board: Any) -> Storyboard:
    if not isinstance(board, Storyboard):
        raise TimelineError("board must be a Storyboard")
    return board


def frame_number(seconds: float, fps: int) -> int:
    """Frame index at ``seconds``: ``floor(seconds * fps)`` with float-edge snapping.

    No timeline bounds are applied; use :func:`frame_at_seconds` for that.
    """
    fps = _integer(fps, "fps")
    if fps <= 0:
        raise TimelineError(f"fps must be positive, got {fps!r}")
    number = _number(seconds, "seconds")
    if number < 0:
        raise TimelineError(f"seconds must not be negative, got {seconds!r}")
    scaled = number * fps
    nearest = round(scaled)
    if abs(scaled - nearest) <= _ULP_TOLERANCE * math.ulp(scaled):
        scaled = float(nearest)
    return math.floor(scaled)


def shot_at_frame(board: Storyboard, frame: int) -> Shot:
    """The shot whose half-open interval ``[start, start + duration)`` holds ``frame``.

    ``frame`` must be an integer inside the board (``bool`` is not an integer
    here) and the boundary frame belongs to the *following* shot.
    """
    board = _board(board)
    frame = _integer(frame, "frame")
    if frame < 0 or frame >= board.total_frames:
        raise TimelineError(
            f"frame {frame} is outside the storyboard timeline "
            f"0..{board.total_frames - 1} ({board.fps} fps)"
        )
    for shot in board.shots:
        if shot.start_frame <= frame < shot.start_frame + shot.duration_frames:
            return shot
    raise TimelineError(f"frame {frame} matches no shot; the storyboard timeline is not contiguous")


def frame_at_seconds(board: Storyboard, seconds: float) -> int:
    """Exact integer frame for ``seconds``, rejected outside the board timeline."""
    board = _board(board)
    frame = frame_number(seconds, board.fps)
    if frame >= board.total_frames:
        last = (board.total_frames - 1) / board.fps
        raise TimelineError(
            f"{_number(seconds, 'seconds')!r}s is past the last frame of the storyboard "
            f"(the timeline ends at frame {board.total_frames - 1}, {last!r}s)"
        )
    return frame


def shot_at_seconds(board: Storyboard, seconds: float) -> Shot:
    """The shot covering ``seconds`` (``floor(seconds * fps)``, half-open bounds)."""
    return shot_at_frame(board, frame_at_seconds(board, seconds))


def label_at_frame(board: Storyboard, frame: int) -> dict:
    """Sample-frame label: exact shot, alias owner and the half-open interval.

    The alias owner is ``asset_shot_id or id``: the shot whose still this frame
    actually shows when a shot reuses another shot's image.
    """
    board = _board(board)
    shot = shot_at_frame(board, frame)
    frames = shot.start_frame + shot.duration_frames
    return {
        "frame": frame,
        "seconds": frame / board.fps,
        "shot_id": shot.id,
        "owner_shot_id": shot.asset_shot_id or shot.id,
        "start_frame": shot.start_frame,
        "end_frame": frames,
        "start_seconds": shot.start_frame / board.fps,
        "end_seconds": frames / board.fps,
    }


def label_at_seconds(board: Storyboard, seconds: float) -> dict:
    """Sample-seconds label; see :func:`label_at_frame`."""
    return label_at_frame(board, frame_at_seconds(board, seconds))


def is_shot_bound(caption: Mapping) -> bool:
    """True when ``caption`` carries any shot-binding key."""
    if not isinstance(caption, Mapping):
        raise TimelineError("caption must be a mapping")
    return any(key in caption for key in SHOT_BOUND_KEYS)


def resolve_caption(caption: Mapping, board: Storyboard | None, fps: int) -> dict:
    """Resolve one caption's window to exact seconds without changing its meaning.

    Absolute captions (legacy) keep their declared ``start``/``end`` seconds
    unchanged and need no board. Shot-bound captions are mapped from
    ``shot_id`` + ``offset_frames`` (default 0) + ``duration_frames`` to
    ``start``/``end`` seconds plus the exact ``start_frame``/``end_frame``, and
    must lie entirely inside their shot and the board timeline. Mixing absolute
    and shot-bound timing, or a shot binding without a board, is refused.
    """
    if not isinstance(caption, Mapping):
        raise TimelineError("caption must be a mapping")
    fps = _integer(fps, "fps")
    if fps <= 0:
        raise TimelineError(f"fps must be positive, got {fps!r}")
    if board is not None:
        board = _board(board)
        if board.fps != fps:
            raise TimelineError(f"fps {fps} does not match the storyboard's {board.fps} fps")
    name = caption.get("id")
    bound = is_shot_bound(caption)
    absolute = "start" in caption or "end" in caption
    if bound and absolute:
        raise TimelineError(
            f"caption {name!r} mixes absolute start/end with a shot binding; "
            "declare exactly one timing form"
        )
    if bound:
        if board is None:
            raise TimelineError(f"caption {name!r} is shot-bound but no storyboard is available")
        shot_id = caption.get("shot_id")
        if not isinstance(shot_id, str) or not shot_id:
            raise TimelineError(f"caption {name!r} needs a non-empty shot_id")
        shot = next((candidate for candidate in board.shots if candidate.id == shot_id), None)
        if shot is None:
            raise TimelineError(f"caption {name!r} names unknown shot {shot_id!r}")
        offset = _integer(caption.get("offset_frames", 0), "offset_frames")
        duration = _integer(caption.get("duration_frames"), "duration_frames")
        if offset < 0:
            raise TimelineError(f"caption {name!r} offset_frames must not be negative")
        if duration <= 0:
            raise TimelineError(f"caption {name!r} duration_frames must be positive")
        start_frame = shot.start_frame + offset
        end_frame = start_frame + duration
        shot_end = shot.start_frame + shot.duration_frames
        if end_frame > shot_end:
            raise TimelineError(
                f"caption {name!r} ({duration} frames from offset {offset}) ends at frame "
                f"{end_frame}, outside shot {shot.id!r} "
                f"[{shot.start_frame}, {shot_end})"
            )
        if end_frame > board.total_frames:
            raise TimelineError(
                f"caption {name!r} ends at frame {end_frame}, past the storyboard's "
                f"{board.total_frames} frames"
            )
        resolved = dict(caption)
        resolved.update(
            {
                "shot_id": shot.id,
                "offset_frames": offset,
                "duration_frames": duration,
                "start_frame": start_frame,
                "end_frame": end_frame,
                "start": start_frame / fps,
                "end": end_frame / fps,
            }
        )
        return resolved
    if not absolute:
        raise TimelineError(f"caption {name!r} needs absolute start/end seconds or a shot binding")
    if "start" not in caption or "end" not in caption:
        raise TimelineError(f"caption {name!r} needs both start and end")
    start = _number(caption["start"], f"caption {name!r} start")
    end = _number(caption["end"], f"caption {name!r} end")
    if start < 0:
        raise TimelineError(f"caption {name!r} start must not be negative")
    if end <= start:
        raise TimelineError(f"caption {name!r} end {end!r}s must follow start {start!r}s")
    return dict(caption)


def resolve_captions(captions: Sequence[Mapping], board: Storyboard | None, fps: int) -> list[dict]:
    """Resolve every caption in declaration order; see :func:`resolve_caption`."""
    return [resolve_caption(caption, board, fps) for caption in captions]
