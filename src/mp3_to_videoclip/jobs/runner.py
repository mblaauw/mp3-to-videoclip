"""In-process job runner: one asyncio queue, per-project serialisation.

Every job for the same project runs one at a time; different projects can
overlap. Async jobs receive task cancellation; explicitly blocking jobs stop
cooperatively, retaining ownership until the worker returns.
Optional per-project receipts are monitoring history, never a spending ledger.

Every event names its job, kind and project, so a browser can tell which film a
finished job changed. Progress reported by the engine through
:mod:`mp3_to_videoclip.operations` (images received, frames rendered) is
streamed as ``job.progress``; a job that changes a production also emits
``project.changed`` when it ends, and an image batch emits one per finished
still so the contact sheet fills in live.
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
import threading
import time
import uuid
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .. import operations, storage
from .events import EventBus

#: Minimum seconds between two ``job.progress`` events for one job.
PROGRESS_INTERVAL = 0.25
#: Job kinds whose intermediate progress means new artifacts on disk.
LIVE_ARTIFACT_KINDS = {"images": "images"}
ACTIVE = {"queued", "running", "stopping", "needs_budget"}
STATUSES = ACTIVE | {"succeeded", "failed", "cancelled", "interrupted"}
RECEIPTS = "work/jobs"
#: Render job kinds; ``titles`` renders the titles review stills.
RENDER_KINDS = (None, "preview", "titles", "base", "final")
logger = logging.getLogger(__name__)


@dataclass
class Job:
    id: str
    kind: str
    project: str
    status: str = "queued"
    progress: dict[str, Any] = field(
        default_factory=lambda: {"done": 0, "total": 0, "unit": "", "phase": ""}
    )
    cost_usd: float = 0.0
    log: list[str] = field(default_factory=list)
    queued_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None
    historical: bool = False
    blocking: bool = False
    render_kind: str | None = None


class JobRunner:
    def __init__(
        self,
        executor: ThreadPoolExecutor | None = None,
        bus: EventBus | None = None,
        projects_dir: Path | None = None,
    ):
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
        self._projects_dir = Path(projects_dir).resolve() if projects_dir is not None else None
        self._closing = False
        self._restore()

    def _project_root(self, project: str) -> Path | None:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", project):
            raise ValueError("invalid project id")
        if self._projects_dir is None:
            return None
        root = storage.inside(self._projects_dir, project)
        # Never create a production, follow an external work symlink or write an archive.
        metadata = storage.read_optional(root / "project.json")
        if not isinstance(metadata, dict) or metadata.get("schema_version") != 3:
            return None
        storage.inside(root, RECEIPTS)
        return root

    def _save(self, job: Job) -> None:
        if job.historical:
            return
        try:
            root = self._project_root(job.project)
            if root is not None:
                record = asdict(job)
                record.pop("log")  # no unbounded logs, results or financial journal copies
                storage.write_json(root / RECEIPTS / f"{job.id}.json", record)
        except (OSError, ValueError):
            logger.warning("Could not save job receipt %s", job.id, exc_info=True)

    def _restore(self) -> None:
        if self._projects_dir is None:
            return
        for path in self._projects_dir.glob(f"*/{RECEIPTS}/*.json"):
            try:
                project = path.parents[2].name
                root = self._project_root(project)
                if root is None or not path.resolve().is_relative_to(root):
                    continue
                data = storage.read_json(path)
                if not isinstance(data, dict):
                    continue
                job = Job(**data)
                if (
                    job.project != project
                    or not re.fullmatch(r"[a-f0-9]{12}", job.id)
                    or path.stem != job.id
                    or job.status not in STATUSES
                    or not isinstance(job.blocking, bool)
                    or not isinstance(job.kind, str)
                    or job.render_kind not in RENDER_KINDS
                    or not isinstance(job.progress, dict)
                    or any(
                        not isinstance(value, (int, float)) or not math.isfinite(value)
                        for value in (job.queued_at, job.cost_usd)
                    )
                    or any(
                        value is not None
                        and (not isinstance(value, (int, float)) or not math.isfinite(value))
                        for value in (job.started_at, job.finished_at)
                    )
                    or any(
                        not isinstance(job.progress.get(key, 0), int) for key in ("done", "total")
                    )
                    or any(
                        not isinstance(job.progress.get(key, ""), str) for key in ("unit", "phase")
                    )
                    or (job.error is not None and not isinstance(job.error, str))
                ):
                    continue
                job.historical = True
                if job.status in ACTIVE:
                    job.status = "interrupted"
                    job.error = "Previous runner ended before completion. Check artifacts and the task journal before retrying."
                    job.finished_at = None  # actual worker completion is unknown
                self._jobs[job.id] = job
            except (OSError, TypeError, ValueError):
                logger.warning("Ignoring unreadable job receipt %s", path)

    @property
    def bus(self) -> EventBus:
        return self._bus

    def _event(self, name: str, job: Job, **extra: Any) -> None:
        self._save(job)
        self._bus.publish(
            name,
            {
                "job_id": job.id,
                "kind": job.kind,
                "project": job.project,
                "render_kind": job.render_kind,
                **extra,
            },
        )

    def submit(
        self,
        kind: str,
        project: str,
        coro_factory: Callable[[], Awaitable[Any]],
        *,
        blocking: bool = False,
        render_kind: str | None = None,
    ) -> str:
        """Queue work, declaring whether cancellation can leave a blocking worker.

        Pure async factories are cancelled normally. Factories using to_thread,
        run_in_executor or another surviving worker MUST declare blocking=True
        and await all their workers before returning. Those factories receive a
        cooperative operations.stop_requested() signal instead of task.cancel().
        """
        if self._closing:
            raise RuntimeError("job runner is stopping")
        if not isinstance(blocking, bool):
            raise TypeError("blocking must be a bool")
        if render_kind not in RENDER_KINDS:
            raise ValueError("invalid render kind")
        self._project_root(project)
        job_id = uuid.uuid4().hex[:12]
        job = Job(id=job_id, kind=kind, project=project, blocking=blocking, render_kind=render_kind)
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
            key=lambda j: (j.status in ACTIVE, j.started_at or j.queued_at),
            reverse=True,
        )

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None or job.historical or job.status not in ("queued", "running", "needs_budget"):
            return False
        queued = job.status == "queued"
        job.status = "cancelled" if queued else "stopping"
        if queued:
            job.finished_at = time.time()
            self._factories.pop(job_id, None)
        stop = self._stops.get(job_id)
        if stop is not None:
            stop.set()  # ask the worker thread to admit nothing new
        self._event("job.cancelled" if queued else "job.stopping", job)
        if not queued and not job.blocking:
            task = self._tasks.get(job_id)
            if task is not None:
                task.cancel()
        return True

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._bus.bind(self._loop)
        self._task = asyncio.ensure_future(self._loop_forever())

    async def stop(self) -> None:
        self._closing = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        for job in list(self._jobs.values()):
            self.cancel(job.id)
        tasks = list(self._tasks.values())
        if tasks:
            drain = asyncio.gather(*tasks, return_exceptions=True)
            while not drain.done():
                try:
                    await asyncio.shield(drain)
                except asyncio.CancelledError:
                    # Shutdown cancellation cannot orphan an inflight blocking worker.
                    continue
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
            task.add_done_callback(lambda task, job_id=job.id: self._completed(job_id, task))

    def _completed(self, job_id: str, task: asyncio.Task) -> None:
        self._tasks.pop(job_id, None)
        if not task.cancelled():
            error = task.exception()
            if error is not None:
                logger.error("Job task %s failed: %s", job_id, error)

    # -- progress ---------------------------------------------------------- #
    def _observer(self, job: Job) -> Callable[[str, dict], None]:
        """Build the engine-progress listener for one job (called from threads)."""
        last = {"at": 0.0, "done": None}
        artifact = LIVE_ARTIFACT_KINDS.get(job.kind)
        loop = self._loop

        def apply(data: dict) -> None:
            if job.status not in ("running", "stopping"):
                return
            progress = dict(job.progress)
            changed_scope = any(
                key in data and data[key] != progress.get(key)
                for key in ("stage", "part", "part_index", "phase")
            )
            if changed_scope:
                progress.update(done=0, total=0, unit="")
                progress.pop("message", None)
                if (
                    "stage" in data and data["stage"] != progress.get("stage")
                ) or "part" not in data:
                    for key in ("part", "part_index", "part_total"):
                        progress.pop(key, None)
            for key in (
                "done",
                "total",
                "unit",
                "phase",
                "stage",
                "part",
                "part_index",
                "part_total",
            ):
                if key in data and data[key] is not None:
                    progress[key] = data[key]
            if "message" in data:
                progress["message"] = str(data["message"])
            job.progress = progress
            now = time.monotonic()
            done_changed = progress.get("done") != last["done"]
            if not changed_scope and not done_changed and now - last["at"] < PROGRESS_INTERVAL:
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
                if job.blocking:
                    # A cancelled to_thread await does not mean its thread exited.
                    # Shield the complete declared-blocking factory and drain it.
                    worker = asyncio.ensure_future(factory())
                    worker.add_done_callback(self._observe_worker)
                    while True:
                        try:
                            result = await asyncio.shield(worker)
                            break
                        except asyncio.CancelledError:
                            self.cancel(job.id)
                            if worker.done():
                                # Cancellation and completion can arrive together.
                                # Preserve the worker's actual result or exception.
                                result = worker.result()
                                break
                else:
                    # Default async work retains normal task cancellation, including
                    # an infinite await. Its cleanup finishes while still owning lock.
                    result = await factory()
                job.finished_at = time.time()
                if job.status == "stopping":
                    job.status = "cancelled"
                    self._event("job.cancelled", job)
                else:
                    job.status = "succeeded"
                    self._event("job.succeeded", job, result=result)
        except asyncio.CancelledError:
            job.status = "cancelled"
            job.finished_at = time.time()
            self._event("job.cancelled", job)
        except Exception as exc:  # noqa: BLE001
            job.status = "cancelled" if job.status == "stopping" else "failed"
            job.error = str(exc)
            job.finished_at = time.time()
            self._event(
                "job.cancelled" if job.status == "cancelled" else "job.failed", job, error=str(exc)
            )
        finally:
            if token is not None:
                operations.unobserve(token)
            if stop_token is not None:
                operations.unwatch_stop(stop_token)
            self._stops.pop(job.id, None)
            job.finished_at = job.finished_at or time.time()
            self._factories.pop(job.id, None)
            self._save(job)
            if changed:
                # Whatever the outcome, the job may have written to the production
                # (a partial batch, a failed render's log); let open views reload.
                self._bus.publish(
                    "project.changed",
                    {"project": job.project, "artifact": job.kind, "source": "job"},
                )

    @staticmethod
    def _observe_worker(worker: asyncio.Future) -> None:
        # A simultaneous outer cancellation and worker failure must not leave an
        # unobserved exception, even if shield delivers cancellation first.
        if not worker.cancelled():
            worker.exception()
