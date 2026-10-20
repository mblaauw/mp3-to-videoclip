"""Live layer, operation import and the capability registry."""

import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from test_creative_production import make_root

from mp3_to_videoclip import serve, spine, studio, tools
from mp3_to_videoclip.cli import execute, parser
from mp3_to_videoclip.storage import write_json


def write_operation(root: Path, operation_id: str, **overrides):
    record = {
        "id": operation_id,
        "command": "render",
        "scope": "base-only",
        "status": "succeeded",
        "phase": "verifying-output",
        "started_at": "2026-10-20T10:00:00+00:00",
        "heartbeat_at": "2026-10-20T10:09:00+00:00",
        "ended_at": "2026-10-20T10:09:00+00:00",
        "owner": {"pid": 1, "host": "test"},
        "expected_outputs": ["renders/base.mp4"],
        "outputs": [{"path": "renders/base.mp4", "missing": True}],
        "progress": {"done": 5517, "total": 5517, "unit": "frames"},
    }
    record.update(overrides)
    write_json(root / "work/operations" / f"{operation_id}.json", record)
    return record


def test_sync_imports_operation_receipts_once(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    root = make_root(projects)
    write_operation(root, "op-20261020T100000-aaaaaa")
    write_operation(root, "op-20261020T110000-bbbbbb", status="failed", error="mux failed")
    (root / "work/operations/broken.json").write_text("{not json")

    with spine.connect(tmp_path / "spine.sqlite3") as conn:
        first = spine.sync_operations(conn, projects)
        assert first["imported"] == 2 and first["skipped"] == 1
        second = spine.sync_operations(conn, projects)
        assert second["imported"] == 0 and second["skipped"] == 3
        runs = spine.run_list(conn)
        assert {runs[0]["production"], runs[1]["production"]} == {root.name}
        statuses = sorted(r["status"] for r in runs)
        assert statuses == ["failed", "succeeded"]
        assert any(
            event["type"] == "operations.imported"
            for event in spine.event_list(conn, runs[0]["id"])
        )


def test_sync_keeps_receipts_as_the_writers(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    root = make_root(projects)
    receipt = write_operation(root, "op-20261020T120000-cccccc")
    before = json.dumps(receipt, sort_keys=True)
    with spine.connect(tmp_path / "spine.sqlite3") as conn:
        spine.sync_operations(conn, projects)
    after = (root / "work/operations" / "op-20261020T120000-cccccc.json").read_text()
    assert json.loads(after) == json.loads(before)


# --------------------------------------------------------------------------- #
# live layer
# --------------------------------------------------------------------------- #
def get(url, *, token=None, method="GET"):
    request = urllib.request.Request(url, method=method)
    if token:
        request.add_header("X-Studio-Token", token)
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, response.read(), response.headers


def test_live_server_is_read_only_and_token_scoped(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    make_root(projects)
    db = tmp_path / "spine.sqlite3"
    with spine.connect(db) as conn:
        spine.start_run(conn, intent="preview", production="production")
    httpd, url, _thread = serve.start_in_thread(projects, db, token="secret")
    try:
        base = url.split("?")[0]
        status, body, _ = get(base + "api/health")
        assert status == 200 and json.loads(body)["read_only"] is True

        with pytest.raises(urllib.error.HTTPError) as denied:
            get(base + "api/status")
        assert denied.value.code == 401

        status, body, _ = get(base + "api/status", token="secret")
        assert status == 200 and json.loads(body)["runs"] == {"running": 1}

        status, body, _ = get(base + "api/runs", token="secret")
        assert json.loads(body)["runs"][0]["intent"] == "preview"

        status, body, _ = get(base + "api/studio", token="secret")
        assert len(json.loads(body)["productions"]) == 1

        status, body, _ = get(base + "api/events", token="secret")
        events = json.loads(body)["events"]
        assert [event["type"] for event in events] == ["run.started"]

        with pytest.raises(urllib.error.HTTPError) as rejected:
            get(base + "api/runs", token="secret", method="POST")
        assert rejected.value.code == 405
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_live_page_is_self_contained(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    make_root(projects)
    httpd, url, _thread = serve.start_in_thread(projects, tmp_path / "spine.sqlite3", token="t")
    try:
        base = url.split("?")[0]
        status, body, headers = get(base + "?token=t")
        assert status == 200
        page = body.decode()
        assert "Studio · live" in page
        assert "http://" not in page.replace("http://127.0.0.1", "")
        assert "EventSource" in page
        assert "cannot approve" in page
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_studio_scan_is_shared_with_the_page(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    make_root(projects)
    entries = studio.scan(projects)
    assert entries and entries[0]["actions"]


# --------------------------------------------------------------------------- #
# capability registry
# --------------------------------------------------------------------------- #
def test_every_command_is_classified():
    assert tools.unclassified() == []
    described = {item["tool"] for item in tools.describe()}
    assert {"status", "approve", "generate", "shot-edit", "serve"} <= described


def test_scopes_split_read_derive_edit_spend_and_human():
    assert tools.scope_for("status")["kind"] == "read"
    assert tools.scope_for("dashboard")["kind"] == "derive"
    assert tools.scope_for("shot-edit")["kind"] == "edit"
    assert tools.scope_for("generate")["kind"] == "spend"
    for decision in ("approve", "authorize", "resolve-task"):
        assert tools.scope_for(decision)["kind"] == "human"


def test_agent_defaults_cannot_edit_spend_or_decide():
    tools.require("status")
    tools.require("dashboard")
    for dangerous in ("generate", "transcribe", "shot-edit"):
        with pytest.raises(PermissionError):
            tools.require(dangerous)
    for decision in ("approve", "authorize", "resolve-task"):
        with pytest.raises(PermissionError, match="human decision"):
            tools.require(decision, tools.DELEGATED_AGENT_KINDS)
    tools.require("shot-edit", tools.DELEGATED_AGENT_KINDS)


def test_classify_argv_and_unknown_command():
    assert tools.classify_argv(["uv", "run", "clip", "status", "projects/x"]) == "status"
    with pytest.raises(ValueError):
        tools.classify_argv(["node", "render.mjs"])
    with pytest.raises(ValueError, match="unclassified"):
        tools.scope_for("does-not-exist")


def test_cli_serve_resolves_the_journal_path(tmp_path, monkeypatch):
    """Regression: the serve branch must resolve the default spine path itself."""
    calls = {}
    monkeypatch.setattr(serve, "serve", lambda projects, db, **kw: calls.update(db=str(db), **kw))
    assert execute(parser().parse_args(["serve", "--projects-dir", str(tmp_path)])) is None
    assert calls["db"].endswith("studio/spine.sqlite3")
