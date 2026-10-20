"""Durable operation receipts: lifecycle, quiet/interrupted reporting, safety."""

import os
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta

from mp3_to_videoclip import operations
from mp3_to_videoclip.storage import read_json, write_json


def test_operation_records_phases_progress_and_hashed_outputs(tmp_path):
    root = tmp_path / "film"
    root.mkdir()
    with operations.operation(
        root,
        "render",
        scope="base-only",
        expected_outputs=["renders/base.mp4"],
        next_action="inspect samples",
    ) as operation:
        operation.phase("rendering-visuals", total=100, unit="frames", done=0)
        operation.tick(done=40)
        (root / "renders").mkdir()
        (root / "renders/base.mp4").write_bytes(b"film")

    receipt = read_json(operation.path)
    assert receipt["status"] == "succeeded"
    assert receipt["command"] == "render" and receipt["scope"] == "base-only"
    assert [phase["name"] for phase in receipt["phases"]] == ["starting", "rendering-visuals"]
    assert receipt["progress"]["done"] == 40 and receipt["progress"]["total"] == 100
    assert receipt["outputs"][0]["bytes"] == 4 and len(receipt["outputs"][0]["sha256"]) == 64
    assert receipt["next_action"] == "inspect samples"
    assert receipt["ended_at"] is not None and receipt["error"] is None


def test_failure_is_recorded_and_reraised(tmp_path):
    root = tmp_path / "film"
    root.mkdir()
    with operations.operation(root, "preview") as operation:
        operation.phase("rendering")
        try:
            with operations.operation(root, "preview"):
                raise ValueError("renderer exploded")
        except ValueError:
            pass
    receipt = read_json(operation.path)
    assert receipt["status"] == "succeeded"  # nested call annotated the outer operation only
    assert len(list((root / "work/operations").glob("*.json"))) == 1

    try:
        with operations.operation(root, "render", scope="final") as failed:
            raise ValueError("mux failed")
    except ValueError:
        pass
    receipt = read_json(failed.path)
    assert receipt["status"] == "failed"
    assert receipt["error"] == "ValueError: mux failed"
    assert receipt["ended_at"] is not None


def test_nested_operation_annotates_only_the_active_receipt(tmp_path):
    root = tmp_path / "film"
    root.mkdir()
    with operations.operation(root, "preview") as outer:
        with operations.operation(root, "render", scope="base-only") as inner:
            assert inner is outer
    assert len(list((root / "work/operations").glob("*.json"))) == 1
    names = [phase["name"] for phase in read_json(outer.path)["phases"]]
    assert "render:base-only" in names


def test_tick_without_an_operation_is_a_noop(tmp_path):
    operations.tick(done=1, total=2, unit="frames")
    operations.phase("nothing-watching")
    assert operations.active() is None


def test_listing_is_read_only_and_reports_quiet_and_interrupted(tmp_path):
    root = tmp_path / "film"
    (root / "work/operations").mkdir(parents=True)
    old = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
    write_json(
        root / "work/operations/op-quiet.json",
        {
            "id": "op-quiet",
            "command": "render",
            "status": "running",
            "phase": "rendering-visuals",
            "started_at": old,
            "heartbeat_at": old,
            "owner": {"pid": os.getpid()},
            "progress": {"done": 10, "total": 100, "unit": "frames"},
        },
    )
    write_json(
        root / "work/operations/op-gone.json",
        {
            "id": "op-gone",
            "command": "preview",
            "status": "running",
            "phase": "rendering",
            "started_at": old,
            "heartbeat_at": old,
            "owner": {"pid": _dead_pid()},
        },
    )
    before = {path.name: path.read_bytes() for path in (root / "work/operations").glob("*.json")}

    snapshot = operations.list_operations(root)
    assert [entry["id"] for entry in snapshot["operations"]] == ["op-quiet", "op-gone"]
    quiet = next(entry for entry in snapshot["operations"] if entry["id"] == "op-quiet")
    assert quiet["quiet"] is True and quiet["fraction"] == 0.1
    assert quiet["owner_process_alive"] is True
    after = {entry.name: entry.read_bytes() for entry in (root / "work/operations").glob("*.json")}
    assert after == before

    reconciled = operations.reconcile(root)
    assert [entry["id"] for entry in reconciled["interrupted"]] == ["op-gone"]
    assert [entry["id"] for entry in reconciled["left_running"]] == ["op-quiet"]
    gone = read_json(root / "work/operations/op-gone.json")
    assert gone["status"] == "interrupted" and gone["reconciled_at"]
    assert "never re-submits" in gone["reconcile_note"]
    # An alive owner is never rewritten, and reconciliation never deletes a receipt.
    assert read_json(root / "work/operations/op-quiet.json")["status"] == "running"
    assert len(list((root / "work/operations").glob("*.json"))) == 2


