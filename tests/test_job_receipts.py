"""Lifecycle history is durable monitoring, never an automatic retry queue."""

import asyncio
import json

import pytest

from mp3_to_videoclip.jobs.runner import JobRunner
from mp3_to_videoclip.storage import write_json


def project(tmp_path, name="film", schema=3):
    root = tmp_path / name
    root.mkdir()
    write_json(root / "project.json", {"schema_version": schema})
    return root


def test_restart_loads_completed_and_interrupted_receipts_read_only(tmp_path):
    root = project(tmp_path)

    async def scenario():
        runner = JobRunner(projects_dir=tmp_path)
        await runner.start()
        done = asyncio.Event()

        async def work():
            done.set()

        finished = runner.submit("analysis", "film", work)
        await asyncio.wait_for(done.wait(), 2)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await runner.stop()
        # A queued receipt models the process dying before it can execute.
        old = JobRunner(projects_dir=tmp_path)
        pending = old.submit("images", "film", work, blocking=True)
        before = {p.name: p.read_bytes() for p in (root / "work/jobs").glob("*.json")}
        restored = JobRunner(projects_dir=tmp_path)
        assert restored.get(finished).status == "succeeded"
        assert restored.get(pending).status == "interrupted"
        assert restored.get(pending).finished_at is None
        assert restored.get(pending).historical
        assert restored.get(pending).blocking is True
        assert not restored.cancel(pending)
        await restored.start()
        assert not restored._factories
        await restored.stop()
        assert before == {p.name: p.read_bytes() for p in (root / "work/jobs").glob("*.json")}

    asyncio.run(scenario())


def test_corrupt_receipts_do_not_break_history(tmp_path):
    root = project(tmp_path)
    receipts = root / "work/jobs"
    receipts.mkdir(parents=True)
    (receipts / "broken.json").write_text("{broken")
    for index, data in enumerate(([], {"status": "running"}, {"extra": True})):
        (receipts / f"bad-{index}.json").write_text(json.dumps(data))
    assert JobRunner(projects_dir=tmp_path).list_jobs() == []


def test_startup_and_submit_never_create_missing_or_archived_projects(tmp_path):
    root = project(tmp_path, "archive", 2)
    before = (root / "project.json").read_bytes()
    runner = JobRunner(projects_dir=tmp_path)

    async def unused():
        raise AssertionError("not executed")

    runner.submit("images", "missing", unused)
    runner.submit("images", "archive", unused)
    assert not (tmp_path / "missing").exists()
    assert list(root.iterdir()) == [root / "project.json"]
    assert (root / "project.json").read_bytes() == before
    for slug in ("../escape", "/absolute", "film/nested", ".", "", "UPPER", "a_b"):
        with pytest.raises(ValueError):
            runner.submit("images", slug, unused)


def test_receipts_do_not_follow_external_work_symlinks(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    root = project(projects)
    external = tmp_path / "external"
    external.mkdir()
    (root / "work").symlink_to(external, target_is_directory=True)
    runner = JobRunner(projects_dir=projects)

    async def unused():
        pass

    with pytest.raises(ValueError):
        runner.submit("images", "film", unused)
    assert list(external.iterdir()) == []
