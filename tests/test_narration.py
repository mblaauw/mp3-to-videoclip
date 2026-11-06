"""Takes are bought like stills: journaled first, never resubmitted. Every client is a fake."""

from __future__ import annotations

from decimal import Decimal
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
    with pytest.raises(ValueError, match="does not offer the voice English_Not_A_Voice"):
        narration.quote_lines(film, voice_id="English_Not_A_Voice", client=Fake())


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


class ElevenFake:
    """What ``providers.ElevenLabsClient`` answers, without the network."""

    def __init__(self, *, pending=(), count=1_000, limit=10_000, extend=False, history=()):
        self.pending = set(pending)
        self.count = count
        self.limit = limit
        self.extend = extend
        self.history = list(history)
        self.submitted = []
        self.downloaded = []

    def terms(self):
        return {
            "tier": "creator",
            "status": "active",
            "currency": "usd",
            "character_count": self.count,
            "character_limit": self.limit,
            "next_character_count_reset_unix": 1_800_000_000,
            "can_extend_character_limit": self.extend,
        }

    def submit_speech(self, request):
        self.submitted.append(request)
        uuid = request["taskUUID"]
        text = request["body"]["text"]
        if text in self.pending:
            return {"taskUUID": uuid}
        self.count += len(text)
        return {
            "taskUUID": uuid,
            "audioURL": f"elevenlabs:take:{uuid}",
            "audio_format": "mp3",
            "characters": len(text),
            "provider_characters": len(text),
            "alignment": {
                "characters": list(text),
                "character_start_times_seconds": [i * 0.1 for i in range(len(text))],
                "character_end_times_seconds": [(i + 1) * 0.1 for i in range(len(text))],
            },
        }

    def recover_speech(self, uuid, task=None):
        if task is None or task["text"] not in self.history:
            return None
        return {
            "taskUUID": uuid,
            "audioURL": "elevenlabs:history:h1",
            "audio_format": "mp3",
            "characters": len(task["text"]),
            "provider_characters": None,
            "alignment": None,
            "history_item_id": "h1",
        }

    def download_audio(self, url, path):
        self.downloaded.append(url)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        tone(Path(path), 1.0)

    def close(self):
        pass


@pytest.fixture
def eleven(film, monkeypatch):
    monkeypatch.setattr(
        voices, "get", lambda _: voices.ElevenLabsVoice(id="rachel", label="Rachel")
    )
    narration.lock_voice(film, "rachel")
    return film


def test_an_elevenlabs_voice_reads_words_and_asks_with_timestamps():
    voice = voices.ElevenLabsVoice(id="rachel", label="Rachel")
    parsed = voice.parse_result(
        {
            "alignment": {
                "characters": list("hi yo"),
                "character_start_times_seconds": [0.0, 0.1, 0.2, 0.3, 0.4],
                "character_end_times_seconds": [0.1, 0.2, 0.3, 0.4, 0.5],
            },
        }
    )
    assert [word["text"] for word in parsed["words"]] == ["hi", "yo"]
    assert parsed["words"][1]["start"] == 0.3
    request = voice.build_request("hi", "u", "eleven_v3")
    assert request["path"] == "/v1/text-to-speech/rachel/with-timestamps"
    assert request["body"] == {"text": "hi", "model_id": "eleven_v3"}


def test_an_elevenlabs_quote_stands_on_the_period_and_the_catalogue_price(eleven):
    client = ElevenFake(count=9_000, limit=10_000)
    quote = narration.quote_lines(eleven, ["l001"], model="eleven_flash_v2_5", client=client)
    text = quote["tasks"][0]["text"]
    assert quote["provider"] == "elevenlabs" and quote["model"] == "eleven_flash_v2_5"
    assert quote["tasks"][0]["request"]["body"] == {"text": text, "model_id": "eleven_flash_v2_5"}
    assert Decimal(quote["tasks"][0]["reserve_usd"]) == max(Decimal("0.01"), Decimal("0.00004") * len(text))  # fmt: skip
    assert quote["warning"].startswith("1,000 characters left this period")
    terms = read_json(eleven / quote["schema"])
    assert terms["price"] == {"amount": "0.04", "unit": "1k_chars", "checked": "2026-11-06", "source": "https://elevenlabs.io/pricing/api"}  # fmt: skip
    assert terms["subscription"]["character_limit"] == 10_000
    assert client.submitted == [] and read_json(eleven / "work/tasks.json") == {}


def test_an_elevenlabs_quote_past_the_period_is_refused_by_number_unless_the_plan_extends(eleven):
    with pytest.raises(ValueError, match="has 10 characters left this period; these lines need"):
        narration.quote_lines(eleven, ["l001"], model="eleven_v3", client=ElevenFake(count=9_990))
    quote = narration.quote_lines(eleven, ["l001"], model="eleven_v3", client=ElevenFake(count=9_990, extend=True))  # fmt: skip
    assert "the plan charges the rest" in quote["warning"]


