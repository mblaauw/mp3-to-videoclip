"""P3 API contract: untimed lyrics, section names, credits and change reasons."""

from __future__ import annotations

import json

from api_support import add_assets, api_client, make_api_project

from mp3_to_videoclip import production as P
from mp3_to_videoclip.storage import read_json, write_json


def _stage(payload, name):
    return next(item for item in payload["stages"] if item["stage"] == name)


def _approve(client, slug, stage, note=None):
    state = _stage(client.get(f"/api/projects/{slug}/approvals?stages={stage}").json(), stage)
    body = {"expected_hash": state["expected_hash"], "confirmed": True}
    if note is not None:
        body["note"] = note
    response = client.post(f"/api/projects/{slug}/approvals/{stage}", json=body)
    assert response.status_code == 200, response.text
    return state


def test_plain_text_lyrics_are_stored_without_invented_times(tmp_path):
    root = make_api_project(tmp_path)
    with api_client(tmp_path) as client:
        saved = client.put(
            "/api/projects/production/lyrics",
            json={"text": "Every light goes out behind me\nOne tape, one city\n\nCarry the signal"},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json() == {"status": "saved", "segments": 0, "lines": 3}

        stored = read_json(root / "work/lyrics.json")
        assert stored["lines"] == [
            "Every light goes out behind me",
            "One tape, one city",
            "Carry the signal",
        ]
        assert stored["segments"] == []
        assert all("start" not in line for line in stored["lines"])

        _approve(client, "production", "analysis")
        _approve(client, "production", "lyrics")
        state = _stage(
            client.get("/api/projects/production/approvals?stages=lyrics").json(), "lyrics"
        )
        assert state["state"] == "approved"


def test_the_same_paste_box_accepts_lrc(tmp_path):
    make_api_project(tmp_path)
    with api_client(tmp_path) as client:
        saved = client.put(
            "/api/projects/production/lyrics",
            json={"text": "[00:00.50] one\n[00:01.50] two"},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json() == {"status": "saved", "segments": 2}
        stored = client.get("/api/projects/production/track").json()["lyrics"]
        assert [segment["text"] for segment in stored["segments"]] == ["one", "two"]
        assert "lines" not in stored


def test_lrc_metadata_lines_are_ignored_not_mistaken_for_plain_text(tmp_path):
    make_api_project(tmp_path)
    with api_client(tmp_path) as client:
        saved = client.put(
            "/api/projects/production/lyrics",
            json={"text": "[ar:Maha Kala]\n[ti:Zero Bars]\n[00:00.50] one\n[00:01.50] two"},
        )
    assert saved.status_code == 200, saved.text
    assert saved.json()["segments"] == 2


def test_a_mixed_timed_and_untimed_paste_is_refused(tmp_path):
    root = make_api_project(tmp_path)
    before = read_json(root / "work" / "lyrics.json")
    with api_client(tmp_path) as client:
        refused = client.put(
            "/api/projects/production/lyrics",
            json={"text": "[00:00.50] one\nno timestamp here"},
        )
    assert refused.status_code == 400
    assert "every line" in refused.text
    assert read_json(root / "work" / "lyrics.json") == before


def test_lyrics_stay_a_music_video_intake(tmp_path):
    root = make_api_project(tmp_path)
    (root / "work" / "lyrics.json").unlink(missing_ok=True)
    project = read_json(root / "project.json")
    project["kind"] = "advert"
    write_json(root / "project.json", project)
    with api_client(tmp_path) as client:
        refused = client.put(
            "/api/projects/production/lyrics",
            json={"text": "This belongs to a song, not an advert"},
        )
    assert refused.status_code == 400
    assert "music-video intake" in refused.text
    assert not (root / "work" / "lyrics.json").exists()


def test_section_names_live_outside_the_measured_file(tmp_path):
    root = make_api_project(tmp_path)
    music = {
        "duration": 2.0,
        "sections": [
            {"start": 0.0, "end": 1.0, "energy": 0.1, "label": "unreviewed"},
            {"start": 1.0, "end": 2.0, "energy": 0.5, "label": "unreviewed"},
        ],
    }
    write_json(root / "work" / "music.json", music)
    before = (root / "work" / "music.json").read_bytes()
    with api_client(tmp_path) as client:
        saved = client.put(
            "/api/projects/production/music-notes",
            json={
                "sections": [
                    {"start": 0.0, "name": "Opening"},
                    {"start": 1.0, "name": "Final chorus"},
                ]
            },
        )
        assert saved.status_code == 200, saved.text
        assert (root / "work" / "music.json").read_bytes() == before

        notes = client.get("/api/projects/production/music-notes").json()
        assert notes["sections"] == [
            {"start": 0.0, "name": "Opening"},
            {"start": 1.0, "name": "Final chorus"},
        ]
        sections = client.get("/api/projects/production/track").json()["music"]["sections"]
        assert [section["name"] for section in sections] == ["Opening", "Final chorus"]
        assert sections[0]["energy"] == 0.1

        bad = client.put(
            "/api/projects/production/music-notes",
            json={"sections": [{"start": 0.25, "name": "Invented"}]},
        )
        assert bad.status_code == 400
        assert (root / "work" / "music.json").read_bytes() == before


def test_an_empty_lyrics_file_is_not_a_lyrics_artifact(tmp_path):
    root = make_api_project(tmp_path)
    write_json(
        root / "work" / "lyrics.json",
        {
            "provider": "embedded-id3",
            "model": "untimed-metadata",
            "segments": [],
            "words": [],
            "warning": "no words",
        },
    )
    with api_client(tmp_path) as client:
        summary = next(
            item for item in client.get("/api/projects").json() if item["slug"] == "production"
        )
        state = _stage(
            client.get("/api/projects/production/approvals?stages=brief").json(), "brief"
        )
    assert summary["has_lyrics"] is False
    assert state["state"] == "missing"
    # The frontend sees has_lyrics=false and asks for words before this approval.


def test_music_mode_is_locked_once_the_story_is_approved(tmp_path):
    root = make_api_project(tmp_path)
    with api_client(tmp_path) as client:
        changed = client.put(
            "/api/projects/production/music-mode", json={"music_mode": "instrumental"}
        )
        assert changed.status_code == 200, changed.text
        assert read_json(root / "project.json")["music_mode"] == "instrumental"

        _approve(client, "production", "brief")
        locked = client.put("/api/projects/production/music-mode", json={"music_mode": "vocal"})
        assert locked.status_code == 409
        assert read_json(root / "project.json")["music_mode"] == "instrumental"


def test_credits_route_confirms_factual_cards_and_updates_the_template(tmp_path):
    root = make_api_project(tmp_path)
    from mp3_to_videoclip.signature import draft_spec

    write_json(root / "work" / "graphics-spec.json", draft_spec("Creative"))
    with api_client(tmp_path) as client:
        saved = client.put(
            "/api/projects/production/graphics/credits",
            json={
                "cards": [["MUSIC", "MAHA KALA"], ["DIRECTION", "VJDJ69"]],
                "use_as_template": True,
            },
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["confirmed"] is True
        spec = read_json(root / "work" / "graphics-spec.json")
        assert spec["credit_roles_confirmed"] is True
        assert spec["credits"]["cards"] == [["MUSIC", "MAHA KALA"], ["DIRECTION", "VJDJ69"]]
        assert (
            read_json(root / "work" / "credits-template.json")["cards"] == spec["credits"]["cards"]
        )

        assert (
            client.put("/api/projects/production/graphics/credits", json={"cards": []}).status_code
            == 400
        )


def test_recorded_v2_credits_are_refused(tmp_path):
    root = make_api_project(tmp_path)
    from mp3_to_videoclip.signature import draft_spec

    (root / "work" / "guided-flow.json").unlink()
    write_json(root / "work" / "graphics-spec.json", draft_spec("Creative"))
    with api_client(tmp_path) as client:
        response = client.put(
            "/api/projects/production/graphics/credits",
            json={"cards": [["MUSIC", "MAHA KALA"]]},
        )
    assert response.status_code == 400
    assert "brief approval" in response.text


def test_changes_endpoint_explains_a_treatment_edit_and_a_star_move(tmp_path):
    make_api_project(tmp_path)
    with api_client(tmp_path) as client:
        state = _approve(client, "production", "brief")

        patched = client.patch(
            "/api/projects/production/brief", json={"treatment": "A new story, same song."}
        )
        assert patched.status_code == 200
        stale = _stage(
            client.get("/api/projects/production/approvals?stages=brief").json(), "brief"
        )
        assert stale["state"] == "stale"
        assert stale["reason"] == "The treatment changed."
        diff = client.get("/api/projects/production/approvals/brief/changes").json()
        assert diff["available"] is True
        assert diff["reason"] == "The treatment changed."
        assert any(change["field"] == "Treatment" for change in diff["changes"])

        _approve(client, "production", "brief")
        moved = client.post(
            "/api/projects/production/proof-shots",
            json={"shot_ids": ["s001", "s003", "s004"]},
        )
        assert moved.status_code == 200, moved.text
        stale = _stage(
            client.get("/api/projects/production/approvals?stages=brief").json(), "brief"
        )
        assert stale["state"] == "stale"
        assert stale["reason"] == "The style-check shots moved to s001, s003 and s004."
        diff = client.get("/api/projects/production/approvals/brief/changes").json()
        assert any(change["field"] == "Style-check shots" for change in diff["changes"])
        assert state["expected_hash"] != stale["expected_hash"]


def test_image_review_note_is_optional_but_inspection_is_not(tmp_path):
    root = make_api_project(tmp_path)
    add_assets(root)
    board = P.load_board(root)
    shot = next(item for item in board.shots if item.id == "s001")
    with api_client(tmp_path) as client:
        missing = client.post(
            "/api/projects/production/images/review",
            json={
                "shot_id": shot.id,
                "version": 1,
                "verdict": "accept",
                "inspected": False,
            },
        )
        assert missing.status_code == 400
        accepted = client.post(
            "/api/projects/production/images/review",
            json={
                "shot_id": shot.id,
                "version": 1,
                "verdict": "accept",
                "inspected": True,
            },
        )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["review"]["note"] is None
    stored = json.loads((root / "work" / "reviews.json").read_text())
    assert stored[-1]["note"] is None
