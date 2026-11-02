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
    after = sorted(path.name for path in (root / "work").iterdir())
    assert after == before
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


def _grid(root: Path, *, score: float = 1.5) -> None:
    """A 2 s bar, with beats every half second, over the whole 60 s film."""
    music = read_json(root / "work/music.json")
    music["beats"] = [index * 0.5 for index in range(120)]
    write_json(root / "work/music.json", music)
    write_json(
        root / "work/music-deep.json",
        {
            "refined_tempo": {"primary_bpm": 120.0},
            "downbeats": [{"time": index * 2.0, "strength": 1.0} for index in range(30)],
            "bar_length_candidates": [{"beats_per_bar": 4, "score": score}],
            "sections": [],
        },
    )


def test_grid_tiers_lead_a_hit_by_a_frame():
    assert pacing.grid_tiers([48, 96], [12, 48], 1) == ([47, 95], [11, 47])
    assert pacing.grid_tiers([0], [], 1) == ([0], [])


def test_a_join_a_frame_before_a_downbeat_beats_a_nearer_beat():
    downbeats, beats = pacing.grid_tiers([100], [97], 1)
    moved = pacing.snap_joins(
        [97], total_frames=400, min_frames=24, reach=20, tiers=[[], [], downbeats, beats]
    )
    assert moved == [99]


def test_a_sung_line_still_beats_a_downbeat():
    moved = pacing.snap_joins([100], total_frames=400, min_frames=24, reach=20, tiers=[[92], [99]])
    assert moved == [92]


def test_split_points_stay_on_bars_and_keep_every_part_long_enough():
    bars = [48, 96, 144, 192, 240, 288]
    assert pacing.split_points(0, 300, bars, 96, 36) == [96, 192]
    assert pacing.split_points(0, 300, bars, 48, 36) == [48, 96, 144, 192, 240]
    assert pacing.split_points(0, 300, [], 48, 36) == []


def test_with_a_grid_joins_land_on_it_and_targets_are_written(tmp_path):
    root = _film(tmp_path)
    _grid(root)
    result = first_cut.suggest(root)
    suggested = EditDecisionList.model_validate(result["edit"])
    suggested.check_board(P.load_board(root))
    assert result["report"]["ok"] is True
    assert all(section.density_per_10s > 0 for section in suggested.sections)
    bars = {index * 48 - 1 for index in range(1, 31)}
    full = [
        shot.start_frame
        for shot in suggested.shots
        if 444 <= shot.start_frame < 888 and shot.start_frame != 444
    ]
    assert full and all(frame in bars for frame in full)


def test_no_trusted_grid_means_no_snap_to_it_and_no_crop_cuts(tmp_path):
    root = _film(tmp_path)
    _grid(root, score=1.02)
    suggested = EditDecisionList.model_validate(first_cut.suggest(root)["edit"])
    assert not any(shot.crops for shot in suggested.shots)


def test_crop_cuts_come_only_in_full_sections_and_stay_sharp(tmp_path):
    root = _film(tmp_path)
    _grid(root)
    result = first_cut.suggest(root)
    suggested = EditDecisionList.model_validate(result["edit"])
    crops = [(shot, crop) for shot in suggested.shots for crop in shot.crops]
    assert crops
    assert result["changes"]["crops_added"] == len(crops)
    for shot, crop in crops:
        assert crop.zoom <= edits.SOFT_CROP_ZOOM
        assert 444 <= shot.start_frame < 888
        assert (crop.frame + 1) % 48 == 0


def test_a_quiet_section_drops_a_crop_cut_and_can_hold(tmp_path):
    from mp3_to_videoclip.models import EditCrop

    root = _film(tmp_path)
    _grid(root)
    edit = edits.seed_edit(root)
    first = edit.shots[0]
    first.crops.append(EditCrop(frame=first.start_frame + 30, zoom=1.2))
    edits.save_edit(root, edit)
    result = first_cut.suggest(root)
    suggested = EditDecisionList.model_validate(result["edit"])
    assert suggested.shots[0].crops == []
    assert result["changes"]["crops_removed"] >= 1


def test_the_report_names_cuts_off_the_grid_and_just_after_it(tmp_path):
    root = _film(tmp_path)
    _grid(root)
    edit = edits.seed_edit(root)
    middle = next(shot for shot in edit.shots if 444 <= shot.start_frame < 888)
    earlier = edit.shots[edit.shots.index(middle) - 1]
    # 2 frames after a beat at 576, and 6 away from every beat at 582.
    for offset, code in (
        (578 - middle.start_frame, "late_cut"),
        (582 - middle.start_frame, "off_grid"),
    ):
        earlier.duration_frames += offset
        middle.start_frame += offset
        middle.duration_frames -= offset
        found = {item["code"] for item in edits.report(root, edit=edit)["warnings"]}
        assert code in found
        earlier.duration_frames -= offset
        middle.start_frame -= offset
        middle.duration_frames += offset


def test_every_section_gets_its_target_where_rounding_and_flooring_disagree(tmp_path):
    root = _film(tmp_path)
    _grid(root)
    music = read_json(root / "work/music.json")
    # 18.5625 s is frame 445.5: it rounds up to 446 and floors to 445.
    music["sections"][0]["end"] = 18.5625
    music["sections"][1]["start"] = 18.5625
    write_json(root / "work/music.json", music)
    material = edits.cut_material(root)
    assert all(section["target_per_10s"] for section in material["sections"])
    assert all(section["energy_word"] for section in material["sections"])
    suggested = EditDecisionList.model_validate(first_cut.suggest(root)["edit"])
    assert all(section.density_per_10s > 0 for section in suggested.sections)
