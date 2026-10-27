"""In-memory pub/sub feeding the SSE stream.

``publish`` is safe from any thread. Job work runs in the thread pool (a paid
image batch, a render, an analysis pass) and now reports progress from there;
an ``asyncio.Queue`` is not thread-safe, and a ``put_nowait`` from a worker
thread does not wake a coroutine waiting in ``get()``. Off-loop publishes are
therefore handed to the owning loop with ``call_soon_threadsafe``.

Every subscriber queue is bounded: a stalled or abandoned browser tab drops its
oldest events instead of growing without limit. The browser reconciles by
reloading on reconnect, so a dropped event is never a lost state change.
"""

from __future__ import annotations

import asyncio
import itertools
import threading
from typing import Any

MAX_QUEUED = 512


class EventBus:
    def __init__(self, *, max_queued: int = MAX_QUEUED):
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = []
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._max = max_queued
        self._ids = itertools.count(1)

    # -- loop binding ------------------------------------------------------ #
    def bind(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Remember the loop that owns the subscriber queues."""
        self._loop = loop or asyncio.get_running_loop()

    def _owner(self) -> asyncio.AbstractEventLoop | None:
        if self._loop is not None and not self._loop.is_closed():
            return self._loop
        return None

    # -- subscribers ------------------------------------------------------- #
    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        if self._loop is None:
            try:
                self.bind()
            except RuntimeError:
                pass
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._max)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        with self._lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    # -- publishing -------------------------------------------------------- #
    def publish(self, event: str, payload: dict[str, Any] | None = None) -> None:
        message = {"id": next(self._ids), "event": event, "payload": payload or {}}
        loop = self._owner()
        if loop is None:
            self._deliver(message)
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            self._deliver(message)
        else:
            try:
                loop.call_soon_threadsafe(self._deliver, message)
            except RuntimeError:  # loop closed while shutting down
                pass

    def _deliver(self, message: dict[str, Any]) -> None:
        with self._lock:
            queues = list(self._subscribers)
        for q in queues:
            if q.full():
                try:
                    q.get_nowait()  # drop the oldest; the client resyncs on reconnect
                except asyncio.QueueEmpty:
                    pass
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                pass
