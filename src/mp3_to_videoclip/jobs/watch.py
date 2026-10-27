"""Notice production changes made outside a Studio request.

The CLI (transcription, listening, maintenance), the director's MCP tools and a
second Studio tab all write productions without passing through the request
that would announce the change. While at least one browser listens, this
watcher takes a cheap signature of each production every second and publishes
``project.changed`` when it moves, so every open view reloads by itself.

The signature only reads names, sizes and modification times. It covers the
artifacts a view renders (top-level and ``work/`` JSON) and the *names* of the
rendered films, never a file that is being written: renders grow for minutes
and a progress file is rewritten every half second, and neither may turn into a
reload storm. Dot-files (atomic-write temporaries, progress, locks) are ignored.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from pathlib import Path

from .events import EventBus

logger = logging.getLogger(__name__)

INTERVAL = 1.0
FILM_DIRS = ("renders", "previews")

Signature = tuple


def _json_entries(directory: Path) -> list[tuple[str, int, int]]:
    entries = []
    try:
        with os.scandir(directory) as items:
            for item in items:
                if item.name.startswith(".") or not item.name.endswith(".json"):
                    continue
                try:
                    if not item.is_file():
                        continue
                    stat = item.stat()
                except OSError:
                    continue
                entries.append((item.name, stat.st_mtime_ns, stat.st_size))
    except OSError:
        return []
    return sorted(entries)


def _names(directory: Path) -> tuple[str, ...]:
    try:
        with os.scandir(directory) as items:
            return tuple(sorted(item.name for item in items if not item.name.startswith(".")))
    except OSError:
        return ()


def signature(root: Path) -> Signature:
    """A cheap fingerprint of what the Studio shows for one production."""
    root = Path(root)
    return (
        tuple(_json_entries(root)),
        tuple(_json_entries(root / "work")),
        tuple(_names(root / name) for name in FILM_DIRS),
    )


def library(projects_dir: Path) -> tuple[str, ...]:
    projects_dir = Path(projects_dir)
    try:
        with os.scandir(projects_dir) as items:
            return tuple(
                sorted(
                    item.name
                    for item in items
                    if not item.name.startswith(".")
                    and item.is_dir()
                    and (Path(item.path) / "project.json").is_file()
                )
            )
    except OSError:
        return ()


class ProjectWatcher:
    def __init__(self, projects_dir: Path, bus: EventBus, *, interval: float = INTERVAL):
        self.projects_dir = Path(projects_dir)
        self.bus = bus
        self.interval = interval
        self._known: dict[str, Signature] = {}
        self._library: tuple[str, ...] | None = None
        self._task: asyncio.Task | None = None

    # -- snapshots ------------------------------------------------------- #
    def scan(self) -> tuple[list[str], bool]:
        """Return the slugs whose signature moved and whether the library changed."""
        slugs = library(self.projects_dir)
        library_changed = self._library is not None and slugs != self._library
        self._library = slugs
        changed = []
        for slug in slugs:
            current = signature(self.projects_dir / slug)
            previous = self._known.get(slug)
            self._known[slug] = current
            if previous is not None and previous != current:
                changed.append(slug)
        for slug in list(self._known):
            if slug not in slugs:
                del self._known[slug]
        return changed, library_changed

    def absorb(self, slug: str) -> None:
        """Re-snapshot after a change the Studio already announced itself."""
        root = self.projects_dir / slug
        if (root / "project.json").is_file():
            self._known[slug] = signature(root)

    def reset(self) -> None:
        """Forget every snapshot; the next scan only records a baseline."""
        self._known.clear()
        self._library = None

    # -- loop ------------------------------------------------------------ #
    async def _loop(self) -> None:
        idle = True
        while True:
            await asyncio.sleep(self.interval)
            if self.bus.subscriber_count == 0:
                # Nobody listens: drop the baseline so a stale snapshot can't fire
                # a burst of reloads when the first tab connects again.
                if not idle:
                    self.reset()
                    idle = True
                continue
            idle = False
            try:
                changed, library_changed = await asyncio.to_thread(self.scan)
            except Exception:  # noqa: BLE001 - a watcher must never take the app down
                logger.exception("project watcher scan failed")
                continue
            for slug in changed:
                self.bus.publish("project.changed", {"project": slug, "source": "disk"})
            if library_changed:
                self.bus.publish("library.changed", {"source": "disk"})

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.ensure_future(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
