"""A hung render fails instead of waiting forever, and settings survive any value."""

from __future__ import annotations

import json
import stat
import sys

from mp3_to_videoclip import config, remotion


def test_a_render_whose_frames_stop_is_stopped_and_says_where(tmp_path, monkeypatch):
    monkeypatch.setattr(remotion, "STALL_SECONDS", 1.0)
    progress = tmp_path / "progress.json"
    progress.write_text(
        json.dumps({"phase": "rendering-frames", "done": 7, "total": 10, "unit": "frames"})
    )
    argv = [sys.executable, "-c", "import time; time.sleep(60)"]
    stdout, stderr = remotion._run_streaming(argv, tmp_path / "out.mp4", progress, 10)
    assert stdout is None
    assert "frame 7 of 10" in stderr


def test_a_render_before_its_first_frame_is_not_called_stuck(tmp_path, monkeypatch):
    monkeypatch.setattr(remotion, "STALL_SECONDS", 0.1)
    argv = [sys.executable, "-c", "import time; time.sleep(1.5); print('ok')"]
    stdout, _ = remotion._run_streaming(argv, tmp_path / "out.mp4", tmp_path / "none.json", 10)
    assert stdout is not None and "ok" in stdout


def test_settings_survive_quotes_and_backslashes_and_stay_private(tmp_path, monkeypatch):
    monkeypatch.setattr(config.Path, "home", lambda: tmp_path)
    saved = config.Settings(llm_api_key='a"b\\c', ffmpeg_path="C:\\tools\\ffmpeg")
    config.save_settings(saved)
    loaded = config.load_settings()
    assert loaded.llm_api_key == 'a"b\\c'
    assert loaded.ffmpeg_path == "C:\\tools\\ffmpeg"
    assert loaded.default_credit_roles == saved.default_credit_roles
    assert stat.S_IMODE(config.settings_path().stat().st_mode) == 0o600
