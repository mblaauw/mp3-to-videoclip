"""The chat route can route a turn through the gateway without a real process."""

from __future__ import annotations

import asyncio
import json

from api_support import api_client, make_api_project

from mp3_to_videoclip.api import director as director_api
from mp3_to_videoclip.config import Settings
from mp3_to_videoclip.director.opencode import OpenCodeError


class FakeClient:
    def __init__(self):
        self.created = 0
        self.models = []
        self.prompted = False
        self.closed = False
        self.interrupted = 0

    async def create_session(self, *, title, agent):
        self.created += 1
        return f"ses_{agent}"

    async def set_model(self, session_id, model):
        self.models.append(model)

    async def prompt(self, session_id, text, files=None):
        self.prompted = True

    async def model_available(self, model):
        return True

    async def interrupt(self, session_id):
        self.interrupted += 1

    async def aclose(self):
        self.closed = True

    async def events(self):
        yield {"type": "server.connected"}
        while not self.prompted:
            await asyncio.sleep(0)
        yield {
            "type": "session.text.delta",
            "data": {"delta": "Hello from the gateway."},
        }
        yield {"type": "session.execution.succeeded", "data": {}}


class FakeGateway:
    def __init__(self, client):
        self._client = client

    def client(self):
        return self._client


def _settings(gateway="opencode", key=""):
    return Settings(
        gateway=gateway,
        llm_api_key=key,
        writer_model="openai/gpt-6.1-sol",
        editor_model="opencode-go/deepseek-v4.1-flash",
    )


def test_chat_routes_a_writer_turn_through_the_gateway(tmp_path, monkeypatch):
    root = make_api_project(tmp_path)
    fake = FakeClient()
    monkeypatch.setattr(director_api, "effective_settings", lambda: _settings())

    async def gateway(settings, projects_dir):
        return FakeGateway(fake)

    monkeypatch.setattr(director_api, "get_gateway", gateway)
    client = api_client(tmp_path)

    response = client.post(
        "/api/projects/production/chat",
        json={"message": "Write a treatment.", "stage": "story"},
    )
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert events[0]["kind"] == "text"
    assert events[-1]["kind"] == "done"
    assert fake.created == 2
    assert fake.models == ["openai/gpt-6.1-sol"]
    assert fake.closed is True

    from mp3_to_videoclip.director.conversation import load_messages

    user_turn = load_messages(root)[0]
    assert user_turn["role"] == "user"
    assert user_turn["prompt"]["task"] == "brief"
    assert user_turn["prompt"]["hash"]
    assert user_turn["prompt"]["files"]


def test_chat_uses_the_editor_role_for_the_film_stage(tmp_path, monkeypatch):
    make_api_project(tmp_path)
    fake = FakeClient()
    monkeypatch.setattr(director_api, "effective_settings", lambda: _settings())

    async def gateway(settings, projects_dir):
        return FakeGateway(fake)

    monkeypatch.setattr(director_api, "get_gateway", gateway)
    client = api_client(tmp_path)

    response = client.post(
        "/api/projects/production/chat",
        json={"message": "Plan the cut.", "stage": "film"},
    )
    assert response.status_code == 200
    assert fake.models == ["opencode-go/deepseek-v4.1-flash"]


def test_chat_reports_an_unavailable_model(tmp_path, monkeypatch):
    make_api_project(tmp_path)
    fake = FakeClient()
    monkeypatch.setattr(director_api, "effective_settings", lambda: _settings())

    async def gateway(settings, projects_dir):
        return FakeGateway(fake)

    async def unavailable(self, model):
        return False

    monkeypatch.setattr(director_api, "get_gateway", gateway)
    monkeypatch.setattr(FakeClient, "model_available", unavailable)
    client = api_client(tmp_path)

    response = client.post(
        "/api/projects/production/chat",
        json={"message": "Write a treatment.", "stage": "story"},
    )
    assert response.status_code == 503
    assert "not available in OpenCode" in response.json()["detail"]
    assert fake.closed is True


def test_chat_reports_a_gateway_failure_without_direct_credentials(tmp_path, monkeypatch):
    make_api_project(tmp_path)
    monkeypatch.setattr(director_api, "effective_settings", lambda: _settings())

    async def gateway(settings, projects_dir):
        raise OpenCodeError("OpenCode binary not found: opencode")

    monkeypatch.setattr(director_api, "get_gateway", gateway)
    client = api_client(tmp_path)

    response = client.post(
        "/api/projects/production/chat",
        json={"message": "Write a treatment.", "stage": "story"},
    )
    assert response.status_code == 503
    assert "OpenCode gateway unavailable" in response.json()["detail"]
