"""Delivery progress is scoped monitoring, not an overall completion estimate."""

import asyncio

import pytest

from mp3_to_videoclip import operations
from mp3_to_videoclip.jobs.runner import Job, JobRunner
from mp3_to_videoclip.storage import write_json


def test_nested_scope_survives_thread_and_restores_after_error():
    async def scenario():
        events = []
        token = operations.observe(lambda event, data: events.append(data))
        try:
            with operations.progress_scope(stage="base-render"):
                await asyncio.to_thread(operations.tick, done=100, total=100, unit="frames")
                try:
                    with operations.progress_scope(stage="graphics-review", part="intro"):
                        raise ValueError("test")
                except ValueError:
                    pass
                operations.phase("verifying-output")
            operations.phase("outside")
        finally:
            operations.unobserve(token)
        assert events[1]["stage"] == "base-render"
        assert events[1]["done"] == 100
        assert events[2]["stage"] == "graphics-review"
        assert events[3] == {"stage": "base-render", "phase": "verifying-output"}
        assert events[4] == {"phase": "outside"}

    asyncio.run(scenario())


def test_phase_stage_and_part_changes_reset_counters_without_throttling():
    async def scenario():
        runner = JobRunner()
        runner._loop = asyncio.get_running_loop()
        job = Job("abcdef123456", "render", "film", status="running")
        observe = runner._observer(job)
        observe(
            "tick",
            {
                "stage": "base-render",
                "phase": "rendering",
                "done": 100,
                "total": 100,
                "unit": "frames",
            },
        )
        observe("phase", {"stage": "graphics-review", "phase": "starting"})
        assert job.progress == {
            "done": 0,
            "total": 0,
            "unit": "",
            "phase": "starting",
            "stage": "graphics-review",
        }
        observe(
            "tick",
            {
                "stage": "final-composite",
                "part": "intro",
                "part_index": 1,
                "part_total": 2,
                "phase": "rendering",
                "done": 50,
                "total": 50,
                "unit": "frames",
            },
        )
        observe(
            "tick",
            {
                "stage": "final-composite",
                "part": "credits",
                "part_index": 2,
                "part_total": 2,
                "phase": "starting",
            },
        )
        assert job.progress["total"] == 0
        observe("phase", {"stage": "final-composite", "phase": "compositing"})
        assert "part" not in job.progress
        observe("phase", {"stage": "final-composite", "phase": "verifying-output"})
        assert job.progress["total"] == 0

    asyncio.run(scenario())


def test_render_purpose_is_persisted_and_restored_without_resume(tmp_path):
    root = tmp_path / "film"
    write_json(root / "project.json", {"schema_version": 3})
    runner = JobRunner(projects_dir=tmp_path)

    async def unused():
        raise AssertionError("must not resume")

    identity = runner.submit("render", "film", unused, blocking=True, render_kind="base")
    restored = JobRunner(projects_dir=tmp_path).get(identity)
    assert restored.render_kind == "base"
    assert restored.status == "interrupted"


def test_a_titles_check_is_a_render_job_that_survives_a_restart(tmp_path):
    root = tmp_path / "film"
    write_json(root / "project.json", {"schema_version": 3})
    runner = JobRunner(projects_dir=tmp_path)

    async def unused():
        raise AssertionError("must not resume")

    identity = runner.submit("render", "film", unused, blocking=True, render_kind="titles")
    assert JobRunner(projects_dir=tmp_path).get(identity).render_kind == "titles"
    with pytest.raises(ValueError, match="invalid render kind"):
        runner.submit("render", "film", unused, blocking=True, render_kind="trailer")
