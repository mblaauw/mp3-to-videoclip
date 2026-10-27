"""Intake copies a real MP3 into a schema 3 production; no provider is involved."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from mp3_to_videoclip import flow
from mp3_to_videoclip import production as P
from mp3_to_videoclip.domain import intake
from mp3_to_videoclip.domain.models import Lyrics, Project, Segment
from mp3_to_videoclip.storage import write_json


@pytest.fixture
def fake_probe(monkeypatch):
    monkeypatch.setattr(
        "mp3_to_videoclip.production.probe",
        lambda path: {"streams": [{"codec_type": "audio"}]},
    )
    monkeypatch.setattr("mp3_to_videoclip.production.audio_seconds", lambda path: 12.0)


def _source(tmp_path: Path, name: str = "song.mp3", payload: bytes = b"ID3fake") -> Path:
    path = tmp_path / name
    path.write_bytes(payload)
    return path


def test_create_from_upload_writes_a_guided_schema_three_project(tmp_path, fake_probe):
    projects = tmp_path / "projects"
    source = _source(tmp_path)
    created = intake.create_from_upload(
        projects,
        source,
        title="Café Zero Bars",
        aspect="9:16",
        music_mode="instrumental",
        budget="3.50",
    )
    root = created["root"]
    assert created["slug"] == "cafe-zero-bars"
    assert root == projects / "cafe-zero-bars"

    project = Project.model_validate(json.loads((root / "project.json").read_text()))
    assert project.schema_version == 3
    assert project.slug == "cafe-zero-bars"
    assert project.title == "Café Zero Bars"
    assert project.aspect == "9:16"
    assert (project.width, project.height) == (1080, 1920)
    assert project.music_mode == "instrumental"
    assert project.duration == 12.0
    assert project.cap_usd == "3.50"
    assert project.source == "media/song.mp3"
    assert (root / "media/song.mp3").read_bytes() == b"ID3fake"

    assert flow.guided(root) is True
    assert (root / "brief.json").is_file()
    assert (root / "brand.json").is_file()
    assert (root / "work/events.json").is_file()
    assert (root / "work/approvals.json").read_text().strip() == "{}"
    assert (root / "work/tasks.json").read_text().strip() == "{}"


def test_the_same_title_gets_a_unique_slug(tmp_path, fake_probe):
    projects = tmp_path / "projects"
    source = _source(tmp_path)
    first = intake.create_from_upload(projects, source, title="Zero Bars")
    second = intake.create_from_upload(projects, source, title="Zero Bars")
    assert first["slug"] == "zero-bars"
    assert second["slug"] == "zero-bars-2"


def test_concurrent_same_title_uploads_both_survive(tmp_path, fake_probe, monkeypatch):
    projects = tmp_path / "projects"
    source = _source(tmp_path)
    barrier = Barrier(2)
    original = P.init_project

    def both_reserved(*args, **kwargs):
        # Force both calls past slug selection before either starts writing.
        barrier.wait(timeout=10)
        return original(*args, **kwargs)

    monkeypatch.setattr(P, "init_project", both_reserved)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(intake.create_from_upload, projects, source, title="Zero Bars")
        second = pool.submit(intake.create_from_upload, projects, source, title="Zero Bars")
        results = [first.result(timeout=30), second.result(timeout=30)]

    assert {result["slug"] for result in results} == {"zero-bars", "zero-bars-2"}
    for result in results:
        root = result["root"]
        assert (root / "project.json").is_file()
        assert (root / "media/song.mp3").read_bytes() == b"ID3fake"


def test_failed_migration_leaves_no_half_production(tmp_path, fake_probe, monkeypatch):
    projects = tmp_path / "projects"
    source = _source(tmp_path)

    def boom(root):
        raise RuntimeError("migration exploded")

    monkeypatch.setattr("mp3_to_videoclip.domain.intake.migrate", boom)
    with pytest.raises(RuntimeError):
        intake.create_from_upload(projects, source, title="Broken")
    assert not (projects / "broken").exists()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"title": "   "},
        {"title": "Zero", "budget": "0"},
        {"title": "Zero", "budget": "-1"},
        {"title": "Zero", "aspect": "1:1"},
        {"title": "Zero", "music_mode": "spoken"},
    ],
)
def test_invalid_intake_input_is_rejected_before_writing(tmp_path, fake_probe, kwargs):
    projects = tmp_path / "projects"
    source = _source(tmp_path)
    with pytest.raises(ValueError):
        intake.create_from_upload(projects, source, **kwargs)
    assert not projects.exists() or list(projects.iterdir()) == []


def test_non_mp3_and_oversize_sources_are_rejected(tmp_path, fake_probe, monkeypatch):
    projects = tmp_path / "projects"
    with pytest.raises(ValueError, match="MP3"):
        intake.create_from_upload(projects, _source(tmp_path, "song.wav"), title="Wrong")
    monkeypatch.setattr(intake, "MAX_SOURCE_BYTES", 4)
    with pytest.raises(ValueError, match="25 MB"):
        intake.create_from_upload(projects, _source(tmp_path, payload=b"12345"), title="Big")


def test_slug_for_transliterates_and_limits_length(tmp_path):
    projects = tmp_path / "projects"
    assert intake.slug_for("Café déjà vu", projects) == "cafe-deja-vu"
    long = intake.slug_for("A" * 100, projects)
    assert len(long) <= 64
    with pytest.raises(ValueError):
        intake.slug_for("!!!", projects)


def test_a_new_project_keeps_the_default_style_core(tmp_path, fake_probe):
    projects = tmp_path / "projects"
    created = intake.create_from_upload(projects, _source(tmp_path), title="Styled")
    root = created["root"]
    write_json(root / "work/music.json", {"duration": 12.0})
    write_json(
        root / "work/lyrics.json",
        Lyrics(
            provider="manual", model="test", segments=[Segment(start=0, end=1, text="line")]
        ).model_dump(),
    )
    brief = P.load_brief(root)
    brief.direction = "Test direction"
    brief.style = "Test style"
    brief.treatment = "Test treatment"
    brief.creative.profile_version = 1
    write_json(root / "brief.json", brief.model_dump())
    P.approve(root, "brief", "test default look", via="studio", review_confirmed=True)

    brief = P.load_brief(root)
    brief.creative.look = "a different look with no shared core"
    write_json(root / "brief.json", brief.model_dump())
    with pytest.raises(ValueError, match="DEFAULT_STYLE"):
        P.approve(root, "brief", "test changed look", via="studio", review_confirmed=True)


def test_unreadable_audio_is_a_clean_value_error(tmp_path, monkeypatch):
    projects = tmp_path / "projects"

    def broken(path):
        raise RuntimeError("ffprobe failed")

    monkeypatch.setattr("mp3_to_videoclip.production.probe", broken)
    with pytest.raises(ValueError, match="readable MP3"):
        intake.create_from_upload(projects, _source(tmp_path), title="Broken")
    assert not (projects / "broken").exists()
