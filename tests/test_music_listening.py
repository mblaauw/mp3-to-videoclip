"""Listening-pass workflow tests: no cloud calls/uploads, all clients are fake."""

import copy
import json
from uuid import uuid4

import pytest

from mp3_to_videoclip import generation as G
from mp3_to_videoclip import music_analysis as M
from mp3_to_videoclip.models import ListeningDraft, Project
from mp3_to_videoclip.providers import ProviderError
from mp3_to_videoclip.storage import digest, file_hash, read_json, write_json


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


def passage(start, end, label="a passage"):
    return {
        "start": start,
        "end": end,
        "label": label,
        "groove": "slow half-time pulse with a light shuffle",
        "texture": ["sub bass", "room tone", "distant pad"],
        "energy": "low",
        "tension": "medium",
        "transition": "a sustained pad fades in over the low pulse",
        "vocal_hook": None,
        "confidence": "low",
        "evidence": "low sustained tones under a sparse, quiet mix",
        "uncertainty": "no intelligible vocal and no confirmable metre",
    }


def test_internal_uncovered_intervals_are_rejected():
    draft = ListeningDraft(
        passages=[passage(0, 1), passage(9, 10)], overall_observations=[], limitations=[]
    )
    with pytest.raises(ValueError, match="uncovered interval"):
        M._validated_draft(draft, 10)


def test_thinking_level_follows_selected_model_schema(project):
    client = Client(project)
    contract = schema()
    contract["components"]["schemas"]["RequestBody"]["items"]["properties"]["settings"] = {
        "type": "object",
        "properties": {
            "temperature": {},
            "maxTokens": {},
            "thinkingLevel": {"enum": ["low", "medium", "high"]},
        },
    }
    client.schema = lambda _: contract
    quote = M.quote_music(project, client=client)
    assert quote["request"]["settings"]["thinkingLevel"] == "low"
    assert not client.calls and not client.uploads


def test_text_only_model_receives_explicit_json_contract_not_unsupported_fields(project):
    client = Client(project)
    contract = schema()
    props = contract["components"]["schemas"]["RequestBody"]["items"]["properties"]
    props["outputFormat"] = {"enum": ["TEXT"]}
    props.pop("jsonSchema")
    client.schema = lambda _: contract
    quote = M.quote_music(project, client=client)
    request = quote["request"]
    assert request["outputFormat"] == "TEXT" and "jsonSchema" not in request
    assert '"passages"' in request["messages"][0]["content"]
    assert "no provider schema enforcement" in quote["output_contract"]
    assert not client.calls and not client.uploads


def test_text_output_may_remove_one_enclosing_fence_without_changing_json(project):
    client = Client(project)
    contract = schema()
    props = contract["components"]["schemas"]["RequestBody"]["items"]["properties"]
    props["outputFormat"] = {"enum": ["TEXT"]}
    props.pop("jsonSchema")
    client.schema = lambda _: contract
    quote = M.quote_music(project, client=client)
    G.authorize(project, quote["id"], "0.05", "test user")
    client.raw_text = "```json\n" + json.dumps(client.draft) + "\n```"
    M.run_music(project, quote["id"], client)
    value = M.load_listening(project)
    assert value["draft"]["passages"] == client.draft["passages"]
    assert any("Markdown fence" in note for note in value["draft"]["limitations"])
    raw = read_json(project / f"work/music-listening/{quote['uuid']}.json")
    assert raw["text"] == client.raw_text


def test_text_output_fence_without_newline_before_close_is_accepted(project):
    client = Client(project)
    contract = schema()
    props = contract["components"]["schemas"]["RequestBody"]["items"]["properties"]
    props["outputFormat"] = {"enum": ["TEXT"]}
    props.pop("jsonSchema")
    client.schema = lambda _: contract
    quote = M.quote_music(project, client=client)
    G.authorize(project, quote["id"], "0.05", "test user")
    client.raw_text = "```json\n" + json.dumps(client.draft) + "```"
    M.run_music(project, quote["id"], client)
    value = M.load_listening(project)
    assert value["draft"]["passages"] == client.draft["passages"]
    assert any("Markdown fence" in note for note in value["draft"]["limitations"])


