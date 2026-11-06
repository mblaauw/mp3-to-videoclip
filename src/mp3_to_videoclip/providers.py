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
import binascii
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
ELEVENLABS_API_URL = "https://api.elevenlabs.io"
#: The one audio format every ElevenLabs tier may ask for.
ELEVENLABS_OUTPUT_FORMAT = "mp3_44100_128"
RUNWARE_SCHEMA_URL = "https://runware.ai/docs/models/{slug}/schema.json"
OPENAI_TRANSCRIBE_URL = "https://api.openai.com/v1/audio/transcriptions"

MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
MAX_VIDEO_BYTES = 200 * 1024 * 1024
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


class MissingProviderKey(ValueError):
    """The owner has not added this provider's key yet. Nothing was sent."""

    code = "no_runware_key"


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


#: MPEG audio frame syncs: layer III at MPEG-1 and MPEG-2, with or without CRC.
_MPEG_SYNCS = (b"\xff\xfb", b"\xff\xfa", b"\xff\xf3", b"\xff\xf2")


def _check_speech(data: bytes) -> None:
    """Refuse anything that is not plainly an audio file before it is saved."""
    if not (
        data[:4] in (b"RIFF", b"fLaC", b"OggS") or data[:3] == b"ID3" or data[:2] in _MPEG_SYNCS
    ):
        raise ProviderError("invalid_audio")


def _check_video(data: bytes) -> None:
    """An MP4 starts with its ``ftyp`` box. ffprobe judges the rest once it is on disk."""
    if data[4:8] != b"ftyp":
        raise ProviderError("invalid_video")


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
        from .storage import sync_directory

        sync_directory(path.parent)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def runware_api_key() -> str:
    """Use the Studio/settings key, then the explicitly selected environment key."""
    from .config import effective_settings

    key = effective_settings().runware_api_key
    if not key or not key.strip():
        raise MissingProviderKey(
            f"{RUNWARE_KEY_ENV} is not configured in Studio settings or the environment; "
            "no audio upload/inference made"
        )
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
        self._download(url, path, _image_format)

    def download_audio(self, url: str, path: Path) -> None:
        """Stream a verified audio file to ``path`` without overwriting an existing asset."""
        self._download(url, path, _check_speech)

    def download_video(self, url: str, path: Path) -> None:
        """Stream an MP4 to ``path`` under the clip cap, without overwriting an existing asset."""
        self._download(url, path, _check_video, limit=MAX_VIDEO_BYTES)

    def _download(self, url: str, path: Path, check, limit: int | None = None) -> None:
        limit = limit or MAX_DOWNLOAD_BYTES
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
                    if declared_size > limit:
                        raise ProviderError("too_large")
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > limit:
                        raise ProviderError("too_large")
                    chunks.append(chunk)
        except ProviderError:
            raise
        except _network_errors() as exc:
            raise ProviderError("network_error") from exc
        data = b"".join(chunks)
        check(data)
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

    # ------------------------------------------------------------------ speech

    @staticmethod
    def _speech_result(task: dict | None, task_uuid: str) -> dict | None:
        """The canonical finished result, or ``None`` while the task is still pending."""
        if task is None:
            return None
        if task.get("status") == "error":
            raise ProviderError(_safe_code(task.get("code")))
        if task.get("status") in _PENDING or task.get("audioURL") is None:
            return None
        cost = task.get("cost")
        if (
            isinstance(cost, bool)
            or not isinstance(cost, (int, float))
            or not math.isfinite(cost)
            or cost < 0
        ):
            raise ProviderError("invalid_cost")
        url = _safe_media_url(task.get("audioURL"))
        return {"taskUUID": task_uuid, "audioURL": url, "cost": float(cost)}

    def submit_speech(self, request: dict) -> dict:
        """Submit one speech task. Returns the finished result or ``{taskUUID}``."""
        if not isinstance(request, dict) or request.get("taskType") != "audioInference":
            raise ProviderError("invalid_request")
        task_uuid = request.get("taskUUID")
        if not isinstance(task_uuid, str) or not task_uuid:
            raise ProviderError("invalid_request")
        data = self._post_json([{**request, "includeCost": True}])
        task = self._match(data, task_uuid)
        if task is None:
            raise ProviderError("mismatched_task")
        return self._speech_result(task, task_uuid) or {"taskUUID": task_uuid}

    def recover_speech(self, task_uuid: str) -> dict | None:
        """Read-only ``getResponse`` poll. Returns the finished result, or ``None``."""
        if not isinstance(task_uuid, str) or not task_uuid:
            raise ProviderError("invalid_request")
        data = self._post_json([{"taskType": "getResponse", "taskUUID": task_uuid}])
        return self._speech_result(self._match(data, task_uuid), task_uuid)

    @staticmethod
    def _video_result(task: dict | None, task_uuid: str) -> dict | None:
        """The canonical finished result, or ``None`` while the task is still pending."""
        if task is None:
            return None
        if task.get("status") == "error":
            raise ProviderError(_safe_code(task.get("code")))
        if task.get("status") in _PENDING or task.get("videoURL") is None:
            return None
        cost = task.get("cost")
        if (
            isinstance(cost, bool)
            or not isinstance(cost, (int, float))
            or not math.isfinite(cost)
            or cost < 0
        ):
            raise ProviderError("invalid_cost")
        url = _safe_media_url(task.get("videoURL"))
        return {"taskUUID": task_uuid, "videoURL": url, "cost": float(cost)}

    def submit_video(self, request: dict) -> dict:
        """Submit one image-to-video task. Returns the finished result or ``{taskUUID}``."""
        if not isinstance(request, dict) or request.get("taskType") != "videoInference":
            raise ProviderError("invalid_request")
        task_uuid = request.get("taskUUID")
        if not isinstance(task_uuid, str) or not task_uuid:
            raise ProviderError("invalid_request")
        data = self._post_json([{**request, "includeCost": True}])
        task = self._match(data, task_uuid)
        if task is None:
            raise ProviderError("mismatched_task")
        return self._video_result(task, task_uuid) or {"taskUUID": task_uuid}

    def recover_video(self, task_uuid: str) -> dict | None:
        """Read-only ``getResponse`` poll. Returns the finished result, or ``None``."""
        if not isinstance(task_uuid, str) or not task_uuid:
            raise ProviderError("invalid_request")
        data = self._post_json([{"taskType": "getResponse", "taskUUID": task_uuid}])
        return self._video_result(self._match(data, task_uuid), task_uuid)

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


