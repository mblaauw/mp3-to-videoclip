"""Focused, real-FFmpeg tests for the local animated-stills renderer.

Everything here runs locally: tiny 192x108 / 108x192 plates at 24fps and short
generated PCM audio. No network and no paid services are involved. Assertions on
the written file use an independent ``ffprobe`` invocation rather than the
module's own :func:`probe`, so the checks are not self-confirming.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw

from mp3_to_videoclip import render as R
from mp3_to_videoclip.models import Project, RenderShot, Shot

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg and ffprobe are required for the real render tests",
)

FPS = 24
SIZES = {"16:9": (192, 108), "9:16": (108, 192)}
ONE_FRAME = 1.0 / FPS


# --------------------------------------------------------------------------- #
# fixtures and helpers
# --------------------------------------------------------------------------- #
def make_pattern(path: Path, size: tuple[int, int], stripes: int = 8) -> Path:
    """Draw a high-contrast striped pattern so any real motion changes pixels."""
    width, height = size
    image = Image.new("RGB", size)
    draw = ImageDraw.Draw(image)
    for x in range(0, width, stripes):
        draw.rectangle(
            [x, 0, x + stripes // 2, height],
            fill=((x * 7) % 256, (x * 13) % 256, 64),
        )
    draw.line([0, height - 1, width, 0], fill=(255, 255, 255), width=2)
    image.save(path)
    return path


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


def test_real_jpeg_stills_render_as_limited_range_and_reuse_cache(tmp_path):
    project = make_project(tmp_path, duration=1)
    shots = make_shots(tmp_path, project, [(12, 3, "zoom_in"), (12, 0, "pan_left")])
    for rs in shots:
        path = Path(rs.image).with_suffix(".jpg")
        with Image.open(rs.image) as image:
            image.convert("RGB").save(path, quality=95)
        rs.image = str(path)
    audio = make_audio(tmp_path / "audio.wav", 1)
    report = R.render(project, shots, audio, tmp_path / "jpeg.mp4", tmp_path / "work")
    assert report["video"]["pix_fmt"] == "yuv420p"
    assert report["video"]["frames"] == 24
    repeated = R.render(project, shots, audio, tmp_path / "jpeg-v2.mp4", tmp_path / "work")
    assert all(p["cached"] for p in repeated["plates"])


def make_project(
    root: Path, *, duration: float, aspect: str = "16:9", slug: str = "demo"
) -> Project:
    width, height = SIZES[aspect]
    return Project(
        slug=slug,
        title="Demo",
        source_sha256="0" * 64,
        duration=duration,
        aspect=aspect,
        fps=FPS,
        width=width,
        height=height,
    )


def make_shots(
    root: Path,
    project: Project,
    specs: list[tuple[int, int, str]],
    *,
    missing_image: int | None = None,
) -> list[RenderShot]:
    """specs are ``(duration_frames, dissolve_frames, camera)`` in order."""
    shots: list[RenderShot] = []
    cursor = 0
    for index, (duration, dissolve, camera) in enumerate(specs):
        image = root / f"plate-{index}.png"
        image.parent.mkdir(parents=True, exist_ok=True)
        make_pattern(image, (project.width, project.height))
        shot = Shot(
            id=f"shot-{index}",
            start_frame=cursor,
            duration_frames=duration,
            purpose="test",
            image_prompt="test",
            camera=camera,
            dissolve_frames=dissolve,
        )
        path = "/definitely/missing.png" if index == missing_image else str(image)
        shots.append(RenderShot(shot=shot, image=path))
        cursor += duration
    return shots


def ffprobe(path: Path) -> dict:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-count_frames",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return json.loads(out)


def video_frames(path: Path) -> int:
    for stream in ffprobe(path)["streams"]:
        if stream.get("codec_type") == "video":
            return int(stream.get("nb_read_frames") or stream["nb_frames"])
    raise AssertionError("no video stream")


def extract_frame(video: Path, frame: int, out: Path) -> Path:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(video),
            "-vf",
            f"select=eq(n\\,{frame})",
            "-frames:v",
            "1",
            str(out),
        ],
        check=True,
    )
    return out


def mean_abs_diff(a: Path, b: Path) -> float:
    left = Image.open(a).convert("L")
    right = Image.open(b).convert("L")
    diff = ImageChops.difference(left, right)
    total = diff.width * diff.height
    return sum(i * c for i, c in enumerate(diff.histogram())) / total


def stray_files(directory: Path) -> list[str]:
    return [p.name for p in directory.iterdir() if p.name.startswith(".") or p.suffix == ".tmp.mp4"]


# --------------------------------------------------------------------------- #
# tests
# --------------------------------------------------------------------------- #
def test_probe_exposes_format_and_streams(tmp_path):
    audio = make_audio(tmp_path / "mus.wav", 1.0)
    info = R.probe(audio)
    assert info["format"]["format_name"].startswith("wav")
    assert any(s.get("codec_type") == "audio" for s in info["streams"])
    assert float(info["format"]["duration"]) == pytest.approx(1.0, abs=ONE_FRAME)


def test_contact_sheet_labels_shots_and_tolerates_missing_image(tmp_path):
    project = make_project(tmp_path, duration=1.5)
    shots = make_shots(
        tmp_path,
        project,
        [(12, 4, "zoom_in"), (12, 0, "pan_right"), (12, 0, "hold")],
        missing_image=1,
    )
    sheet = R.contact_sheet(shots, tmp_path / "nested" / "sheet.png")
    assert sheet.exists()
    with Image.open(sheet) as image:
        assert image.width > 0 and image.height > 0
    assert sheet.parent == tmp_path / "nested"


def test_render_dissolve_then_cut_is_frame_exact(tmp_path):
    project = make_project(tmp_path, duration=1.5)  # 36 frames
    shots = make_shots(
        tmp_path,
        project,
        [(12, 4, "zoom_in"), (12, 0, "pan_right"), (12, 0, "hold")],
    )
    audio = make_audio(tmp_path / "mus.wav", 1.5)
    audio_before = audio.read_bytes()
    output = tmp_path / "out.mp4"

    report = R.render(project, shots, audio, output, tmp_path / "work")

    assert report["total_frames"] == 36
    assert report["video"]["frames"] == 36
    assert report["video"]["faststart"] is True
    assert report["audio"]["codec_name"] == "aac"

    # independent verification of the written file
    info = ffprobe(output)
    streams = {s["codec_type"]: s for s in info["streams"]}
    assert streams["video"]["codec_name"] == "h264"
    assert streams["video"]["pix_fmt"] == "yuv420p"
    assert (streams["video"]["width"], streams["video"]["height"]) == (192, 108)
    assert video_frames(output) == 36
    assert float(info["format"]["duration"]) == pytest.approx(1.5, abs=ONE_FRAME)
    assert streams["audio"]["codec_name"] == "aac"
    assert float(streams["audio"]["duration"]) >= 1.5 - ONE_FRAME

    # the source music is never altered, and no temporary file is left behind
    assert audio.read_bytes() == audio_before
    assert stray_files(tmp_path) == []


def test_render_cut_then_dissolve_is_frame_exact(tmp_path):
    project = make_project(tmp_path, duration=1.25)  # 30 frames
    shots = make_shots(
        tmp_path,
        project,
        [(10, 0, "hold"), (10, 3, "pan_left"), (10, 0, "zoom_out")],
    )
    audio = make_audio(tmp_path / "mus.wav", 1.25)
    output = tmp_path / "out.mp4"

    report = R.render(project, shots, audio, output, tmp_path / "work")

    assert report["video"]["frames"] == 30
    assert video_frames(output) == 30
    assert float(ffprobe(output)["format"]["duration"]) == pytest.approx(1.25, abs=ONE_FRAME)


def test_render_portrait_exact_dimensions(tmp_path):
    project = make_project(tmp_path, duration=1.0, aspect="9:16")  # 24 frames
    shots = make_shots(tmp_path, project, [(12, 0, "hold"), (12, 0, "zoom_in")])
    audio = make_audio(tmp_path / "mus.wav", 1.0)
    output = tmp_path / "out.mp4"

    report = R.render(project, shots, audio, output, tmp_path / "work")

    assert (report["width"], report["height"]) == (108, 192)
    info = ffprobe(output)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == (108, 192)
    assert video_frames(output) == 24


def test_moves_change_pixels_but_hold_is_static(tmp_path):
    project = make_project(tmp_path, duration=1.0)  # 24 frames
    audio = make_audio(tmp_path / "mus.wav", 1.0)

    moving = make_shots(tmp_path, project, [(24, 0, "zoom_in")])
    move_out = tmp_path / "move.mp4"
    R.render(project, moving, audio, move_out, tmp_path / "work-move")
    first = extract_frame(move_out, 0, tmp_path / "move-0.png")
    last = extract_frame(move_out, 23, tmp_path / "move-23.png")
    assert mean_abs_diff(first, last) > 3.0

    static = make_shots(tmp_path / "static", project, [(24, 0, "hold")])
    still_out = tmp_path / "still.mp4"
    R.render(project, static, audio, still_out, tmp_path / "work-still")
    s_first = extract_frame(still_out, 0, tmp_path / "still-0.png")
    s_last = extract_frame(still_out, 23, tmp_path / "still-23.png")
    assert mean_abs_diff(s_first, s_last) < 2.0


def test_plate_cache_reuses_and_rebuilds_corrupt_entries(tmp_path):
    project = make_project(tmp_path, duration=1.5)
    audio = make_audio(tmp_path / "mus.wav", 1.5)
    work = tmp_path / "work"

    first = R.render(
        project,
        make_shots(tmp_path, project, [(12, 4, "zoom_in"), (12, 0, "hold"), (12, 0, "hold")]),
        audio,
        tmp_path / "one.mp4",
        work,
    )
    assert [p["cached"] for p in first["plates"]] == [False, False, False]

    plate_paths = [Path(p["path"]) for p in first["plates"]]
    mtimes = [p.stat().st_mtime_ns for p in plate_paths]

    second = R.render(
        project,
        make_shots(tmp_path, project, [(12, 4, "zoom_in"), (12, 0, "hold"), (12, 0, "hold")]),
        audio,
        tmp_path / "two.mp4",
        work,
    )
    assert [p["cached"] for p in second["plates"]] == [True, True, True]
    assert [p.stat().st_mtime_ns for p in plate_paths] == mtimes  # immutable on reuse

    # corrupt the first plate; the renderer must notice and rebuild it
    plate_paths[0].write_bytes(b"")

    third = R.render(
        project,
        make_shots(tmp_path, project, [(12, 4, "zoom_in"), (12, 0, "hold"), (12, 0, "hold")]),
        audio,
        tmp_path / "three.mp4",
        work,
    )
    assert [p["cached"] for p in third["plates"]] == [False, True, True]
    assert plate_paths[0].stat().st_size > 0
    assert video_frames(tmp_path / "three.mp4") == 36


def test_plate_key_depends_on_image_contents(tmp_path):
    project = make_project(tmp_path, duration=1.0)
    shots = make_shots(tmp_path, project, [(24, 0, "zoom_in")])
    image = Path(shots[0].image)
    original = R._plate_key(shots[0], project)

    make_pattern(image, (project.width, project.height), stripes=12)
    assert R._plate_key(shots[0], project) != original


def test_render_refuses_to_overwrite_existing_output(tmp_path):
    project = make_project(tmp_path, duration=1.0)
    shots = make_shots(tmp_path, project, [(24, 0, "hold")])
    audio = make_audio(tmp_path / "mus.wav", 1.0)
    output = tmp_path / "out.mp4"

    R.render(project, shots, audio, output, tmp_path / "work")
    before = output.read_bytes()

    with pytest.raises(FileExistsError):
        R.render(project, shots, audio, output, tmp_path / "work")

    assert output.read_bytes() == before
    assert stray_files(tmp_path) == []


def test_render_rejects_timeline_that_does_not_cover_the_project(tmp_path):
    project = make_project(tmp_path, duration=1.5)  # needs 36 frames
    shots = make_shots(tmp_path, project, [(12, 0, "hold"), (12, 0, "hold")])
    audio = make_audio(tmp_path / "mus.wav", 1.5)

    with pytest.raises(ValueError):
        R.render(project, shots, audio, tmp_path / "out.mp4", tmp_path / "work")
    assert not (tmp_path / "out.mp4").exists()


def test_render_rejects_dissolve_on_the_last_shot(tmp_path):
    project = make_project(tmp_path, duration=1.0)
    shots = make_shots(tmp_path, project, [(12, 0, "hold"), (12, 4, "hold")])
    audio = make_audio(tmp_path / "mus.wav", 1.0)

    with pytest.raises(ValueError):
        R.render(project, shots, audio, tmp_path / "out.mp4", tmp_path / "work")
