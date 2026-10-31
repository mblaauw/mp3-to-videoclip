"""Suggest a cut: deterministic, covers every shot, and writes nothing."""

from __future__ import annotations

from pathlib import Path

import pytest
from api_support import api_client, make_api_project

from mp3_to_videoclip import edits, first_cut, pacing
from mp3_to_videoclip import production as P
from mp3_to_videoclip.domain import lyric_timing
from mp3_to_videoclip.models import EditDecisionList, Shot, Storyboard
from mp3_to_videoclip.storage import read_json, write_json


def _film(tmp_path: Path) -> Path:
    root = make_api_project(tmp_path)
    project = read_json(root / "project.json")
    project["duration"] = 60.0
    write_json(root / "project.json", project)
    framings = ["wide", "close_up", "medium", "detail"]
    write_json(
        root / "work/storyboard.json",
        Storyboard(
            aspect="16:9",
            fps=24,
            total_frames=1440,
            shots=[
                Shot(
                    id=f"s{index + 1:03d}",
                    start_frame=index * 144,
                    duration_frames=144,
                    purpose=f"Beat {index}",
                    image_prompt=f"SHOT-s{index + 1:03d} prompt",
                    framing=framings[index % 4],
                    camera="zoom_in",
                )
                for index in range(10)
            ],
        ).model_dump(),
    )
    write_json(
        root / "work/music.json",
        {
            "duration": 60.0,
            "sections": [
                {"start": 0.0, "end": 18.5, "energy": 0.1, "label": "unreviewed"},
                {"start": 18.5, "end": 37.0, "energy": 0.8, "label": "unreviewed"},
                {"start": 37.0, "end": 60.0, "energy": 0.2, "label": "unreviewed"},
            ],
        },
    )
    write_json(
        root / "work/lyrics.json",
        {"provider": "manual", "model": "text", "segments": [], "lines": ["[Hook]", "one"]},
    )
    lyric_timing.save(root, {"lines": [{"index": 1, "start": 11.0, "source": "auto"}]}, 60.0)
    return root


def test_joins_snap_to_the_strongest_evidence_within_reach():
    moved = pacing.snap_joins(
        [100, 200], total_frames=400, min_frames=24, reach=20, tiers=[[110], [195]]
    )
    assert moved == [110, 195]


def test_a_snap_never_leaves_a_shot_too_short_or_crosses_a_neighbour():
    moved = pacing.snap_joins([100, 130], total_frames=400, min_frames=24, reach=40, tiers=[[120]])
    assert moved[1] - moved[0] >= 24 and moved[0] >= 24


def test_suggestion_covers_every_shot_and_writes_nothing(tmp_path):
    root = _film(tmp_path)
    before = sorted(path.name for path in (root / "work").iterdir())
    result = first_cut.suggest(root)
    assert sorted(path.name for path in (root / "work").iterdir()) == before
    suggested = EditDecisionList.model_validate(result["edit"])
    suggested.check_board(P.load_board(root))
    assert result["report"]["ok"] is True
    assert [shot.shot_id for shot in suggested.shots] == [s.id for s in P.load_board(root).shots]


def test_suggestion_is_deterministic(tmp_path):
    root = _film(tmp_path)
    assert first_cut.suggest(root)["edit"] == first_cut.suggest(root)["edit"]


def test_suggestion_moves_joins_onto_sections_and_lines(tmp_path):
    root = _film(tmp_path)
    suggested = EditDecisionList.model_validate(first_cut.suggest(root)["edit"])
    starts = {shot.start_frame for shot in suggested.shots}
    assert 444 in starts  # the section at 18.5 s, from a join at 432
    assert 262 in starts  # just before the line at 11 s, from a join at 288


def test_suggestion_varies_travel_and_writes_section_feels(tmp_path):
    root = _film(tmp_path)
    result = first_cut.suggest(root)
    codes = {item["code"] for item in result["report"]["warnings"]}
    assert "travel_repetition" not in codes and "section_no_feel" not in codes
    assert "motion_repetition" not in codes
    suggested = EditDecisionList.model_validate(result["edit"])
    assert len({shot.motion.to_scale for shot in suggested.shots}) > 1
    assert "quiet" in suggested.sections[0].feel and "full" in suggested.sections[1].feel


def test_suggestion_marks_the_loud_arrival_and_the_drop_away(tmp_path):
    root = _film(tmp_path)
    suggested = EditDecisionList.model_validate(first_cut.suggest(root)["edit"])
    punches = [a for shot in suggested.shots for a in shot.accents if a.type == "punch_in"]
    assert [accent.frame for accent in punches] == [444]
    fades = [shot for shot in suggested.shots if shot.transition_in.type == "fade"]
    assert [shot.start_frame for shot in fades] == [888]
    assert fades[0].transition_in.reason


def test_text_and_cards_keep_their_own_motion(tmp_path):
    root = _film(tmp_path)
    edit = edits.seed_edit(root)
    from mp3_to_videoclip.models import EditText

    shots = list(edit.shots)
    shots[4] = shots[4].model_copy(
        update={
            "text": [
                EditText(
                    id="t1",
                    text="words",
                    in_frame=shots[4].start_frame + 40,
                    out_frame=shots[4].start_frame + 100,
                )
            ]
        }
    )
    edits.save_edit(root, edit.model_copy(update={"shots": shots}))
    suggested = EditDecisionList.model_validate(first_cut.suggest(root)["edit"])
    assert suggested.shots[4].text and suggested.shots[4].motion == shots[4].motion


def test_api_suggests_without_saving_and_the_film_stays_unedited(tmp_path):
    root = _film(tmp_path)
    with api_client(tmp_path) as client:
        response = client.post("/api/projects/production/edit/suggest", json={})
    assert response.status_code == 200, response.text
    assert response.json()["changes"]["joins_moved"] > 0
    assert not (root / "work/edit.json").exists()


@pytest.mark.parametrize("bad", [True, 1.5])
def test_snap_refuses_bad_input(bad):
    with pytest.raises(pacing.PacingError):
        pacing.snap_joins([bad], total_frames=100, min_frames=2, reach=2, tiers=[])
