"""Pure, no-ffmpeg tests for the integer-frame timeline helpers.

The helpers are read-only functions over an already-validated ``Storyboard``:
exact half-open shot boundaries, frame-exact caption resolution (legacy absolute
and shot-bound) and the sample labels a preflight still is stamped with. Nothing
here touches a project file, a provider or a paid call.
"""

from __future__ import annotations

import math

import pytest

from mp3_to_videoclip import timeline
from mp3_to_videoclip.models import Shot, Storyboard

FPS = 24
DURATIONS = (48, 72, 60)
BOUNDARIES = (0, 48, 120, 180)


def _board(fps: int = FPS, durations=DURATIONS, alias: dict | None = None) -> Storyboard:
    """A contiguous three-shot board; frame sizes stay exact integers."""
    shots, cursor = [], 0
    for index, duration in enumerate(durations):
        shots.append(
            Shot(
                id=f"s{index + 1:03d}",
                start_frame=cursor,
                duration_frames=duration,
                purpose=f"shot {index + 1}",
                image_prompt=f"prompt for shot {index + 1}",
                asset_shot_id=(alias or {}).get(index),
            )
        )
        cursor += duration
    return Storyboard(aspect="16:9", fps=fps, total_frames=cursor, shots=shots)


def _caption(**extra) -> dict:
    return {"id": "c1", "style": "caption", "text": "A LINE", **extra}


# --------------------------------------------------------------------------- #
# frames and half-open shot boundaries
# --------------------------------------------------------------------------- #
def test_shot_at_frame_boundaries_are_half_open():
    board = _board()
    assert board.total_frames == 180
    assert timeline.shot_at_frame(board, 0).id == "s001"
    assert timeline.shot_at_frame(board, 47).id == "s001"
    # The boundary frame belongs to the following shot, never to the previous.
    assert timeline.shot_at_frame(board, 48).id == "s002"
    assert timeline.shot_at_frame(board, 119).id == "s002"
    assert timeline.shot_at_frame(board, 120).id == "s003"
    assert timeline.shot_at_frame(board, 179).id == "s003"


@pytest.mark.parametrize("frame", [-1, 180, True, False, 1.0, "1", None, 48.0])
def test_shot_at_frame_rejects_non_integers_and_out_of_range(frame):
    with pytest.raises(timeline.TimelineError):
        timeline.shot_at_frame(_board(), frame)


def test_frame_at_seconds_floors_and_handles_ulp_boundaries():
    board = _board()
    assert timeline.frame_at_seconds(board, 1.9999) == 47
    assert timeline.shot_at_seconds(board, 1.9999).id == "s001"
    assert timeline.frame_at_seconds(board, 2.0) == 48
    assert timeline.shot_at_seconds(board, 2.0).id == "s002"
    assert timeline.frame_at_seconds(board, 2.0 - 1e-9) == 47
    # Just under the next frame stays in the previous frame, exactly.
    assert timeline.shot_at_seconds(board, 5.0 - 1 / FPS / 2).id == "s002"
    # Every boundary re-multiplies to its own frame, not the previous one: this is
    # the float edge that a bare floor(seconds * fps) gets wrong.
    for boundary in BOUNDARIES[:-1]:
        seconds = boundary / FPS
        assert timeline.frame_at_seconds(board, seconds) == boundary
        assert (
            timeline.shot_at_frame(board, boundary).id
            == timeline.shot_at_seconds(board, seconds).id
        )
    last = board.total_frames - 1
    assert timeline.frame_at_seconds(board, last / FPS) == last


def test_frame_number_round_trips_every_frame_at_both_fps_values():
    # frame / fps must re-multiply to its own frame for every frame, at both
    # supported rates: otherwise a frame-exact caption drifts one frame earlier.
    for fps in (24, 30):
        for frame in range(3000):
            assert timeline.frame_number(frame / fps, fps) == frame


@pytest.mark.parametrize(
    "seconds",
    [math.nan, math.inf, -math.inf, -0.001, 7.5, 7.6, True, "2.0", None],
)
def test_shot_at_seconds_rejects_non_finite_and_out_of_range(seconds):
    board = _board()
    with pytest.raises(timeline.TimelineError):
        timeline.shot_at_seconds(board, seconds)


