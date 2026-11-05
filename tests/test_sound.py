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


# ------------------------------------------------------------------ paid cues

from decimal import Decimal  # noqa: E402

from mp3_to_videoclip import budget, generation  # noqa: E402

SCHEMA = {
    "info": {
        "x-status": "live",
        "x-air-id": "runware:ace-step@v1.5-xl-turbo",
        "x-pricing": {"rates": []},
    },  # fmt: skip
    "components": {
        "schemas": {
            "RequestBody": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["taskType", "taskUUID", "model", "positivePrompt"],
                    "additionalProperties": False,
                    "properties": {
                        "taskType": {"const": "audioInference"},
                        "taskUUID": {"type": "string"},
                        "model": {"const": "runware:ace-step@v1.5-xl-turbo"},
                        "positivePrompt": {"type": "string", "minLength": 2},
                        "duration": {
                            "type": "number",
                            "minimum": 30,
                            "maximum": 300,
                            "multipleOf": 0.1,
                        },  # fmt: skip
                        "outputType": {"enum": ["URL"]},
                        "outputFormat": {"enum": ["MP3", "WAV", "FLAC"]},
                        "deliveryMethod": {"enum": ["sync", "async"]},
                        "numberResults": {"type": "integer"},
                        "includeCost": {"type": "boolean"},
                        "settings": {
                            "type": "object",
                            "properties": {"instrumental": {"type": "boolean"}},
                        },
                    },
                },
            }
        }
    },
}


def effects_schema():
    value = {"info": {**SCHEMA["info"], "x-air-id": "mirelo:1@1"}, "components": {"schemas": {"RequestBody": {"type": "array", "items": {}}}}}  # fmt: skip
    item = {**SCHEMA["components"]["schemas"]["RequestBody"]["items"]}
    props = {**item["properties"], "model": {"const": "mirelo:1@1"}, "duration": {"type": "number", "minimum": 1, "maximum": 10}}  # fmt: skip
    props.pop("settings")
    value["components"]["schemas"]["RequestBody"]["items"] = {**item, "properties": props}
    return value


class FakeSound:
    """Stands in for Runware: counts calls, can answer late, never spends twice."""

    def __init__(self, source, *, schema=None, pending=0, cost=0.0009):
        self.source = source
        self.schema_value = schema or SCHEMA
        self.pending = pending
        self.cost = cost
        self.submitted = []
        self.polls = 0

    def schema(self, slug):
        return self.schema_value

    def submit_speech(self, request):
        self.submitted.append(request)
        if self.pending:
            return {"taskUUID": request["taskUUID"]}
        return self._done(request["taskUUID"])

    def recover_speech(self, task_uuid):
        self.polls += 1
        if self.polls < self.pending:
            return None
        return self._done(task_uuid)

    def _done(self, task_uuid):
        return {"taskUUID": task_uuid, "audioURL": "https://example.test/a.wav", "cost": self.cost}

    def download_audio(self, url, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.source.read_bytes())

    def close(self):
        pass


@pytest.fixture
def cued(story):
    root, script = story
    budget.set_budget(root, "5.00", "test budget")
    ids = [line.id for line in script.lines]
    sound.set_cues(root, [
        {"id": "bed", "kind": "music", "prompt": "a slow instrumental bed"},
        {"id": "room", "kind": "ambience", "prompt": "a quiet room", "start": {"line": ids[0]}, "end": {"line": ids[2]}},  # fmt: skip
    ])  # fmt: skip
    return root


def test_a_quote_fits_the_model_schema_and_reserves_from_the_catalogue(cued, tmp_path):
    root = cued
    client = FakeSound(tone(tmp_path / "bed.wav", 2.0))
    quote = sound.quote_cues(root, ["bed"], client=client)
    task = quote["tasks"][0]
    request = task["request"]
    assert request["taskType"] == "audioInference" and request["model"] == "runware:ace-step@v1.5-xl-turbo"  # fmt: skip
    assert request["duration"] == float(round(P.load_project(root).duration))
    assert request["settings"] == {"instrumental": True}
    assert request["outputFormat"] == "WAV" and request["deliveryMethod"] == "async"
    # A run price is doubled, because compute time is not known in advance, then floored.
    assert sound._reserve("ace-step-v1-5-xl-turbo", 120.0, 0.2) == Decimal("0.01")
    assert sound._reserve("minimax-music-2-6", None, 0.2) == Decimal("0.15")
    assert sound._reserve("mirelo-sfx-1-5", 100.0, 0.2) == Decimal("0.025")
    assert sound._reserve("no-such-model", None, 0.2) == Decimal("0.2")
    assert Decimal(task["reserve_usd"]) == Decimal("0.01")
    assert (root / quote["schema"]).is_file()
    with pytest.raises(ValueError, match="separately"):
        sound.quote_cues(root, ["bed", "room"], client=client)
    with pytest.raises(ValueError, match="choose cues"):
        sound.quote_cues(root, ["nope"], client=client)
    # An effects model clamps the span to its own range and says nothing about instruments.
    effects = sound.quote_cues(root, ["room"], model="mirelo-sfx-1-5", client=FakeSound(tmp_path / "bed.wav", schema=effects_schema()))  # fmt: skip
    request = effects["tasks"][0]["request"]
    assert request["duration"] == 6.0 and "settings" not in request  # three 1.5 s takes and pauses
    assert Decimal(effects["tasks"][0]["reserve_usd"]) == Decimal("0.01")


