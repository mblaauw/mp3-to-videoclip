"""The chat route can route a turn through the gateway without a real process."""

from __future__ import annotations

import asyncio
import json

from api_support import api_client, make_api_project

from mp3_to_videoclip import promptlog
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
    # The model that answered is written down with the turn, and in the current record.
    assert user_turn["prompt"]["provider"] == "openai"
    assert user_turn["prompt"]["model"] == "gpt-6.1-sol"
    assert promptlog.current(root)["model"] == "gpt-6.1-sol"


def test_the_direct_path_records_its_one_model_for_every_role(tmp_path):
    settings = Settings(gateway="direct", llm_model="flash", writer_model="openai/other")
    assert director_api._answering(settings, "writer") == {"provider": "direct", "model": "flash"}
    assert director_api._answering(settings, "critic") == {"provider": "direct", "model": "flash"}
    settings = Settings(gateway="opencode", editor_model="a/b/c")
    assert director_api._answering(settings, "editor") == {"provider": "a", "model": "b/c"}


def test_only_the_writers_storyboard_turn_is_given_the_story_timings(tmp_path, monkeypatch):
    make_api_project(tmp_path)
    monkeypatch.setattr(director_api, "effective_settings", lambda: _settings())

    async def gateway(settings, projects_dir):
        return FakeGateway(FakeClient())

    snapshots = []
    original = director_api.build_context

    def tracked(*args, **kwargs):
        snapshots.append(original(*args, **kwargs))
        return snapshots[-1]

    monkeypatch.setattr(director_api, "get_gateway", gateway)
    monkeypatch.setattr(director_api, "build_context", tracked)
    client = api_client(tmp_path)

    for payload in (
        {"stage": "storyboard"},
        {"stage": "story", "task": "storyboard"},
        {"stage": "storyboard", "role": "editor"},
        {"stage": "story"},
    ):
        response = client.post("/api/projects/production/chat", json={"message": "Go.", **payload})
        assert response.status_code == 200

    assert ["Story on the song" in text for text in snapshots] == [True, True, False, False]


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


def _model_report(tmp_path, monkeypatch, settings, can_see=None, fails=False):
    root = make_api_project(tmp_path)

    class SightClient(FakeClient):
        async def model_can_see(self, model):
            if fails:
                raise OpenCodeError("gateway down")
            return can_see

    class Gateway:
        def client(self):
            return SightClient()

    async def get_gateway(_settings, _projects):
        return Gateway()

    monkeypatch.setattr(director_api, "effective_settings", lambda: settings)
    monkeypatch.setattr(director_api, "get_gateway", get_gateway)
    with api_client(root.parent) as client:
        return client.get(f"/api/projects/{root.name}/director/model", params={"role": "editor"})


def test_direct_gateway_names_the_model_that_really_answers(tmp_path, monkeypatch):
    settings = Settings(gateway="direct", editor_model="openai/gpt-6.1-sol", llm_model="flash")
    report = _model_report(tmp_path, monkeypatch, settings).json()
    assert report == {"model": "flash", "gateway": "direct", "can_see": None}


def test_opencode_reports_whether_the_editor_can_see(tmp_path, monkeypatch):
    settings = Settings(gateway="opencode", editor_model="openai/gpt-6.1-sol")
    report = _model_report(tmp_path, monkeypatch, settings, can_see=True).json()
    assert report == {"model": "openai/gpt-6.1-sol", "gateway": "opencode", "can_see": True}


def test_a_gateway_failure_never_claims_sight(tmp_path, monkeypatch):
    settings = Settings(gateway="opencode", editor_model="openai/gpt-6.1-sol")
    report = _model_report(tmp_path, monkeypatch, settings, fails=True)
    assert report.status_code == 200 and report.json()["can_see"] is None


def test_model_can_see_reads_the_gateways_capabilities():
    from mp3_to_videoclip.director.opencode import OpenCodeClient

    async def run():
        client = OpenCodeClient.__new__(OpenCodeClient)

        async def models():
            return [
                {"providerID": "a", "id": "sees", "capabilities": {"input": ["text", "image"]}},
                {"providerID": "a", "id": "blind", "capabilities": {"input": ["text"]}},
                {"providerID": "a", "id": "quiet"},
            ]

        client.models = models
        return [
            await client.model_can_see(f"a/{name}") for name in ("sees", "blind", "quiet", "no")
        ]

    assert asyncio.run(run()) == [True, False, None, None]