def test_frame_number_rejects_bad_fps_and_seconds():
    for fps in (0, -24, 24.0, True):
        with pytest.raises(timeline.TimelineError):
            timeline.frame_number(1.0, fps)
    with pytest.raises(timeline.TimelineError):
        timeline.frame_number(-1.0, FPS)


# --------------------------------------------------------------------------- #
# labels: exact shot, alias owner and interval
# --------------------------------------------------------------------------- #
def test_labels_report_shot_alias_owner_and_half_open_interval():
    board = _board(alias={2: "s001"})
    label = timeline.label_at_frame(board, 130)
    assert label["frame"] == 130
    assert label["seconds"] == 130 / FPS
    assert label["shot_id"] == "s003"
    assert label["owner_shot_id"] == "s001"
    assert (label["start_frame"], label["end_frame"]) == (120, 180)
    assert (label["start_seconds"], label["end_seconds"]) == (120 / FPS, 180 / FPS)

    by_seconds = timeline.label_at_seconds(board, 5.0)
    assert by_seconds["shot_id"] == "s003"
    assert by_seconds["frame"] == 120
    # A shot that owns its own still reports itself as the owner.
    assert timeline.label_at_frame(board, 0)["owner_shot_id"] == "s001"


@pytest.mark.parametrize("frame", [-1, 180, 1.5])
def test_labels_reject_out_of_range_and_non_integer_frames(frame):
    with pytest.raises(timeline.TimelineError):
        timeline.label_at_frame(_board(), frame)


# --------------------------------------------------------------------------- #
# legacy absolute captions stay untouched
# --------------------------------------------------------------------------- #
def test_legacy_absolute_caption_is_unchanged_and_needs_no_board():
    cap = _caption(start=27, end=30.0)
    resolved = timeline.resolve_caption(cap, None, FPS)
    assert resolved == cap
    assert resolved is not cap
    assert "start_frame" not in resolved
    # A board may be supplied without changing an absolute caption's meaning.
    assert timeline.resolve_caption(cap, _board(), FPS) == cap


@pytest.mark.parametrize(
    "cap",
    [
        _caption(start=27.0),
        _caption(end=30.0),
        _caption(start=30.0, end=27.0),
        _caption(start=27.0, end=27.0),
        _caption(start=-1.0, end=30.0),
        _caption(start=27.0, end=math.nan),
        _caption(start=True, end=30.0),
    ],
)
def test_legacy_absolute_caption_is_validated(cap):
    with pytest.raises(timeline.TimelineError):
        timeline.resolve_caption(cap, None, FPS)


# --------------------------------------------------------------------------- #
# shot-bound captions
# --------------------------------------------------------------------------- #
def test_shot_bound_caption_maps_to_frame_exact_seconds():
    board = _board()
    resolved = timeline.resolve_caption(
        _caption(shot_id="s002", offset_frames=12, duration_frames=24), board, FPS
    )
    assert resolved["shot_id"] == "s002"
    assert (resolved["start_frame"], resolved["end_frame"]) == (60, 84)
    assert resolved["start"] == 60 / FPS
    assert resolved["end"] == 84 / FPS
    assert resolved["offset_frames"] == 12 and resolved["duration_frames"] == 24
    # The other caption data survives the resolution untouched.
    assert resolved["text"] == "A LINE" and resolved["style"] == "caption"


def test_shot_bound_caption_defaults_to_the_shot_start():
    board = _board()
    resolved = timeline.resolve_caption(_caption(shot_id="s002", duration_frames=8), board, FPS)
    assert resolved["offset_frames"] == 0
    assert resolved["start_frame"] == board.shots[1].start_frame == 48


def test_shot_bound_caption_may_fill_its_shot_exactly():
    board = _board()
    resolved = timeline.resolve_caption(_caption(shot_id="s001", duration_frames=48), board, FPS)
    # [0, 48) is exactly shot s001: allowed, no implicit stretching.
    assert (resolved["start_frame"], resolved["end_frame"]) == (0, 48)


@pytest.mark.parametrize(
    "extra",
    [
        {"shot_id": "s001", "duration_frames": 49},  # one frame past the shot
        {"shot_id": "s001", "offset_frames": 47, "duration_frames": 2},
        {"shot_id": "s001", "offset_frames": 48, "duration_frames": 1},
        {"shot_id": "s003", "offset_frames": 59, "duration_frames": 2},
    ],
)
def test_shot_caption_past_its_boundary_is_rejected(extra):
    with pytest.raises(timeline.TimelineError, match="outside shot|past the storyboard"):
        timeline.resolve_caption(_caption(**extra), _board(), FPS)


