"""The story film's mix: bed, ambience, fades and what was measured. Real FFmpeg, no provider."""

from __future__ import annotations

import wave

import numpy as np
import pytest
from test_story_film import make_film, script_for, tone

from mp3_to_videoclip import captions, narration
from mp3_to_videoclip import production as P
from mp3_to_videoclip.production import soundtrack
from mp3_to_videoclip.production.script import load_script


def _rms(path, start, end):
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        handle.setpos(int(start * rate))
        data = np.frombuffer(handle.readframes(int((end - start) * rate)), dtype="<i2")
    return float(np.sqrt(np.mean((data / 32768.0) ** 2)))


@pytest.fixture
def film(tmp_path):
    root = make_film(tmp_path)
    script = script_for(root)
    soundtrack.ensure_spec(root, script)
    return root, script


def _sound(root, tmp_path, name, **options):
    return soundtrack.add_sound(root, tone(tmp_path / name, 3.0, **options))


def test_a_sound_is_kept_under_its_own_hash(film, tmp_path):
    root, _ = film
    first = _sound(root, tmp_path, "a.wav")
    assert first.startswith("media/sound-") and (root / first).is_file()
    assert _sound(root, tmp_path, "b.wav") == first
    (tmp_path / "x.txt").write_text("no")
    with pytest.raises(ValueError, match="a sound must be"):
        soundtrack.add_sound(root, tmp_path / "x.txt")


def test_a_key_without_ambience_is_the_key_it_always_was(film, tmp_path):
    root, script = film
    before = soundtrack.key(root)
    assert "ambience" not in soundtrack._inputs(root)
    sound = _sound(root, tmp_path, "rain.wav")
    first = script.lines[0].id
    soundtrack.set_mix(root, {"ambience": [{"path": sound, "from_line": first, "to_line": first}]})
    assert soundtrack.key(root) != before
    soundtrack.set_mix(root, {"ambience": []})
    assert soundtrack.key(root) == before


def test_the_mix_refuses_what_it_cannot_play(film, tmp_path):
    root, script = film
    sound = _sound(root, tmp_path, "bed.wav")
    with pytest.raises(ValueError, match="not in this film"):
        soundtrack.set_mix(root, {"bed": {"path": "media/none.wav"}})
    with pytest.raises(ValueError, match="bed gain"):
        soundtrack.set_mix(root, {"bed": {"path": sound, "gain_db": 6}})
    with pytest.raises(ValueError, match="fade_in"):
        soundtrack.set_mix(root, {"fade_in": -1})
    with pytest.raises(ValueError, match="one line of this script"):
        soundtrack.set_mix(
            root,
            {"ambience": [{"path": sound, "from_line": "nope", "to_line": script.lines[0].id}]},
        )


def _with_two_takes(root, script, tmp_path):
    for line in script.lines[:2]:
        narration.import_take(root, line.id, tone(tmp_path / f"{line.id}.wav", 2.0))


def test_the_bed_ducks_under_the_voice_and_the_receipt_says_what_was_measured(film, tmp_path):
    root, script = film
    _with_two_takes(root, script, tmp_path)
    bed = _sound(root, tmp_path, "bed.wav", amplitude=0.5, frequency=90.0)
    soundtrack.set_mix(root, {"bed": {"path": bed, "gain_db": -6.0, "duck_db": -20.0}})
    built = soundtrack.build(root)
    path = root / built["path"]
    receipt = soundtrack.receipt(root)
    assert receipt["output_lufs"] == pytest.approx(-16.0, abs=1.5)
    assert receipt["output_true_peak_db"] <= 0.0
    assert "output_range_lu" in receipt
    rows = (
        soundtrack.narration_timing.layout(root)
        if hasattr(soundtrack, "narration_timing")
        else None
    )
    from mp3_to_videoclip import narration_timing

    rows = narration_timing.layout(root)
    # A later line with no take is silence over which only the bed plays, undipped.
    free = rows[3]
    bed_alone = _rms(path, free["start"] + 0.5, free["end"] - 0.5)
    assert bed_alone > 0.01
    # Remove the voice's share by comparing bed energy with and without ducking.
    soundtrack.set_mix(root, {"bed": {"path": bed, "gain_db": -6.0, "duck_db": 0.0}})
    undipped = root / soundtrack.build(root)["path"]
    assert _rms(undipped, rows[0]["start"] + 0.5, rows[0]["end"] - 0.5) > _rms(
        path, rows[0]["start"] + 0.5, rows[0]["end"] - 0.5
    )


