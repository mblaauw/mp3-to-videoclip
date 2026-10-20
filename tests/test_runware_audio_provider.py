"""Mocked Runware audio-upload and text-inference contracts.

No live calls: every request goes through ``httpx.MockTransport``. These tests pin the
single-attempt, recovery-by-UUID behaviour and the exact wire encoding of the
``mediaStorage`` and ``textInference`` tasks.
"""

import base64
import hashlib
import json

import httpx
import pytest

from mp3_to_videoclip import providers
from mp3_to_videoclip.providers import ProviderError, RunwareClient

UUID = "a1b2c3d4-0000-4000-8000-000000000000"
OTHER_UUID = "ffffffff-0000-4000-8000-000000000000"
MEDIA_UUID = "b2c3d4e5-1111-4222-8333-444444444444"
KEY = "runware-secret-key"
MEDIA_URL = "https://im.runware.ai/audio/opaque-handle"


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def mp3_bytes() -> bytes:
    return b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"fake-mp3-frame" * 4


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_mp3(tmp_path, name="kortjakje.mp3"):
    path = tmp_path / name
    path.write_bytes(mp3_bytes())
    return path


def upload_result(**overrides):
    task = {
        "taskUUID": UUID,
        "taskType": "mediaStorage",
        "operation": "upload",
        "mediaUUID": MEDIA_UUID,
        "mediaURL": MEDIA_URL,
    }
    task.update(overrides)
    return task


def text_request(**overrides):
    request = {
        "taskType": "textInference",
        "taskUUID": UUID,
        "model": "google:gemma@4-31b",
        "inputs": {"audios": [MEDIA_UUID]},
        "messages": [{"role": "user", "content": "transcribe"}],
        "outputFormat": "JSON",
        "jsonSchema": {"type": "object"},
        "settings": {"maxTokens": 8192, "thinkingLevel": "minimal", "temperature": 0},
        "deliveryMethod": "async",
        "numberResults": 1,
    }
    request.update(overrides)
    return request


def test_submit_text_rejects_other_task_types_before_network():
    def handler(_):
        raise AssertionError("must not submit an incorrect taskType")

    with (
        RunwareClient(KEY, client_for(handler)) as rw,
        pytest.raises(ProviderError, match="invalid_request"),
    ):
        rw.submit_text(text_request(taskType="imageInference"))


# --------------------------------------------------------------------------- upload


def test_upload_audio_posts_canonical_media_storage_array(tmp_path):
    source = write_mp3(tmp_path)
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["method"] = request.method
        seen["auth"] = request.headers.get("authorization")
        seen["ctype"] = request.headers.get("content-type")
        seen["body"] = json.loads(request.read().decode())
        return httpx.Response(200, json={"data": [upload_result()]})

    with RunwareClient(KEY, client_for(handler)) as rw:
        result = rw.upload_audio(UUID, source, sha256_of(source.read_bytes()))

    assert result == {"taskUUID": UUID, "mediaUUID": MEDIA_UUID, "mediaURL": MEDIA_URL}
    assert seen["url"] == "https://api.runware.ai/v1"
    assert seen["method"] == "POST"
    assert seen["auth"] == f"Bearer {KEY}"
    assert seen["ctype"] == "application/json"
    assert isinstance(seen["body"], list) and len(seen["body"]) == 1
    task = seen["body"][0]
    encoded = base64.b64encode(source.read_bytes()).decode("ascii")
    assert task == {
        "taskType": "mediaStorage",
        "taskUUID": UUID,
        "operation": "upload",
        "media": f"data:audio/mpeg;base64,{encoded}",
    }
    # No unsupported cost/delivery/ttl fields are ever sent.
    assert set(task) == {"taskType", "taskUUID", "operation", "media"}


def test_upload_response_checkpoint_survives_validation_failure_without_input_echo(tmp_path):
    source = write_mp3(tmp_path)
    result = upload_result(
        operation="unexpected",
        media="base64-source-must-not-persist",
        apiKey=KEY,
        request={"media": "source-must-not-persist"},
    )
    saved = []
    with RunwareClient(
        KEY, client_for(lambda _: httpx.Response(200, json={"data": [result]}))
    ) as rw:
        with pytest.raises(ProviderError, match="invalid_response"):
            rw.upload_audio(UUID, source, sha256_of(source.read_bytes()), on_response=saved.append)
    assert len(saved) == 1 and saved[0]["mediaUUID"] == MEDIA_UUID
    assert saved[0]["operation"] == "unexpected"
    assert "media" not in saved[0] and "apiKey" not in saved[0] and "request" not in saved[0]


