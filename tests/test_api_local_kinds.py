"""Local kinds are visible in Images/Player but never enter a paid batch."""

from __future__ import annotations

from pathlib import Path

import pytest
from api_support import add_assets, api_client, make_api_project

from mp3_to_videoclip.storage import read_json, write_json


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = make_api_project(tmp_path)
    add_assets(root)
    return root


@pytest.fixture
def client(tmp_path: Path, project: Path):
    with api_client(tmp_path) as value:
        yield value


def _make_local(client, project: Path):
    changes = [
        {"id": "s002", "kind": "card", "message": "silence", "text": ["Two years of silence."]},
        {
            "id": "s003",
            "kind": "end_card",
            "message": "out",
            "text": ["Out 14 Nov", "Pre-save now"],
        },
    ]
    response = client.patch("/api/projects/production/storyboard/shots", json={"changes": changes})
    assert response.status_code == 200, response.text
    brief = read_json(project / "brief.json")
    brief["creative"]["proof_shot_ids"] = ["s001"]
    write_json(project / "brief.json", brief)


def test_images_lists_local_kinds_with_a_plate_and_no_versions(client, project):
    _make_local(client, project)
    shots = {
        shot["id"]: shot for shot in client.get("/api/projects/production/images").json()["shots"]
    }
    card = shots["s002"]
    assert card["kind"] == "card"
    assert card["local"] is True
    assert card["paid"] is False
    assert card["plate"] == "/api/projects/production/plates/s002"
    assert card["versions"] == []
    assert card["review"] is None
    assert shots["s001"]["paid"] is True
    assert shots["s001"]["plate"] is None

    plate = client.get(card["plate"])
    assert plate.status_code == 200
    assert plate.headers["content-type"] == "image/png"
    assert plate.content.startswith(b"\x89PNG")
    assert client.get("/api/projects/production/plates/s001").status_code == 404


def test_player_uses_the_plate_url_and_keeps_paid_stills(client, project):
    _make_local(client, project)
    data = client.get("/api/projects/production/preview").json()
    by_id = {shot["id"]: shot for shot in data["shots"]}
    assert by_id["s002"]["src"] == "/api/projects/production/plates/s002"
    assert by_id["s002"]["still_current"] is True
    assert by_id["s002"]["kind"] == "card"
    assert by_id["s001"]["src"] == "/api/projects/production/images/s001/1"
    assert data["preview_placeholders"] == []


def test_local_shot_estimate_and_review_are_refused(client, project):
    _make_local(client, project)
    estimate = client.post(
        "/api/projects/production/images/estimate",
        json={"shot_ids": ["s002"], "scope": "stills", "reserve_usd": "0.05"},
    ).json()
    assert "local shot" in estimate["error"]

    review = client.post(
        "/api/projects/production/images/review",
        json={
            "shot_id": "s002",
            "version": 1,
            "verdict": "accept",
            "note": "the card is right",
            "inspected": True,
        },
    )
    assert review.status_code == 400
    assert "local" in review.text


def test_storyboard_can_change_a_shot_to_a_designed_bridge(client, project):
    response = client.patch(
        "/api/projects/production/storyboard/shots",
        json={
            "changes": [
                {
                    "id": "s004",
                    "kind": "bridge",
                    "message": "then everything changed",
                    "bridge": {
                        "mode": "designed",
                        "match": {"type": "shape", "anchor": [0.5, 0.45]},
                    },
                }
            ]
        },
    )
    assert response.status_code == 200, response.text
    shot = next(s for s in response.json()["shots"] if s["id"] == "s004")
    assert shot["kind"] == "bridge"
    assert shot["bridge"]["mode"] == "designed"
    assert shot["message"] == "then everything changed"


def _concepts(structures=("narrative", "demonstration", "three reasons")):
    return {
        "concepts": [
            {
                "id": f"c{index}",
                "title": f"Route {index}",
                "structure": structure,
                "logline": "A courier crosses the city with a record.",
                "why": "The measured chorus earns the arrival.",
                "world": "Night streets, practical light, one record.",
                "shape": ["open", "lose", "search", "arrive"],
                "signature_moment": "The label becomes a street lamp.",
                "risk": "The city may read as generic.",
            }
            for index, structure in enumerate(structures)
        ]
    }


def test_treatments_require_three_distinct_structures(client):
    response = client.put("/api/projects/production/treatments", json=_concepts())
    assert response.status_code == 200, response.text
    assert len(response.json()["concepts"]) == 3
    listed = client.get("/api/projects/production/treatments").json()
    assert len(listed["treatments"]) == 3

    duplicate = _concepts(("narrative", "narrative", "three reasons"))
    assert client.put("/api/projects/production/treatments", json=duplicate).status_code == 400
