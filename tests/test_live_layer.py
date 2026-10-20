"""Live layer, operation import and the capability registry."""

import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from test_creative_production import jpeg, make_root, record_stills

from mp3_to_videoclip import appdata, serve, spine, studio, tools
from mp3_to_videoclip import production as P
from mp3_to_videoclip.cli import execute, parser
from mp3_to_videoclip.reviews import record_review
from mp3_to_videoclip.storage import read_json, write_json


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
# app projections: stills, board, approvals
# --------------------------------------------------------------------------- #
def test_stills_projection_uses_selected_version_and_exact_bytes(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    root = make_root(projects)
    record_stills(root, ["s001", "s002"])
    record_review(root, "s001", 1, "accept", note="clear", reviewer="test", inspected=True)
    write_json(
        root / "work/reviews.json",
        [
            *read_json(root / "work/reviews.json"),
            {
                "shot_id": "s002",
                "version": 1,
                "sha256": "0" * 64,
                "verdict": "reject",
                "note": "stale bytes",
            },
        ],
    )

    data = appdata.stills(root)
    rows = {row["id"]: row for row in data["shots"]}
    assets = read_json(root / "work/assets.json")
    assert rows["s001"]["version"] == 1
    assert rows["s001"]["verdict"] == "accept"
    assert rows["s001"]["sha256"] == assets["s001"]["versions"][0]["sha256"]
    assert rows["s001"]["seconds"] == 0.5 and rows["s001"]["framing"] == "wide"
    assert rows["s002"]["version"] == 1 and rows["s002"]["verdict"] is None
    assert rows["s003"]["version"] is None and rows["s003"]["verdict"] is None
    assert data["counts"] == {"accept": 1, "reject": 0, "uncertain": 0, "unreviewed": 3}

    status = P.status(root)
    assert [shot["id"] for shot in status["shots"]] == [row["id"] for row in data["shots"]]


def test_shot_detail_has_contract_and_compiled_prompt(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    root = make_root(projects)
    record_stills(root, ["s001"])

    detail = appdata.shot_detail(root, "s001")
    assert detail["contract"]["purpose"] == "Beat 0"
    assert detail["contract"]["must_show"] == ["a brass lamp"]
    assert detail["version"] == 1
    assert detail["prompt"] and "SHOT-s001 prompt" in detail["prompt"]
    assert detail["thumb"].endswith("/thumb/s001")
    with pytest.raises(LookupError):
        appdata.shot_detail(root, "missing")


def test_board_projection_has_timeline_and_bands(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    root = make_root(projects)
    write_json(
        root / "work/events.json",
        {
            "source_sha256": P.load_project(root).source_sha256,
            "fps": 24,
            "total_frames": 48,
            "events": [
                {
                    "id": "e001",
                    "frame": 0,
                    "end_frame": 24,
                    "kind": "section",
                    "label": "First measured band",
                    "timing_basis": "estimated",
                }
            ],
        },
    )

    data = appdata.board(root)
    assert data["available"] is True
    assert data["grid"]["enabled"] is False
    assert len(data["shots"]) == 4
    assert data["shots"][0]["start_frame"] == 0 and data["shots"][0]["end_frame"] == 12
    assert data["bands"][0]["id"] == "e001"
    assert data["bands"][0]["shot_ids"] == ["s001", "s002"]


def test_approvals_report_live_hash_and_stale_drift(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    root = make_root(projects)
    P.approve(root, "analysis", "test")

    data = appdata.approvals(root)
    analysis = next(stage for stage in data["stages"] if stage["stage"] == "analysis")
    assert analysis["state"] == "approved"
    assert analysis["would_pass_now"] is True
    assert analysis["hash"] == analysis["approved_hash"]

    write_json(root / "work/music.json", {"duration": 0.5, "beats": []})
    data = appdata.approvals(root)
    analysis = next(stage for stage in data["stages"] if stage["stage"] == "analysis")
    assert analysis["state"] == "stale"
    assert analysis["would_pass_now"] is False


def test_project_routes_and_thumbnail_are_read_only_and_guarded(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    root = make_root(projects)
    record_stills(root, ["s001"])
    httpd, url, _thread = serve.start_in_thread(
        projects, tmp_path / "spine.sqlite3", token="secret"
    )
    try:
        base = url.split("?")[0]
        status, body, _ = get(base + "api/project/production/stills", token="secret")
        assert status == 200
        data = json.loads(body)
        assert data["shots"][0]["id"] == "s001"
        assert set(["id", "version", "verdict", "sha256", "seconds", "framing"]) <= set(
            data["shots"][0]
        )

        status, body, headers = get(base + "api/project/production/thumb/s001", token="secret")
        assert status == 200 and headers["Content-Type"] == "image/jpeg"
        assert body.startswith(b"\xff\xd8")

        status, body, _ = get(base + "api/project/production/shot/s001", token="secret")
        assert json.loads(body)["contract"]["purpose"] == "Beat 0"

        status, body, _ = get(base + "api/project/production/board", token="secret")
        assert json.loads(body)["available"] is True

        status, body, _ = get(base + "api/project/production/approvals", token="secret")
        assert len(json.loads(body)["stages"]) == 8

        with pytest.raises(urllib.error.HTTPError) as denied:
            get(base + "api/project/production/stills")
        assert denied.value.code == 401

        for path in (
            "api/project/%2e%2e/stills",
            "api/project/production/thumb/..%2f..%2fproject.json",
            "api/project/production/thumb/unknown",
        ):
            with pytest.raises(urllib.error.HTTPError) as refused:
                get(base + path, token="secret")
            assert refused.value.code == 404

        outside = tmp_path / "outside.jpg"
        jpeg(outside)
        assets = read_json(root / "work/assets.json")
        assets["s001"]["versions"][0]["path"] = "../outside.jpg"
        write_json(root / "work/assets.json", assets)
        with pytest.raises(urllib.error.HTTPError) as escaped:
            get(base + "api/project/production/thumb/s001", token="secret")
        assert escaped.value.code == 404

        with pytest.raises(urllib.error.HTTPError) as write:
            get(base + "api/project/production/stills", token="secret", method="POST")
        assert write.value.code == 405
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_app_shell_exposes_read_only_review_views(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    make_root(projects)
    httpd, url, _thread = serve.start_in_thread(projects, tmp_path / "spine.sqlite3", token="t")
    try:
        base = url.split("?")[0]
        status, body, _ = get(base + "app?token=t")
        assert status == 200
        page = body.decode()
        for label in ("Stills", "Board", "Approvals", "Runs", "Compiled prompt"):
            assert label in page
        assert "EventSource" in page
        assert "read-only" in page
        assert "http://" not in page.replace("http://127.0.0.1", "")
        assert "https://" not in page
    finally:
        httpd.shutdown()
        httpd.server_close()


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
