"""Runware audio workflow tests: no cloud calls/uploads, all clients are fake."""

import copy
import json
from uuid import uuid4

import pytest

from mp3_to_videoclip import generation as G
from mp3_to_videoclip import production as P
from mp3_to_videoclip import transcription as T
from mp3_to_videoclip.cli import execute, parser
from mp3_to_videoclip.models import Project
from mp3_to_videoclip.providers import ProviderError
from mp3_to_videoclip.storage import file_hash, read_json, write_json


def schema():
    props = {
        k: {}
        for k in [
            "taskUUID",
            "messages",
            "outputFormat",
            "jsonSchema",
            "settings",
            "numberResults",
            "deliveryMethod",
            "includeCost",
            "includeUsage",
        ]
    }
    props.update(
        {
            "taskType": {"const": "textInference"},
            "model": {"const": "google:gemini@3.1-flash-lite"},
            "inputs": {
                "type": "object",
                "properties": {
                    "audios": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 1,
                        "items": {"type": "string"},
                    }
                },
                "additionalProperties": False,
            },
        }
    )
    return {
        "info": {
            "x-status": "live",
            "x-air-id": "google-gemini-3-1-flash-lite",
            "x-capabilities": ["audio-to-text"],
            "x-pricing": {"audio_input": 0.0000005},
        },
        "components": {
            "schemas": {
                "RequestBody": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": props,
                        "required": ["taskUUID", "taskType", "model"],
                        "additionalProperties": False,
                    },
                }
            }
        },
    }


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "production"
    (root / "media").mkdir(parents=True)
    source = root / "media/song.mp3"
    source.write_bytes(b"local fake audio never sent to cloud")
    config = Project(
        slug="fixture",
        title="Fixture",
        source_sha256=file_hash(source),
        duration=4,
        width=192,
        height=108,
    )
    write_json(root / "project.json", config.model_dump())
    write_json(root / "work/music.json", {"duration": 4, "beats": []})
    for name in ["approvals", "tasks", "assets"]:
        write_json(root / f"work/{name}.json", {})
    P.approve(root, "analysis", "test user approved local analysis")
    return root


class Client:
    def __init__(self, root):
        self.root = root
        self.uploads = []
        self.calls = []
        self.polls = []
        self.media = str(uuid4())
        self.pending_upload = False
        self.pending_text = False
        self.upload_error = None
        self.text_error = None
        self.cost = 0.002
        self.reason = "stop"
        self.draft = {
            "language": "nl",
            "segments": [
                {
                    "start": 0.2,
                    "end": 2.5,
                    "text": "[unintelligible]",
                    "uncertain": True,
                    "reason": "vocal masked by instruments",
                }
            ],
            "music_notes": ["Soft strings, subjective"],
        }
        self.raw_text = None

    def schema(self, _):
        return schema()

    def upload_result(self, uuid):
        return {"taskUUID": uuid, "mediaUUID": self.media, "mediaURL": "https://media.example/song"}

    def upload_audio(self, uuid, source, expected, *, on_response=None):
        journal = read_json(self.root / "work/tasks.json")
        assert journal[uuid]["status"] == "submitted" and journal[uuid]["kind"] == "audio-upload"
        assert file_hash(source) == expected
        self.uploads.append(uuid)
        if self.upload_error:
            raise ProviderError(self.upload_error)
        result = {"taskUUID": uuid} if self.pending_upload else self.upload_result(uuid)
        if on_response:
            on_response({**result, "operation": "upload"})
        return result

    def text_result(self, uuid):
        return {
            "taskUUID": uuid,
            "text": self.raw_text if self.raw_text is not None else json.dumps(self.draft),
            "cost": self.cost,
            "finishReason": self.reason,
            "usage": {"inputTokens": 100, "outputTokens": 200},
        }

    def submit_text(self, request):
        task = read_json(self.root / "work/tasks.json")[request["taskUUID"]]
        assert task["status"] == "submitted"
        assert request["inputs"]["audios"] == [self.media]
        self.calls.append(copy.deepcopy(request))
        if self.text_error:
            raise ProviderError(self.text_error)
        return (
            {"taskUUID": request["taskUUID"]}
            if self.pending_text
            else self.text_result(request["taskUUID"])
        )

    def recover_audio_upload(self, uuid):
        self.polls.append(("upload", uuid))
        return None if self.pending_upload else self.upload_result(uuid)

    def recover_text(self, uuid):
        self.polls.append(("text", uuid))
        return None if self.pending_text else self.text_result(uuid)


