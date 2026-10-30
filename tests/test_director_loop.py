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
from types import SimpleNamespace

from api_support import add_assets, make_api_project

from mp3_to_videoclip.director.llm import (
    IDLE_LIMIT,
    MAX_RETRIES,
    DirectorLLM,
    TextDelta,
    ToolCall,
    TurnResult,
    Usage,
)
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


class _Delta:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _Chunk:
    usage = None

    def __init__(self, delta, finish_reason=None):
        self.choices = [SimpleNamespace(delta=delta, finish_reason=finish_reason)]


def _tool_delta(name=None, arguments=None):
    function = SimpleNamespace(name=name, arguments=arguments)
    return _Delta(tool_calls=[SimpleNamespace(index=0, id="call-1", function=function)])


class _FakeStream:
    """An OpenAI stream that sends its chunks and then, if told to, goes silent."""

    def __init__(self, chunks, stall):
        self.chunks = chunks
        self.stall = stall
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk
        if self.stall:
            await asyncio.Event().wait()

    async def close(self):
        self.closed = True


def _llm_over(stream, idle_limit=0.05):
    llm = DirectorLLM(
        base_url="http://127.0.0.1:9/v1", api_key="test", model="m", idle_limit=idle_limit
    )

    async def create(**kwargs):
        return stream

    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return llm


def test_a_stalled_tool_call_ends_the_turn_with_a_plain_error_and_writes_nothing(
    tmp_path, monkeypatch
):
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    # A real write, cut off halfway through its arguments.
    stream = _FakeStream(
        [
            _Chunk(_Delta(content="Rewriting the story. ")),
            _Chunk(_tool_delta(name="update_brief")),
            _Chunk(_tool_delta(arguments='{"slug": "demo", "brief": {"title": "Half')),
        ],
        stall=True,
    )

    async def run():
        return [
            event
            async for event in run_turn(
                _llm_over(stream), root, "demo", "Rewrite it.", "system", role="writer"
            )
        ]

    events = asyncio.run(asyncio.wait_for(run(), 5))

    last = events[-1]
    assert last.kind == "done"
    assert last.payload["stalled"] is True
    assert "The Writer sent nothing" in last.payload["error"]
    assert "Nothing was lost" in last.payload["error"]
    assert stream.closed
    # The reader saw the tool call being written, and it never ran.
    assert any(e.kind == "progress" and e.tool == "update_brief" for e in events)
    assert not [e for e in events if e.kind == "tool"]

    chat = root / "work" / "chat.jsonl"
    stored = [json.loads(line) for line in chat.read_text().splitlines()]
    assert [(m["role"], m["content"]) for m in stored] == [
        ("user", "Rewrite it."),
        ("assistant", "Rewriting the story. "),
    ]
    after = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    assert {path: data for path, data in after.items() if path != chat} == before


def test_a_model_that_never_answers_is_bounded_too(tmp_path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    llm = _llm_over(_FakeStream([], stall=False))

    async def create(**kwargs):
        await asyncio.Event().wait()

    llm._client.chat.completions.create = create

    async def run():
        return [event async for event in run_turn(llm, root, "demo", "Hello?", "system")]

    events = asyncio.run(asyncio.wait_for(run(), 5))
    assert [event.kind for event in events] == ["done"]
    assert "The Director sent nothing" in events[0].payload["error"]


def test_slow_tool_arguments_that_keep_arriving_are_not_a_stall(tmp_path, monkeypatch):
    """The whole call outlasts the limit; no single gap does."""
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)

    class Trickle(_FakeStream):
        async def __aiter__(self):
            yield _Chunk(_tool_delta(name="get_project"))
            for part in ('{"slug"', ': "de', 'mo"', "}"):
                await asyncio.sleep(0.1)
                yield _Chunk(_tool_delta(arguments=part))

    class Then(_FakeStream):
        async def __aiter__(self):
            yield _Chunk(_Delta(content="Done."), finish_reason="stop")

    streams = iter([Trickle([], False), Then([], False)])
    llm = _llm_over(None, idle_limit=0.3)

    async def create(**kwargs):
        return next(streams)

    llm._client.chat.completions.create = create

    async def run():
        return [event async for event in run_turn(llm, root, "demo", "Go.", "system")]

    events = asyncio.run(run())
    assert events[-1].kind == "done"
    assert "error" not in events[-1].payload
    assert any("Demo" in e.result for e in events if e.kind == "tool")


def test_the_direct_client_does_not_keep_the_library_defaults():
    llm = DirectorLLM(base_url="http://127.0.0.1:9/v1", api_key="test", model="m")
    assert llm._client.timeout.read == IDLE_LIMIT
    assert llm._client.max_retries == MAX_RETRIES
    # A long tool call takes a minute or more and must fit well inside the limit.
    assert IDLE_LIMIT >= 120
