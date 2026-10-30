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

from api_support import add_assets, make_api_project

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


async def _collect_in_projects(llm, root, projects_dir):
    return [
        event
        async for event in run_turn(
            llm,
            root,
            "production",
            "Look at s001 and s002.",
            "system",
            projects_dir=projects_dir,
        )
    ]


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


def test_the_loop_passes_tool_thumbnails_to_the_next_model_call(tmp_path):
    root = make_api_project(tmp_path)
    add_assets(root)

    class ImageLLM:
        def __init__(self):
            self.calls = []
            self.n = 0

        async def stream(self, messages, tools=None, system=None):
            self.calls.append(messages)
            self.n += 1
            if self.n == 1:
                call = ToolCall(
                    id="call-images",
                    name="get_images",
                    arguments='{"slug": "production", "shot_ids": ["s001", "s002"]}',
                )
                yield call
                yield TurnResult(text="", tool_calls=[call])
            else:
                last = messages[-1]
                assert last["role"] == "user"
                assert isinstance(last["content"], list)
                assert any(part.get("type") == "image_url" for part in last["content"])
                assert sum(part.get("type") == "image_url" for part in last["content"]) == 2
                yield TextDelta(text="I inspected both stills.")
                yield TurnResult(text="I inspected both stills.")

    llm = ImageLLM()
    events = asyncio.run(_collect_in_projects(llm, root, tmp_path))
    assert events[-1].kind == "done"
    assert len(llm.calls) == 2
    chat = (root / "work" / "chat.jsonl").read_text()
    assert "data:image" not in chat
    stored = [json.loads(line) for line in chat.splitlines()]
    tool = next(message for message in stored if message.get("name") == "get_images")
    assert json.loads(tool["content"])["image_count"] == 2


def test_the_loop_keeps_parallel_tool_results_before_the_image_message(tmp_path):
    root = make_api_project(tmp_path)
    add_assets(root)

    class ParallelLLM:
        def __init__(self):
            self.calls = []
            self.n = 0

        async def stream(self, messages, tools=None, system=None):
            self.calls.append(messages)
            self.n += 1
            if self.n == 1:
                calls = [
                    ToolCall(
                        id="call-project", name="get_project", arguments='{"slug": "production"}'
                    ),
                    ToolCall(
                        id="call-images",
                        name="get_images",
                        arguments='{"slug": "production", "shot_ids": ["s001"]}',
                    ),
                ]
                for call in calls:
                    yield call
                yield TurnResult(text="", tool_calls=calls)
            else:
                roles = [message["role"] for message in messages[-3:]]
                assert roles == ["tool", "tool", "user"], roles
                assert isinstance(messages[-1]["content"], list)
                yield TurnResult(text="Done.", tool_calls=[])

    llm = ParallelLLM()
    events = asyncio.run(_collect_in_projects(llm, root, tmp_path))
    assert events[-1].kind == "done"
    assert len(llm.calls) == 2


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


def test_each_role_sees_and_writes_only_its_own_thread(tmp_path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    path = root / "work" / "chat.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    writer_prompt = {"hash": "w", "files": [{"path": "writer/system.md", "version": 1}]}
    history = [
        {"role": "user", "content": "before the split"},
        {"role": "assistant", "content": "shared answer"},
        {"role": "user", "content": "rewrite the brief", "prompt": writer_prompt},
        {"role": "tool", "name": "update_brief", "content": "ok"},
        {"role": "assistant", "content": "brief rewritten"},
        {"role": "user", "content": "tighten the cut", "agent": "editor"},
        {"role": "assistant", "content": "cut tightened", "agent": "editor"},
    ]
    path.write_text("\n".join(json.dumps(message) for message in history) + "\n")

    llm = FakeLLM()

    async def editor_turn():
        return [
            event async for event in run_turn(llm, root, "demo", "next?", "system", role="editor")
        ]

    asyncio.run(editor_turn())

    sent = [message.get("content") for message in llm.calls[0]]
    assert sent == [
        "before the split",
        "shared answer",
        "tighten the cut",
        "cut tightened",
        "next?",
    ]
    assert all("agent" not in message for message in llm.calls[0])
    stored = [json.loads(line) for line in path.read_text().splitlines()]
    assert stored[: len(history)] == history
    assert {message.get("agent") for message in stored[len(history) :]} == {"editor"}

    from mp3_to_videoclip.director.conversation import load_messages

    writer = [message["content"] for message in load_messages(root, "writer")]
    assert writer == [
        "before the split",
        "shared answer",
        "rewrite the brief",
        "ok",
        "brief rewritten",
    ]
    assert len(load_messages(root)) == len(stored)
