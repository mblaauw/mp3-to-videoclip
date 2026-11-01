"""A story film: no song, the script as its plan and the kept takes as its clock."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import pytest

from mp3_to_videoclip import narration, narration_timing, structures
from mp3_to_videoclip import production as P
from mp3_to_videoclip.models import Project
from mp3_to_videoclip.production import script as scripts
from mp3_to_videoclip.production import soundtrack
from mp3_to_videoclip.storage import read_json, write_json


def make_film(tmp_path, *, fictional=True, length=120, source=None) -> Path:
    root = tmp_path / "the-last-house-key"
    P.init_project(
        root,
        source,
        root.name,
        title="The Last House Key",
        kind="narrative",
        length_seconds=length,
        intent={"kind": "narrative", "fictional": fictional, "structure": "five-beat-2m"},
    )
    return root


def lines(words=8, **beats) -> list[dict]:
    beats = beats or {"hook": 2, "world": 3, "develop": 4, "reveal": 3, "payoff": 2}
    rows = []
    for beat, count in beats.items():
        for _ in range(count):
            number = len(rows) + 1
            rows.append(
                {"id": f"l{number:03d}", "beat": beat, "text": " ".join([f"word{number}"] * words)}
            )
    return rows


def script_for(root, **extra):
    return scripts.write_script(root, {"structure": "five-beat-2m", "lines": lines(), **extra})


def tone(path: Path, seconds: float, *, amplitude=0.4, frequency=220.0):
    rate = 48_000
    t = np.arange(int(rate * seconds)) / rate
    pcm = (np.sin(2 * np.pi * frequency * t) * amplitude * 32767).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm.tobytes())
    return path


def approve_story(root):
    brief = read_json(root / "brief.json")
    brief["treatment"] = "A curator explains a key."
    brief["creative"]["profile_version"] = 1
    write_json(root / "brief.json", brief)
    P.approve(root, "brief", "owner")


def test_a_story_film_needs_no_song(tmp_path):
    root = make_film(tmp_path)
    project = P.load_project(root)
    assert project.spine == "soundtrack"
    assert project.music_mode == "narration-led"
    stored = read_json(root / "project.json")
    assert "source" not in stored and "source_sha256" not in stored and "bed" not in stored
    assert project.duration == 120
    intent = read_json(root / "brief.json")["intent"]
    assert intent["fictional"] is True and intent["structure"] == "five-beat-2m"


def test_a_song_film_serialises_as_it_always_did(tmp_path):
    project = Project(
        slug="x", title="X", source_sha256="abc", duration=10.0, width=1920, height=1080
    )
    value = project.model_dump()
    assert value["source"] == "media/song.mp3" and value["source_sha256"] == "abc"
    assert not {"spine", "bed"} & set(value)
    payload = P.project_payload(project)
    assert payload["duration"] == 10.0


def test_a_soundtrack_films_length_stays_out_of_its_hashes(tmp_path):
    payload = P.project_payload(P.load_project(make_film(tmp_path)))
    assert "duration" not in payload and "source_duration" not in payload


def test_other_kinds_still_refuse_no_source(tmp_path):
    with pytest.raises(ValueError, match="MP3"):
        P.init_project(tmp_path / "x", None, "x", kind="promo")


def test_budgets_scale_with_the_length():
    instance = structures.instance("five-beat-2m", 120)
    assert [beat["budget"] for beat in instance["beats"]] == [8, 27, 40, 30, 15]
    assert structures.instance("five-beat-2m", 60)["beats"][0]["budget"] == 4


def test_the_script_writes_its_beats_and_an_estimate(tmp_path):
    root = make_film(tmp_path)
    script_for(root)
    assert scripts.read_beats(root)["structure"] == "five-beat-2m"
    timing = narration_timing.read(root)
    first, second = timing["lines"][:2]
    assert first["source"] == "estimate" and "words" not in first
    assert first["start"] == 0
    assert first["end"] == round(8 / 2.3, 3)
    assert second["start"] == round(first["end"] + 0.5, 3)


def test_an_unknown_beat_and_an_overrun_are_refused_plainly(tmp_path):
    root = make_film(tmp_path)
    with pytest.raises(ValueError, match="beat this structure does not have"):
        scripts.write_script(root, {"structure": "five-beat-2m", "lines": lines(chorus=1)})
    with pytest.raises(ValueError, match="for a 8.0 s budget"):
        scripts.write_script(root, {"structure": "five-beat-2m", "lines": lines(words=30, hook=1)})


def test_an_invented_claim_needs_a_fictional_world(tmp_path):
    claim = [{"text": "No door was found", "invented": True}]
    row = {**lines(hook=1)[0], "claims": claim}
    real = make_film(tmp_path, fictional=False)
    with pytest.raises(ValueError, match="invents a fact"):
        scripts.write_script(real, {"structure": "five-beat-2m", "lines": [row]})
    fiction = tmp_path / "other"
    fiction.mkdir()
    root = make_film(fiction)
    scripts.write_script(root, {"structure": "five-beat-2m", "lines": [row]})
    assert scripts.script_report(root)["invented"] == [
        {"line": "l001", "text": "No door was found"}
    ]


def test_a_draft_soundtrack_is_silence_of_the_estimated_length(tmp_path):
    from mp3_to_videoclip.render import audio_seconds

    root = make_film(tmp_path)
    script_for(root)
    with pytest.raises(ValueError, match="build the soundtrack first"):
        P.render_audio(root, P.load_project(root))
    built = soundtrack.build(root)
    path = P.render_audio(root, P.load_project(root))
    assert abs(audio_seconds(path) - built["seconds"]) < 0.01
    assert P.load_project(root).duration == built["seconds"]
    assert soundtrack.receipt(root)["input_lufs"] is None
    music = read_json(root / "work/music.json")
    assert music["estimated_tempo_bpm"] is None and music["beats"] == []
    assert [item["name"] for item in music["sections"]] == [
        "Hook", "World", "Develop", "Reveal", "Payoff",
    ]  # fmt: skip


def test_the_soundtrack_key_follows_every_input(tmp_path):
    root = make_film(tmp_path)
    script_for(root)
    first = soundtrack.key(root)
    assert soundtrack.key(root) == first
    scripts.update_lines(root, [{"id": "l001", "pause_after": 2.0}])
    second = soundtrack.key(root)
    assert second != first
    narration.import_take(root, "l001", tone(tmp_path / "a.wav", 2.0))
    assert soundtrack.key(root) != second


def test_a_kept_take_is_the_clock_and_moves_only_what_follows(tmp_path):
    root = make_film(tmp_path)
    script_for(root)
    approve_story(root)
    P.approve(root, "script", "owner")
    soundtrack.build(root)
    board = P.skeleton(root)
    assert board.shots[0].start_frame == 0
    assert sum(shot.duration_frames for shot in board.shots) == board.total_frames
    assert board.shots[0].line_ids == ["l001"]
    before = {shot.id: shot.start_frame for shot in board.shots}
    narration.import_take(root, "l003", tone(tmp_path / "long.wav", 8.0))
    after = P.load_board(root)
    moved = {shot.id: shot.start_frame for shot in after.shots}
    third = next(shot for shot in after.shots if "l003" in shot.line_ids)
    for shot in after.shots:
        if shot.start_frame <= third.start_frame:
            assert moved[shot.id] == before[shot.id]
        else:
            assert moved[shot.id] > before[shot.id]
    assert sum(shot.duration_frames for shot in after.shots) == after.total_frames
    assert after.total_frames == P.load_project(root).total_frames
    timing = {row["id"]: row for row in narration_timing.read(root)["lines"]}
    assert timing["l003"]["source"] == "measured"
    assert timing["l001"]["source"] == "estimate"
    assert scripts.script_report(root)["moved"]


def test_approvals_run_brief_script_voice_then_storyboard(tmp_path):
    root = make_film(tmp_path)
    script_for(root)
    with pytest.raises(ValueError, match="brief needs"):
        P.approve(root, "script", "owner")
    approve_story(root)
    P.approve(root, "script", "owner")
    with pytest.raises(ValueError, match="no kept take"):
        P.approve(root, "voice", "owner")
    for row in read_json(root / "work/script.json")["lines"]:
        narration.import_take(
            root, row["id"], tone(tmp_path / f"{row['id']}.wav", 1.0), follow=False
        )
    soundtrack.build(root)
    P.approve(root, "voice", "owner")
    P.require_approval(root, "voice")
    assert P.effective_upstream(root, "storyboard") == "voice"
    assert P.effective_upstream(root, "brief") is None


def _approved_voice(tmp_path):
    root = make_film(tmp_path)
    script_for(root)
    approve_story(root)
    P.approve(root, "script", "owner")
    for row in read_json(root / "work/script.json")["lines"]:
        narration.import_take(
            root, row["id"], tone(tmp_path / f"{row['id']}.wav", 1.0), follow=False
        )
    soundtrack.build(root)
    P.approve(root, "voice", "owner")
    return root


def test_a_changed_line_unapproves_script_and_voice_but_not_the_brief(tmp_path):
    root = _approved_voice(tmp_path)
    scripts.update_lines(root, [{"id": "l001", "text": "Other words entirely."}])
    P.require_approval(root, "brief")
    with pytest.raises(ValueError):
        P.require_approval(root, "script")
    with pytest.raises(ValueError):
        P.require_approval(root, "voice")
    assert narration.stale_lines(root) == ["l001"]
    assert scripts.script_report(root)["stale"] == ["l001"]
    P.approve(root, "script", "owner")
    with pytest.raises(ValueError, match="stale take of l001"):
        P.approve(root, "voice", "owner")


def test_a_new_kept_take_unapproves_voice_but_not_the_script(tmp_path):
    root = _approved_voice(tmp_path)
    narration.import_take(root, "l002", tone(tmp_path / "again.wav", 1.5))
    # A second take waits to be kept, so nothing has changed yet.
    P.require_approval(root, "voice")
    narration.keep(root, "l002", 2)
    P.require_approval(root, "script")
    with pytest.raises(ValueError):
        P.require_approval(root, "voice")


def test_a_real_mix_ducks_the_bed_under_the_voice(tmp_path):
    bed = tone(tmp_path / "bed.wav", 40.0, amplitude=0.5, frequency=110.0)
    import subprocess

    from mp3_to_videoclip.audio import _ffmpeg

    mp3 = tmp_path / "bed.mp3"
    subprocess.run([_ffmpeg(), "-nostdin", "-v", "error", "-i", str(bed), str(mp3)], check=True)
    root = make_film(tmp_path, source=mp3)
    assert P.load_project(root).bed == "media/bed.mp3"
    scripts.write_script(
        root,
        {
            "structure": "five-beat-2m",
            "lines": [
                {"id": "l001", "beat": "hook", "text": "one two three", "pause_after": 6.0},
                {"id": "l002", "beat": "world", "text": "four five six", "pause_after": 1.0},
            ],
        },
    )
    narration.import_take(root, "l001", tone(tmp_path / "a.wav", 3.0, frequency=1000.0))
    narration.import_take(root, "l002", tone(tmp_path / "b.wav", 3.0, frequency=1000.0))
    path = soundtrack.current(root)
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        data = np.frombuffer(handle.readframes(handle.getnframes()), dtype="<i2")[::2] / 32767

    def bed_level(start, end):
        chunk = data[int(start * rate) : int(end * rate)]
        spectrum = np.abs(np.fft.rfft(chunk))
        freq = np.fft.rfftfreq(chunk.size, 1 / rate)
        return float(spectrum[(freq > 90) & (freq < 130)].max())

    under = bed_level(1.0, 2.0)
    rest = bed_level(5.0, 8.0) * (1.0 / 3.0)  # same window length as ``under``
    assert 20 * np.log10(rest / under) >= 9
    receipt = soundtrack.receipt(root)
    assert abs(receipt["output_lufs"] - receipt["target_lufs"]) < 2.5


def test_the_report_names_a_beat_over_its_budget(tmp_path):
    root = make_film(tmp_path)
    scripts.write_script(
        root,
        {"structure": "five-beat-2m", "lines": [{"id": "l001", "beat": "hook", "text": "short"}]},
    )
    narration.import_take(root, "l001", tone(tmp_path / "a.wav", 12.0))
    report = scripts.script_report(root)
    hook = report["beats"][0]
    assert hook["measured"] == 12.5
    assert hook["over"] == 4.5
    assert "Hook runs 4.5 s over" in report["notes"][0]
    assert report["measured_rate"] == round(1 / 12.0, 2)
    assert narration.read_index(root)["measured_rate"] == report["measured_rate"]
