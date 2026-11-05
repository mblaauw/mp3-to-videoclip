"""Cues under the speech: a layer on the film's sound that moves no clock and no hash."""

from __future__ import annotations

import wave

import numpy as np
import pytest
from test_story_film import make_film, script_for, tone
from test_voice import film as song_film  # noqa: F401  (a song film with real audio)

from mp3_to_videoclip import audio as music
from mp3_to_videoclip import narration, narration_timing, sound, voice
from mp3_to_videoclip import production as P
from mp3_to_videoclip.production import soundtrack
from mp3_to_videoclip.storage import file_hash, read_json


def _rms(path, start, end):
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        handle.setpos(int(start * rate))
        data = np.frombuffer(handle.readframes(int((end - start) * rate)), dtype="<i2")
    return float(np.sqrt(np.mean((data / 32768.0) ** 2)))


@pytest.fixture
def story(tmp_path):
    root = make_film(tmp_path)
    script = script_for(root)
    soundtrack.ensure_spec(root, script)
    for line in script.lines[:3]:
        narration.import_take(root, line.id, tone(tmp_path / f"{line.id}.wav", 1.5), follow=False)
    soundtrack.build(root)
    return root, script


def test_a_film_without_cues_keeps_its_sound_byte_for_byte(story):
    root, _ = story
    project = P.load_project(root)
    before = P.film_audio(root, project)
    assert sound.read(root) == {"version": 1, "cues": []}
    sound.set_cues(root, [{"id": "bed", "kind": "music", "prompt": "a bed"}])
    assert P.film_audio(root, project) == before
    assert voice.audio_version(root, project) is None
    assert sound.report(root)["notes"][0]["code"] == "cue_silent"


def test_a_cue_is_validated_and_keeps_its_versions_across_list_edits(story, tmp_path):
    root, script = story
    first = script.lines[0].id
    with pytest.raises(ValueError, match="short lowercase id"):
        sound.set_cues(root, [{"id": "Bed!"}])
    with pytest.raises(ValueError, match="one of music"):
        sound.set_cues(root, [{"id": "x", "kind": "voice"}])
    with pytest.raises(ValueError, match="no line"):
        sound.set_cues(root, [{"id": "x", "start": {"line": "nope"}}])
    with pytest.raises(ValueError, match="name each cue once"):
        sound.set_cues(root, [{"id": "x"}, {"id": "x"}])
    sound.set_cues(root, [{"id": "rain", "kind": "ambience", "start": {"line": first}, "end": {"line": first}}])  # fmt: skip
    cue = sound.import_sound(root, "rain", tone(tmp_path / "rain.wav", 2.0))
    assert cue["selected"] == 1 and cue["versions"][0]["source"] == "upload"
    # The list is rewritten with the same id: the bought or brought sound stays.
    sound.set_cues(root, [{"id": "rain", "kind": "ambience", "prompt": "rain", "gain_db": -20}])
    kept = sound.read(root)["cues"][0]
    assert kept["selected"] == 1 and kept["gain_db"] == -20.0 and len(kept["versions"]) == 1
    with pytest.raises(ValueError, match="no version 9"):
        sound.select(root, "rain", 9)
    sound.select(root, "rain", None)
    assert sound.read(root)["cues"][0]["selected"] is None


