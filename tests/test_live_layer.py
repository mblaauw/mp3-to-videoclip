"""Live layer, operation import and the capability registry."""

import json
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

import pytest
from test_creative_production import jpeg, make_root, record_stills

from mp3_to_videoclip import appdata, serve, studio
from mp3_to_videoclip import production as P
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
    httpd, url, _thread = serve.start_in_thread(projects, token="secret")
    try:
        base = url.split("?")[0]
        status, body, _ = get(base + "api/health")
        assert status == 200 and json.loads(body)["review_only"] is True
        assert json.loads(body)["read_only"] is False

        with pytest.raises(urllib.error.HTTPError) as denied:
            get(base + "api/status")
        assert denied.value.code == 401

        status, body, _ = get(base + "api/status", token="secret")
        assert status == 200 and json.loads(body)["retired"] is True

        status, body, _ = get(base + "api/runs", token="secret")
        assert json.loads(body)["retired"] is True

        status, body, _ = get(base + "api/studio", token="secret")
        assert len(json.loads(body)["productions"]) == 1

        status, body, _ = get(base + "api/events", token="secret")
        assert json.loads(body)["events"] == []

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
    httpd, url, _thread = serve.start_in_thread(projects, token="t")
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


def test_human_auth_recovery_headers_and_refused_write_aliases(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    httpd, url, thread = serve.start_in_thread(projects, token="secret")
    try:
        base = url.split("?")[0]
        with pytest.raises(urllib.error.HTTPError) as error:
            get(base + "app")
        response = error.value
        assert response.code == 401
        assert response.headers["Content-Type"].startswith("text/html")
        assert b"uv run clip serve" in response.read()
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
        for method in ("PUT", "PATCH", "DELETE"):
            with pytest.raises(urllib.error.HTTPError) as rejected:
                get(base + "api/create", token="secret", method=method)
            assert rejected.value.code == 405
        assert list(projects.iterdir()) == []
        with pytest.raises(urllib.error.HTTPError) as unknown:
            get(base + "unknown", token="secret")
        assert unknown.value.code == 404
        assert b"This Studio page was not found" in unknown.value.read()
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def test_detail_uses_one_verified_stage_snapshot(tmp_path):
    from test_creative_production import approve_through_proof

    projects = tmp_path / "projects"
    projects.mkdir()
    root = make_root(projects)
    approve_through_proof(root)
    approvals = read_json(root / "work/approvals.json")
    approvals["proof"]["hash"] = "old-proof"
    write_json(root / "work/approvals.json", approvals)
    httpd, url, thread = serve.start_in_thread(projects, token="t")
    try:
        base = url.split("?")[0]
        summary = json.loads(get(base + "api/studio", token="t")[1])["productions"][0]
        assert summary["stages"]["proof"] == "recorded"
        detail = json.loads(get(base + "api/project/production", token="t")[1])
        assert detail["checked_at"]
        assert detail["entry"]["stages"] == {
            row["stage"]: row["state"] for row in detail["approvals"]["stages"]
        }
        assert detail["entry"]["stages"]["proof"] == "stale"
        assert detail["entry"]["next_step"] == "proof approval"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def test_matching_hash_does_not_override_a_rejected_proof_review(tmp_path):
    from test_creative_production import approve_prerequisites
    from test_workflow_v2 import accept, strict_root

    root = strict_root(tmp_path)
    approve_prerequisites(root)
    P.approve(root, "storyboard", "approved board")
    ids = P.proof_ids(P.load_board(root), P.load_brief(root))
    record_stills(root, ids)
    accept(root, ids)
    P.approve(root, "proof", "accepted exact versions")
    proof_hash = P.stage_hash(root, "proof")
    record_review(root, "s001", 1, "reject", note="new defect", reviewer="test", inspected=True)
    assert P.stage_hash(root, "proof") == proof_hash
    with pytest.raises(ValueError, match="accepted review"):
        P.require_approval(root, "proof")
    proof = next(s for s in appdata.approvals(root)["stages"] if s["stage"] == "proof")
    assert proof["hash"] == proof["approved_hash"]
    assert proof["state"] == "blocked"
    assert proof["would_pass_now"] is False
    assert "accepted review" in proof["problem"]


@pytest.mark.parametrize("invalid", [{"note": " "}, {"cap": "NaN"}, {"cap": "0"}])
def test_invalid_setup_does_not_leave_a_project(tmp_path, monkeypatch, invalid):
    projects = tmp_path / "projects"
    projects.mkdir()
    source = tmp_path / "source.mp3"
    source.write_bytes(b"validation must happen before decoding")
    calls = []
    monkeypatch.setattr(P, "init_project", lambda *args, **kwargs: calls.append(args))
    httpd, url, thread = serve.start_in_thread(projects, token="t")
    try:
        body = {"title": "Invalid setup", "audio": str(source), "cap": "1.00", **invalid}
        request = urllib.request.Request(
            url.split("?")[0] + "api/create?token=t",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=5)
        assert error.value.code == 400
        assert calls == []
        assert list(projects.iterdir()) == []
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def test_partial_setup_names_the_created_project(tmp_path, monkeypatch):
    from mp3_to_videoclip import budget

    projects = tmp_path / "projects"
    projects.mkdir()
    source = tmp_path / "source.mp3"
    source.write_bytes(b"fake source; init is stubbed")

    def init(root, *_args, **_kwargs):
        (root / "work").mkdir(parents=True)

    def fail(*_args, **_kwargs):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(P, "init_project", init)
    monkeypatch.setattr(budget, "set_budget", fail)
    httpd, url, thread = serve.start_in_thread(projects, token="t")
    try:
        request = urllib.request.Request(
            url.split("?")[0] + "api/create?token=t",
            data=json.dumps({"title": "Partial", "audio": str(source), "cap": "1.00"}).encode(),
        )
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=5)
        assert error.value.code == 400
        text = json.loads(error.value.read())["error"]
        assert "'partial' was created" in text
        assert "do not create it again" in text
        assert (projects / "partial").is_dir()
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def test_studio_scan_is_shared_with_the_page(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    make_root(projects)
    entries = studio.scan(projects)
    assert entries and entries[0]["actions"]


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
    httpd, url, _thread = serve.start_in_thread(projects, token="secret")
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
    httpd, url, _thread = serve.start_in_thread(projects, token="t")
    try:
        base = url.split("?")[0]
        status, body, _ = get(base + "app?token=t")
        assert status == 200
        page = body.decode()
        for label in (
            "Track",
            "Story",
            "Style check",
            "Images",
            "Finish",
            "Project",
            "Compiled prompt",
        ):
            assert label in page
        assert "EventSource" in page
        assert "Read-only session" in page
        assert "http://" not in page.replace("http://127.0.0.1", "")
        assert "https://" not in page
    finally:
        httpd.shutdown()
        httpd.server_close()


# --------------------------------------------------------------------------- #
# capability registry
# --------------------------------------------------------------------------- #
def test_source_upload_copies_browser_file_and_create_uses_it(tmp_path):
    from test_native_size import synth_source

    projects = tmp_path / "projects"
    projects.mkdir()
    source = synth_source(tmp_path)
    httpd, url, thread = serve.start_in_thread(projects, token="t")
    base = url.split("?")[0]

    def post(target, data, headers):
        request = urllib.request.Request(target, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    try:
        status, _ = post(base + "api/source?name=song.mp3", b"x", {})
        assert status == 401
        status, body = post(
            base + "api/source?token=t&name=" + quote("My Song.mp3"),
            source.read_bytes(),
            {"X-Studio-Token": "t", "Content-Type": "application/octet-stream"},
        )
        assert status == 201
        uploaded = Path(body["path"])
        assert uploaded.is_file()
        assert uploaded.parent == httpd.upload_dir
        assert body["title"] == "My Song"
        assert body["seconds"] > 0
        status, _ = post(
            base + "api/source?token=t&name=notes.txt",
            b"x",
            {"X-Studio-Token": "t"},
        )
        assert status == 400

        status, created = post(
            base + "api/create?token=t",
            json.dumps({"title": "Uploaded", "audio": str(uploaded), "cap": "1.00"}).encode(),
            {"X-Studio-Token": "t", "Content-Type": "application/json"},
        )
        assert status == 201
        assert created["created"] == "uploaded"
        assert (projects / "uploaded/media/song.mp3").is_file()
        assert not uploaded.exists()
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)
