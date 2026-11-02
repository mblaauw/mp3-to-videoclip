"""FFmpeg and ffprobe: finding them, running them, and measuring what they made.

Nothing here draws a picture. The renderer is ``remotion.py``; this is what it and the audio
code use to mux and to verify. A wrong measurement here would certify a wrong file, so each
check reads the file itself and not what a render reported.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from .models import Project, RenderShot, Storyboard

AUDIO_BITRATE = "192k"
DURATION_SAMPLE_RATE = 8000
_DEFAULT_THREADS_CAP = 4
_TOLERANT_FRAME_SLACK = 1


# --------------------------------------------------------------------------- #
# process helpers
# --------------------------------------------------------------------------- #
def _binary(name: str) -> str:
    override = os.environ.get(f"{name.upper()}_BIN")
    if override:
        return override
    found = shutil.which(name)
    if not found:
        raise RuntimeError(f"{name} was not found on PATH")
    return found


def _max_threads() -> int:
    override = os.environ.get("CLIP_FFMPEG_THREADS")
    if override:
        return max(1, int(override))
    return max(1, min(_DEFAULT_THREADS_CAP, os.cpu_count() or 1))


def _run(argv: list[str]) -> str:
    """Run an argv list (never a shell string) and return stdout."""
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        tail = proc.stderr.strip().splitlines()[-8:]
        raise RuntimeError(f"{argv[0]} failed ({proc.returncode}): " + " | ".join(tail))
    return proc.stdout


def probe(path: Path | str) -> dict:
    """Return the full ffprobe JSON document for ``path``."""
    out = _run(
        [
            _binary("ffprobe"),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
    )
    return json.loads(out)


def _video_stream(info: dict) -> dict:
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            return stream
    raise ValueError("no video stream found")


def _audio_stream(info: dict) -> dict:
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "audio":
            return stream
    raise ValueError("no audio stream found")


def _count_frames(path: Path | str) -> int:
    """The video stream's packet count, read from the file without decoding it."""
    out = subprocess.run(
        [
            _binary("ffprobe"),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_packets",
            "-show_entries",
            "stream=nb_read_packets",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    try:
        return int(out.stdout.strip().rstrip(","))
    except ValueError:
        raise ValueError(f"could not read frame count from {path}") from None


def _decoded_frames(path: Path | str) -> int:
    """Decode every frame and count them; a small picture makes it about 4× faster."""
    width, height = 16, 9
    decoded = subprocess.run(
        [
            _binary("ffmpeg"),
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-vf",
            f"scale={width}:{height},format=gray",
            "-f",
            "rawvideo",
            "-",
        ],
        capture_output=True,
    )
    if decoded.returncode != 0:
        raise ValueError(f"could not read frame count from {path}")
    return len(decoded.stdout) // (width * height)


def audio_seconds(path: Path | str) -> float:
    """Exact seconds of decodable audio, counted from decoded PCM.

    ffprobe's ``format.duration`` over-reports a VBR MP3 without a Xing header
    (a 60 s file probes 0.7 s long), and some builds omit the per-stream
    ``duration_ts``. Decoding to 8 kHz mono is cheap, gives a sample count that
    does not depend on container metadata or ffmpeg version, and is the length
    the mux will actually carry.
    """
    process = subprocess.run(
        [
            _binary("ffmpeg"),
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-ac",
            "1",
            "-ar",
            str(DURATION_SAMPLE_RATE),
            "pipe:1",
        ],
        check=True,
        capture_output=True,
    )
    samples = len(process.stdout) // 2
    if samples <= 0:
        raise ValueError(f"no decodable audio in {path}")
    return round(samples / DURATION_SAMPLE_RATE, 6)


def _is_faststart(path: Path, window: int = 262_144) -> bool:
    """True when the ``moov`` atom precedes ``mdat`` in the first window."""
    with path.open("rb") as handle:
        head = handle.read(window)
    moov = head.find(b"moov")
    mdat = head.find(b"mdat")
    return moov != -1 and (mdat == -1 or moov < mdat)


# --------------------------------------------------------------------------- #
# timeline
# --------------------------------------------------------------------------- #
def _validate_shots(project: Project, shots: list[RenderShot]) -> Storyboard:
    if not shots:
        raise ValueError("at least one shot is required")
    board = Storyboard(
        aspect=project.aspect,
        fps=project.fps,
        total_frames=project.total_frames,
        shots=[rs.shot for rs in shots],
    )
    board.check_project(project)
    for rs in shots:
        if not Path(rs.image).is_file():
            raise FileNotFoundError(f"shot {rs.shot.id}: missing plate image {rs.image}")
    return board


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
def _validate_output(
    path: Path,
    project: Project,
    source_audio: Path,
    expected_audio_duration: float,
    *,
    decode: bool = True,
) -> dict:
    """``decode`` counts by decoding every frame, as a delivered film always does."""
    info = probe(path)
    video = _video_stream(info)
    audio = _audio_stream(info)

    frames = _decoded_frames(path) if decode else _count_frames(path)
    duration = float(info["format"]["duration"])
    frame_seconds = 1.0 / project.fps
    tolerance = frame_seconds + 1e-3

    if video.get("codec_name") != "h264":
        raise ValueError(f"unexpected video codec {video.get('codec_name')!r}, want h264")
    if video.get("pix_fmt") != "yuv420p":
        raise ValueError(f"unexpected pixel format {video.get('pix_fmt')!r}, want yuv420p")
    if (int(video.get("width", 0)), int(video.get("height", 0))) != (
        project.width,
        project.height,
    ):
        raise ValueError("rendered dimensions do not match the project")
    if abs(frames - project.total_frames) > _TOLERANT_FRAME_SLACK:
        raise ValueError(f"rendered {frames} frames, expected {project.total_frames}")
    if abs(duration - project.total_frames / project.fps) > tolerance:
        raise ValueError(
            f"rendered duration {duration:.6f}s differs from the timeline by more than one frame"
        )
    if audio.get("codec_name") != "aac":
        raise ValueError(f"unexpected audio codec {audio.get('codec_name')!r}, want aac")
    audio_duration = float(audio.get("duration") or info["format"]["duration"])
    if audio_duration + tolerance < expected_audio_duration:
        raise ValueError(
            f"rendered audio {audio_duration:.4f}s is shorter than the source music "
            f"{expected_audio_duration:.4f}s beyond the {tolerance:.4f}s tolerance"
        )
    if not _is_faststart(path):
        raise ValueError("output is not faststart (moov atom is not first)")

    return {
        "video": {
            "codec_name": video.get("codec_name"),
            "pix_fmt": video.get("pix_fmt"),
            "width": int(video.get("width", 0)),
            "height": int(video.get("height", 0)),
            "frames": frames,
            "faststart": True,
        },
        "audio": {
            "codec_name": audio.get("codec_name"),
            "sample_rate": int(audio.get("sample_rate", 0) or 0),
            "channels": int(audio.get("channels", 0) or 0),
            "duration": audio_duration,
        },
        "duration": duration,
    }
