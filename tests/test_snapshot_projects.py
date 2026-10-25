"""The pre-migration metadata snapshot must be complete and strictly read-only.

``projects/`` is gitignored, so this zip is the rollback for real productions.
The test builds a throwaway production containing metadata beside media, stills
and renders, then proves the archive holds every metadata file, no binary, a
per-file sha256 manifest, and that the source tree is byte-identical afterwards.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "snapshot_projects.py"


def _load():
    spec = importlib.util.spec_from_file_location("snapshot_projects", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write(path: Path, content: bytes | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode() if isinstance(content, str) else content)


def _fixture(root: Path) -> None:
    project = root / "projects" / "demo"
    _write(project / "project.json", '{"schema_version": 1}\n')
    _write(project / "work" / "storyboard.json", '{"shots": []}\n')
    _write(project / "work" / "tasks.json", '{"tasks": []}\n')
    _write(project / "DELIVERY.md", "# delivered\n")
    _write(project / "media" / "song.mp3", b"not really audio")
    _write(project / "assets" / "s001" / "v001.jpg", b"\xff\xd8\xff")
    _write(project / "assets" / "s001" / "notes.json", '{"ignored": true}\n')
    _write(project / "renders" / "final-v001.mp4", b"\x00\x00\x00")
    _write(project / "previews" / "preview.mp4", b"\x00\x00\x00")
    _write(root / "projects" / "README.txt", "outside a production\n")


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_snapshot_captures_metadata_only_and_leaves_projects_untouched(tmp_path):
    snapshot = _load()
    _fixture(tmp_path)
    before = _tree_hashes(tmp_path / "projects")

    result = snapshot.snapshot(tmp_path / "projects", tmp_path / "backups")
    assert result["projects"] == 1
    assert result["files"] == 4
    archive_path = Path(result["zip"])
    assert archive_path.is_file()

    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert names == {
            "manifest.json",
            "demo/DELIVERY.md",
            "demo/project.json",
            "demo/work/storyboard.json",
            "demo/work/tasks.json",
        }
        manifest = json.loads(archive.read("manifest.json"))
        payload = archive.read("demo/work/tasks.json")

    assert manifest["projects"]["demo"]["work/tasks.json"] == hashlib.sha256(payload).hexdigest()
    assert _tree_hashes(tmp_path / "projects") == before


def test_each_snapshot_is_a_new_archive_and_nothing_is_overwritten(tmp_path):
    snapshot = _load()
    _fixture(tmp_path)
    before = _tree_hashes(tmp_path / "projects")
    first = snapshot.snapshot(tmp_path / "projects", tmp_path / "backups")
    second = snapshot.snapshot(tmp_path / "projects", tmp_path / "backups")
    assert first["zip"] != second["zip"]
    # Both survive even when two runs land in the same second.
    for result in (first, second):
        with zipfile.ZipFile(result["zip"]) as archive:
            assert "demo/work/storyboard.json" in archive.namelist()
    assert _tree_hashes(tmp_path / "projects") == before


def test_dry_run_writes_nothing(tmp_path, capsys):
    snapshot = _load()
    _fixture(tmp_path)
    code = snapshot.main(
        [
            "--projects",
            str(tmp_path / "projects"),
            "--out",
            str(tmp_path / "backups"),
            "--dry-run",
        ]
    )
    assert code == 0
    assert json.loads(capsys.readouterr().out)["files"] == 4
    assert not (tmp_path / "backups").exists()