def test_upload_audio_hash_mismatch_never_calls_network(tmp_path):
    source = write_mp3(tmp_path)
    calls = []

    def handler(request):  # pragma: no cover - must never run
        calls.append(request)
        return httpx.Response(200, json={})

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).upload_audio(UUID, source, "0" * 64)
    assert excinfo.value.code == "source_changed"
    assert calls == []


def test_upload_audio_rejects_oversize_before_upload(tmp_path, monkeypatch):
    monkeypatch.setattr(providers, "MAX_TRANSCRIBE_BYTES", 4)
    source = write_mp3(tmp_path)
    calls = []

    def handler(request):  # pragma: no cover - must never run
        calls.append(request)
        return httpx.Response(200, json={})

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).upload_audio(
            UUID, source, sha256_of(source.read_bytes())
        )
    assert excinfo.value.code == "source_too_large"
    assert calls == []


def test_upload_audio_rejects_non_mp3_suffix(tmp_path):
    source = tmp_path / "song.wav"
    source.write_bytes(mp3_bytes())
    calls = []

    def handler(request):  # pragma: no cover - must never run
        calls.append(request)
        return httpx.Response(200, json={})

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).upload_audio(UUID, source, sha256_of(mp3_bytes()))
    assert excinfo.value.code == "unsupported_audio"
    assert calls == []


def test_upload_audio_missing_source_is_controlled(tmp_path):
    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(lambda r: httpx.Response(200))).upload_audio(
            UUID, tmp_path / "missing.mp3", "0" * 64
        )
    assert excinfo.value.code == "source_unreadable"


@pytest.mark.parametrize("task_uuid", ["", None, 5])
def test_upload_audio_requires_task_uuid(tmp_path, task_uuid):
    source = write_mp3(tmp_path)
    calls = []

    def handler(request):  # pragma: no cover - must never run
        calls.append(request)
        return httpx.Response(200, json={})

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).upload_audio(
            task_uuid, source, sha256_of(source.read_bytes())
        )
    assert excinfo.value.code == "invalid_request"
    assert calls == []


def test_upload_audio_requires_sha256_shaped_hash(tmp_path):
    source = write_mp3(tmp_path)
    calls = []

    def handler(request):  # pragma: no cover - must never run
        calls.append(request)
        return httpx.Response(200, json={})

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).upload_audio(UUID, source, "not-a-hash")
    assert excinfo.value.code == "invalid_request"
    assert calls == []


def test_upload_audio_pending_returns_task_uuid_only(tmp_path):
    source = write_mp3(tmp_path)

    def handler(request):
        return httpx.Response(200, json={"data": [{"taskUUID": UUID, "status": "processing"}]})

    result = RunwareClient(KEY, client_for(handler)).upload_audio(
        UUID, source, sha256_of(source.read_bytes())
    )
    assert result == {"taskUUID": UUID}


def test_upload_audio_mismatched_task_is_rejected(tmp_path):
    source = write_mp3(tmp_path)

    def handler(request):
        return httpx.Response(200, json={"data": [upload_result(taskUUID=OTHER_UUID)]})

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).upload_audio(
            UUID, source, sha256_of(source.read_bytes())
        )
    assert excinfo.value.code == "mismatched_task"


def test_upload_audio_accepts_live_response_without_operation(tmp_path):
    """Pin the live mediaStorage shape: no "operation" (or "status") key."""
    source = write_mp3(tmp_path)
    live = {
        "taskType": "mediaStorage",
        "taskUUID": UUID,
        "mediaUUID": MEDIA_UUID,
        "mediaURL": MEDIA_URL,
    }

    def handler(request):
        return httpx.Response(200, json={"data": [live]})

    result = RunwareClient(KEY, client_for(handler)).upload_audio(
        UUID, source, sha256_of(source.read_bytes())
    )
    assert result == {"taskUUID": UUID, "mediaUUID": MEDIA_UUID, "mediaURL": MEDIA_URL}


