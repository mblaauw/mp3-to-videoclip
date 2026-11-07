"""The Sound stage's routes, the Writer's cue tool and the snapshot's ear. No provider is called."""

from __future__ import annotations

import asyncio
import json

from api_support import api_client
from test_sound import FakeSound
from test_story_film import make_film, script_for, tone

from mp3_to_videoclip import budget, narration, sound
from mp3_to_videoclip import production as P
from mp3_to_videoclip.director import prompts, tools
from mp3_to_videoclip.director.context import build_context
from mp3_to_videoclip.production import soundtrack
from mp3_to_videoclip.storage import read_json


def _film(tmp_path):
    root = make_film(tmp_path)
    script = script_for(root)
    soundtrack.ensure_spec(root, script)
    narration.import_take(root, script.lines[0].id, tone(tmp_path / "t.wav", 1.5))
    budget.set_budget(root, "5.00", "test budget")
    return root


def test_the_stage_lists_suggests_keeps_and_serves(tmp_path):
    root = _film(tmp_path)
    with api_client(tmp_path) as client:
        base = f"/api/projects/{root.name}/sound"
        empty = client.get(base).json()
        assert empty["cues"] == [] and empty["story_film"] is True and empty["suggestions"] == 6
        # The one take on disk is where the voice is; cues duck under it.
        assert len(empty["speech"]) == 1 and empty["speech"][0]["end"] > empty["speech"][0]["start"]
        assert {m["for"] for m in empty["models"]} == {"music", "effects"}
        assert all(m["price"] for m in empty["models"])
        suggested = client.post(f"{base}/suggest", json={}).json()
        assert [c["id"] for c in suggested["cues"]][:2] == ["bed", "room-hook"]
        assert suggested["cues"][1]["start_seconds"] == 0.0
        saved = client.put(base, json={"cues": [{"id": "bed", "kind": "music", "prompt": "a bed"}]})
        assert saved.status_code == 200 and len(saved.json()["cues"]) == 1
        bad = client.put(base, json={"cues": [{"id": "Bad Id"}]})
        assert bad.status_code == 400 and "lowercase" in bad.text
        uploaded = client.post(
            f"{base}/upload",
            params={"cue_id": "bed", "filename": "bed.wav"},
            content=tone(tmp_path / "bed.wav", 2.0).read_bytes(),
            headers={"Content-Type": "application/octet-stream"},
        )
        assert uploaded.status_code == 200, uploaded.text
        cue = uploaded.json()["cues"][0]
        assert cue["selected"] == 1 and cue["versions"][0]["source"] == "upload"
        assert client.get(f"{base}/bed/1").status_code == 200
        assert client.get(f"{base}/bed/9").status_code == 404
        off = client.post(f"{base}/select", json={"cue_id": "bed", "version": None}).json()
        assert off["cues"][0]["selected"] is None
        report = client.get(f"{base}/report").json()
        assert report["cues"] == 1 and report["sounding"] == 0
        assert {n["code"] for n in report["notes"]} >= {"cue_silent"}
        measured = client.get(base, params={"measure": "true"}).json()
        assert measured["report"]["mixed"] is True


def test_a_quote_and_a_run_go_through_the_journal(tmp_path, monkeypatch):
    root = _film(tmp_path)
    sound.set_cues(root, [{"id": "bed", "kind": "music", "prompt": "a slow bed"}])
    fake = FakeSound(tone(tmp_path / "made.wav", 2.0))
    monkeypatch.setattr(sound, "RunwareClient", lambda *a, **k: fake, raising=False)
    monkeypatch.setattr("mp3_to_videoclip.providers.RunwareClient", lambda *a, **k: fake)
    monkeypatch.setenv("PROJECT_VEIL_RUNWARE_API", "test-key")
    with api_client(tmp_path) as client:
        base = f"/api/projects/{root.name}/sound"
        estimate = client.post(f"{base}/estimate", json={"cue_ids": ["bed"]})
        assert estimate.status_code == 200, estimate.text
        quote = estimate.json()
        assert quote["model"] == "ace-step-v1-5-xl-turbo" and quote["decision"]["ok"] is True
        assert quote["tasks"][0]["cue_id"] == "bed"
        refused = client.post(f"{base}/generate", json={})
        assert refused.status_code == 400
        started = client.post(f"{base}/generate", json={"quote_id": quote["quote_id"]})
        assert started.status_code == 200, started.text
        job = started.json()["job_id"]
        for _ in range(200):
            state = client.get(f"/api/jobs/{job}").json()
            if state["status"] in ("succeeded", "failed"):
                break
            asyncio.run(asyncio.sleep(0.05))
        assert state["status"] == "succeeded", state
    journal = read_json(root / "work/tasks.json")
    task = next(iter(journal.values()))
    assert task["kind"] == "sound" and task["status"] == "ready"
    assert sound.read(root)["cues"][0]["selected"] == 1
    assert len(fake.submitted) == 1


def test_the_writer_names_the_cues_and_the_snapshot_hears_them(tmp_path):
    root = _film(tmp_path)
    assert prompts.role_for_stage("sound") == "writer"
    assert prompts.select_task(root, "sound", "writer") == "sound"
    assert prompts.select_task(root, "sound", "editor") == "notes"
    bundle = prompts.assemble(root, "sound", role="writer")
    assert "# W6" in bundle.text and "## Example" in bundle.text and bundle.meta["words"] <= 2000
    ids = [line["id"] for line in read_json(root / "work/script.json")["lines"]]
    result = asyncio.run(
        tools.dispatch(
            "write_sound_cues",
            {
                "slug": root.name,
                "cues": [
                    {"id": "bed", "kind": "music", "prompt": "a felt piano bed", "why": "a floor"},
                    {
                        "id": "hall",
                        "kind": "ambience",
                        "prompt": "a museum hall",
                        "start": {"line": ids[0]},
                        "end": {"line": ids[3]},
                    },  # fmt: skip
                ],
                "reason": "The film needs a floor and a room.",
            },
            projects_dir=root.parent,
            require_reason=True,
            role="writer",
        )
    )
    assert json.loads(result)["cues"] == ["bed", "hall"]
    assert sound.read(root)["cues"][1]["start"] == {"line": ids[0]}
    decisions = (root / "work/decisions.jsonl").read_text()
    assert "write_sound_cues" in decisions and "a floor and a room" in decisions
    refused = asyncio.run(
        tools.dispatch(
            "write_sound_cues",
            {"slug": root.name, "cues": [{"id": "x", "kind": "music", "prompt": "y"}]},
            projects_dir=root.parent,
            require_reason=True,
            role="writer",
        )
    )
    assert "error" in json.loads(refused)
    assert [c["id"] for c in sound.read(root)["cues"]] == ["bed", "hall"]
    snapshot = build_context(root.name, root.parent, stage="sound", task="sound")
    assert "## Sound" in snapshot and "Cues: 2, with a sound: 0" in snapshot
    assert "cue_silent" in snapshot
    # A film with no cues says nothing about sound outside its own stage.
    quiet = build_context(root.name, root.parent, stage="story", task="revise")
    assert "## Sound" in quiet  # cues exist now
    project = P.load_project(root)
    assert project.spine == "soundtrack"
