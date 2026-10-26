"""Shared real-FFmpeg scaffolding for the graphics test modules.

``tests/test_graphics.py`` and ``tests/test_graphics_cache.py`` both synthesize a
tiny 640x360 base with lavfi, declare the same audio as the project source and
drive the package compositor in a throwaway ``tmp_path`` project. The builders,
the frame readers and the packet hashing live here so the two modules cannot
drift apart. Each module keeps its own constants, spec factory and pytest marks:
the fixtures read ``DURATION``, ``FPS`` and ``_spec()`` from the requesting
module and reproduce exactly the base that module described before.

Everything is function-scoped. No provider call and no paid call is ever made.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

# Tests are also a package so ``python -m tests.evals`` works; keep the
# historical top-level imports used by the test modules working.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pytest

from mp3_to_videoclip import graphics

SIZE = (640, 360)

FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
requires_ffmpeg = pytest.mark.skipif(
    not FFMPEG, reason="ffmpeg and ffprobe are required for the real composite tests"
)


@pytest.fixture(autouse=True)
def isolated_user_settings(tmp_path: Path, monkeypatch):
    """Never read the developer's real settings or provider key during tests."""
    monkeypatch.setattr(
        "mp3_to_videoclip.config.settings_path",
        lambda: tmp_path / "no-user-settings.toml",
    )


# --------------------------------------------------------------------------- #
# process, frame and packet helpers
# --------------------------------------------------------------------------- #
def run_ffmpeg(argv: list[str]) -> None:
    subprocess.run(argv, check=True, capture_output=True)


def read_frame(path: Path, seconds: float, fps: int = 24) -> np.ndarray:
    """Decode one exact frame by index.

    Input seeking lands on the nearest keyframe and then relies on decoder
    behaviour, which differs between ffmpeg builds and between two files that
    encode the same picture with different keyframe grids. Selecting the frame by
    number is deterministic: the same index is the same picture in both files.
    """
    frame = int(round(seconds * fps))
    raw = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(path),
            "-vf",
            f"select=eq(n\\,{frame}),format=rgb24,scale=in_range=limited:out_range=full",
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "pipe:1",
        ],
        check=True,
        capture_output=True,
    ).stdout
    assert len(raw) == SIZE[0] * SIZE[1] * 3, "unexpected decoded frame size"
    return np.frombuffer(raw, dtype=np.uint8).reshape(SIZE[1], SIZE[0], 3).astype(np.int16)


def frame_diff(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=2)


def audio_packet_hash(path: Path) -> str:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_packets",
            "-show_data_hash",
            "sha256",
            "-show_entries",
            "packet=pts,dts,duration,size,flags,data_hash",
            "-of",
            "compact=p=0",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return hashlib.sha256(out.encode()).hexdigest()


# --------------------------------------------------------------------------- #
# project scaffolding
# --------------------------------------------------------------------------- #
def build_project(root: Path, *, duration: float, fps: int, spec: dict) -> Path:
    """A throwaway project with a synthesized 640x360 base, source and spec."""
    (root / "media").mkdir(parents=True)
    (root / "work").mkdir(parents=True)
    base = root / "work" / "base-fixture.mp4"
    run_ffmpeg(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size={SIZE[0]}x{SIZE[1]}:rate={fps}:duration={duration}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=330:duration={duration}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(base),
        ]
    )
    # The declared source is the same audio, so the fixture needs no second file.
    source = root / "media" / "song.mp3"
    shutil.copyfile(base, source)
    (root / "project.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slug": "cool-cat",
                "title": "Cool Cat",
                "source": "media/song.mp3",
                "source_sha256": graphics._file_hash(source),
                "duration": duration,
                "aspect": "16:9",
                "fps": fps,
                "width": SIZE[0],
                "height": SIZE[1],
                "music_mode": "music-led",
            },
            indent=2,
        )
        + "\n"
    )
    (root / "work" / "graphics-spec.json").write_text(json.dumps(spec, indent=2) + "\n")
    return root


@pytest.fixture()
def project_root(tmp_path: Path, request) -> Path:
    """A throwaway ``tmp_path`` project, sized by the requesting module."""
    module = request.module
    return build_project(
        tmp_path / "cool-cat",
        duration=module.DURATION,
        fps=module.FPS,
        spec=module._spec(),
    )


@pytest.fixture()
def base(project_root: Path) -> Path:
    return project_root / "work" / "base-fixture.mp4"
