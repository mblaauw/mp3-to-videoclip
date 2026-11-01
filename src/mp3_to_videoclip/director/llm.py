"""Director LLM adapter: one interface over every provider, with streaming tool calls.

``DirectorLLM`` keeps the idle limit and the plain-language failures; the wire formats live
in ``providers/``. Silence is bounded: IDLE_LIMIT is the longest gap between stream chunks,
and waiting for the first response counts as a gap. Any chunk counts as life, including
tool-call arguments that show nothing to the reader, so a long tool call that is still
arriving is never cut off. A whole Writer turn has been seen to take 55 s; the limit is about
three of those, in case a provider holds a tool call back and sends it in one piece.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import Any

from .providers import KINDS
from .providers.base import (
    MAX_RETRIES,
    Progress,
    ProviderFailure,
    StreamStalled,
    TextDelta,
    ToolCall,
    TurnResult,
    Usage,
)

__all__ = [
    "IDLE_LIMIT",
    "MAX_RETRIES",
    "DirectorLLM",
    "Progress",
    "ProviderFailure",
    "StreamStalled",
    "TextDelta",
    "ToolCall",
    "TurnResult",
    "Usage",
    "service_failed_message",
    "stall_message",
]

IDLE_LIMIT = 180.0
NOTHING_LOST = (
    "Nothing was lost: everything saved so far is still there, and no half-finished "
    "step was saved. Ask again when you are ready."
)


def _who(role: str | None) -> str:
    return role.capitalize() if role else "Director"


def stall_message(role: str | None, seconds: float) -> str:
    minutes = max(1, round(seconds / 60))
    span = "1 minute" if minutes == 1 else f"{minutes} minutes"
    return f"The {_who(role)} sent nothing for {span}, so this turn was ended. {NOTHING_LOST}"


def service_failed_message(role: str | None, failure: Exception, model: str = "") -> str:
    status = getattr(failure, "status_code", None)
    named = f" for {model}" if model else ""
    if status in (401, 403):
        return (
            f"The provider refused the key{named}, so the {_who(role)} couldn't answer. "
            f"Check it in Settings. {NOTHING_LOST}"
        )
    if status == 404:
        return (
            f"The provider doesn't offer {model or 'that model'} to this key. "
            f"Choose another for the {_who(role)} in Settings. {NOTHING_LOST}"
        )
    detail = f" (error {status})" if status else ""
    return f"The model service didn't answer the {_who(role)}{detail}, so this turn ended. {NOTHING_LOST}"


class DirectorLLM:
    def __init__(
        self,
        base_url: str | None,
        api_key: str,
        model: str,
        kind: str = "openai-compatible",
        user_agent: str = "mp3-to-videoclip-studio/0.1",
        session_id: str | None = None,
        idle_limit: float = IDLE_LIMIT,
        transport=None,
    ):
        self.model = model
        self.kind = kind
        self.idle_limit = idle_limit
        self._provider = KINDS[kind](
            base_url=base_url,
            api_key=api_key,
            model=model,
            headers={"User-Agent": user_agent, "x-opencode-session": session_id or "studio"},
            idle_limit=idle_limit,
            transport=transport,
        )

    @property
    def _client(self):
        return self._provider.client

    @_client.setter
    def _client(self, value):
        self._provider.client = value

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
    ) -> AsyncIterator[TextDelta | Progress | ToolCall | Usage | TurnResult]:
        async with aclosing(self._provider.stream(messages, tools, system)) as events:
            async for event in events:
                yield event
