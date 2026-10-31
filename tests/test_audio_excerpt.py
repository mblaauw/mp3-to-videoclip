"""The derived excerpt is exactly the window, fades, and the render muxes it."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from mp3_to_videoclip import production as P
from mp3_to_videoclip import remotion
from mp3_to_videoclip.models import RenderShot, Shot
from mp3_to_videoclip.render import audio_seconds
from mp3_to_videoclip.storage import file_hash

pytestmark = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
    reason="ffmpeg and ffprobe are required for the excerpt render test",
)


def _tone(path: Path, seconds: float = 40.0) -> Path:
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
            "-ac",
            "2",
            "-ar",
            "44100",
            str(path),
        ],
        check=True,
    )
    return path


def _rms(path: Path, start: float, seconds: float = 0.25) -> float:
    raw = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-ss",
            str(start),
            "-t",
            str(seconds),
            "-i",
            str(path),
            "-ac",
            "1",
            "-ar",
            "48000",
            "-f",
            "f32le",
            "pipe:1",
        ],
        check=True,
        capture_output=True,
    ).stdout
    samples = np.frombuffer(raw, dtype=np.float32)
    return float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0


def _advert(tmp_path: Path) -> tuple[Path, object, Path]:
    source = _tone(tmp_path / "song.mp3")
    root = tmp_path / "projects" / "advert"
    project = P.init_project(
        root,
        source,
        "advert",
        kind="advert",
        length_seconds=30,
        window_start=5,
        fade_out=1.5,
        title="Thirty Seconds",
    )
    return root, project, source


def test_excerpt_is_thirty_seconds_with_a_fifteen_tenths_fade(tmp_path):
    root, project, source = _advert(tmp_path)
    before = file_hash(source)
    excerpt = P.render_audio(root, project)
    assert excerpt.suffix == ".wav"
    assert excerpt.is_file()
    assert abs(audio_seconds(excerpt) - 30.0) < 0.05
    assert file_hash(root / "media/song.mp3") == before
    assert file_hash(source) == before

    middle = _rms(excerpt, 15.0)
    last = _rms(excerpt, 29.7)
    assert middle > 0.05
    assert last < middle / 4


def test_remotion_mux_uses_the_excerpt_and_keeps_the_fade(tmp_path, monkeypatch):
    root, project, _ = _advert(tmp_path)
    project = project.model_copy(update={"width": 320, "height": 180})
    excerpt = P.render_audio(root, project)
    plate = root / "work" / "plate.png"
    Image.new("RGB", (16, 16), (40, 80, 120)).save(plate)

    shot = Shot(
        id="s001",
        start_frame=0,
        duration_frames=720,
        purpose="Prove the excerpt is the rendered audio",
        image_prompt="Solid test plate",
    )
    shots = [RenderShot(shot=shot, image=str(plate))]

    def fake_invoke(kind, output, asset_root, canvas, fps, frames, inputs, reuse=False):
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c=black:s={canvas[0]}x{canvas[1]}:r={fps}:d={frames / fps}",
                "-frames:v",
                str(frames),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(output),
            ],
            check=True,
        )
        return {"renderer_revision": "test"}

    monkeypatch.setattr(remotion, "_render_silent", fake_invoke)
    output = root / "renders" / "excerpt-v001.mp4"
    report = remotion.render_base(
        project,
        shots,
        excerpt,
        output,
        root / "work",
    )

    assert output.is_file()
    assert abs(report["duration"] - 30.0) < 0.05
    assert report["source_sha256"] == file_hash(excerpt)
    assert abs(audio_seconds(output) - 30.0) < 0.05
    middle = _rms(output, 15.0)
    last = _rms(output, 29.7)
    assert middle > 0.05
    assert last < middle / 3
