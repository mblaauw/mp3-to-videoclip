"""Images routes: listing, file serving, selection, estimate and queueing.

The generation service is faked; this module owns the HTTP contract and the
authorize-before-queue ordering, never a provider call.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from api_support import add_assets, api_client, make_api_project

from mp3_to_videoclip import services


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return make_api_project(tmp_path)


@pytest.fixture
def client(tmp_path: Path, project: Path):
    with api_client(tmp_path) as value:
        yield value


def _cap(client, amount="5.00"):
    response = client.post(
        "/api/projects/production/budget", json={"amount": amount, "reason": "test"}
    )
    assert response.status_code == 200, response.text


def test_images_list_file_and_select(client, project):
    add_assets(project)
    data = client.get("/api/projects/production/images").json()
    assert len(data["shots"]) == 4
    first = data["shots"][0]
    assert first["selected"] == 1
    assert len(first["versions"]) == 2

    image = client.get(f"/api/projects/production/images/{first['owner']}/1")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"
    assert image.content[:2] == b"\xff\xd8"
    assert client.get(f"/api/projects/production/images/{first['owner']}/9").status_code == 404
    assert client.get("/api/projects/production/images/missing/1").status_code == 404

    selected = client.post(
        "/api/projects/production/images/select",
        json={"shot_id": first["id"], "version": 2},
    )
    assert selected.status_code == 200
    assert client.get("/api/projects/production/images").json()["shots"][0]["selected"] == 2
    unknown = client.post(
        "/api/projects/production/images/select",
        json={"shot_id": first["id"], "version": 9},
    )
    assert unknown.status_code == 400


def test_estimate_returns_the_quote_and_the_budget_decision(client, monkeypatch):
    _cap(client)
    fake = {
        "quote_id": "quote-1",
        "scope": "stills",
        "tasks": 2,
        "reserve_usd": "0.10",
        "cap_usd": "5.00",
        "uploads_required": False,
        "shot_ids": ["s001", "s002"],
    }
    monkeypatch.setattr(services.generation, "estimate", lambda *a, **k: fake)
    response = client.post(
        "/api/projects/production/images/estimate",
        json={"shot_ids": ["s001", "s002"], "reserve_usd": "0.05", "scope": "stills"},
    )
    body = response.json()
    assert body["estimate"]["quote_id"] == "quote-1"
    assert body["decision"]["ok"] is True
    assert body["budget"]["cap_usd"] == "5.00"

    assert client.post(
        "/api/projects/production/images/estimate", json={"shot_ids": []}
    ).json() == {"error": "select at least one shot"}

    def fail(*args, **kwargs):
        raise ValueError("brief needs current user approval")

    monkeypatch.setattr(services.generation, "estimate", fail)
    assert client.post(
        "/api/projects/production/images/estimate", json={"shot_ids": ["s001"]}
    ).json() == {"error": "brief needs current user approval"}


def test_generate_authorizes_the_exact_quote_before_queueing(client, monkeypatch):
    _cap(client)
    quote = {
        "id": "quote-1",
        "reserve_total_usd": "0.10",
        "tasks": [{"shot_id": "s001"}, {"shot_id": "s002"}],
    }
    monkeypatch.setattr(services.generation, "quote", lambda root, quote_id: quote)
    monkeypatch.setattr(services.generation, "uploads_required", lambda value: False)
    calls = {}
    monkeypatch.setattr(
        services.generation,
        "authorize",
        lambda root, quote_id, **kwargs: calls.update(quote_id=quote_id, **kwargs) or {},
    )
    submitted = []
    monkeypatch.setattr(
        client.app.state.runner,
        "submit",
        lambda kind, slug, factory: submitted.append((kind, slug)) or "job-1",
    )

    response = client.post(
        "/api/projects/production/images/generate",
        json={"quote_id": "quote-1", "note": "test batch"},
    )
    body = response.json()
    assert body["job_id"] == "job-1"
    assert body["tasks"] == 2
    assert body["reserve_usd"] == "0.10"
    assert calls["quote_id"] == "quote-1"
    assert calls["note"] == "test batch"
    assert submitted == [("images", "production")]
    assert client.post("/api/projects/production/images/generate", json={}).json() == {
        "error": "estimate the selection first"
    }


def test_generate_pauses_at_the_cap_and_never_authorizes(client, monkeypatch):
    _cap(client, "1.00")
    monkeypatch.setattr(
        services.generation,
        "quote",
        lambda root, quote_id: {"id": quote_id, "reserve_total_usd": "2.00", "tasks": []},
    )
    monkeypatch.setattr(
        services.generation,
        "authorize",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not authorize")),
    )
    body = client.post(
        "/api/projects/production/images/generate", json={"quote_id": "quote-1"}
    ).json()
    assert body["needs_budget"] is True
    assert body["decision"]["suggested_usd"]


def test_generate_needs_explicit_reference_upload_consent(client, monkeypatch):
    _cap(client)
    monkeypatch.setattr(
        services.generation,
        "quote",
        lambda root, quote_id: {
            "id": quote_id,
            "reserve_total_usd": "0.10",
            "tasks": [{"shot_id": "s001"}],
        },
    )
    monkeypatch.setattr(services.generation, "uploads_required", lambda value: True)
    monkeypatch.setattr(
        services.generation,
        "authorize",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not authorize")),
    )
    body = client.post(
        "/api/projects/production/images/generate", json={"quote_id": "quote-1"}
    ).json()
    assert "confirm" in body["error"]


def test_generate_reports_a_stale_or_unknown_quote(client, monkeypatch):
    def fail(root, quote_id):
        raise ValueError("quote needs explicit spending authorization")

    monkeypatch.setattr(services.generation, "quote", fail)
    body = client.post(
        "/api/projects/production/images/generate", json={"quote_id": "quote-x"}
    ).json()
    assert body["error"] == "quote needs explicit spending authorization"


def test_review_records_a_verdict_on_the_exact_version(client, project):
    add_assets(project)
    first = client.get("/api/projects/production/images").json()["shots"][0]
    assert first["review"] is None

    rejected = client.post(
        "/api/projects/production/images/review",
        json={
            "shot_id": first["id"],
            "version": 1,
            "verdict": "reject",
            "note": "The face is wrong",
            "inspected": True,
        },
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["review"]["verdict"] == "reject"
    assert rejected.json()["review"]["shot_id"] == first["id"]

    accepted = client.post(
        "/api/projects/production/images/review",
        json={
            "shot_id": first["id"],
            "version": 1,
            "verdict": "accept",
            "note": "Inspected the current bytes; this one is right",
            "inspected": True,
        },
    )
    assert accepted.status_code == 200
    listed = client.get("/api/projects/production/images").json()["shots"][0]
    assert listed["review"]["verdict"] == "accept"
    assert listed["review"]["version"] == 1

    assert (
        client.post(
            "/api/projects/production/images/review",
            json={
                "shot_id": first["id"],
                "version": 1,
                "verdict": "accept",
                "note": "no inspection",
                "inspected": False,
            },
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/projects/production/images/review",
            json={
                "shot_id": first["id"],
                "version": 9,
                "verdict": "accept",
                "note": "missing version",
                "inspected": True,
            },
        ).status_code
        == 400
    )


def test_review_refuses_stale_inputs_and_accepts_the_proof_set(client, project):
    from mp3_to_videoclip import production as P
    from mp3_to_videoclip import reviews

    add_assets(project)
    board = P.load_board(project)
    proof = P.proof_ids(board, P.load_brief(project))
    for shot_id in proof:
        response = client.post(
            "/api/projects/production/images/review",
            json={
                "shot_id": shot_id,
                "version": 1,
                "verdict": "accept",
                "note": "Inspected this exact proof image",
                "inspected": True,
            },
        )
        assert response.status_code == 200, response.text
    reviews.require_accepted(project, proof)

    brief = client.get("/api/projects/production/brief").json()
    brief["creative"]["look"] = brief["creative"]["look"] + " with more grain"
    from mp3_to_videoclip.storage import write_json

    write_json(project / "brief.json", brief)
    assert (
        client.post(
            "/api/projects/production/images/review",
            json={
                "shot_id": proof[0],
                "version": 1,
                "verdict": "accept",
                "note": "stale prompt",
                "inspected": True,
            },
        ).status_code
        == 400
    )


def test_reviews_unlock_the_proof_approval(client, project):
    from mp3_to_videoclip import production as P

    add_assets(project)

    def approve(stage: str):
        states = client.get("/api/projects/production/approvals").json()["stages"]
        item = next(state for state in states if state["stage"] == stage)
        return client.post(
            f"/api/projects/production/approvals/{stage}",
            json={
                "expected_hash": item["expected_hash"],
                "note": f"Reviewed {stage}",
                "confirmed": True,
            },
        )

    assert approve("brief").status_code == 200
    assert approve("storyboard").status_code == 200
    blocked = approve("proof")
    assert blocked.status_code == 400
    assert "accepted review" in blocked.text

    proof = P.proof_ids(P.load_board(project), P.load_brief(project))
    for shot_id in proof:
        assert (
            client.post(
                "/api/projects/production/images/review",
                json={
                    "shot_id": shot_id,
                    "version": 1,
                    "verdict": "accept",
                    "note": "Inspected the exact proof image",
                    "inspected": True,
                },
            ).status_code
            == 200
        )
    assert approve("proof").status_code == 200

    for shot in P.load_board(project).shots:
        if shot.id in proof:
            continue
        assert (
            client.post(
                "/api/projects/production/images/review",
                json={
                    "shot_id": shot.id,
                    "version": 1,
                    "verdict": "accept",
                    "note": "Inspected this exact still",
                    "inspected": True,
                },
            ).status_code
            == 200
        )
    assert approve("stills").status_code == 200


def test_alias_review_records_the_shared_asset_owner(client, project):
    from mp3_to_videoclip import production as P
    from mp3_to_videoclip.storage import read_json, write_json

    add_assets(project)
    board = read_json(project / P.STAGE_FILES["storyboard"])
    board["shots"][1]["asset_shot_id"] = "s001"
    write_json(project / P.STAGE_FILES["storyboard"], board)
    response = client.post(
        "/api/projects/production/images/review",
        json={
            "shot_id": "s002",
            "version": 1,
            "verdict": "accept",
            "note": "The alias points at the inspected shared asset",
            "inspected": True,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["review"]["shot_id"] == "s001"
    assert response.json()["review"]["verdict"] == "accept"
