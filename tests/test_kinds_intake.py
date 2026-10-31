"""Production kinds, the Story intake and the excerpt contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from mp3_to_videoclip import kinds, profiles, story_beats, styles
from mp3_to_videoclip import production as P
from mp3_to_videoclip.domain import intake
from mp3_to_videoclip.models import Brief, Intent
from mp3_to_videoclip.storage import digest, read_json, write_json

EXAMPLE_INTENT = {
    "kind": "advert",
    "objective": "pre-save the single 'Forward Ever' before 14 Nov",
    "audience": "existing listeners, 18-34, on YouTube",
    "message": "The new single is out 14 Nov - pre-save now",
    "reasons": ["first release in two years", "recorded live in one take"],
    "tone": ["urgent", "warm", "nocturnal"],
    "mandatories": ["logo end card", "release date", "pre-save URL"],
    "avoid": ["stock-photo smiles"],
    "cta": {"text": "Pre-save now", "url": "https://example.com"},
    "length_seconds": 30,
    "audio_window": {"start": 62.0, "end": 92.0, "fade_in": 0.0, "fade_out": 1.5},
}


@pytest.fixture
def fake_probe(monkeypatch):
    monkeypatch.setattr(
        "mp3_to_videoclip.production.intake.probe",
        lambda path: {"streams": [{"codec_type": "audio"}]},
    )
    monkeypatch.setattr("mp3_to_videoclip.production.intake.audio_seconds", lambda path: 120.0)


def _source(tmp_path: Path) -> Path:
    path = tmp_path / "song.mp3"
    path.write_bytes(b"ID3fake")
    return path


def test_kind_table_and_prompt_files_are_complete():
    assert set(kinds.KINDS) == {"music_video", "promo", "advert"}
    assert kinds.get("music_video").signature_required is True
    assert kinds.get("promo").signature_required is False
    assert kinds.get("advert").signature_required is False
    assert kinds.get("advert").lengths == (6, 15, 20, 30, 60)
    for kind in kinds.KINDS:
        text = kinds.prompt(kind)
        assert f"kind: {kind}" in text
        assert len(text.split()) > 80


def test_advert_intake_matches_the_brief_example(tmp_path, fake_probe):
    created = intake.create_from_upload(
        tmp_path / "projects",
        _source(tmp_path),
        title="Forward Ever",
        kind="advert",
        length_seconds=30,
        window_start=62,
        fade_out=1.5,
        intent=EXAMPLE_INTENT,
    )
    root = created["root"]
    project = P.load_project(root)
    assert project.kind == "advert"
    assert project.duration == 30.0
    assert project.source_duration == 120.0
    assert project.audio_window.model_dump() == {
        "start": 62.0,
        "end": 92.0,
        "fade_in": 0.0,
        "fade_out": 1.5,
    }
    assert project.signature_required is False
    assert not (root / "brand.json").exists()
    assert not (root / "work" / "graphics-spec.json").exists()
    assert P.requires_signature(root, project) is False

    brief = read_json(root / "brief.json")
    assert brief["intent"] == EXAMPLE_INTENT
    assert Brief.model_validate(brief).intent == Intent.model_validate(EXAMPLE_INTENT)
    assert (root / "media" / "song.mp3").read_bytes() == b"ID3fake"


def test_advert_requires_message_cta_and_length(tmp_path, fake_probe):
    source = _source(tmp_path)
    base = {
        "title": "Missing facts",
        "kind": "advert",
        "length_seconds": 30,
    }
    with pytest.raises(ValueError, match="message"):
        intake.create_from_upload(tmp_path / "projects", source, **base)
    with pytest.raises(ValueError, match="call to action"):
        intake.create_from_upload(
            tmp_path / "projects",
            source,
            **base,
            intent={"message": "out now"},
        )
    with pytest.raises(ValueError, match="target length"):
        intake.create_from_upload(
            tmp_path / "projects",
            source,
            title="No length",
            kind="advert",
            intent={
                "message": "out now",
                "cta": {"text": "Buy"},
            },
        )


def test_music_video_keeps_the_signature_and_whole_track(tmp_path, fake_probe):
    created = intake.create_from_upload(
        tmp_path / "projects", _source(tmp_path), title="Whole Song"
    )
    root = created["root"]
    project = P.load_project(root)
    assert project.kind == "music_video"
    assert project.duration == 120.0
    assert project.audio_window is None
    assert project.signature_required is True
    assert (root / "work" / "graphics-spec.json").is_file()
    assert P.requires_signature(root, project) is True


def test_style_presets_are_selectable_and_only_the_protected_core_is_forced(tmp_path, fake_probe):
    root = tmp_path / "advert"
    project = P.init_project(
        root,
        _source(tmp_path),
        "advert",
        kind="advert",
        length_seconds=30,
        title="Styled Advert",
    )
    assert project.style_preset == "clean-photographic-v1"
    brief = P.load_brief(root)
    assert brief.creative.look == styles.preset("clean-photographic-v1").look
    # A non-protected preset is a starting point, not a verbatim obligation.
    brief.creative.look = "A different, deliberately custom look"
    P._require_default_style_core(project, brief)

    protected = tmp_path / "isolated" / "protected"
    video = P.init_project(protected, _source(tmp_path), "protected", title="Core")
    assert video.style_preset == profiles.STYLE_PRESET_ID
    guarded = P.load_brief(protected)
    assert guarded.creative.look == profiles.DEFAULT_STYLE
    guarded.creative.look = profiles.DEFAULT_STYLE + "\n\nNight exteriors only."
    P._require_default_style_core(video, guarded)
    guarded.creative.look = "A different look"
    with pytest.raises(ValueError, match="DEFAULT_STYLE"):
        P._require_default_style_core(video, guarded)


def test_apply_intake_can_switch_to_custom_without_rewriting_the_look(tmp_path, fake_probe):
    created = intake.create_from_upload(
        tmp_path / "projects", _source(tmp_path), title="Custom Look"
    )
    root = created["root"]
    assert P.load_project(root).style_preset == profiles.STYLE_PRESET_ID
    supplied = "A supplied master style that replaces the protected core."
    P.update_brief(root, {"creative": {"look": supplied}})

    result = P.apply_intake(root, style_preset="")

    assert result["project"].style_preset is None
    assert result["brief"].creative.look == supplied
    # The protected-core rule no longer applies once the preset is detached.
    P._require_default_style_core(result["project"], result["brief"])


def test_apply_intake_updates_window_and_invalidates_stale_measurement(tmp_path, fake_probe):
    created = intake.create_from_upload(
        tmp_path / "projects",
        _source(tmp_path),
        title="Window",
        kind="promo",
        length_seconds=60,
    )
    root = created["root"]
    write_json(root / "work" / "music.json", {"duration": 60})
    result = P.apply_intake(
        root,
        audio_window={"start": 10, "end": 40, "fade_in": 0.5, "fade_out": 1.5},
        intent={"objective": "release", "message": "out now"},
        style_preset="brand-graphic-v1",
    )
    assert result["analysis_needed"] is True
    assert result["project"].duration == 30.0
    assert result["project"].audio_window.start == 10.0
    assert result["brief"].intent.audio_window.end == 40.0
    assert result["brief"].intent.length_seconds == 30
    assert result["project"].style_preset == "brand-graphic-v1"
    assert result["brief"].creative.look == styles.preset("brand-graphic-v1").look
    assert not (root / "work" / "music.json").exists()


def _placed_promo(tmp_path: Path) -> tuple[Path, dict]:
    created = intake.create_from_upload(
        tmp_path / "projects",
        _source(tmp_path),
        title="Placed",
        kind="promo",
        length_seconds=30,
    )
    root = created["root"]
    P.apply_intake(root, audio_window={"start": 10, "end": 40, "fade_in": 0, "fade_out": 1.5})
    P.update_brief(root, {"treatment": "One walks.\n\nTwo runs."})
    placement = {
        "passages": [
            {"start": 0, "end": 10, "text": "One walks."},
            {"start": 10, "end": 20, "text": "Two runs."},
        ]
    }
    story_beats.place_story(root, placement)
    return root, read_json(root / story_beats.PATH)


def test_a_same_length_window_move_unplaces_the_story_and_keeps_the_placement(tmp_path, fake_probe):
    root, placed = _placed_promo(tmp_path)
    assert all(item["start"] is not None for item in story_beats.passages(root))

    result = P.apply_intake(
        root, audio_window={"start": 50, "end": 80, "fade_in": 0, "fade_out": 1.5}
    )

    assert result["project"].duration == 30.0
    assert not (root / story_beats.PATH).exists()
    items = story_beats.passages(root)
    assert [item["text"] for item in items] == ["One walks.", "Two runs."]
    assert all(item["start"] is None and item["end"] is None for item in items)
    assert read_json(root / f"work/story-beats-history/{digest(placed)}.json") == placed


def test_a_new_fade_plays_the_same_music_so_the_story_stays_placed(tmp_path, fake_probe):
    root, placed = _placed_promo(tmp_path)
    P.apply_intake(root, audio_window={"start": 10, "end": 40, "fade_in": 2, "fade_out": 3})
    assert read_json(root / story_beats.PATH) == placed


def test_a_refused_intake_leaves_the_story_placed(tmp_path, fake_probe):
    root, placed = _placed_promo(tmp_path)
    with pytest.raises(ValueError, match="intent is invalid"):
        P.apply_intake(
            root,
            audio_window={"start": 50, "end": 80, "fade_in": 0, "fade_out": 1.5},
            intent={"length_seconds": "long"},
        )
    assert read_json(root / story_beats.PATH) == placed
    assert P.load_project(root).audio_window.start == 10.0


def test_a_damaged_placement_refuses_the_move_rather_than_losing_the_file(tmp_path, fake_probe):
    root, _ = _placed_promo(tmp_path)
    (root / story_beats.PATH).write_text("{not json")
    with pytest.raises(ValueError):
        P.apply_intake(root, audio_window={"start": 50, "end": 80, "fade_in": 0, "fade_out": 1.5})
    assert (root / story_beats.PATH).read_text() == "{not json"
    assert P.load_project(root).audio_window.start == 10.0


def test_window_change_is_refused_once_a_storyboard_exists(tmp_path, fake_probe):
    created = intake.create_from_upload(
        tmp_path / "projects",
        _source(tmp_path),
        title="Timed",
        kind="advert",
        length_seconds=30,
        intent={
            "objective": "launch",
            "message": "out now",
            "cta": {"text": "Buy"},
        },
    )
    root = created["root"]
    (root / "work" / "storyboard.json").write_text("{}")
    with pytest.raises(ValueError, match="storyboard"):
        P.apply_intake(root, audio_window={"start": 5, "end": 35, "fade_in": 0, "fade_out": 1.5})


def test_a_promo_can_use_the_whole_track_then_add_an_excerpt(tmp_path, fake_probe):
    created = intake.create_from_upload(
        tmp_path / "projects",
        _source(tmp_path),
        title="Whole Promo",
        kind="promo",
        intent={"objective": "release", "message": "out now"},
    )
    root = created["root"]
    project = P.load_project(root)
    assert project.duration == 120.0
    assert project.audio_window is None
    assert project.signature_required is False
    assert P.render_audio(root, project) == root / "media" / "song.mp3"

    result = P.apply_intake(
        root,
        audio_window={"start": 10, "end": 40, "fade_in": 0, "fade_out": 1.5},
    )
    assert result["project"].duration == 30.0
    assert result["project"].audio_window.start == 10.0
    assert result["brief"].intent.length_seconds == 30
    assert result["analysis_needed"] is True
