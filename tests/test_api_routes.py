"""Every non-image Studio route has a test; no provider or paid call is made."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from api_support import api_client, make_api_project

from mp3_to_videoclip import production as P
from mp3_to_videoclip.config import Settings, load_settings
from mp3_to_videoclip.director.loop import TurnEvent
from mp3_to_videoclip.models import Lyrics, Segment
from mp3_to_videoclip.storage import read_json, write_json


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return make_api_project(tmp_path)


@pytest.fixture
def client(tmp_path: Path, project: Path):
    with api_client(tmp_path) as value:
        yield value


def test_health_and_frontend_are_served(client):
    assert client.get("/api/health").json()["ok"] is True
    home = client.get("/")
    assert home.status_code == 200
    assert "mp3-to-videoclip Studio" in home.text


def test_project_slugs_cannot_escape_the_library(client):
    for path in ("/api/projects/%2e%2e", "/api/projects/..", "/api/projects/UPPER"):
        response = client.get(path)
        assert response.status_code == 404, path


def test_projects_list_and_detail(client):
    rows = client.get("/api/projects").json()
    assert [row["slug"] for row in rows] == ["production"]
    assert rows[0]["archived"] is False
    detail = client.get("/api/projects/production").json()
    assert detail["slug"] == "production"
    assert detail["fps"] == 24
    assert detail["archived"] is False
    assert detail["shots"] == 4
    assert detail["stills"] == 0
    assert detail["approvals"] == []
    assert "status" not in detail
    verified = client.get("/api/projects/production?verify=true").json()
    assert "status" in verified
    assert client.get("/api/projects/missing").status_code == 404


def test_settings_are_masked_and_empty_secrets_preserve(monkeypatch, tmp_path):
    path = tmp_path / "settings.toml"
    monkeypatch.setattr("mp3_to_videoclip.config.settings_path", lambda: path)
    monkeypatch.setattr("mp3_to_videoclip.api.settings.effective_settings", load_settings)
    with api_client(tmp_path) as client:
        first = client.get("/api/settings").json()
        assert first["llm_api_key"] == ""
        assert first["has_llm_api_key"] is False

        saved = client.put("/api/settings", json={"llm_api_key": "secret-1", "brand_name": "Test"})
        assert saved.status_code == 200
        body = saved.json()
        assert body["llm_api_key"] == ""
        assert body["has_llm_api_key"] is True
        assert "secret-1" not in saved.text
        assert "secret-1" in path.read_text()

        client.put("/api/settings", json={"llm_api_key": "", "brand_name": "Other"})
        assert "secret-1" in path.read_text()
        assert load_settings().brand_name == "Other"


def test_track_read_lyrics_write_and_local_analysis(client, project, monkeypatch):
    track = client.get("/api/projects/production/track").json()
    assert track["music"]["duration"] == 2.0
    assert track["lyrics"]["segments"][0]["text"] == "Reviewed line"

    bad = client.put("/api/projects/production/lyrics", json={"provider": "manual"})
    assert bad.status_code == 200 and "error" in bad.json()

    lyrics = Lyrics(
        provider="manual", model="test", segments=[Segment(start=0, end=1, text="line")]
    )
    saved = client.put("/api/projects/production/lyrics", json=lyrics.model_dump())
    assert saved.json() == {"status": "saved", "segments": 1}

    imported = client.put(
        "/api/projects/production/lyrics",
        json={"lrc": "[00:00.50] one\n[00:01.50] two"},
    )
    assert imported.json() == {"status": "saved", "segments": 2}
    stored = client.get("/api/projects/production/track").json()["lyrics"]
    assert stored["segments"][-1]["end"] == 2.0
    assert "error" in client.put("/api/projects/production/lyrics", json={"lrc": "no tags"}).json()

    audio = client.get("/api/projects/production/audio")
    assert audio.status_code == 200
    assert audio.headers["content-type"] == "audio/mpeg"
    assert audio.content == (project / "media/song.mp3").read_bytes()

    monkeypatch.setattr(
        "mp3_to_videoclip.analysis.analyze",
        lambda path, duration: {
            "duration": duration,
            "estimated_tempo_bpm": 120.0,
            "sections": [],
            "warnings": [],
        },
    )
    analysed = client.post("/api/projects/production/analyze", json={})
    assert analysed.status_code == 200
    assert analysed.json()["status"] == "done"
    assert read_json(project / "work/music.json")["estimated_tempo_bpm"] == 120.0


def test_story_brief_and_treatments(client, project):
    brief = client.get("/api/projects/production/brief").json()
    assert brief["direction"] == "DIRECTION-SECRET"

    patched = client.patch("/api/projects/production/brief", json={"treatment": "A new treatment"})
    assert patched.status_code == 200
    assert patched.json()["treatment"] == "A new treatment"

    bad = client.patch("/api/projects/production/brief", json={"creative": {"look": 123}})
    assert bad.status_code == 400
    assert client.get("/api/projects/production/brief").json()["treatment"] == ("A new treatment")

    assert client.get("/api/projects/production/treatments").json() == {"treatments": []}
    write_json(project / "work/treatments.json", {"treatments": [{"id": "a"}]})
    assert client.get("/api/projects/production/treatments").json()["treatments"][0]["id"] == "a"


def test_storyboard_patch_validates_before_writing(client):
    board = client.get("/api/projects/production/storyboard").json()
    shot_id = board["shots"][0]["id"]

    ok = client.patch(
        "/api/projects/production/storyboard/shots",
        json={"changes": [{"id": shot_id, "camera": "zoom_in"}]},
    )
    assert ok.status_code == 200
    assert ok.json()["shots"][0]["camera"] == "zoom_in"

    bad = client.patch(
        "/api/projects/production/storyboard/shots",
        json={"changes": [{"id": shot_id, "camera": "warp"}]},
    )
    assert bad.status_code == 400
    assert (
        client.get("/api/projects/production/storyboard").json()["shots"][0]["camera"] == "zoom_in"
    )


def test_missing_storyboard_is_an_empty_state(client, project):
    (project / "work/storyboard.json").unlink()
    response = client.get("/api/projects/production/storyboard")
    assert response.status_code == 200
    assert response.json() == {"available": False}


def test_storyboard_boundary_update_keeps_later_cuts_in_place(client):
    board = client.get("/api/projects/production/storyboard").json()
    first, second = board["shots"][:2]
    second_end = second["start_frame"] + second["duration_frames"]
    after = board["shots"][2]["start_frame"]
    frame = first["start_frame"] + first["duration_frames"] + 2
    updated = client.patch(
        "/api/projects/production/storyboard/shots",
        json={
            "changes": [
                {"id": first["id"], "duration_frames": frame - first["start_frame"]},
                {
                    "id": second["id"],
                    "start_frame": frame,
                    "duration_frames": second_end - frame,
                },
            ]
        },
    )
    assert updated.status_code == 200, updated.text
    shots = updated.json()["shots"]
    assert shots[0]["duration_frames"] == frame - first["start_frame"]
    assert shots[1]["start_frame"] == frame
    assert shots[1]["start_frame"] + shots[1]["duration_frames"] == second_end
    assert shots[2]["start_frame"] == after


def test_storyboard_skeleton_needs_an_approved_brief(client, project):
    P.approve(project, "brief", "test brief", via="studio", review_confirmed=True)
    (project / "work/storyboard.json").unlink()
    created = client.post(
        "/api/projects/production/storyboard/skeleton",
        json={"seconds": 2, "timing": "free"},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["total_frames"] == 48
    assert body["shots"]


def test_proof_shots_are_validated_and_saved(client, project):
    board = client.get("/api/projects/production/storyboard").json()
    ids = [shot["id"] for shot in board["shots"] if not shot["asset_shot_id"]][:3]
    saved = client.post("/api/projects/production/proof-shots", json={"shot_ids": ids})
    assert saved.status_code == 200
    assert saved.json()["proof_shot_ids"] == ids
    assert client.get("/api/projects/production/brief").json()["creative"]["proof_shot_ids"] == ids
    assert (
        client.post("/api/projects/production/proof-shots", json={"shot_ids": ids[:2]}).status_code
        == 400
    )
    assert (
        client.post(
            "/api/projects/production/proof-shots",
            json={"shot_ids": [ids[0], "missing", ids[1]]},
        ).status_code
        == 400
    )


def test_adaptive_skeleton_uses_guided_evidence_without_extra_approvals(client, project):
    P.approve(project, "brief", "test brief", via="studio", review_confirmed=True)
    (project / "work/storyboard.json").unlink()
    created = client.post(
        "/api/projects/production/storyboard/skeleton",
        json={"seconds": 2, "timing": "adaptive"},
    )
    assert created.status_code == 200, created.text
    board = created.json()
    assert board["total_frames"] == 48
    assert board["shots"][0]["start_frame"] == 0


def test_film_graphics_render_and_exports(client, project, monkeypatch):
    assert client.get("/api/projects/production/graphics").json() == {"available": False}
    write_json(project / "work/graphics-spec.json", {"version": 1})
    assert client.get("/api/projects/production/graphics").json()["available"] is True

    submitted = []
    monkeypatch.setattr(
        client.app.state.runner,
        "submit",
        lambda kind, slug, factory: submitted.append((kind, slug)) or "job-1",
    )
    queued = client.post("/api/projects/production/render", json={"kind": "preview"})
    assert queued.json() == {"job_id": "job-1", "kind": "preview", "status": "queued"}
    assert submitted == [("render", "production")]
    assert client.post("/api/projects/production/render", json={"kind": "warp"}).status_code == 400
    blocked = client.post("/api/projects/production/render", json={"kind": "final"})
    assert blocked.status_code == 400
    assert "needs current user approval" in blocked.text
    assert submitted == [("render", "production")]

    (project / "renders").mkdir()
    (project / "renders" / "a.mp4").write_bytes(b"x")
    (project / "previews").mkdir()
    (project / "previews" / "p.mp4").write_bytes(b"p")
    assert client.get("/api/projects/production/exports").json() == {
        "exports": ["a.mp4"],
        "previews": ["p.mp4"],
    }
    played = client.get("/api/projects/production/film/renders/a.mp4")
    assert played.status_code == 200
    assert played.headers["content-type"] == "video/mp4"
    assert played.content == b"x"
    assert client.get("/api/projects/production/film/previews/p.mp4").status_code == 200
    assert client.get("/api/projects/production/film/renders/missing.mp4").status_code == 404
    assert client.get("/api/projects/production/film/renders/a.txt").status_code == 404
    assert client.get("/api/projects/production/film/other/a.mp4").status_code == 404


def test_budget_read_topup_and_validation(client, project):
    first = client.get("/api/projects/production/budget").json()
    assert first["cap_usd"] is None
    assert first["committed_usd"] == "0.00"
    assert first["remaining_usd"] is None

    added = client.post(
        "/api/projects/production/budget", json={"amount": "5.00", "reason": "test cap"}
    )
    assert added.status_code == 200
    assert added.json()["cap_usd"] == "5.00"
    assert client.get("/api/projects/production/budget").json()["remaining_usd"] == "5.00"

    for payload in (
        {"amount": "0", "reason": "zero"},
        {"amount": "-1", "reason": "negative"},
        {"amount": "nope", "reason": "not money"},
        {"amount": "6.00"},
    ):
        assert client.post("/api/projects/production/budget", json=payload).status_code == 400, (
            payload
        )

    write_json(
        project / "work/tasks.json",
        {"t1": {"status": "ready", "cost_usd": "6.00"}},
    )
    assert (
        client.post(
            "/api/projects/production/budget", json={"amount": "5.00", "reason": "lower"}
        ).status_code
        == 400
    )


def test_jobs_list_get_and_cancel(client):
    from mp3_to_videoclip.jobs.runner import Job

    assert client.get("/api/jobs").json() == []
    runner = client.app.state.runner
    # Route contract only: the runner's own queue behaviour is tested directly.
    runner._jobs["job-test"] = Job(
        id="job-test", kind="test", project="production", status="queued"
    )
    assert any(row["id"] == "job-test" for row in client.get("/api/jobs").json())
    assert client.get("/api/jobs/job-test").json()["kind"] == "test"
    assert client.post("/api/jobs/job-test/cancel", json={}).status_code == 200
    assert client.get("/api/jobs/job-test").json()["status"] == "cancelled"
    assert client.get("/api/jobs/missing").status_code == 404
    assert client.post("/api/jobs/missing/cancel", json={}).status_code == 404


def test_events_stream_starts_with_hello(client):
    with client.stream("GET", "/api/events") as response:
        assert response.status_code == 200
        lines = response.iter_lines()
        head = [next(lines) for _ in range(4)]
    assert "hello" in "\n".join(head)


def test_director_chat_reads_and_streams(client, monkeypatch):
    assert client.get("/api/projects/production/chat").json() == {"messages": []}
    assert client.post("/api/projects/production/chat", json={"message": ""}).json() == {
        "error": "message required"
    }

    monkeypatch.setattr(
        "mp3_to_videoclip.api.director.effective_settings",
        lambda: Settings(llm_api_key=""),
    )
    missing = client.post("/api/projects/production/chat", json={"message": "hi"}).json()
    assert missing["error"].startswith("no LLM key")

    monkeypatch.setattr(
        "mp3_to_videoclip.api.director.effective_settings",
        lambda: Settings(llm_api_key="test-key"),
    )

    async def fake_turn(*args, **kwargs):
        yield TurnEvent(kind="text", text="hello")
        yield TurnEvent(kind="done", text="hello")

    monkeypatch.setattr("mp3_to_videoclip.api.director.run_turn", fake_turn)
    streamed = client.post(
        "/api/projects/production/chat", json={"message": "hi", "stage": "story"}
    )
    assert streamed.status_code == 200
    events = [json.loads(line) for line in streamed.text.splitlines() if line]
    assert [event["kind"] for event in events] == ["text", "done"]
