"""A hung render fails and takes its browser with it; renders run one at a time."""

import subprocess
import sys
import time
from multiprocessing import get_context
from pathlib import Path

import pytest

from mp3_to_videoclip import operations, remotion

SLEEPER = "import time; time.sleep(60)"
FAMILY = f"""
import subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", {SLEEPER!r}], start_new_session=True)
open(sys.argv[1], "w").write(str(child.pid))
time.sleep(60)
"""


def _alive(pid: int) -> bool:
    state = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
    return bool(state.stdout.strip()) and not state.stdout.startswith("Z")


def _wait_for(condition, seconds=10):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return False


def test_watch_counts_frames_not_timestamps():
    now = [0.0]
    watch = remotion._StallWatch(clock=lambda: now[0])
    rendering = {"phase": "rendering-frames", "done": 10, "updated_at": "a"}
    watch.saw(rendering)
    now[0] = 119
    watch.saw({**rendering, "updated_at": "b"})
    assert not watch.stalled()
    now[0] = 121
    watch.saw({**rendering, "updated_at": "c"})
    assert watch.stalled()
    watch.saw({**rendering, "done": 11})
    assert not watch.stalled()


def test_bundling_gets_longer_than_frames():
    now = [0.0]
    watch = remotion._StallWatch(clock=lambda: now[0])
    watch.saw({"phase": "bundling-assets", "done": 5})
    now[0] = 200
    assert not watch.stalled()
    now[0] = 301
    assert watch.stalled()


def test_a_stuck_render_is_ended_with_its_browser(tmp_path, monkeypatch):
    monkeypatch.setattr(remotion, "STALL_SECONDS_OTHER", 1)
    marker = tmp_path / "child.pid"
    argv = [sys.executable, "-c", FAMILY, str(marker)]
    with pytest.raises(ValueError, match="stopped moving during startup"):
        remotion._run_streaming(argv, tmp_path / "out.mp4", tmp_path / "progress.json", 10)
    child = int(marker.read_text())
    assert _wait_for(lambda: not _alive(child)), "the detached browser survived"


def test_a_stop_ends_the_render(tmp_path, monkeypatch):
    monkeypatch.setattr(operations, "stop_requested", lambda: True)
    argv = [sys.executable, "-c", SLEEPER]
    started = time.monotonic()
    with pytest.raises(ValueError, match="stopped by the user"):
        remotion._run_streaming(argv, tmp_path / "out.mp4", tmp_path / "progress.json", 10)
    assert time.monotonic() - started < 10


def test_a_finished_render_still_returns_its_output(tmp_path):
    argv = [sys.executable, "-c", "print('done')"]
    out, _ = remotion._run_streaming(argv, tmp_path / "out.mp4", tmp_path / "p.json", 10)
    assert "done" in out


def _hold_lock(engine: str, held, release):
    remotion.ENGINE = Path(engine)
    with remotion._one_render_at_a_time():
        held.set()
        release.wait(20)


def test_a_second_render_waits_and_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(remotion, "ENGINE", tmp_path)
    ctx = get_context("fork")
    held, release = ctx.Event(), ctx.Event()
    holder = ctx.Process(target=_hold_lock, args=(str(tmp_path), held, release))
    holder.start()
    try:
        assert held.wait(10)
        phases = []

        def phase(name, **_):
            phases.append(name)
            release.set()

        monkeypatch.setattr(operations, "phase", phase)
        with remotion._one_render_at_a_time():
            assert phases == ["waiting-for-another-render"]
    finally:
        release.set()
        holder.join(10)


def test_a_waiting_render_can_be_stopped(tmp_path, monkeypatch):
    monkeypatch.setattr(remotion, "ENGINE", tmp_path)
    ctx = get_context("fork")
    held, release = ctx.Event(), ctx.Event()
    holder = ctx.Process(target=_hold_lock, args=(str(tmp_path), held, release))
    holder.start()
    try:
        assert held.wait(10)
        monkeypatch.setattr(operations, "stop_requested", lambda: True)
        with pytest.raises(ValueError, match="stopped by the user"):
            with remotion._one_render_at_a_time():
                pass
    finally:
        release.set()
        holder.join(10)
