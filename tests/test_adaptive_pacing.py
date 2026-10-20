"""Pure, no-ffmpeg tests for the adaptive 4-12 second timing planner.

``mp3_to_videoclip.pacing`` is arithmetic over caller-supplied integer frames, so
everything here is a pure function call: no project directory, no ffmpeg, no
provider, no paid call and no file on disk. The fixtures model the shapes a real
production would hand over (a 3-6 minute track at 24/30 fps with a non-integer
frame count, constant or changing beat estimates, measured changes and reviewed
event boundaries) so the properties that matter are: exact coverage of
``total_frames``, durations inside the bounds, no tiny final tail, and reviewed
structure winning over estimates.
"""

from __future__ import annotations

import math

import pytest

from mp3_to_videoclip.pacing import PacingError, plan_boundaries

MIN_SECONDS = 4
MAX_SECONDS = 12


def frames(seconds: float, fps: int) -> int:
    """What a project records for a duration: ``ceil(seconds * fps)``."""
    return math.ceil(seconds * fps)


def bounds(fps: int, min_seconds: float = MIN_SECONDS, max_seconds: float = MAX_SECONDS):
    return math.ceil(min_seconds * fps), math.floor(max_seconds * fps)


def assert_partition(boundaries, total, fps, min_seconds=MIN_SECONDS, max_seconds=MAX_SECONDS):
    """Exact full coverage, sorted/unique endpoints and in-bounds durations."""
    min_frames, max_frames = bounds(fps, min_seconds, max_seconds)
    assert boundaries[0] == 0
    assert boundaries[-1] == total
    assert boundaries == sorted(boundaries)
    assert len(set(boundaries)) == len(boundaries)
    durations = [end - start for start, end in zip(boundaries, boundaries[1:], strict=False)]
    assert sum(durations) == total
    if total < min_frames:
        assert boundaries == [0, total]
        return durations
    assert all(min_frames <= duration <= max_frames for duration in durations)
    return durations


# --------------------------------------------------------------------------- #
# Short tracks and the single explicit short shot
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("fps,seconds", [(24, 2.5), (30, 1.0), (24, 3.999), (30, 3.5)])
def test_track_shorter_than_one_shot_is_a_single_explicit_shot(fps, seconds):
    total = frames(seconds, fps)
    assert plan_boundaries(total, fps) == [0, total]
    assert_partition(plan_boundaries(total, fps), total, fps)


def test_short_track_allowance_is_the_only_duration_below_minimum():
    # 4s at 24 fps is exactly the minimum: one full shot, not a short one.
    assert plan_boundaries(4 * 24, 24) == [0, 96]
    # 95 frames is one frame below the minimum and stays one explicit shot.
    assert plan_boundaries(95, 24) == [0, 95]


# --------------------------------------------------------------------------- #
# Bounds, coverage and the target
# --------------------------------------------------------------------------- #


def test_three_to_six_minute_tracks_cover_every_frame():
    # Same inputs as the former two-parameter sweep: both rates, five lengths.
    for fps in (24, 30):
        for seconds in (200.0, 213.37, 251.03, 300.0, 358.71):
            total = frames(seconds, fps)
            boundaries = plan_boundaries(total, fps)
            durations = assert_partition(boundaries, total, fps)
            # An unmarked track follows the eight-second target wherever the tail
            # allows: no more shots than the target implies, and most of them
            # exactly on target.
            assert len(durations) <= math.ceil(total / (8 * fps)) + 1
            assert len(durations) >= math.ceil(total / bounds(fps)[1])
            assert durations.count(8 * fps) >= len(durations) - 2


def test_unmarked_track_cuts_on_the_target_duration():
    total = frames(45.0, 24)
    assert plan_boundaries(total, 24) == [0, 192, 384, 576, 768, 960, 1080]
    assert_partition([0, 192, 384, 576, 768, 960, 1080], total, 24)


