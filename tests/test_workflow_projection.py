"""Workflow review reads small canonical JSON only, never approval authority."""

import json
from pathlib import Path

import pytest
from test_creative_production import make_root

from mp3_to_videoclip import appdata, human_actions, serve
from mp3_to_videoclip import production as P
from mp3_to_videoclip.storage import read_json, write_json


def snapshot(root):
    return {
        str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file()
    }


def test_workflow_available_artifacts_and_proof_are_raw_read_only_data(tmp_path):
    root = make_root(tmp_path)
    graphics = {"note": "Pending actual inspection", "inspected": False}
    write_json(root / P.STAGE_FILES["graphics"], graphics)
    before = snapshot(root)

    result = appdata.workflow(root)

    assert (result["slug"], result["title"], result["music_mode"]) == (
        root.name,
        "Creative",
        "vocal",
    )
    assert set(result["artifacts"]) == {"analysis", "events", "brief", "lyrics", "graphics"}
    for stage, panel in result["artifacts"].items():
        assert panel == {
            "available": True,
            "artifact": read_json(root / P.STAGE_FILES[stage]),
        }
    assert result["proof_shot_ids"] == ["s001", "s002", "s004"]
    assert "proof_problem" not in result
    assert result["rollout"]["automatic_gate"] is False
    assert result["rollout"]["completion"] is None
    assert result["rollout"]["recommended_shots"] == {"min": 6, "max": 8}
    assert snapshot(root) == before
    assert "source_sha256" not in result
    assert "approved" not in result["artifacts"]["graphics"]
    assert result["graphics_spec"]["available"] is False
    json.dumps(result, allow_nan=False)


def test_workflow_missing_artifacts_are_explicit(tmp_path):
    root = make_root(tmp_path, with_events=False, with_storyboard=False)
    (root / "brief.json").unlink()
    result = appdata.workflow(root)

    for stage in ("events", "brief", "graphics"):
        assert result["artifacts"][stage] == {
            "available": False,
            "artifact": None,
            "problem": "Artifact is missing.",
        }
    assert result["artifacts"]["analysis"]["available"] is True
    assert result["proof_shot_ids"] == []
    assert result["proof_problem"]


@pytest.mark.parametrize(
    "content", ["{broken", "null", "[]", '"text"', "42", '{"value":NaN}', '{"value":Infinity}']
)
def test_workflow_malformed_or_wrong_shape_artifact_degrades_one_panel(tmp_path, content):
    root = make_root(tmp_path)
    path = root / P.STAGE_FILES["analysis"]
    path.write_text(content)
    before = snapshot(root)

    result = appdata.workflow(root)

    assert result["artifacts"]["analysis"]["available"] is False
    assert result["artifacts"]["analysis"]["artifact"] is None
    assert "invalid" in result["artifacts"]["analysis"]["problem"]
    assert result["artifacts"]["events"]["available"] is True
    assert result["proof_shot_ids"] == ["s001", "s002", "s004"]
    assert snapshot(root) == before


