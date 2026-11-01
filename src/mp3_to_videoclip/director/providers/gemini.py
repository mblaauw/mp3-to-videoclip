"""Google's Gemini API, over plain HTTP streaming."""

from __future__ import annotations

import json
from contextlib import aclosing
from uuid import uuid4

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

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
#: Gemini's function declarations take a subset of JSON Schema and refuse the rest.
UNSUPPORTED = {"additionalProperties", "$schema", "$ref", "$defs", "default", "const"}


def clean_schema(schema):
    if isinstance(schema, dict):
        return {key: clean_schema(value) for key, value in schema.items() if key not in UNSUPPORTED}
    if isinstance(schema, list):
        return [clean_schema(item) for item in schema]
    return schema


def _parts(value) -> list[dict]:
    if isinstance(value, str):
        return [{"text": value}] if value else []
    parts = []
    for part in value or []:
        if part.get("type") == "text":
            parts.append({"text": part["text"]})
        elif part.get("type") == "image_url":
            found = image_part(part["image_url"]["url"])
            if found:
                parts.append({"inline_data": {"mime_type": found[0], "data": found[1]}})
    return parts


def translate_messages(messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    names: dict[str, str] = {}

    def add(role: str, parts: list[dict]) -> None:
        if not parts:
            return
        if out and out[-1]["role"] == role:
            out[-1]["parts"].extend(parts)
        else:
            out.append({"role": role, "parts": parts})

    for message in messages:
        role = message["role"]
        if role == "tool":
            name = message.get("name") or names.get(message.get("tool_call_id"), "tool")
            response = {"name": name, "response": {"content": message.get("content") or ""}}
            add("user", [{"functionResponse": response}])
        elif role == "assistant":
            parts = _parts(message.get("content"))
            for call in message.get("tool_calls") or []:
                function = call["function"]
                names[call["id"]] = function["name"]
                part = {
                    "functionCall": {
                        "name": function["name"],
                        "args": parsed_arguments(function.get("arguments")),
                    }
                }
                if call.get("signature"):
                    part["thoughtSignature"] = call["signature"]
                parts.append(part)
            add("model", parts)
        else:
            add("user", _parts(message.get("content")))
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


def translate_tools(tools: list[dict]) -> list[dict]:
    declarations = []
    for tool in tools:
        function = tool["function"]
        declared = {"name": function["name"], "description": function.get("description", "")}
        schema = function.get("parameters")
        if schema and schema.get("properties"):
            declared["parameters"] = clean_schema(schema)
        declarations.append(declared)
    return [{"functionDeclarations": declarations}]


class Gemini:
    def __init__(self, *, base_url, api_key, model, headers, idle_limit, transport=None):
        self.model = model
        self.idle_limit = idle_limit
        root = (base_url or BASE_URL).rstrip("/")
        self.url = f"{root}/models/{model}:streamGenerateContent?alt=sse"
        self.headers = {**headers, "x-goog-api-key": api_key, "content-type": "application/json"}
        self.client = httpx.AsyncClient(
            transport=transport, timeout=httpx.Timeout(idle_limit, connect=CONNECT_LIMIT)
        )

    async def stream(self, messages, tools=None, system=None):
        body = {"contents": translate_messages(messages)}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            body["tools"] = translate_tools(tools)
        text = ""
        calls: list[ToolCall] = []
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
                counted = event.get("usageMetadata")
                if counted:
                    usage = Usage(
                        prompt_tokens=counted.get("promptTokenCount") or 0,
                        completion_tokens=counted.get("candidatesTokenCount") or 0,
                        cached_tokens=counted.get("cachedContentTokenCount") or 0,
                        reported=True,
                    )
                candidates = event.get("candidates") or []
                if not candidates:
                    continue
                finish = candidates[0].get("finishReason") or finish
                for part in (candidates[0].get("content") or {}).get("parts") or []:
                    if part.get("text") and not part.get("thought"):
                        text += part["text"]
                        yield TextDelta(text=part["text"])
                    call = part.get("functionCall")
                    if call:
                        calls.append(
                            ToolCall(
                                id=f"gemini-{uuid4().hex[:12]}",
                                name=call["name"],
                                arguments=json.dumps(call.get("args") or {}),
                                signature=part.get("thoughtSignature") or "",
                            )
                        )
                        yield Progress(tool=call["name"])
        for call in calls:
            yield call
        yield usage
        yield TurnResult(text=text, tool_calls=calls, usage=usage, finish_reason=finish)
