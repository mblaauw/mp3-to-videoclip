"""Edit-owned timing, coverage, the computed report and the draft API."""

from __future__ import annotations

from pathlib import Path

import pytest
from api_support import add_assets, api_client, make_api_project

from mp3_to_videoclip import edits, remotion
from mp3_to_videoclip import production as P
from mp3_to_videoclip.models import (
    EditAccent,
    EditDecisionList,
    EditMotion,
    EditSection,
    EditShot,
    EditText,
    EditTransition,
    Grade,
    Shot,
    Storyboard,
)
from mp3_to_videoclip.services import preview
from mp3_to_videoclip.storage import read_json, write_json


def _energetic_root(tmp_path: Path) -> Path:
    root = make_api_project(tmp_path)
    project = read_json(root / "project.json")
    project["duration"] = 10.0
    write_json(root / "project.json", project)
    framings = ["wide", "close_up", "detail", "medium"]
    board = Storyboard(
        aspect="16:9",
        fps=24,
        total_frames=240,
        shots=[
            Shot(
                id=f"s{index + 1:03d}",
                start_frame=index * 24,
                duration_frames=24,
                purpose=f"Beat {index}",
                image_prompt=f"SHOT-s{index + 1:03d} prompt",
                framing=framings[index % len(framings)],
                camera="hold",
            )
            for index in range(10)
        ],
    )
    write_json(root / P.STAGE_FILES["storyboard"], board.model_dump())
    add_assets(root)
    return root


def _energetic_edit() -> EditDecisionList:
    decisions = []
    for index in range(10):
        shot_id = f"s{index + 1:03d}"
        start = index * 24
        motion = EditMotion(type="hold")
        transition = EditTransition(type="cut")
        accents = []
        text = []
        if index == 0:
            motion = EditMotion(type="hold", reason="open on the first accent")
        elif index == 1:
            motion = EditMotion(
                type="push_in",
                **{"from": 1.0, "to": 1.08},
                reason="approach the reveal",
            )
            transition = EditTransition(
                type="whip_pan",
                frames=4,
                direction="left",
                reason="chorus entry",
            )
        elif index == 2:
            motion = EditMotion(
                type="pull_back",
                **{"from": 1.1, "to": 1.0},
                reason="release the section",
            )
            transition = EditTransition(
                type="dip_to_black",
                frames=4,
                reason="chapter break",
            )
            accents = [
                EditAccent(
                    frame=start + 4,
                    type="punch_in",
                    amount=1.05,
                    reason="first hard hit",
                )
            ]
            text = [
                EditText(
                    id="t1",
                    style="super",
                    text="OUT NOW",
                    in_frame=start,
                    out_frame=start + 24,
                    animation="type_on",
                    reason="date lands with the line",
                )
            ]
        elif index == 3:
            motion = EditMotion(type="hold", reason="let the image land")
        elif index == 4:
            motion = EditMotion(
                type="pan_right",
                **{"from": 1.08, "to": 1.08},
                reason="discover the second subject",
            )
            transition = EditTransition(
                type="slide",
                frames=4,
                direction="left",
                reason="list structure",
            )
            accents = [
                EditAccent(
                    frame=start + 6,
                    type="flash",
                    duration_frames=2,
                    reason="accent flash",
                )
            ]
        elif index == 5:
            motion = EditMotion(
                type="push_in",
                **{"from": 1.0, "to": 1.06},
                reason="intimacy",
            )
            text = [
                EditText(
                    id="t2",
                    style="lower_third",
                    text="ONE TAKE",
                    in_frame=start,
                    out_frame=start + 24,
                    animation="kinetic_words",
                    reason="words hit the rhythm",
                )
            ]
        elif index == 6:
            motion = EditMotion(
                type="pull_back",
                **{"from": 1.07, "to": 1.0},
                reason="reveal the room",
            )
            transition = EditTransition(
                type="push",
                frames=4,
                reason="graphic transition",
            )
        elif index == 7:
            motion = EditMotion(type="hold", reason="breath after the montage")
            accents = [
                EditAccent(
                    frame=start + 2,
                    type="light_leak",
                    duration_frames=8,
                    reason="memory warmth",
                )
            ]
        elif index == 8:
            motion = EditMotion(
                type="pan_left",
                **{"from": 1.08, "to": 1.08},
                reason="return to the room",
            )
            transition = EditTransition(
                type="fade",
                frames=4,
                reason="time passing",
            )
        else:
            motion = EditMotion(
                type="push_in",
                **{"from": 1.0, "to": 1.05},
                reason="land the last line",
            )
            transition = EditTransition(
                type="dip_to_white",
                frames=4,
                reason="end card arrival",
            )
            text = [
                EditText(
                    id="t3",
                    style="card",
                    text="14 NOV",
                    in_frame=start,
                    out_frame=start + 24,
                    animation="pop",
                    reason="closing date",
                )
            ]
        decisions.append(
            EditShot(
                shot_id=shot_id,
                start_frame=start,
                duration_frames=24,
                motion=motion,
                transition_in=transition,
                accents=accents,
                text=text,
            )
        )
    return EditDecisionList(
        sections=[
            EditSection(
                id="build",
                start_frame=0,
                end_frame=120,
                feel="build, close and restless",
                density_per_10s=8,
                techniques=["cut on accent", "push-in"],
            ),
            EditSection(
                id="release",
                start_frame=120,
                end_frame=240,
                feel="release, wide and bright chorus",
                density_per_10s=8,
                techniques=["pull-back", "flash frame"],
            ),
        ],
        shots=decisions,
        grade=Grade(preset="warm-night", strength=0.6),
    )