def test_target_is_clamped_into_the_duration_bounds():
    # A 30s target cannot produce longer shots than max_seconds allows.
    total = frames(120.0, 24)
    boundaries = plan_boundaries(total, 24, target_seconds=30)
    durations = assert_partition(boundaries, total, 24)
    assert set(durations) == {12 * 24}


def test_tighter_bounds_are_honoured():
    total = frames(100.0, 30)
    boundaries = plan_boundaries(total, 30, target_seconds=5, min_seconds=3, max_seconds=5)
    assert_partition(boundaries, total, 30, min_seconds=3, max_seconds=5)


# --------------------------------------------------------------------------- #
# Candidate priority: reviewed events, measured changes, beats, unmarked
# --------------------------------------------------------------------------- #


def test_reviewed_events_at_5_17_and_25_seconds_are_preferred():
    """Reviewed structure wins over the eight-second target, inside the bounds."""
    total = frames(40.0, 24)  # 960 frames
    events = (5 * 24, 17 * 24, 25 * 24)
    boundaries = plan_boundaries(total, 24, event_frames=events)
    assert boundaries[:4] == [0, 120, 408, 600]
    assert_partition(boundaries, total, 24)
    durations = [end - start for start, end in zip(boundaries, boundaries[1:], strict=False)]
    # 5s, 12s, 8s, ... - genuinely varied, not eight seconds everywhere.
    assert durations[:3] == [120, 288, 192]
    assert len(set(durations)) > 1


def test_event_outranks_a_change_and_a_beat_in_the_same_window():
    total = frames(40.0, 24)
    event = plan_boundaries(total, 24, event_frames=(11 * 24,))
    change = plan_boundaries(total, 24, change_frames=(11 * 24,))
    beat = plan_boundaries(total, 24, beat_frames=(11 * 24,))
    assert event == change == beat == [0, 264, 456, 648, 840, 960]


def test_reviewed_event_outranks_a_closer_measured_change():
    total = frames(40.0, 24)
    boundaries = plan_boundaries(
        total, 24, event_frames=(5 * 24,), change_frames=(8 * 24,), beat_frames=(8 * 24,)
    )
    assert boundaries[1] == 5 * 24


def test_measured_change_outranks_a_nearby_beat_but_not_a_far_change():
    total = frames(40.0, 24)
    # A beat sits exactly on the target; a measured change one second earlier wins.
    boundaries = plan_boundaries(total, 24, change_frames=(7 * 24,), beat_frames=(8 * 24,))
    assert boundaries[1] == 7 * 24


def test_events_far_from_the_target_still_win_inside_the_bounds():
    total = frames(45.0, 24)
    boundaries = plan_boundaries(total, 24, event_frames=(4 * 24, 33 * 24))
    assert boundaries[1] == 4 * 24  # the earliest reviewed event, still >= 4s
    assert 33 * 24 in boundaries
    assert_partition(boundaries, total, 24)


def test_an_event_that_would_leave_an_uncoverable_remainder_is_not_forced():
    # 45s at 24 fps: the last cut happens at frame 768 with 312 frames (13s) left.
    total = frames(45.0, 24)  # 1080
    # An event at 41s leaves exactly the 4s minimum: coverable, so it is honoured.
    honoured = plan_boundaries(total, 24, event_frames=(41 * 24,))
    assert honoured[-2] == 41 * 24
    assert honoured[-1] - honoured[-2] == 96
    # An event at 41.67s would leave a 3.3s tail: uncoverable, so it is dropped in
    # favour of the target cut and exact coverage survives.
    dropped = plan_boundaries(total, 24, event_frames=(1000,))
    assert 1000 not in dropped
    assert dropped == [0, 192, 384, 576, 768, 960, 1080]
    assert_partition(dropped, total, 24)


# --------------------------------------------------------------------------- #
# Candidate frame handling: order, duplicates, endpoints
# --------------------------------------------------------------------------- #


