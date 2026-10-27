"""Uploading an MP3 creates a project, queues analysis and respects the guards."""

from __future__ import annotations

import json

import pytest
from api_support import api_client

from mp3_to_videoclip import styles
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


def _upload(client, overrides=None, **extra):
    params = {
        "title": "New Film",
        "filename": "song.mp3",
        "aspect": "16:9",
        "music_mode": "vocal",
        "budget": "3.50",
    }
    params.update(overrides or {})
    params.update(extra)
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


def test_upload_an_advert_keeps_intent_and_skips_signature(tmp_path, monkeypatch):
    monkeypatch.setattr("mp3_to_videoclip.production.audio_seconds", lambda path: 120.0)
    intent = {
        "kind": "advert",
        "objective": "pre-save the single before 14 Nov",
        "audience": "existing listeners",
        "message": "Out 14 Nov - pre-save now",
        "reasons": ["first release in two years"],
        "tone": ["urgent", "warm", "nocturnal"],
        "mandatories": ["release date"],
        "avoid": ["stock-photo smiles"],
        "cta": {"text": "Pre-save now", "url": "https://example.com"},
        "length_seconds": 30,
        "audio_window": {"start": 62.0, "end": 92.0, "fade_in": 0.0, "fade_out": 1.5},
    }
    with api_client(tmp_path) as client:
        submitted = []
        monkeypatch.setattr(
            client.app.state.runner,
            "submit",
            lambda kind, slug, factory: submitted.append((kind, slug)) or "job-ad",
        )
        response = _upload(
            client,
            title="Forward Ever",
            overrides={
                "kind": "advert",
                "objective": intent["objective"],
                "message": intent["message"],
                "cta_text": "Pre-save now",
                "cta_url": "https://example.com",
                "length_seconds": 30,
                "window_start": 62,
                "fade_out": 1.5,
            },
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["kind"] == "advert"
        assert body["duration"] == 30.0
        assert body["source_duration"] == 120.0
        assert body["signature_required"] is False
        assert submitted == [("analysis", "forward-ever")]

        root = tmp_path / "forward-ever"
        project = Project.model_validate(json.loads((root / "project.json").read_text()))
        assert project.kind == "advert"
        assert project.audio_window.model_dump() == intent["audio_window"]
        assert not (root / "brand.json").exists()
        assert not (root / "work" / "graphics-spec.json").exists()

        brief = json.loads((root / "brief.json").read_text())
        assert brief["intent"]["objective"] == intent["objective"]
        assert brief["intent"]["message"] == intent["message"]
        assert brief["intent"]["cta"] == intent["cta"]
        assert brief["intent"]["length_seconds"] == 30

        saved = client.put(
            "/api/projects/forward-ever/intake",
            json={
                "intent": intent,
                "style_preset": "clean-photographic-v1",
                "audio_window": intent["audio_window"],
            },
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["brief"]["intent"] == intent

        intake = client.get("/api/projects/forward-ever/intake").json()
        assert intake["kind"] == "advert"
        assert intake["audio_window"] == intent["audio_window"]
        assert intake["style_preset"] == "clean-photographic-v1"
        assert intake["intent"] == intent
        assert intake["peaks"] == []

        custom = client.put(
            "/api/projects/forward-ever/intake",
            json={"style_preset": ""},
        )
        assert custom.status_code == 200, custom.text
        assert custom.json()["style_preset"] is None
        assert (
            custom.json()["brief"]["creative"]["look"]
            == styles.preset("clean-photographic-v1").look
        )


def test_advert_upload_refuses_missing_creative_intent(tmp_path):
    with api_client(tmp_path) as client:
        response = _upload(
            client,
            title="Incomplete",
            overrides={
                "kind": "advert",
                "objective": "launch",
                "message": "out now",
                "length_seconds": 30,
            },
        )
        assert response.status_code == 400
        assert "call to action" in response.json()["detail"]
        assert not (tmp_path / "incomplete").exists()


def test_intake_update_applies_style_and_window(tmp_path, monkeypatch):
    monkeypatch.setattr("mp3_to_videoclip.production.audio_seconds", lambda path: 120.0)
    with api_client(tmp_path) as client:
        created = _upload(
            client,
            title="Window Change",
            overrides={
                "kind": "promo",
                "objective": "release",
                "message": "out now",
                "length_seconds": 60,
            },
        )
        assert created.status_code == 201, created.text
        response = client.put(
            "/api/projects/window-change/intake",
            json={
                "intent": {
                    "kind": "promo",
                    "objective": "release the record",
                    "message": "out now",
                    "tone": ["warm"],
                },
                "style_preset": "brand-graphic-v1",
                "audio_window": {
                    "start": 10,
                    "end": 40,
                    "fade_in": 0.5,
                    "fade_out": 1.5,
                },
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["analysis_needed"] is True
        assert body["duration"] == 30.0
        assert body["audio_window"]["start"] == 10.0
        assert body["intent"]["length_seconds"] == 30
        assert body["style_preset"] == "brand-graphic-v1"
        assert body["brief"]["creative"]["look"].startswith("A designed brand-graphic frame")
