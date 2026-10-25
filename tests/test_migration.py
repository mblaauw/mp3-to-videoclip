"""Schema 1 -> 3 migration must be lossless for the work and reversible.

The live production (zero-bars) was the first real migration; this test pins the
contract on a synthetic project: legacy flags dropped, budget moved into the
project document, a history snapshot written, and the source/stills untouched.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from mp3_to_videoclip.domain.migrate import is_legacy, migrate
from mp3_to_videoclip.domain.models import Project


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) if not isinstance(value, str) else value)


def _legacy(root: Path) -> Path:
    _write(
        root / "project.json",
        {
            "schema_version": 1,
            "slug": "demo",
            "title": "Demo",
            "source": "media/song.mp3",
            "source_sha256": "a" * 64,
            "duration": 120.0,
            "aspect": "16:9",
            "fps": 24,
            "width": 1920,
            "height": 1080,
            "music_mode": "vocal",
            "native_size": [1376, 768],
            "workflow_version": 2,
            "image_model": "google-nano-banana-2-1",
            "prompt_version": 2,
            "signature_required": True,
            "renderer_backend": "remotion",
            "source_filename": "download.mp3",
        },
    )
    _write(
        root / "work" / "production-budget.json",
        {
            "version": 1,
            "cap_usd": "5",
            "max_corrections": 1,
            "note": "created in studio",
            "at": "2026-10-24T00:00:00+00:00",
        },
    )
    (root / "media").mkdir(parents=True, exist_ok=True)
    (root / "media" / "song.mp3").write_bytes(b"source")
    (root / "assets" / "s001").mkdir(parents=True, exist_ok=True)
    (root / "assets" / "s001" / "v001.jpg").write_bytes(b"still")
    return root


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_legacy_project_migrates_and_keeps_its_work(tmp_path):
    root = _legacy(tmp_path / "projects" / "demo")
    before = {
        "media/song.mp3": (root / "media/song.mp3").read_bytes(),
        "assets/s001/v001.jpg": (root / "assets/s001/v001.jpg").read_bytes(),
    }
    assert is_legacy(root) is True

    result = migrate(root)
    assert result["migrated"] is True
    stored = json.loads((root / "project.json").read_text())
    assert stored["schema_version"] == 3
    assert not set(stored) & {
        "workflow_version",
        "prompt_version",
        "signature_required",
        "renderer_backend",
        "source_filename",
    }
    assert stored["budget"][0]["cap_usd"] == "5"
    assert not (root / "work" / "production-budget.json").exists()
    Project.model_validate(stored)

    for relative, content in before.items():
        assert (root / relative).read_bytes() == content
    assert (root / "history").is_dir()
    assert any(p.name.startswith("migration-") for p in (root / "history").iterdir())


def test_dry_run_writes_nothing(tmp_path):
    root = _legacy(tmp_path / "projects" / "demo")
    before = _tree_hashes(root)
    result = migrate(root, dry_run=True)
    assert result["migrated"] is False
    assert result["would_write"]["schema_version"] == 3
    assert _tree_hashes(root) == before


def test_already_migrated_is_a_no_op(tmp_path):
    root = _legacy(tmp_path / "projects" / "demo")
    migrate(root)
    after = _tree_hashes(root)
    assert migrate(root)["migrated"] is False
    assert _tree_hashes(root) == after


def test_migrated_project_loads_in_the_engine(tmp_path):
    from mp3_to_videoclip import production as P

    root = _legacy(tmp_path / "projects" / "demo")
    migrate(root)
    project = P.load_project(root, verify_source=False)
    assert project.schema_version == 3
    assert project.budget[0]["cap_usd"] == "5"


def test_migration_keeps_the_correction_policy_and_engine_sees_the_cap(tmp_path):
    from mp3_to_videoclip import budget as engine

    root = _legacy(tmp_path / "projects" / "demo")
    migrate(root)
    stored = json.loads((root / "project.json").read_text())
    assert stored["budget"][0]["max_corrections"] == 1
    record = engine.read_budget(root)
    assert record["cap_usd"] == "5"
    assert record["max_corrections"] == 1


def test_migration_keeps_workflow_two_prompt_semantics(tmp_path):
    """Schema 3 keeps the v2 prompt layout; otherwise every still input hash changes."""
    from test_creative_production import make_root

    from mp3_to_videoclip import production as P

    root = make_root(tmp_path / "work", name="prompted")
    data = json.loads((root / "project.json").read_text())
    data["workflow_version"] = 2
    data["prompt_version"] = 2
    (root / "project.json").write_text(json.dumps(data))
    shot = P.load_board(root).shots[0]
    before = P.image_spec(root, shot)

    migrate(root)

    after = P.image_spec(root, shot)
    assert after == before