def test_seed_moves_timing_into_the_edit_and_guards_the_storyboard(tmp_path):
    root = make_api_project(tmp_path)
    edit = edits.seed_edit(root)
    assert (root / edits.EDIT).is_file()
    assert [(s.shot_id, s.start_frame) for s in edit.shots] == [
        (s.id, s.start_frame) for s in P.load_board(root).shots
    ]

    with pytest.raises(ValueError, match="edit.json owns timing"):
        P.update_shots(root, [{"id": "s001", "duration_frames": 10}])
    board, changed = P.update_shots(root, [{"id": "s001", "purpose": "New content"}])
    assert changed == ["s001"]
    assert board.shots[0].purpose == "New content"


def test_edit_reorders_and_retimes_the_effective_preview(tmp_path):
    root = _energetic_root(tmp_path)
    edit = _energetic_edit()
    # Put s002 first and s001 second; content is unchanged, order is edit-owned.
    first, second = edit.shots[0], edit.shots[1]
    edit.shots[0] = second.model_copy(update={"start_frame": 0, "transition_in": EditTransition()})
    edit.shots[1] = first.model_copy(update={"start_frame": 24})
    edits.save_edit(root, edit)
    payload = preview.player_input(root, "production")
    assert payload["durationInFrames"] == 240
    assert [shot["id"] for shot in payload["shots"][:2]] == ["s002", "s001"]
    assert payload["shots"][0]["start_frame"] == 0
    assert payload["shots"][1]["start_frame"] == 24
    assert payload["shots"][0]["edit"]["shot_id"] == "s002"
    assert payload["grade"]["preset"] == "warm-night"


def test_edit_report_flags_flashes_and_broken_transitions(tmp_path):
    root = _energetic_root(tmp_path)
    edit = _energetic_edit()
    first = edit.shots[0]
    edit.shots[0] = first.model_copy(
        update={
            "accents": [EditAccent(frame=frame, type="flash") for frame in (0, 6, 12, 18)],
            "transition_in": EditTransition(type="whip_pan", frames=0),
        }
    )
    edits.save_edit(root, edit)
    value = edits.report(root)
    codes = {finding["code"] for finding in value["hard"]}
    assert "flash_rate" in codes
    assert "transition_handle" in codes
    assert "transition_reason" in codes


def test_energetic_fixture_has_five_reasoned_techniques_and_no_hard_findings(tmp_path):
    root = _energetic_root(tmp_path)
    edits.save_edit(root, _energetic_edit())
    value = edits.report(root)
    assert value["ok"] is True, value["hard"]
    assert value["counts"]["hold_ratio"] < 0.5
    reasoned = [row["name"] for row in value["techniques"] if row["reasoned"]]
    assert len(reasoned) >= 5, reasoned
    assert {"push-in", "whip pan", "dip to black", "punch-in", "type-on"} <= set(reasoned)
    assert all(row["count"] > 0 for row in value["techniques"])
    # Hard cuts are the default; only named transitions can become repetitive.
    assert not any(warning["code"] == "transition_repetition" for warning in value["warnings"])


