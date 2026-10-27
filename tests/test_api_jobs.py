"""Job APIs explain stopping and read-only restart history."""

import asyncio
import threading

from api_support import api_client, make_api_project

from mp3_to_videoclip.jobs.runner import JobRunner


def test_cancel_api_reports_stopping_until_worker_drains(tmp_path):
    make_api_project(tmp_path)
    with api_client(tmp_path) as client:
        entered = threading.Event()
        release = threading.Event()

        def blocking():
            entered.set()
            assert release.wait(3)

        async def submit():
            async def work():
                await asyncio.to_thread(blocking)

            return client.app.state.runner.submit("images", "production", work, blocking=True)

        job = client.portal.call(submit)
        try:
            assert entered.wait(2)
            response = client.post(f"/api/jobs/{job}/cancel", json={})
            assert response.status_code == 200
            assert response.json() == {"cancelled": True, "status": "stopping"}
            detail = client.get(f"/api/jobs/{job}").json()
            assert detail["status"] == "stopping"
            assert detail["blocking"] is True
            assert detail["finished_at"] is None
            assert client.post(f"/api/jobs/{job}/cancel", json={}).status_code == 404
        finally:
            release.set()
    restored = JobRunner(projects_dir=tmp_path)
    assert restored.get(job).status == "cancelled"
    assert restored.get(job).historical


def test_restart_api_reports_interrupted_without_rewriting(tmp_path):
    root = make_api_project(tmp_path)
    old = JobRunner(projects_dir=tmp_path)

    async def never_run():
        raise AssertionError("no automatic retry")

    job = old.submit("images", "production", never_run)
    path = root / "work/jobs" / f"{job}.json"
    before = path.read_bytes()
    with api_client(tmp_path) as client:
        rows = client.get("/api/jobs?project=production").json()
        assert rows[0]["status"] == "interrupted"
        assert rows[0]["historical"] is True
        assert client.post(f"/api/jobs/{job}/cancel", json={}).status_code == 404
    assert path.read_bytes() == before
