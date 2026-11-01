"""Timed lines as layers inside their shots, and as SRT and VTT files."""

from __future__ import annotations

from pathlib import Path

import pytest
from api_support import api_client
from test_first_cut import _film

from mp3_to_videoclip import captions, edits
from mp3_to_videoclip import production as P
from mp3_to_videoclip.domain import lyric_timing
from mp3_to_videoclip.models import EditDecisionList
from mp3_to_videoclip.storage import write_json


def _timed(root: Path, *times) -> None:
    lines = [f"Line {index}" for index in range(len(times))]
    write_json(root / "work/lyrics.json", {"lines": lines})
    lyric_timing.save(
        root,
        {
            "lines": [
                {"index": index, "start": start, "end": end, "source": "tapped"}
                for index, (start, end) in enumerate(times)
            ]
        },
        60,
    )


@pytest.fixture
def film(tmp_path):
    root = _film(tmp_path)
    edits.seed_edit(root)
    # Shots are 6 s long: joins at 6 s, 12 s, 18 s and so on.
    _timed(root, (1.0, 3.0), (5.0, None), (6.5, 7.0), (50.0, None))
    return root


def _layers(root: Path) -> list:
    edit = edits.load_edit(root)
    return [item for shot in edit.shots for item in shot.text]


def test_each_timed_line_gets_a_layer_inside_its_shot(film):
    report = edits.apply_captions(film, mode="all")
    assert report["timed_lines"] == 4
    edit = edits.load_edit(film)
    EditDecisionList.model_validate(edit.model_dump(by_alias=True))
    first = edit.shots[0].text[0]
    assert (first.id, first.in_frame, first.out_frame, first.style) == ("cap-0", 24, 72, "lyric")
    for shot in edit.shots:
        for item in shot.text:
            assert shot.start_frame <= item.in_frame
            assert item.out_frame <= shot.start_frame + shot.duration_frames


def test_a_line_with_no_end_stops_before_the_next_one(film):
    lines = captions.timed_lines(film, 24, 1440)
    assert lines[1]["end"] == round(6.5 * 24) - captions.GAP_FRAMES


def test_a_short_line_is_held_a_second_and_a_long_one_six(tmp_path):
    root = _film(tmp_path)
    _timed(root, (1.0, 1.1), (20.0, 40.0), (50.0, None))
    lines = captions.timed_lines(root, 24, 1440)
    assert lines[0]["end"] - lines[0]["start"] == 24
    assert lines[1]["end"] - lines[1]["start"] == 144


def test_a_line_across_a_join_continues_as_a_second_layer(tmp_path):
    root = _film(tmp_path)
    edits.seed_edit(root)
    _timed(root, (5.0, 8.0))
    edits.apply_captions(root, mode="all")
    edit = edits.load_edit(root)
    assert [item.id for item in edit.shots[0].text] == ["cap-0"]
    assert [item.id for item in edit.shots[1].text] == ["cap-0-2"]
    assert edit.shots[0].text[0].out_frame == edit.shots[1].text[0].in_frame


def test_a_tiny_tail_past_a_join_is_not_drawn(tmp_path):
    root = _film(tmp_path)
    edits.seed_edit(root)
    _timed(root, (5.0, 6.2))
    edits.apply_captions(root, mode="all")
    assert [item.id for item in _layers(root)] == ["cap-0"]


def test_captions_replace_each_other_and_off_removes_them(film):
    edits.apply_captions(film, mode="all")
    assert len(_layers(film)) >= 4
    edits.apply_captions(film, [0])
    assert [item.id for item in _layers(film)] == ["cap-0"]
    edits.apply_captions(film, mode="off")
    assert _layers(film) == []


def test_named_sections_choose_only_their_lines(film):
    write_json(
        film / "work/section-map.json",
        {"sections": [{"start": 0.0, "name": "Verse"}, {"start": 45.0, "name": "Big Hook"}]},
    )
    edits.apply_captions(film, mode="named")
    assert {item.id.split("-")[1] for item in _layers(film)} == {"3"}


def test_a_cut_without_captions_saves_as_before(film):
    edit = edits.load_edit(film)
    before = edit.model_dump(by_alias=True)
    edits.apply_captions(film, mode="off")
    assert edits.load_edit(film).model_dump(by_alias=True) == before


def test_too_many_lines_in_one_shot_is_refused_by_name(tmp_path):
    root = _film(tmp_path)
    edits.seed_edit(root)
    _timed(root, *[(0.1 + index * 0.2, None) for index in range(25)])
    with pytest.raises(ValueError, match="s001 would carry 25"):
        edits.apply_captions(root, mode="all")


def test_unknown_lines_and_modes_are_refused(film):
    with pytest.raises(ValueError):
        edits.apply_captions(film, [99])
    with pytest.raises(ValueError):
        edits.apply_captions(film, mode="some")
    with pytest.raises(ValueError):
        edits.apply_captions(film)


def test_srt_and_vtt_carry_every_timed_line(film):
    edits.apply_captions(film, [0])
    lines = captions.timed_lines(film, 24, 1440)
    srt = captions.srt(lines, 24)
    assert srt.startswith("1\n00:00:01,000 --> 00:00:03,000\nLine 0\n")
    assert "4\n00:00:50,000" in srt
    vtt = captions.vtt(lines, 24)
    assert vtt.startswith("WEBVTT\n")
    assert "00:00:01.000 --> 00:00:03.000\nLine 0\n" in vtt


def test_sidecars_are_written_beside_a_final_and_never_replace_a_file(film, tmp_path):
    output = film / "renders/film-final-v001.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    project = P.load_project(film, verify_source=False)
    assert captions.sidecars_for(film, output, project) == [
        "film-final-v001.srt",
        "film-final-v001.vtt",
    ]
    (film / "renders/film-final-v001.srt").write_text("kept")
    assert captions.sidecars_for(film, output, project) == []
    assert (film / "renders/film-final-v001.srt").read_text() == "kept"


def test_two_layers_at_once_are_named(film):
    from mp3_to_videoclip.models import EditText

    edit = edits.load_edit(film)
    edit.shots[0].text.extend(
        [
            EditText(id="a", text="One", in_frame=10, out_frame=50),
            EditText(id="b", text="Two", in_frame=40, out_frame=60),
        ]
    )
    edits.save_edit(film, edit)
    codes = {item["code"] for item in edits.report(film)["warnings"]}
    assert "caption_overlap" in codes


def test_the_routes(film, tmp_path):
    with api_client(tmp_path) as client:
        base = f"/api/projects/{film.name}"
        saved = client.post(f"{base}/edit/captions", json={"mode": "all"}).json()
        assert saved["captions"] >= 4 and saved["timed_lines"] == 4
        srt = client.get(f"{base}/captions.srt")
        assert srt.status_code == 200 and "Line 0" in srt.text
        assert client.get(f"{base}/captions.vtt").text.startswith("WEBVTT")
        assert client.get(f"{base}/captions.txt").status_code == 404
        refused = client.post(f"{base}/edit/captions", json={"mode": "some"})
        assert refused.status_code == 400
