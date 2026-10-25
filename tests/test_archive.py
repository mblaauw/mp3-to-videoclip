"""The frozen-film reader must be tolerant and strictly read-only.

The two finished productions are never written again, so this reader answers the
library's four questions from whatever metadata survived and must not fail on a
missing brief, a malformed JSON file or an asset whose file was moved away.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from mp3_to_videoclip.domain import archive


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) if not isinstance(value, str) else value)


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _legacy(root: Path, *, title: str = "Frozen film", schema: int = 1) -> Path:
    _write(root / "project.json", {"schema_version": schema, "title": title, "duration": 241.5})
    _write(root / "brief.json", {"title": title, "treatment": "Finished."})
    _write(
        root / "work" / "assets.json",
        {
            "s001": {
                "selected": 2,
                "versions": [
                    {"version": 1, "path": "assets/s001/v001.jpg"},
                    {"version": 2, "path": "assets/s001/v002.jpg"},
                ],
            },
            "s002": {
                "selected": 1,
                "versions": [{"version": 1, "path": "assets/s002/v001.jpg"}],
            },
            "s003": {"versions": [{"version": 1, "path": "assets/s003/missing.jpg"}]},
        },
    )
    for path in ("assets/s001/v002.jpg", "assets/s001/v001.jpg", "assets/s002/v001.jpg"):
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_bytes(b"still")
    (root / "renders").mkdir(parents=True, exist_ok=True)
    (root / "renders" / "frozen-base-v002.mp4").write_bytes(b"base")
    (root / "renders" / "frozen-final-v001.mp4").write_bytes(b"final")
    return root


def test_reads_title_duration_newest_final_and_selected_stills(tmp_path):
    root = _legacy(tmp_path / "projects" / "frozen")
    film = archive.read(root)
    assert film.title == "Frozen film"
    assert film.duration == 241.5
    assert film.render == (root / "renders" / "frozen-final-v001.mp4").resolve()
    assert [p.name for p in film.stills] == ["v002.jpg", "v001.jpg"]


def test_only_pre_schema_3_projects_are_archived(tmp_path):
    legacy = _legacy(tmp_path / "projects" / "old")
    _legacy(tmp_path / "projects" / "current", schema=3)
    assert archive.is_archived(legacy) is True
    assert archive.is_archived(tmp_path / "projects" / "current") is False
    assert [film.slug for film in archive.scan(tmp_path / "projects")] == ["old"]


def test_malformed_metadata_degrades_instead_of_failing(tmp_path):
    root = tmp_path / "projects" / "broken"
    (root / "renders").mkdir(parents=True)
    _write(root / "project.json", "{not json")
    assert archive.is_archived(root) is False
    broken = tmp_path / "projects" / "thin"
    _write(broken / "project.json", '{"schema_version": 1}')
    film = archive.read(broken)
    assert film.title == "thin"
    assert film.duration is None
    assert film.render is None
    assert film.stills == ()


def test_assets_with_a_shots_wrapper_and_a_moved_file(tmp_path):
    root = _legacy(tmp_path / "projects" / "wrapped")
    _write(
        root / "work" / "assets.json",
        {"shots": {"s001": {"selected": 1, "versions": [{"version": 1, "path": "gone.jpg"}]}}},
    )
    assert archive.read(root).stills == ()


def test_scan_and_read_never_write_into_a_production(tmp_path):
    root = _legacy(tmp_path / "projects" / "frozen")
    before = _tree_hashes(tmp_path)
    archive.scan(tmp_path / "projects")
    archive.read(root)
    assert _tree_hashes(tmp_path) == before


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / "projects").is_dir(),
    reason="live productions are local and gitignored",
)
def test_the_two_finished_films_are_readable():
    projects = Path(__file__).resolve().parents[1] / "projects"
    films = {film.slug: film for film in archive.scan(projects)}
    for slug in ("forward-ever", "stof-en-stilte"):
        if slug not in films:  # pragma: no cover - depends on the local machine
            pytest.skip(f"{slug} is not present locally")
        film = films[slug]
        assert film.duration and film.duration > 60
        assert film.render is not None and film.render.is_file()
        assert len(film.stills) > 10
