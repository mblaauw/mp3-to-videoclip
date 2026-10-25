"""Derived excerpt audio and the waveform envelope used by the window picker.

The source MP3 is never rewritten. An excerpt is a PCM WAV cached under
``work/audio/`` and keyed by the source hash plus the exact window. Music videos
without a window keep using the original file.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np

from .models import AudioWindow, Project
from .storage import digest, inside, read_optional, write_json

SAMPLE_RATE = 48_000
CHANNELS = 2
MAX_PEAK_BUCKETS = 512


def _ffmpeg() -> str:
    override = os.environ.get("FFMPEG_BIN")
    if override:
        return override
    found = shutil.which("ffmpeg")
    if not found:
        raise RuntimeError("ffmpeg was not found on PATH")
    return found


def _tail(value: bytes, limit: int = 1200) -> str:
    return value.decode("utf-8", "replace")[-limit:]


def source_audio(root: Path, project: Project) -> Path:
    return inside(root, project.source)


def excerpt_key(project: Project) -> str:
    window = project.audio_window
    if window is None:
        raise ValueError("project has no audio window")
    return digest(
        {
            "source_sha256": project.source_sha256,
            "window": window.model_dump(),
            "rate": SAMPLE_RATE,
            "channels": CHANNELS,
        }
    )[:20]


def excerpt_path(root: Path, project: Project) -> Path:
    return root / "work" / "audio" / f"excerpt-{excerpt_key(project)}.wav"


def _fade_filter(window: AudioWindow) -> str:
    length = window.duration
    parts = ["asetpts=PTS-STARTPTS"]
    if window.fade_in:
        parts.append(f"afade=t=in:st=0:d={window.fade_in:.6f}")
    if window.fade_out:
        start = max(0.0, length - window.fade_out)
        parts.append(f"afade=t=out:st={start:.6f}:d={window.fade_out:.6f}")
    return ",".join(parts)


def build_excerpt(root: Path, project: Project) -> Path:
    """Create (or reuse) the exact PCM excerpt for the project window."""
    window = project.audio_window
    if window is None:
        raise ValueError("project has no audio window")
    source = source_audio(root, project)
    if not source.is_file():
        raise FileNotFoundError(f"source audio not found: {source}")
    target = excerpt_path(root, project)
    if target.is_file():
        from .render import audio_seconds

        if abs(audio_seconds(target) - window.duration) <= 0.05:
            return target
        target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".partial.wav")
    temp.unlink(missing_ok=True)
    argv = [
        _ffmpeg(),
        "-nostdin",
        "-v",
        "error",
        "-n",
        "-i",
        str(source),
        "-af",
        (f"atrim=start={window.start:.6f}:end={window.end:.6f},{_fade_filter(window)}"),
        "-vn",
        "-ac",
        str(CHANNELS),
        "-ar",
        str(SAMPLE_RATE),
        "-c:a",
        "pcm_s16le",
        str(temp),
    ]
    completed = subprocess.run(argv, capture_output=True)
    if completed.returncode != 0 or not temp.is_file():
        temp.unlink(missing_ok=True)
        raise RuntimeError("ffmpeg could not cut the excerpt: " + _tail(completed.stderr))
    from .render import audio_seconds

    measured = audio_seconds(temp)
    if abs(measured - window.duration) > 0.05:
        temp.unlink(missing_ok=True)
        raise ValueError(f"excerpt is {measured:.3f}s but the window is {window.duration:.3f}s")
    os.replace(temp, target)
    return target


def render_audio(root: Path, project: Project) -> Path:
    """The audio every render, preview and Player must use."""
    if project.audio_window is None:
        return source_audio(root, project)
    return build_excerpt(root, project)


def peaks(path: Path, buckets: int = 320) -> list[float]:
    """A normalized peak envelope, or an empty list for undecodable audio."""
    buckets = max(1, min(MAX_PEAK_BUCKETS, int(buckets)))
    completed = subprocess.run(
        [
            _ffmpeg(),
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "8000",
            "-f",
            "f32le",
            "pipe:1",
        ],
        capture_output=True,
    )
    if completed.returncode != 0 or not completed.stdout:
        return []
    samples = np.frombuffer(completed.stdout, dtype=np.float32)
    if samples.size == 0:
        return []
    step = max(1, math.ceil(samples.size / buckets))
    values = [
        float(np.max(np.abs(samples[index : index + step])))
        for index in range(0, samples.size, step)
    ]
    top = max(values)
    if top <= 1e-9:
        return [0.0 for _ in values]
    return [round(value / top, 4) for value in values]


def cached_peaks(path: Path, source_sha256: str, cache: Path, buckets: int = 320) -> list[float]:
    value = read_optional(cache)
    if (
        isinstance(value, dict)
        and value.get("source_sha256") == source_sha256
        and value.get("buckets") == buckets
        and isinstance(value.get("peaks"), list)
    ):
        return value["peaks"]
    values = peaks(path, buckets)
    if values:
        write_json(cache, {"source_sha256": source_sha256, "buckets": buckets, "peaks": values})
    return values