def test_upload_audio_non_upload_operation_is_invalid_response(tmp_path):
    source = write_mp3(tmp_path)

    def handler(request):
        return httpx.Response(200, json={"data": [upload_result(operation="download")]})

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).upload_audio(
            UUID, source, sha256_of(source.read_bytes())
        )
    assert excinfo.value.code == "invalid_response"


@pytest.mark.parametrize(
    "url",
    ["http://im.runware.ai/x", "https://127.0.0.1/x", "https://user:pw@im.runware.ai/x", ""],
)
def test_upload_audio_rejects_unsafe_media_url(tmp_path, url):
    source = write_mp3(tmp_path)

    def handler(request):
        return httpx.Response(200, json={"data": [upload_result(mediaURL=url)]})

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).upload_audio(
            UUID, source, sha256_of(source.read_bytes())
        )
    assert excinfo.value.code in {"unsafe_url", "invalid_media_url"}


def test_upload_audio_http_error_is_single_attempt_and_redacted(tmp_path):
    source = write_mp3(tmp_path)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(500, text=f"upstream leak {KEY}")

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).upload_audio(
            UUID, source, sha256_of(source.read_bytes())
        )
    assert excinfo.value.code == "http_error"
    assert excinfo.value.status == 500
    assert len(calls) == 1
    assert KEY not in str(excinfo.value)


def test_upload_audio_http_error_unknown_code_is_not_echoed(tmp_path):
    source = write_mp3(tmp_path)

    def handler(request):
        return httpx.Response(
            400,
            json={"data": [], "errors": [{"code": "mysteryCode", "message": f"leak {KEY}"}]},
        )

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).upload_audio(
            UUID, source, sha256_of(source.read_bytes())
        )
    assert excinfo.value.code == "http_error"
    assert excinfo.value.status == 400
    assert KEY not in str(excinfo.value)


def test_upload_audio_upstream_error_uses_safe_code_only(tmp_path):
    source = write_mp3(tmp_path)

    def handler(request):
        return httpx.Response(
            200, json={"errors": [{"code": "invalidApiKey", "message": f"bad {KEY}"}]}
        )

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).upload_audio(
            UUID, source, sha256_of(source.read_bytes())
        )
    assert excinfo.value.code == "invalidApiKey"
    assert KEY not in str(excinfo.value)


# --------------------------------------------------------------------------- upload recovery


def details_response(task_uuid=UUID, original=None):
    original = upload_result() if original is None else original
    return {
        "data": [
            {
                "taskUUID": task_uuid,
                "taskType": "getTaskDetails",
                "request": [{"taskType": "mediaStorage", "media": f"data:audio/mpeg;base64,{KEY}"}],
                "response": {"data": [original]},
            }
        ]
    }


def test_recover_audio_upload_get_task_details_returns_canonical():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.read().decode())
        return httpx.Response(200, json=details_response())

    result = RunwareClient(KEY, client_for(handler)).recover_audio_upload(UUID)
    assert seen["body"] == [{"taskType": "getTaskDetails", "taskUUID": UUID}]
    assert result == {"taskUUID": UUID, "mediaUUID": MEDIA_UUID, "mediaURL": MEDIA_URL}


def test_recover_audio_upload_does_not_expose_original_request():
    def handler(request):
        return httpx.Response(200, json=details_response())

    result = RunwareClient(KEY, client_for(handler)).recover_audio_upload(UUID)
    assert set(result) == {"taskUUID", "mediaUUID", "mediaURL"}
    assert KEY not in json.dumps(result)


def test_recover_audio_upload_mismatch_or_pending_or_empty_returns_none():
    def outer_mismatch(request):
        return httpx.Response(200, json=details_response(task_uuid=OTHER_UUID))

    assert RunwareClient(KEY, client_for(outer_mismatch)).recover_audio_upload(UUID) is None

    def inner_mismatch(request):
        return httpx.Response(
            200, json=details_response(original=upload_result(taskUUID=OTHER_UUID))
        )

    assert RunwareClient(KEY, client_for(inner_mismatch)).recover_audio_upload(UUID) is None

    def pending(request):
        return httpx.Response(
            200, json={"data": [{"taskUUID": UUID, "taskType": "getTaskDetails"}]}
        )

    assert RunwareClient(KEY, client_for(pending)).recover_audio_upload(UUID) is None

    def empty(request):
        return httpx.Response(200, json={"data": []})

    assert RunwareClient(KEY, client_for(empty)).recover_audio_upload(UUID) is None


