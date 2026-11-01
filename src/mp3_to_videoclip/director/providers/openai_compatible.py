"""OpenAI, OpenCode Go and anything else that speaks chat completions."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import Any

import httpx
from openai import APITimeoutError, AsyncOpenAI, BadRequestError

from .base import (
    CONNECT_LIMIT,
    MAX_RETRIES,
    Progress,
    StreamStalled,
    TextDelta,
    ToolCall,
    TurnResult,
    Usage,
)

PROGRESS_EVERY = 1.0


class OpenAICompatible:
    def __init__(self, *, base_url, api_key, model, headers, idle_limit, transport=None):
        self.model = model
        self.idle_limit = idle_limit
        self.ask_for_usage = True
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=httpx.Timeout(idle_limit, connect=CONNECT_LIMIT),
            max_retries=MAX_RETRIES,
            default_headers=headers,
            http_client=httpx.AsyncClient(transport=transport) if transport else None,
        )

    async def _chunks(self, kwargs: dict[str, Any]) -> AsyncIterator[Any]:
        """Yield stream chunks; raise StreamStalled after a silent idle limit.

        The socket timeout alone is not enough: keep-alive bytes reset it without
        ever producing a chunk.
        """
        limit = self.idle_limit
        try:
            stream = await asyncio.wait_for(self.client.chat.completions.create(**kwargs), limit)
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

    async def stream(self, messages, tools=None, system=None):
        full = [{"role": "system", "content": system}, *messages] if system else list(messages)
        kwargs: dict[str, Any] = {"model": self.model, "messages": full, "stream": True}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if self.ask_for_usage:
            kwargs["stream_options"] = {"include_usage": True}
        try:
            async with aclosing(self._read(kwargs)) as events:
                async for event in events:
                    yield event
        except BadRequestError:
            # Not every compatible endpoint takes this option, and it is only a nicety.
            if "stream_options" not in kwargs:
                raise
            self.ask_for_usage = False
            kwargs.pop("stream_options")
            async with aclosing(self._read(kwargs)) as events:
                async for event in events:
                    yield event

    async def _read(self, kwargs: dict[str, Any]):
        accumulated = ""
        calls: dict[int, dict[str, str]] = {}
        usage = Usage()
        finish_reason = None
        writing = ""
        last_progress = time.monotonic()
        async with aclosing(self._chunks(kwargs)) as chunks:
            async for chunk in chunks:
                counted = getattr(chunk, "usage", None)
                if counted:
                    details = getattr(counted, "prompt_tokens_details", None)
                    usage = Usage(
                        prompt_tokens=counted.prompt_tokens or 0,
                        completion_tokens=counted.completion_tokens or 0,
                        cached_tokens=getattr(details, "cached_tokens", 0) or 0,
                        reported=True,
                    )
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                named = False
                if delta.content:
                    accumulated += delta.content
                    yield TextDelta(text=delta.content)
                if delta.tool_calls:
                    for call in delta.tool_calls:
                        slot = calls.setdefault(call.index, {"id": "", "name": "", "arguments": ""})
                        if call.id:
                            slot["id"] = call.id
                        if call.function and call.function.name:
                            slot["name"] = call.function.name
                            writing = call.function.name
                            named = True
                        if call.function and call.function.arguments:
                            slot["arguments"] += call.function.arguments
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
                now = time.monotonic()
                if not delta.content and (named or now - last_progress >= PROGRESS_EVERY):
                    last_progress = now
                    yield Progress(
                        tool=writing, chars=sum(len(call["arguments"]) for call in calls.values())
                    )
        finished = [
            ToolCall(id=calls[i]["id"], name=calls[i]["name"], arguments=calls[i]["arguments"])
            for i in sorted(calls)
        ]
        for call in finished:
            yield call
        yield usage
        yield TurnResult(
            text=accumulated, tool_calls=finished, usage=usage, finish_reason=finish_reason
        )
