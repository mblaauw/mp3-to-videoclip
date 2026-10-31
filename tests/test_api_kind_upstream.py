"""P0 regressions: a vocal advert can approve its brief; blockers name a stage."""

from __future__ import annotations

from api_support import api_client, make_api_project

from mp3_to_videoclip.storage import write_json


def _fake_probe(monkeypatch):
    monkeypatch.setattr(
        "mp3_to_videoclip.production.intake.probe",
        lambda path: {"streams": [{"codec_type": "audio"}]},
    )
    monkeypatch.setattr("mp3_to_videoclip.production.intake.audio_seconds", lambda path: 60.0)


def _advert_upload(client):
    return client.post(
        "/api/projects",
        params={
            "title": "Night Signal Advert",
            "filename": "song.mp3",
            "aspect": "16:9",
            "music_mode": "vocal",
            "budget": "3.50",
            "kind": "advert",
            "objective": "Fill the late-night listening slot",
            "message": "Night Signal is out Friday",
            "cta_text": "Pre-save now",
            "cta_url": "https://example.com",
            "length_seconds": 30,
        },
        content=b"ID3fake",
        headers={"Content-Type": "audio/mpeg"},
    )


def test_vocal_advert_can_approve_its_brief(tmp_path, monkeypatch):
    """A promo/advert has no lyrics artifact; the brief depends on analysis."""
    _fake_probe(monkeypatch)
    with api_client(tmp_path) as client:
        monkeypatch.setattr(
            client.app.state.runner,
            "submit",
            lambda kind, slug, factory, *, blocking=False: "job-1",
        )
        created = _advert_upload(client)
        assert created.status_code == 201, created.text
        slug = created.json()["slug"]
        root = tmp_path / slug

        # The local analysis job is not run in this test. Write the artifact it
        # would produce; this regression is about the brief's upstream, not DSP.
        write_json(root / "work" / "music.json", {"duration": 30.0})

        patched = client.patch(
            f"/api/projects/{slug}/brief",
            json={
                "direction": "Late-night city, one signal",
                "style": "Clean photographic, sodium light",
                "treatment": "A courier carries the last tape across a dark city.",
                "creative": {"profile_version": 1},
            },
        )
        assert patched.status_code == 200, patched.text

        state = client.get(f"/api/projects/{slug}/approvals?stages=brief").json()["stages"][0]
        assert state["state"] == "missing", state
        assert state["expected_hash"]

        approved = client.post(
            f"/api/projects/{slug}/approvals/brief",
            json={
                "expected_hash": state["expected_hash"],
                "note": "The advert story is ready",
                "confirmed": True,
            },
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["approved"] == "brief"


def test_missing_lyrics_is_named_as_the_blocking_stage(tmp_path):
    """A vocal music video without lyrics must say lyrics, not a generic stage."""
    root = make_api_project(tmp_path)
    (root / "work" / "lyrics.json").unlink()
    with api_client(tmp_path) as client:
        state = client.get("/api/projects/production/approvals?stages=brief").json()["stages"][0]
    assert state["state"] == "unavailable", state
    assert state["blocking_stage"] == "lyrics", state
    assert "lyrics" in state["error"].lower(), state


def test_a_missing_artifact_names_its_own_stage(tmp_path):
    """The blocker is the file that failed, not always the stage's parent."""
    root = make_api_project(tmp_path)
    (root / "work" / "storyboard.json").unlink()
    with api_client(tmp_path) as client:
        state = client.get("/api/projects/production/approvals?stages=storyboard").json()["stages"][
            0
        ]
    assert state["state"] == "unavailable", state
    assert state["blocking_stage"] == "storyboard", state
    assert "storyboard" in state["error"].lower(), state
