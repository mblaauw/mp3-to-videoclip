"""The graphics preflight must be keyed on the renderer, not only on spec and base.

A preflight reuses its directory when one already exists. That is a cache, and a
cache keyed on the wrong inputs silently hands back composites drawn by older
code: approving those approves pixels the current renderer does not produce.
These tests pin the key. ``preflight_frames`` is stubbed, so no ffmpeg is needed
and the assertions are about the cache contract only.
"""

from __future__ import annotations

import json
from pathlib import Path

from mp3_to_videoclip import graphics, production, signature
from mp3_to_videoclip.storage import file_hash, read_json, write_json

TITLE = "Stof en Stilte"


def _spec() -> dict:
    return {
        "version": 1,
        "demo": False,
        "credit_roles_confirmed": True,
        "intro_seconds": 25.0,
        "credits_tail_seconds": 40.0,
        "lockup_seconds": 4.0,
        "intro": {
            "names": signature.NAMES,
            "title": TITLE,
            "tagline": signature.PRODUCTION_LINE,
            "notes": [],
            "mini_credits": [["MUSIC", "MAHA KALA"], ["FILM DIRECTION", "VJDJ69"]],
        },
        "captions": [],
        "credits": {
            "cards": [["MUSIC", "MAHA KALA"], ["FILM DIRECTION", "VJDJ69"]],
            "lockup": signature.PRODUCTION_LINE,
        },
    }


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "production"
    (root / "media").mkdir(parents=True, exist_ok=True)
    source = root / "media" / "song.mp3"
    source.write_bytes(b"stand-in source")
    (root / "work").mkdir(parents=True, exist_ok=True)
    (root / "project.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slug": "probe",
                "title": TITLE,
                "source": "media/song.mp3",
                "source_sha256": file_hash(source),
                "duration": 120.0,
                "aspect": "16:9",
                "fps": 24,
                "width": 1920,
                "height": 1080,
                "music_mode": "vocal",
                "native_size": [1376, 768],
                "workflow_version": 2,
                "image_model": "google-nano-banana-2-1",
                "style_preset": "photographic-painted-v2",
                "prompt_version": 2,
                "signature_required": True,
            }
        )
    )
    write_json(root / "work" / "graphics-spec.json", _spec())
    (root / "work" / "base-fixture.mp4").write_bytes(b"stand-in base")
    return root


def _stub_preflight(monkeypatch, calls: list, revision_box: dict) -> None:
    def fake(root, base, directory, **kwargs):
        calls.append(Path(directory))
        Path(directory).mkdir(parents=True, exist_ok=True)
        sidecar = Path(directory) / "preflight.json"
        write_json(
            sidecar,
            {
                "implementation_revision": revision_box["value"](),
                "spec_sha256": signature.digest(graphics.load_spec(root)),
                "base": {"sha256": file_hash(Path(base))},
                "frames": [],
                "truncated": False,
            },
        )
        return {"sidecar": str(sidecar)}

    monkeypatch.setattr(graphics, "preflight_frames", fake)
    # This unit tests cache identity, not storyboard/still approval scaffolding.
    monkeypatch.setattr(signature, "current_input_hash", lambda root: "same-film-inputs")
    monkeypatch.setattr(graphics, "implementation_revision", lambda: revision_box["value"]())


def _prepare(tmp_path: Path, monkeypatch, calls, revision_box) -> dict:
    root = _root(tmp_path)
    project = production.load_project(root)
    return signature.prepare_review(root, root / "work" / "base-fixture.mp4", project)


def test_preflight_directory_follows_the_implementation_revision(tmp_path: Path, monkeypatch):
    calls: list = []
    box = {"value": lambda: "revision-a"}
    _stub_preflight(monkeypatch, calls, box)
    first = _prepare(tmp_path, monkeypatch, calls, box)

    box["value"] = lambda: "revision-b"
    second = _prepare(tmp_path, monkeypatch, calls, box)

    assert Path(first["preflight"]).parent != Path(second["preflight"]).parent, (
        "an implementation change must not reuse the previous preflight directory"
    )
    assert len(calls) == 2, "the second revision must actually rebuild the samples"


def test_brand_palette_changes_the_cache_key_without_changing_raw_spec(tmp_path, monkeypatch):
    root = _root(tmp_path)
    spec = _spec()
    spec["design"] = "joint-v1"
    write_json(root / signature.SPEC, spec)
    write_json(root / "brand.json", {"id": "joint", "mark": "joint", "accent": "#D4AE6A"})
    calls = []
    _stub_preflight(monkeypatch, calls, {"value": lambda: "revision-a"})
    project = production.load_project(root)
    first = signature.prepare_review(root, root / "work/base-fixture.mp4", project)
    brand = read_json(root / "brand.json")
    brand["accent"] = "#112233"
    write_json(root / "brand.json", brand)
    second = signature.prepare_review(root, root / "work/base-fixture.mp4", project)
    assert first["spec_hash"] == second["spec_hash"]
    assert first["resolved_spec_hash"] != second["resolved_spec_hash"]
    assert first["preflight"] != second["preflight"]
    assert len(calls) == 2


def test_same_revision_reuses_its_preflight(tmp_path: Path, monkeypatch):
    calls: list = []
    box = {"value": lambda: "revision-a"}
    _stub_preflight(monkeypatch, calls, box)
    first = _prepare(tmp_path, monkeypatch, calls, box)
    second = _prepare(tmp_path, monkeypatch, calls, box)

    assert first["preflight"] == second["preflight"]
    assert first["preflight_sha256"] == second["preflight_sha256"]
    assert len(calls) == 1, "an unchanged revision should reuse its cache"


def test_a_sidecar_recording_another_revision_is_rebuilt(tmp_path: Path, monkeypatch):
    # Even if a directory name were reused, a sidecar that records a different
    # revision must be rebuilt rather than trusted.
    calls: list = []
    box = {"value": lambda: "revision-a"}
    _stub_preflight(monkeypatch, calls, box)
    first = _prepare(tmp_path, monkeypatch, calls, box)

    sidecar = tmp_path / "production" / first["preflight"]
    stale = read_json(sidecar)
    stale["implementation_revision"] = "older-code"
    write_json(sidecar, stale)

    second = _prepare(tmp_path, monkeypatch, calls, box)
    assert len(calls) == 2, "a sidecar from another revision must be regenerated"
    assert (
        read_json(tmp_path / "production" / second["preflight"])["implementation_revision"]
        == "revision-a"
    )
