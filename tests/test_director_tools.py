"""Paid director tools estimate, authorize and only then queue work.

The services are faked here: this test owns the money ordering, not the provider.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

from mp3_to_videoclip import services
from mp3_to_videoclip.director import tools


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "projects" / "demo"
    (root / "work").mkdir(parents=True)
    (root / "media").mkdir()
    source = root / "media" / "song.mp3"
    source.write_bytes(b"x")
    (root / "project.json").write_text(
        json.dumps(
            {
                "schema_version": 3,
                "slug": "demo",
                "title": "Demo",
                "source": "media/song.mp3",
                "source_sha256": hashlib.sha256(b"x").hexdigest(),
                "duration": 60.0,
                "aspect": "16:9",
                "fps": 24,
                "width": 1920,
                "height": 1080,
                "budget": [{"at": "2026-10-25T00:00:00+00:00", "cap_usd": "5.00"}],
            }
        )
    )
    (root / "work" / "tasks.json").write_text("{}")
    return root


class FakeRunner:
    def __init__(self):
        self.submitted = []

    def submit(self, kind, project, factory):
        self.submitted.append((kind, project))
        return "job-1"


def _fake_estimate(reserve="2.00", uploads=False, tasks=3):
    return {
        "quote_id": "quote-1",
        "scope": "stills",
        "tasks": tasks,
        "reserve_usd": reserve,
        "cap_usd": "5.00",
        "uploads_required": uploads,
        "shot_ids": ["s001", "s002", "s003"],
    }


def test_generate_images_authorizes_before_queueing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _project(tmp_path)
    authorized = {}
    monkeypatch.setattr(services.generation, "estimate", lambda *a, **k: _fake_estimate())
    monkeypatch.setattr(
        services.generation,
        "authorize",
        lambda root, quote_id, **kw: authorized.update(quote_id=quote_id, **kw) or {},
    )
    runner = FakeRunner()
    result = json.loads(
        asyncio.run(
            tools.dispatch(
                "generate_images",
                {"slug": "demo", "shot_ids": ["s001", "s002", "s003"]},
                runner,
            )
        )
    )
    assert result["status"] == "queued"
    assert result["job_id"] == "job-1"
    assert authorized["quote_id"] == "quote-1"
    assert runner.submitted == [("images", "demo")]


def test_generate_images_stops_at_the_cap(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _project(tmp_path)
    monkeypatch.setattr(
        services.generation, "estimate", lambda *a, **k: _fake_estimate(reserve="9.00")
    )
    monkeypatch.setattr(
        services.generation,
        "authorize",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not authorize")),
    )
    runner = FakeRunner()
    result = json.loads(
        asyncio.run(
            tools.dispatch("generate_images", {"slug": "demo", "shot_ids": ["s001"]}, runner)
        )
    )
    assert result["needs_budget"] is True
    assert result["decision"]["suggested_usd"]
    assert runner.submitted == []


def test_reference_upload_needs_confirmation_before_queueing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _project(tmp_path)
    monkeypatch.setattr(
        services.generation, "estimate", lambda *a, **k: _fake_estimate(uploads=True)
    )
    runner = FakeRunner()
    result = json.loads(
        asyncio.run(
            tools.dispatch("generate_images", {"slug": "demo", "shot_ids": ["s001"]}, runner)
        )
    )
    assert "needs_confirmation" in result
    assert runner.submitted == []


def test_transcription_never_uploads_audio_from_chat(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _project(tmp_path)
    monkeypatch.setattr(
        services.transcription,
        "quote",
        lambda root, language=None: {"id": "quote-2", "reserve_total_usd": "0.05"},
    )
    runner = FakeRunner()
    result = json.loads(asyncio.run(tools.dispatch("transcribe_lyrics", {"slug": "demo"}, runner)))
    assert "needs_confirmation" in result
    assert runner.submitted == []
