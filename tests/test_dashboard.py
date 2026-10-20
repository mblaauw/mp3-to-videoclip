"""Dashboard generator: determinism, honest uncertainty, escaping, no network."""

import json
from pathlib import Path

import pytest
from test_creative_production import approve_through_proof, make_root

from mp3_to_videoclip import dashboard
from mp3_to_videoclip.cli import execute, parser
from mp3_to_videoclip.storage import read_json, write_json


def seed_event(root):
    """One supplied, clearly estimated section spanning the project."""
    events = read_json(root / "work/events.json")
    events["events"] = [
        {
            "id": "supplied-intro",
            "frame": 0,
            "end_frame": events["total_frames"],
            "kind": "section",
            "label": "Supplied candidate: Intro",
            "timing_basis": "estimated",
            "note": "not independently verified",
            "level": "section",
            "confidence": "high",
            "source": "provided-intent",
            "evidence": "user-supplied seconds",
        }
    ]
    write_json(root / "work/events.json", events)
    return events


def build(root, stage="board", **kwargs):
    kwargs.setdefault("embed_images", False)
    kwargs.setdefault("embed_audio", False)
    return dashboard.build_dashboard(root, stage, **kwargs)


def test_dashboard_lists_every_shot_and_section(tmp_path):
    root = make_root(tmp_path)
    seed_event(root)
    # A dashboard is a view: it renders an unapproved project and shows what is missing.
    result = build(root)
    assert result["shots"] == len(read_json(root / "work/storyboard.json")["shots"])
    document = (root / result["html"]).read_text()
    for shot in read_json(root / "work/storyboard.json")["shots"]:
        assert f'id="shot-{shot["id"]}"' in document
    assert result["sections"] > 0
    assert "Sections: supplied tags vs. measurement" in document


def test_board_dashboard_claims_no_meter_or_bars(tmp_path):
    root = make_root(tmp_path)
    result = build(root)
    document = (root / result["html"]).read_text()
    assert result["grid_enabled"] is False
    assert "No bar grid" in document
    assert "no meter, bar or downbeat claimed" in document
    assert "bars" not in document.lower().replace("no meter, bar", "")
    # A single asserted BPM would be a fabrication; the measured estimate is labelled.
    assert "unresolved" in document


def test_dashboard_is_deterministic_for_fixed_inputs(tmp_path):
    root = make_root(tmp_path)
    first = build(root)
    second = build(root)
    one = (root / first["html"]).read_bytes()
    two = (root / second["html"]).read_bytes()
    assert one == two
    assert first["html"] != second["html"]  # never overwrite a version
    assert one.count(b"<html") == 1


def test_dashboard_has_no_network_or_external_assets(tmp_path):
    root = make_root(tmp_path)
    result = build(root, "stills", embed_images=True)
    document = (root / result["html"]).read_text()
    assert "http://" not in document and "https://" not in document
    assert "<link" not in document and "<script src" not in document
    assert "fetch(" not in document


def test_adopted_prompt_text_is_escaped_not_executed(tmp_path):
    root = make_root(tmp_path)
    board = read_json(root / "work/storyboard.json")
    board["shots"][0]["purpose"] = "<script>alert('x')</script> & <b>bold</b>"
    board["shots"][0]["must_show"] = ["a < b", "c & d"]
    write_json(root / "work/storyboard.json", board)
    result = build(root)
    document = (root / result["html"]).read_text()
    assert "<script>alert" not in document
    assert "&lt;script&gt;alert" in document
    assert "a &lt; b" in document and "c &amp; d" in document


def test_estimated_events_are_visually_distinct(tmp_path):
    root = make_root(tmp_path)
    seed_event(root)
    result = build(root)
    document = (root / result["html"]).read_text()
    assert 'class="card estimated"' in document
    assert 'class="badge estimated"' in document
    assert "dashed means estimated" in document


