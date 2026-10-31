"""Voiceover: takes, the money journal and the mix. No provider is ever called."""

from __future__ import annotations

import subprocess
import wave
from decimal import Decimal

import numpy as np
import pytest
from api_support import make_api_project

from mp3_to_videoclip import audio as music
from mp3_to_videoclip import budget, edits, flow, generation, voice
from mp3_to_videoclip import production as P
from mp3_to_videoclip.models import EditDecisionList
from mp3_to_videoclip.storage import file_hash, read_json, write_json

SCHEMA = {
    "info": {"x-status": "live", "x-air-id": "minimax:speech@2.8"},
    "components": {
        "schemas": {
            "RequestBody": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["taskType", "taskUUID", "model", "speech"],
                    "properties": {
                        "taskType": {"const": "audioInference"},
                        "speech": {
                            "type": "object",
                            "properties": {
                                "voice": {"enum": ["English_Deep-VoicedGentleman", "Other"]}
                            },
                        },
                    },
                },
            }
        }
    },
}


def tone(path, seconds, frequency=220.0, amplitude=0.3, channels=1, rate=48_000):
    t = np.arange(int(seconds * rate)) / rate
    wavy = amplitude * np.sin(2 * np.pi * frequency * t)
    data = np.repeat(wavy[:, None], channels, axis=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes((data * 32767).astype("<i2").tobytes())
    return path


class FakeSpeech:
    """Stands in for Runware: counts calls and can answer late."""

    def __init__(self, source, *, pending=False, cost=0.0045):
        self.source = source
        self.pending = pending
        self.cost = cost
        self.submitted = []

    def schema(self, slug):
        return SCHEMA

    def submit_speech(self, request):
        self.submitted.append(request)
        if self.pending:
            return {"taskUUID": request["taskUUID"]}
        return self._done(request["taskUUID"])

    def recover_speech(self, task_uuid):
        return self._done(task_uuid)

    def _done(self, task_uuid):
        return {"taskUUID": task_uuid, "audioURL": "https://example.test/a.wav", "cost": self.cost}

    def download_audio(self, url, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.source.read_bytes())


@pytest.fixture
def film(tmp_path):
    root = make_api_project(tmp_path)
    # The fixture's song is a placeholder; the mix has to read real audio.
    subprocess.run(
        [
            music._ffmpeg(),
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=110:duration=4",
            "-ac",
            "2",
            str(root / P.load_project(root).source),
        ],
        check=True,
    )
    project = read_json(root / "project.json")
    project["source_sha256"] = file_hash(root / project["source"])
    write_json(root / "project.json", project)
    flow.mark(root)
    if edits.load_edit(root) is None:
        edits.seed_edit(root)
    edit = edits.load_edit(root).model_dump()
    edit["voice"] = [
        {"id": "l1", "text": "They say the city goes quiet.", "start_frame": 0},
        {"id": "l2", "text": "Find the second heartbeat.", "start_frame": 24},
    ]
    edits.save_edit(root, edit)
    budget.set_budget(root, "5.00", "test budget")
    return root


def _authorize(root, quote):
    generation.authorize(root, quote["id"], quote["reserve_total_usd"], "test authorization")


def test_a_cut_without_voice_serializes_as_it_always_has(film):
    edit = edits.load_edit(film).model_dump()
    edit.pop("voice")
    assert "voice" not in EditDecisionList.model_validate(edit).model_dump()


def test_voice_lines_must_be_ordered_unique_and_inside_the_film(film):
    edit = edits.load_edit(film).model_dump()
    swapped = {**edit, "voice": list(reversed(edit["voice"]))}
    with pytest.raises(ValueError, match="ordered"):
        EditDecisionList.model_validate(swapped)
    twice = {**edit, "voice": [edit["voice"][0], {**edit["voice"][1], "id": "l1"}]}
    with pytest.raises(ValueError, match="unique"):
        EditDecisionList.model_validate(twice)
    board = P.load_board(film)
    late = {**edit, "voice": [{"id": "l1", "text": "x", "start_frame": board.total_frames}]}
    with pytest.raises(ValueError, match="after the film"):
        EditDecisionList.model_validate(late).check_board(board)


def test_quote_uses_the_owners_voice_and_reserves_by_length(film):
    quote = voice.quote_voice(film, client=FakeSpeech(tone(film / "t.wav", 1)))
    assert quote["kind"] == "voice"
    assert [task["line_id"] for task in quote["tasks"]] == ["l1", "l2"]
    request = quote["tasks"][0]["request"]
    assert request["model"] == "minimax:speech@2.8"
    assert request["speech"]["voice"] == "English_Deep-VoicedGentleman"
    assert request["settings"] == {"turbo": False}
    assert Decimal(quote["reserve_total_usd"]) >= Decimal("0.02")
    assert read_json(film / "work/tasks.json") == {} or all(
        task.get("kind") != "voice" for task in read_json(film / "work/tasks.json").values()
    )


def test_nothing_is_sent_without_authorization(film):
    client = FakeSpeech(tone(film / "t.wav", 1))
    quote = voice.quote_voice(film, client=client)
    with pytest.raises(ValueError, match="authorization"):
        voice.generate_voice(film, quote["id"], client=client)
    assert client.submitted == []


def test_cost_is_journalled_before_download_and_a_take_is_recorded(film):
    client = FakeSpeech(tone(film / "t.wav", 1))
    quote = voice.quote_voice(film, client=client)
    _authorize(film, quote)
    outcome = voice.generate_voice(film, quote["id"], client=client)
    assert outcome["done"] == ["l1", "l2"]
    journal = read_json(film / "work/tasks.json")
    voiced = [task for task in journal.values() if task.get("kind") == "voice"]
    assert [task["status"] for task in voiced] == ["ready", "ready"]
    assert all(task["cost_usd"] == "0.0045" for task in voiced)
    index = voice.read_index(film)
    take = index["lines"]["l1"]["versions"][0]
    assert file_hash(film / take["path"]) == take["sha256"]
    assert index["lines"]["l1"]["selected"] == 1


def test_a_download_failure_keeps_the_bill_and_recovery_never_resubmits(film):
    class Broken(FakeSpeech):
        def download_audio(self, url, path):
            raise RuntimeError("network fell over")

    good = FakeSpeech(tone(film / "t.wav", 1))
    broken = Broken(good.source)
    quote = voice.quote_voice(film, ["l1"], client=good)
    _authorize(film, quote)
    with pytest.raises(RuntimeError):
        voice.generate_voice(film, quote["id"], client=broken)
    task = read_json(film / "work/tasks.json")[quote["tasks"][0]["uuid"]]
    assert (task["status"], task["cost_usd"]) == ("result", "0.0045")
    assert generation.recover(film, task["uuid"], client=good) is True
    assert good.submitted == []
    assert voice.read_index(film)["lines"]["l1"]["selected"] == 1


def test_a_pending_task_blocks_a_second_paid_quote_for_that_line(film):
    client = FakeSpeech(tone(film / "t.wav", 1), pending=True)
    quote = voice.quote_voice(film, ["l1"], client=client)
    _authorize(film, quote)
    assert voice.generate_voice(film, quote["id"], client=client)["pending"] == ["l1"]
    with pytest.raises(ValueError, match="unresolved"):
        voice.quote_voice(film, ["l1"], client=client, regenerate=True)


def test_a_quote_stops_when_the_words_change(film):
    client = FakeSpeech(tone(film / "t.wav", 1))
    quote = voice.quote_voice(film, ["l1"], client=client)
    _authorize(film, quote)
    edit = edits.load_edit(film).model_dump()
    edit["voice"][0]["text"] = "Different words."
    edits.save_edit(film, edit)
    with pytest.raises(ValueError, match="changed"):
        voice.generate_voice(film, quote["id"], client=client)
    assert client.submitted == []


def test_your_own_recording_is_a_new_take_and_old_takes_stay(film):
    client = FakeSpeech(tone(film / "t.wav", 1))
    quote = voice.quote_voice(film, ["l1"], client=client)
    _authorize(film, quote)
    voice.generate_voice(film, quote["id"], client=client)
    first = voice.read_index(film)["lines"]["l1"]["versions"][0]
    before = (film / first["path"]).read_bytes()
    take = voice.import_take(film, "l1", tone(film / "mine.wav", 0.5, frequency=330))
    assert take["version"] == 2
    assert take["source"] == "upload"
    assert (film / first["path"]).read_bytes() == before
    voice.select_take(film, "l1", 1)
    assert voice.read_index(film)["lines"]["l1"]["selected"] == 1


def test_changed_words_leave_a_line_without_a_take_and_a_final_refuses(film):
    voice.import_take(film, "l1", tone(film / "mine.wav", 0.5))
    edit = edits.load_edit(film).model_dump()
    edit["voice"][0]["text"] = "New words."
    edits.save_edit(film, edit)
    project = P.load_project(film)
    with pytest.raises(ValueError, match="l1"):
        voice.film_audio(film, project, strict=True)
    assert voice.film_audio(film, project) == music.render_audio(film, project)


def test_mix_keeps_the_music_exact_outside_speech_and_ducks_under_it(tmp_path):
    base = tone(tmp_path / "base.wav", 6, frequency=110, amplitude=0.5, channels=2)
    take = tone(tmp_path / "take.wav", 1, frequency=880, amplitude=0.2)
    target = voice.mix(base, [(2 * 48_000, take, 0.0)], tmp_path / "mix.wav")
    original = voice._decode(base, 2)
    mixed = voice._decode(target, 2)
    assert mixed.shape == original.shape
    before = int(1.5 * 48_000)
    assert np.allclose(mixed[:before], original[:before], atol=1e-3)
    after = int(3.5 * 48_000)
    assert np.allclose(mixed[after:], original[after:], atol=1e-3)
    assert np.max(np.abs(mixed)) <= voice.PEAK_LIMIT + 1e-3
    # Halfway through the line the music alone would be far louder than it now is,
    # so speech rides on lowered music rather than simply being added.
    spectrum = np.abs(np.fft.rfft(mixed[int(2.2 * 48_000) : int(2.8 * 48_000), 0]))
    frequencies = np.fft.rfftfreq(int(2.8 * 48_000) - int(2.2 * 48_000), 1 / 48_000)
    low = spectrum[np.argmin(np.abs(frequencies - 110))]
    high = spectrum[np.argmin(np.abs(frequencies - 880))]
    assert high > low
    original_low = np.abs(np.fft.rfft(original[int(2.2 * 48_000) : int(2.8 * 48_000), 0]))[
        np.argmin(np.abs(frequencies - 110))
    ]
    assert low == pytest.approx(original_low * 10 ** (voice.DUCK_DB / 20), rel=0.05)


def test_mix_refuses_a_take_that_runs_past_the_end(tmp_path):
    base = tone(tmp_path / "base.wav", 1, channels=2)
    take = tone(tmp_path / "take.wav", 1)
    with pytest.raises(ValueError, match="past the end"):
        voice.mix(base, [(24_000, take, 0.0)], tmp_path / "mix.wav")


def test_film_audio_rebuilds_only_when_a_take_or_its_place_changes(film):
    project = P.load_project(film)
    silent = voice.film_audio(film, project)
    source_bytes = (film / project.source).read_bytes()
    assert silent == music.render_audio(film, project)
    seconds = float(project.duration)
    voice.import_take(film, "l1", tone(film / "mine.wav", min(0.5, seconds / 4)))
    first = voice.film_audio(film, project)
    assert first.parent == film / "work" / "audio"
    assert voice.film_audio(film, project) == first
    edit = edits.load_edit(film).model_dump()
    edit["voice"][0]["start_frame"] = 12
    edits.save_edit(film, edit)
    assert voice.film_audio(film, project) != first
    assert (film / project.source).read_bytes() == source_bytes


def test_analysis_keeps_hearing_the_music_alone(film):
    project = P.load_project(film)
    voice.import_take(film, "l1", tone(film / "mine.wav", 0.2))
    assert P.render_audio(film, project) == music.render_audio(film, project)
    assert P.film_audio(film, project) != P.render_audio(film, project)
