"""The Publish stage's routes and the Writer's copy tool. A real small final, no provider."""

from __future__ import annotations

import asyncio
import json

from api_support import api_client
from test_publish import _stamped_final, film  # noqa: F401

from mp3_to_videoclip import publish
from mp3_to_videoclip.director import prompts, tools
from mp3_to_videoclip.storage import read_json


def test_heard_copy_thumbnails_and_the_release_through_the_routes(film):  # noqa: F811
    root = film
    final = _stamped_final(root)
    with api_client(root.parent) as client:
        base = f"/api/projects/{root.name}/publish"
        view = client.get(base).json()
        assert view["final"] == final.name and view["can_release"] is False
        assert [line["id"] for line in view["lines"]][:2] == ["final", "heard"]
        assert view["heard"]["share"] == 0.0 and view["presets"] == ["youtube"]
        heard = client.post(f"/api/projects/{root.name}/watched", json={"media": f"renders/{final.name}", "seconds": [0, 1, 2]})  # fmt: skip
        assert heard.status_code == 200 and heard.json()["heard"] == 3
        assert client.post(f"/api/projects/{root.name}/watched", json={"media": "x", "seconds": ["a"]}).status_code == 400  # fmt: skip
        assert client.get(f"/api/projects/{root.name}/watched", params={"media": f"renders/{final.name}"}).json()["share"] == 0.75  # fmt: skip
        client.post(
            f"/api/projects/{root.name}/watched",
            json={"media": f"renders/{final.name}", "seconds": [3]},
        )
        checked = client.post(
            f"{base}/check", json={"titles": ["x"], "description": "https://elsewhere.example"}
        )
        assert "not the brief's call to action" in checked.json()["problems"][0]
        refused = client.put(f"{base}/copy", json={"titles": ["x"], "description": "Only $9"})
        assert refused.status_code == 400
        saved = client.put(f"{base}/copy", json={"titles": ["Cool Cat After Dark"], "description": "Doors at 23:00.", "tags": ["jazz"]})  # fmt: skip
        assert saved.status_code == 200 and saved.json()["copy"]["titles"] == [
            "Cool Cat After Dark"
        ]
        presets = client.put(f"{base}/presets", json={"presets": ["youtube", "shorts"]})
        assert [row["id"] for row in presets.json()["plan"]] == ["youtube", "shorts"]
        assert client.put(f"{base}/presets", json={"presets": ["tiktok"]}).status_code == 400
        drawn = client.post(f"{base}/thumbnails", json={})
        assert drawn.status_code == 200, drawn.text
        names = [row["name"] for row in drawn.json()["thumbnails"]]
        assert names and client.get(f"{base}/thumb/{names[0]}").status_code == 200
        assert client.get(f"{base}/thumb/../x.jpg").status_code in (404, 400)
        chosen = client.post(f"{base}/choose", json={"name": names[0]})
        assert chosen.json()["thumbnail"]["name"] == names[0]
        view = client.get(base).json()
        assert view["can_release"] is True, view["outstanding"]
        released = client.post(f"{base}/release", json={"note": "v1"})
        assert released.status_code == 200, released.text
        assert released.json()["released"]["final"] == final.name
        assert released.json()["manifest"]["note"] == "v1"
    assert read_json(root / "work/publish.json")["released"]["final"] == final.name


def test_the_writer_writes_the_copy_under_the_rules(film):  # noqa: F811
    root = film
    assert prompts.role_for_stage("publish") == "writer"
    assert prompts.select_task(root, "publish", "writer") == "publish"
    bundle = prompts.assemble(root, "publish", role="writer")
    assert "# W7" in bundle.text and bundle.meta["words"] <= 2000

    def call(arguments):
        return json.loads(asyncio.run(tools.dispatch("write_publish_copy", {"slug": root.name, **arguments}, projects_dir=root.parent, require_reason=True, role="writer")))  # fmt: skip

    refused = call(
        {"titles": ["x"], "description": "See https://elsewhere.example", "reason": "copy"}
    )
    assert "not the brief's call to action" in refused["error"]
    assert publish.read(root)["copy"] is None
    saved = call({"titles": ["Cool Cat After Dark", "Find the second heartbeat"], "description": "Find the second heartbeat. Enter After Dark: https://coolcat.example/after-dark", "tags": ["jazz"], "reason": "The message leads."})  # fmt: skip
    assert saved["saved"] is True and saved["tags"] == 1
    assert publish.read(root)["copy"]["by"] == "writer"
    assert "write_publish_copy" in (root / "work/decisions.jsonl").read_text()