def test_explicit_refinement_archives_unreviewed_draft_and_reuses_upload(project):
    client = Client(project)
    first = M.quote_music(project, client=client)
    G.authorize(project, first["id"], "0.05", "test user approved analysis")
    M.run_music(project, first["id"], client)
    original = read_json(project / M.LISTENING_PATH)
    second = M.quote_music(project, client=client, refine=True)
    assert second["reuse_upload"] and second["refines_hash"] == digest(original)
    assert second["max_passage_seconds"] == 20
    assert (
        "measured" not in second["request"]["messages"][0]["content"]
        or "checkpoints" in second["request"]["messages"][0]["content"]
    )
    G.authorize(project, second["id"], "0.05", "test user approved explicit refinement")
    client.draft = copy.deepcopy(client.draft)
    client.draft["passages"][0]["label"] = "More specific description"
    M.run_music(project, second["id"], client)
    history = project / f"work/music-listening-history/{digest(original)}.json"
    assert read_json(history) == original
    assert read_json(project / M.LISTENING_PATH)["task_uuid"] == second["uuid"]
    assert len(client.uploads) == 1 and len(client.calls) == 2


def test_refinement_refuses_changed_or_reviewed_draft(project):
    client = Client(project)
    first = M.quote_music(project, client=client)
    G.authorize(project, first["id"], "0.05", "test user approved analysis")
    M.run_music(project, first["id"], client)
    second = M.quote_music(project, client=client, refine=True)
    G.authorize(project, second["id"], "0.05", "test user approved explicit refinement")
    changed = read_json(project / M.LISTENING_PATH)
    changed["draft"]["passages"][0]["label"] = "User correction"
    write_json(project / M.LISTENING_PATH, changed)
    with pytest.raises(ValueError, match="changed since"):
        M.run_music(project, second["id"], client)
    write_json(project / "work/approvals.json", {"listening": {"hash": "test-reviewed"}})
    with pytest.raises(ValueError, match="reviewed"):
        M.quote_music(project, client=client, refine=True)
    assert len(client.calls) == 1


def test_deleted_refinement_target_does_not_allow_a_paid_submission(project):
    client = Client(project)
    first = M.quote_music(project, client=client)
    G.authorize(project, first["id"], "0.05", "test user approved analysis")
    M.run_music(project, first["id"], client)
    second = M.quote_music(project, client=client, refine=True)
    G.authorize(project, second["id"], "0.05", "test user approved explicit refinement")
    (project / M.LISTENING_PATH).unlink()
    with pytest.raises(ValueError, match="target is missing"):
        M.run_music(project, second["id"], client)
    assert len(client.calls) == 1 and len(client.uploads) == 1


def listening_draft():
    return {
        "passages": [
            passage(0.0, 0.75, "sparse opening"),
            passage(0.75, 2.5, "pulse and pad"),
            passage(2.5, 4.0, "release"),
        ],
        "overall_observations": ["Subjective: patient and dark; no confirmed tempo or key."],
        "limitations": ["No time signature, key or instrument list could be confirmed."],
    }


@pytest.fixture
def project(tmp_path):
    """No approvals are recorded: a listening pass must not require an analysis approval."""
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
        self.draft = listening_draft()
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
        assert task["status"] == "submitted" and task["kind"] == "music-analysis"
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


def quote(root, client, cap="0.50"):
    q = M.quote_music(root, client=client)
    G.authorize(root, q["id"], cap, "test user authorized upload and one listening pass")
    return q


def test_quote_binds_source_and_local_analysis_without_upload_or_approval(project):
    client = Client(project)
    q = M.quote_music(project, client=client)
    assert q["kind"] == "music-analysis" and q["provider"] == "runware"
    assert q["model"] == "google:gemini@3.1-flash-lite" and q["model_slug"] == M.DEFAULT_MUSIC_MODEL
    assert q["source_hash"] == file_hash(project / "media/song.mp3")
    assert q["analysis_hash"] == digest(read_json(project / "work/music.json"))
    assert q["estimate_usd"] is None and "provider-enforced cap" in q["warning"]
    assert q["reserve_total_usd"] == "0.05"
    assert q["upload_reserve_usd"] == "0.01" and q["inference_reserve_usd"] == "0.04"
    assert q["reuse_upload"] is False and q["published_pricing"] == schema()["info"]["x-pricing"]
    assert not client.uploads and not client.calls
    assert read_json(project / "work/tasks.json") == {}
    assert read_json(project / "work/approvals.json") == {}


