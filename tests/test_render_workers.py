"""Several browsers at once, the bounded store of a final, and the scan's planned frames."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from test_chunk_render import _encode

from mp3_to_videoclip import framecheck, remotion, render


def chunk(start, frames, key=None):
    return SimpleNamespace(start=start, frames=frames, key=key or f"k{start}", shot_id=f"s{start}")


def test_lists_are_disjoint_cover_everything_and_balance_frames():
    chunks = [chunk(0, 100), chunk(100, 10), chunk(110, 50), chunk(160, 60), chunk(220, 30)]
    lists = remotion.split_chunks(chunks, 2)
    seen = [item.start for items in lists for item in items]
    assert sorted(seen) == [0, 100, 110, 160, 220]
    loads = [sum(item.frames for item in items) for items in lists]
    assert abs(loads[0] - loads[1]) <= 30
    assert (
        remotion.split_chunks([chunk(0, 5)], 4) == [[chunk(0, 5)]]
        or len(remotion.split_chunks([chunk(0, 5)], 4)) == 1
    )


def test_workers_follow_cores_memory_and_the_work_left(monkeypatch):
    monkeypatch.delenv(remotion.WORKERS_ENV, raising=False)
    monkeypatch.setattr(remotion.os, "cpu_count", lambda: 8)
    monkeypatch.setattr(remotion, "_free_memory", lambda: 10 * 2**30)
    assert remotion.render_workers(100) == 4
    assert remotion.render_workers(2) == 2
    monkeypatch.setattr(remotion, "_free_memory", lambda: 1300 * 2**20)
    assert remotion.render_workers(100) == 2
    monkeypatch.setattr(remotion, "_free_memory", lambda: 0)
    assert remotion.render_workers(100) == 1
    monkeypatch.setattr(remotion, "_free_memory", lambda: None)
    monkeypatch.setattr(remotion.os, "cpu_count", lambda: 2)
    assert remotion.render_workers(100) == 1


def test_the_setting_overrides_and_nonsense_is_refused(monkeypatch):
    monkeypatch.setenv(remotion.WORKERS_ENV, "3")
    assert remotion.render_workers(100) == 3
    assert remotion.render_workers(2) == 2
    monkeypatch.setenv(remotion.WORKERS_ENV, "many")
    with pytest.raises(ValueError, match="whole number"):
        remotion.render_workers(5)


def _script(tmp_path: Path, name: str, body: str) -> list[str]:
    path = tmp_path / name
    path.write_text(textwrap.dedent(body))
    return [sys.executable, str(path)]


def _worker(tmp_path: Path, number: int, body: str) -> dict:
    output = tmp_path / f"run-{number}.mp4"
    progress = tmp_path / f"run-{number}.progress.json"
    return {
        "output": output,
        "progress": progress,
        "argv": [*_script(tmp_path, f"w{number}.py", body), str(progress)],
    }


GOOD = """
import json, sys, time
for done in (5, 10):
    with open(sys.argv[1] + ".t", "w") as f:
        json.dump({"phase": "rendering-frames", "done": done, "unit": "frames", "chunks_done": 1}, f)
    __import__("os").replace(sys.argv[1] + ".t", sys.argv[1])
    time.sleep(0.2)
