"""Mocked provider-contract tests. No live calls: every request goes through httpx.MockTransport."""

import base64
import io
import json

import httpx
import pytest
from PIL import Image

from mp3_to_videoclip import providers
from mp3_to_videoclip.providers import ProviderError, RunwareClient, transcribe

UUID = "a1b2c3d4-0000-4000-8000-000000000000"
OTHER_UUID = "ffffffff-0000-4000-8000-000000000000"
KEY = "runware-secret-key"
OPENAI_KEY = "sk-secret-openai"
IMAGE_URL = "https://im.runware.ai/image/x.png"


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def png_bytes(size=(4, 4), color=(200, 10, 10)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def generation_request(**overrides):
    request = {
        "taskType": "imageInference",
        "taskUUID": UUID,
        "positivePrompt": "a calm harbour at dawn",
        "model": "runware:100@1",
    }
    request.update(overrides)
    return request


def test_provider_error_is_value_error():
    assert issubclass(ProviderError, ValueError)
    assert ProviderError("http_error", status=500).status == 500


# --------------------------------------------------------------------------- schema


def test_schema_fetches_document_without_credentials():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["method"] = request.method
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"type": "object"})

    rw = RunwareClient(KEY, client_for(handler))
    assert rw.schema("runware:100@1") == {"type": "object"}
    assert seen["method"] == "GET"
    assert seen["url"].startswith("https://runware.ai/docs/models/")
    assert seen["url"].endswith("/schema.json")
    assert "runware" in seen["url"]
    assert seen["auth"] is None


@pytest.mark.parametrize("slug", ["", "../secret", "a/b", ".", "..", "x?y", "x#y"])
def test_schema_rejects_unsafe_slugs(slug):
    calls = []

    def handler(request):  # pragma: no cover - must never run
        calls.append(request)
        return httpx.Response(200, json={})

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).schema(slug)
    assert excinfo.value.code == "invalid_slug"
    assert calls == []


def test_schema_http_error_and_non_object_body():
    def failing(request):
        return httpx.Response(404, text="nope")

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(failing)).schema("runware:100@1")
    assert excinfo.value.code == "http_error"
    assert excinfo.value.status == 404

    def not_object(request):
        return httpx.Response(200, json=[1, 2, 3])

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(not_object)).schema("runware:100@1")
    assert excinfo.value.code == "invalid_response"


# --------------------------------------------------------------------------- submit


def test_submit_completed_result_is_canonical_and_forces_include_cost():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["method"] = request.method
        seen["auth"] = request.headers.get("authorization")
        seen["ctype"] = request.headers.get("content-type")
        seen["body"] = json.loads(request.read().decode())
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "taskUUID": UUID,
                        "imageURL": IMAGE_URL,
                        "cost": 0.0013,
                        "seed": 4242,
                    }
                ]
            },
        )

    request = generation_request(includeCost=False)
    with RunwareClient(KEY, client_for(handler)) as rw:
        result = rw.submit(request)
    assert result == {"taskUUID": UUID, "imageURL": IMAGE_URL, "cost": 0.0013, "seed": 4242}
    assert seen["url"] == "https://api.runware.ai/v1"
    assert seen["method"] == "POST"
    assert seen["auth"] == f"Bearer {KEY}"
    assert seen["ctype"] == "application/json"
    assert isinstance(seen["body"], list) and len(seen["body"]) == 1
    assert seen["body"][0]["includeCost"] is True
    assert request["includeCost"] is False  # caller dict is never mutated


def test_submit_pending_returns_only_task_uuid():
    def handler(request):
        return httpx.Response(200, json={"data": [{"taskUUID": UUID, "status": "processing"}]})

    with RunwareClient(KEY, client_for(handler)) as rw:
        assert rw.submit(generation_request()) == {"taskUUID": UUID}


