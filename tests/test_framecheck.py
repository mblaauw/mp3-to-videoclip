"""Broken frames are found in real encoded pictures and confirmed by a fresh render."""

import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from mp3_to_videoclip import framecheck, remotion
from mp3_to_videoclip.storage import read_json


def _picture(seed: int = 1, contrast: float = 1.0) -> np.ndarray:
    """A smooth scene, like a still: broad shapes, not noise."""
    y, x = np.mgrid[0:54, 0:96].astype(np.float32)
    value = 128 + 90 * contrast * np.sin(x / 13 + seed) * np.cos(y / 9 + seed)
    return np.clip(value, 0, 255).astype(np.float32)


def _tiled(picture: np.ndarray) -> np.ndarray:
    """What the browser's fault looks like: the corner repeated three times across."""
    corner = picture[:18, :32]
    return np.tile(corner, (3, 3))


def _film(count=40, **kwargs) -> np.ndarray:
    # A slow move, so ordinary frames differ a little from each other.
    base = _picture(**kwargs)
    return np.stack([np.roll(base, index // 4, axis=1) for index in range(count)])


def test_a_tiled_frame_is_suspect_and_its_neighbours_are_not():
    frames = _film()
    frames[20] = _tiled(frames[20])
    assert framecheck.suspects(frames) == [20]


def test_a_low_contrast_tiled_frame_is_still_suspect():
    frames = _film(contrast=0.25)
    frames[20] = _tiled(frames[20])
    assert framecheck.suspects(frames) == [20]


@pytest.mark.parametrize("position", [0, -1])
def test_the_ends_of_a_movie_are_checked(position):
    frames = _film()
    frames[position] = _tiled(frames[position])
    assert framecheck.suspects(frames) == [position % len(frames)]


def test_a_hard_cut_and_a_held_shot_are_not_suspect():
    frames = _film()
    frames[20:] = _film(count=20, seed=4)
    assert framecheck.suspects(frames) == []
    assert framecheck.suspects(np.stack([_picture()] * 10)) == []


def test_a_one_frame_flash_is_suspect_but_a_fresh_render_clears_it():
    frames = _film()
    frames[20] = np.minimum(frames[20] + 60, 255)
    assert framecheck.suspects(frames) == [20]
    assert not framecheck.disagrees(frames[20], frames[20] * 0.9 + 3)


def test_a_fresh_render_contradicts_a_tiled_frame():
    picture = _picture()
    assert framecheck.disagrees(_tiled(picture), picture)
    low = _picture(contrast=0.25)
    assert framecheck.disagrees(_tiled(low), low)


def test_black_frames_agree_despite_noise():
    rng = np.random.default_rng(1)
    assert not framecheck.disagrees(rng.random((54, 96)), rng.random((54, 96)))
    assert framecheck.disagrees(rng.random((54, 96)), _picture())


def _encode(frames: np.ndarray, path: Path) -> None:
    process = subprocess.Popen(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-s",
            "96x54",
            "-r",
            "24",
            "-i",
            "-",
            "-c:v",
            "libx264",
            "-crf",
            "10",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        stdin=subprocess.PIPE,
    )
    process.communicate(frames.astype(np.uint8).tobytes())
    assert process.returncode == 0


def _fake_stills(film: np.ndarray, calls: list):
    """The renderer's stills: always the sound picture, whatever the movie shows."""

    def invoke(kind, output, selected, canvas, fps, total, inputs):
        assert kind == "stills"
        assert "capture" not in inputs
        calls.append(inputs["still_frames"])
        output.mkdir()
        stills = []
        for frame in inputs["still_frames"]:
            name = f"f{frame:05d}.png"
            Image.fromarray(film[frame].astype(np.uint8)).save(output / name)
            stills.append({"frame": frame, "file": name})
        return {"renderer_report": {"stills": stills}}

    return invoke


def _check(movie, film, monkeypatch, start=0):
    calls: list = []
    monkeypatch.setattr(remotion, "invoke", _fake_stills(film, calls))
    inputs = {"shots": [], "capture": {"format": "jpeg", "quality": 95}}
    return remotion.check_frames(movie, start, None, (96, 54), 24, len(film), inputs), calls


def test_a_real_encoded_broken_frame_is_found(tmp_path, monkeypatch):
    film = _film()
    damaged = film.copy()
    damaged[20] = _tiled(film[20])
    _encode(damaged, tmp_path / "movie.mp4")
    check, calls = _check(tmp_path / "movie.mp4", film, monkeypatch)
    assert check == {"scanned": 40, "suspects": [20], "broken": [20]}
    assert calls == [[20]]
    assert not list(tmp_path.glob(".frame-check-*"))


def test_a_real_flash_is_cleared_by_the_fresh_render(tmp_path, monkeypatch):
    film = _film()
    film[20] = np.minimum(film[20] + 60, 255)
    _encode(film, tmp_path / "movie.mp4")
    check, _ = _check(tmp_path / "movie.mp4", film, monkeypatch)
    assert check == {"scanned": 40, "suspects": [20], "broken": []}


def test_a_clean_movie_renders_nothing_more(tmp_path, monkeypatch):
    film = _film()
    _encode(film, tmp_path / "movie.mp4")
    check, calls = _check(tmp_path / "movie.mp4", film, monkeypatch)
    assert check == {"scanned": 40, "suspects": [], "broken": []}
    assert calls == []


def test_frames_are_reported_in_film_numbers(tmp_path, monkeypatch):
    film = _film(count=140)
    damaged = film[100:].copy()
    damaged[20] = _tiled(damaged[20])
    _encode(damaged, tmp_path / "chunk.mp4")
    check, calls = _check(tmp_path / "chunk.mp4", film, monkeypatch, start=100)
    assert check["broken"] == [120]
    assert calls == [[120]]


def test_a_silent_render_with_a_broken_frame_fails_and_is_kept(tmp_path, monkeypatch):
    film = _film()
    damaged = film.copy()
    damaged[20] = _tiled(film[20])
    stills = _fake_stills(film, [])

    def invoke(kind, output, *rest):
        if kind == "base":
            _encode(damaged, output)
            return {}
        return stills(kind, output, *rest)

    monkeypatch.setattr(remotion, "invoke", invoke)
    silent = tmp_path / "silent.mp4"
    with pytest.raises(ValueError, match=r"broken frames at \[20\]"):
        remotion._render_silent("base", silent, None, (96, 54), 24, 40, {"shots": []})
    assert silent.is_file()


def test_a_clean_silent_render_records_its_check(tmp_path, monkeypatch):
    film = _film()
    monkeypatch.setattr(remotion, "invoke", lambda kind, output, *rest: _encode(film, output) or {})
    silent = tmp_path / "silent.mp4"
    remotion._render_silent("base", silent, None, (96, 54), 24, 40, {"shots": []})
    assert read_json(silent.with_suffix(".frames.json"))["broken"] == []
