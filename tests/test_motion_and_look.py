"""Curves, ramps, impulses, look options and word times, without moving an existing hash."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mp3_to_videoclip import captions, first_cut
from mp3_to_videoclip.domain import lyric_timing
from mp3_to_videoclip.lyric_tools import match_words
from mp3_to_videoclip.models import (
    EditAccent,
    EditDecisionList,
    EditMotion,
    EditShot,
    EditText,
    FilmLook,
)


def test_unused_fields_stay_out_so_existing_cuts_hash_the_same():
    motion = EditMotion().model_dump(by_alias=True)
    assert "ramp" not in motion
    assert "direction" not in EditAccent(frame=1, type="flash").model_dump()
    text = EditText(id="a", text="hi", in_frame=0, out_frame=4).model_dump()
    assert not {"decoration", "words"} & set(text)
    assert FilmLook(grain=0.2).model_dump() == {"grain": 0.2, "weave": 0, "drift": 0}


def test_a_ramp_must_land_inside_its_shot():
    ramp = {"type": "push_in", "from": 1.0, "to": 1.1, "ramp": {"frame": 10, "share": 0.7}}
    assert EditShot(shot_id="s", start_frame=0, duration_frames=24, motion=ramp).motion.ramp
    with pytest.raises(ValidationError, match="outside shot"):
        EditShot(shot_id="s", start_frame=0, duration_frames=8, motion=ramp)
    with pytest.raises(ValidationError):
        EditMotion(**{**ramp, "ramp": {"frame": 10, "share": 1.2}})


def test_an_impulse_has_its_own_bounds():
    assert EditAccent(frame=1, type="impulse", amount=1.05, duration_frames=8, direction="up")
    for bad in (
        {"amount": 1.15, "duration_frames": 8},
        {"amount": 1.05, "duration_frames": 1},
        {"amount": 1.05, "duration_frames": 13},
    ):
        with pytest.raises(ValidationError, match="impulse"):
            EditAccent(frame=1, type="impulse", **bad)
    with pytest.raises(ValidationError, match="only an impulse"):
        EditAccent(frame=1, type="flash", direction="up")


def test_a_word_must_land_inside_its_text():
    assert EditText(
        id="a", text="hi", in_frame=2, out_frame=6, words=[{"text": "hi", "in_frame": 2}]
    )
    with pytest.raises(ValidationError, match="inside its text"):
        EditText(id="a", text="hi", in_frame=2, out_frame=6, words=[{"text": "hi", "in_frame": 6}])


MATERIAL = {"grid_trusted": True, "downbeats": [10, 50, 96, 150], "beats": []}


def test_a_push_in_lands_on_the_downbeat_nearest_its_middle():
    assert first_cut._landing(MATERIAL, 60, 130) == 96
    assert first_cut._landing(MATERIAL, 11, 49) is None


def test_only_a_trusted_grid_gives_a_section_its_downbeat():
    assert first_cut._strong_downbeat(MATERIAL, 96) == 96
    assert first_cut._strong_downbeat(MATERIAL, 70) is None
    assert first_cut._strong_downbeat({**MATERIAL, "grid_trusted": False}, 96) is None


def test_whole_lines_get_their_words_and_a_gap_gets_none():
    rows = [
        {"index": 0, "text": "Hello there", "tag": False},
        {"index": 1, "text": "Missing words here", "tag": False},
    ]
    tokens = [
        {"text": " hello", "start": 1.0, "end": 1.2},
        {"text": " there", "start": 1.3, "end": 1.6},
        {"text": " missing", "start": 2.0, "end": 2.2},
    ]
    found = match_words(rows, tokens)
    assert [word["start"] for word in found[0]] == [1.0, 1.3]
    assert found[0][0]["text"] == "Hello"
    assert 1 not in found


def test_a_tapped_line_keeps_no_words_and_an_auto_line_does(tmp_path):
    from mp3_to_videoclip.storage import write_json

    write_json(tmp_path / "work/lyrics.json", {"lines": ["One two", "Three four"]})
    words = [{"text": "One", "start": 1.0, "end": 1.2}, {"text": "two", "start": 1.3, "end": 1.5}]
    view = lyric_timing.save(
        tmp_path,
        {
            "lines": [
                {"index": 0, "start": 1.0, "end": 2.0, "source": "auto", "words": words},
                {"index": 1, "start": 3.0, "end": 4.0, "source": "tapped", "words": words},
            ]
        },
        10.0,
    )
    assert view["lines"][0]["words"][1]["start"] == 1.3
    assert "words" not in view["lines"][1]


def _edit(*lengths) -> EditDecisionList:
    shots, cursor = [], 0
    for index, length in enumerate(lengths):
        shots.append(EditShot(shot_id=f"s{index}", start_frame=cursor, duration_frames=length))
        cursor += length
    return EditDecisionList(shots=shots)


def test_a_timed_caption_lands_word_by_word_and_a_crossing_one_fades():
    words = [{"text": "One", "in_frame": 5}, {"text": "two", "in_frame": 12}]
    line = {"index": 0, "text": "One two", "start": 5, "end": 20, "words": words}
    layers = captions.caption_layers(_edit(48), [line], None, 24)
    assert layers["s0"][0].animation == "kinetic_words"
    assert layers["s0"][0].words[1].in_frame == 12
    crossing = captions.caption_layers(_edit(10, 38), [line], None, 24)
    assert crossing["s0"][0].animation == "fade" and not crossing["s0"][0].words
    plain = {"index": 0, "text": "One two", "start": 5, "end": 20}
    assert captions.caption_layers(_edit(48), [plain], None, 24)["s0"][0].animation == "fade"
