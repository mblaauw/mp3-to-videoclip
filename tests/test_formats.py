"""Production formats: presets for the New film form that only promise what the engine makes."""

from __future__ import annotations

from api_support import api_client

from mp3_to_videoclip import formats, kinds, publish
from mp3_to_videoclip.director import context
from mp3_to_videoclip.storage import read_json


def _fake_probe(monkeypatch):
    monkeypatch.setattr(
        "mp3_to_videoclip.production.intake.probe",
        lambda path: {"streams": [{"codec_type": "audio"}]},
    )
    monkeypatch.setattr("mp3_to_videoclip.production.intake.audio_seconds", lambda path: 90.0)


def _quiet(client, monkeypatch):
    monkeypatch.setattr(
        client.app.state.runner, "submit", lambda kind, slug, factory, *, blocking=False: "job-1"
    )


def _promo(client, **extra):
    return client.post(
        "/api/projects",
        params={
            "title": "Night Signal Teaser",
            "filename": "song.mp3",
            "aspect": "9:16",
            "kind": "promo",
            "message": "Night Signal is out Friday",
            "length_seconds": 30,
            **extra,
        },
        content=b"ID3fake",
        headers={"Content-Type": "audio/mpeg"},
    )


def test_every_format_is_one_the_engine_can_make():
    assert formats.check() == []


def test_every_kind_has_formats_and_a_story_film_has_one_per_template():
    by_kind = {kind: [f for f in formats.FORMATS if f.kind == kind] for kind in kinds.KINDS}
    assert all(by_kind.values())
    narrative = {f.structure for f in by_kind["narrative"]}
    assert narrative == set(formats.structure_ids("narrative"))


def test_a_promo_keeps_the_structure_and_destinations_it_was_made_with(tmp_path, monkeypatch):
    _fake_probe(monkeypatch)
    with api_client(tmp_path) as client:
        _quiet(client, monkeypatch)
        made = _promo(client, structure="Release teaser", destinations="shorts,reels,shorts")
        assert made.status_code == 201, made.text
        root = tmp_path / made.json()["slug"]
    assert read_json(root / "brief.json")["intent"]["structure"] == "Release teaser"
    assert publish.read(root)["presets"] == ["shorts", "reels"]


def test_a_structure_or_destination_the_kind_lacks_is_refused(tmp_path, monkeypatch):
    _fake_probe(monkeypatch)
    with api_client(tmp_path) as client:
        _quiet(client, monkeypatch)
        assert _promo(client, structure="five-beat-2m").status_code == 400
        assert _promo(client, destinations="myspace").status_code == 400
        assert _promo(client, voice="English_magnetic_voiced_man").status_code == 400
        assert not [p for p in tmp_path.iterdir() if (p / "project.json").is_file()]


def test_a_story_film_starts_with_the_narrator_it_was_given(tmp_path):
    from mp3_to_videoclip import narration

    with api_client(tmp_path) as client:
        made = client.post(
            "/api/projects",
            params={
                "title": "The House Key",
                "kind": "narrative",
                "length_seconds": 60,
                "structure": "fable",
                "voice": "English_Deep-VoicedGentleman",
            },
            headers={"Content-Type": "application/json"},
        )
        assert made.status_code == 201, made.text
        root = tmp_path / made.json()["slug"]
        assert narration.current_voice(root) == "English_Deep-VoicedGentleman"
        refused = client.post(
            "/api/projects",
            params={"title": "Nobody", "kind": "narrative", "voice": "no-such-voice"},
            headers={"Content-Type": "application/json"},
        )
        assert refused.status_code == 400


def test_the_writer_hears_the_structure_the_owner_chose(tmp_path, monkeypatch):
    _fake_probe(monkeypatch)
    with api_client(tmp_path) as client:
        _quiet(client, monkeypatch)
        made = _promo(client, structure="Event teaser")
    block = context.build_context(made.json()["slug"], tmp_path, stage="story")
    assert "Structure the owner chose: Event teaser" in block


def test_settings_serve_the_formats_and_the_beats_they_scale():
    from mp3_to_videoclip.api.settings import _public
    from mp3_to_videoclip.config import effective_settings

    value = _public(effective_settings())
    assert [f["id"] for f in value["formats"]] == [f.id for f in formats.FORMATS]
    five = next(s for s in value["structures"] if s["id"] == "five-beat-2m")
    assert sum(beat["seconds"] for beat in five["beats"]) == five["length"]
    assert value["voice_list"]
