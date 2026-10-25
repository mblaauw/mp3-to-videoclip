"""Uploading an MP3 creates a project, queues analysis and respects the guards."""

from __future__ import annotations

import json

import pytest
from api_support import api_client

from mp3_to_videoclip.app import create_app
from mp3_to_videoclip.domain.models import Project

pytestmark = pytest.mark.usefixtures("fake_probe")


@pytest.fixture
def fake_probe(monkeypatch):
    monkeypatch.setattr(
        "mp3_to_videoclip.production.probe",
        lambda path: {"streams": [{"codec_type": "audio"}]},
    )
    monkeypatch.setattr("mp3_to_videoclip.production.audio_seconds", lambda path: 12.0)


def _upload(client, **overrides):
    params = {
        "title": "New Film",
        "filename": "song.mp3",
        "aspect": "16:9",
        "music_mode": "vocal",
        "budget": "3.50",
    }
    params.update(overrides)
    return client.post(
        "/api/projects",
        params=params,
        content=b"ID3fake",
        headers={"Content-Type": "audio/mpeg"},
    )


def test_upload_creates_the_project_and_queues_analysis(tmp_path, monkeypatch):
    with api_client(tmp_path) as client:
        submitted = []
        monkeypatch.setattr(
            client.app.state.runner,
            "submit",
            lambda kind, slug, factory: submitted.append((kind, slug)) or "job-1",
        )
        response = _upload(client)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["slug"] == "new-film"
        assert body["analysis_job"] == "job-1"
        assert body["duration"] == 12.0
        assert submitted == [("analysis", "new-film")]

        root = tmp_path / "new-film"
        stored = json.loads((root / "project.json").read_text())
        project = Project.model_validate(stored)
        assert project.schema_version == 3
        # The app creates schema-3 projects natively; rewriting the budget must
        # not erase the backend or signature choice it was created with.
        assert stored["renderer_backend"] == "remotion"
        assert stored["signature_required"] is True
        assert project.cap_usd == "3.50"
        assert (root / "media/song.mp3").read_bytes() == b"ID3fake"

        listed = client.get("/api/projects").json()
        assert [row["slug"] for row in listed] == ["new-film"]
        detail = client.get("/api/projects/new-film").json()
        assert detail["shots"] == 0
        assert detail["approvals"] == []


def test_upload_guards(tmp_path):
    with api_client(tmp_path) as client:
        assert _upload(client, filename="song.wav").status_code == 400
        assert _upload(client, budget="0").status_code == 400
        missing = client.post(
            "/api/projects",
            params={"filename": "song.mp3"},
            content=b"x",
            headers={"Content-Type": "audio/mpeg"},
        )
        assert missing.status_code == 422
        json_body = client.post(
            "/api/projects",
            params={"title": "Json", "filename": "song.mp3"},
            json={},
        )
        assert json_body.status_code == 415
        assert not (tmp_path / "new-film").exists()


def test_oversize_upload_is_refused(tmp_path, monkeypatch):
    from mp3_to_videoclip.domain import intake

    monkeypatch.setattr(intake, "MAX_SOURCE_BYTES", 4)
    with api_client(tmp_path) as client:
        response = _upload(client, title="Big")
        assert response.status_code == 413
        assert not (tmp_path / "big").exists()


def test_same_origin_and_vite_dev_origin_are_allowed(tmp_path):
    from fastapi.testclient import TestClient

    with TestClient(create_app(projects_dir=tmp_path), base_url="http://127.0.0.1:8799") as client:
        created = client.post(
            "/api/projects",
            params={"title": "Origin Film", "filename": "song.mp3"},
            content=b"ID3fake",
            headers={"Content-Type": "audio/mpeg", "Origin": "http://127.0.0.1:8799"},
        )
        assert created.status_code == 201, created.text

        same = client.post(
            "/api/projects/origin-film/budget",
            json={"amount": "6.00", "reason": "same origin"},
            headers={"Origin": "http://127.0.0.1:8799"},
        )
        assert same.status_code == 200
        dev = client.post(
            "/api/projects/origin-film/budget",
            json={"amount": "7.00", "reason": "vite dev"},
            headers={"Origin": "http://localhost:5173"},
        )
        assert dev.status_code == 200
        evil = client.post(
            "/api/projects/origin-film/budget",
            json={"amount": "8.00", "reason": "evil"},
            headers={"Origin": "http://evil.example:8799"},
        )
        assert evil.status_code == 403
        wrong_port = client.post(
            "/api/projects/origin-film/budget",
            json={"amount": "8.00", "reason": "wrong port"},
            headers={"Origin": "http://127.0.0.1:9999"},
        )
        assert wrong_port.status_code == 403


def test_unreadable_upload_is_a_400(tmp_path, monkeypatch):
    def broken(path):
        raise RuntimeError("ffprobe failed")

    monkeypatch.setattr("mp3_to_videoclip.production.probe", broken)
    with api_client(tmp_path) as client:
        response = _upload(client, title="Broken")
        assert response.status_code == 400
        assert "readable MP3" in response.json()["detail"]
        assert not (tmp_path / "broken").exists()
