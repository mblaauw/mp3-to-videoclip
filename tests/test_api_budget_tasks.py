"""A paid task that never came back: the owner can see it and free the film from the Studio."""

from __future__ import annotations

from api_support import api_client, make_api_project

from mp3_to_videoclip import budget, generation
from mp3_to_videoclip.providers import ProviderError
from mp3_to_videoclip.storage import read_json, write_json

TASK = "220e9503-5a86-4c8f-9cc3-7b4a96e2a503"


def _stuck(tmp_path):
    root = make_api_project(tmp_path)
    budget.set_budget(root, "5.00", "test")
    write_json(
        root / "work/tasks.json",
        {
            TASK: {
                "uuid": TASK,
                "kind": "clip",
                "shot_id": "s018",
                "status": "submitted",
                "reserve_usd": "0.29",
                "submitted_at": "now",
            }
        },  # fmt: skip
    )
    return root


def test_the_budget_names_what_holds_the_film(tmp_path):
    _stuck(tmp_path)
    with api_client(tmp_path) as client:
        body = client.get("/api/projects/production/budget").json()
    assert body["unresolved"] == [
        {"id": TASK, "kind": "clip", "shot_id": "s018", "reserve_usd": "0.29", "at": "now"}
    ]


def test_a_provider_outage_is_an_answer_and_buys_nothing(tmp_path, monkeypatch):
    root = _stuck(tmp_path)

    def down(*_):
        raise ProviderError("http_error", status=504)

    monkeypatch.setattr(generation, "recover", down)
    with api_client(tmp_path) as client:
        said = client.post(f"/api/projects/production/tasks/{TASK}/recover", json={})
    assert said.status_code == 200 and said.json() == {"recovered": False, "answered": False}
    assert read_json(root / "work/tasks.json")[TASK]["status"] == "submitted"


def test_a_task_the_provider_ended_is_failed_and_still_the_owners_to_settle(tmp_path, monkeypatch):
    root = _stuck(tmp_path)

    def ended(*_):
        raise ProviderError("task_failed", status=504)

    monkeypatch.setattr(generation, "recover", ended)
    with api_client(tmp_path) as client:
        said = client.post(f"/api/projects/production/tasks/{TASK}/recover", json={})
    assert said.json() == {"recovered": False, "answered": True, "failed": True}
    assert read_json(root / "work/tasks.json")[TASK]["status"] == "submitted"


def test_settling_needs_evidence_and_frees_the_film(tmp_path):
    root = _stuck(tmp_path)
    url = f"/api/projects/production/tasks/{TASK}/resolve"
    with api_client(tmp_path) as client:
        assert client.post(url, json={"cost": "0.21", "note": " "}).status_code == 400
        assert client.post(url, json={"cost": "soon", "note": "bill"}).status_code == 400
        assert client.post(url, json={"cost": "0.21", "note": "billing page"}).status_code == 200
        assert client.post(url, json={"cost": "0.21", "note": "again"}).status_code == 404
    task = read_json(root / "work/tasks.json")[TASK]
    assert task["status"] == "resolved" and task["cost_usd"] == "0.21"
    budget.require_reconciled(root)