def test_quote_requires_existing_local_analysis(project):
    (project / "work/music.json").unlink()
    with pytest.raises(ValueError, match="local music analysis is missing"):
        M.quote_music(project, client=Client(project))


def test_quote_rejects_unconfirmed_or_wrong_modality_models(project):
    client = Client(project)
    wrong = schema()
    wrong["info"]["x-capabilities"] = ["text-to-text"]
    client.schema = lambda _: wrong
    with pytest.raises(ValueError, match="audio input"):
        M.quote_music(project, client=client)
    wrong = schema()
    wrong["info"]["x-status"] = "draft"
    client.schema = lambda _: wrong
    with pytest.raises(ValueError, match="live"):
        M.quote_music(project, client=client)
    assert read_json(project / "work/tasks.json") == {}


def test_reservation_and_authorization_gate_before_upload(project):
    client = Client(project)
    q = M.quote_music(project, client=client)
    with pytest.raises(ValueError, match="authorization"):
        M.run_music(project, q["id"], client=client)
    with pytest.raises(ValueError, match="cap must cover"):
        G.authorize(project, q["id"], "0.04", "test user authorized too little")
    G.authorize(project, q["id"], "0.50", "test user authorized the full-song listening pass")
    assert not client.uploads and not client.calls
    assert read_json(project / "work/tasks.json") == {}


def test_listening_pass_needs_no_analysis_approval(project):
    client = Client(project)
    q = quote(project, client)
    assert read_json(project / "work/approvals.json") == {}
    result = M.run_music(project, q["id"], client=client)
    assert result["status"] == "ready" and result["approved"] is False
    artifact = M.load_listening(project)
    assert artifact["task_uuid"] == q["uuid"] and artifact["model"] == q["model"]
    assert len(artifact["draft"]["passages"]) == 3
    assert M.PROVENANCE_LIMITATION in artifact["draft"]["limitations"]
    assert artifact["warning"] == M.UNREVIEWED_WARNING


@pytest.mark.parametrize("changed", ["analysis", "source"])
def test_changed_analysis_or_source_blocks_the_upload(project, changed):
    client = Client(project)
    q = quote(project, client)
    if changed == "analysis":
        write_json(project / "work/music.json", {"duration": 4, "beats": [1.0]})
        expected = "analysis changed since quote"
    else:
        (project / "media/song.mp3").write_bytes(b"different local audio bytes")
        config = Project.model_validate(read_json(project / "project.json"))
        config = config.model_copy(update={"source_sha256": file_hash(project / "media/song.mp3")})
        write_json(project / "project.json", config.model_dump())
        expected = "source changed since quote"
    with pytest.raises(ValueError, match=expected):
        M.run_music(project, q["id"], client=client)
    assert not client.uploads and not client.calls
    assert read_json(project / "work/tasks.json") == {}


def test_ready_reuse_never_replays_the_paid_pass(project):
    client = Client(project)
    q = quote(project, client)
    result = M.run_music(project, q["id"], client=client)
    assert result["status"] == "ready" and result["listening"].endswith("music-listening.json")
    again = M.run_music(project, q["id"], client=client)
    assert again["reused"] is True
    assert len(client.uploads) == len(client.calls) == 1 and not client.polls
    ledger = read_json(project / "work/tasks.json")
    assert ledger[q["uuid"]]["cost_usd"] == "0.002"
    assert ledger[q["uuid"]]["usage"]["outputTokens"] == 200
    assert ledger[q["upload_uuid"]]["cost_usd"] is None
    assert G.costs(project)["unresolved_reservations_usd"] == "0.01"


def test_upload_pending_recovers_then_continues_same_quote(project):
    client = Client(project)
    client.pending_upload = True
    q = quote(project, client)
    assert M.run_music(project, q["id"], client=client)["status"] == "upload_pending"
    assert not client.calls
    with pytest.raises(ValueError, match="unresolved"):
        M.run_music(project, q["id"], client=client)
    with pytest.raises(ValueError, match="unresolved"):
        M.quote_music(project, client=client)
    assert not M.recover_music(project, q["upload_uuid"], client)
    client.pending_upload = False
    assert M.recover_music(project, q["upload_uuid"], client)
    assert M.run_music(project, q["id"], client=client)["status"] == "ready"
    assert len(client.uploads) == len(client.calls) == 1


