"""Adaptive timing wiring and instrumental no-transcription invariants."""

import pytest
from test_creative_production import approve_prerequisites, make_root

from mp3_to_videoclip import generation as G
from mp3_to_videoclip import production as P
from mp3_to_videoclip import profiles
from mp3_to_videoclip.cli import execute, parser
from mp3_to_videoclip.models import MusicEvent
from mp3_to_videoclip.storage import read_json, write_json


def musical_root(tmp_path, *, frames=24 * 53 + 7, preset=True):
    root = make_root(
        tmp_path, with_storyboard=False, music_mode="instrumental", total_frames=frames
    )
    config = read_json(root / "project.json")
    if preset:
        config.update(
            image_model=profiles.DEFAULT_MODEL,
            image_settings=profiles.default_settings(),
            native_size=[1376, 768],
        )
        write_json(root / "project.json", config)
    local = read_json(root / "work/music.json")
    local.update(
        beats=[n / 2 for n in range(int(config["duration"] * 2))],
        candidate_changes=[{"time": t} for t in (5, 17, 25, 41) if t < config["duration"]],
    )
    write_json(root / "work/music.json", local)
    event_map = read_json(root / "work/events.json")
    event_map["events"] = (
        [
            MusicEvent(
                id="change",
                frame=5 * 24,
                kind="accent",
                label="Reviewed change",
                timing_basis="manual",
            ).model_dump()
        ]
        if frames > 5 * 24
        else []
    )
    write_json(root / "work/events.json", event_map)
    approve_prerequisites(root)
    return root


def test_new_preset_defaults_adaptive_exact_coverage_with_no_lyrics(tmp_path):
    root = musical_root(tmp_path)
    result = execute(parser().parse_args(["skeleton", str(root)]))
    assert result["timing"] == "adaptive"
    assert not (root / "work/lyrics.json").exists()
    board = P.load_board(root)
    assert board.shots[0].duration_frames == 5 * 24
    assert sum(s.duration_frames for s in board.shots) == P.load_project(root).total_frames
    assert all(4 * 24 <= s.duration_frames <= 12 * 24 for s in board.shots)
    assert len({s.duration_frames for s in board.shots}) > 1
    with pytest.raises(ValueError, match="already exists"):
        P.skeleton(root, timing="adaptive")


def test_existing_project_cli_keeps_beat_timing(tmp_path):
    root = musical_root(tmp_path, preset=False)
    result = execute(parser().parse_args(["skeleton", str(root)]))
    assert result["timing"] == "beats"


def test_explicit_fixed_timing_overrides_adaptive_preset(tmp_path):
    root = musical_root(tmp_path, frames=24 * 48)
    result = execute(
        parser().parse_args(["skeleton", str(root), "--timing", "free", "--seconds", "6"])
    )
    assert result["timing"] == "free"
    assert all(s.duration_frames == 6 * 24 for s in P.load_board(root).shots)


def test_short_track_is_one_labelled_exception_not_truncated(tmp_path):
    root = musical_root(tmp_path, frames=63)
    result = execute(parser().parse_args(["skeleton", str(root)]))
    assert result["short_track_exception"] is True
    assert [s.duration_frames for s in P.load_board(root).shots] == [63]
    assert any("shorter than one minimum shot" in note for note in result["timing_notes"])


def test_audio_rounded_up_to_full_minimum_is_not_short_exception(tmp_path):
    root = musical_root(tmp_path, frames=96)
    config = read_json(root / "project.json")
    config["duration"] = 3.999
    write_json(root / "project.json", config)
    local = read_json(root / "work/music.json")
    local["duration"] = 3.999
    write_json(root / "work/music.json", local)
    approve_prerequisites(root)
    result = execute(parser().parse_args(["skeleton", str(root)]))
    assert result["short_track_exception"] is False
    assert [s.duration_frames for s in P.load_board(root).shots] == [96]


def test_impossible_narrow_range_fails_clearly_without_writing_board(tmp_path):
    root = musical_root(tmp_path, frames=349)
    with pytest.raises(ValueError, match="cannot cover 349 frames exactly.*widen"):
        execute(
            parser().parse_args(
                ["skeleton", str(root), "--min-seconds", "4", "--max-seconds", "4.5"]
            )
        )
    assert not (root / "work/storyboard.json").exists()


def test_estimated_events_are_not_promoted_to_reviewed_structure(tmp_path):
    root = musical_root(tmp_path, frames=48 * 24)
    events = read_json(root / "work/events.json")
    events["events"][0]["timing_basis"] = "estimated"
    write_json(root / "work/events.json", events)
    approve_prerequisites(root)
    result = execute(parser().parse_args(["skeleton", str(root)]))
    assert any("Ignored 1 estimated event" in n for n in result["timing_notes"])
    assert any("No reviewed manual event boundaries" in n for n in result["timing_notes"])


def test_missing_analysis_fails_the_existing_approval_gate(tmp_path):
    root = musical_root(tmp_path)
    (root / "work/music.json").unlink()
    with pytest.raises(ValueError, match="analysis review artifact is missing"):
        P.skeleton(root, timing="adaptive")
    assert not (root / "work/storyboard.json").exists()


def test_adaptive_uses_only_approved_events_and_does_not_transcribe(tmp_path):
    root = musical_root(tmp_path)
    event_map = read_json(root / "work/events.json")
    event_map["events"][0]["frame"] += 1
    write_json(root / "work/events.json", event_map)
    with pytest.raises(ValueError, match="approval"):
        P.skeleton(root, timing="adaptive")
    assert not (root / "work/storyboard.json").exists()

    class NeverCall:
        def __getattr__(self, name):
            raise AssertionError(f"provider should never be accessed: {name}")

    with pytest.raises(ValueError, match="instrumental"):
        G.quote_transcription(root, client=NeverCall())
    with pytest.raises(ValueError, match="instrumental"):
        G.transcribe_quote(root, "nonexistent", client=NeverCall())
    assert read_json(root / "work/tasks.json") == {}