def test_input_order_does_not_change_the_result():
    total = frames(60.0, 24)
    events = (5 * 24, 21 * 24, 33 * 24)
    changes = (9 * 24, 26 * 24)
    beats = (2 * 24, 8 * 24, 24 * 24, 40 * 24)
    expected = plan_boundaries(
        total, 24, event_frames=events, change_frames=changes, beat_frames=beats
    )
    for event_order in (events, events[::-1]):
        for change_order in (changes, changes[::-1]):
            for beat_order in (beats, beats[::-1]):
                assert (
                    plan_boundaries(
                        total,
                        24,
                        event_frames=event_order,
                        change_frames=change_order,
                        beat_frames=beat_order,
                    )
                    == expected
                )


def test_duplicate_candidates_collapse():
    total = frames(45.0, 24)
    once = plan_boundaries(total, 24, event_frames=(5 * 24,), change_frames=(11 * 24,))
    twice = plan_boundaries(
        total,
        24,
        event_frames=(5 * 24, 5 * 24, 5 * 24),
        change_frames=(11 * 24, 11 * 24),
        beat_frames=(5 * 24, 11 * 24),
    )
    assert once == twice


def test_endpoint_candidates_never_add_a_boundary_and_are_deduped():
    total = frames(45.0, 24)
    boundaries = plan_boundaries(
        total,
        24,
        event_frames=(0, total, total + 1, total + 480),
        change_frames=(0,),
        beat_frames=(total,),
    )
    assert boundaries.count(0) == 1
    assert boundaries.count(total) == 1
    assert boundaries[-1] == total
    assert_partition(boundaries, total, 24)


def test_event_end_on_the_final_frame_is_ignored_not_rejected():
    # A reviewed event interval may legitimately end on the track's last frame.
    total = frames(45.0, 24)
    assert plan_boundaries(total, 24, event_frames=(total,)) == plan_boundaries(total, 24)


def test_absent_evidence_behaves_like_an_unmarked_track():
    """Same frame counts, different provenance: only the supplied lists matter."""
    for total, fps in ((frames(50.0, 30), 30), (frames(180.0, 24), 24)):
        assert plan_boundaries(total, fps) == plan_boundaries(
            total, fps, event_frames=(), change_frames=(), beat_frames=()
        )


# --------------------------------------------------------------------------- #
# Beat estimates: constant, changing, empty, unreliable
# --------------------------------------------------------------------------- #


def test_constant_beats_do_not_cut_once_per_beat():
    total = frames(180.0, 24)
    beats = tuple(range(0, total, 12))  # a beat every half second, 360 of them
    boundaries = plan_boundaries(total, 24, beat_frames=beats)
    durations = assert_partition(boundaries, total, 24)
    assert len(boundaries) - 1 == 22  # ~8s shots plus a 4s tail, not 360 cuts
    assert len(durations) < len(beats) / 2
    assert all(duration >= 96 for duration in durations)


def test_beats_every_two_seconds_keep_the_target_pace():
    total = frames(120.0, 30)
    beats = tuple(range(0, total, 60))
    boundaries = plan_boundaries(total, 30, beat_frames=beats)
    durations = assert_partition(boundaries, total, 30)
    assert set(durations) <= {240, 60, 180, 300}


def test_changing_tempo_beats_and_measured_changes_stay_in_bounds():
    total = frames(216.4, 24)  # a 3.6 minute track, non-integer frame count
    beats, frame = [], 0
    step = 8  # a speeding-up local estimate, not a real tempo claim
    while frame < total:
        beats.append(frame)
        frame += step
        step = max(4, step - 1)
    changes = (frames(37.0, 24), frames(88.0, 24), frames(151.0, 24))
    boundaries = plan_boundaries(total, 24, change_frames=changes, beat_frames=tuple(beats))
    durations = assert_partition(boundaries, total, 24)
    assert len(set(durations)) > 1
    assert boundaries[1] in {frame for frame in changes} | set(beats)


