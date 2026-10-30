"""Integer-frame title windows: the opening, captions, credit cards and lockup.

One plan feeds every surface that draws titles: the Studio Player, the review
stills and the final render. Windows are whole output frames on the film's own
timeline (``start_frame`` inclusive, ``start_frame + frames`` exclusive), the
same contract the storyboard and the edit use.

The rules are the signature compositor's, expressed in frames: the opening
starts at frame 0, a caption keeps clear of the opening and the credits, the
credits tail ends with the music, and no two windows overlap. Shot-bound
captions resolve against the edit-owned timing when an edit exists, so a caption
follows its shot when the cut moves it. Nothing here reads pixels, fonts or
movies, and nothing is written.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import Path

from .models import Storyboard
from .timeline import TimelineError, is_shot_bound, resolve_captions

#: Seconds a caption keeps clear of the opening and of the credits tail.
MIN_CAPTION_GAP = 0.25
#: The joint-identity beat that opens the closing package in ``joint-v1``.
DESIGN_JOINT = "joint-v1"
IDENTITY_MAX_SECONDS = 6.0


class TitleError(ValueError):
    """The spec cannot be laid out on this film's timeline."""


def _window(kind: str, ident: str, start_frame: int, frames: int, **extra) -> dict:
    return {"kind": kind, "id": ident, "start_frame": start_frame, "frames": frames, **extra}


def plan_titles(
    spec: Mapping,
    *,
    fps: int,
    duration: float,
    captions: Sequence[Mapping] | None = None,
) -> tuple[list[dict], int]:
    """Lay the spec out as ordered, non-overlapping windows; returns ``(windows, total)``.

    ``captions`` are already resolved (see :func:`resolve_titles`); without them
    the spec's captions must all be absolute. ``total`` is the film's frame count.
    """
    total = math.ceil(duration * fps)
    intro_frames = max(1, round(float(spec["intro_seconds"]) * fps))
    credits_tail = float(spec["credits_tail_seconds"])
    lockup_seconds = float(spec["lockup_seconds"])
    credits_start = duration - credits_tail
    windows = [_window("intro", "intro", 0, intro_frames)]

    planned = list(captions) if captions is not None else list(spec["captions"])
    for cap in sorted(planned, key=lambda c: float(c["start"])):
        start, end = float(cap["start"]), float(cap["end"])
        if start < intro_frames / fps + MIN_CAPTION_GAP:
            raise TitleError(f"caption {cap['id']} starts inside the intro window")
        if end > credits_start - MIN_CAPTION_GAP:
            raise TitleError(f"caption {cap['id']} overlaps the credits window")
        windows.append(
            _window(
                "caption",
                cap["id"],
                round(start * fps),
                max(1, round((end - start) * fps)),
                caption=dict(cap),
            )
        )

    cards = spec["credits"]["cards"]
    if not cards:
        raise TitleError("the credits need at least one card")
    cursor = round(credits_start * fps)
    # A joint-identity beat opens the closing package, so the partnership reads
    # as a signature rather than as one more name in a list. Its window is
    # capped so a short credit tail degrades to the plain card sequence.
    identity_span = 0.0
    if spec.get("design") == DESIGN_JOINT:
        identity_span = max(
            0.0, min(IDENTITY_MAX_SECONDS, (credits_tail - lockup_seconds) / (len(cards) + 1))
        )
        if identity_span > 0:
            frames = max(1, round(identity_span * fps))
            windows.append(_window("identity", "identity", cursor, frames))
            cursor += frames
    card_span = (credits_tail - lockup_seconds - identity_span) / len(cards)
    for index, card in enumerate(cards):
        frames = max(1, round(card_span * fps))
        windows.append(
            _window("card", f"card-{index + 1:02d}", cursor, frames, index=index, card=list(card))
        )
        cursor += frames
    lock_frames = max(1, total - cursor)
    windows.append(_window("lockup", "lockup", cursor, lock_frames))

    windows.sort(key=lambda window: window["start_frame"])
    for a, b in zip(windows, windows[1:], strict=False):
        if b["start_frame"] < a["start_frame"] + a["frames"]:
            raise TitleError(f"overlay window {b['id']} overlaps {a['id']}")
    if cursor + lock_frames > total + 2:
        raise TitleError("credits extend past the end of the music")
    return windows, total


def resolve_titles(spec: Mapping, board: Storyboard | None, fps: int) -> list[dict]:
    """Resolve the spec's captions; a shot-bound caption needs ``board``."""
    try:
        return resolve_captions(spec["captions"], board, fps)
    except TimelineError as exc:
        raise TitleError(f"caption timeline resolution failed: {exc}") from exc


def needs_board(spec: Mapping) -> bool:
    return any(is_shot_bound(cap) for cap in spec["captions"])


def timing_board(root: Path, board: Storyboard) -> Storyboard:
    """The board whose timing a shot-bound caption follows: the edit's, when one exists."""
    from .edits import effective_board

    return effective_board(root, board)