def test_mp4_compiled_input_carries_the_same_edit_and_grade_as_the_player(tmp_path):
    root = _energetic_root(tmp_path)
    edits.save_edit(root, _energetic_edit())
    assets = root / "work" / "remotion-assets"
    assets.mkdir(parents=True, exist_ok=True)
    compiled = remotion.compile_shots(P.resolved_assets(root), root / "work", assets)
    assert compiled[0]["grade"]["preset"] == "warm-night"
    assert compiled[0]["edit"]["shot_id"] == "s001"
    assert compiled[1]["edit"]["motion"]["type"] == "push_in"
    assert compiled[1]["edit"]["transition_in"]["type"] == "whip_pan"
    assert compiled[0]["image"].endswith(".jpg")


def test_coverage_gap_is_refused_before_it_can_reach_the_renderer(tmp_path):
    root = make_api_project(tmp_path)
    edit = edits.seed_edit(root)
    raw = edit.model_dump(by_alias=True)
    raw["shots"][0]["duration_frames"] -= 1
    with pytest.raises(ValueError, match="starts at|edit covers"):
        edits.save_edit(root, raw)


def test_edit_api_seeds_reports_and_saves(tmp_path):
    root = _energetic_root(tmp_path)
    client = api_client(tmp_path)
    before = client.get("/api/projects/production/edit").json()
    assert before["present"] is False
    assert before["report"]["hard"] == []

    seeded = client.post("/api/projects/production/edit/seed", json={})
    assert seeded.status_code == 200
    assert seeded.json()["present"] is True

    payload = _energetic_edit().model_dump(by_alias=True)
    saved = client.put("/api/projects/production/edit", json={"edit": payload})
    assert saved.status_code == 200
    assert saved.json()["report"]["ok"] is True
    assert read_json(root / edits.EDIT)["shots"][1]["motion"]["type"] == "push_in"


def test_cut_summary_names_sections_and_labels_every_decision(tmp_path):
    from mp3_to_videoclip.domain import music_notes

    root = _energetic_root(tmp_path)
    write_json(
        root / "work" / "music.json",
        {
            "duration": 10.0,
            "sections": [
                {"start": 0.0, "end": 5.0, "label": "low"},
                {"start": 5.0, "end": 10.0, "label": "high"},
            ],
        },
    )
    music_notes.save(
        root,
        {"sections": [{"start": 0.0, "name": "Opening"}, {"start": 5.0, "name": "Chorus"}]},
    )
    edits.save_edit(root, _energetic_edit())

    value = edits.cut_summary(root)
    assert [section["name"] for section in value["sections"]] == ["Opening", "Chorus"]
    assert value["present"] is True
    assert value["edit"]["schema_version"] == 1
    shots = {shot["shot_id"]: shot for shot in value["shots"]}
    assert shots["s001"]["transition"]["label"] == "Cut"
    assert shots["s001"]["motion"]["label"] == "Hold"
    assert shots["s002"]["transition"]["label"] == "Whip pan 4 f"
    assert shots["s002"]["transition"]["reason"] == "chorus entry"
    assert shots["s002"]["motion"]["label"] == "Push in"
    assert shots["s002"]["reason"] == "chorus entry"
    assert shots["s008"]["accents"][0]["label"] == "Light leak"
    assert shots["s008"]["accents"][0]["reason"] == "memory warmth"
    assert shots["s010"]["text"][0]["text"] == "14 NOV"
    assert shots["s002"]["section_name"] == "Opening"
    assert shots["s010"]["section_name"] == "Chorus"


def test_storyboard_history_restores_the_previous_writes(tmp_path):
    root = make_api_project(tmp_path)
    original = P.load_board(root).shots[0].purpose
    P.update_shots(root, [{"id": "s001", "purpose": "First change"}])
    P.update_shots(root, [{"id": "s001", "purpose": "Second change"}])

    with api_client(tmp_path) as client:
        listed = client.get("/api/projects/production/history/storyboard")
        assert listed.status_code == 200
        assert len(listed.json()["snapshots"]) >= 2
        first = client.post("/api/projects/production/history/storyboard/restore", json={})
        assert first.status_code == 200, first.text
        assert P.load_board(root).shots[0].purpose == "First change"
        second = client.post("/api/projects/production/history/storyboard/restore", json={})
        assert second.status_code == 200, second.text
        assert P.load_board(root).shots[0].purpose == original

    refused = None
    with api_client(tmp_path) as client:
        refused = client.post("/api/projects/production/history/nope/restore", json={})
    assert refused.status_code == 400


