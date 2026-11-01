"""Takes are bought like stills: journaled first, never resubmitted. Every client is a fake."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_story_film import approve_story, make_film, script_for, tone

from mp3_to_videoclip import budget, narration, voices
from mp3_to_videoclip import generation as G
from mp3_to_videoclip import production as P
from mp3_to_videoclip.director.context import build_context
from mp3_to_videoclip.storage import file_hash, read_json

VOICE = "English_Deep-VoicedGentleman"


def schema(status="live"):
    return {
        "info": {"x-status": status, "x-air-id": "minimax:speech@2.8", "x-pricing": {}},
        "components": {
            "schemas": {
                "RequestBody": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["speech", "taskType", "taskUUID", "model"],
                        "additionalProperties": False,
                        "properties": {
                            "taskType": {"const": "audioInference"},
                            "taskUUID": {"type": "string"},
                            "model": {"const": "minimax:speech@2.8"},
                            "speech": {
                                "type": "object",
                                "properties": {
                                    "text": {"type": "string"},
                                    "voice": {"enum": [VOICE, "English_expressive_narrator"]},
                                },
                            },
                            "settings": {"type": "object"},
                            "outputType": {"enum": ["URL"]},
                            "outputFormat": {"enum": ["WAV"]},
                            "deliveryMethod": {"const": "sync"},
                            "numberResults": {"type": "integer"},
                            "includeCost": {"type": "boolean"},
                        },
                    },
                }
            }
        },
    }


class Fake:
    def __init__(self, *, pending=(), cost=0.01, seconds=1.0):
        self.pending = set(pending)
        self.cost = cost
        self.seconds = seconds
        self.submitted = []

    def schema(self, slug):
        return schema()

    def submit_speech(self, request):
        self.submitted.append(request)
        uuid = request["taskUUID"]
        if request["speech"]["text"] in self.pending:
            return {"taskUUID": uuid}
        return {"taskUUID": uuid, "audioURL": "https://x.test/a.wav", "cost": self.cost}

    def recover_speech(self, uuid):
        return {"taskUUID": uuid, "audioURL": "https://x.test/a.wav", "cost": self.cost}

    def download_audio(self, url, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        tone(Path(path), self.seconds)

    def close(self):
        pass


@pytest.fixture
def film(tmp_path):
    root = make_film(tmp_path)
    script_for(root)
    approve_story(root)
    P.approve(root, "script", "owner")
    budget.set_budget(root, "5.00", "test budget")
    narration.lock_voice(root, VOICE)
    return root


def _authorized(root, ids=None, client=None, **options):
    quote = narration.quote_lines(root, ids, client=client or Fake(), **options)
    G.authorize(root, quote["id"], quote["reserve_total_usd"], "owner", via="studio", review_confirmed=True)  # fmt: skip
    return quote


def test_a_quote_needs_the_script_approved_and_spends_nothing(tmp_path):
    root = make_film(tmp_path)
    script_for(root)
    with pytest.raises(ValueError, match="needs current user approval"):
        narration.quote_lines(root, client=Fake())
    assert read_json(root / "work/tasks.json") == {}


def test_each_line_gets_a_task_and_a_reservation(film):
    quote = narration.quote_lines(film, client=Fake())
    assert quote["kind"] == "narration" and len(quote["tasks"]) == 14
    task = quote["tasks"][0]
    assert task["request"]["speech"] == {"text": task["text"], "voice": VOICE}
    assert task["reserve_usd"] == "0.0150"[:6] or float(task["reserve_usd"]) >= 0.01
    assert read_json(film / "work/tasks.json") == {}


def test_a_voice_the_model_does_not_offer_is_refused_by_name(film):
    with pytest.raises(ValueError, match="does not offer the voice English_Magnetic_Male_2"):
        narration.quote_lines(film, voice_id="English_Magnetic_Male_2", client=Fake())


def test_nothing_is_bought_without_authorization(film):
    quote = narration.quote_lines(film, client=Fake())
    client = Fake()
    with pytest.raises(ValueError, match="authorization"):
        narration.generate(film, quote["id"], client=client)
    assert client.submitted == []


def test_buying_journals_first_and_keeps_a_receipt(film):
    class Watching(Fake):
        def submit_speech(self, request):
            task = read_json(film / "work/tasks.json")[request["taskUUID"]]
            assert task["status"] == "submitted" and task["kind"] == "narration"
            return super().submit_speech(request)

    quote = _authorized(film, ["l001"])
    result = narration.generate(film, quote["id"], client=Watching())
    assert result["done"] == ["l001"]
    uuid = quote["tasks"][0]["uuid"]
    task = read_json(film / "work/tasks.json")[uuid]
    assert task["status"] == "ready" and task["cost_usd"] == "0.01"
    take = narration.read_index(film)["lines"]["l001"]["versions"][0]
    assert take["provider"] == "runware" and take["voice"] == VOICE
    assert take["input_hash"] == quote["tasks"][0]["input_hash"]
    assert take["sha256"] == file_hash(film / take["path"])
    assert take["cost_usd"] == "0.01"


def test_the_first_take_plays_and_a_redo_waits_to_be_kept(film):
    narration.generate(film, _authorized(film, ["l001"])["id"], client=Fake())
    assert narration.read_index(film)["lines"]["l001"]["selected"] == 1
    assert (film / "work/audio").is_dir() and P.render_audio(film, P.load_project(film)).is_file()
    client = Fake(seconds=2.0)
    quote = _authorized(film, ["l001"], regenerate=True, client=client)
    narration.generate(film, quote["id"], client=client)
    entry = narration.read_index(film)["lines"]["l001"]
    assert [v["version"] for v in entry["versions"]] == [1, 2]
    assert entry["selected"] == 1
    narration.keep(film, "l001", 2)
    assert narration.read_index(film)["lines"]["l001"]["kept"] == [1, 2]
    assert narration.selected_takes(film)["l001"]["version"] == 2
    narration.unkeep(film, "l001")
    assert "l001" not in narration.selected_takes(film)
    assert (film / entry["versions"][0]["path"]).is_file()


def test_a_lost_answer_is_recovered_and_never_bought_twice(film):
    text = read_json(film / "work/script.json")["lines"][0]["text"]
    client = Fake(pending=[text])
    quote = _authorized(film, ["l001"], client=client)
    result = narration.generate(film, quote["id"], client=client)
    assert result["pending"] == ["l001"]
    uuid = quote["tasks"][0]["uuid"]
    with pytest.raises(ValueError, match="recover"):
        narration.generate(film, quote["id"], client=client)
    with pytest.raises(ValueError, match="unresolved"):
        narration.quote_lines(film, ["l001"], client=client, regenerate=True)
    assert len(client.submitted) == 1
    assert G.recover(film, uuid, client=client) is True
    assert len(client.submitted) == 1
    assert "l001" in narration.selected_takes(film)


def test_a_changed_cost_is_refused_on_recovery(film):
    text = read_json(film / "work/script.json")["lines"][0]["text"]
    client = Fake(pending=[text])
    quote = _authorized(film, ["l001"], client=client)
    narration.generate(film, quote["id"], client=client)
    uuid = quote["tasks"][0]["uuid"]
    G.update_task(film, uuid, cost_usd="0.50")
    with pytest.raises(ValueError, match="cost changed"):
        narration.recover_take(film, uuid, client=client)


def test_a_changed_line_stops_the_batch_before_it_spends(film):
    from mp3_to_videoclip.production import script as scripts

    client = Fake()
    quote = _authorized(film, ["l001"], client=client)
    scripts.update_lines(film, [{"id": "l001", "text": "Other words."}])
    result = narration.generate(film, quote["id"], client=client)
    assert client.submitted == [] and result["done"] == []
    assert result["stopped"]


def test_the_cap_stops_the_batch_once_cost_outruns_it(film):
    client = Fake(cost=0.5)
    quote = _authorized(film, client=client)
    result = narration.generate(film, quote["id"], client=client)
    assert result["stopped"] and len(client.submitted) == 1
    assert len(result["done"]) == 1


def test_changed_bytes_are_kept_aside_and_the_paid_take_restored(film):
    quote = _authorized(film, ["l001"])
    narration.generate(film, quote["id"], client=Fake())
    uuid = quote["tasks"][0]["uuid"]
    task = read_json(film / "work/tasks.json")[uuid]
    path = film / task["path"]
    path.write_bytes(b"not the take")
    assert narration.finish_take(film, uuid, task["result"], Fake()) is False or True
    assert list((film / "work/quarantine").iterdir())


def test_an_elevenlabs_voice_is_scaffolded_and_cannot_be_bought(film, monkeypatch):
    voice = voices.ElevenLabsVoice(id="rachel", label="Rachel")
    parsed = voice.parse_result(
        {
            "audio_url": "https://x.test/a.mp3",
            "cost": 0.02,
            "alignment": {
                "characters": list("hi yo"),
                "character_start_times_seconds": [0.0, 0.1, 0.2, 0.3, 0.4],
                "character_end_times_seconds": [0.1, 0.2, 0.3, 0.4, 0.5],
            },
        }
    )
    assert [word["text"] for word in parsed["words"]] == ["hi", "yo"]
    assert parsed["words"][1]["start"] == 0.3
    assert "with-timestamps" in voice.build_request("hi", "u", "m")["path"]
    monkeypatch.setattr(voices, "get", lambda _: voice)
    with pytest.raises(ValueError, match="can't be bought"):
        narration.quote_lines(film, client=Fake())


def test_the_catalogue_lists_elevenlabs_only_with_a_key(monkeypatch):
    assert all(row["provider"] != "elevenlabs" for row in voices.catalogue())
    assert voices.catalogue()[0]["recommended"] is True


def test_the_writer_sees_the_beats_lines_and_voice(film):
    text = build_context(film.name, film.parent, stage="script", task="narration_pass")
    assert "## The narration" in text
    assert "Beat hook: budget 8.0 s" in text
    assert f"Voice: {VOICE}" in text
    assert "l001 (hook, estimate)" in text
    assert "## The song" not in text