def test_submit_pending_without_image_url_returns_task_uuid():
    def handler(request):
        return httpx.Response(200, json={"data": [{"taskUUID": UUID}]})

    with RunwareClient(KEY, client_for(handler)) as rw:
        assert rw.submit(generation_request()) == {"taskUUID": UUID}


def test_submit_mismatched_task_uuid_is_rejected():
    def handler(request):
        return httpx.Response(
            200,
            json={"data": [{"taskUUID": OTHER_UUID, "imageURL": IMAGE_URL, "cost": 0.0}]},
        )

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).submit(generation_request())
    assert excinfo.value.code == "mismatched_task"


@pytest.mark.parametrize(
    "task",
    [
        {"taskUUID": UUID, "imageURL": IMAGE_URL},  # missing cost
        {"taskUUID": UUID, "imageURL": IMAGE_URL, "cost": -1.0},
        {"taskUUID": UUID, "imageURL": IMAGE_URL, "cost": "cheap"},
        {"taskUUID": UUID, "imageURL": IMAGE_URL, "cost": True},
    ],
)
def test_submit_completed_requires_finite_non_negative_numeric_cost(task):
    def handler(request):
        return httpx.Response(200, json={"data": [task]})

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).submit(generation_request())
    assert excinfo.value.code == "invalid_cost"


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "-Infinity"])
def test_submit_rejects_non_finite_cost(raw):
    body = f'{{"data": [{{"taskUUID": "{UUID}", "imageURL": "{IMAGE_URL}", "cost": {raw}}}]}}'

    def handler(request):
        return httpx.Response(200, text=body, headers={"content-type": "application/json"})

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).submit(generation_request())
    assert excinfo.value.code == "invalid_cost"


@pytest.mark.parametrize(
    "url",
    [
        "http://im.runware.ai/image/x.png",
        "https://127.0.0.1/image/x.png",
        "https://localhost/image/x.png",
        "https://10.0.0.5/image/x.png",
        "https://169.254.169.254/latest/meta-data",
        "https://2130706433/image/x.png",
        "https://user:pw@im.runware.ai/image/x.png",
        "",
    ],
)
def test_submit_rejects_unsafe_image_urls(url):
    def handler(request):
        return httpx.Response(
            200, json={"data": [{"taskUUID": UUID, "imageURL": url, "cost": 0.0}]}
        )

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).submit(generation_request())
    assert excinfo.value.code in {"unsafe_url", "invalid_image_url"}


def test_submit_task_error_status_raises_safe_code():
    def handler(request):
        return httpx.Response(
            200,
            json={"data": [{"taskUUID": UUID, "status": "error", "code": "invalidTaskUUID"}]},
        )

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).submit(generation_request())
    assert excinfo.value.code == "invalidTaskUUID"


def test_submit_upstream_errors_use_safe_code_only():
    def handler(request):
        return httpx.Response(
            200,
            json={"errors": [{"code": "invalidApiKey", "message": f"bad key {KEY}"}]},
        )

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).submit(generation_request())
    assert excinfo.value.code == "invalidApiKey"
    assert KEY not in str(excinfo.value)


def test_submit_upstream_unsafe_error_code_is_normalised():
    def handler(request):
        return httpx.Response(200, json={"errors": [{"code": "bad code! /etc/passwd"}]})

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).submit(generation_request())
    assert excinfo.value.code == "provider_error"


def test_secret_shaped_error_token_is_not_echoed():
    def handler(_):
        return httpx.Response(200, json={"errors": [{"code": KEY}]})

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).submit(generation_request())
    assert KEY not in str(excinfo.value) and excinfo.value.code == "provider_error"


@pytest.mark.parametrize("host", ["127.1", "0x7f.1", "0177.0.0.1"])
def test_legacy_local_ip_forms_cannot_be_download_targets(host, tmp_path):
    def handler(_):
        raise AssertionError("no network attempt allowed")

    with pytest.raises(ProviderError):
        RunwareClient(KEY, client_for(handler)).download(
            f"https://{host}/image.jpg", tmp_path / "asset.jpg"
        )


