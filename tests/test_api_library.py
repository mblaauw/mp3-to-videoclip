"""Library summaries and the budget split that feed the redesigned shell."""

from __future__ import annotations

import json

from api_support import api_client, make_api_project
from fastapi.testclient import TestClient
from test_creative_production import approve_prerequisites, record_stills

from mp3_to_videoclip import production as P
from mp3_to_videoclip.app import create_app
from mp3_to_videoclip.storage import write_json


def test_summary_stage_states_follow_real_artifacts(tmp_path):
    root = make_api_project(tmp_path)
    with api_client(tmp_path) as client:
        row = client.get("/api/projects").json()[0]

    assert row["stage_states"] == {
        "track": "done",
        "story": "you",
        "storyboard": "you",
        "images": "you",
        "film": "not_ready",
    }
    assert row["next_step"] == "story"
    assert row["poster_stills"] == []
    assert row["shots"] == len(P.load_board(root).shots)
    assert row["has_analysis"] is True
    assert row["has_lyrics"] is True
    assert row["audio_url"].endswith("/audio")
    assert row["updated_at"]

    approve_prerequisites(root)
    with api_client(tmp_path) as client:
        row = client.get("/api/projects").json()[0]
    assert row["stage_states"]["story"] == "done"
    assert row["next_step"] == "storyboard"

    P.approve(root, "storyboard", "test user approved shots")
    with api_client(tmp_path) as client:
        row = client.get("/api/projects").json()[0]
    assert row["stage_states"]["storyboard"] == "done"
    assert row["next_step"] == "images"


def test_summary_posters_use_selected_image_versions(tmp_path):
    root = make_api_project(tmp_path)
    shots = [shot.id for shot in P.load_board(root).shots]
    record_stills(root, shots[:2])

    with api_client(tmp_path) as client:
        row = client.get("/api/projects").json()[0]
    assert len(row["poster_stills"]) == 2
    assert row["poster_stills"][0] == f"/api/projects/production/images/{shots[0]}/1"


def test_budget_splits_spent_reserved_and_paid_stills(tmp_path):
    root = make_api_project(tmp_path)
    write_json(
        root / "work" / "tasks.json",
        {
            "paid": {
                "kind": "images",
                "status": "ready",
                "cost_usd": "0.04",
                "reserve_usd": "0.05",
            },
            "reserved": {"kind": "images", "status": "submitted", "reserve_usd": "0.10"},
            "free": {"kind": "render", "status": "ready", "cost_usd": "0.00"},
        },
    )
    with api_client(tmp_path) as client:
        client.post(
            "/api/projects/production/budget",
            json={"amount": "5.00", "reason": "library test cap"},
        )
        body = client.get("/api/projects/production/budget").json()

    assert body["spent_usd"] == "0.04"
    assert body["reserved_usd"] == "0.10"
    assert body["committed_usd"] == "0.14"
    assert body["paid_stills"] == 1
    assert body["remaining_usd"] == "4.86"


def _archived_project(tmp_path) -> TestClient:
    projects = tmp_path / "projects"
    root = projects / "old"
    (root / "renders").mkdir(parents=True)
    (root / "assets").mkdir(parents=True)
    (root / "project.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slug": "old",
                "title": "Old Film",
                "source_sha256": "a" * 64,
                "duration": 10.0,
                "width": 1920,
                "height": 1080,
            }
        )
    )
    (root / "renders" / "old-final-v001.mp4").write_bytes(b"movie")
    (root / "assets" / "one.jpg").write_bytes(b"still")
    write_json(
        root / "work" / "assets.json",
        {
            "s001": {
                "versions": [
                    {"version": 1, "path": "assets/one.jpg", "sha256": "x", "input_hash": "x"}
                ],
                "selected": 1,
            }
        },
    )
    return TestClient(create_app(projects_dir=projects), base_url="http://127.0.0.1")


def test_archived_summary_and_player_routes_are_read_only(tmp_path):
    with _archived_project(tmp_path) as client:
        row = client.get("/api/projects").json()[0]
        assert row["archived"] is True
        assert row["render"] == "old-final-v001.mp4"
        assert row["poster_stills"] == ["/api/projects/old/archive/stills/0"]
        assert row["next_step"] is None
        assert row["stage_states"]["film"] == "done"

        still = client.get("/api/projects/old/archive/stills/0")
        assert still.status_code == 200
        assert still.content == b"still"
        movie = client.get("/api/projects/old/archive/render")
        assert movie.status_code == 200
        assert movie.content == b"movie"
        assert client.get("/api/projects/old/archive/stills/9").status_code == 404


def test_film_is_done_only_for_a_verified_final_newer_than_its_inputs(tmp_path):
    import os

    from mp3_to_videoclip.api.projects import _final_state

    root = make_api_project(tmp_path)
    renders = root / "renders"
    renders.mkdir(exist_ok=True)
    assert _final_state(root) is None

    # A movie named like a final, from a compositor that never stamped it.
    (renders / "production-final-v001.mp4").write_bytes(b"movie")
    write_json(renders / "production-final-v001.json", {"delivery_ready": True})
    assert _final_state(root) is None

    report = {
        "render_kind": "final",
        "verified": True,
        "delivery_ready": True,
        "current": True,
    }
    (renders / "production-final-v002.mp4").write_bytes(b"movie")
    write_json(renders / "production-final-v002.json", report)
    assert _final_state(root) == "done"

    board = root / "work" / "storyboard.json"
    later = (renders / "production-final-v002.json").stat().st_mtime + 60
    os.utime(board, (later, later))
    assert _final_state(root) == "changed"

    write_json(renders / "production-final-v002.json", {**report, "current": False})
    assert _final_state(root) is None
