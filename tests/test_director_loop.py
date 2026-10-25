"""The director turn loop must execute tools and stop cleanly with a fake provider.

No network, no paid call. The fake streams one text delta and one tool call, then
a final turn; the test proves the tool ran, the result was fed back and the turn
ended with a done event.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

from mp3_to_videoclip.director.llm import TextDelta, ToolCall, TurnResult, Usage
from mp3_to_videoclip.director.loop import run_turn


class FakeLLM:
    def __init__(self):
        self.calls = []
        self.systems = []
        self.n = 0

    async def stream(self, messages, tools=None, system=None):
        self.calls.append(list(messages))
        self.systems.append(system)
        self.n += 1
        if self.n == 1:
            yield TextDelta(text="Checking the project. ")
            yield ToolCall(id="call-1", name="get_project", arguments='{"slug": "demo"}')
            yield Usage(prompt_tokens=1, completion_tokens=1)
            yield TurnResult(
                text="Checking the project. ",
                tool_calls=[
                    ToolCall(id="call-1", name="get_project", arguments='{"slug": "demo"}')
                ],
            )
        else:
            yield TextDelta(text="Done.")
            yield Usage(prompt_tokens=1, completion_tokens=1)
            yield TurnResult(text="Done.")


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "projects" / "demo"
    root.mkdir(parents=True)
    (root / "project.json").write_text(
        json.dumps(
            {
                "schema_version": 3,
                "slug": "demo",
                "title": "Demo",
                "source": "media/song.mp3",
                "source_sha256": "a" * 64,
                "duration": 60.0,
                "aspect": "16:9",
                "fps": 24,
                "width": 1920,
                "height": 1080,
            }
        )
    )
    (root / "media").mkdir()
    source = root / "media" / "song.mp3"
    source.write_bytes(b"x")
    data = json.loads((root / "project.json").read_text())
    data["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    (root / "project.json").write_text(json.dumps(data))
    return root


def test_turn_runs_a_tool_and_stops(tmp_path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    llm = FakeLLM()
    events = asyncio.run(_collect(llm, root))
    kinds = [e.kind for e in events]
    assert "tool" in kinds
    assert kinds[-1] == "done"
    assert any("Demo" in e.result for e in events if e.kind == "tool")


async def _collect(llm, root):
    return [e async for e in run_turn(llm, root, "demo", "What is this?", "system")]


def test_long_history_is_compacted_before_the_model_call(tmp_path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    history = []
    for index in range(40):
        history.append({"role": "user", "content": f"request {index}"})
        history.append({"role": "assistant", "content": f"answer {index}"})
    path = root / "work" / "chat.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(message) for message in history) + "\n")

    llm = FakeLLM()
    asyncio.run(_collect(llm, root))

    sent = llm.calls[0]
    assert len(sent) < len(history) + 1
    assert sent[0]["role"] == "user"
    assert "Earlier conversation compressed" in llm.systems[0]
    assert "request 39" in llm.systems[0] or "request 39" in json.dumps(sent)
    stored = [json.loads(line) for line in path.read_text().splitlines()]
    assert stored[:2] == history[:2]
    assert len(stored) > len(history)


class SlowLLM:
    async def stream(self, messages, tools=None, system=None):
        yield TextDelta(text="Thinking")
        await asyncio.sleep(5)
        yield TurnResult(text="Too late")


def test_closing_the_stream_stops_within_one_second(tmp_path, monkeypatch):
    import time

    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)

    async def first_and_close():
        stream = run_turn(SlowLLM(), root, "demo", "go", "system")
        first = await stream.__anext__()
        assert first.kind == "text"
        started = time.perf_counter()
        await stream.aclose()
        return time.perf_counter() - started

    assert asyncio.run(first_and_close()) < 1.0