def test_submit_invalid_request_never_calls_network():
    calls = []

    def handler(request):  # pragma: no cover - must never run
        calls.append(request)
        return httpx.Response(200, json={})

    rw = RunwareClient(KEY, client_for(handler))
    for bad in (
        {},
        {"taskType": "imageInference"},
        {"taskUUID": UUID},
        {"taskType": 5, "taskUUID": UUID},
    ):
        with pytest.raises(ProviderError) as excinfo:
            rw.submit(bad)
        assert excinfo.value.code == "invalid_request"
    assert calls == []


def test_submit_missing_data_is_invalid_response():
    def handler(request):
        return httpx.Response(200, json={"unexpected": True})

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).submit(generation_request())
    assert excinfo.value.code == "invalid_response"


def test_submit_http_error_is_single_attempt_and_redacted():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(500, text=f"upstream leak {KEY}")

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).submit(generation_request())
    assert excinfo.value.code == "http_error"
    assert excinfo.value.status == 500
    assert len(calls) == 1
    assert KEY not in str(excinfo.value)


def test_submit_network_error_is_wrapped():
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).submit(generation_request())
    assert excinfo.value.code == "network_error"


def test_submit_non_json_body_is_invalid_response():
    def handler(request):
        return httpx.Response(200, text="not json")

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).submit(generation_request())
    assert excinfo.value.code == "invalid_response"


# --------------------------------------------------------------------------- recover


def test_recover_uses_get_response_and_returns_completed_result():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.read().decode())
        return httpx.Response(
            200,
            json={"data": [{"taskUUID": UUID, "imageURL": IMAGE_URL, "cost": 0.002, "seed": 7}]},
        )

    result = RunwareClient(KEY, client_for(handler)).recover(UUID)
    assert result == {"taskUUID": UUID, "imageURL": IMAGE_URL, "cost": 0.002, "seed": 7}
    assert seen["body"] == [{"taskType": "getResponse", "taskUUID": UUID}]


def test_recover_pending_or_mismatched_or_empty_returns_none():
    def processing(request):
        return httpx.Response(200, json={"data": [{"taskUUID": UUID, "status": "processing"}]})

    assert RunwareClient(KEY, client_for(processing)).recover(UUID) is None

    def other(request):
        return httpx.Response(200, json={"data": [{"taskUUID": OTHER_UUID}]})

    assert RunwareClient(KEY, client_for(other)).recover(UUID) is None

    def empty(request):
        return httpx.Response(200, json={"data": []})

    assert RunwareClient(KEY, client_for(empty)).recover(UUID) is None


def test_recover_error_status_raises():
    def handler(request):
        return httpx.Response(
            200, json={"data": [{"taskUUID": UUID, "status": "error", "code": "taskNotFound"}]}
        )

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).recover(UUID)
    assert excinfo.value.code == "taskNotFound"


def test_recover_invalid_uuid_never_calls_network():
    calls = []

    def handler(request):  # pragma: no cover - must never run
        calls.append(request)
        return httpx.Response(200, json={})

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).recover("")
    assert excinfo.value.code == "invalid_request"
    assert calls == []


# --------------------------------------------------------------------------- download


def test_download_writes_verified_image(tmp_path):
    payload = png_bytes()
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, content=payload, headers={"content-type": "image/png"})

    target = tmp_path / "shots" / "shot-01.png"
    RunwareClient(KEY, client_for(handler)).download(IMAGE_URL, target)
    assert target.read_bytes() == payload
    assert seen["url"] == IMAGE_URL
    with Image.open(target) as image:
        assert image.format == "PNG"
    assert [p.name for p in target.parent.iterdir()] == ["shot-01.png"]  # no temp leftovers


