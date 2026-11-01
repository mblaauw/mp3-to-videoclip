"""Clearing removes the named derived folders and proves nothing else moved."""

from __future__ import annotations

import fcntl
import hashlib
import json
from pathlib import Path

import pytest

from mp3_to_videoclip import caches, remotion
from mp3_to_videoclip.storage import ProjectBusy, project_lock

CACHED = (
    "work/remotion-chunks/c1.mp4",
    "work/remotion-assets/a.png",
    "work/graphics/cache/f.png",
)
KEPT = (
    "project.json",
    ".lock",
    "work/approvals.json",
    "work/tasks.json",
    "work/remotion-chunks-notes.txt",
    "assets/images/s001/v001.png",
    "media/song.mp3",
    "renders/final-v001.mp4",
)


def _film(projects: Path, name: str, schema: int = 3) -> Path:
    root = projects / name
    for relative in (*CACHED, *KEPT):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(relative.encode())
    (root / "project.json").write_text(json.dumps({"schema_version": schema}))
    return root


def _hashes(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


@pytest.fixture
def engine(tmp_path, monkeypatch):
    target = tmp_path / "engine"
    (target / ".cache").mkdir(parents=True)
    monkeypatch.setattr(remotion, "ENGINE", target)
    monkeypatch.setenv("STUDIO_LYRIC_TOOLS", str(tmp_path / "no-tools"))
    return target


@pytest.mark.parametrize("cache", caches.PRODUCTION_CACHES, ids=lambda cache: cache.name)
def test_a_clear_removes_only_that_folder(tmp_path, cache):
    root = _film(tmp_path, "film")
    before = _hashes(root)
    report = caches.clear(tmp_path, cache.name)
    assert report["removed"] == 1 and report["bytes"] > 0 and report["busy"] == []
    after = _hashes(root)
    gone = {path for path in before if path.startswith(cache.relative + "/")}
    assert gone
    assert after == {path: value for path, value in before.items() if path not in gone}


@pytest.mark.parametrize(
    "name",
    [
        "work",
        "assets",
        "../film",
        "work/remotion-chunks",
        "work/tasks.json",
        "lyric_tools",
        "",
        ".",
    ],
)
def test_anything_not_on_the_list_is_refused(tmp_path, name):
    root = _film(tmp_path, "film")
    before = _hashes(root)
    with pytest.raises(ValueError):
        caches.clear(tmp_path, name)
    assert _hashes(root) == before


def test_a_frozen_film_is_never_touched(tmp_path):
    root = _film(tmp_path, "frozen", schema=1)
    before = _hashes(root)
    for cache in caches.PRODUCTION_CACHES:
        assert caches.clear(tmp_path, cache.name)["removed"] == 0
    assert _hashes(root) == before


def test_a_film_being_written_is_skipped_and_named(tmp_path):
    root = _film(tmp_path, "film")
    before = _hashes(root)
    with project_lock(root):
        report = caches.clear(tmp_path, "remotion_chunks")
    assert report["busy"] == ["film"] and report["removed"] == 0
    assert _hashes(root) == before


def test_a_symlinked_cache_is_left_alone(tmp_path):
    root = _film(tmp_path, "film")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "precious").write_text("x")
    (root / "work/remotion-assets/a.png").unlink()
    (root / "work/remotion-assets").rmdir()
    (root / "work/remotion-assets").symlink_to(outside)
    assert caches.clear(tmp_path, "remotion_assets")["removed"] == 0
    assert (outside / "precious").exists()


def test_bundles_clear_only_their_own_entries(tmp_path, engine):
    store = engine / ".cache"
    for name in ("a" * 64, "b" * 32, "not-a-bundle", ".staging-x"):
        (store / name).mkdir()
        (store / name / "index.html").write_text("x")
    (store / "render.lock").write_text("")
    report = caches.clear(tmp_path, "renderer_bundles")
    assert report["removed"] == 2
    assert sorted(p.name for p in store.iterdir()) == [".staging-x", "not-a-bundle", "render.lock"]


def test_bundles_wait_for_a_running_render(tmp_path, engine):
    store = engine / ".cache"
    (store / ("a" * 64)).mkdir()
    with (store / "render.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with pytest.raises(ProjectBusy):
            caches.clear(tmp_path, "renderer_bundles")
    assert (store / ("a" * 64)).exists()


def test_the_listing_sizes_each_cache(tmp_path, engine):
    _film(tmp_path, "film")
    _film(tmp_path, "frozen", schema=1)
    rows = {row["name"]: row for row in caches.listing(tmp_path)}
    assert rows["remotion_chunks"]["folders"] == 1
    assert rows["remotion_chunks"]["bytes"] == len(CACHED[0])
    assert rows["lyric_tools"]["clearable"] is False
    assert rows["renderer_bundles"]["clearable"] is True
