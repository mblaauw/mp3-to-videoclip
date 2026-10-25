"""The in-process runner: one job at a time per project, cancellation, events."""

from __future__ import annotations

import asyncio

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
        assert runner.get(job).status == "cancelled"
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
