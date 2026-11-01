"""Archived films are readable in the library and never writable through a stage API."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from mp3_to_videoclip.app import create_app


def test_archived_production_is_listed_but_stage_endpoints_refuse(tmp_path):
    projects = tmp_path / "projects"
    root = projects / "old"
    root.mkdir(parents=True)
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
    client = TestClient(create_app(projects_dir=projects), base_url="http://127.0.0.1")
    with client:
        listed = client.get("/api/projects")
        assert listed.status_code == 200
        assert listed.json()[0]["archived"] is True
        assert listed.json()[0]["title"] == "Old Film"

        assert client.get("/api/projects/old/budget").status_code == 409
        assert client.get("/api/projects/old/storyboard").status_code == 409
        assert client.post("/api/projects/old/render", json={"kind": "final"}).status_code == 409


def _make_film(projects, slug, schema=1):
    root = projects / slug
    root.mkdir(parents=True)
    (root / "project.json").write_text(
        json.dumps({"schema_version": schema, "slug": slug, "title": slug, "duration": 1.0})
    )
    return root


def test_parking_moves_a_film_in_the_library_without_touching_its_folder(tmp_path):
    projects = tmp_path / "projects"
    root = _make_film(projects, "old")
    _make_film(projects, "other")
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    stamp = root.stat().st_mtime_ns
    client = TestClient(create_app(projects_dir=projects), base_url="http://127.0.0.1")
    with client:
        assert client.put("/api/projects/old/parked", json={"parked": True}).status_code == 200
        listed = {film["slug"]: film for film in client.get("/api/projects").json()}
        assert listed["old"]["parked"] is True
        assert listed["other"]["parked"] is False

        assert client.put("/api/projects/old/parked", json={"parked": False}).status_code == 200
        assert client.get("/api/projects").json()[0]["parked"] is False

        missing = client.put("/api/projects/nothing/parked", json={"parked": True})
        assert missing.status_code == 404
    assert {path: path.read_bytes() for path in root.rglob("*") if path.is_file()} == before
    assert root.stat().st_mtime_ns == stamp