def test_text_pending_recovery_without_resubmission(project):
    client = Client(project)
    client.pending_text = True
    q = quote(project, client)
    assert M.run_music(project, q["id"], client=client)["status"] == "listening_pending"
    with pytest.raises(ValueError, match="recover"):
        M.run_music(project, q["id"], client=client)
    assert not M.recover_music(project, q["uuid"], client)
    client.pending_text = False
    assert M.recover_music(project, q["uuid"], client)
    assert len(client.polls) == 2 and len(client.calls) == 1 and len(client.uploads) == 1
    assert M.load_listening(project)["task_uuid"] == q["uuid"]


def test_checkpointed_upload_result_recovers_without_a_duplicate_upload(project):
    client = Client(project)
    original_upload = client.upload_audio

    def crash_after_response(uuid, source, expected, *, on_response=None):
        original_upload(uuid, source, expected, on_response=on_response)
        raise ProviderError("invalid_response")

    client.upload_audio = crash_after_response
    q = quote(project, client)
    with pytest.raises(ProviderError):
        M.run_music(project, q["id"], client=client)
    task = read_json(project / "work/tasks.json")[q["upload_uuid"]]
    assert task["upload_response"]["mediaUUID"] == client.media
    assert M.recover_music(project, q["upload_uuid"], client)
    assert not client.polls and len(client.uploads) == 1
    assert M.run_music(project, q["id"], client=client)["status"] == "ready"
    assert len(client.calls) == 1


@pytest.mark.parametrize(
    "failure", ["length", "blocked", "malformed", "overlap", "reversed", "beyond", "gap", "empty"]
)
def test_invalid_billed_listening_is_priced_before_parsing(project, failure):
    client = Client(project)
    if failure == "length":
        client.reason = "length"
    elif failure == "blocked":
        client.reason = "content_filter"
    elif failure == "malformed":
        client.raw_text = "not json"
    elif failure == "overlap":
        client.draft["passages"][1]["start"] = 0.5
    elif failure == "reversed":
        client.draft["passages"][1].update({"start": 3.0, "end": 1.0})
    elif failure == "beyond":
        client.draft["passages"][-1]["end"] = 4.2
    elif failure == "gap":
        client.draft["passages"] = client.draft["passages"][:2]
        client.draft["passages"][1]["end"] = 2.0
    else:
        client.draft["passages"] = []
    q = quote(project, client)
    with pytest.raises(ValueError, match="raw result retained"):
        M.run_music(project, q["id"], client=client)
    task = read_json(project / "work/tasks.json")[q["uuid"]]
    assert task["status"] == "invalid" and task["cost_usd"] == "0.002"
    assert task["usage"]["outputTokens"] == 200
    assert (project / task["raw_path"]).exists()
    assert not (project / "work/music-listening.json").exists()
    assert G.costs(project)["reported_or_calculated_usd"] == "0.002"
    assert G.costs(project)["unresolved_reservations_usd"] == "0.01"
    with pytest.raises(ValueError, match="already submitted"):
        M.run_music(project, q["id"], client=client)
    new = M.quote_music(project, client=client)
    assert new["reuse_upload"] and new["upload_uuid"] == q["upload_uuid"]
    assert len(client.uploads) == len(client.calls) == 1


def test_final_end_rounding_overshoot_is_clamped_with_a_warning(project):
    client = Client(project)
    client.draft["passages"][-1]["end"] = 4.02
    q = quote(project, client)
    assert M.run_music(project, q["id"], client=client)["status"] == "ready"
    artifact = M.load_listening(project)
    assert artifact["draft"]["passages"][-1]["end"] == 4.0
    assert artifact["draft"]["passages"][1]["end"] == 2.5
    assert any("clamped" in note for note in artifact["draft"]["limitations"])
    raw = read_json(project / f"work/music-listening/{q['uuid']}.json")
    assert json.loads(raw["text"])["passages"][-1]["end"] == 4.02