@pytest.mark.parametrize(
    "extra",
    [
        {"shot_id": "s002"},  # no duration
        {"shot_id": "s002", "duration_frames": 0},
        {"shot_id": "s002", "duration_frames": -8},
        {"shot_id": "s002", "duration_frames": 8.0},
        {"shot_id": "s002", "duration_frames": True},
        {"shot_id": "s002", "offset_frames": -1, "duration_frames": 8},
        {"shot_id": "s002", "offset_frames": True, "duration_frames": 8},
        {"shot_id": "s900", "duration_frames": 8},
        {"shot_id": "", "duration_frames": 8},
        {"shot_id": 3, "duration_frames": 8},
    ],
)
def test_shot_bound_caption_rejects_invalid_bindings(extra):
    with pytest.raises(timeline.TimelineError):
        timeline.resolve_caption(_caption(**extra), _board(), FPS)


def test_shot_bound_caption_requires_a_board():
    with pytest.raises(timeline.TimelineError, match="no storyboard"):
        timeline.resolve_caption(_caption(shot_id="s002", duration_frames=8), None, FPS)


def test_mixed_absolute_and_shot_timing_is_rejected():
    cap = _caption(shot_id="s002", offset_frames=0, duration_frames=8, start=8.0, end=9.0)
    with pytest.raises(timeline.TimelineError, match="mixes absolute"):
        timeline.resolve_caption(cap, _board(), FPS)
    # A lone absolute key counts as the absolute form too.
    cap = _caption(shot_id="s002", duration_frames=8, end=9.0)
    with pytest.raises(timeline.TimelineError, match="mixes absolute"):
        timeline.resolve_caption(cap, _board(), FPS)


def test_caption_without_any_timing_is_rejected():
    with pytest.raises(timeline.TimelineError, match="needs absolute start/end"):
        timeline.resolve_caption(_caption(), None, FPS)


def test_fps_must_be_positive_and_match_the_storyboard():
    board = _board()
    bound = _caption(shot_id="s002", duration_frames=8)
    with pytest.raises(timeline.TimelineError, match="does not match"):
        timeline.resolve_caption(bound, board, 30)
    for fps in (0, -1, True, 24.0):
        with pytest.raises(timeline.TimelineError):
            timeline.resolve_caption(bound, board, fps)
    # A board at 30 fps resolves the same frame window at 30 fps.
    board30 = Storyboard(
        aspect="16:9",
        fps=30,
        total_frames=300,
        shots=[
            Shot(
                id="s001",
                start_frame=0,
                duration_frames=300,
                purpose="one",
                image_prompt="prompt",
            )
        ],
    )
    resolved = timeline.resolve_caption(
        {
            "id": "c1",
            "style": "caption",
            "text": "X",
            "shot_id": "s001",
            "offset_frames": 30,
            "duration_frames": 30,
        },
        board30,
        30,
    )
    assert (resolved["start_frame"], resolved["end_frame"]) == (30, 60)
    assert resolved["start"] == 1.0 and resolved["end"] == 2.0


# --------------------------------------------------------------------------- #
# helpers over a caption list
# --------------------------------------------------------------------------- #
def test_is_shot_bound_detects_every_binding_key():
    assert timeline.is_shot_bound({"shot_id": "s001"}) is True
    assert timeline.is_shot_bound({"offset_frames": 0}) is True
    assert timeline.is_shot_bound({"duration_frames": 4}) is True
    assert timeline.is_shot_bound({"start": 1.0, "end": 2.0}) is False
    with pytest.raises(timeline.TimelineError):
        timeline.is_shot_bound("not-a-caption")


def test_resolve_captions_keeps_declaration_order_and_mixes_both_forms():
    board = _board()
    captions = [
        _caption(id="legacy", start=2.0, end=3.0),
        _caption(id="bound", shot_id="s003", offset_frames=4, duration_frames=8),
    ]
    resolved = timeline.resolve_captions(captions, board, FPS)
    assert [cap["id"] for cap in resolved] == ["legacy", "bound"]
    assert resolved[0] == captions[0]
    assert resolved[1]["start_frame"] == 124
    with pytest.raises(timeline.TimelineError):
        timeline.resolve_captions(captions, None, FPS)
