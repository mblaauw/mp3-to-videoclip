"""Anthropic's Messages API, over plain HTTP streaming."""

from __future__ import annotations

import json
from contextlib import aclosing

import httpx

from .base import (
    CONNECT_LIMIT,
    Progress,
    TextDelta,
    ToolCall,
    TurnResult,
    Usage,
    image_part,
    parsed_arguments,
    sse_events,
)

VERSION = "2023-06-01"
MAX_TOKENS = 8192


def _content(value) -> list[dict]:
    if isinstance(value, str):
        return [{"type": "text", "text": value}] if value else []
    parts = []
    for part in value or []:
        if part.get("type") == "text":
            parts.append({"type": "text", "text": part["text"]})
        elif part.get("type") == "image_url":
            found = image_part(part["image_url"]["url"])
            if found:
                source = {"type": "base64", "media_type": found[0], "data": found[1]}
                parts.append({"type": "image", "source": source})
    return parts


def translate_messages(messages: list[dict]) -> list[dict]:
    """Tool results go in a user turn, and the first turn must be the user's."""
    out: list[dict] = []

    def add(role: str, parts: list[dict]) -> None:
        if not parts:
            return
        if out and out[-1]["role"] == role:
            out[-1]["content"].extend(parts)
        else:
            out.append({"role": role, "content": parts})

    for message in messages:
        role = message["role"]
        if role == "tool":
            add(
                "user",
                [
                    {
                        "type": "tool_result",
                        "tool_use_id": message["tool_call_id"],
                        "content": message.get("content") or "",
                    }
                ],
            )
        elif role == "assistant":
            parts = _content(message.get("content"))
            for call in message.get("tool_calls") or []:
                function = call["function"]
                parts.append(
                    {
                        "type": "tool_use",
                        "id": call["id"],
                        "name": function["name"],
                        "input": parsed_arguments(function.get("arguments")),
                    }
                )
            add("assistant", parts)
        else:
            add("user", _content(message.get("content")))
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


def translate_tools(tools: list[dict]) -> list[dict]:
    return [
        {
            "name": tool["function"]["name"],
            "description": tool["function"].get("description", ""),
            "input_schema": tool["function"].get("parameters") or {"type": "object"},
        }
        for tool in tools
    ]


class Anthropic:
    def __init__(self, *, base_url, api_key, model, headers, idle_limit, transport=None):
        self.model = model
        self.idle_limit = idle_limit
        self.url = f"{(base_url or 'https://api.anthropic.com/v1').rstrip('/')}/messages"
        self.headers = {
            **headers,
            "x-api-key": api_key,
            "anthropic-version": VERSION,
            "content-type": "application/json",
        }
        self.client = httpx.AsyncClient(
            transport=transport, timeout=httpx.Timeout(idle_limit, connect=CONNECT_LIMIT)
        )

    async def stream(self, messages, tools=None, system=None):
        body = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "stream": True,
            "messages": translate_messages(messages),
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = translate_tools(tools)
        text = ""
        blocks: dict[int, dict[str, str]] = {}
        usage = Usage()
        finish = None
        async with aclosing(
            sse_events(
                self.client,
                "POST",
                self.url,
                headers=self.headers,
                body=body,
                idle_limit=self.idle_limit,
            )
        ) as events:
            async for event in events:
                kind = event.get("type")
                if kind == "message_start":
                    counted = (event.get("message") or {}).get("usage") or {}
                    usage.prompt_tokens = counted.get("input_tokens") or 0
                    usage.cached_tokens = counted.get("cache_read_input_tokens") or 0
                    usage.reported = True
                elif kind == "content_block_start":
                    block = event.get("content_block") or {}
                    if block.get("type") == "tool_use":
                        blocks[event["index"]] = {"id": block["id"], "name": block["name"], "arguments": ""}  # fmt: skip
                        yield Progress(tool=block["name"])
                elif kind == "content_block_delta":
                    delta = event.get("delta") or {}
                    if delta.get("type") == "text_delta":
                        text += delta["text"]
                        yield TextDelta(text=delta["text"])
                    elif delta.get("type") == "input_json_delta" and event["index"] in blocks:
                        blocks[event["index"]]["arguments"] += delta.get("partial_json") or ""
                        yield Progress(
                            tool=blocks[event["index"]]["name"],
                            chars=sum(len(block["arguments"]) for block in blocks.values()),
                        )
                elif kind == "message_delta":
                    finish = (event.get("delta") or {}).get("stop_reason") or finish
                    counted = event.get("usage") or {}
                    if counted.get("output_tokens") is not None:
                        usage.completion_tokens = counted["output_tokens"]
                        usage.reported = True
        calls = [
            ToolCall(
                id=blocks[i]["id"],
                name=blocks[i]["name"],
                arguments=blocks[i]["arguments"] or json.dumps({}),
            )
            for i in sorted(blocks)
        ]
        for call in calls:
            yield call
        yield usage
        yield TurnResult(text=text, tool_calls=calls, usage=usage, finish_reason=finish)