def test_summary_and_report_flag_attention_without_authorising_retries(tmp_path):
    root = tmp_path / "film"
    (root / "work/operations").mkdir(parents=True)
    write_json(
        root / "work/operations/op-doomed.json",
        {
            "id": "op-doomed",
            "command": "generate",
            "status": "failed",
            "error": "http_error",
            "started_at": datetime.now(UTC).isoformat(),
            "heartbeat_at": datetime.now(UTC).isoformat(),
        },
    )
    write_json(root / "work/operations/broken.json", {"not": "a receipt"})
    (root / "work/operations/corrupt.json").write_text("{not json")

    summary = operations.summary(root)
    assert summary["counts"] == {"failed": 1}
    assert summary["unreadable"] == 2
    assert "Completion is not approval" in summary["note"]

    payload = operations.report(root, running_only=True)
    assert payload["operations"] == []

    everything = operations.report(root)
    assert [entry["status"] for entry in everything["operations"]] == ["failed"]
    assert everything["needs_attention"][0]["reason"] == "http_error"


def test_progress_survives_a_long_operation_in_another_process(tmp_path):
    """The receipt is readable while a writer holds the project lock."""
    root = tmp_path / "film"
    root.mkdir()
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import sys, time\n"
                "from pathlib import Path\n"
                "from mp3_to_videoclip import operations\n"
                "from mp3_to_videoclip.storage import project_lock\n"
                f"root = Path({str(root)!r})\n"
                "with project_lock(root):\n"
                "    with operations.operation(root, 'render', scope='base-only') as op:\n"
                "        op.phase('rendering-visuals', total=10, unit='frames', done=3)\n"
                "        print('READY', flush=True)\n"
                "        time.sleep(5)\n"
            ),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdout.readline().strip() == "READY"
        snapshot = operations.list_operations(root)
        running = snapshot["operations"][0]
        assert running["status"] == "running" and running["phase"] == "rendering-visuals"
        assert running["progress"]["done"] == 3 and running["owner_process_alive"] is True
    finally:
        child.terminate()
        child.wait(timeout=10)


def test_operation_receipt_write_never_breaks_the_observed_work(tmp_path, monkeypatch):
    """A receipt failure is swallowed; the render it observes must still finish."""
    root = tmp_path / "film"
    root.mkdir()

    def explode(*args, **kwargs):
        raise OSError("receipt disk full")

    monkeypatch.setattr(operations, "write_json", explode)
    with operations.operation(root, "render") as operation:
        operation.phase("rendering")  # swallowed internally
        operations.tick(done=1)
    assert operations.active() is None
    assert operation.record["status"] == "succeeded"  # in-memory truth survives persistence failure


def _dead_pid() -> int:
    """A PID that has certainly exited: spawn and reap a short-lived process."""
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    time.sleep(0.05)
    return process.pid


def test_reconcile_leaves_unknown_owner_receipts_alone(tmp_path):
    root = tmp_path / "film"
    (root / "work/operations").mkdir(parents=True)
    write_json(
        root / "work/operations/op-ownerless.json",
        {
            "id": "op-ownerless",
            "command": "render",
            "status": "running",
            "started_at": datetime.now(UTC).isoformat(),
        },
    )
    result = operations.reconcile(root)
    assert result["interrupted"] == []
    assert result["left_running"][0]["owner_process_alive"] is None
    assert read_json(root / "work/operations/op-ownerless.json")["status"] == "running"


def test_operations_directory_is_absent_until_something_runs(tmp_path):
    root = tmp_path / "film"
    root.mkdir()
    assert not (root / "work/operations").exists()
    assert operations.list_operations(root)["operations"] == []
    assert not (root / "work/operations").exists()
