"""CLI monitoring and derivative registration: lock-free reads, honest adopt."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_creative_production import approve_through_proof, make_root

from mp3_to_videoclip import operations
from mp3_to_videoclip.cli import execute, parser
from mp3_to_videoclip.storage import file_hash, read_json, write_json


def hold_lock(root: Path):
    """Run a child process that holds the exclusive project lock for a while."""
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import time\n"
                "from pathlib import Path\n"
                "from mp3_to_videoclip.storage import project_lock\n"
                f"root = Path({str(root)!r})\n"
                "with project_lock(root):\n"
                "    print('LOCKED', flush=True)\n"
                "    time.sleep(8)\n"
            ),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert child.stdout.readline().strip() == "LOCKED"
    return child


@pytest.mark.parametrize(
    ("argv", "key"),
    [
        (["status"], "approvals"),
        (["progress"], "operations"),
        (["costs"], "currency"),
        (["dashboard"], "html"),
        (["studio", "--projects-dir"], "page"),
    ],
)
def test_monitoring_and_review_pages_work_while_a_writer_holds_the_lock(tmp_path, argv, key):
    root = make_root(tmp_path)
    child = hold_lock(root)
    try:
        # studio indexes the projects directory rather than one project.
        if argv[0] == "studio":
            args = parser().parse_args([*argv, str(tmp_path)])
        else:
            args = parser().parse_args([*argv, str(root)])
        result = execute(args)
        assert key in result
    finally:
        child.terminate()
        child.wait(timeout=10)


def test_a_writing_command_still_refuses_a_concurrent_writer(tmp_path):
    root = make_root(tmp_path)
    child = hold_lock(root)
    try:
        with pytest.raises(ValueError, match="another command is writing this project"):
            execute(parser().parse_args(["restage", str(root), "--shots", "s001", "--note", "x"]))
    finally:
        child.terminate()
        child.wait(timeout=10)


def test_progress_reports_attention_without_authorising_a_retry(tmp_path):
    root = make_root(tmp_path)
    (root / "work/operations").mkdir(parents=True, exist_ok=True)
    write_json(
        root / "work/operations/op-abandoned.json",
        {
            "id": "op-abandoned",
            "command": "render",
            "scope": "base-only",
            "status": "running",
            "phase": "rendering-visuals",
            "started_at": "2026-01-01T00:00:00+00:00",
            "heartbeat_at": "2026-01-01T00:00:00+00:00",
            "owner": {"pid": 999_999_999},
            "progress": {"done": 5, "total": 10, "unit": "frames"},
            "expected_outputs": ["renders/base.mp4"],
        },
    )
    first = execute(parser().parse_args(["progress", str(root)]))
    assert first["operations"][0]["status"] == "running"
    assert first["operations"][0]["quiet"] is True
    assert first["operations"][0]["fraction"] == 0.5
    assert "never re-submit automatically" in first["needs_attention"][0]["reason"]
    assert "Completion is not approval" in first["note"]

    reconciled = execute(parser().parse_args(["progress", str(root), "--reconcile"]))
    assert [entry["id"] for entry in reconciled["reconciled"]["interrupted"]] == ["op-abandoned"]
    assert reconciled["operations"][0]["status"] == "interrupted"
    assert reconciled["operations"][0]["outputs"] == [{"path": "renders/base.mp4", "missing": True}]


def test_status_summarises_operations_without_claiming_anything_else(tmp_path):
    root = make_root(tmp_path)
    summary = execute(parser().parse_args(["status", str(root)]))["operations"]
    assert summary["counts"] == {}
    assert summary["newest_running"] is None
    assert summary["unreadable"] == 0


def write_png(path: Path, size=(1376, 768), colour=(30, 40, 60)):
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, colour).save(path)
    return path


def test_adopt_records_a_version_and_provenance_without_selecting_or_approving(tmp_path):
    root = make_root(tmp_path)
    approve_through_proof(root)
    candidate = write_png(tmp_path / "candidates" / "crash.png")
    before = read_json(root / "work/assets.json")

    receipt = execute(
        parser().parse_args(
            [
                "adopt",
                str(root),
                "--shot",
                "s001",
                "--source",
                str(candidate),
                "--operation",
                "native crop 0,90,984,732",
                "--note",
                "remove bottom matte; no resampling",
                "--from-version",
                "1",
                "--permission-confirmed",
            ]
        )
    )
    assert receipt["version"] == 2 and receipt["selected"] is False and receipt["reviewed"] is False
    assert receipt["sha256"] == file_hash(Path(root) / receipt["path"])
    assert receipt["dimensions"] == [1376, 768]
    assert receipt["source"]["sha256"] == file_hash(candidate)
    assert receipt["from_version"] == 1
    assert "Recording a version is not inspection" in receipt["warning"]
    assert any("clip review" in step for step in receipt["next_steps"])

    assets = read_json(root / "work/assets.json")
    assert assets["s001"]["selected"] == before["s001"]["selected"]
    assert [v["version"] for v in assets["s001"]["versions"]] == [1, 2]
    assert assets["s001"]["versions"][1]["task_id"].startswith("local:")
    stored = read_json(root / "work/derivations/s001-v002.json")
    assert stored["sha256"] == receipt["sha256"]

    # The project file is not the image: the derived bytes must be identical.
    assert file_hash(Path(root) / receipt["path"]) == file_hash(candidate)


def test_adopt_refuses_unattested_duplicate_and_alias_targets(tmp_path):
    root = make_root(tmp_path)
    approve_through_proof(root)
    candidate = write_png(tmp_path / "candidates" / "one.png")
    common = [
        "adopt",
        str(root),
        "--shot",
        "s001",
        "--source",
        str(candidate),
        "--operation",
        "horizontal mirror",
        "--note",
        "direction fix",
    ]
    with pytest.raises(ValueError, match="permission-confirmed"):
        execute(parser().parse_args(common))
    with pytest.raises(ValueError, match="operation describing"):
        execute(parser().parse_args([*common, "--permission-confirmed", "--operation", "  "]))
    with pytest.raises(ValueError, match="why this derivative"):
        execute(parser().parse_args([*common, "--permission-confirmed", "--note", " "]))

    execute(parser().parse_args([*common, "--permission-confirmed"]))
    with pytest.raises(ValueError, match="already recorded"):
        execute(parser().parse_args([*common, "--permission-confirmed"]))
    with pytest.raises(ValueError, match="no version 9"):
        execute(parser().parse_args([*common, "--permission-confirmed", "--from-version", "9"]))

    board = read_json(root / "work/storyboard.json")
    alias = board["shots"][0]["id"]
    board["shots"][1]["asset_shot_id"] = alias
    write_json(root / "work/storyboard.json", board)
    with pytest.raises(ValueError, match="reprise"):
        execute(
            parser().parse_args(
                [
                    "adopt",
                    str(root),
                    "--shot",
                    board["shots"][1]["id"],
                    "--source",
                    str(candidate),
                    "--operation",
                    "horizontal mirror",
                    "--note",
                    "direction fix",
                    "--permission-confirmed",
                ]
            )
        )


def test_adopt_rejects_unknown_shot_and_unreadable_source(tmp_path):
    root = make_root(tmp_path)
    approve_through_proof(root)
    candidate = tmp_path / "candidates" / "broken.png"
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_bytes(b"not an image")
    with pytest.raises(ValueError, match="unknown shot"):
        execute(
            parser().parse_args(
                [
                    "adopt",
                    str(root),
                    "--shot",
                    "nope",
                    "--source",
                    str(candidate),
                    "--operation",
                    "crop",
                    "--note",
                    "x",
                    "--permission-confirmed",
                ]
            )
        )
    with pytest.raises(ValueError):
        execute(
            parser().parse_args(
                [
                    "adopt",
                    str(root),
                    "--shot",
                    "s001",
                    "--source",
                    str(candidate),
                    "--operation",
                    "crop",
                    "--note",
                    "x",
                    "--permission-confirmed",
                ]
            )
        )


def test_render_command_records_an_operation_receipt(tmp_path, monkeypatch):
    """A real render is not run here; the receipt contract is exercised directly."""
    root = make_root(tmp_path)
    with operations.operation(
        root, "render", scope="base-only", expected_outputs=["renders/x.mp4"]
    ):
        operations.phase("rendering-visuals", total=10, unit="frames", done=0)
        operations.tick(done=10)
    receipts = sorted((root / "work/operations").glob("*.json"))
    assert len(receipts) == 1
    record = json.loads(receipts[0].read_text())
    assert record["command"] == "render" and record["status"] == "succeeded"
    assert record["outputs"] == [{"path": "renders/x.mp4", "missing": True}]
