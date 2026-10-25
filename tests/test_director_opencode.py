"""Gateway process, config, event relay and Stop, without a real model call."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from api_support import make_api_project

from mp3_to_videoclip.director.opencode import (
    OpenCodeError,
    OpenCodeGateway,
    _version,
    discover_binary,
    gateway_config,
    parse_model,
    run_gateway_turn,
)

FAKE = """#!/usr/bin/env python3
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

port = int(sys.argv[sys.argv.index("--port") + 1])
version = "VERSION"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path != "/api/info":
            self.send_error(404)
            return
        if not self.headers.get("authorization", "").startswith("Basic "):
            self.send_response(401)
            self.end_headers()
            return
        body = json.dumps({"version": version}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


HTTPServer(("127.0.0.1", port), Handler).serve_forever()
"""


def _fake_binary(tmp_path: Path, version: str = "2.1.4") -> Path:
    path = tmp_path / "opencode"
    path.write_text(FAKE.replace("VERSION", version))
    path.chmod(0o755)
    return path


def _gateway(tmp_path: Path, binary: Path) -> OpenCodeGateway:
    return OpenCodeGateway(
        binary=str(binary),
        workspace=tmp_path / "workspace",
        projects_dir=tmp_path,
        writer_model="openai/gpt-6.1-sol",
        editor_model="opencode-go/deepseek-v4.1-flash",
    )


def test_gateway_config_denies_builtins_and_allows_studio_tools(tmp_path):
    config = gateway_config(projects_dir=tmp_path, python="/usr/bin/python3")
    assert config["default_agent"] == "writer"
    assert config["agents"]["writer"]["model"] == "openai/gpt-6.1-sol"
    assert config["agents"]["editor"]["model"] == "opencode-go/deepseek-v4.1-flash"
    permissions = config["agents"]["writer"]["permissions"]
    assert all(rule["action"] != "*" for rule in permissions)
    assert {"action": "shell", "resource": "*", "effect": "deny"} in permissions
    assert {"action": "edit", "resource": "*", "effect": "deny"} in permissions
    assert {"action": "execute", "resource": "*", "effect": "deny"} in permissions
    assert permissions[-1] == {"action": "clipstudio_*", "resource": "*", "effect": "allow"}
    server = config["mcp"]["servers"]["clipstudio"]
    assert server["type"] == "local"
    assert server["codemode"] is False
    assert server["protocol"] == "legacy"
    assert server["command"][:2] == ["/usr/bin/python3", "-m"]
    assert str(tmp_path) in server["command"]
    assert Path(server["command"][-1]).is_absolute()
    assert Path(server["environment"]["PYTHONPATH"]).is_absolute()


def test_model_reference_and_version_parsing():
    assert parse_model("openai/gpt-6.1-sol") == ("openai", "gpt-6.1-sol", None)
    assert parse_model("openai/gpt-6.1-sol#high") == ("openai", "gpt-6.1-sol", "high")
    with pytest.raises(OpenCodeError):
        parse_model("not-a-provider-model")
    assert _version("2.0.28") == (2, 0, 28)
    assert _version("2.0") == (2, 0, 0)


def test_discovery_prefers_a_supported_desktop_cli(tmp_path):
    old = tmp_path / "old-opencode"
    old.write_text("#!/bin/sh\necho 'opencode v2.0.28'\n")
    old.chmod(0o755)
    desktop = tmp_path / "desktop"
    (desktop / "2.1.4-arm64").mkdir(parents=True)
    new = desktop / "2.1.4-arm64" / "opencode-cli"
    new.write_text("#!/bin/sh\necho 'opencode v2.1.4'\n")
    new.chmod(0o755)

    assert discover_binary(str(old), search_roots=[desktop]) == str(new)
    assert discover_binary(str(new), search_roots=[desktop]) == str(new)
    assert discover_binary(str(old), search_roots=[tmp_path / "empty"]) == str(old)


def test_gateway_starts_authenticates_and_stops(tmp_path):
    gateway = _gateway(tmp_path, _fake_binary(tmp_path))

    async def run():
        await gateway.start()
        client = gateway.client()
        try:
            info = await client.info()
            return info, gateway.base_url
        finally:
            await client.aclose()
            gateway.stop()

    info, base_url = asyncio.run(run())
    assert info["version"] == "2.1.4"
    assert base_url.startswith("http://127.0.0.1:")
    assert gateway.process is None


def test_gateway_refuses_an_unverified_version(tmp_path):
    gateway = _gateway(tmp_path, _fake_binary(tmp_path, "2.0.28"))
    with pytest.raises(OpenCodeError, match="outside the verified"):
        asyncio.run(gateway.start())
    assert gateway.process is None


def test_gateway_reports_a_missing_binary(tmp_path):
    gateway = _gateway(tmp_path, tmp_path / "missing")
    with pytest.raises(OpenCodeError, match="not found"):
        asyncio.run(gateway.start())
    assert gateway.process is None


class FakeClient:
    def __init__(self, events):
        self.events_in = events
        self.created = 0
        self.prompted = False
        self.prompt_text = ""
        self.interrupted = 0
        self.models = []
        self.waited = 0
        self.order = []

    async def create_session(self, *, title, agent):
        self.created += 1
        self.order.append("create")
        return "ses_test"

    async def set_model(self, session_id, model):
        self.models.append(model)

    async def delete_session(self, session_id):
        self.order.append("delete")

    async def wait_for_mcp(self):
        self.waited += 1
        self.order.append("wait")

    async def prompt(self, session_id, text, files=None):
        self.prompted = True
        self.prompt_text = text

    async def interrupt(self, session_id):
        self.interrupted += 1

    async def events(self):
        yield {"type": "server.connected"}
        while not self.prompted:
            await asyncio.sleep(0)
        for event in self.events_in:
            yield event


def _events(deltas=("Hello ", "world"), done="session.execution.succeeded"):
    return [
        *[
            {"type": "session.text.delta", "data": {"sessionID": "ses_test", "delta": delta}}
            for delta in deltas
        ],
        {
            "type": "session.tool.input.started",
            "data": {"sessionID": "ses_test", "id": "c1", "name": "clipstudio_update_brief"},
        },
        {
            "type": "session.tool.called",
            "data": {"sessionID": "ses_test", "id": "c1", "input": {"slug": "production"}},
        },
        {
            "type": "session.tool.success",
            "data": {
                "sessionID": "ses_test",
                "id": "c1",
                "content": [{"type": "text", "text": '{"ok": true}'}],
            },
        },
        {"type": done, "data": {"sessionID": "ses_test"}},
    ]


def test_gateway_turn_relays_text_tools_and_persists_history(tmp_path):
    root = make_api_project(tmp_path)
    client = FakeClient(_events())

    async def run():
        return [
            event
            async for event in run_gateway_turn(
                client,
                root,
                "production",
                "writer",
                "Revise the treatment.",
                "PROJECT CONTEXT",
                model="openai/gpt-6.1-sol",
                warmup_delay=0,
            )
        ]

    events = asyncio.run(run())
    assert [event.kind for event in events] == ["text", "text", "tool", "tool", "done"]
    assert events[0].text + events[1].text == "Hello world"
    assert events[2].tool == "clipstudio_update_brief"
    assert json.loads(events[2].arguments) == {"slug": "production"}
    assert events[3].result == '{"ok": true}'
    assert client.created == 2
    assert client.models == ["openai/gpt-6.1-sol"]
    assert client.waited == 1
    assert client.order == ["wait", "create", "create", "delete"]
    assert "PROJECT CONTEXT" in client.prompt_text
    assert "Revise the treatment." in client.prompt_text

    stored = [
        json.loads(line)
        for line in (root / "work" / "chat.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert [message["role"] for message in stored] == ["user", "tool", "assistant"]
    assert stored[-1]["content"] == "Hello world"


def test_gateway_turn_reuses_the_saved_session(tmp_path):
    root = make_api_project(tmp_path)
    first = FakeClient(_events(deltas=("one",)))
    asyncio.run(_collect(first, root))

    second = FakeClient(_events(deltas=("two",)))
    asyncio.run(_collect(second, root))
    assert first.created == 2
    assert second.created == 0
    assert second.models == []


async def _collect(client, root):
    return [
        event
        async for event in run_gateway_turn(
            client,
            root,
            "production",
            "writer",
            "Continue.",
            "CONTEXT",
            model="openai/gpt-6.1-sol",
            warmup_delay=0,
        )
    ]


def test_gateway_turn_surfaces_a_provider_error(tmp_path):
    root = make_api_project(tmp_path)
    client = FakeClient(
        [
            {
                "type": "session.execution.failed",
                "data": {
                    "sessionID": "ses_test",
                    "error": {"message": "quota", "type": "provider"},
                },
            }
        ]
    )
    events = asyncio.run(_collect(client, root))
    assert events[-1].kind == "done"
    assert events[-1].payload["error"] == "quota"


def test_closing_the_gateway_turn_interrupts_the_session(tmp_path):
    root = make_api_project(tmp_path)

    class SlowClient(FakeClient):
        async def events(self):
            yield {"type": "server.connected"}
            while not self.prompted:
                await asyncio.sleep(0)
            yield {
                "type": "session.text.delta",
                "data": {"sessionID": "ses_test", "delta": "partial"},
            }
            while True:
                await asyncio.sleep(10)

    client = SlowClient([])

    async def run():
        stream = run_gateway_turn(
            client,
            root,
            "production",
            "writer",
            "Keep going.",
            "CONTEXT",
            model="openai/gpt-6.1-sol",
            warmup_delay=0,
        )
        event = await anext(stream)
        await stream.aclose()
        return event

    event = asyncio.run(run())
    assert event.text == "partial"
    assert client.interrupted == 1