def test_recover_audio_upload_error_status_raises_controlled():
    def handler(request):
        return httpx.Response(
            200, json={"data": [{"taskUUID": UUID, "status": "error", "code": "taskNotFound"}]}
        )

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).recover_audio_upload(UUID)
    assert excinfo.value.code == "taskNotFound"


def test_recover_audio_upload_http_400_task_not_found_is_controlled():
    def handler(request):
        return httpx.Response(
            400,
            json={
                "data": [],
                "errors": [{"code": "taskNotFound", "message": f"leak {KEY}"}],
            },
        )

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).recover_audio_upload(UUID)
    assert excinfo.value.code == "taskNotFound"
    assert excinfo.value.status == 400
    assert KEY not in str(excinfo.value)


def test_recover_audio_upload_invalid_uuid_never_calls_network():
    calls = []

    def handler(request):  # pragma: no cover - must never run
        calls.append(request)
        return httpx.Response(200, json={})

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).recover_audio_upload("")
    assert excinfo.value.code == "invalid_request"
    assert calls == []


# --------------------------------------------------------------------------- text submit


def test_submit_text_forces_cost_and_usage_without_mutating_caller():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.read().decode())
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "taskUUID": UUID,
                        "text": '{"verses": []}',
                        "cost": 0.0021,
                        "finishReason": "stop",
                        "usage": {"promptTokens": 10, "completionTokens": 4},
                    }
                ]
            },
        )

    request = text_request(includeCost=False, includeUsage=False)
    result = RunwareClient(KEY, client_for(handler)).submit_text(request)
    assert result == {
        "taskUUID": UUID,
        "text": '{"verses": []}',
        "cost": 0.0021,
        "finishReason": "stop",
        "usage": {"promptTokens": 10, "completionTokens": 4},
    }
    assert isinstance(seen["body"], list) and len(seen["body"]) == 1
    assert seen["body"][0]["includeCost"] is True
    assert seen["body"][0]["includeUsage"] is True
    # Caller request untouched.
    assert request["includeCost"] is False and request["includeUsage"] is False


def test_submit_text_completed_without_usage_omits_usage_key():
    def handler(request):
        return httpx.Response(
            200,
            json={"data": [{"taskUUID": UUID, "text": "{}", "cost": 0.0, "finishReason": "stop"}]},
        )

    result = RunwareClient(KEY, client_for(handler)).submit_text(text_request())
    assert result == {"taskUUID": UUID, "text": "{}", "cost": 0.0, "finishReason": "stop"}
    assert "usage" not in result


def test_submit_text_async_ack_returns_task_uuid_only():
    def handler(request):
        return httpx.Response(200, json={"data": [{"taskUUID": UUID, "status": "processing"}]})

    assert RunwareClient(KEY, client_for(handler)).submit_text(text_request()) == {"taskUUID": UUID}


@pytest.mark.parametrize(
    "task",
    [
        {"taskUUID": UUID, "text": "{}", "finishReason": "stop"},  # missing cost
        {"taskUUID": UUID, "text": "{}", "cost": -1.0, "finishReason": "stop"},
        {"taskUUID": UUID, "text": "{}", "cost": "cheap", "finishReason": "stop"},
        {"taskUUID": UUID, "text": "{}", "cost": True, "finishReason": "stop"},
    ],
)
def test_submit_text_completed_requires_finite_non_negative_cost(task):
    def handler(request):
        return httpx.Response(200, json={"data": [task]})

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).submit_text(text_request())
    assert excinfo.value.code == "invalid_cost"


def test_submit_text_length_finish_reason_is_completed():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "data": [{"taskUUID": UUID, "text": "[", "cost": 0.01, "finishReason": "length"}]
            },
        )

    result = RunwareClient(KEY, client_for(handler)).submit_text(text_request())
    assert result["finishReason"] == "length"
    assert result["text"] == "["


