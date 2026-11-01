"""The Script stage's routes, and a story film through the same Studio surfaces as any other."""

from __future__ import annotations

import asyncio
import json

from api_support import api_client
from test_story_film import approve_story, lines, make_film, tone

from mp3_to_videoclip import production as P
from mp3_to_videoclip.director import prompts, tools
from mp3_to_videoclip.storage import read_json


def _client(tmp_path, root):
    return api_client(tmp_path)


def _script():
    return {"structure": "five-beat-2m", "lines": lines()}


def test_a_story_film_is_created_with_no_upload(tmp_path):
    with api_client(tmp_path) as client:
        made = client.post(
            "/api/projects",
            params={
                "title": "The Last House Key",
                "kind": "narrative",
                "length_seconds": 120,
                "structure": "five-beat-2m",
                "fictional": True,
            },
            headers={"Content-Type": "application/json"},
        )
        assert made.status_code == 201, made.text
        assert made.json()["spine"] == "soundtrack"
        assert made.json()["analysis_job"] is None
        slug = made.json()["slug"]
        listed = next(p for p in client.get("/api/projects").json() if p["slug"] == slug)
        assert listed["spine"] == "soundtrack"
        assert listed["stage_states"]["script"] == "you"
        assert client.get(f"/api/projects/{slug}/intake").status_code == 200
        assert client.get(f"/api/projects/{slug}/audio").status_code == 404


def test_a_song_film_still_needs_its_upload(tmp_path):
    with api_client(tmp_path) as client:
        refused = client.post(
            "/api/projects",
            params={"title": "No Song", "filename": "x.mp3", "kind": "promo"},
            headers={"Content-Type": "audio/mpeg"},
        )
        assert refused.status_code == 400


def test_the_stage_writes_hears_and_keeps(tmp_path):
    root = make_film(tmp_path)
    with api_client(tmp_path) as client:
        base = f"/api/projects/{root.name}"
        empty = client.get(f"{base}/script").json()
        assert empty["script"] is None
        assert [beat["budget"] for beat in empty["beats"]["beats"]] == [8, 27, 40, 30, 15]
        saved = client.put(f"{base}/script", json=_script())
        assert saved.status_code == 200
        assert len(saved.json()["timing"]["lines"]) == 14
        assert saved.json()["soundtrack"]["built"] is False
        heard = client.post(f"{base}/soundtrack", json={}).json()
        assert heard["soundtrack"]["built"] is True
        assert client.get(heard["soundtrack"]["url"]).status_code == 200
        take = tone(tmp_path / "t.wav", 2.0).read_bytes()
        uploaded = client.post(
            f"{base}/narration/upload",
            params={"line_id": "l001", "filename": "t.wav"},
            content=take,
            headers={"Content-Type": "application/octet-stream"},
        )
        assert uploaded.status_code == 200, uploaded.text
        row = uploaded.json()["timing"]["lines"][0]
        assert row["source"] == "measured" and row["end"] == 2.0
        assert client.get(f"{base}/narration/l001/1").status_code == 200
        assert client.get(f"{base}/narration/l001/9").status_code == 404
        out = client.post(f"{base}/narration/unkeep", json={"line_id": "l001"}).json()
        assert out["timing"]["lines"][0]["source"] == "estimate"
        back = client.post(f"{base}/narration/keep", json={"line_id": "l001", "version": 1}).json()
        assert back["timing"]["lines"][0]["source"] == "measured"


def test_a_bad_script_is_refused_in_a_sentence(tmp_path):
    root = make_film(tmp_path)
    with api_client(tmp_path) as client:
        bad = client.put(
            f"/api/projects/{root.name}/script",
            json={"structure": "five-beat-2m", "lines": lines(chorus=1)},
        )
        assert bad.status_code == 400
        assert "beat this structure does not have" in bad.text


def test_only_a_story_film_has_a_script(tmp_path):
    from api_support import make_api_project

    root = make_api_project(tmp_path)
    with api_client(tmp_path) as client:
        assert client.get(f"/api/projects/{root.name}/script").status_code == 409


def test_the_writer_is_routed_by_what_exists(tmp_path):
    root = make_film(tmp_path)
    assert prompts.select_task(root, "script", "writer") == "script_narrative"
    bundle = prompts.assemble(root, "script", role="writer")
    assert {"path": "structures/five-beat-2m.md", "version": 1} in bundle.meta["files"]
    assert {"path": "shared/craft.md", "version": 1} in bundle.meta["files"]
    assert bundle.meta["words"] <= 2000
    assert "# Story film" in bundle.text
    _call(root, "write_script", structure="five-beat-2m", lines=lines())
    assert prompts.select_task(root, "script", "writer") == "narration_pass"
    assert prompts.assemble(root, "script", role="writer").meta["words"] <= 2000
    assert prompts.select_task(root, "story", "writer") in ("brief", "profile")


def _call(root, name, **arguments):
    result = asyncio.run(
        tools.dispatch(name, {"slug": root.name, **arguments}, projects_dir=root.parent)
    )
    return json.loads(result) if isinstance(result, str) else result


def test_the_writers_tools_guard_an_approved_script(tmp_path):
    root = make_film(tmp_path)
    saved = _call(root, "write_script", structure="five-beat-2m", lines=lines())
    assert saved["lines"] == 14
    assert _call(root, "get_script")["beats"]["structure"] == "five-beat-2m"
    approve_story(root)
    P.approve(root, "script", "owner")
    refused = _call(root, "update_lines", changes=[{"id": "l001", "direction": "slower"}])
    assert "error" in refused or refused.get("saved") is None
    assert read_json(root / "work/script.json")["lines"][0]["direction"] == ""
    _call(root, "update_lines", changes=[{"id": "l001", "direction": "slower"}], revising=True)
    assert read_json(root / "work/script.json")["lines"][0]["direction"] == "slower"
    assert "report" in _call(root, "get_narration")
