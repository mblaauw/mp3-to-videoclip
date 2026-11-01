"""The clean-up command removes only named caches, and only when told to."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "clean_caches", Path(__file__).parents[1] / "scripts" / "clean_caches.py"
)
clean_caches = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(clean_caches)


def _film(tmp_path):
    root = tmp_path / "projects" / "film"
    for relative in (
        "work/graphics/cache/frame.png",
        "work/graphics/graphics-v1/review.png",
        "work/remotion-chunks/one.mp4",
        "assets/s001/v001.jpg",
        "renders/film-final-v001.mp4",
        "media/song.mp3",
        "work/tasks.json",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"data")
    return root


def test_it_changes_nothing_without_yes(tmp_path, capsys):
    root = _film(tmp_path)
    assert clean_caches.main(["--projects", str(tmp_path / "projects")]) == 0
    assert (root / "work/graphics/cache/frame.png").exists()
    assert "would be removed" in capsys.readouterr().out


def test_yes_removes_only_the_named_caches(tmp_path):
    root = _film(tmp_path)
    assert clean_caches.main(["--projects", str(tmp_path / "projects"), "--yes"]) == 0
    assert not (root / "work/graphics/cache").exists()
    assert not (root / "work/remotion-chunks").exists()
    for kept in (
        "work/graphics/graphics-v1/review.png",
        "assets/s001/v001.jpg",
        "renders/film-final-v001.mp4",
        "media/song.mp3",
        "work/tasks.json",
    ):
        assert (root / kept).exists(), kept