def test_download_never_overwrites_existing_asset(tmp_path):
    target = tmp_path / "shot-01.png"
    target.write_bytes(b"existing-bytes")
    calls = []

    def handler(request):  # pragma: no cover - must never run
        calls.append(request)
        return httpx.Response(200, content=png_bytes())

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).download(IMAGE_URL, target)
    assert excinfo.value.code == "asset_exists"
    assert calls == []
    assert target.read_bytes() == b"existing-bytes"


@pytest.mark.parametrize(
    "url",
    [
        "http://im.runware.ai/image/x.png",
        "https://127.0.0.1/image/x.png",
        "https://localhost/image/x.png",
        "https://user:pw@im.runware.ai/image/x.png",
        "file:///etc/passwd",
    ],
)
def test_download_rejects_unsafe_urls_before_request(tmp_path, url):
    calls = []

    def handler(request):  # pragma: no cover - must never run
        calls.append(request)
        return httpx.Response(200, content=png_bytes())

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).download(url, tmp_path / "x.png")
    assert excinfo.value.code in {"unsafe_url", "invalid_image_url"}
    assert calls == []
    assert not (tmp_path / "x.png").exists()


def test_download_rejects_redirect_without_following(tmp_path):
    def handler(request):
        return httpx.Response(302, headers={"location": "http://127.0.0.1/evil"})

    target = tmp_path / "x.png"
    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).download(IMAGE_URL, target)
    assert excinfo.value.code == "unsafe_redirect"
    assert excinfo.value.status == 302
    assert not target.exists()


def test_download_caps_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(providers, "MAX_DOWNLOAD_BYTES", 8)

    def handler(request):
        return httpx.Response(200, content=b"0123456789")

    target = tmp_path / "x.png"
    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).download(IMAGE_URL, target)
    assert excinfo.value.code == "too_large"
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_download_rejects_corrupt_image_and_removes_temp(tmp_path):
    def handler(request):
        return httpx.Response(200, content=b"this is definitely not an image")

    target = tmp_path / "x.png"
    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).download(IMAGE_URL, target)
    assert excinfo.value.code == "invalid_image"
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_download_http_error_single_attempt(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(403, text="denied")

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY, client_for(handler)).download(IMAGE_URL, tmp_path / "x.png")
    assert excinfo.value.code == "http_error"
    assert excinfo.value.status == 403
    assert len(calls) == 1


# --------------------------------------------------------------------------- reference_image


def test_reference_image_returns_validated_data_uri(tmp_path):
    path = tmp_path / "ref.png"
    path.write_bytes(png_bytes())
    uri = RunwareClient(KEY).reference_image(path)
    assert uri.startswith("data:image/png;base64,")
    assert base64.b64decode(uri.split(",", 1)[1]) == path.read_bytes()


def test_reference_image_rejects_oversize(tmp_path, monkeypatch):
    monkeypatch.setattr(providers, "MAX_REFERENCE_BYTES", 8)
    path = tmp_path / "ref.png"
    path.write_bytes(png_bytes())
    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY).reference_image(path)
    assert excinfo.value.code == "reference_too_large"


def test_reference_image_rejects_invalid_and_missing(tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY).reference_image(bad)
    assert excinfo.value.code == "invalid_image"

    with pytest.raises(ProviderError) as excinfo:
        RunwareClient(KEY).reference_image(tmp_path / "missing.png")
    assert excinfo.value.code == "reference_unreadable"


# --------------------------------------------------------------------------- transcribe


