"""Derived folders the app can rebuild, and the one list of what may be cleared.

This is the only written exception to "a production folder is never deleted from":
the folders named here hold copies and renders with receipts that fail closed, so a
missing one is rebuilt and never trusted. Anything not named here is refused, and a
frozen film or a production being written is left alone.
"""

from __future__ import annotations

import fcntl
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import lyric_tools, remotion
from .domain import archive
from .storage import ProjectBusy, project_lock


@dataclass(frozen=True)
class Cache:
    name: str
    label: str
    rebuilds: str
    relative: str = ""


#: Inside each production. Nothing else under a production can be cleared.
PRODUCTION_CACHES = (
    Cache(
        "remotion_chunks",
        "Finished render chunks",
        "The next render of each film takes longer.",
        "work/remotion-chunks",
    ),
    Cache(
        "remotion_assets",
        "Copied stills for rendering",
        "Copied again from the film's own stills at the next render.",
        "work/remotion-assets",
    ),
    Cache(
        "graphics_cache",
        "Old compositor frames",
        "Drawn again only if an old film is rendered with the old compositor.",
        "work/graphics/cache",
    ),
)
RENDERER_BUNDLES = Cache(
    "renderer_bundles",
    "Renderer bundles",
    "The next render bundles the renderer again, which adds about a minute.",
)
LYRIC_TOOLS = Cache(
    "lyric_tools",
    "Lyric timing tools",
    "Not cleared here: they are installed on purpose and are a large download.",
)
#: Only the renderer's content-addressed entries; its locks and staging stay.
_BUNDLE = re.compile(r"^[0-9a-f]{32}(?:[0-9a-f]{32})?$")


def _size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file() and not item.is_symlink())  # fmt: skip


def _productions(projects_dir: Path) -> list[Path]:
    """Live productions only: a frozen film is never written to, not even here."""
    if not projects_dir.is_dir():
        return []
    return [
        root
        for root in sorted(projects_dir.iterdir())
        if root.is_dir()
        and not root.is_symlink()
        and (root / "project.json").is_file()
        and not archive.is_archived(root)
    ]


def find(projects_dir: Path, cache: Cache) -> list[tuple[Path, int]]:
    """Each real folder of one production cache, with its size."""
    found = []
    for root in _productions(projects_dir):
        path = root / cache.relative
        if path.is_dir() and not path.is_symlink():
            found.append((path, _size(path)))
    return found


def _bundles() -> list[Path]:
    store = remotion.ENGINE / ".cache"
    if not store.is_dir():
        return []
    return [
        path
        for path in sorted(store.iterdir())
        if path.is_dir() and not path.is_symlink() and _BUNDLE.match(path.name)
    ]


def listing(projects_dir: Path) -> list[dict]:
    rows = []
    for cache in PRODUCTION_CACHES:
        found = find(projects_dir, cache)
        rows.append(_row(cache, sum(size for _, size in found), len(found), True))
    bundles = _bundles()
    rows.append(_row(RENDERER_BUNDLES, sum(_size(path) for path in bundles), len(bundles), True))
    tools = lyric_tools._home()
    rows.append(_row(LYRIC_TOOLS, _size(tools) if tools.is_dir() else 0, int(tools.is_dir()), False))  # fmt: skip
    return rows


def _row(cache: Cache, size: int, folders: int, clearable: bool) -> dict:
    return {
        "name": cache.name,
        "label": cache.label,
        "rebuilds": cache.rebuilds,
        "bytes": size,
        "folders": folders,
        "clearable": clearable,
    }


def _clear_bundles() -> dict:
    """Take the machine's render lock, so no render is using what is removed."""
    store = remotion.ENGINE / ".cache"
    store.mkdir(parents=True, exist_ok=True)
    with (store / "render.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ProjectBusy("a render is running; clear this after it finishes") from exc
        bundles = _bundles()
        freed = sum(_size(path) for path in bundles)
        for path in bundles:
            shutil.rmtree(path)
    return {"name": RENDERER_BUNDLES.name, "removed": len(bundles), "bytes": freed, "busy": []}


def clear(projects_dir: Path, name: str) -> dict:
    """Remove one named cache. Anything not on the list is refused."""
    if name == RENDERER_BUNDLES.name:
        return _clear_bundles()
    cache = next((item for item in PRODUCTION_CACHES if item.name == name), None)
    if cache is None:
        raise ValueError(f"{name} is not a cache that can be cleared")
    removed = freed = 0
    busy = []
    for root in _productions(projects_dir):
        path = root / cache.relative
        if not path.is_dir() or path.is_symlink():
            continue
        try:
            with project_lock(root):
                freed += _size(path)
                shutil.rmtree(path)
                removed += 1
        except ProjectBusy:
            busy.append(root.name)
    return {"name": name, "removed": removed, "bytes": freed, "busy": busy}
