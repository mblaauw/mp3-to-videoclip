"""Every API failure carries the stable `{detail, code}` envelope (K11)."""

from __future__ import annotations

import pytest
from api_support import api_client, make_api_project
from fastapi.testclient import TestClient

from mp3_to_videoclip.api.errors import engine_error
from mp3_to_videoclip.app import create_app
from mp3_to_videoclip.config import Settings
from mp3_to_videoclip.providers import MissingProviderKey, ProviderError
from mp3_to_videoclip.storage import ProjectBusy, RevisionConflict


def test_unknown_project_is_enveloped(tmp_path):
    with api_client(tmp_path) as client:
        response = client.get("/api/projects/missing")
    assert response.status_code == 404
    body = response.json()
    assert body == {"detail": "project not found", "code": "not_found"}


def test_missing_job_has_a_specific_code(tmp_path):
    with api_client(tmp_path) as client:
        response = client.get("/api/jobs/missing")
    assert response.status_code == 404
    assert response.json() == {"detail": "job not found", "code": "job_not_found"}


def test_validation_errors_are_enveloped(tmp_path):
    with api_client(tmp_path) as client:
        response = client.post("/api/projects", json={})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert isinstance(body["detail"], list)


def test_json_content_type_is_enveloped(tmp_path):
    with api_client(tmp_path) as client:
        response = client.post("/api/projects/production/chat", content=b"hi")
    assert response.status_code == 415
    assert response.json() == {"detail": "JSON required", "code": "json_required"}


def test_stale_approval_has_a_specific_code(tmp_path):
    make_api_project(tmp_path)
    with api_client(tmp_path) as client:
        response = client.post(
            "/api/projects/production/approvals/brief",
            json={"expected_hash": "0" * 64, "note": "stale decision", "confirmed": True},
        )
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "approval_stale"
    assert "changed" in body["detail"].lower()


def test_invalid_approval_has_a_specific_code(tmp_path):
    make_api_project(tmp_path)
    with api_client(tmp_path) as client:
        response = client.post("/api/projects/production/approvals/brief", json={})
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "approval_invalid"
    assert body["detail"]


def test_unexpected_errors_hide_exception_text(tmp_path, monkeypatch):
    def explode(_request):
        raise RuntimeError("secret path /Users/owner/private")

    monkeypatch.setattr("mp3_to_videoclip.api.projects._projects_dir", explode)
    with TestClient(
        create_app(projects_dir=tmp_path),
        base_url="http://127.0.0.1",
        raise_server_exceptions=False,
    ) as client:
        response = client.get("/api/projects")
    assert response.status_code == 500
    assert response.json() == {"detail": "internal error", "code": "internal_error"}
    assert "secret" not in response.text


def test_missing_director_key_has_a_settings_code(tmp_path, monkeypatch):
    make_api_project(tmp_path)
    with api_client(tmp_path) as client:
        monkeypatch.setattr(
            "mp3_to_videoclip.api.director.effective_settings",
            lambda: Settings(llm_api_key=""),
        )
        response = client.post("/api/projects/production/chat", json={"message": "hello"})
    assert response.status_code == 503
    assert response.json()["code"] == "no_llm_key"


def _no_path(body: dict) -> None:
    assert "/" not in str(body["detail"]) and ".json" not in str(body["detail"])


def test_missing_artifacts_name_the_artifact_and_never_the_path(tmp_path):
    root = make_api_project(tmp_path)
    (root / "work" / "storyboard.json").unlink(missing_ok=True)
    with api_client(tmp_path) as client:
        response = client.get("/api/projects/production/edit")
    assert response.status_code == 404
    assert response.json()["code"] == "storyboard_missing"
    _no_path(response.json())


def test_a_film_with_no_brief_says_so(tmp_path):
    root = make_api_project(tmp_path)
    (root / "brief.json").unlink()
    with api_client(tmp_path) as client:
        response = client.get("/api/projects/production/brief")
    assert response.status_code == 404
    assert response.json() == {
        "detail": "The story has not been written yet.",
        "code": "brief_missing",
    }


@pytest.mark.parametrize(
    ("raised", "status", "code"),
    [
        (ValueError("no such shot"), 400, "bad_request"),
        (ProjectBusy("another job is running"), 409, "project_busy"),
        (RevisionConflict("changed under you"), 409, "conflict"),
        (ProviderError("network_error"), 502, "network_error"),
        (ProviderError("invalidApiKey", status=401), 502, "invalidApiKey"),
        (MissingProviderKey("no key"), 409, "no_runware_key"),
        (FileNotFoundError(2, "gone", "/secret/place/music.json"), 404, "analysis_missing"),
        (FileNotFoundError(2, "gone", "/secret/place/other.bin"), 404, "artifact_missing"),
        (FileNotFoundError("source audio not found: /secret/song.mp3"), 404, "artifact_missing"),
    ],
)
def test_engine_error_mapping(raised, status, code):
    error = engine_error(raised)
    assert (error.status_code, error.code) == (status, code)
    assert "secret" not in error.detail


@pytest.mark.parametrize(
    ("route", "payload"),
    [
        ("images/estimate", {"shot_ids": []}),
        ("images/generate", {}),
        ("images/select", {}),
        ("voice/generate", {}),
    ],
)
def test_refusals_are_not_http_200(tmp_path, route, payload):
    make_api_project(tmp_path)
    with api_client(tmp_path) as client:
        response = client.post(f"/api/projects/production/{route}", json=payload)
    assert response.status_code == 400, route
    assert response.json()["code"] == "bad_request"


def test_a_lost_quote_is_a_404_with_a_way_forward(tmp_path):
    make_api_project(tmp_path)
    with api_client(tmp_path) as client:
        response = client.post(
            "/api/projects/production/images/generate", json={"quote_id": "gone"}
        )
    assert response.status_code in (400, 404)
    _no_path(response.json())
