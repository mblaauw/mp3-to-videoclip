"""Stable JSON error envelope for every API failure.

The UI switches on ``code`` and treats ``detail`` as the human fallback. Codes
are API surface: add one deliberately, never derive it from an exception class.
"""

from __future__ import annotations

from pathlib import PurePath
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# Generic codes for plain HTTPException and framework-generated failures.
STATUS_CODES: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    502: "upstream_error",
    503: "service_unavailable",
    504: "timeout",
}


class ApiError(HTTPException):
    """An HTTPException that carries a stable, client-facing code."""

    def __init__(self, status_code: int, detail: str, code: str):
        super().__init__(status_code=status_code, detail=detail)
        self.code = code


def error_code(exc: StarletteHTTPException) -> str:
    return getattr(exc, "code", None) or STATUS_CODES.get(exc.status_code, "error")


def error_payload(detail: Any, code: str) -> dict[str, Any]:
    return {"detail": detail, "code": code}


def error_response(detail: Any, code: str, status_code: int) -> JSONResponse:
    return JSONResponse(error_payload(detail, code), status_code=status_code)


# What a missing file means to the owner. Never the path: it names this computer.
_MISSING = {
    "storyboard.json": ("storyboard_missing", "The storyboard has not been made yet."),
    "brief.json": ("brief_missing", "The story has not been written yet."),
    "edit.json": ("edit_missing", "The cut has not been made yet."),
    "music.json": ("analysis_missing", "The song has not been analyzed yet."),
}


def engine_error(exc: Exception) -> ApiError:
    """The one mapping from an engine refusal to what the API answers."""
    from mp3_to_videoclip.providers import MissingProviderKey, ProviderError
    from mp3_to_videoclip.storage import ProjectBusy, RevisionConflict

    if isinstance(exc, FileNotFoundError):
        name = PurePath(str(exc.filename)).name if exc.filename else ""
        code, detail = _MISSING.get(name, ("artifact_missing", "That file is not there yet."))
        return ApiError(404, detail, code)
    if isinstance(exc, ProjectBusy):
        return ApiError(409, str(exc), "project_busy")
    if isinstance(exc, RevisionConflict):
        return ApiError(409, str(exc), "conflict")
    if isinstance(exc, MissingProviderKey):
        return ApiError(409, str(exc), exc.code)
    if isinstance(exc, ProviderError):
        return ApiError(502, str(exc), exc.code)
    return ApiError(400, str(exc), "bad_request")