def test_a_cue_on_lines_follows_the_takes_and_ducks_under_them(story, tmp_path):
    root, script = story
    ids = [line.id for line in script.lines]
    sound.set_cues(root, [{"id": "room", "kind": "effect", "loop": True, "start": {"line": ids[1]}, "end": {"line": ids[2]}, "gain_db": -12, "duck_db": -20}])  # fmt: skip
    sound.import_sound(root, "room", tone(tmp_path / "room.wav", 0.5, frequency=2000.0))
    project = P.load_project(root)
    rows = {row["id"]: row for row in narration_timing.layout(root)}
    start, end = sound.span_seconds(project, sound.read(root)["cues"][0], list(rows.values()))
    assert start == rows[ids[1]]["start"]
    assert end == rows[ids[2]]["end"] + rows[ids[2]]["pause_after"]
    base = soundtrack.current(root)
    mixed = P.film_audio(root, project)
    assert mixed.name.startswith("sound-") and voice.audio_version(root, project)
    layer = voice._decode(mixed, 2) - voice._decode(base, 2)
    rate = music.SAMPLE_RATE

    def level(first: float, last: float) -> float:
        return float(np.sqrt(np.mean(np.square(layer[round(first * rate) : round(last * rate)]))))

    spoken = rows[ids[2]]
    assert level(rows[ids[0]]["start"], rows[ids[0]]["end"]) < 1e-4  # before the cue: nothing
    in_line = level(spoken["start"] + 0.4, spoken["end"] - 0.2)
    in_pause = level(spoken["end"] + 0.4, spoken["end"] + spoken["pause_after"])
    assert in_pause > 0.05 and in_line < in_pause * 0.2  # ducked 20 dB under the line
    # A longer take of the line before moves the cue with it.
    before_key = mixed.name
    narration.import_take(root, ids[0], tone(tmp_path / "long.wav", 3.0))
    narration.keep(root, ids[0], 2)
    later = {row["id"]: row for row in narration_timing.layout(root)}
    assert later[ids[1]]["start"] > rows[ids[1]]["start"]
    again = P.film_audio(root, P.load_project(root))
    assert again.name != before_key
    receipt = read_json(again.with_suffix(".json"))
    assert receipt["cues"] == ["room"] and receipt["layer_scaled"] is False


def test_a_cue_past_the_end_is_cut_and_reported(story, tmp_path):
    root, _ = story
    project = P.load_project(root)
    last = project.total_frames
    sound.set_cues(root, [{"id": "sting", "kind": "effect", "start": {"frame": last - 12}, "end": {"frame": -1}, "loop": False}])  # fmt: skip
    sound.import_sound(root, "sting", tone(tmp_path / "sting.wav", 4.0, amplitude=0.2))
    mixed = P.film_audio(root, project)
    with wave.open(str(mixed), "rb") as handle:
        seconds = handle.getnframes() / handle.getframerate()
    assert abs(seconds - project.duration) < 0.01
    with pytest.raises(ValueError, match="inside the film"):
        sound.set_cues(root, [{"id": "late", "start": {"frame": last + 1}}])
    value = sound.report(root)
    codes = {note["code"] for note in value["notes"]}
    assert "silence" in codes  # the lines without takes are silent for longer than 8 s
    assert value["mixed"] and value["sounding"] == 1


def test_a_song_film_takes_cues_by_frame_only(song_film, tmp_path):  # noqa: F811
    root = song_film
    project = P.load_project(root)
    with pytest.raises(ValueError, match="only a story film"):
        sound.set_cues(root, [{"id": "x", "start": {"line": "l1"}}])
    before = P.film_audio(root, project)
    sound.set_cues(root, [{"id": "hit", "kind": "effect", "start": {"frame": 24}, "end": {"frame": 48}, "loop": False, "gain_db": 0}])  # fmt: skip
    sound.import_sound(
        root, "hit", tone(tmp_path / "hit.wav", 1.0, frequency=3000.0, amplitude=0.5)
    )
    after = P.film_audio(root, project)
    assert after != before and file_hash(after) != file_hash(before)
    rate = music.SAMPLE_RATE
    loud = voice._decode(after, 2)[round(1.1 * rate) : round(1.9 * rate)]
    quiet = voice._decode(before, 2)[round(1.1 * rate) : round(1.9 * rate)]
    assert float(np.sqrt(np.mean(np.square(loud)))) > float(np.sqrt(np.mean(np.square(quiet))))
    # Nothing in any stage hash moved.
    assert P.stage_hash(root, "brief") == P.stage_hash(root, "brief")


def test_suggestions_follow_the_structure_and_write_nothing(story):
    root, script = story
    cues = sound.suggest(root)
    assert cues[0]["id"] == "bed" and cues[0]["kind"] == "music"
    rooms = [cue for cue in cues if cue["kind"] == "ambience"]
    assert len(rooms) == 5 and rooms[0]["start"] == {"line": script.lines[0].id}
    assert sound.read(root)["cues"] == []
    sound.set_cues(root, cues)
    assert len(sound.read(root)["cues"]) == 6