def test_edit_history_restores_the_previous_cut(tmp_path):
    root = _energetic_root(tmp_path)
    first = _energetic_edit()
    edits.save_edit(root, first)
    second = first.model_copy(deep=True)
    second.shots[0] = second.shots[0].model_copy(
        update={"motion": EditMotion(type="hold", reason="a later correction")}
    )
    edits.save_edit(root, second)

    with api_client(tmp_path) as client:
        restored = client.post("/api/projects/production/history/edit/restore", json={})
    assert restored.status_code == 200, restored.text
    saved = edits.load_edit(root)
    assert saved is not None
    assert saved.shots[0].motion.reason == "open on the first accent"


def test_split_preview_carries_native_pane_sources(tmp_path):
    root = make_api_project(tmp_path)
    add_assets(root)
    board = P.load_board(root)
    raw = board.model_dump()
    raw["shots"][2] = {
        "id": "s003",
        "start_frame": 24,
        "duration_frames": 12,
        "kind": "split",
        "purpose": "two reactions at once",
        "panes": [
            {"shot_id": "s001", "crop": {"zoom": 1.1, "x": 0.4, "y": 0.5}},
            {"shot_id": "s002", "crop": {"zoom": 1, "x": 0.5, "y": 0.5}},
        ],
        "camera": "hold",
    }
    write_json(root / P.STAGE_FILES["storyboard"], raw)
    edit = edits.seed_edit(root)
    payload = preview.player_input(root, "production")
    split = next(shot for shot in payload["shots"] if shot["id"] == "s003")
    assert split["edit"]["shot_id"] == edit.shots[2].shot_id
    assert len(split["split_panes"]) == 2
    assert all(pane["src"] for pane in split["split_panes"])

    assets = root / "work" / "remotion-assets"
    assets.mkdir(parents=True, exist_ok=True)
    compiled = remotion.compile_shots(P.resolved_assets(root), root / "work", assets)
    compiled_split = next(shot for shot in compiled if shot["id"] == "s003")
    assert len(compiled_split["split_panes"]) == 2
    assert all(pane["image"] for pane in compiled_split["split_panes"])


def test_a_density_warning_needs_a_pace_target_to_compare_against(tmp_path):
    root = _energetic_root(tmp_path)
    edit = _energetic_edit()
    sections = [section.model_copy(update={"density_per_10s": 0}) for section in edit.sections]
    assert sections

    def density(value):
        return [
            finding
            for finding in edits.report(root, edit=value)["warnings"]
            if finding["code"] == "density_target"
        ]

    assert not density(edit.model_copy(update={"sections": sections}))
    far = [section.model_copy(update={"density_per_10s": 99}) for section in edit.sections]
    assert density(edit.model_copy(update={"sections": far}))


def _codes(root, edit):
    return {item["code"] for item in edits.report(root, edit=edit)["warnings"]}


def test_report_flags_a_long_still_shot_and_a_section_with_no_feel(tmp_path):
    root = _energetic_root(tmp_path)
    edit = edits.seed_edit(root)
    shots = [shot.model_copy(update={"motion": EditMotion(type="hold")}) for shot in edit.shots]
    long_shot = shots[:1] + []
    long_shot[0] = long_shot[0].model_copy(update={"duration_frames": 360})
    board = P.load_board(root)
    board = board.model_copy(
        update={
            "total_frames": 360,
            "shots": [board.shots[0].model_copy(update={"duration_frames": 360})],
        }
    )
    still = EditDecisionList(
        sections=[EditSection(id="a", start_frame=0, feel="unreviewed")],
        shots=long_shot,
    )
    assert {"long_static_shot", "section_no_feel"} <= {
        item["code"] for item in edits.report(root, edit=still, board=board)["warnings"]
    }


def test_report_flags_the_same_travel_again_and_again_but_not_varied_travel(tmp_path):
    root = _energetic_root(tmp_path)
    edit = edits.seed_edit(root)

    def pushed(to):
        return EditMotion(type="push_in", **{"from": 1.0, "to": to})

    same = edit.model_copy(
        update={"shots": [s.model_copy(update={"motion": pushed(1.08)}) for s in edit.shots]}
    )
    assert "travel_repetition" in _codes(root, same)
    varied = edit.model_copy(
        update={
            "shots": [
                s.model_copy(update={"motion": pushed(1.03 + index * 0.01)})
                for index, s in enumerate(edit.shots)
            ]
        }
    )
    assert "travel_repetition" not in _codes(root, varied)