def test_approved_grid_enables_bars_and_unapproved_grid_is_ignored(tmp_path):
    root = make_root(tmp_path)
    unapproved = {
        "approved": False,
        "bpm": 120,
        "beats_per_bar": 4,
        "bar_zero_frame": 0,
        "frames_per_bar": 48,
    }
    write_json(root / "work/music-grid.json", unapproved)
    result = build(root)
    assert result["grid_enabled"] is False
    assert "<th>Bars</th>" not in (root / result["html"]).read_text()

    approved = {**unapproved, "approved": True, "approved_by": "test user", "note": "reviewed"}
    write_json(root / "work/music-grid.json", approved)
    result = build(root)
    assert result["grid_enabled"] is True
    document = (root / result["html"]).read_text()
    assert "<th>Bars</th>" in document
    assert "reviewed grid file" in document


def test_invalid_grid_fails_closed_with_a_reason(tmp_path):
    root = make_root(tmp_path)
    write_json(root / "work/music-grid.json", {"approved": True, "bpm": 0, "beats_per_bar": 99})
    result = build(root)
    assert result["grid_enabled"] is False
    document = (root / result["html"]).read_text()
    assert "bbox" not in document
    assert "beats_per_bar must be an integer" in document


def test_stale_approval_is_reported_as_stale(tmp_path):
    root = make_root(tmp_path)
    approve_through_proof(root)
    states = {state["stage"]: state for state in dashboard._approval_states(root)}
    assert states["storyboard"]["state"] == "approved"
    brief = read_json(root / "brief.json")
    brief["direction"] = brief["direction"] + " (changed after approval)"
    write_json(root / "brief.json", brief)
    states = {state["stage"]: state for state in dashboard._approval_states(root)}
    assert states["brief"]["state"] == "stale"
    # The board's own hash chains through the brief, so it is honestly stale too.
    assert states["storyboard"]["state"] == "stale"


def test_stage_stills_requires_selected_images_and_reports_missing(tmp_path):
    root = make_root(tmp_path)
    result = build(root, "stills")
    details = [finding["detail"] for finding in result["findings"]]
    assert any("no selected image" in detail for detail in details)
    document = (root / result["html"]).read_text()
    assert "no selected image" in document


def test_stage_stills_embeds_thumbnails_when_asked(tmp_path):
    root = make_root(tmp_path)
    approve_through_proof(root)
    result = build(root, "stills", embed_images=True)
    document = (root / result["html"]).read_text()
    assert result["embedded_images"] > 0
    assert "data:image/jpeg;base64," in document
    assert (root / "work/dashboard/thumbs").is_dir()


def test_dashboard_versioning_never_overwrites_and_name_is_safe(tmp_path):
    root = make_root(tmp_path)
    first = build(root)
    second = build(root)
    assert Path(first["html"]).name == "board-v001.html"
    assert Path(second["html"]).name == "board-v002.html"
    with pytest.raises(ValueError, match="never overwritten"):
        build(root, name="board-v001.html")
    with pytest.raises(ValueError, match="safe lowercase"):
        build(root, name="../escape.html")


def test_sidecar_binds_every_input_hash(tmp_path):
    root = make_root(tmp_path)
    result = build(root)
    sidecar = read_json(root / Path(result["html"]).with_suffix(".json"))
    assert sidecar["html_sha256"] == result["html_sha256"]
    for key in ("project", "brief", "storyboard", "events", "music"):
        assert sidecar["inputs"][key] == dashboard.file_hash(root / sidecar_path(key))
    assert "Review aid only" in sidecar["warning"]


def sidecar_path(key):
    return {
        "project": "project.json",
        "brief": "brief.json",
        "storyboard": "work/storyboard.json",
        "events": "work/events.json",
        "music": "work/music.json",
    }[key]


def test_cli_dashboard_command_writes_a_versioned_page(tmp_path):
    root = make_root(tmp_path)
    out = execute(parser().parse_args(["dashboard", str(root), "--stage", "board"]))
    assert out["stage"] == "board" and out["grid_enabled"] is False
    assert (root / out["html"]).is_file()
    assert (
        json.loads((root / Path(out["html"]).with_suffix(".json")).read_text())["shots"]
        == out["shots"]
    )


def test_alias_shot_is_marked_as_reuse_not_new_generation(tmp_path):
    root = make_root(tmp_path)
    board = read_json(root / "work/storyboard.json")
    board["shots"][1]["asset_shot_id"] = board["shots"][0]["id"]
    write_json(root / "work/storyboard.json", board)
    result = build(root)
    document = (root / result["html"]).read_text()
    assert f"reuses {board['shots'][0]['id']}" in document