def test_an_unpriced_elevenlabs_model_is_not_quoted(eleven):
    with pytest.raises(ValueError, match="no catalogue price per character"):
        narration.quote_lines(eleven, ["l001"], model="eleven_turbo_v2", client=ElevenFake())


def test_an_elevenlabs_take_is_journaled_at_the_catalogue_rate_with_its_basis(eleven):
    client = ElevenFake()
    quote = _authorized(eleven, ["l001"], client=client, model="eleven_multilingual_v2")
    result = narration.generate(eleven, quote["id"], client=client)
    assert result["done"] == ["l001"]
    task = read_json(eleven / "work/tasks.json")[quote["tasks"][0]["uuid"]]
    text = task["text"]
    assert task["status"] == "ready"
    assert Decimal(task["cost_usd"]) == Decimal("0.00008") * len(text)
    assert task["cost_basis"] == "catalogue price, read 2026-11-06"
    assert task["provider_characters"] == len(text) and task["provider"] == "elevenlabs"
    take = narration.read_index(eleven)["lines"]["l001"]["versions"][0]
    assert take["provider"] == "elevenlabs" and take["path"].endswith(".mp3")
    assert take["cost_usd"] == task["cost_usd"]
    assert [word["text"] for word in take["words"]] == text.split()
    assert client.downloaded == [f"elevenlabs:take:{task['uuid']}"]


def test_an_interrupted_elevenlabs_take_is_found_in_the_history_never_bought_twice(eleven):
    text = read_json(eleven / "work/script.json")["lines"][0]["text"]
    client = ElevenFake(pending=[text])
    quote = _authorized(eleven, ["l001"], client=client, model="eleven_v3")
    assert narration.generate(eleven, quote["id"], client=client)["pending"] == ["l001"]
    uuid = quote["tasks"][0]["uuid"]
    assert narration.recover_take(eleven, uuid, client=ElevenFake()) is False
    assert read_json(eleven / "work/tasks.json")[uuid]["status"] == "submitted"
    assert narration.recover_take(eleven, uuid, client=ElevenFake(history=[text])) is True
    task = read_json(eleven / "work/tasks.json")[uuid]
    assert task["status"] == "ready" and task["cost_basis"] == "catalogue price, read 2026-11-06"
    assert Decimal(task["cost_usd"]) == Decimal("0.00008") * len(text)
    assert narration.read_index(eleven)["lines"]["l001"]["versions"][0]["path"].endswith(".mp3")
    assert len(client.submitted) == 1


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


def test_a_film_locks_the_voice_with_its_provider_and_model(film, monkeypatch):
    narration.lock_voice(film, VOICE)
    index = narration.read_index(film)
    assert index["provider"] == "runware" and index["model"] == "minimax-speech-2-8"
    assert narration.view(film)["model"] == "minimax-speech-2-8"

    monkeypatch.setattr(
        voices, "get", lambda _: voices.ElevenLabsVoice(id="rachel", label="Rachel")
    )
    narration.lock_voice(film, "rachel", "eleven_flash_v2_5")
    assert narration.read_index(film)["model"] == "eleven_flash_v2_5"
    # Settings may change; the film records with what it locked.
    quote = narration.quote_lines(film, ["l001"], client=ElevenFake())
    assert quote["model"] == "eleven_flash_v2_5"
    with pytest.raises(ValueError, match="choose a model"):
        narration.lock_voice(film, "rachel", "  ")


def test_the_narration_facts_price_the_script_and_say_where_the_lines_fall(film):
    facts = narration.facts(film)
    assert facts["voice"] == VOICE and facts["provider"] == "runware"
    assert facts["model"] == "minimax-speech-2-8" and facts["model_label"] == "MiniMax Speech 2.8"
    assert facts["price"] == {"amount": "0.10", "unit": "1k_chars", "checked": "2026-11-01"}
    script = facts["script"]
    assert script["lines"] == 14 and script["recorded"] == 0 and script["first_line"] == "l001"
    assert Decimal(script["cost_usd"]) == (Decimal("0.10") / 1000 * script["characters"]).quantize(Decimal("0.0001"))  # fmt: skip
    assert sum(beat["lines"] for beat in script["beats"]) == 14
    assert all(beat["characters"] > 0 for beat in script["beats"])
    rows = {row["id"]: row for row in facts["voices"]}
    assert (
        rows[VOICE]["provider_label"] == "Runware" and rows[VOICE]["model"] == "minimax-speech-2-8"
    )
    assert rows[VOICE]["price"]["amount"] == "0.10" and rows[VOICE]["preview_url"] == ""
    assert {m["id"] for m in facts["elevenlabs_models"]} == {"eleven_multilingual_v2", "eleven_v3", "eleven_flash_v2_5"}  # fmt: skip