def test_cut_material_offers_sections_lines_and_changes_in_frames(tmp_path):
    from mp3_to_videoclip.domain import lyric_timing

    root = _energetic_root(tmp_path)
    write_json(
        root / "work/music.json",
        {
            "duration": 10.0,
            "sections": [{"start": 0.0, "end": 10.0, "energy": 0.5, "label": "unreviewed"}],
            "candidate_changes": [{"time": 4.0, "spectral_change": 0.7}],
            "beats": [0.5, 1.0],
        },
    )
    write_json(
        root / "work/lyrics.json",
        {"provider": "manual", "model": "text", "segments": [], "lines": ["[Hook]", "one"]},
    )
    lyric_timing.save(root, {"lines": [{"index": 1, "start": 2.0, "source": "auto"}]}, 10.0)
    material = edits.cut_material(root)
    assert material["sections"][0]["end_frame"] == 240
    assert material["lines"] == [{"frame": 48, "text": "one", "source": "auto"}]
    assert material["changes"][0]["frame"] == 96
    assert material["beats"] == [12, 24]


def test_crop_cuts_are_bounded_counted_and_absent_when_unused(tmp_path):
    from mp3_to_videoclip.models import EditCrop

    root = _energetic_root(tmp_path)
    edit = edits.seed_edit(root)
    assert "crops" not in edit.shots[0].model_dump(by_alias=True)
    shots = list(edit.shots)
    start = shots[0].start_frame
    shots[0] = shots[0].model_copy(
        update={"crops": [EditCrop(frame=start + 6, zoom=1.5, x=0.2, y=0.8)]}
    )
    cropped = edit.model_copy(update={"shots": shots})
    report = edits.report(root, edit=cropped)
    assert "crop_soft" in {item["code"] for item in report["warnings"]}
    baseline = edits.report(root, edit=edit)
    assert report["sections"][0]["cuts"] == baseline["sections"][0]["cuts"] + 1
    with pytest.raises(ValueError, match="outside"):
        EditShot(
            shot_id="s001",
            start_frame=0,
            duration_frames=24,
            crops=[EditCrop(frame=24, zoom=1.2)],
        )
    with pytest.raises(ValueError, match="in order"):
        EditShot(
            shot_id="s001",
            start_frame=0,
            duration_frames=24,
            crops=[EditCrop(frame=12, zoom=1.2), EditCrop(frame=6, zoom=1.2)],
        )
    with pytest.raises(ValueError):
        EditCrop(frame=6, zoom=1.7)


def test_a_film_look_is_bounded_and_absent_when_unset():
    from mp3_to_videoclip.models import FilmLook

    assert "look" not in Grade().model_dump()
    assert Grade(look=FilmLook(grain=0.4)).model_dump()["look"]["grain"] == 0.4
    with pytest.raises(ValueError):
        FilmLook(grain=1.5)


def test_the_editors_tool_reads_a_cut_in_pages(tmp_path):
    root = _energetic_root(tmp_path)
    edits.seed_edit(root)
    first = edits.tool_page(root, 0, 4)
    assert [shot["shot_id"] for shot in first["shots"]] == ["s001", "s002", "s003", "s004"]
    assert first["next_first"] == 4 and "report" in first and first["shot_total"] == 10
    rest = edits.tool_page(root, 8, 4)
    assert len(rest["shots"]) == 2 and "next_first" not in rest and "report" not in rest


def test_patching_shots_changes_only_what_it_names_and_cant_retime(tmp_path):
    root = _energetic_root(tmp_path)
    before = edits.seed_edit(root)
    result = edits.patch_shots(
        root,
        [
            {
                "shot_id": "s002",
                "motion": {"type": "push_in", "from": 1.0, "to": 1.04, "anchor": [0.2, 0.7]},
                "crops": [{"frame": before.shots[1].start_frame + 6, "zoom": 1.2}],
            }
        ],
    )
    assert result["saved"] == 1
    after = edits.load_edit(root)
    assert after.shots[1].motion.anchor == [0.2, 0.7] and len(after.shots[1].crops) == 1
    assert after.shots[0] == before.shots[0]
    with pytest.raises(ValueError, match="can't be changed"):
        edits.patch_shots(root, [{"shot_id": "s002", "start_frame": 3}])
    with pytest.raises(ValueError, match="no shot"):
        edits.patch_shots(root, [{"shot_id": "nope", "crops": []}])
    with pytest.raises(ValueError):
        edits.patch_shots(root, [{"shot_id": "s002", "crops": [{"frame": 9999, "zoom": 1.2}]}])
    assert edits.load_edit(root).shots[1].motion.anchor == [0.2, 0.7]