def test_recovery_does_not_clobber_user_corrected_listening(project):
    client = Client(project)
    client.pending_text = True
    q = quote(project, client)
    M.run_music(project, q["id"], client=client)
    edited = {
        "source_sha256": file_hash(project / "media/song.mp3"),
        "duration": 4.0,
        "model": q["model"],
        "task_uuid": q["uuid"],
        "analysis_hash": digest(read_json(project / "work/music.json")),
        "draft": listening_draft(),
        "warning": "user edited listening notes",
    }
    write_json(project / "work/music-listening.json", edited)
    client.pending_text = False
    with pytest.raises(ValueError, match="refusing to overwrite"):
        M.recover_music(project, q["uuid"], client)
    assert read_json(project / "work/music-listening.json") == edited
    assert read_json(project / "work/tasks.json")[q["uuid"]]["status"] == "conflict"
    assert G.costs(project)["reported_or_calculated_usd"] == "0.002"


def test_recovery_after_a_user_edit_preserves_ready_status(project):
    client = Client(project)
    q = quote(project, client)
    M.run_music(project, q["id"], client=client)
    edited = read_json(project / "work/music-listening.json")
    edited["draft"]["passages"][0]["label"] = "user corrected label"
    write_json(project / "work/music-listening.json", edited)
    with pytest.raises(ValueError, match="refusing to overwrite"):
        M.recover_music(project, q["uuid"], client)
    assert read_json(project / "work/music-listening.json") == edited
    assert read_json(project / "work/tasks.json")[q["uuid"]]["status"] == "ready"
    assert M.load_listening(project)["draft"]["passages"][0]["label"] == "user corrected label"
    assert M.run_music(project, q["id"], client=client)["reused"] is True
    assert len(client.uploads) == len(client.calls) == 1


def test_lost_listening_draft_is_recovered_from_the_saved_result(project):
    client = Client(project)
    q = quote(project, client)
    M.run_music(project, q["id"], client=client)
    (project / "work/music-listening.json").unlink()
    with pytest.raises(ValueError, match="missing listening draft"):
        M.run_music(project, q["id"], client=client)
    assert M.recover_music(project, q["uuid"], client)
    assert not client.polls and len(client.calls) == 1


def test_two_quoted_listening_scopes_cannot_duplicate_upload(project):
    client = Client(project)
    first = quote(project, client)
    second = quote(project, client)
    client.pending_text = True
    M.run_music(project, first["id"], client=client)
    with pytest.raises(ValueError, match="unresolved"):
        M.run_music(project, second["id"], client=client)
    assert len(client.uploads) == len(client.calls) == 1


def test_pending_guard_is_separate_from_a_pending_transcription(project):
    other = str(uuid4())
    write_json(
        project / "work/tasks.json",
        {
            other: {
                "uuid": other,
                "kind": "transcription",
                "provider": "runware",
                "quote_id": "older-quote",
                "source_hash": file_hash(project / "media/song.mp3"),
                "status": "submitted",
                "cost_usd": None,
                "reserve_usd": "0.04",
            }
        },
    )
    client = Client(project)
    q = quote(project, client)
    assert M.run_music(project, q["id"], client=client)["status"] == "ready"
    assert len(client.uploads) == len(client.calls) == 1


def test_missing_runware_key_does_not_upload_or_journal(project, monkeypatch):
    monkeypatch.delenv("PROJECT_VEIL_RUNWARE_API", raising=False)
    monkeypatch.setenv("MP3_TO_VIDEOCLIP_RUNWARE_API_KEY", "mock-unused-key")
    monkeypatch.setenv("RUNWARE_API_KEY", "mock-unused-key")
    client = Client(project)
    q = quote(project, client)
    with pytest.raises(ValueError, match="no audio upload"):
        M.run_music(project, q["id"])
    assert read_json(project / "work/tasks.json") == {}


@pytest.mark.parametrize("field", ["uuid", "upload_uuid"])
def test_reauthorized_non_uuid_identifiers_cannot_upload(project, field):
    client = Client(project)
    q = quote(project, client)
    q[field] = "../../project"
    if field == "uuid":
        q["request"]["taskUUID"] = q[field]
    write_json(project / f"work/quotes/{q['id']}.json", q)
    G.authorize(project, q["id"], "0.50", "test user reauthorized an edited artifact")
    with pytest.raises(ValueError, match="UUID"):
        M.run_music(project, q["id"], client=client)
    assert not client.uploads and not client.calls
    assert read_json(project / "work/tasks.json") == {}


