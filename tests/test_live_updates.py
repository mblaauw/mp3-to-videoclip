"""Live updates: the event bus, job progress, change notices and the watcher.

The browser reloads a view only when it hears about a change. These tests pin
the four ways a change is announced and the guard that keeps reads from
announcing anything (a read that writes would reload the page forever).
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest
from api_support import add_assets, api_client, make_api_project

from mp3_to_videoclip import operations
from mp3_to_videoclip.jobs.events import EventBus
from mp3_to_videoclip.jobs.runner import JobRunner
from mp3_to_videoclip.jobs.watch import ProjectWatcher, signature
from mp3_to_videoclip.storage import project_lock, read_json, write_json


def _drain(queue) -> list[dict]:
    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return items


# -- the bus ---------------------------------------------------------------- #
def test_a_publish_from_a_worker_thread_wakes_the_stream():
    async def scenario():
        bus = EventBus()
        bus.bind()
        queue = bus.subscribe()
        thread = threading.Thread(target=bus.publish, args=("job.progress", {"done": 1}))
        thread.start()
        # A plain cross-thread put_nowait would not wake a coroutine blocked in
        # get(); the bus hands off-loop publishes to the loop instead.
        message = await asyncio.wait_for(queue.get(), timeout=2)
        thread.join()
        assert message["event"] == "job.progress"
        assert message["payload"] == {"done": 1}
        assert message["id"] >= 1

    asyncio.run(scenario())


def test_a_stalled_subscriber_keeps_only_the_newest_events():
    async def scenario():
        bus = EventBus(max_queued=3)
        bus.bind()
        queue = bus.subscribe()
        for index in range(10):
            bus.publish("tick", {"n": index})
        assert [item["payload"]["n"] for item in _drain(queue)] == [7, 8, 9]
        bus.unsubscribe(queue)
        assert bus.subscriber_count == 0

    asyncio.run(scenario())


# -- the runner ------------------------------------------------------------- #
def test_engine_progress_streams_from_the_worker_thread_and_ends_with_a_change():
    async def scenario():
        runner = JobRunner()
        await runner.start()
        queue = runner.bus.subscribe()

        def engine():
            operations.phase("submitting-images", total=3, unit="images", done=0)
            for done in (1, 2, 3):
                operations.tick(phase="receiving-images", done=done, total=3, unit="images")
            return {"ok": True}

        async def work():
            return await asyncio.to_thread(engine)

        job_id = runner.submit("images", "film-a", work)
        for _ in range(200):
            if runner.get(job_id).status == "succeeded":
                break
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)
        events = _drain(queue)
        await runner.stop()

        job = runner.get(job_id)
        assert job.status == "succeeded"
        assert job.progress["done"] == 3 and job.progress["total"] == 3
        assert job.progress["phase"] == "receiving-images"
        names = [item["event"] for item in events]
        assert names[0] == "job.queued" and "job.succeeded" in names
        # Every job event names its film so the browser knows what to reload.
        for item in events:
            if item["event"].startswith("job."):
                assert item["payload"]["project"] == "film-a"
                assert item["payload"]["kind"] == "images"
        progress = [
            item["payload"]["progress"]["done"]
            for item in events
            if item["event"] == "job.progress"
        ]
        assert progress[-1] == 3
        changes = [item for item in events if item["event"] == "project.changed"]
        # One per finished still after the first, and one when the job ends.
        assert len(changes) >= 3
        assert all(item["payload"]["project"] == "film-a" for item in changes)

    asyncio.run(scenario())


def test_a_failed_job_still_announces_the_change_and_its_film():
    async def scenario():
        runner = JobRunner()
        await runner.start()
        queue = runner.bus.subscribe()

        async def work():
            raise ValueError("renderer exploded")

        job_id = runner.submit("render", "film-b", work)
        for _ in range(200):
            if runner.get(job_id).status == "failed":
                break
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.02)
        events = _drain(queue)
        await runner.stop()
        failed = next(item for item in events if item["event"] == "job.failed")
        assert failed["payload"] == {
            "job_id": job_id,
            "kind": "render",
            "project": "film-b",
            "error": "renderer exploded",
        }
        assert any(item["event"] == "project.changed" for item in events)

    asyncio.run(scenario())


def test_an_observer_error_never_breaks_the_work():
    def broken(_event, _data):
        raise RuntimeError("monitor bug")

    token = operations.observe(broken)
    try:
        operations.tick(done=1, total=2)
        operations.phase("rendering", done=0)
    finally:
        operations.unobserve(token)


# -- request notices -------------------------------------------------------- #
def test_a_saved_write_announces_the_film_and_a_read_does_not(tmp_path):
    make_api_project(tmp_path)
    with api_client(tmp_path) as client:
        bus = client.app.state.runner.bus
        queue = bus.subscribe()
        assert client.get("/api/projects/production/brief").status_code == 200
        time.sleep(0.05)
        assert not [item for item in _drain(queue) if item["event"] == "project.changed"]

        brief = client.get("/api/projects/production/brief").json()
        saved = client.patch(
            "/api/projects/production/brief",
            json={"treatment": (brief.get("treatment") or "") + " A new beat."},
        )
        assert saved.status_code == 200, saved.text
        time.sleep(0.05)
        changes = [item for item in _drain(queue) if item["event"] == "project.changed"]
        assert changes and changes[0]["payload"]["project"] == "production"

        rejected = client.post("/api/projects/production/approvals/brief", json={})
        assert rejected.status_code >= 400
        time.sleep(0.05)
        assert not [item for item in _drain(queue) if item["event"] == "project.changed"]
        bus.unsubscribe(queue)


def test_a_busy_production_is_a_clear_409(tmp_path):
    root = make_api_project(tmp_path)
    with api_client(tmp_path) as client:
        brief = next(
            item
            for item in client.get("/api/projects/production/approvals").json()["stages"]
            if item["stage"] == "brief"
        )
        with project_lock(root):
            response = client.post(
                "/api/projects/production/approvals/brief",
                json={"expected_hash": brief["expected_hash"], "note": "", "confirmed": True},
            )
        assert response.status_code == 409
        assert response.json()["code"] == "project_busy"


# -- the watcher -------------------------------------------------------------- #
def test_the_watcher_notices_outside_writes_and_ignores_temporaries(tmp_path):
    root = make_api_project(tmp_path)
    bus = EventBus()
    watcher = ProjectWatcher(tmp_path, bus)
    assert watcher.scan() == ([], False)  # baseline only

    (root / "work" / ".write-tmp").write_text("partial")
    (root / "previews").mkdir(exist_ok=True)
    (root / "previews" / ".film.progress.json").write_text("{}")
    assert watcher.scan() == ([], False)

    brief = read_json(root / "brief.json")
    brief["treatment"] = (brief.get("treatment") or "") + " Changed by the CLI."
    write_json(root / "brief.json", brief)
    assert watcher.scan() == (["production"], False)

    write_json(root / "brief.json", {**brief, "treatment": "Changed by the Studio."})
    watcher.absorb("production")
    assert watcher.scan() == ([], False)

    make_api_project(tmp_path, name="second")
    assert watcher.scan() == ([], True)


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/brief",
        "/intake",
        "/storyboard",
        "/track",
        "/music-notes",
        "/treatments",
        "/images",
        "/graphics-review",
        "/preview",
        "/edit",
        "/edit/summary",
        "/film/checklist",
        "/exports",
        "/budget",
        "/chat",
        "/approvals",
        "/approvals/brief/changes",
        "/ratings?artifact=brief",
    ],
)
def test_reads_never_change_what_the_watcher_sees(tmp_path, path):
    """A read that writes would reload every open view in an endless loop."""
    root = make_api_project(tmp_path)
    add_assets(root)
    with api_client(tmp_path) as client:
        client.get(f"/api/projects/production{path}")  # warm any one-time cache
        before = signature(root)
        response = client.get(f"/api/projects/production{path}")
        assert response.status_code < 500, response.text
        assert signature(root) == before
