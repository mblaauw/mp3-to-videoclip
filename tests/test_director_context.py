"""The director context is a cheap snapshot, never a full gate pass."""

from __future__ import annotations

from pathlib import Path

from api_support import add_assets, make_api_project

from mp3_to_videoclip import production as P
from mp3_to_videoclip.director.context import build_context


def test_context_contains_the_brief_shots_and_stage_without_source_hashes(
    tmp_path: Path, monkeypatch
):
    root = make_api_project(tmp_path)
    add_assets(root)
    seen: list[bool] = []
    original = P.load_project

    def tracked(project_root, verify_source=True):
        seen.append(verify_source)
        return original(project_root, verify_source=False)

    monkeypatch.setattr(P, "load_project", tracked)

    def fail(_root):
        raise AssertionError("context must not run P.status")

    monkeypatch.setattr(P, "status", fail)

    text = build_context("production", tmp_path, stage="story")

    assert "Project snapshot" in text
    assert "Current stage: story" in text
    assert "Direction: DIRECTION-SECRET" in text
    assert "Shots (4:" in text
    assert "current v1" in text
    assert "Recorded approvals" in text
    assert seen and not any(seen), "the snapshot must never re-hash the source"


def test_context_reports_stale_stills_after_a_brief_change(tmp_path: Path):
    root = make_api_project(tmp_path)
    add_assets(root)
    P.update_brief(root, {"creative": {"look": "A different look"}})
    text = build_context("production", tmp_path)
    assert "stale (inputs changed)" in text
    assert "0 current" in text


def test_context_carries_the_playhead_and_selected_shots(tmp_path: Path):
    make_api_project(tmp_path)
    text = build_context(
        "production",
        tmp_path,
        stage="storyboard",
        context={"stage": "storyboard", "time": 12.5, "selected_shots": ["s001", "s004"]},
    )
    assert "## Session context" in text
    assert "Stage when asked: storyboard" in text
    assert "Playhead: 12.50s" in text
    assert "Selected shots: s001, s004" in text
