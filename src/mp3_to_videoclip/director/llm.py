"""Director LLM adapter: OpenAI-compatible streaming with tool calls.

Targets OpenCode Go (deepseek-v4.1-flash) by default; any OpenAI-compatible
provider is a settings change. Phase 3 starts with scripts/probe_llm.py to
verify tool calling and vision before relying on them.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI


@dataclass
class TextDelta:
    text: str


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str


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
    ):
        self.model = model
        self._client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            default_headers={
                "User-Agent": user_agent,
                "x-opencode-session": session_id or "studio",
            },
        )

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
    ) -> AsyncIterator[TextDelta | ToolCall | Usage | TurnResult]:
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

        async for chunk in await self._client.chat.completions.create(**kwargs):
            if not chunk.choices:
                if chunk.usage:
                    usage.prompt_tokens = chunk.usage.prompt_tokens or 0
                    usage.completion_tokens = chunk.usage.completion_tokens or 0
                continue
            choice = chunk.choices[0]
            delta = choice.delta
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
                    if tc.function and tc.function.arguments:
                        tool_calls_acc[idx]["arguments"] += tc.function.arguments
            if choice.finish_reason:
                finish_reason = choice.finish_reason

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