def test_workflow_unreadable_artifact_degrades_without_exposing_path(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    original = Path.read_text

    def read(path, *args, **kwargs):
        if path == root / P.STAGE_FILES["analysis"]:
            raise PermissionError("private absolute path")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    result = appdata.workflow(root)
    assert result["artifacts"]["analysis"]["available"] is False
    assert "private absolute path" not in json.dumps(result)


def test_workflow_instrumental_omits_lyrics_even_when_file_exists(tmp_path, monkeypatch):
    root = make_root(tmp_path, music_mode="instrumental")
    lyrics = root / P.STAGE_FILES["lyrics"]
    lyrics.write_text("{stale malformed lyrics")
    original = appdata.read_optional

    def read(path, *args, **kwargs):
        assert Path(path) != lyrics
        return original(path, *args, **kwargs)

    monkeypatch.setattr(appdata, "read_optional", read)
    result = appdata.workflow(root)
    assert result["music_mode"] == "instrumental"
    assert "lyrics" not in result["artifacts"]


def test_workflow_never_reads_media_approvals_or_human_review(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    before = snapshot(root)
    allowed = {
        "project.json",
        *(P.STAGE_FILES[stage] for stage in ("analysis", "events", "brief", "lyrics")),
        P.STAGE_FILES["storyboard"],
    }
    original = Path.read_text

    def read_text(path, *args, **kwargs):
        assert str(path.relative_to(root)) in allowed
        return original(path, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail("workflow called a media reader, gate check or human action")

    monkeypatch.setattr(Path, "read_text", read_text)
    with monkeypatch.context() as guard:
        guard.setattr(Path, "read_bytes", forbidden)
        guard.setattr(P, "file_hash", forbidden)
        guard.setattr(P, "load_project", forbidden)
        guard.setattr(P, "stage_hash", forbidden)
        guard.setattr(human_actions, "project_lock", forbidden)
        guard.setattr(human_actions, "review_stage", forbidden)
        result = appdata.workflow(root)
    assert result["artifacts"]["analysis"]["available"] is True
    assert snapshot(root) == before


def test_workflow_legacy_proof_uses_existing_selection_without_inventing_mode(tmp_path):
    root = make_root(tmp_path, creative=False, music_mode=None)
    result = appdata.workflow(root)
    assert result["proof_shot_ids"] == ["s001", "s003", "s004"]
    assert result["music_mode"] is None


def test_workflow_invalid_explicit_proof_has_no_fallback(tmp_path):
    root = make_root(tmp_path, proof_shot_ids=("s001", "s002", "unknown"))
    result = appdata.workflow(root)
    assert result["artifacts"]["brief"]["available"] is True
    assert result["proof_shot_ids"] == []
    assert result["proof_problem"]


def test_workflow_does_not_follow_artifact_outside_project(tmp_path):
    root = make_root(tmp_path)
    external = tmp_path / "private.json"
    external.write_text('{"private": "do not expose"}')
    path = root / P.STAGE_FILES["analysis"]
    path.unlink()
    path.symlink_to(external)
    result = appdata.workflow(root)
    assert result["artifacts"]["analysis"]["available"] is False
    assert "do not expose" not in json.dumps(result)


def test_graphics_design_is_separate_from_composite_review(tmp_path):
    root = make_root(tmp_path)
    spec = {"title": "Studio film", "credits": [{"role": "Director", "name": "Test"}]}
    write_json(root / "work/graphics-spec.json", spec)
    result = appdata.workflow(root)
    assert result["graphics_spec"] == {"available": True, "artifact": spec}
    assert result["artifacts"]["graphics"]["available"] is False


@pytest.mark.parametrize(
    "mode,expected", [("vocal", ["lyrics"]), ("instrumental", []), ("music-led", [])]
)
def test_supporting_decisions_follow_real_optional_gates(tmp_path, mode, expected):
    root = make_root(tmp_path, music_mode=mode)
    result = appdata.approvals(root)
    assert [s["stage"] for s in result["supporting_stages"]] == expected
    assert result["total"] == 8
    assert [s["stage"] for s in result["stages"]] == list(appdata.studio.ORDER)


def test_workflow_http_route_is_token_scoped_read_only_and_path_guarded(tmp_path):
    import urllib.error
    import urllib.request

    projects = tmp_path / "projects"
    projects.mkdir()
    root = make_root(projects)
    before = snapshot(root)
    server, url, thread = serve.start_in_thread(
        projects, tmp_path / "journal.sqlite3", token="test"
    )
    base = url.split("?")[0]
    try:
        with pytest.raises(urllib.error.HTTPError) as denied:
            urllib.request.urlopen(base + "api/project/production/workflow")
        assert denied.value.code == 401
        with urllib.request.urlopen(
            base + "api/project/production/workflow?token=test"
        ) as response:
            payload = json.load(response)
        assert payload["proof_shot_ids"] == ["s001", "s002", "s004"]
        request = urllib.request.Request(
            base + "api/project/production/workflow?token=test", method="POST"
        )
        with pytest.raises(urllib.error.HTTPError) as denied:
            urllib.request.urlopen(request)
        assert denied.value.code == 405
        with pytest.raises(urllib.error.HTTPError) as denied:
            urllib.request.urlopen(base + "api/project/%2e%2e/workflow?token=test")
        assert denied.value.code == 404
        assert snapshot(root) == before
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_serve_prints_the_workflow_workspace_not_the_old_journal(tmp_path, monkeypatch, capsys):
    import queue

    class Server:
        closed = False

        def serve_forever(self, **kwargs):
            raise KeyboardInterrupt

        def server_close(self):
            self.closed = True

    server = Server()
    monkeypatch.setattr(
        serve, "build_server", lambda *a, **kw: (server, "http://127.0.0.1:8800/?token=test")
    )
    ready = queue.Queue()
    serve.serve(tmp_path, tmp_path / "journal.sqlite3", ready=ready)
    assert ready.get_nowait() == "http://127.0.0.1:8800/app?token=test"
    assert "Studio live: http://127.0.0.1:8800/app?token=test" in capsys.readouterr().out
    assert server.closed


def test_preview_projection_uses_recorded_target_without_reading_movie_bytes(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    movie = root / "previews/bound.mp4"
    movie.parent.mkdir()
    movie.write_bytes(b"not decoded or hashed by this projection")
    report = {"movie": "previews/bound.mp4", "movie_sha256": "a" * 64}
    write_json(root / P.STAGE_FILES["preview"], report)
    before = snapshot(root)
    with monkeypatch.context() as guard:
        guard.setattr(Path, "read_bytes", lambda *a: pytest.fail("movie bytes must not be read"))
        result = appdata.workflow(root)
    assert result["preview_movie"] == {"path": "previews/bound.mp4", "exists": True}
    assert result["preview_review"] == {"available": True, "artifact": report}
    assert snapshot(root) == before
    report["movie"] = "../outside.mp4"
    write_json(root / P.STAGE_FILES["preview"], report)
    result = appdata.workflow(root)
    assert result["preview_movie"]["path"] is None
    assert result["preview_movie"]["exists"] is False
    assert result["preview_movie"]["problem"]
