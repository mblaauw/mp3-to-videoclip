"""Offline eval fixtures and checks; no Writer model or paid provider is called."""

from __future__ import annotations

from evals import checks

from mp3_to_videoclip.models import Shot, Storyboard


def test_three_fixtures_are_frozen_and_complete():
    fixtures = checks.load_fixtures()
    assert [value["name"] for value in fixtures] == [
        "advert-30s",
        "energetic-vocal",
        "slow-instrumental",
    ]
    for value in fixtures:
        assert value["kind"] in ("music_video", "advert")
        assert value["music"]["sections"]
        assert value["stills"]
        if value["music_mode"] == "instrumental":
            assert value["lyrics"] == []
        else:
            assert value["lyrics"]


def test_materialized_stills_are_deterministic(tmp_path):
    value = checks.fixture("advert-30s")
    first = checks.materialize_stills(value, tmp_path / "one")
    second = checks.materialize_stills(value, tmp_path / "two")
    assert len(first) == len(value["stills"])
    assert [path.name for path in first] == [path.name for path in second]
    assert all(path.read_bytes().startswith(b"\x89PNG") for path in first)


def _concepts():
    return {
        "concepts": [
            {
                "id": f"c{index}",
                "title": f"Route {index}",
                "structure": structure,
                "logline": "A line",
                "why": "A reason",
                "world": "A world",
                "shape": ["a", "b", "c", "d"],
                "signature_moment": "One image",
                "risk": "One risk",
            }
            for index, structure in enumerate(("narrative", "demonstration", "three reasons"))
        ]
    }


def test_concept_report_requires_three_distinct_structures():
    assert checks.concept_report(_concepts())["ok"] is True
    duplicate = _concepts()
    duplicate["concepts"][1]["structure"] = "narrative"
    report = checks.concept_report(duplicate)
    assert report["ok"] is False
    assert report["distinct_structures"] == 2


def _advert_board():
    return Storyboard(
        aspect="16:9",
        fps=24,
        total_frames=720,
        shots=[
            Shot(
                id="s001",
                start_frame=0,
                duration_frames=240,
                kind="scene",
                purpose="open",
                message="the record",
                image_prompt="A record on a turntable",
            ),
            Shot(
                id="s002",
                start_frame=240,
                duration_frames=120,
                kind="card",
                purpose="state the silence",
                message="two years",
                text=["Two years of silence."],
            ),
            Shot(
                id="s003",
                start_frame=360,
                duration_frames=360,
                kind="end_card",
                purpose="close",
                message="out now",
                text=["Out 14 Nov", "Pre-save now"],
            ),
        ],
    )


def test_storyboard_report_covers_frames_and_counts_local_kinds():
    report = checks.storyboard_report(_advert_board(), kind="advert")
    assert report["ok"] is True, report["issues"]
    assert report["non_scene"] == ["s002", "s003"]

    all_scene = _advert_board()
    all_scene.shots[1] = Shot(
        id="s002",
        start_frame=240,
        duration_frames=120,
        purpose="open",
        message="the record",
        image_prompt="A record",
    )
    all_scene.shots[2] = Shot(
        id="s003",
        start_frame=360,
        duration_frames=360,
        purpose="open",
        message="the record",
        image_prompt="A record",
    )
    assert checks.storyboard_report(all_scene, kind="advert")["ok"] is False


def test_claims_must_trace_to_the_intent():
    allowed = checks.fixture("advert-30s")["allowed_facts"]
    good = checks.claim_report(
        ["The new single is out 14 Nov.", "Pre-save now", "https://example.com"], allowed
    )
    assert good["ok"] is True
    bad = checks.claim_report(["Out 18 Dec for $9.99 at https://other.example"], allowed)
    assert bad["ok"] is False
    assert len(bad["invented"]) == 3
