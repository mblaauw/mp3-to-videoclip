"""Durable spine: idempotent replay, leases, events and honest reconciliation."""

import os
import subprocess
import sys
import time
from pathlib import Path

from mp3_to_videoclip import spine


def db(tmp_path):
    return tmp_path / "spine.sqlite3"


def test_run_command_records_a_replayable_journal(tmp_path):
    with spine.connect(db(tmp_path)) as conn:
        first = spine.run_command(
            conn,
            [sys.executable, "-c", "print('hello'); print('world')"],
            production="demo",
            intent="say hello",
            cwd=tmp_path,
        )
        assert first["returncode"] == 0 and first["replayed"] is False
        assert "hello" in first["output_tail"]

        events = spine.event_list(conn, first["run_id"])
        types = [event["type"] for event in events]
        assert types[0] == "run.started"
        assert "command.spawned" in types
        assert types.count("command.output") == 2
        assert types[-1] == "run.succeeded"

        second = spine.run_command(
            conn,
            [sys.executable, "-c", "print('hello'); print('world')"],
            production="demo",
            intent="say hello",
            cwd=tmp_path,
        )
        assert second["replayed"] is True and second["run_id"] == first["run_id"]
        # A replay must not spawn a second process or append a second output event.
        assert len(spine.event_list(conn, first["run_id"])) == len(events)


def test_events_are_append_only_and_ordered(tmp_path):
    with spine.connect(db(tmp_path)) as conn:
        run_id = spine.start_run(conn, intent="test", production="demo")
        spine.append_event(conn, run_id, "a")
        spine.append_event(conn, run_id, "b")
        seqs = [event["seq"] for event in spine.event_list(conn, run_id)]
        assert seqs == sorted(seqs)
        after = spine.event_list(conn, run_id, after=seqs[0])
        assert [event["type"] for event in after] == ["a", "b"]


def test_failed_command_is_step_and_run_failure(tmp_path):
    with spine.connect(db(tmp_path)) as conn:
        result = spine.run_command(
            conn, [sys.executable, "-c", "import sys; sys.exit(3)"], cwd=tmp_path
        )
        assert result["returncode"] == 3
        run = spine.run_list(conn)[0]
        assert run["status"] == "failed"
        assert run["steps"][0]["status"] == "failed"


def test_human_waits_are_durable_not_timeouts(tmp_path):
    with spine.connect(db(tmp_path)) as conn:
        run_id = spine.start_run(conn, intent="approve", production="demo")
        interrupt = spine.ask_human(conn, run_id, kind="approval", payload={"stage": "storyboard"})
        run = spine.run_list(conn)[0]
        assert run["status"] == "waiting" and run["open_interrupts"] == 1
        assert spine.status(conn)["open_interrupts"] == 1
        spine.resolve_human(conn, interrupt, resolution={"approved": True})
        assert spine.status(conn)["open_interrupts"] == 0
        types = [event["type"] for event in spine.event_list(conn, run_id)]
        assert "interrupt.opened" in types and "interrupt.resolved" in types


def test_reconcile_marks_dead_owners_interrupted_and_leaves_live_ones(tmp_path):
    with spine.connect(db(tmp_path)) as conn:
        dead = spine.start_run(conn, intent="render", production="demo", pid=_dead_pid())
        live = spine.start_run(conn, intent="preview", production="demo", pid=os.getpid())
        result = spine.reconcile(conn)
        assert [item["id"] for item in result["interrupted"]] == [dead]
        statuses = {run["id"]: run["status"] for run in spine.run_list(conn)}
        assert statuses[dead] == "interrupted"
        assert statuses[live] == "running"
        # Reconciliation records the outcome as evidence and never re-runs.
        assert any(event["type"] == "run.interrupted" for event in spine.event_list(conn, dead))


def test_overlong_output_is_truncated_in_events(tmp_path):
    script = "print('x' * 10); [print('line', i) for i in range(600)]"
    with spine.connect(db(tmp_path)) as conn:
        result = spine.run_command(conn, [sys.executable, "-c", script], cwd=tmp_path)
        assert result["lines"] > spine.MAX_OUTPUT_LINES
        events = [
            e
            for e in spine.event_list(conn, result["run_id"], limit=10_000)
            if e["type"] == "command.output"
        ]
        assert len(events) <= spine.MAX_OUTPUT_LINES


def test_status_reports_counts_and_is_disposable(tmp_path):
    path = db(tmp_path)
    with spine.connect(path) as conn:
        spine.start_run(conn, intent="test")
        assert spine.status(conn)["runs"] == {"running": 1}
    path.unlink()
    with spine.connect(path) as conn:
        assert spine.status(conn)["runs"] == {}


def test_run_command_validates_argv(tmp_path):
    with spine.connect(db(tmp_path)) as conn:
        for bad in ([], "echo hi", ["echo", 1]):
            try:
                spine.run_command(conn, bad)
            except ValueError:
                continue
            raise AssertionError(f"accepted invalid argv {bad!r}")


def _dead_pid() -> int:
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    time.sleep(0.05)
    return process.pid


def test_reconcile_never_touches_finished_runs(tmp_path):
    with spine.connect(db(tmp_path)) as conn:
        result = spine.run_command(conn, [sys.executable, "-c", "pass"], cwd=tmp_path)
        before = spine.run_list(conn)
        assert spine.reconcile(conn)["interrupted"] == []
        assert [run["status"] for run in before] == ["succeeded"]
        assert Path(result["run_id"]).name  # run id is a plain identifier
