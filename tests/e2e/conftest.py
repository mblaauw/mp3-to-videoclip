"""A real Studio on a free loopback port, with no keys and a throwaway projects folder."""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn

sys.path.insert(0, str(Path(__file__).parent.parent))

from api_support import make_api_project

from mp3_to_videoclip.app import create_app
from mp3_to_videoclip.storage import read_json, write_json


class Studio:
    def __init__(self, url: str, root: Path):
        self.url = url
        self.root = root
        self.api = f"{url}/api/projects/{root.name}"

    def film(self, stage: str) -> str:
        return f"{self.url}/#/{self.root.name}/{stage}"

    def approve(self, *stages: str) -> None:
        for stage in stages:
            rows = httpx.get(f"{self.api}/approvals").json()["stages"]
            expected = next(row for row in rows if row["stage"] == stage)["expected_hash"]
            answer = httpx.post(
                f"{self.api}/approvals/{stage}",
                json={"expected_hash": expected, "confirmed": True},
            )
            assert answer.status_code == 200, answer.text

    def unfinish_shots(self, count: int) -> None:
        path = self.root / "work/storyboard.json"
        board = read_json(path)
        for shot in board["shots"][:count]:
            shot["purpose"] = "TODO: approved story purpose"
            shot["image_prompt"] = "TODO: compose this shot"
            shot["message"] = ""
        write_json(path, board)


@pytest.fixture
def studio(tmp_path, monkeypatch):
    monkeypatch.delenv("PROJECT_VEIL_RUNWARE_API", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    root = make_api_project(tmp_path)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(create_app(projects_dir=tmp_path), port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.02)
    yield Studio(f"http://127.0.0.1:{port}", root)
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture
def stays_local(page, studio):
    """Fails a test if anything leaves this computer."""
    outside: list[str] = []

    def note(request):
        if not request.url.startswith((studio.url, "data:", "blob:")):
            outside.append(request.url)

    page.on("request", note)
    yield
    assert outside == []


@pytest.fixture(scope="session")
def browser(launch_browser):
    """No browser on this computer is a skip here and a failure in CI, where one must exist."""
    from playwright.sync_api import Error

    try:
        opened = launch_browser()
    except Error as exc:
        if os.environ.get("CI"):
            raise
        pytest.skip(f"no browser to run these in: {str(exc).splitlines()[0]}")
    yield opened
    opened.close()
