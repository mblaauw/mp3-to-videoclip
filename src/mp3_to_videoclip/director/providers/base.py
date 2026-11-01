"""What every provider shares: the events it yields and how it reads a stream.

Messages stay in the OpenAI shape the loop has always built (roles, ``tool_calls``, ``tool``
rows and ``image_url`` parts), and each provider translates them. Silence is bounded here:
waiting for the first response counts as a gap, and any bytes count as life.
"""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx

CONNECT_LIMIT = 10.0
# Retries happen before anything has streamed, and inside the idle limit.
MAX_RETRIES = 1
RETRY_STATUSES = frozenset({408, 409, 429, 500, 502, 503, 504})


class StreamStalled(RuntimeError):
    """The model sent nothing for the whole idle limit."""

    def __init__(self, seconds: float):
        super().__init__(f"no response for {seconds:g} s")
        self.seconds = seconds


class ProviderFailure(RuntimeError):
    """The provider refused or dropped the call. Its reply is never repeated: it can echo keys."""

    def __init__(self, status_code: int | None = None):
        super().__init__(f"provider failed ({status_code})")
        self.status_code = status_code


@dataclass
class TextDelta:
    text: str


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str
    #: Opaque to us. Gemini asks for it back with the call it came with.
    signature: str = ""


@dataclass
class Progress:
    """The model is sending something the reader cannot see yet."""

    tool: str = ""
    chars: int = 0


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    #: False when the stream carried no counts, which must never read as "free".
    reported: bool = False


@dataclass
class TurnResult:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    finish_reason: str | None = None


def image_part(url: str) -> tuple[str, str] | None:
    """A ``data:`` URL as its media type and base64 body. Nothing else is ever sent."""
    if not url.startswith("data:") or ";base64," not in url:
        return None
    media, data = url[5:].split(";base64,", 1)
    base64.b64decode(data, validate=True)
    return media, data


def parsed_arguments(raw: str | None) -> dict:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


async def sse_events(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    headers: dict,
    body: dict,
    idle_limit: float,
) -> AsyncIterator[dict[str, Any]]:
    """POST and yield each server-sent JSON event, with one retry before anything streamed."""
    for attempt in range(MAX_RETRIES + 1):
        request = client.build_request(method, url, headers=headers, json=body)
        try:
            response = await asyncio.wait_for(client.send(request, stream=True), idle_limit)
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise StreamStalled(idle_limit) from exc
        except httpx.HTTPError as exc:
            if attempt < MAX_RETRIES:
                continue
            raise ProviderFailure(None) from exc
        if response.status_code >= 400:
            await response.aclose()
            if attempt < MAX_RETRIES and response.status_code in RETRY_STATUSES:
                continue
            raise ProviderFailure(response.status_code)
        break
    try:
        lines = response.aiter_lines()
        while True:
            try:
                line = await asyncio.wait_for(anext(lines), idle_limit)
            except StopAsyncIteration:
                return
            except (TimeoutError, httpx.TimeoutException) as exc:
                raise StreamStalled(idle_limit) from exc
            except httpx.HTTPError as exc:
                raise ProviderFailure(None) from exc
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                value = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                yield value
    finally:
        await response.aclose()
