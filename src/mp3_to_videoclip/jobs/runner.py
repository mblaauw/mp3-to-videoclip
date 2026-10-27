"""In-process job runner: one asyncio queue, per-project serialisation.

Every job for the same project runs one at a time; different projects can
overlap. Blocking work runs in a thread pool. Records are in memory only and
start empty on each launch; cancelling a job marks it and suppresses its result,
but the current worker keeps running until it returns.

Every event names its job, kind and project, so a browser can tell which film a
finished job changed. Progress reported by the engine through
:mod:`mp3_to_videoclip.operations` (images received, frames rendered) is
streamed as ``job.progress``; a job that changes a production also emits
``project.changed`` when it ends, and an image batch emits one per finished
still so the contact sheet fills in live.
"""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from .. import operations
from .events import EventBus

#: Minimum seconds between two ``job.progress`` events for one job.
PROGRESS_INTERVAL = 0.25
#: Job kinds whose intermediate progress means new artifacts on disk.
LIVE_ARTIFACT_KINDS = {"images": "images"}


@dataclass
class Job:
    id: str
    kind: str
    project: str
    status: str = "queued"  # queued/running/succeeded/failed/cancelled/needs_budget/interrupted
    progress: dict[str, Any] = field(
        default_factory=lambda: {"done": 0, "total": 0, "unit": "", "phase": ""}
    )
    cost_usd: float = 0.0
    log: list[str] = field(default_factory=list)
    queued_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None


class JobRunner:
    def __init__(self, executor: ThreadPoolExecutor | None = None, bus: EventBus | None = None):
        self._executor = executor or ThreadPoolExecutor(max_workers=4)
        self._bus = bus or EventBus()
        self._jobs: dict[str, Job] = {}
        self._factories: dict[str, Callable] = {}
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._project_locks: dict[str, asyncio.Lock] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stops: dict[str, threading.Event] = {}

    @property
    def bus(self) -> EventBus:
        return self._bus

    def _event(self, name: str, job: Job, **extra: Any) -> None:
        self._bus.publish(
            name, {"job_id": job.id, "kind": job.kind, "project": job.project, **extra}
        )

    def submit(self, kind: str, project: str, coro_factory: Callable[[], Awaitable[Any]]) -> str:
        job_id = uuid.uuid4().hex[:12]
        job = Job(id=job_id, kind=kind, project=project)
        self._jobs[job_id] = job
        # Store the factory before the id is queued so the loop always finds it.
        self._factories[job_id] = coro_factory
        self._queue.put_nowait(job_id)
        self._event("job.queued", job)
        return job_id

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list_jobs(self, project: str | None = None) -> list[Job]:
        jobs = list(self._jobs.values())
        if project is not None:
            jobs = [j for j in jobs if j.project == project]
        # Active work first, then the most recent; a queued job has no start yet.
        return sorted(
            jobs,
            key=lambda j: (j.status in ("queued", "running"), j.started_at or j.queued_at),
            reverse=True,
        )

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None or job.status in ("succeeded", "failed", "cancelled"):
            return False
        job.status = "cancelled"
        job.finished_at = job.finished_at or time.time()
        stop = self._stops.get(job_id)
        if stop is not None:
            stop.set()  # ask the worker thread to admit nothing new
        self._event("job.cancelled", job)
        task = self._tasks.get(job_id)
        if task is not None and not task.done():
            task.cancel()
        return True

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._bus.bind(self._loop)
        self._task = asyncio.ensure_future(self._loop_forever())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._executor.shutdown(wait=False)

    async def _loop_forever(self) -> None:
        while True:
            job_id = await self._queue.get()
            job = self._jobs.get(job_id)
            if job is None or job.status == "cancelled":
                self._factories.pop(job_id, None)
                continue
            # One task per admitted job; the per-project lock still serialises
            # that project while other projects (and a render beside images) run.
            task = asyncio.create_task(self._run(job))
            self._tasks[job.id] = task
            task.add_done_callback(lambda _task, job_id=job.id: self._tasks.pop(job_id, None))

    # -- progress ---------------------------------------------------------- #
    def _observer(self, job: Job) -> Callable[[str, dict], None]:
        """Build the engine-progress listener for one job (called from threads)."""
        last = {"at": 0.0, "done": None}
        artifact = LIVE_ARTIFACT_KINDS.get(job.kind)
        loop = self._loop

        def apply(data: dict) -> None:
            if job.status != "running":
                return
            progress = dict(job.progress)
            for key in ("done", "total", "unit", "phase"):
                if key in data and data[key] is not None:
                    progress[key] = data[key]
            if "message" in data:
                progress["message"] = str(data["message"])
            job.progress = progress
            now = time.monotonic()
            done_changed = progress.get("done") != last["done"]
            if not done_changed and now - last["at"] < PROGRESS_INTERVAL:
                return
            last["at"] = now
            previous, last["done"] = last["done"], progress.get("done")
            self._event("job.progress", job, progress=progress)
            if artifact and done_changed and previous is not None:
                self._bus.publish(
                    "project.changed",
                    {"project": job.project, "artifact": artifact, "source": "job"},
                )

        def observer(_event: str, data: dict) -> None:
            if loop is None or loop.is_closed():
                return
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is loop:
                apply(data)
            else:
                loop.call_soon_threadsafe(apply, data)

        return observer

    async def _run(self, job: Job) -> None:
        lock = self._project_locks.setdefault(job.project, asyncio.Lock())
        token = None
        stop_token = None
        changed = False
        try:
            async with lock:
                if job.status == "cancelled":
                    return
                job.status = "running"
                job.started_at = time.time()
                self._event("job.started", job)
                factory = self._factories.pop(job.id, None)
                if factory is None:
                    raise ValueError("job factory is missing")
                # ``asyncio.to_thread`` copies this context into the worker, so
                # engine ``operations.tick`` calls reach the observer.
                token = operations.observe(self._observer(job))
                stop = self._stops.setdefault(job.id, threading.Event())
                stop_token = operations.watch_stop(stop)
                changed = True
                result = await factory()
                if job.status == "cancelled":
                    return
                job.status = "succeeded"
                self._event("job.succeeded", job, result=result)
        except asyncio.CancelledError:
            if job.status != "cancelled":
                job.status = "cancelled"
                self._event("job.cancelled", job)
            raise
        except Exception as exc:  # noqa: BLE001
            if job.status == "cancelled":
                return
            job.status = "failed"
            job.error = str(exc)
            self._event("job.failed", job, error=str(exc))
        finally:
            if token is not None:
                operations.unobserve(token)
            if stop_token is not None:
                operations.unwatch_stop(stop_token)
            self._stops.pop(job.id, None)
            job.finished_at = job.finished_at or time.time()
            self._factories.pop(job.id, None)
            if changed:
                # Whatever the outcome, the job may have written to the production
                # (a partial batch, a failed render's log); let open views reload.
                self._bus.publish(
                    "project.changed",
                    {"project": job.project, "artifact": job.kind, "source": "job"},
                )

    def run_sync(self, func, *args, **kwargs):
        """Run a blocking function in the thread pool."""
        return self._executor.submit(func, *args, **kwargs)
