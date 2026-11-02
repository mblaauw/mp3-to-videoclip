"""What the probe and duration helpers report on real files."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mp3_to_videoclip import ffmpeg as R

ONE_FRAME = 1 / 24


def make_audio(path: Path, seconds: float) -> Path:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(path),
        ],
        check=True,
    )
    return path


def test_probe_exposes_format_and_streams(tmp_path):
    audio = make_audio(tmp_path / "mus.wav", 1.0)
    info = R.probe(audio)
    assert info["format"]["format_name"].startswith("wav")
    assert any(s.get("codec_type") == "audio" for s in info["streams"])
    assert float(info["format"]["duration"]) == pytest.approx(1.0, abs=ONE_FRAME)


def test_audio_seconds_counts_decoded_samples(tmp_path):
    """Length comes from decoded PCM, not the container's over-reported duration."""
    source = tmp_path / "tone.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1.013",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(source),
        ],
        check=True,
    )
    assert R.audio_seconds(source) == pytest.approx(1.013, abs=0.002)
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        R.audio_seconds(tmp_path / "missing.mp3")