def quote(root, client):
    q = G.quote_transcription(root, client=client)
    G.authorize(
        root, q["id"], q["reserve_total_usd"], "test user authorized Runware full-song processing"
    )
    return q


def test_default_quote_live_metadata_scope_and_no_upload(project):
    client = Client(project)
    q = G.quote_transcription(project, client=client)
    assert q["provider"] == "runware" and q["model"] == "google:gemini@3.1-flash-lite"
    assert q["estimate_usd"] is None and q["reserve_total_usd"] == "0.05"
    assert q["upload_reserve_usd"] == "0.01" and q["inference_reserve_usd"] == "0.04"
    assert q["published_pricing"] == schema()["info"]["x-pricing"]
    assert not client.uploads and not client.calls
    assert read_json(project / "work/tasks.json") == {}


def test_success_no_openai_key_flags_notes_actual_cost_and_no_replay(project, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = Client(project)
    q = quote(project, client)
    result = G.transcribe_quote(project, q["id"], client=client)
    assert result["status"] == "ready" and result["approved"] is False
    lyrics = read_json(project / "work/lyrics.json")
    assert lyrics["provider"] == "Runware" and lyrics["words"] == []
    assert len(lyrics["segments"][0]["flags"]) == 3
    assert "forced alignment" in lyrics["segments"][0]["flags"][1]
    assert read_json(project / "work/audio-notes.json")["notes"] == client.draft["music_notes"]
    ledger = read_json(project / "work/tasks.json")
    assert ledger[q["uuid"]]["cost_usd"] == "0.002"
    assert ledger[q["uuid"]]["usage"]["outputTokens"] == 200
    assert ledger[q["upload_uuid"]]["cost_usd"] is None
    assert G.costs(project)["unresolved_reservations_usd"] == "0.01"
    assert G.transcribe_quote(project, q["id"], client=client)["reused"]
    assert len(client.uploads) == len(client.calls) == 1
    with pytest.raises(ValueError, match="ack-uncertain"):
        P.approve(project, "lyrics", "test user")
    P.approve(project, "lyrics", "test user reviewed draft timing/text", True)


def test_upload_pending_recover_then_continue_same_quote(project):
    client = Client(project)
    client.pending_upload = True
    q = quote(project, client)
    assert G.transcribe_quote(project, q["id"], client=client)["status"] == "upload_pending"
    assert not client.calls
    with pytest.raises(ValueError, match="unresolved"):
        G.transcribe_quote(project, q["id"], client=client)
    with pytest.raises(ValueError, match="unresolved"):
        G.quote_transcription(project, client=client)
    assert not G.recover(project, q["upload_uuid"], client)
    client.pending_upload = False
    assert G.recover(project, q["upload_uuid"], client)
    assert G.transcribe_quote(project, q["id"], client=client)["status"] == "ready"
    assert len(client.uploads) == len(client.calls) == 1


def test_text_pending_recovery_no_submission_repeats(project):
    client = Client(project)
    client.pending_text = True
    q = quote(project, client)
    assert G.transcribe_quote(project, q["id"], client=client)["status"] == "transcription_pending"
    with pytest.raises(ValueError, match="recover"):
        G.transcribe_quote(project, q["id"], client=client)
    assert not G.recover(project, q["uuid"], client)
    client.pending_text = False
    assert G.recover(project, q["uuid"], client)
    assert len(client.calls) == len(client.uploads) == 1


@pytest.mark.parametrize("step", ["upload", "text"])
def test_ambiguous_network_errors_require_recovery_not_resubmission(project, step):
    client = Client(project)
    setattr(client, f"{step}_error", "network_error")
    q = quote(project, client)
    with pytest.raises(ProviderError):
        G.transcribe_quote(project, q["id"], client=client)
    with pytest.raises(ValueError):
        G.transcribe_quote(project, q["id"], client=client)
    assert len(client.uploads) == 1 and len(client.calls) == (step == "text")
    assert G.recover(project, q["upload_uuid"] if step == "upload" else q["uuid"], client)


def test_two_quoted_scopes_cannot_duplicate_upload(project):
    client = Client(project)
    first = quote(project, client)
    second = quote(project, client)
    client.pending_text = True
    G.transcribe_quote(project, first["id"], client=client)
    with pytest.raises(ValueError, match="unresolved"):
        G.transcribe_quote(project, second["id"], client=client)
    assert len(client.uploads) == len(client.calls) == 1


def test_rejected_inference_reconciled_new_quote_reuses_audio(project):
    client = Client(project)
    client.text_error = "http_error"
    first = quote(project, client)
    with pytest.raises(ProviderError):
        G.transcribe_quote(project, first["id"], client=client)
    G.resolve_task(
        project, first["uuid"], "0", "Test user verified request rejected with no charge"
    )
    client.text_error = None
    second = quote(project, client)
    assert second["reuse_upload"] and second["upload_uuid"] == first["upload_uuid"]
    assert second["upload_reserve_usd"] == "0"
    G.transcribe_quote(project, second["id"], client=client)
    assert len(client.uploads) == 1 and len(client.calls) == 2


@pytest.mark.parametrize(
    "failure", ["length", "blocked", "malformed", "overlap", "beyond", "empty", "booltime"]
)
def test_invalid_billed_outputs_saved_before_rejection(project, failure):
    client = Client(project)
    if failure == "length":
        client.reason = "length"
    elif failure == "blocked":
        client.reason = "content_filter"
    elif failure == "malformed":
        client.raw_text = "not json"
    elif failure == "overlap":
        client.draft["segments"].append({**client.draft["segments"][0], "start": 1.0, "end": 3.0})
    elif failure == "beyond":
        client.draft["segments"][0]["end"] = 5.0
    elif failure == "empty":
        client.draft["segments"] = []
    else:
        client.draft["segments"][0]["start"] = True
    q = quote(project, client)
    with pytest.raises(ValueError, match="raw result retained"):
        G.transcribe_quote(project, q["id"], client=client)
    task = read_json(project / "work/tasks.json")[q["uuid"]]
    assert task["status"] == "invalid" and task["cost_usd"] == "0.002"
    assert (project / task["raw_path"]).exists() and not (project / "work/lyrics.json").exists()
    with pytest.raises(ValueError, match="already submitted"):
        G.transcribe_quote(project, q["id"], client=client)
    new = quote(project, client)
    assert new["reuse_upload"] and len(client.uploads) == len(client.calls) == 1


def test_recovery_does_not_clobber_imported_or_corrected_lyrics(project):
    client = Client(project)
    client.pending_text = True
    q = quote(project, client)
    G.transcribe_quote(project, q["id"], client=client)
    corrected = {"provider": "manual", "segments": []}
    write_json(project / "work/lyrics.json", corrected)
    client.pending_text = False
    with pytest.raises(ValueError, match="refusing to overwrite"):
        G.recover(project, q["uuid"], client)
    assert read_json(project / "work/lyrics.json") == corrected
    assert G.costs(project)["reported_or_calculated_usd"] == "0.002"
    assert read_json(project / "work/tasks.json")[q["uuid"]]["status"] == "conflict"


def test_lost_lyrics_recovered_from_saved_result_without_provider_call(project):
    client = Client(project)
    q = quote(project, client)
    G.transcribe_quote(project, q["id"], client=client)
    (project / "work/lyrics.json").unlink()
    with pytest.raises(ValueError, match="missing lyrics"):
        G.transcribe_quote(project, q["id"], client=client)
    assert G.recover(project, q["uuid"], client)
    assert not client.polls and len(client.calls) == 1


def test_approval_and_authorization_gates_before_upload(project):
    client = Client(project)
    q = G.quote_transcription(project, client=client)
    with pytest.raises(ValueError, match="authorization"):
        G.transcribe_quote(project, q["id"], client=client)
    G.authorize(project, q["id"], "0.05", "test user")
    write_json(project / "work/music.json", {"duration": 4, "beats": [1]})
    with pytest.raises(ValueError, match="analysis"):
        G.transcribe_quote(project, q["id"], client=client)
    assert not client.uploads and not client.calls


def test_missing_runware_key_no_upload_or_journal(project, monkeypatch):
    monkeypatch.delenv("PROJECT_VEIL_RUNWARE_API", raising=False)
    monkeypatch.setenv("MP3_TO_VIDEOCLIP_RUNWARE_API_KEY", "mock-old-project-key-must-not-be-used")
    monkeypatch.setenv("RUNWARE_API_KEY", "mock-other-project-key-must-not-be-used")
    client = Client(project)
    q = quote(project, client)
    with pytest.raises(ValueError, match="no audio upload"):
        G.transcribe_quote(project, q["id"])
    assert read_json(project / "work/tasks.json") == {}


def test_mutated_quote_and_request_identity_do_not_upload(project):
    client = Client(project)
    q = quote(project, client)
    q["request"]["taskUUID"] = str(uuid4())
    write_json(project / f"work/quotes/{q['id']}.json", q)
    with pytest.raises(ValueError, match="authorization"):
        G.transcribe_quote(project, q["id"], client=client)
    G.authorize(project, q["id"], "0.05", "test user approved edited artifact")
    with pytest.raises(ValueError, match="identity"):
        G.transcribe_quote(project, q["id"], client=client)
    assert not client.uploads


def test_actual_overrun_retained_and_no_resubmit(project):
    client = Client(project)
    client.cost = 0.06
    q = quote(project, client)
    with pytest.raises(ValueError, match="exceeded"):
        G.transcribe_quote(project, q["id"], client=client)
    assert G.costs(project)["reported_or_calculated_usd"] == "0.06"
    assert G.transcribe_quote(project, q["id"], client=client)["reused"]
    assert len(client.calls) == 1


def test_local_safety_limit_and_model_capability_preflight(project, monkeypatch):
    client = Client(project)
    monkeypatch.setattr(T, "MAX_TRANSCRIBE_BYTES", 1)
    with pytest.raises(ValueError, match="local 25 MB"):
        G.quote_transcription(project, client=client)
    assert read_json(project / "work/tasks.json") == {}
    monkeypatch.setattr(T, "MAX_TRANSCRIBE_BYTES", 25000000)
    wrong = schema()
    wrong["info"]["x-capabilities"] = ["text-to-text"]
    client.schema = lambda _: wrong
    with pytest.raises(ValueError, match="audio input"):
        G.quote_transcription(project, client=client)


def test_cli_default_and_provider_recovery_dispatch(project, monkeypatch):
    args = parser().parse_args(["quote-transcription", str(project)])
    assert args.provider == "runware" and args.reserve == "0.05"
    legacy = parser().parse_args(["quote-transcription", str(project), "--provider", "openai"])
    assert legacy.provider == "openai"
    client = Client(project)
    q = quote(project, client)
    client.pending_text = True
    monkeypatch.setattr(T, "_client", lambda _: (client, False))
    result = execute(parser().parse_args(["transcribe", str(project), "--quote", q["id"]]))
    assert result["status"] == "transcription_pending"
    client.pending_text = False
    result = execute(parser().parse_args(["recover", str(project), "--task", q["uuid"]]))
    assert result["recovered"] is True


def test_legacy_quotes_stay_openai(project, monkeypatch):
    q = G.quote_transcription(project, provider="openai")
    assert q["model"] == "whisper-1" and "provider" not in q
    G.authorize(project, q["id"], "0.01", "test user approved original OpenAI scope")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        G.transcribe_quote(project, q["id"], client=Client(project))
    assert read_json(project / "work/tasks.json") == {}


def test_recover_after_user_corrections_preserves_ready_status(project):
    client = Client(project)
    q = quote(project, client)
    G.transcribe_quote(project, q["id"], client=client)
    corrected = read_json(project / "work/lyrics.json")
    corrected["segments"][0]["text"] = "User corrected the words"
    write_json(project / "work/lyrics.json", corrected)
    with pytest.raises(ValueError, match="refusing to overwrite"):
        G.recover(project, q["uuid"], client)
    assert read_json(project / "work/lyrics.json") == corrected
    assert read_json(project / "work/tasks.json")[q["uuid"]]["status"] == "ready"
    assert G.transcribe_quote(project, q["id"], client=client)["reused"]
    assert len(client.uploads) == len(client.calls) == 1


@pytest.mark.parametrize("field", ["uuid", "upload_uuid"])
def test_reauthorized_non_uuid_identifiers_cannot_write_or_upload(project, field):
    client = Client(project)
    q = quote(project, client)
    q[field] = "../../project"
    if field == "uuid":
        q["request"]["taskUUID"] = q[field]
    write_json(project / f"work/quotes/{q['id']}.json", q)
    G.authorize(project, q["id"], "0.05", "test user reauthorized edited artifact")
    with pytest.raises(ValueError, match="UUID"):
        G.transcribe_quote(project, q["id"], client=client)
    assert not client.uploads and not client.calls
    assert read_json(project / "work/tasks.json") == {}


def test_resolved_upload_requires_new_quote_not_recovery(project):
    client = Client(project)
    client.upload_error = "http_error"
    q = quote(project, client)
    with pytest.raises(ProviderError):
        G.transcribe_quote(project, q["id"], client=client)
    G.resolve_task(
        project, q["upload_uuid"], "0", "Test user verified upload rejected, not stored or charged"
    )
    with pytest.raises(ValueError, match="new quote"):
        G.transcribe_quote(project, q["id"], client=client)
    with pytest.raises(ValueError, match="reconciled"):
        G.recover(project, q["upload_uuid"], client)
    new = quote(project, client)
    assert new["upload_uuid"] != q["upload_uuid"] and not new["reuse_upload"]


def test_invalid_runware_result_does_not_block_authorized_openai_alternative(project, monkeypatch):
    client = Client(project)
    client.reason = "length"
    q = quote(project, client)
    with pytest.raises(ValueError, match="invalid/incomplete"):
        G.transcribe_quote(project, q["id"], client=client)
    legacy = G.quote_transcription(project, provider="openai")
    G.authorize(project, legacy["id"], "0.01", "test user authorized explicit OpenAI alternative")
    monkeypatch.setenv("OPENAI_API_KEY", "mock-key")

    def fake_transcribe(*_):
        return {"duration": 4, "segments": [{"start": 0, "end": 1, "text": "Draft"}]}

    G.transcribe_quote(project, legacy["id"], fake_transcribe)
    assert read_json(project / "work/lyrics.json")["provider"] == "OpenAI"
    assert len(client.calls) == 1


def test_checkpointed_upload_result_recovers_without_lookup_or_duplicate_upload(project):
    client = Client(project)
    original_upload = client.upload_audio

    def crash_after_response(uuid, source, expected, *, on_response=None):
        original_upload(uuid, source, expected, on_response=on_response)
        raise ProviderError("invalid_response")

    client.upload_audio = crash_after_response
    q = quote(project, client)
    with pytest.raises(ProviderError):
        G.transcribe_quote(project, q["id"], client=client)
    task = read_json(project / "work/tasks.json")[q["upload_uuid"]]
    assert task["upload_response"]["mediaUUID"] == client.media
    assert G.recover(project, q["upload_uuid"], client)
    assert not client.polls and len(client.uploads) == 1
    assert G.transcribe_quote(project, q["id"], client=client)["status"] == "ready"
    assert len(client.calls) == 1


def test_changed_media_handle_is_never_silently_replaced(project):
    client = Client(project)
    client.pending_text = True
    q = quote(project, client)
    G.transcribe_quote(project, q["id"], client=client)
    bad = client.upload_result(q["upload_uuid"])
    bad["mediaUUID"] = str(uuid4())
    with pytest.raises(ValueError, match="handle changed"):
        T.finish_upload(project, q["upload_uuid"], bad)
    assert (
        read_json(project / "work/tasks.json")[q["upload_uuid"]]["result"]["mediaUUID"]
        == client.media
    )
