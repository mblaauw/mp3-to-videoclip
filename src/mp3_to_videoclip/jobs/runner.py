"""In-process job runner: one asyncio queue, per-project serialisation.

Every job for the same project runs one at a time; different projects can
overlap. Blocking work runs in a thread pool. Records are in memory only and
start empty on each launch; cancelling a job marks it and suppresses its result,
but the current worker keeps running until it returns.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from .events import EventBus


@dataclass
class Job:
    id: str
    kind: str
    project: str
    status: str = "queued"  # queued/running/succeeded/failed/cancelled/needs_budget/interrupted
    progress: dict[str, Any] = field(default_factory=lambda: {"done": 0, "total": 0, "unit": ""})
    cost_usd: float = 0.0
    log: list[str] = field(default_factory=list)
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

    @property
    def bus(self) -> EventBus:
        return self._bus

    def submit(self, kind: str, project: str, coro_factory: Callable[[], Awaitable[Any]]) -> str:
        job_id = uuid.uuid4().hex[:12]
        job = Job(id=job_id, kind=kind, project=project)
        self._jobs[job_id] = job
        self._queue.put_nowait(job_id)
        # Store the factory for execution.
        self._factories[job_id] = coro_factory
        self._bus.publish("job.queued", {"job_id": job_id, "kind": kind, "project": project})
        return job_id

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list_jobs(self, project: str | None = None) -> list[Job]:
        jobs = list(self._jobs.values())
        if project is not None:
            jobs = [j for j in jobs if j.project == project]
        return sorted(jobs, key=lambda j: j.started_at or 0, reverse=True)

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None or job.status in ("succeeded", "failed", "cancelled"):
            return False
        job.status = "cancelled"
        self._bus.publish("job.cancelled", {"job_id": job_id})
        task = self._tasks.get(job_id)
        if task is not None and not task.done():
            task.cancel()
        return True

    async def start(self) -> None:
        self._task = asyncio.ensure_future(self._loop())

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

    async def _loop(self) -> None:
        while True:
            job_id = await self._queue.get()
            job = self._jobs.get(job_id)
            if job is None or job.status == "cancelled":
                continue
            # One task per admitted job; the per-project lock still serialises
            # that project while other projects (and a render beside images) run.
            task = asyncio.create_task(self._run(job))
            self._tasks[job.id] = task
            task.add_done_callback(lambda _task, job_id=job.id: self._tasks.pop(job_id, None))

    async def _run(self, job: Job) -> None:
        lock = self._project_locks.setdefault(job.project, asyncio.Lock())
        try:
            async with lock:
                if job.status == "cancelled":
                    return
                job.status = "running"
                job.started_at = time.time()
                self._bus.publish(
                    "job.started",
                    {"job_id": job.id, "kind": job.kind, "project": job.project},
                )
                factory = self._factories.pop(job.id, None)
                if factory is None:
                    raise ValueError("job factory is missing")
                result = await factory()
                if job.status == "cancelled":
                    return
                job.status = "succeeded"
                self._bus.publish("job.succeeded", {"job_id": job.id, "result": result})
        except asyncio.CancelledError:
            if job.status != "cancelled":
                job.status = "cancelled"
                self._bus.publish("job.cancelled", {"job_id": job.id})
            raise
        except Exception as exc:  # noqa: BLE001
            if job.status == "cancelled":
                return
            job.status = "failed"
            job.error = str(exc)
            self._bus.publish("job.failed", {"job_id": job.id, "error": str(exc)})
        finally:
            job.finished_at = time.time()
            self._factories.pop(job.id, None)

    def run_sync(self, func, *args, **kwargs):
        """Run a blocking function in the thread pool."""
        return self._executor.submit(func, *args, **kwargs)