def test_a_speech_model_is_refused_as_a_sound_model(cued, tmp_path):
    root = cued
    speaking = {**SCHEMA, "components": {"schemas": {"RequestBody": {"type": "array", "items": {**SCHEMA["components"]["schemas"]["RequestBody"]["items"], "required": ["taskType", "taskUUID", "model", "speech"]}}}}}  # fmt: skip
    with pytest.raises(ValueError, match="speaks"):
        sound.quote_cues(root, ["bed"], client=FakeSound(tmp_path / "x.wav", schema=speaking))


def test_the_journal_holds_the_reservation_before_the_request_and_never_resubmits(cued, tmp_path):
    root = cued
    client = FakeSound(tone(tmp_path / "bed.wav", 2.0), pending=2)
    quote = sound.quote_cues(root, ["bed"], client=client)
    generation.authorize(root, quote["id"], quote["reserve_total_usd"], "owner", via="studio", review_confirmed=True)  # fmt: skip
    slept = []
    result = sound.generate_cues(root, quote["id"], client=client, sleep=slept.append)
    assert result["done"] == ["bed"] and len(client.submitted) == 1 and len(slept) == 2
    journal = read_json(root / "work/tasks.json")
    task = journal[quote["tasks"][0]["uuid"]]
    assert task["kind"] == "sound" and task["status"] == "ready" and task["cost_usd"] == "0.0009"
    cue = sound.read(root)["cues"][0]
    assert cue["selected"] == 1 and cue["versions"][0]["source"] == "generated"
    assert cue["versions"][0]["cost_usd"] == "0.0009" and (root / cue["versions"][0]["path"]).is_file()  # fmt: skip
    # The same quote again is a resubmission, which the journal refuses.
    with pytest.raises(ValueError, match="needs recover"):
        sound.generate_cues(root, quote["id"], client=client)
    assert len(client.submitted) == 1
    # And the mix now carries the bed.
    project = P.load_project(root)
    assert P.film_audio(root, project).name.startswith("sound-")


def test_a_cue_still_out_holds_the_spending_until_it_is_recovered(cued, tmp_path):
    root = cued
    client = FakeSound(tone(tmp_path / "bed.wav", 2.0), pending=10_000)
    quote = sound.quote_cues(root, ["bed"], client=client)
    generation.authorize(root, quote["id"], quote["reserve_total_usd"], "owner", via="studio", review_confirmed=True)  # fmt: skip
    result = sound.generate_cues(root, quote["id"], client=client, sleep=lambda _s: None)
    assert result["pending"] == ["bed"] and result["done"] == []
    task_uuid = quote["tasks"][0]["uuid"]
    assert read_json(root / "work/tasks.json")[task_uuid]["status"] == "submitted"
    assert [t["id"] for t in budget.unresolved_tasks(root)] == [task_uuid]
    with pytest.raises(ValueError, match="unresolved task"):
        sound.quote_cues(root, ["bed"], client=client)
    # Recovery is a read, never a resubmission.
    client.pending = 0
    assert generation.recover(root, task_uuid, client=client) is True
    assert len(client.submitted) == 1
    assert read_json(root / "work/tasks.json")[task_uuid]["status"] == "ready"
    assert budget.unresolved_tasks(root) == []


def test_a_changed_prompt_between_quote_and_spend_is_refused(cued, tmp_path):
    root = cued
    client = FakeSound(tone(tmp_path / "bed.wav", 2.0))
    quote = sound.quote_cues(root, ["bed"], client=client)
    generation.authorize(root, quote["id"], quote["reserve_total_usd"], "owner", via="studio", review_confirmed=True)  # fmt: skip
    sound.set_cues(root, [{"id": "bed", "kind": "music", "prompt": "a different bed"}])
    result = sound.generate_cues(root, quote["id"], client=client)
    assert result["done"] == [] and "changed since the quote" in result["stopped"]
    assert client.submitted == [] and read_json(root / "work/tasks.json") == {}
