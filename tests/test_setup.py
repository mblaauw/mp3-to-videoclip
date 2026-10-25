"""First-run setup: capability reporting, the local install and the GUI fallback."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from api_support import api_client

from mp3_to_videoclip import launcher, setup

READY = {
    "node": True,
    "npm": True,
    "chrome": True,
    "ffmpeg": True,
    "ffprobe": True,
    "renderer": True,
    "frontend": True,
}


def test_setup_status_is_boolean_only_and_covers_the_render_tools(tmp_path, monkeypatch):
    engine = tmp_path / "engine"
    (engine / "node_modules/@remotion/renderer").mkdir(parents=True)
    (tmp_path / "frontend/dist").mkdir(parents=True)
    (tmp_path / "frontend/dist/index.html").write_text("built")
    monkeypatch.setattr(setup, "REPO", tmp_path)
    monkeypatch.setattr(setup, "_chrome", lambda: True)
    monkeypatch.setattr(setup.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(setup, "ENGINE", engine)
    status = setup.status()
    assert status == READY


def test_install_renderer_is_a_no_op_when_pinned_packages_exist(tmp_path, monkeypatch):
    engine = tmp_path / "engine"
    (engine / "node_modules/@remotion/renderer").mkdir(parents=True)
    monkeypatch.setattr(setup, "ENGINE", engine)
    assert setup.install_renderer()["already_present"] is True


def test_install_renderer_runs_the_pinned_local_install(tmp_path, monkeypatch):
    engine = tmp_path / "engine"
    engine.mkdir()
    monkeypatch.setattr(setup, "ENGINE", engine)
    monkeypatch.setattr(setup.shutil, "which", lambda name: "/usr/bin/npm")
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        (engine / "node_modules/@remotion/renderer").mkdir(parents=True)
        return SimpleNamespace(returncode=0, stdout="added packages", stderr="")

    monkeypatch.setattr(setup.subprocess, "run", fake_run)
    result = setup.install_renderer()
    assert result["installed"] is True
    assert result["already_present"] is False
    argv, kwargs = calls[0]
    assert argv[:3] == ["/usr/bin/npm", "ci", "--prefix"]
    assert "--ignore-scripts" in argv
    assert kwargs["cwd"] == setup.REPO


def test_install_renderer_reports_npm_failure(tmp_path, monkeypatch):
    engine = tmp_path / "engine"
    engine.mkdir()
    monkeypatch.setattr(setup, "ENGINE", engine)
    monkeypatch.setattr(setup.shutil, "which", lambda name: "/usr/bin/npm")
    monkeypatch.setattr(
        setup.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="network down"),
    )
    with pytest.raises(ValueError, match="network down"):
        setup.install_renderer()


def test_setup_routes_report_and_install(tmp_path, monkeypatch):
    monkeypatch.setattr("mp3_to_videoclip.api.setup.setup.status", lambda: dict(READY))
    monkeypatch.setattr(
        "mp3_to_videoclip.api.setup.setup.install_renderer",
        lambda: {"installed": True, "already_present": True, "output": ""},
    )
    with api_client(tmp_path) as client:
        assert client.get("/api/setup").json() == READY
        response = client.post("/api/setup/renderer", json={})
        assert response.status_code == 200
        assert response.json()["already_present"] is True


def test_setup_install_failure_is_an_http_400(tmp_path, monkeypatch):
    def fail():
        raise ValueError("npm is not available")

    monkeypatch.setattr("mp3_to_videoclip.api.setup.setup.install_renderer", fail)
    with api_client(tmp_path) as client:
        response = client.post("/api/setup/renderer", json={})
        assert response.status_code == 400
        assert "npm is not available" in response.text


def test_launcher_skips_a_frontend_build_without_node_modules(tmp_path, monkeypatch):
    frontend = tmp_path / "frontend"
    (frontend / "src").mkdir(parents=True)
    (frontend / "dist").mkdir()
    monkeypatch.setattr(launcher.shutil, "which", lambda name: "/usr/bin/npm")
    calls = []
    monkeypatch.setattr(launcher.subprocess, "run", lambda *a, **k: calls.append(a))
    launcher._build_frontend(tmp_path)
    assert calls == []


def test_launcher_rebuilds_the_frontend_when_deps_and_sources_are_ready(tmp_path, monkeypatch):
    frontend = tmp_path / "frontend"
    (frontend / "src").mkdir(parents=True)
    (frontend / "dist").mkdir()
    (frontend / "node_modules").mkdir()
    import os

    os.utime(frontend / "dist", (1, 1))
    monkeypatch.setattr(launcher.shutil, "which", lambda name: "/usr/bin/npm")
    calls = []
    monkeypatch.setattr(launcher.subprocess, "run", lambda *a, **k: calls.append(a))
    launcher._build_frontend(tmp_path)
    assert calls[0][0][:3] == ["/usr/bin/npm", "run", "build"]


def test_launcher_installs_the_renderer_on_first_run(monkeypatch, capsys):
    monkeypatch.setattr(
        launcher.setup,
        "install_renderer",
        lambda: {"installed": True, "already_present": False, "output": ""},
    )
    launcher._ensure_renderer()
    assert "installed the pinned local renderer" in capsys.readouterr().out