def test_transcribe_sends_multipart_with_timestamps(tmp_path):
    source = tmp_path / "kortjakje.mp3"
    source.write_bytes(b"ID3\x04\x00\x00\x00\x00\x00\x00")
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["method"] = request.method
        seen["auth"] = request.headers.get("authorization")
        seen["ctype"] = request.headers.get("content-type", "")
        seen["body"] = request.read()
        return httpx.Response(
            200, json={"text": "hi", "language": "nl", "segments": [], "words": []}
        )

    result = transcribe(OPENAI_KEY, source, language="nl", client=client_for(handler))
    assert result["language"] == "nl"
    assert seen["url"] == "https://api.openai.com/v1/audio/transcriptions"
    assert seen["method"] == "POST"
    assert seen["auth"] == f"Bearer {OPENAI_KEY}"
    assert seen["ctype"].startswith("multipart/form-data; boundary=")
    body = seen["body"]
    assert b'name="file"' in body and source.name.encode() in body
    assert b'name="model"' in body and b"whisper-1" in body
    assert b'name="response_format"' in body and b"verbose_json" in body
    assert body.count(b'name="timestamp_granularities[]"') == 2
    assert b"segment" in body and b"word" in body
    assert b'name="language"' in body and b"nl" in body


def test_transcribe_omits_language_when_not_given(tmp_path):
    source = tmp_path / "a.mp3"
    source.write_bytes(b"ID3")
    seen = {}

    def handler(request):
        seen["body"] = request.read()
        return httpx.Response(200, json={"text": ""})

    transcribe(OPENAI_KEY, source, client=client_for(handler))
    assert b'name="language"' not in seen["body"]


def test_transcribe_rejects_oversize_before_upload(tmp_path, monkeypatch):
    monkeypatch.setattr(providers, "MAX_TRANSCRIBE_BYTES", 4)
    source = tmp_path / "big.mp3"
    source.write_bytes(b"12345")
    calls = []

    def handler(request):  # pragma: no cover - must never run
        calls.append(request)
        return httpx.Response(200, json={})

    with pytest.raises(ProviderError) as excinfo:
        transcribe(OPENAI_KEY, source, client=client_for(handler))
    assert excinfo.value.code == "source_too_large"
    assert calls == []


def test_transcribe_missing_source_and_empty_key(tmp_path):
    with pytest.raises(ProviderError) as excinfo:
        transcribe(
            OPENAI_KEY, tmp_path / "missing.mp3", client=client_for(lambda r: httpx.Response(200))
        )
    assert excinfo.value.code == "source_unreadable"

    source = tmp_path / "a.mp3"
    source.write_bytes(b"ID3")
    with pytest.raises(ProviderError) as excinfo:
        transcribe("", source, client=client_for(lambda r: httpx.Response(200)))
    assert excinfo.value.code == "invalid_request"


def test_transcribe_http_error_is_single_attempt_and_redacted(tmp_path):
    source = tmp_path / "a.mp3"
    source.write_bytes(b"ID3")
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(401, text=f"bad key {OPENAI_KEY}")

    with pytest.raises(ProviderError) as excinfo:
        transcribe(OPENAI_KEY, source, client=client_for(handler))
    assert excinfo.value.code == "http_error"
    assert excinfo.value.status == 401
    assert len(calls) == 1
    assert OPENAI_KEY not in str(excinfo.value)


def test_transcribe_network_and_non_json_errors(tmp_path):
    source = tmp_path / "a.mp3"
    source.write_bytes(b"ID3")

    def raising(request):
        raise httpx.ConnectTimeout("timeout")

    with pytest.raises(ProviderError) as excinfo:
        transcribe(OPENAI_KEY, source, client=client_for(raising))
    assert excinfo.value.code == "network_error"

    def textual(request):
        return httpx.Response(200, text="not json")

    with pytest.raises(ProviderError) as excinfo:
        transcribe(OPENAI_KEY, source, client=client_for(textual))
    assert excinfo.value.code == "invalid_response"


# --------------------------------------------------------------------------- client lifecycle


def test_injected_client_is_not_closed_by_runware_client():
    def handler(request):  # pragma: no cover - must never run
        return httpx.Response(200, json={})

    http = client_for(handler)
    with RunwareClient(KEY, http):
        pass
    assert not http.is_closed
    http.close()


def test_runware_client_requires_api_key():
    with pytest.raises(ProviderError) as excinfo:
        RunwareClient("")
    assert excinfo.value.code == "invalid_request"
