"""Find broken frames in a rendered movie.

The browser's capture occasionally returns a single frame as a tiled fragment of
the picture, and nothing else in a render's verification looks at pictures. The
scan is deliberately eager, because a real flash or dip looks the same to it; a
suspect only counts as broken once a fresh render of that frame disagrees.
"""

import subprocess
from pathlib import Path

import numpy as np

from .render import _binary

WIDTH, HEIGHT = 96, 54
# Mean brightness change, out of 255, that a frame must jump to be suspect.
MIN_JUMP = 3.0
# Its neighbours must be this much closer to each other than the jump itself.
NEIGHBOUR_SHARE = 0.5
# A sound re-render correlates near 1 with the movie's frame; a tiled one doesn't.
MIN_CORRELATION = 0.9
# Below this contrast (a fade to black) a correlation only measures noise.
FLAT_CONTRAST = 2.0


def small_frames(path: Path | str) -> np.ndarray:
    """Every frame of a movie or image, small and grey, as (frames, height, width)."""
    raw = subprocess.run(
        [
            _binary("ffmpeg"),
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(path),
            "-vf",
            f"scale={WIDTH}:{HEIGHT}:flags=area,format=gray",
            "-f",
            "rawvideo",
            "-",
        ],
        check=True,
        capture_output=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.uint8).reshape(-1, HEIGHT, WIDTH).astype(np.float32)


def suspects(frames: np.ndarray) -> list[int]:
    """Frames unlike both neighbours while those neighbours resemble each other.

    The first and last frame have one neighbour, so they compare it with the next one
    along. Movies may be single shots, so their ends need checking too.
    """
    count = len(frames)
    if count < 3:
        return []
    step = np.abs(frames[1:] - frames[:-1]).mean(axis=(1, 2))
    across = np.abs(frames[2:] - frames[:-2]).mean(axis=(1, 2))
    found = []
    if step[0] >= MIN_JUMP and step[1] < step[0] * NEIGHBOUR_SHARE:
        found.append(0)
    for index in range(1, count - 1):
        jump = min(step[index - 1], step[index])
        if jump >= MIN_JUMP and across[index - 1] < jump * NEIGHBOUR_SHARE:
            found.append(index)
    if step[-1] >= MIN_JUMP and step[-2] < step[-1] * NEIGHBOUR_SHARE:
        found.append(count - 1)
    return found


def disagrees(frame: np.ndarray, fresh: np.ndarray) -> bool:
    """Whether a frame and a fresh render of it show different pictures.

    Correlation ignores the small brightness and range shifts between an encoded
    frame and a PNG.
    """
    if frame.std() < FLAT_CONTRAST and fresh.std() < FLAT_CONTRAST:
        return abs(float(frame.mean()) - float(fresh.mean())) > MIN_JUMP
    if frame.std() < FLAT_CONTRAST or fresh.std() < FLAT_CONTRAST:
        return True
    return float(np.corrcoef(frame.ravel(), fresh.ravel())[0, 1]) < MIN_CORRELATION


def broken_frames(frames: np.ndarray, found: list[int], fresh: dict[int, Path]) -> list[int]:
    """The suspects (indices into ``frames``) that a fresh render contradicts."""
    return [index for index in found if disagrees(frames[index], small_frames(fresh[index])[0])]
