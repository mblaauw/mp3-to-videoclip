"""Validated re-edit: presentation-only changes with honest invalidation."""

import pytest
from test_creative_production import approve_through_proof, make_root

from mp3_to_videoclip.cli import execute, parser
from mp3_to_videoclip.storage import read_json


def test_camera_and_effects_are_applied_and_history_is_recorded(tmp_path):
    root = make_root(tmp_path)
    before = read_json(root / "work/storyboard.json")
    result = execute(
        parser().parse_args(
            [
                "shot-edit",
                str(root),
                "--shot",
                "s001",
                "--camera",
                "hold",
                "--effect",
                "contrast=1.05",
                "--effect",
                "vignette=0.08",
                "--note",
                "calm opening, slight contrast",
            ]
        )
    )
    assert result["edited"] == "s001"
    assert result["changes"]["camera"]["after"] == "hold"
    board = read_json(root / "work/storyboard.json")
    assert board["shots"][0]["post_effects"] == {
        "contrast": 1.05,
        "saturation": 1,
        "brightness": 1,
        "vignette": 0.08,
    }
    # Timing and other shots are untouched.
    assert board["total_frames"] == before["total_frames"]
    assert [s["start_frame"] for s in board["shots"]] == [s["start_frame"] for s in before["shots"]]
    assert [s["duration_frames"] for s in board["shots"]] == [
        s["duration_frames"] for s in before["shots"]
    ]
    history = read_json(root / "work/edits.json")
    assert len(history) == 1 and history[0]["note"] == "calm opening, slight contrast"
    assert (root / history[0]["previous_board"]).is_file()


def test_transition_needs_a_dissolve_handle(tmp_path):
    root = make_root(tmp_path)
    with pytest.raises(ValueError, match="dissolve"):
        execute(
            parser().parse_args(
                ["shot-edit", str(root), "--shot", "s002", "--transition", "fade", "--note", "x"]
            )
        )
    result = execute(
        parser().parse_args(
            [
                "shot-edit",
                str(root),
                "--shot",
                "s002",
                "--transition",
                "fade",
                "--dissolve",
                "4",
                "--note",
                "soften the arrival",
            ]
        )
    )
    assert result["changes"]["transition"]["after"] == "fade"
    assert result["changes"]["dissolve_frames"]["after"] == 4


def test_effect_bounds_and_unknown_keys_are_rejected(tmp_path):
    root = make_root(tmp_path)
    for effect in ("contrast=9", "saturation=0.1", "nope=1"):
        with pytest.raises(ValueError):
            execute(
                parser().parse_args(
                    ["shot-edit", str(root), "--shot", "s001", "--effect", effect, "--note", "x"]
                )
            )
    assert read_json(root / "work/storyboard.json")["shots"][0].get("post_effects") is None


def test_edit_reports_invalidated_approvals(tmp_path):
    root = make_root(tmp_path)
    approve_through_proof(root)
    result = execute(
        parser().parse_args(
            ["shot-edit", str(root), "--shot", "s001", "--camera", "pan_right", "--note", "re-edit"]
        )
    )
    assert "storyboard" in result["invalidated"]
    assert "proof" in result["invalidated"]
    assert "bytes changed" in result["reason"]


def test_no_change_alias_and_unknown_shot_are_refused(tmp_path):
    root = make_root(tmp_path)
    with pytest.raises(ValueError, match="nothing to change"):
        execute(parser().parse_args(["shot-edit", str(root), "--shot", "s001", "--note", "x"]))
    with pytest.raises(ValueError, match="already match"):
        execute(
            parser().parse_args(
                ["shot-edit", str(root), "--shot", "s001", "--camera", "zoom_in", "--note", "x"]
            )
        )
    with pytest.raises(ValueError, match="unknown shot"):
        execute(
            parser().parse_args(
                ["shot-edit", str(root), "--shot", "nope", "--camera", "hold", "--note", "x"]
            )
        )
    board = read_json(root / "work/storyboard.json")
    board["shots"][1]["asset_shot_id"] = "s001"
    from mp3_to_videoclip.storage import write_json

    write_json(root / "work/storyboard.json", board)
    with pytest.raises(ValueError, match="reprise"):
        execute(
            parser().parse_args(
                ["shot-edit", str(root), "--shot", "s002", "--camera", "hold", "--note", "x"]
            )
        )


def test_clear_effects(tmp_path):
    root = make_root(tmp_path)
    execute(
        parser().parse_args(
            [
                "shot-edit",
                str(root),
                "--shot",
                "s001",
                "--effect",
                "vignette=0.1",
                "--note",
                "grade",
            ]
        )
    )
    result = execute(
        parser().parse_args(
            ["shot-edit", str(root), "--shot", "s001", "--clear-effects", "--note", "clean"]
        )
    )
    assert result["changes"]["post_effects"]["after"] is None
    assert "post_effects" not in read_json(root / "work/storyboard.json")["shots"][0]
