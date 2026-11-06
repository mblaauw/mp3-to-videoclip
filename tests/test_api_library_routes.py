"""The library's routes: promote, adopt, series, a still from another film. Nothing is deleted."""

from __future__ import annotations

from api_support import add_assets, api_client, make_api_project
from test_creative_production import jpeg

from mp3_to_videoclip import production as P
from mp3_to_videoclip.references import import_reference
from mp3_to_videoclip.storage import read_json


def _two(tmp_path):
    first = make_api_project(tmp_path, "first")
    second = make_api_project(tmp_path, "second")
    face = import_reference(first, jpeg(tmp_path / "face.jpg"), note="owner", permission_confirmed=True)  # fmt: skip
    P.update_brief(first, {"characters": [{"id": "curator", "identity": "a curator", "permission_confirmed": True, "references": [face["path"]]}]}, owner=True)  # fmt: skip
    return first, second


def test_promote_adopt_and_a_series_through_the_routes(tmp_path):
    first, second = _two(tmp_path)
    with api_client(tmp_path) as client:
        assert client.get("/api/library").json() == {"entries": [], "series": []}
        promoted = client.post("/api/library/promote", json={"slug": "first", "kind": "character", "id": "curator", "label": "The curator"})  # fmt: skip
        assert promoted.status_code == 200, promoted.text
        entry = promoted.json()["entry"]
        assert entry["key"] == "character:curator" and entry["summary"] == "a curator"
        assert entry["thumbnail"].startswith("/api/library/references/")
        assert client.get(entry["thumbnail"]).status_code == 200
        assert client.get("/api/library/references/nope.png").status_code == 404
        refused = client.post("/api/library/promote", json={"slug": "first", "kind": "character", "id": "nobody"})  # fmt: skip
        assert refused.status_code == 400 and "no character" in refused.text
        assert client.post("/api/library/promote", json={"slug": "../x", "kind": "character", "id": "a"}).status_code == 404  # fmt: skip
        series = client.put("/api/library/series/museum", json={"title": "The Museum", "bible": "A curator.", "recurring": ["character:curator"]})  # fmt: skip
        assert series.status_code == 200, series.text
        assert series.json()["saved"]["recurring"] == ["character:curator"]
        assert client.get("/api/library/series/museum").json()["title"] == "The Museum"
        assert client.get("/api/library/series/nope").status_code == 400
        adopted = client.post(
            "/api/projects/second/library/adopt", json={"key": "character:curator"}
        )
        assert adopted.status_code == 200, adopted.text
        assert adopted.json()["changed"] == ["characters"]
        assert [c.id for c in P.load_brief(second).characters] == ["curator"]
        assert client.post("/api/projects/second/library/adopt", json={"key": "nope"}).status_code == 400  # fmt: skip
        assert client.post("/api/projects/second/library/adopt", json={"key": "look:none"}).status_code == 400  # fmt: skip
        # A new film in the series carries the cast from its first byte.
        made = client.post(
            "/api/projects",
            params={
                "title": "002",
                "kind": "narrative",
                "length_seconds": 120,
                "structure": "five-beat-2m",
                "fictional": True,
                "series": "museum",
                "episode": 2,
            },  # fmt: skip
            headers={"Content-Type": "application/json"},
        )
        assert made.status_code == 201, made.text
        slug = made.json()["slug"]
        listed = next(p for p in client.get("/api/projects").json() if p["slug"] == slug)
        assert listed["series"] == {"id": "museum", "episode": 2}
        assert [c.id for c in P.load_brief(tmp_path / slug).characters] == ["curator"]
        assert [ep["slug"] for ep in client.get("/api/library/series/museum").json()["episodes"]] == [slug]  # fmt: skip
        again = client.post(
            "/api/projects",
            params={
                "title": "003",
                "kind": "narrative",
                "length_seconds": 120,
                "structure": "five-beat-2m",
                "fictional": True,
                "series": "museum",
                "episode": 2,
            },  # fmt: skip
            headers={"Content-Type": "application/json"},
        )
        assert again.status_code == 400 and "already exists" in again.text
        assert (
            client.post(
                "/api/projects",
                params={
                    "title": "004",
                    "kind": "narrative",
                    "length_seconds": 120,
                    "structure": "five-beat-2m",
                    "fictional": True,
                    "series": "nope",
                    "episode": 1,
                },  # fmt: skip
                headers={"Content-Type": "application/json"},
            ).status_code
            == 400
        )
    # The library lives where the app was told, and the first film was only read.
    assert (tmp_path / "_library" / "world.json").is_file()
    assert read_json(first / "brief.json")["characters"][0]["id"] == "curator"


def test_a_still_is_brought_from_another_film(tmp_path):
    first, second = _two(tmp_path)
    add_assets(first)
    with api_client(tmp_path) as client:
        brought = client.post("/api/projects/second/library/bring-still", json={"from_slug": "first", "shot_id": "s001", "version": 1})  # fmt: skip
        assert brought.status_code == 200, brought.text
        assert brought.json()["path"].startswith("media/uploads/")
        assert (second / brought.json()["path"]).is_file()
        assert client.post("/api/projects/second/library/bring-still", json={"from_slug": "first", "shot_id": "s001", "version": "1"}).status_code == 400  # fmt: skip
        assert client.post("/api/projects/second/library/bring-still", json={"from_slug": "first", "shot_id": "s001", "version": 9}).status_code == 400  # fmt: skip
