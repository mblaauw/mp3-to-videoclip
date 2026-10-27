"""The in-process runner: one job at a time per project, cancellation, events."""

from __future__ import annotations

import asyncio
import threading

import pytest

from mp3_to_videoclip import operations
from mp3_to_videoclip.jobs.runner import JobRunner


def test_jobs_run_one_at_a_time_per_project():
    async def scenario():
        runner = JobRunner()
        await runner.start()
        order = []
        done = asyncio.Event()

        async def first():
            order.append("a-start")
            await asyncio.sleep(0.01)
            order.append("a-end")

        async def second():
            order.append("b-start")
            await asyncio.sleep(0.01)
            order.append("b-end")
            done.set()

        one = runner.submit("kind", "p1", first)
        two = runner.submit("other", "p1", second)
        await asyncio.wait_for(done.wait(), timeout=2)
        assert order == ["a-start", "a-end", "b-start", "b-end"]
        assert runner.get(one).status == "succeeded"
        assert runner.get(two).status == "succeeded"
        await runner.stop()

    asyncio.run(scenario())


def test_cancel_drains_thread_before_next_project_job_and_stops_admission():
    async def scenario():
        runner = JobRunner()
        await runner.start()
        entered = threading.Event()
        release = threading.Event()
        other = asyncio.Event()
        next_started = asyncio.Event()
        admitted = []

        def blocking():
            entered.set()
            assert release.wait(2)
            # The inflight result is recorded, but a second submission is refused.
            admitted.append("inflight-result")
            if not operations.stop_requested():
                admitted.append("new-paid-submission")

        async def work():
            await asyncio.to_thread(blocking)

        async def next_work():
            assert release.is_set()
            next_started.set()

        async def other_work():
            other.set()

        first = runner.submit("images", "p1", work, blocking=True)
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            assert runner.cancel(first)
            assert runner.get(first).status == "stopping"
            assert runner.get(first).finished_at is None
            runner.submit("images", "p1", next_work)
            queued = runner.submit("images", "p1", other_work)
            assert runner.cancel(queued)
            runner.submit("images", "p2", other_work)
            await asyncio.wait_for(other.wait(), 2)
            assert not next_started.is_set()
            assert runner.get(first).status == "stopping"
        finally:
            release.set()
        await asyncio.wait_for(next_started.wait(), 2)
        assert admitted == ["inflight-result"]
        assert runner.get(first).status == "cancelled"
        await runner.stop()

    asyncio.run(scenario())


@pytest.mark.parametrize("blocking", [False, True])
def test_queued_cancel_never_calls_factory(blocking):
    async def scenario():
        runner = JobRunner()
        calls = []

        async def work():
            calls.append(True)

        job = runner.submit("images", "p1", work, blocking=blocking)
        assert runner.cancel(job)
        await runner.start()
        await asyncio.sleep(0)
        await runner.stop()
        assert calls == []
        assert runner.get(job).status == "cancelled"

    asyncio.run(scenario())


def test_shutdown_and_outer_cancellation_wait_for_thread():
    async def scenario():
        runner = JobRunner()
        await runner.start()
        entered = threading.Event()
        release = threading.Event()
        drained = threading.Event()

        def blocking():
            entered.set()
            assert release.wait(2)
            drained.set()

        async def work():
            await asyncio.to_thread(blocking)

        job = runner.submit("images", "p1", work, blocking=True)
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            runner._tasks[job].cancel()
            await asyncio.sleep(0)
            stopping = asyncio.create_task(runner.stop())
            await asyncio.sleep(0)
            stopping.cancel()
            await asyncio.sleep(0)
            assert not stopping.done()
            assert runner.get(job).status == "stopping"
        finally:
            release.set()
        await asyncio.wait_for(stopping, 2)
        assert drained.is_set()
        assert runner.get(job).status == "cancelled"

    asyncio.run(scenario())