def test_mutated_request_identity_is_rejected_before_upload(project):
    client = Client(project)
    q = quote(project, client)
    q["model"] = "google:some-other-model"
    write_json(project / f"work/quotes/{q['id']}.json", q)
    G.authorize(project, q["id"], "0.50", "test user reauthorized an edited artifact")
    with pytest.raises(ValueError, match="identity"):
        M.run_music(project, q["id"], client=client)
    assert not client.uploads and not client.calls


def test_request_that_no_longer_matches_the_schema_is_rejected_before_upload(project):
    client = Client(project)
    q = quote(project, client)
    q["request"]["taskType"] = "imageInference"
    write_json(project / f"work/quotes/{q['id']}.json", q)
    G.authorize(project, q["id"], "0.50", "test user reauthorized an edited artifact")
    with pytest.raises(ValueError, match="rejected by model schema"):
        M.run_music(project, q["id"], client=client)
    assert not client.uploads and not client.calls


def test_actual_cost_overrun_stops_and_is_never_resubmitted(project):
    client = Client(project)
    client.cost = 0.06
    q = quote(project, client, cap="0.05")
    with pytest.raises(ValueError, match="exceeded"):
        M.run_music(project, q["id"], client=client)
    assert G.costs(project)["reported_or_calculated_usd"] == "0.06"
    assert M.run_music(project, q["id"], client=client)["reused"] is True
    assert len(client.calls) == 1


def test_rejected_inference_reconciled_new_quote_reuses_the_audio(project):
    client = Client(project)
    client.text_error = "http_error"
    first = quote(project, client)
    with pytest.raises(ProviderError):
        M.run_music(project, first["id"], client=client)
    G.resolve_task(
        project, first["uuid"], "0", "Test user verified the request was rejected before billing"
    )
    client.text_error = None
    second = M.quote_music(project, client=client)
    assert second["reuse_upload"] and second["upload_uuid"] == first["upload_uuid"]
    assert second["upload_reserve_usd"] == "0"
    G.authorize(project, second["id"], "0.50", "test user authorized the retry")
    assert M.run_music(project, second["id"], client=client)["status"] == "ready"
    assert len(client.uploads) == 1 and len(client.calls) == 2


def test_resolved_upload_needs_a_new_quote(project):
    client = Client(project)
    client.upload_error = "http_error"
    q = quote(project, client)
    with pytest.raises(ProviderError):
        M.run_music(project, q["id"], client=client)
    G.resolve_task(
        project, q["upload_uuid"], "0", "Test user verified the upload was rejected before storage"
    )
    with pytest.raises(ValueError, match="new quote"):
        M.run_music(project, q["id"], client=client)
    with pytest.raises(ValueError, match="reconciled"):
        M.recover_music(project, q["upload_uuid"], client)
    new = M.quote_music(project, client=client)
    assert new["upload_uuid"] != q["upload_uuid"] and not new["reuse_upload"]


def test_existing_listening_draft_blocks_new_quotes_and_recovery_is_read_only(project):
    client = Client(project)
    q = quote(project, client)
    M.run_music(project, q["id"], client=client)
    with pytest.raises(ValueError, match="already exists"):
        M.quote_music(project, client=client)
    assert M.recover_music(project, q["uuid"], client) and not client.polls


def test_recover_music_rejects_unknown_tasks(project):
    with pytest.raises(ValueError, match="unknown Runware music task"):
        M.recover_music(project, str(uuid4()), Client(project))


def test_load_listening_validates_shape_and_source_binding(project):
    with pytest.raises(FileNotFoundError):
        M.load_listening(project)
    client = Client(project)
    q = quote(project, client)
    M.run_music(project, q["id"], client=client)
    artifact = M.load_listening(project)
    assert set(artifact) == {
        "source_sha256",
        "duration",
        "model",
        "task_uuid",
        "analysis_hash",
        "draft",
        "warning",
    }
    artifact["source_sha256"] = "0" * 64
    write_json(project / "work/music-listening.json", artifact)
    with pytest.raises(ValueError, match="different source"):
        M.load_listening(project)
    artifact["source_sha256"] = file_hash(project / "media/song.mp3")
    artifact["duration"] = 9.0
    write_json(project / "work/music-listening.json", artifact)
    with pytest.raises(ValueError, match="duration does not match"):
        M.load_listening(project)
    artifact["duration"] = 4.0
    artifact["extra"] = "not part of the contract"
    write_json(project / "work/music-listening.json", artifact)
    with pytest.raises(ValueError):
        M.load_listening(project)