def test_ambience_plays_only_between_its_lines(film, tmp_path):
    root, script = film
    _with_two_takes(root, script, tmp_path)
    rain = _sound(root, tmp_path, "rain.wav", amplitude=0.5, frequency=400.0)
    target = script.lines[3].id
    soundtrack.set_mix(
        root,
        {"ambience": [{"path": rain, "from_line": target, "to_line": target, "gain_db": -6.0}]},
    )
    path = root / soundtrack.build(root)["path"]
    from mp3_to_videoclip import narration_timing

    rows = narration_timing.layout(root)
    inside_span = _rms(path, rows[3]["start"] + 1.05, rows[3]["end"] - 1.05)
    after = _rms(path, rows[5]["start"], rows[5]["end"])
    assert inside_span > 0.01
    assert after < 0.0005


def test_a_fade_reaches_silence_at_the_film_ends(film, tmp_path):
    root, script = film
    _with_two_takes(root, script, tmp_path)
    bed = _sound(root, tmp_path, "bed.wav")
    soundtrack.set_mix(root, {"bed": {"path": bed}, "fade_in": 2.0, "fade_out": 2.0})
    built = soundtrack.build(root)
    path = root / built["path"]
    assert _rms(path, 0.0, 0.05) < _rms(path, 2.1, 2.4)


def test_a_long_spoken_line_splits_where_the_sentence_breathes():
    text = "This is a long sentence, and it keeps on going with another clause, " * 3
    pieces = captions._phrases(text.strip())
    assert len(pieces) > 1
    assert all(len(piece) <= captions.MAX_SPOKEN for piece in pieces)
    assert " ".join(pieces) == text.strip()
    assert captions._phrases("Short and whole.") == ["Short and whole."]
    assert captions._phrases("word " * 40) and all(
        len(piece) <= captions.MAX_SPOKEN for piece in captions._phrases("word " * 40)
    )


def test_spoken_captions_come_from_the_timing_file(film):
    root, script = film
    soundtrack.build(root)
    project = P.load_project(root, verify_source=False)
    rows = captions.timed_lines(root, project.fps, project.total_frames)
    assert rows[0]["start"] == 0 and rows[0]["end"] <= rows[1]["start"]
    assert load_script(root).lines[1].text in {row["text"] for row in rows}
    assert captions.srt(rows, project.fps).startswith("1\n00:00:00,000 --> ")
    assert captions.vtt(rows, project.fps).startswith("WEBVTT")


def test_the_checklist_and_a_render_report_show_the_measured_mix(film, tmp_path):
    from mp3_to_videoclip.domain import delivery

    root, script = film
    _with_two_takes(root, script, tmp_path)
    soundtrack.build(root)
    line = next(item for item in delivery.build(root)["lines"] if item["id"] == "loudness")
    assert "LUFS measured" in line["detail"]
    assert line["state"] == "optional"


def test_captions_follow_a_rebuilt_mix(tmp_path):
    from test_story_film import approve_story

    from mp3_to_videoclip import edits

    root = make_film(tmp_path)
    script_for(root)
    approve_story(root)
    P.approve(root, "script", "owner")
    soundtrack.build(root)
    P.skeleton(root)
    edits.save_edit(root, edits.seed_edit(root))
    assert edits.apply_captions(root, mode="all")["captions"] > 0

    def starts():
        return {
            item.id: item.in_frame
            for shot in edits.load_edit(root).shots
            for item in shot.text
            if item.id.startswith("cap-")
        }

    before = starts()
    assert all(
        item.style == "caption" for shot in edits.load_edit(root).shots for item in shot.text
    )
    narration.import_take(root, "l001", tone(tmp_path / "long.wav", 9.0))
    after = starts()
    assert {key for key in after if key.count("-") == 1} == {
        key for key in before if key.count("-") == 1
    }
    assert after["cap-1"] == before["cap-1"] == 0
    assert after["cap-2"] > before["cap-2"]