def test_blocking_failure_during_outer_cancellation_retains_error_and_ownership():
    async def scenario():
        runner = JobRunner()
        await runner.start()
        entered = asyncio.Event()
        release = asyncio.Event()
        finished = asyncio.Event()
        next_started = asyncio.Event()

        async def failing():
            entered.set()
            await release.wait()
            finished.set()
            raise RuntimeError("provider failed during stop")

        async def following():
            assert finished.is_set()
            next_started.set()

        job = runner.submit("images", "p1", failing, blocking=True)
        try:
            await asyncio.wait_for(entered.wait(), 2)
            outer = runner._tasks[job]
            assert runner.cancel(job)
            runner.submit("analysis", "p1", following)
            await asyncio.sleep(0)
            assert runner.get(job).status == "stopping"
            assert runner.get(job).finished_at is None
            assert not next_started.is_set()

            # Queue worker completion before outer cancellation, without yielding:
            # shield delivers cancellation when the failed worker is already done.
            release.set()
            outer.cancel()
            await asyncio.wait_for(next_started.wait(), 2)
            assert runner.get(job).status == "cancelled"
            assert runner.get(job).error == "provider failed during stop"
            assert runner.get(job).finished_at is not None
        finally:
            release.set()
            await runner.stop()

    asyncio.run(scenario())


@pytest.mark.parametrize("shutdown", [False, True])
def test_pure_async_infinite_await_cancels_and_drains_cleanup(shutdown):
    async def scenario():
        runner = JobRunner()
        await runner.start()
        entered = asyncio.Event()
        cleaned_up = asyncio.Event()
        next_started = asyncio.Event()

        async def infinite():
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                # Async cancellation cleanup still owns the project's slot.
                await asyncio.sleep(0)
                cleaned_up.set()

        async def following():
            assert cleaned_up.is_set()
            next_started.set()

        job = runner.submit("analysis", "p1", infinite)
        await asyncio.wait_for(entered.wait(), 2)
        assert not runner.get(job).blocking
        if shutdown:
            await asyncio.wait_for(runner.stop(), 2)
        else:
            runner.submit("analysis", "p1", following)
            assert runner.cancel(job)
            await asyncio.wait_for(next_started.wait(), 2)
            await asyncio.wait_for(runner.stop(), 2)
        assert cleaned_up.is_set()
        assert runner.get(job).status == "cancelled"
        assert runner.get(job).finished_at is not None

    asyncio.run(scenario())


def test_coroutine_cancelled_error_is_observed_and_releases_project():
    async def scenario():
        runner = JobRunner()
        await runner.start()
        done = asyncio.Event()

        async def cancelled():
            raise asyncio.CancelledError

        async def following():
            done.set()

        job = runner.submit("analysis", "p1", cancelled)
        runner.submit("analysis", "p1", following)
        await asyncio.wait_for(done.wait(), 2)
        assert runner.get(job).status == "cancelled"
        await runner.stop()

    asyncio.run(scenario())


def test_different_projects_can_overlap():
    async def scenario():
        runner = JobRunner()
        await runner.start()
        both = asyncio.Event()
        release = asyncio.Event()
        count = 0

        async def work():
            nonlocal count
            count += 1
            if count == 2:
                both.set()
            await release.wait()

        runner.submit("kind", "p1", work)
        runner.submit("kind", "p2", work)
        # Two projects run concurrently; a global lock would time out here.
        await asyncio.wait_for(both.wait(), timeout=2)
        release.set()
        await runner.stop()

    asyncio.run(scenario())


def test_cancel_marks_a_running_job_and_never_reports_success():
    async def scenario():
        runner = JobRunner()
        await runner.start()
        started = asyncio.Event()
        release = asyncio.Event()

        async def work():
            started.set()
            await release.wait()
            return "too late"

        job = runner.submit("kind", "p1", work)
        await asyncio.wait_for(started.wait(), timeout=2)
        assert runner.cancel(job) is True
        assert runner.get(job).status == "stopping"
        release.set()
        await asyncio.sleep(0.05)
        assert runner.get(job).status == "cancelled"
        assert runner.cancel(job) is False
        assert runner.cancel("missing") is False
        await runner.stop()

    asyncio.run(scenario())


def test_lifecycle_events_reach_subscribers():
    async def scenario():
        runner = JobRunner()
        queue = runner.bus.subscribe()
        await runner.start()
        done = asyncio.Event()

        async def work():
            done.set()
            return {"ok": True}

        runner.submit("kind", "p1", work)
        await asyncio.wait_for(done.wait(), timeout=2)
        await asyncio.sleep(0.02)
        events = []
        while not queue.empty():
            events.append(queue.get_nowait()["event"])
        assert events[:3] == ["job.queued", "job.started", "job.succeeded"]
        runner.bus.unsubscribe(queue)
        await runner.stop()

    asyncio.run(scenario())
