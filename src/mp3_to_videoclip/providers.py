"""Provider HTTP clients: Runware generation/schema/asset retrieval and OpenAI transcription.

Every call here is a single attempt. Nothing in this module retries, resubmits or
falls back: a paid task that is ambiguous, errored asymmetrically or still
processing must be recovered by its persisted task UUID, never resubmitted.
:class:`ProviderError` carries only a stable code and an HTTP status; raw response
bodies, request bodies, request URLs and credentials are never interpolated into
messages and nothing is logged. There is no dry-run mode: an upstream header is
claimed but unverified, so no dry-run is exposed.
"""

from __future__ import annotations

import base64
import hashlib
import io
import ipaddress
import json
import math
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from PIL import Image, UnidentifiedImageError

__all__ = ["ProviderError", "RunwareClient", "transcribe"]

RUNWARE_API_URL = "https://api.runware.ai/v1"
RUNWARE_SCHEMA_URL = "https://runware.ai/docs/models/{slug}/schema.json"
OPENAI_TRANSCRIBE_URL = "https://api.openai.com/v1/audio/transcriptions"

MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
MAX_REFERENCE_BYTES = 10 * 1024 * 1024
MAX_TRANSCRIBE_BYTES = 25_000_000
RUNWARE_KEY_ENV = "PROJECT_VEIL_RUNWARE_API"

_TIMEOUT = httpx.Timeout(120.0, connect=15.0)

_MEDIA_TYPES = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
    "GIF": "image/gif",
    "BMP": "image/bmp",
    "TIFF": "image/tiff",
}
_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,127}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_PENDING = frozenset({"processing", "pending", "queued", "requested"})
# Provider-agnostic set of recognised completion reasons. Anything else (including
# a missing field) is reported as "unknown"; the caller decides what is usable.
_TEXT_FINISH_REASONS = frozenset({"stop", "length", "content_filter"})
_PUBLIC_ERROR_CODES = frozenset(
    {
        "invalidApiKey",
        "invalidTaskUUID",
        "insufficientCredits",
        "rateLimitExceeded",
        "invalidModel",
        "invalidRequest",
        "modelNotFound",
        "taskNotFound",
    }
)


class ProviderError(ValueError):
    """Controlled provider failure carrying a stable code and optional HTTP status."""

    def __init__(self, code: str, *, status: int | None = None):
        self.code = code if _TOKEN_RE.match(code) else "provider_error"
        self.status = status
        message = self.code if status is None else f"{self.code} (http status {status})"
        super().__init__(message)


def _network_errors() -> tuple[type[Exception], ...]:
    return (httpx.HTTPError, httpx.InvalidURL)


def _safe_code(value) -> str:
    # A syntactically valid token might still be an echoed credential.
    return value if isinstance(value, str) and value in _PUBLIC_ERROR_CODES else "provider_error"


def _check_host(host: str) -> None:
    name = host.strip("[]").lower()
    if name == "localhost" or name.endswith(".localhost"):
        raise ProviderError("unsafe_url")
    if name.isdigit():  # integer/decimal IP forms resolve to loopback or private ranges.
        raise ProviderError("unsafe_url")
    if re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+)(?:\.(?:0x[0-9a-f]+|[0-9]+)){0,3}", name):
        # Reject legacy shorthand, hexadecimal and octal-looking IPv4 forms.
        # Canonical public IPv4 literals are checked below instead.
        try:
            ipaddress.ip_address(name)
        except ValueError as exc:
            raise ProviderError("unsafe_url") from exc
    try:
        address = ipaddress.ip_address(name)
    except ValueError:
        return
    if (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    ):
        raise ProviderError("unsafe_url")


def _safe_asset_url(value) -> str:
    if not isinstance(value, str) or not value or any(ord(ch) < 0x20 or ch == " " for ch in value):
        raise ProviderError("invalid_image_url")
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname:
        raise ProviderError("unsafe_url")
    if parts.username is not None or parts.password is not None:
        raise ProviderError("unsafe_url")
    _check_host(parts.hostname)
    return value


def _safe_media_url(value) -> str:
    """Validate an opaque Runware media URL: HTTPS, no credentials, public host."""
    if not isinstance(value, str) or not value or any(ord(ch) < 0x20 or ch == " " for ch in value):
        raise ProviderError("invalid_media_url")
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname:
        raise ProviderError("unsafe_url")
    if parts.username is not None or parts.password is not None:
        raise ProviderError("unsafe_url")
    _check_host(parts.hostname)
    return value


