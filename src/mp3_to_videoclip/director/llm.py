"""Director LLM adapter: OpenAI-compatible streaming with tool calls.

Targets OpenCode Go (deepseek-v4.1-flash) by default; any OpenAI-compatible
provider is a settings change. Phase 3 starts with scripts/probe_llm.py to
verify tool calling and vision before relying on them.

Silence is bounded here: IDLE_LIMIT is the longest gap between stream chunks, and
waiting for the first response counts as a gap. Any chunk counts as life, including
tool-call arguments that show nothing to the reader, so a long tool call that is
still arriving is never cut off. A whole Writer turn has been seen to take 55 s; the
limit is about three of those, in case a provider holds a tool call back and sends
it in one piece.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass, field
from typing import Any

import httpx
from openai import APITimeoutError, AsyncOpenAI

IDLE_LIMIT = 180.0
CONNECT_LIMIT = 10.0
# Retries happen before anything has streamed, and inside IDLE_LIMIT.
MAX_RETRIES = 1
PROGRESS_EVERY = 1.0
NOTHING_LOST = (
    "Nothing was lost: everything saved so far is still there, and no half-finished "
    "step was saved. Ask again when you are ready."
)


class StreamStalled(RuntimeError):
    """The model sent nothing for the whole idle limit."""

    def __init__(self, seconds: float):
        super().__init__(f"no response for {seconds:g} s")
        self.seconds = seconds


def _who(role: str | None) -> str:
    return role.capitalize() if role else "Director"


def stall_message(role: str | None, seconds: float) -> str:
    minutes = max(1, round(seconds / 60))
    span = "1 minute" if minutes == 1 else f"{minutes} minutes"
    return f"The {_who(role)} sent nothing for {span}, so this turn was ended. {NOTHING_LOST}"


def service_failed_message(role: str | None, failure: Exception) -> str:
    status = getattr(failure, "status_code", None)
    detail = f" (error {status})" if status else ""
    return f"The model service didn't answer the {_who(role)}{detail}, so this turn ended. {NOTHING_LOST}"


@dataclass
class TextDelta:
    text: str


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class Progress:
    """The model is sending something the reader cannot see yet."""

    tool: str = ""
    chars: int = 0


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class TurnResult:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    finish_reason: str | None = None


class DirectorLLM:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        user_agent: str = "mp3-to-videoclip-studio/0.1",
        session_id: str | None = None,
        idle_limit: float = IDLE_LIMIT,
    ):
        self.model = model
        self.idle_limit = idle_limit
        self._client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=httpx.Timeout(idle_limit, connect=CONNECT_LIMIT),
            max_retries=MAX_RETRIES,
            default_headers={
                "User-Agent": user_agent,
                "x-opencode-session": session_id or "studio",
            },
        )

    async def _chunks(self, kwargs: dict[str, Any]) -> AsyncIterator[Any]:
        """Yield stream chunks; raise StreamStalled after a silent idle limit.

        The socket timeout alone is not enough: keep-alive bytes reset it without
        ever producing a chunk.
        """
        limit = self.idle_limit
        try:
            stream = await asyncio.wait_for(self._client.chat.completions.create(**kwargs), limit)
            try:
                chunks = aiter(stream)
                while True:
                    try:
                        chunk = await asyncio.wait_for(anext(chunks), limit)
                    except StopAsyncIteration:
                        return
                    yield chunk
            finally:
                await stream.close()
        except (TimeoutError, httpx.TimeoutException, APITimeoutError) as exc:
            raise StreamStalled(limit) from exc

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
    ) -> AsyncIterator[TextDelta | Progress | ToolCall | Usage | TurnResult]:
        full_messages = list(messages)
        if system:
            full_messages = [{"role": "system", "content": system}] + full_messages

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": full_messages,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        accumulated_text = ""
        tool_calls_acc: dict[int, dict[str, str]] = {}
        usage = Usage()
        finish_reason = None

        writing = ""
        last_progress = time.monotonic()

        async with aclosing(self._chunks(kwargs)) as chunks:
            async for chunk in chunks:
                if not chunk.choices:
                    if chunk.usage:
                        usage.prompt_tokens = chunk.usage.prompt_tokens or 0
                        usage.completion_tokens = chunk.usage.completion_tokens or 0
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                named = False
                if delta.content:
                    accumulated_text += delta.content
                    yield TextDelta(text=delta.content)
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc.id:
                            tool_calls_acc[idx]["id"] = tc.id
                        if tc.function and tc.function.name:
                            tool_calls_acc[idx]["name"] = tc.function.name
                            writing = tc.function.name
                            named = True
                        if tc.function and tc.function.arguments:
                            tool_calls_acc[idx]["arguments"] += tc.function.arguments
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
                now = time.monotonic()
                if not delta.content and (named or now - last_progress >= PROGRESS_EVERY):
                    last_progress = now
                    yield Progress(
                        tool=writing,
                        chars=sum(len(tc["arguments"]) for tc in tool_calls_acc.values()),
                    )

        for idx in sorted(tool_calls_acc):
            tc = tool_calls_acc[idx]
            yield ToolCall(id=tc["id"], name=tc["name"], arguments=tc["arguments"])

        yield Usage(prompt_tokens=usage.prompt_tokens, completion_tokens=usage.completion_tokens)
        yield TurnResult(
            text=accumulated_text,
            tool_calls=[
                ToolCall(id=tc["id"], name=tc["name"], arguments=tc["arguments"])
                for tc in [tool_calls_acc[i] for i in sorted(tool_calls_acc)]
            ],
            usage=usage,
            finish_reason=finish_reason,
        )
