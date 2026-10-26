"""Stable JSON error envelope for every API failure.

The UI switches on ``code`` and treats ``detail`` as the human fallback. Codes
are API surface: add one deliberately, never derive it from an exception class.
"""

from __future__ import annotations

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