def _image_format(data: bytes) -> str:
    try:
        with Image.open(io.BytesIO(data)) as image:
            fmt = image.format
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ProviderError("invalid_image") from exc
    if fmt not in _MEDIA_TYPES:
        raise ProviderError("unsupported_image")
    return fmt


def _atomic_write(path: Path, data: bytes) -> None:
    """Write bytes atomically without ever replacing an existing asset file."""
    if path.exists():
        raise ProviderError("asset_exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}-", suffix=".part", dir=path.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(tmp, path)  # Atomic no-clobber publication on the same filesystem.
        except FileExistsError as exc:
            raise ProviderError("asset_exists") from exc
        tmp.unlink()
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def runware_api_key() -> str:
    """Use the user's explicitly selected project-veil key; ignore generic fallback."""
    key = os.environ.get(RUNWARE_KEY_ENV)
    if not key or not key.strip():
        raise ValueError(f"{RUNWARE_KEY_ENV} is not configured; no audio upload/inference made")
    return key


class RunwareClient:
    """Single-attempt Runware REST client. Caller supplies the task UUID and owns tracking."""

    def __init__(self, api_key: str, client: httpx.Client | None = None):
        if not isinstance(api_key, str) or not api_key:
            raise ProviderError("invalid_request")
        self._api_key = api_key
        self._owns_client = client is None
        self._client = client if client is not None else httpx.Client(timeout=_TIMEOUT)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> RunwareClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _post_json(self, payload: list) -> dict:
        try:
            response = self._client.post(
                RUNWARE_API_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                content=json.dumps(payload).encode(),
            )
        except _network_errors() as exc:
            raise ProviderError("network_error") from exc
        if response.status_code >= 400:
            # The standard error envelope carries a public code (e.g. taskNotFound
            # from getTaskDetails). Surface recognised codes; never echo unknowns.
            code = "http_error"
            try:
                envelope = response.json()
            except ValueError:
                envelope = None
            if isinstance(envelope, dict):
                errors = envelope.get("errors")
                first = errors[0] if isinstance(errors, list) and errors else None
                if isinstance(first, dict) and first.get("code") in _PUBLIC_ERROR_CODES:
                    code = first["code"]
            raise ProviderError(code, status=response.status_code)
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError("invalid_response") from exc
        if not isinstance(data, dict):
            raise ProviderError("invalid_response")
        return data

    @staticmethod
    def _tasks(data: dict) -> list:
        errors = data.get("errors")
        if errors:
            first = errors[0] if isinstance(errors, list) and errors else None
            code = first.get("code") if isinstance(first, dict) else None
            raise ProviderError(_safe_code(code))
        tasks = data.get("data")
        if not isinstance(tasks, list):
            raise ProviderError("invalid_response")
        return [task for task in tasks if isinstance(task, dict)]

    def _match(self, data: dict, task_uuid: str) -> dict | None:
        for task in self._tasks(data):
            if task.get("taskUUID") == task_uuid:
                return task
        return None

    @staticmethod
    def _completed(task: dict, task_uuid: str) -> dict:
        url = _safe_asset_url(task.get("imageURL"))
        cost = task.get("cost")
        if (
            isinstance(cost, bool)
            or not isinstance(cost, (int, float))
            or not math.isfinite(cost)
            or cost < 0
        ):
            raise ProviderError("invalid_cost")
        result = {"taskUUID": task_uuid, "imageURL": url, "cost": float(cost)}
        seed = task.get("seed")
        if seed is not None:
            result["seed"] = seed
        return result

    @staticmethod
    def _result(task: dict | None, task_uuid: str) -> dict:
        if task is None or task.get("status") == "error":
            if task is not None:
                raise ProviderError(_safe_code(task.get("code")))
            raise ProviderError("mismatched_task")
        if task.get("status") in _PENDING or task.get("imageURL") is None:
            return {"taskUUID": task_uuid}
        return RunwareClient._completed(task, task_uuid)

    def submit(self, request: dict) -> dict:
        """Submit one task. Returns the completed canonical result or ``{taskUUID}``.

        Pending results are distinguished by the absence of ``imageURL``; the caller
        must persist the returned UUID and recover it rather than resubmitting.
        """
        if not isinstance(request, dict) or not isinstance(request.get("taskType"), str):
            raise ProviderError("invalid_request")
        task_uuid = request.get("taskUUID")
        if not isinstance(task_uuid, str) or not task_uuid:
            raise ProviderError("invalid_request")
        task = dict(request)
        if task["taskType"].endswith("Inference"):
            task["includeCost"] = True  # never claim an exact billed cost, only request it
        data = self._post_json([task])
        return self._result(self._match(data, task_uuid), task_uuid)

    def recover(self, task_uuid: str) -> dict | None:
        """Read-only ``getResponse`` poll. Returns the canonical result, or ``None`` if unresolved."""
        if not isinstance(task_uuid, str) or not task_uuid:
            raise ProviderError("invalid_request")
        data = self._post_json([{"taskType": "getResponse", "taskUUID": task_uuid}])
        task = self._match(data, task_uuid)
        if task is None or task.get("status") == "error":
            if task is not None:
                raise ProviderError(_safe_code(task.get("code")))
            return None
        if task.get("status") in _PENDING or task.get("imageURL") is None:
            return None
        return self._completed(task, task_uuid)

    def schema(self, slug: str) -> dict:
        """Fetch a model schema document. Validation against it is the caller's job."""
        if not isinstance(slug, str) or slug in (".", "..") or not _SLUG_RE.match(slug):
            raise ProviderError("invalid_slug")
        try:
            response = self._client.get(RUNWARE_SCHEMA_URL.format(slug=slug))
        except _network_errors() as exc:
            raise ProviderError("network_error") from exc
        if response.status_code >= 400:
            raise ProviderError("http_error", status=response.status_code)
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError("invalid_response") from exc
        if not isinstance(data, dict):
            raise ProviderError("invalid_response")
        return data

    def download(self, url: str, path: Path) -> None:
        """Stream a verified image to ``path`` without overwriting an existing asset."""
        path = Path(path)
        if path.exists():
            raise ProviderError("asset_exists")
        target = _safe_asset_url(url)  # validate before emitting any request
        try:
            with self._client.stream("GET", target, follow_redirects=False) as response:
                if 300 <= response.status_code < 400:
                    raise ProviderError("unsafe_redirect", status=response.status_code)
                if response.status_code >= 400:
                    raise ProviderError("http_error", status=response.status_code)
                declared = response.headers.get("content-length")
                if declared is not None:
                    try:
                        declared_size = int(declared)
                    except ValueError:
                        declared_size = 0
                    if declared_size > MAX_DOWNLOAD_BYTES:
                        raise ProviderError("too_large")
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > MAX_DOWNLOAD_BYTES:
                        raise ProviderError("too_large")
                    chunks.append(chunk)
        except ProviderError:
            raise
        except _network_errors() as exc:
            raise ProviderError("network_error") from exc
        data = b"".join(chunks)
        _image_format(data)
        _atomic_write(path, data)

    def reference_image(self, path: Path) -> str:
        """Return a validated ``data:`` URI for an image reference (<= 10 MB)."""
        path = Path(path)
        try:
            if path.stat().st_size > MAX_REFERENCE_BYTES:
                raise ProviderError("reference_too_large")
            data = path.read_bytes()
        except OSError as exc:
            raise ProviderError("reference_unreadable") from exc
        if len(data) > MAX_REFERENCE_BYTES:
            raise ProviderError("reference_too_large")
        fmt = _image_format(data)
        encoded = base64.b64encode(data).decode("ascii")
        return f"data:{_MEDIA_TYPES[fmt]};base64,{encoded}"

    # ------------------------------------------------------------------ audio upload

    @staticmethod
    def _upload_result(task: dict | None, task_uuid: str) -> dict:
        if task is None:
            raise ProviderError("mismatched_task")
        if task.get("status") == "error":
            raise ProviderError(_safe_code(task.get("code")))
        if task.get("status") in _PENDING or task.get("mediaUUID") is None:
            return {"taskUUID": task_uuid}  # pending: caller persists the UUID and recovers
        media_uuid = task.get("mediaUUID")
        operation = task.get("operation")
        # Live mediaStorage results omit "operation" (the published example shows
        # it): accept an absent value, but never a contradictory one.
        if (operation is not None and operation != "upload") or not (
            isinstance(media_uuid, str) and _UUID_RE.match(media_uuid)
        ):
            raise ProviderError("invalid_response")
        media_url = _safe_media_url(task.get("mediaURL"))
        return {"taskUUID": task_uuid, "mediaUUID": media_uuid, "mediaURL": media_url}

    def _task_details(self, task_uuid: str) -> dict | None:
        """Read-only ``getTaskDetails``. Returns the original task result, or ``None``.

        The nested ``response.data[0]`` is the recorded result of the original request.
        Only that result is returned: the echoed original request and any credentials are
        never surfaced or persisted.
        """
        data = self._post_json([{"taskType": "getTaskDetails", "taskUUID": task_uuid}])
        task = self._match(data, task_uuid)
        if task is None:
            return None
        if task.get("status") == "error":
            raise ProviderError(_safe_code(task.get("code")))
        response = task.get("response")
        if not isinstance(response, dict):
            return None
        inner = response.get("data")
        if not isinstance(inner, list) or not inner or not isinstance(inner[0], dict):
            return None
        return inner[0]

    def upload_audio(
        self, task_uuid: str, source: Path, expected_sha256: str, *, on_response=None
    ) -> dict:
        """Upload one local MP3 as a ``mediaStorage`` task and return its media handle.

        The exact bytes are hashed and compared to ``expected_sha256`` before any network
        call, so a changed source is never uploaded. Returns the canonical
        ``{taskUUID, mediaUUID, mediaURL}`` or a pending ``{taskUUID}``; the caller must
        persist the UUID and recover it rather than resubmitting.
        """
        if not isinstance(task_uuid, str) or not task_uuid:
            raise ProviderError("invalid_request")
        if not isinstance(expected_sha256, str) or not _SHA256_RE.match(expected_sha256):
            raise ProviderError("invalid_request")
        source = Path(source)
        if source.suffix.lower() != ".mp3":
            raise ProviderError("unsupported_audio")
        try:
            size = source.stat().st_size
        except OSError as exc:
            raise ProviderError("source_unreadable") from exc
        if size > MAX_TRANSCRIBE_BYTES:
            raise ProviderError("source_too_large")
        try:
            data = source.read_bytes()
        except OSError as exc:
            raise ProviderError("source_unreadable") from exc
        if len(data) > MAX_TRANSCRIBE_BYTES:
            raise ProviderError("source_too_large")
        if hashlib.sha256(data).hexdigest() != expected_sha256.lower():
            raise ProviderError("source_changed")
        encoded = base64.b64encode(data).decode("ascii")
        task = {
            "taskType": "mediaStorage",
            "taskUUID": task_uuid,
            "operation": "upload",
            "media": f"data:audio/mpeg;base64,{encoded}",
        }
        matched = self._match(self._post_json([task]), task_uuid)
        if matched is not None and on_response is not None:
            # Preserve output metadata before validation: utility tasks may not
            # be retrievable from getTaskDetails after a schema mismatch. Never
            # pass echoed input media, credentials or original requests through.
            fields = ("taskType", "taskUUID", "operation", "mediaUUID", "mediaURL", "status")
            on_response({key: matched[key] for key in fields if key in matched})
        return self._upload_result(matched, task_uuid)

    def recover_audio_upload(self, task_uuid: str) -> dict | None:
        """Read-only audio-upload recovery. Returns the canonical result, or ``None``.

        Uses ``getTaskDetails`` only: the upload is never resubmitted. ``None`` means
        pending, missing or mismatched; a failed original task raises a controlled error.
        """
        if not isinstance(task_uuid, str) or not task_uuid:
            raise ProviderError("invalid_request")
        original = self._task_details(task_uuid)
        if original is None:
            return None
        original_uuid = original.get("taskUUID")
        if original_uuid is not None and original_uuid != task_uuid:
            return None  # mismatched recorded task
        if original.get("operation") != "upload":
            return None
        if original.get("status") == "error":
            raise ProviderError(_safe_code(original.get("code")))
        if original.get("status") in _PENDING or original.get("mediaUUID") is None:
            return None
        return self._upload_result(original, task_uuid)

    # ------------------------------------------------------------------ text inference

    @staticmethod
    def _text_completed(task: dict, task_uuid: str) -> dict:
        text = task.get("text")
        if not isinstance(text, str):
            raise ProviderError("invalid_response")
        reason = task.get("finishReason")
        if reason not in _TEXT_FINISH_REASONS:
            reason = "unknown"
        cost = task.get("cost")
        if (
            isinstance(cost, bool)
            or not isinstance(cost, (int, float))
            or not math.isfinite(cost)
            or cost < 0
        ):
            raise ProviderError("invalid_cost")
        result = {
            "taskUUID": task_uuid,
            "text": text,
            "cost": float(cost),
            "finishReason": reason,
        }
        usage = task.get("usage")
        if isinstance(usage, dict):
            result["usage"] = usage
        return result

    @staticmethod
    def _text_result(task: dict | None, task_uuid: str) -> dict:
        if task is None or task.get("status") == "error":
            if task is not None:
                raise ProviderError(_safe_code(task.get("code")))
            raise ProviderError("mismatched_task")
        if task.get("status") in _PENDING or task.get("text") is None:
            return {"taskUUID": task_uuid}
        return RunwareClient._text_completed(task, task_uuid)

    def submit_text(self, request: dict) -> dict:
        """Submit one ``textInference`` request. Returns the canonical result or ``{taskUUID}``.

        ``includeCost`` and ``includeUsage`` are forced on a private copy; the caller's
        request is never mutated. The caller owns the whole request (model, inputs,
        messages, schema, settings, async delivery) and must supply ``taskType`` and
        ``taskUUID``. Pending results carry only the UUID and must be recovered, not
        resubmitted.
        """
        if not isinstance(request, dict) or request.get("taskType") != "textInference":
            raise ProviderError("invalid_request")
        task_uuid = request.get("taskUUID")
        if not isinstance(task_uuid, str) or not task_uuid:
            raise ProviderError("invalid_request")
        task = dict(request)
        task["includeCost"] = True  # never claim an exact billed cost, only request it
        task["includeUsage"] = True
        return self._text_result(self._match(self._post_json([task]), task_uuid), task_uuid)

    def recover_text(self, task_uuid: str) -> dict | None:
        """Read-only ``getResponse`` poll. Returns the canonical result, or ``None``.

        A single read-only call, no fallback and no resubmission. ``None`` means pending
        or unmatched. Any non-``stop`` finish reason is a completed result whose content
        the caller validates.
        """
        if not isinstance(task_uuid, str) or not task_uuid:
            raise ProviderError("invalid_request")
        data = self._post_json([{"taskType": "getResponse", "taskUUID": task_uuid}])
        task = self._match(data, task_uuid)
        if task is None:
            return None
        if task.get("status") == "error":
            raise ProviderError(_safe_code(task.get("code")))
        if task.get("status") in _PENDING or task.get("text") is None:
            return None
        return self._text_completed(task, task_uuid)


def transcribe(
    api_key: str,
    source: Path,
    language: str | None = None,
    client: httpx.Client | None = None,
) -> dict:
    """Transcribe one file with whisper-1, requesting verbose_json segment+word timestamps."""
    if not isinstance(api_key, str) or not api_key:
        raise ProviderError("invalid_request")
    source = Path(source)
    try:
        size = source.stat().st_size
    except OSError as exc:
        raise ProviderError("source_unreadable") from exc
    if size > MAX_TRANSCRIBE_BYTES:
        raise ProviderError("source_too_large")
    owns_client = client is None
    http = client if client is not None else httpx.Client(timeout=_TIMEOUT)
    fields: dict[str, object] = {
        "model": "whisper-1",
        "response_format": "verbose_json",
        "timestamp_granularities[]": ["segment", "word"],
    }
    if language:
        fields["language"] = language
    try:
        with source.open("rb") as handle:
            response = http.post(
                OPENAI_TRANSCRIBE_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (source.name, handle, "application/octet-stream")},
                data=fields,
            )
    except _network_errors() as exc:
        raise ProviderError("network_error") from exc
    finally:
        if owns_client:
            http.close()
    if response.status_code >= 400:
        raise ProviderError("http_error", status=response.status_code)
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderError("invalid_response") from exc
    if not isinstance(payload, dict):
        raise ProviderError("invalid_response")
    return payload
