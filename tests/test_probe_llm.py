"""The live probe script against a recorded stream: it must check what its header says."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path

import httpx
from test_director_providers import _chunk, sse

from mp3_to_videoclip.director.llm import DirectorLLM

spec = importlib.util.spec_from_file_location(
    "probe_llm", Path(__file__).resolve().parents[1] / "scripts/probe_llm.py"
)
probe_llm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe_llm)

USAGE = {"prompt_tokens": 9, "completion_tokens": 2, "total_tokens": 11}


def _call(word):
    function = {"name": "echo", "arguments": json.dumps({"text": word})}
    return _chunk(
        {"tool_calls": [{"index": 0, "id": "c1", "type": "function", "function": function}]}
    )


def _probe(handler):
    llm = DirectorLLM("https://x.test/v1", "s3", "m", transport=httpx.MockTransport(handler))
    return asyncio.run(probe_llm.probe(llm))


def test_the_probe_sends_a_picture_and_the_tool_result_back():
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        if len(bodies) == 1:
            return sse(_call("red"), _chunk(usage=USAGE))
        return sse(_chunk({"content": "done"}), _chunk(usage=USAGE))

    assert all(_probe(handler).values())
    picture = bodies[0]["messages"][1]["content"][1]
    assert picture["image_url"]["url"].startswith("data:image/png;base64,")
    assert bodies[1]["messages"][-1] == {
        "role": "tool",
        "tool_call_id": "c1",
        "name": "echo",
        "content": "red",
    }


def test_the_probe_fails_a_model_that_cannot_see_or_call():
    blind = _probe(lambda request: sse(_call("blue"), _chunk({"content": "ok"})))
    assert blind["picture read"] is False and blind["usage reported"] is False
    mute = _probe(lambda request: sse(_chunk({"content": "I see red."})))
    assert mute == {
        "tool call": False,
        "usage reported": False,
        "streamed text": True,
        "picture read": False,
    }