# ------------------------------------------------------------------ ElevenLabs

_ELEVENLABS_TERMS = (
    "tier",
    "status",
    "currency",
    "character_count",
    "character_limit",
    "next_character_count_reset_unix",
    "can_extend_character_limit",
)
_ELEVENLABS_SPEECH = "/v1/text-to-speech/"


def _unix(value) -> int | None:
    """An ISO time as the provider's unix seconds, or ``None`` when there is none."""
    from datetime import datetime

    if not isinstance(value, str) or not value:
        return None
    try:
        return int(datetime.fromisoformat(value).timestamp())
    except ValueError:
        return None


class ElevenLabsClient:
    """Single-attempt ElevenLabs client.

    The provider returns no task id and no price. A take's audio comes back in the
    answer, so it is held here until the journal has written the take's cost and
    asks for it. An interrupted take is found again, read-only, among the account's
    generations by its words, voice, model and time.
    """

    def __init__(self, api_key: str, client: httpx.Client | None = None):
        if not isinstance(api_key, str) or not api_key:
            raise ProviderError("invalid_request")
        self._api_key = api_key
        self._owns_client = client is None
        self._client = client if client is not None else httpx.Client(timeout=_TIMEOUT)
        self._held: dict[str, bytes] = {}

    def close(self) -> None:
        self._held.clear()
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> ElevenLabsClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _request(self, method: str, path: str, *, params=None, body=None) -> httpx.Response:
        try:
            response = self._client.request(
                method,
                f"{ELEVENLABS_API_URL}{path}",
                params=params,
                headers={"xi-api-key": self._api_key},
                json=body,
            )
        except _network_errors() as exc:
            raise ProviderError("network_error") from exc
        if response.status_code >= 400:
            # The envelope's detail is free text from the provider; never echo it.
            raise ProviderError("http_error", status=response.status_code)
        return response

    def _json(self, method: str, path: str, **kwargs) -> dict:
        response = self._request(method, path, **kwargs)  # a ProviderError is a ValueError too
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError("invalid_response") from exc
        if not isinstance(data, dict):
            raise ProviderError("invalid_response")
        return data

    def terms(self) -> dict:
        """The account's period as the provider states it: what a quote is made on."""
        data = self._json("GET", "/v1/user/subscription")
        terms = {key: data.get(key) for key in _ELEVENLABS_TERMS}
        for key in ("character_count", "character_limit"):
            value = terms[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ProviderError("invalid_response")
        return terms

    def _count(self) -> int | None:
        """The period's character count, or ``None`` when the free read fails."""
        try:
            return self.terms()["character_count"]
        except ProviderError:
            return None

    def submit_speech(self, request: dict) -> dict:
        """One take, held until the journal asks for it. Never answers pending."""
        if not isinstance(request, dict):
            raise ProviderError("invalid_request")
        path, task_uuid, body = request.get("path"), request.get("taskUUID"), request.get("body")
        if not isinstance(path, str) or not path.startswith(_ELEVENLABS_SPEECH):
            raise ProviderError("invalid_request")
        if not isinstance(task_uuid, str) or not task_uuid:
            raise ProviderError("invalid_request")
        if not isinstance(body, dict) or not isinstance(body.get("text"), str) or not body["text"]:
            raise ProviderError("invalid_request")
        before = self._count()
        data = self._json(
            "POST", path, params={"output_format": ELEVENLABS_OUTPUT_FORMAT}, body=body
        )
        encoded = data.get("audio_base64")
        if not isinstance(encoded, str) or not encoded:
            raise ProviderError("invalid_response")
        if len(encoded) > MAX_DOWNLOAD_BYTES * 4 // 3 + 4:
            raise ProviderError("download_too_large")
        try:
            audio = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ProviderError("invalid_response") from exc
        _check_speech(audio)
        after = self._count()
        self._held[task_uuid] = audio
        alignment = data.get("alignment")
        return {
            "taskUUID": task_uuid,
            "audioURL": f"elevenlabs:take:{task_uuid}",
            "audio_format": "mp3",
            "characters": len(body["text"]),
            "provider_characters": (
                after - before if before is not None and after is not None else None
            ),
            "alignment": alignment if isinstance(alignment, dict) else None,
        }

    def recover_speech(self, task_uuid: str, task: dict | None = None) -> dict | None:
        """Read-only: the account's generation of this task's words after it was submitted.

        Returns the finished result, or ``None`` when the history holds no such take.
        """
        if not isinstance(task_uuid, str) or not task_uuid:
            raise ProviderError("invalid_request")
        if task_uuid in self._held:
            return {
                "taskUUID": task_uuid,
                "audioURL": f"elevenlabs:take:{task_uuid}",
                "audio_format": "mp3",
                "characters": None,
                "provider_characters": None,
                "alignment": None,
            }
        if not isinstance(task, dict):
            return None
        request = task.get("request") if isinstance(task.get("request"), dict) else {}
        body = request.get("body") if isinstance(request.get("body"), dict) else {}
        path = request.get("path") if isinstance(request.get("path"), str) else ""
        voice_id = path[len(_ELEVENLABS_SPEECH) :].split("/", 1)[0]
        text, model = task.get("text"), body.get("model_id")
        if not voice_id or not isinstance(text, str) or not isinstance(model, str):
            raise ProviderError("invalid_request")
        since = _unix(task.get("submitted_at"))
        params = {
            "voice_id": voice_id,
            "model_id": model,
            "page_size": 100,
            "sort_direction": "asc",
        }
        if since is not None:
            params["date_after_unix"] = since - 60
        data = self._json("GET", "/v1/history", params=params)
        items = data.get("history")
        found = [
            item
            for item in (items if isinstance(items, list) else [])
            if isinstance(item, dict)
            and item.get("text") == text
            and isinstance(item.get("history_item_id"), str)
            and _TOKEN_RE.fullmatch(item["history_item_id"])
            and (
                since is None
                or (isinstance(item.get("date_unix"), int) and item["date_unix"] >= since - 60)
            )
        ]
        if not found:
            return None
        item = min(found, key=lambda entry: entry.get("date_unix") or 0)
        return {
            "taskUUID": task_uuid,
            "audioURL": f"elevenlabs:history:{item['history_item_id']}",
            "audio_format": "mp3",
            "characters": len(text),
            "provider_characters": None,
            "alignment": None,
            "history_item_id": item["history_item_id"],
        }

    def download_audio(self, url: str, path: Path) -> None:
        """Write a held or recovered take to ``path`` without overwriting an existing asset."""
        path = Path(path)
        if path.exists():
            raise ProviderError("asset_exists")
        if not isinstance(url, str) or not url.startswith("elevenlabs:"):
            raise ProviderError("invalid_media_url")
        kind, _, key = url[len("elevenlabs:") :].partition(":")
        if kind == "take":
            audio = self._held.get(key)
            if audio is None:
                raise ProviderError("take_not_held")
        elif kind == "history" and _TOKEN_RE.fullmatch(key):
            response = self._request("GET", f"/v1/history/{key}/audio")
            audio = response.content
            if len(audio) > MAX_DOWNLOAD_BYTES:
                raise ProviderError("download_too_large")
            _check_speech(audio)
        else:
            raise ProviderError("invalid_media_url")
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(audio)
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
        self._held.pop(key, None)


def elevenlabs_api_key() -> str:
    from .config import effective_settings

    key = effective_settings().keys.elevenlabs
    if not key:
        raise MissingProviderKey("add an ElevenLabs key in Settings")
    return key