def test_unreliable_beat_counts_are_harmless():
    total = frames(200.0, 24)
    fixed = plan_boundaries(total, 24)
    # No beats, a sparse beat, a dense grid and duplicated beats all stay valid.
    for beats in ((), (total // 2,), tuple(range(0, total, 3)), (120, 120, 120)):
        boundaries = plan_boundaries(total, 24, beat_frames=beats)
        assert_partition(boundaries, total, 24)
    # A beat exactly on the target changes nothing; a beat near the start does
    # move the cut, and that is the documented (weakest) preference.
    assert plan_boundaries(total, 24, beat_frames=(8 * 24,)) == fixed
    assert plan_boundaries(total, 24, beat_frames=(120,))[1] == 120


# --------------------------------------------------------------------------- #
# Tails
# --------------------------------------------------------------------------- #


def test_a_thirteen_second_remainder_is_not_split_into_twelve_plus_one():
    total = frames(45.0, 24)  # 1080 frames: 8s x4 + 13s
    boundaries = plan_boundaries(total, 24)
    durations = assert_partition(boundaries, total, 24)
    assert sum(durations[:-1]) == 960
    assert durations[-1] == 120  # 5s, never a 12s shot followed by a 1s tail
    assert 1080 - boundaries[-2] >= 96


def test_tail_remains_coverable_for_awkward_ends():
    # The former parametrised inputs, unchanged.
    for tail_seconds in (4.1, 4.5, 12.0, 13.0, 13.5, 16.5):
        total = 4 * 192 + frames(tail_seconds, 24)
        boundaries = plan_boundaries(total, 24)
        durations = assert_partition(boundaries, total, 24)
        assert all(duration >= 96 for duration in durations)
        assert durations[-1] <= 288


# --------------------------------------------------------------------------- #
# Determinism and the property sweep
# --------------------------------------------------------------------------- #


def test_hundred_deterministic_track_lengths_form_valid_partitions():
    for index in range(100):
        total = 300 + index * 137 + (index % 7)
        for fps in (24, 30):
            first = plan_boundaries(total, fps, beat_frames=tuple(range(0, total, 13)))
            second = plan_boundaries(total, fps, beat_frames=tuple(range(0, total, 13)))
            assert first == second
            assert_partition(first, total, fps)


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("total", [0, -1, True, False, 12.5, "120", None])
def test_invalid_total_frames_are_rejected(total):
    with pytest.raises(PacingError):
        plan_boundaries(total, 24)


@pytest.mark.parametrize("fps", [0, -24, True, 24.0, "24", None])
def test_invalid_fps_is_rejected(fps):
    with pytest.raises(PacingError):
        plan_boundaries(4800, fps)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"target_seconds": float("nan")},
        {"target_seconds": float("inf")},
        {"target_seconds": -8},
        {"target_seconds": 0},
        {"target_seconds": True},
        {"min_seconds": float("nan")},
        {"min_seconds": float("-inf")},
        {"min_seconds": 0},
        {"min_seconds": -4},
        {"max_seconds": float("nan")},
        {"max_seconds": float("inf")},
        {"max_seconds": -1},
        {"max_seconds": True},
        {"min_seconds": 9, "max_seconds": 8},
        {"min_seconds": 4.2, "max_seconds": 4.4, "fps": 1},
    ],
)
def test_invalid_seconds_bounds_are_rejected(kwargs):
    fps = kwargs.pop("fps", 24)
    with pytest.raises(PacingError):
        plan_boundaries(4800, fps, **kwargs)


@pytest.mark.parametrize(
    "candidate",
    [
        -1,
        -480,
        True,
        False,
        120.0,
        120.5,
        float("nan"),
        float("inf"),
        float("-inf"),
        "120",
        None,
    ],
)
def test_invalid_candidate_frames_are_rejected(candidate):
    with pytest.raises(PacingError):
        plan_boundaries(4800, 24, event_frames=(candidate,))
    with pytest.raises(PacingError):
        plan_boundaries(4800, 24, change_frames=(120, candidate))
    with pytest.raises(PacingError):
        plan_boundaries(4800, 24, beat_frames=(candidate,))


def test_non_iterable_candidate_sets_are_rejected():
    with pytest.raises(PacingError):
        plan_boundaries(4800, 24, event_frames=120)


def test_pacing_error_is_a_value_error():
    assert issubclass(PacingError, ValueError)