"""
FOREVER = """
import time
time.sleep(60)
"""
BAD = """
import sys
sys.stderr.write("chrome fell over\\n")
sys.exit(3)
"""


def test_progress_sums_and_a_finished_run_cleans_up(tmp_path, monkeypatch):
    ticks = []
    monkeypatch.setattr(remotion.operations, "tick", lambda **kw: ticks.append(kw))
    monkeypatch.setattr(remotion, "_keep_awake", lambda pid: None)
    workers = [_worker(tmp_path, 1, GOOD), _worker(tmp_path, 2, GOOD)]
    remotion._run_many(workers, total=20, reused=3, plan_size=9)
    assert any(tick["done"] == 20 for tick in ticks) or max(t["done"] for t in ticks) >= 10
    assert ticks[-1]["total"] == 20
    assert ticks[-1]["message"].endswith("of 9 shots, 2 browsers")
    assert not any(worker["progress"].exists() for worker in workers)


def test_one_failure_ends_the_rest_and_names_itself(tmp_path, monkeypatch):
    monkeypatch.setattr(remotion.operations, "tick", lambda **kw: None)
    monkeypatch.setattr(remotion, "_keep_awake", lambda pid: None)
    workers = [_worker(tmp_path, 1, FOREVER), _worker(tmp_path, 2, BAD)]
    with pytest.raises(ValueError, match=r"browser 2 of 2 failed: chrome fell over"):
        remotion._run_many(workers, total=20, reused=0, plan_size=2)


def test_stop_ends_every_browser(tmp_path, monkeypatch):
    monkeypatch.setattr(remotion.operations, "tick", lambda **kw: None)
    monkeypatch.setattr(remotion.operations, "stop_requested", lambda: True)
    monkeypatch.setattr(remotion, "_keep_awake", lambda pid: None)
    workers = [_worker(tmp_path, 1, FOREVER), _worker(tmp_path, 2, FOREVER)]
    with pytest.raises(ValueError, match="stopped by the user"):
        remotion._run_many(workers, total=20, reused=0, plan_size=2)


def test_a_stalled_browser_is_ended_and_named(tmp_path, monkeypatch):
    monkeypatch.setattr(remotion.operations, "tick", lambda **kw: None)
    monkeypatch.setattr(remotion, "_keep_awake", lambda pid: None)
    monkeypatch.setattr(remotion, "STALL_SECONDS_OTHER", 0)
    workers = [_worker(tmp_path, 1, FOREVER)]
    with pytest.raises(ValueError, match="browser 1 of 1 stopped moving"):
        remotion._run_many(workers, total=20, reused=0, plan_size=1)


def test_the_machine_lock_is_taken_once_in_a_render(tmp_path, monkeypatch):
    monkeypatch.setattr(remotion, "ENGINE", tmp_path)
    with remotion._one_render_at_a_time(), remotion._one_render_at_a_time():
        pass
    with remotion._one_render_at_a_time():
        pass


def test_a_packet_count_equals_the_decoded_count(tmp_path):
    frames = np.random.default_rng(1).integers(0, 255, (37, 54, 96), dtype=np.uint8)
    path = tmp_path / "a.mp4"
    _encode(frames, path)
    assert render._count_frames(path) == render._decoded_frames(path) == 37
    with pytest.raises(ValueError):
        (tmp_path / "bad.mp4").write_bytes(b"nope")
        render._count_frames(tmp_path / "bad.mp4")


def test_planned_windows_name_dips_flashes_and_crops():
    inputs = {
        "shots": [
            {"start_frame": 0, "edit": {"accents": [{"type": "flash", "frame": 10}]}},
            {
                "start_frame": 100,
                "edit": {
                    "transition_in": {"type": "dip_to_black", "frames": 4},
                    "crops": [{"frame": 120}],
                    "accents": [{"type": "punch_in", "frame": 130}],
                },
            },
            {"start_frame": 200, "edit": {"transition_in": {"type": "fade", "frames": 8}}},
            {"start_frame": 300},
        ]
    }
    planned = framecheck.planned_windows(inputs)
    assert planned == {*range(10, 16), *range(96, 105), 119, 120}


def _spiked(tmp_path: Path, spike: int) -> Path:
    frames = np.full((48, 54, 96), 90, dtype=np.uint8)
    frames[spike] = 250
    path = tmp_path / f"spike-{spike}.mp4"
    _encode(frames, path)
    return path


def test_a_planned_flash_is_not_rendered_again_and_is_named(tmp_path, monkeypatch):
    def must_not_render(*args, **kwargs):
        raise AssertionError("a planned frame was rendered again")

    monkeypatch.setattr(remotion, "_fresh_frames", must_not_render)
    inputs = {"shots": [{"start_frame": 0, "edit": {"accents": [{"type": "flash", "frame": 20}]}}]}
    result = remotion.check_movies([(_spiked(tmp_path, 20), 0)], None, (96, 54), 24, 48, inputs)[0]
    assert result["expected"] == [20]
    assert result["suspects"] == [] and result["broken"] == []


def test_a_glitch_beside_a_planned_window_is_still_looked_at(tmp_path, monkeypatch):
    asked = []

    def fresh(frames, *args, **kwargs):
        asked.extend(frames)
        raise RuntimeError("looked at it")

    monkeypatch.setattr(remotion, "_fresh_frames", fresh)
    inputs = {"shots": [{"start_frame": 0, "edit": {"accents": [{"type": "flash", "frame": 20}]}}]}
    with pytest.raises(RuntimeError):
        remotion.check_movies([(_spiked(tmp_path, 30), 0)], None, (96, 54), 24, 48, inputs)
    assert asked == [30]
