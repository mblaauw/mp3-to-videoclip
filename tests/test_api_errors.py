"""Every API failure carries the stable `{detail, code}` envelope (K11)."""

from __future__ import annotations

from api_support import api_client, make_api_project
from fastapi.testclient import TestClient

from mp3_to_videoclip.app import create_app
from mp3_to_videoclip.config import Settings


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