def test_submit_text_unknown_finish_reason_is_normalised():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "data": [{"taskUUID": UUID, "text": "{}", "cost": 0.01, "finishReason": "weird"}]
            },
        )

    result = RunwareClient(KEY, client_for(handler)).submit_text(text_request())
    assert result["finishReason"] == "unknown"

    def missing(request):
        return httpx.Response(200, json={"data": [{"taskUUID": UUID, "text": "{}", "cost": 0.01}]})

    result = RunwareClient(KEY, client_for(missing)).submit_text(text_request())
    assert result["finishReason"] == "unknown"


def test_submit_text_error_status_raises_safe_code():
    def handler(request):
        return httpx.Response(
            200,
            json={"data": [{"taskUUID": UUID, "status": "error", "code": "insufficientCredits"}]},
        )

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).submit_text(text_request())
    assert excinfo.value.code == "insufficientCredits"


def test_submit_text_mismatched_uuid_is_rejected():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "data": [
                    {"taskUUID": OTHER_UUID, "text": "{}", "cost": 0.0, "finishReason": "stop"}
                ]
            },
        )

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).submit_text(text_request())
    assert excinfo.value.code == "mismatched_task"


def test_submit_text_invalid_request_never_calls_network():
    calls = []

    def handler(request):  # pragma: no cover - must never run
        calls.append(request)
        return httpx.Response(200, json={})

    rw = RunwareClient(KEY, client_for(handler))
    for bad in (
        {},
        {"taskType": "textInference"},
        {"taskUUID": UUID},
        {"taskType": 5, "taskUUID": UUID},
    ):
        with pytest.raises(ProviderError) as excinfo:
            rw.submit_text(bad)
        assert excinfo.value.code == "invalid_request"
    assert calls == []


def test_submit_text_http_error_is_single_attempt_and_redacted():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(500, text=f"leak {KEY}")

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).submit_text(text_request())
    assert excinfo.value.code == "http_error"
    assert excinfo.value.status == 500
    assert len(calls) == 1
    assert KEY not in str(excinfo.value)


# --------------------------------------------------------------------------- text recovery


def test_recover_text_uses_get_response_and_returns_completed():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.read().decode())
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "taskUUID": UUID,
                        "text": '{"verses": []}',
                        "cost": 0.003,
                        "finishReason": "stop",
                        "usage": {"totalTokens": 12},
                    }
                ]
            },
        )

    result = RunwareClient(KEY, client_for(handler)).recover_text(UUID)
    assert seen["body"] == [{"taskType": "getResponse", "taskUUID": UUID}]
    assert result == {
        "taskUUID": UUID,
        "text": '{"verses": []}',
        "cost": 0.003,
        "finishReason": "stop",
        "usage": {"totalTokens": 12},
    }


def test_recover_text_pending_missing_or_unmatched_returns_none():
    def pending(request):
        return httpx.Response(200, json={"data": [{"taskUUID": UUID, "status": "processing"}]})

    assert RunwareClient(KEY, client_for(pending)).recover_text(UUID) is None

    def no_text(request):
        return httpx.Response(200, json={"data": [{"taskUUID": UUID}]})

    assert RunwareClient(KEY, client_for(no_text)).recover_text(UUID) is None

    def other(request):
        return httpx.Response(200, json={"data": [{"taskUUID": OTHER_UUID}]})

    assert RunwareClient(KEY, client_for(other)).recover_text(UUID) is None

    def empty(request):
        return httpx.Response(200, json={"data": []})

    assert RunwareClient(KEY, client_for(empty)).recover_text(UUID) is None


def test_recover_text_error_status_raises():
    def handler(request):
        return httpx.Response(
            200, json={"data": [{"taskUUID": UUID, "status": "error", "code": "taskNotFound"}]}
        )

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).recover_text(UUID)
    assert excinfo.value.code == "taskNotFound"


def test_recover_text_invalid_uuid_never_calls_network():
    calls = []

    def handler(request):  # pragma: no cover - must never run
        calls.append(request)
        return httpx.Response(200, json={})

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).recover_text("")
    assert excinfo.value.code == "invalid_request"
    assert calls == []
