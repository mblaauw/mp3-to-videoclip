"""Each provider against a recorded stream. No network, and the payloads are pinned exactly."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from mp3_to_videoclip.config import Settings
from mp3_to_videoclip.director import providers, routing
from mp3_to_videoclip.director.llm import (
    DirectorLLM,
    ProviderFailure,
    TextDelta,
    ToolCall,
    TurnResult,
    Usage,
    service_failed_message,
)
from mp3_to_videoclip.director.providers import anthropic, gemini

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_brief",
            "description": "Read the brief.",
            "parameters": {
                "type": "object",
                "properties": {"slug": {"type": "string", "default": "x"}},
                "additionalProperties": False,
                "required": ["slug"],
            },
        },
    }
]
THUMB = "data:image/jpeg;base64,/9j/AA=="
HISTORY = [
    {"role": "user", "content": "Look at this."},
    {
        "role": "assistant",
        "content": "Reading it.",
        "tool_calls": [
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "get_brief", "arguments": '{"slug": "a"}'},
            }
        ],
    },
    {"role": "tool", "tool_call_id": "c1", "name": "get_brief", "content": "the brief"},
    {
        "role": "user",
        "content": [
            {"type": "text", "text": "One thumbnail."},
            {"type": "image_url", "image_url": {"url": THUMB, "detail": "low"}},
        ],
    },
]


def sse(*events) -> httpx.Response:
    lines = "".join(f"data: {json.dumps(event)}\n\n" for event in events)
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=lines)


def run(llm, messages=HISTORY, tools=TOOLS, system="Be brief."):
    async def collect():
        return [event async for event in llm.stream(messages, tools=tools, system=system)]

    return asyncio.run(collect())


def _llm(kind, handler, **kwargs):
    return DirectorLLM(
        "https://x.test/v1", "s3", "m", kind=kind, transport=httpx.MockTransport(handler), **kwargs
    )


# ------------------------------------------------------------------ Anthropic


def test_anthropic_payload_is_what_its_api_takes():
    messages = anthropic.translate_messages(HISTORY)
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    assert messages[1]["content"][1] == {
        "type": "tool_use",
        "id": "c1",
        "name": "get_brief",
        "input": {"slug": "a"},
    }
    last = messages[2]["content"]
    assert last[0] == {"type": "tool_result", "tool_use_id": "c1", "content": "the brief"}
    assert last[2] == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/jpeg", "data": "/9j/AA=="},
    }


def test_anthropic_never_starts_with_the_assistant_and_drops_empty_text():
    messages = anthropic.translate_messages(
        [
            {"role": "assistant", "content": "Earlier."},
            {"role": "user", "content": "Now."},
            {"role": "assistant", "content": ""},
            {"role": "user", "content": "Again."},
        ]
    )
    assert [m["role"] for m in messages] == ["user"]
    assert len(messages[0]["content"]) == 2


def test_anthropic_streams_text_tools_and_usage():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["headers"] = request.headers
        seen["body"] = json.loads(request.content)
        return sse(
            {"type": "message_start", "message": {"usage": {"input_tokens": 11}}},
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text"}},
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "Hi"},
            },
            {
                "type": "content_block_start",
                "index": 1,
                "content_block": {"type": "tool_use", "id": "t1", "name": "get_brief"},
            },
            {
                "type": "content_block_delta",
                "index": 1,
                "delta": {"type": "input_json_delta", "partial_json": '{"slug"'},
            },
            {
                "type": "content_block_delta",
                "index": 1,
                "delta": {"type": "input_json_delta", "partial_json": ': "a"}'},
            },
            {
                "type": "message_delta",
                "delta": {"stop_reason": "tool_use"},
                "usage": {"output_tokens": 7},
            },
        )

    events = run(_llm("anthropic", handler))
    assert seen["url"] == "https://x.test/v1/messages"
    assert seen["headers"]["x-api-key"] == "s3"
    assert seen["body"]["system"] == "Be brief."
    assert seen["body"]["tools"][0]["input_schema"]["required"] == ["slug"]
    assert seen["body"]["max_tokens"] > 0
    assert [e.text for e in events if isinstance(e, TextDelta)] == ["Hi"]
    call = next(e for e in events if isinstance(e, ToolCall))
    assert (call.id, call.name, json.loads(call.arguments)) == ("t1", "get_brief", {"slug": "a"})
    usage = next(e for e in events if isinstance(e, Usage))
    assert (usage.prompt_tokens, usage.completion_tokens, usage.reported) == (11, 7, True)
    assert isinstance(events[-1], TurnResult)


# ------------------------------------------------------------------ Gemini


def test_gemini_payload_is_what_its_api_takes():
    contents = gemini.translate_messages(HISTORY)
    assert [c["role"] for c in contents] == ["user", "model", "user"]
    assert contents[1]["parts"][1] == {"functionCall": {"name": "get_brief", "args": {"slug": "a"}}}
    assert contents[2]["parts"][0] == {
        "functionResponse": {"name": "get_brief", "response": {"content": "the brief"}}
    }
    assert contents[2]["parts"][2] == {
        "inline_data": {"mime_type": "image/jpeg", "data": "/9j/AA=="}
    }


def test_gemini_gets_only_the_schema_it_accepts():
    declared = gemini.translate_tools(TOOLS)[0]["functionDeclarations"][0]
    assert "additionalProperties" not in declared["parameters"]
    assert "default" not in declared["parameters"]["properties"]["slug"]
    bare = {
        "type": "function",
        "function": {"name": "x", "parameters": {"type": "object", "properties": {}}},
    }
    assert "parameters" not in gemini.translate_tools([bare])[0]["functionDeclarations"][0]


def test_gemini_gives_a_thought_signature_back():
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "c", "function": {"name": "x", "arguments": "{}"}, "signature": "SIG"}
            ],
        }
    ]
    contents = gemini.translate_messages([{"role": "user", "content": "go"}, *messages])
    assert contents[1]["parts"][0]["thoughtSignature"] == "SIG"


def test_gemini_streams_text_tools_and_usage():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["headers"] = request.headers
        seen["body"] = json.loads(request.content)
        return sse(
            {
                "candidates": [
                    {"content": {"parts": [{"text": "Hi"}, {"text": "hidden", "thought": True}]}}
                ]
            },
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "functionCall": {"name": "get_brief", "args": {"slug": "a"}},
                                    "thoughtSignature": "SIG",
                                }
                            ]
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 3},
            },
        )

    events = run(_llm("gemini", handler))
    assert seen["url"] == "https://x.test/v1/models/m:streamGenerateContent?alt=sse"
    assert seen["headers"]["x-goog-api-key"] == "s3"
    assert seen["body"]["systemInstruction"]["parts"][0]["text"] == "Be brief."
    assert [e.text for e in events if isinstance(e, TextDelta)] == ["Hi"]
    call = next(e for e in events if isinstance(e, ToolCall))
    assert (call.name, call.signature) == ("get_brief", "SIG")
    usage = next(e for e in events if isinstance(e, Usage))
    assert (usage.prompt_tokens, usage.completion_tokens) == (5, 3)


# ------------------------------------------------------------------ OpenAI-compatible


def _chunk(delta=None, usage=None, finish=None):
    choices = [{"index": 0, "delta": delta, "finish_reason": finish}] if delta is not None else []
    return {
        "id": "x",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "m",
        "choices": choices,
        "usage": usage,
    }


def test_openai_compatible_asks_for_usage_and_reads_it():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return sse(
            _chunk({"content": "Hi"}),
            _chunk(usage={"prompt_tokens": 9, "completion_tokens": 2, "total_tokens": 11}),
        )

    events = run(_llm("openai-compatible", handler))
    assert seen["body"]["stream_options"] == {"include_usage": True}
    assert seen["body"]["messages"][0] == {"role": "system", "content": "Be brief."}
    usage = next(e for e in events if isinstance(e, Usage))
    assert (usage.prompt_tokens, usage.completion_tokens, usage.reported) == (9, 2, True)


def test_a_stream_with_no_counts_is_not_reported_as_zero():
    events = run(_llm("openai-compatible", lambda request: sse(_chunk({"content": "Hi"}))))
    assert next(e for e in events if isinstance(e, Usage)).reported is False


def test_an_endpoint_that_refuses_the_usage_option_is_asked_again_without_it():
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if "stream_options" in body:
            return httpx.Response(400, json={"error": {"message": "unknown stream_options"}})
        return sse(_chunk({"content": "Hi"}))

    events = run(_llm("openai-compatible", handler))
    assert len(bodies) == 2
    assert [e.text for e in events if isinstance(e, TextDelta)] == ["Hi"]


# ------------------------------------------------------------------ Failures


@pytest.mark.parametrize("kind", ["anthropic", "gemini"])
@pytest.mark.parametrize("status", [401, 404])
def test_a_refusal_is_a_failure_with_its_status_and_is_not_retried(kind, status):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status, text="secret s3 in a body")

    with pytest.raises(ProviderFailure) as caught:
        run(_llm(kind, handler))
    assert caught.value.status_code == status
    assert len(calls) == 1
    assert "s3" not in str(caught.value)


@pytest.mark.parametrize("kind", ["anthropic", "gemini"])
def test_a_busy_service_is_retried_once(kind):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503)

    with pytest.raises(ProviderFailure):
        run(_llm(kind, handler))
    assert len(calls) == 2


def test_the_owner_hears_what_to_do_about_a_refusal():
    refused = service_failed_message("writer", ProviderFailure(401), "m")
    assert "refused the key" in refused and "Settings" in refused
    missing = service_failed_message("writer", ProviderFailure(404), "m")
    assert "doesn't offer m" in missing


def test_every_kind_in_the_catalogue_has_a_provider():
    from mp3_to_videoclip import catalog

    llm_kinds = {
        provider.kind
        for provider in catalog.load().providers
        if set(provider.unlocks) & {"writer", "editor", "critic"}
    }
    assert llm_kinds <= set(providers.KINDS)


# ------------------------------------------------------------------ Routing


def test_each_role_routes_to_its_own_provider_and_key():
    settings = Settings(
        keys={"openai": "o", "anthropic": "a", "gemini": "g", "opencode_go": "c"},
        roles={
            "writer": {"provider": "openai", "model": "w"},
            "editor": {"provider": "anthropic", "model": "e"},
            "critic": {"provider": "gemini", "model": "r"},
        },
    )
    writer = routing.route_for(settings, "writer")
    assert (writer.kind, writer.base_url, writer.key, writer.model) == (
        "openai-compatible",
        routing.OPENAI_URL,
        "o",
        "w",
    )
    assert routing.route_for(settings, "editor").kind == "anthropic"
    assert routing.route_for(settings, "critic").key == "g"


def test_with_no_openai_key_an_openai_model_goes_through_opencode_go():
    settings = Settings(llm_api_key="go-key", writer_model="openai/gpt-6.1-sol")
    writer = routing.route_for(settings, "writer")
    assert (writer.provider, writer.key, writer.base_url, writer.model) == (
        "opencode-go",
        "go-key",
        routing.OPENCODE_GO_URL,
        "gpt-6.1-sol",
    )
    assert writer.listed_under == "openai"


def test_an_openai_key_goes_to_openai_and_a_go_key_never_does():
    both = Settings(keys={"openai": "o", "opencode_go": "c"}, writer_model="openai/gpt-6.1-sol")
    writer = routing.route_for(both, "writer")
    assert (writer.provider, writer.key, writer.base_url) == ("openai", "o", routing.OPENAI_URL)
    neither = Settings(writer_model="openai/gpt-6.1-sol")
    assert routing.route_for(neither, "writer").key == ""
    assert routing.route_for(neither, "writer").provider == "openai"
    settings = Settings(llm_api_key="go-key", writer_model="openai/gpt-6.1-sol")
    editor = routing.route_for(settings, "editor")
    assert (editor.provider, editor.key, editor.base_url) == (
        "opencode-go",
        "go-key",
        routing.OPENCODE_GO_URL,
    )


def test_another_endpoint_keeps_its_key_to_itself():
    settings = Settings(llm_api_key="k", llm_base_url="https://mine.test/v1")
    assert routing.route_for(settings, "editor").key == ""


def test_the_direct_endpoint_and_a_foreign_name_go_to_the_configured_address():
    settings = Settings(
        llm_api_key="k",
        llm_base_url="https://mine.test/v1",
        roles={
            "writer": {"provider": "direct", "model": "m"},
            "editor": {"provider": "openrouter", "model": "a/b"},
        },
    )
    writer = routing.route_for(settings, "writer")
    assert (writer.base_url, writer.key, writer.model) == ("https://mine.test/v1", "k", "m")
    assert routing.route_for(settings, "editor").model == "openrouter/a/b"
