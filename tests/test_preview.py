"""Real-FFmpeg tests for the local low-resolution preview animatic.

Small local stills and a short generated PCM track keep everything cheap; the
preview itself renders at 640x360 / 360x640 from the original full audio using
the real renderer. No network and no paid services are involved.
"""

import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw

from mp3_to_videoclip import preview as P
from mp3_to_videoclip import render as R
from mp3_to_videoclip.models import CameraPath, Framing, Project, RenderShot, Shot, Storyboard
from mp3_to_videoclip.storage import digest, file_hash

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg and ffprobe are required for the real preview tests",
)

FPS = 24
SOURCE_SIZES = {"16:9": (320, 180), "9:16": (180, 320)}
ONE_FRAME = 1.0 / FPS


def test_placeholder_identity_is_applied_after_maximum_portrait_crop(tmp_path, monkeypatch):
    project = make_project(tmp_path, duration=0.5, aspect="9:16")
    board, _ = make_board(tmp_path, project, [(12, 0, "hold")])
    board.shots[0].camera_path = CameraPath(start=Framing(zoom=2, y=1), end=Framing(zoom=2, y=1))
    filters_seen = []
    original = R._finalize

    def capture(filters, label, *args):
        filters_seen.append(filters)
        return original(filters, label, *args)

    monkeypatch.setattr(R, "_finalize", capture)
    report = P.build_preview(
        tmp_path, project, board, [], tmp_path / "preview.mp4", tmp_path / "work"
    )
    assert report["placeholder_shots"] == [board.shots[0].id]
    assert f"PLACEHOLDER - NOT GENERATED / {board.shots[0].id}" in filters_seen[0]
    assert "gte(n,0)*lt(n,12)" in filters_seen[0]
    assert filters_seen[0].index("PLACEHOLDER - NOT GENERATED") > filters_seen[0].index(
        "[marked_preview]"
    )


def test_interrupted_preview_plate_is_rebuilt(tmp_path):
    project = make_project(tmp_path, duration=0.5)
    board, _ = make_board(tmp_path, project, [(12, 0, "hold")])
    work = tmp_path / "work"
    first = P.build_preview(tmp_path, project, board, [], tmp_path / "first.mp4", work)
    plate = next((work / P.INPUTS_DIRNAME).glob("*.png"))
    plate.write_bytes(b"interrupted-png")
    second = P.build_preview(tmp_path, project, board, [], tmp_path / "second.mp4", work)
    assert second["video"]["frames"] == first["video"]["frames"] == 12
    with Image.open(plate) as image:
        image.verify()


# --------------------------------------------------------------------------- #
# fixtures and helpers
# --------------------------------------------------------------------------- #
def make_audio(path: Path, seconds: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def make_plate(path: Path, size: tuple[int, int]) -> Path:
    width, height = size
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", size, (20, 20, 24))
    draw = ImageDraw.Draw(image)
    for x in range(0, width, 20):
        draw.rectangle([x, 0, x + 9, height], fill=((x * 7) % 256, (x * 11) % 256, 90))
    draw.rectangle([0, 0, width // 4, height // 4], fill=(255, 0, 0))
    image.save(path)
    return path


def make_project(root: Path, *, duration: float, aspect: str = "16:9") -> Project:
    width, height = SOURCE_SIZES[aspect]
    make_audio(root / "media" / "song.wav", duration)
    return Project(
        slug="demo",
        title="Demo",
        source="media/song.wav",
        source_sha256=file_hash(root / "media" / "song.wav"),
        duration=duration,
        aspect=aspect,
        fps=FPS,
        width=width,
        height=height,
    )


def make_board(
    root: Path, project: Project, specs: list[tuple[int, int, str]]
) -> tuple[Storyboard, list[Path]]:
    """specs are ``(duration_frames, dissolve_frames, camera)`` in order."""
    shots: list[Shot] = []
    images: list[Path] = []
    cursor = 0
    for index, (duration, dissolve, camera) in enumerate(specs):
        image = make_plate(root / "assets" / f"still-{index}.png", (project.width, project.height))
        images.append(image)
        shots.append(
            Shot(
                id=f"shot-{index}",
                start_frame=cursor,
                duration_frames=duration,
                purpose=f"purpose {index}",
                image_prompt="test",
                camera=camera,  # type: ignore[arg-type]
                dissolve_frames=dissolve,
                framing="wide" if index % 2 == 0 else "close_up",
            )
        )
        cursor += duration
    return (
        Storyboard(
            aspect=project.aspect, fps=project.fps, total_frames=project.total_frames, shots=shots
        ),
        images,
    )


def available_shots(board: Storyboard, images: list[Path], indexes: list[int]) -> list[RenderShot]:
    return [RenderShot(shot=board.shots[i], image=str(images[i])) for i in indexes]


def ffprobe(path: Path) -> dict:
    import json

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


def video_stream(path: Path) -> dict:
    return next(s for s in ffprobe(path)["streams"] if s["codec_type"] == "video")


def audio_stream(path: Path) -> dict:
    return next(s for s in ffprobe(path)["streams"] if s["codec_type"] == "audio")


def video_frames(path: Path) -> int:
    stream = video_stream(path)
    return int(stream.get("nb_read_frames") or stream["nb_frames"])


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
    with Image.open(a).convert("L") as left, Image.open(b).convert("L") as right:
        diff = ImageChops.difference(left, right)
        return sum(i * c for i, c in enumerate(diff.histogram())) / (diff.width * diff.height)


def files_under(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}


def labelled_placeholder(path: Path) -> bool:
    """A dark stand-in with bright banner text in its top band."""
    with Image.open(path).convert("RGB") as image:
        px = image.load()
        band = image.height // 4
        bright = sum(
            1 for x in range(0, image.width, 2) for y in range(0, band, 2) if max(px[x, y]) > 200
        )
        dark = sum(
            1
            for x in range(0, image.width, 8)
            for y in range(band, image.height, 8)
            if max(px[x, y]) < 80
        )
    return bright > 10 and dark > 10


# --------------------------------------------------------------------------- #
# tests
# --------------------------------------------------------------------------- #
def test_build_preview_mixed_cut_and_dissolve_is_frame_exact(tmp_path):
    root = tmp_path / "project"
    project = make_project(root, duration=1.5)  # 36 frames
    board, images = make_board(
        root, project, [(12, 4, "zoom_in"), (12, 0, "pan_right"), (12, 0, "hold")]
    )
    available = available_shots(board, images, [0, 1])
    audio = root / project.source
    audio_before = audio.read_bytes()
    image_hashes = [file_hash(p) for p in images]
    output = root / "renders" / "preview-v001.mp4"

    # No approvals exist for this project: a preview must never require one.
    report = P.build_preview(root, project, board, available, output, root / "work")

    assert report["preview"] is True
    assert report["preview_version"] == P.PREVIEW_VERSION
    assert report["output"] == str(output)
    assert output.is_file()
    assert report["placeholder_shots"] == ["shot-2"]
    assert report["actual_shots"] == ["shot-0", "shot-1"]
    assert report["approved_dimensions"] == {"width": project.width, "height": project.height}
    assert (report["width"], report["height"]) == P.PREVIEW_DIMENSIONS["16:9"]
    assert report["total_frames"] == 36
    assert report["input_hash"] == digest(
        {
            "storyboard": board.model_dump(),
            "available": [
                {"id": rs.shot.id, "image_sha256": file_hash(Path(rs.image))} for rs in available
            ],
        }
    )

    # Independent inspection of the written file: preview format, exact frames and
    # the original full audio.
    info = ffprobe(output)
    video = video_stream(output)
    assert (int(video["width"]), int(video["height"])) == (640, 360)
    assert video["codec_name"] == "h264" and video["pix_fmt"] == "yuv420p"
    assert video_frames(output) == 36
    assert float(info["format"]["duration"]) == pytest.approx(1.5, abs=ONE_FRAME)
    audio_info = audio_stream(output)
    assert audio_info["codec_name"] == "aac"
    assert float(audio_info["duration"]) >= 1.5 - ONE_FRAME
    # The preview is bound to the project's own, unmodified full audio track.
    assert report["audio_path"] == str(audio)
    assert report["audio_sha256"] == file_hash(audio)

    # The marking survives encoding: the first frame still carries banner text.
    frame = extract_frame(output, 0, tmp_path / "preview-frame.png")
    assert labelled_placeholder(frame)

    # The source music and every approved still are read-only inputs.
    assert audio.read_bytes() == audio_before
    assert [file_hash(p) for p in images] == image_hashes
    # The marked preview plates are derived copies, not the sources.
    size = P.PREVIEW_DIMENSIONS["16:9"]
    derived = root / "work" / "preview-inputs"
    available_plate = (
        derived / f"{P._plate_key('actual', board.shots[0], size, file_hash(images[0]))}.png"
    )
    missing_plate = derived / f"{P._plate_key('placeholder', board.shots[2], size, '')}.png"
    assert available_plate.is_file() and missing_plate.is_file()
    assert len(list(derived.iterdir())) == 3
    assert mean_abs_diff(images[0], available_plate) > 1.0
    assert file_hash(images[0]) == image_hashes[0]

    # Nothing is written outside the working directory and the render directory.
    stray = (
        files_under(root)
        - {str(p.relative_to(root)) for p in root.glob("work/**/*")}
        - {str(p.relative_to(root)) for p in root.glob("renders/**/*")}
    )
    assert stray == {
        "media/song.wav",
        "assets/still-0.png",
        "assets/still-1.png",
        "assets/still-2.png",
    }

    # Preview output is versioned/no-clobber at the render layer.
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        P.build_preview(root, project, board, available, output, root / "work")
    assert output.read_bytes() == before


def test_build_preview_portrait_is_360x640(tmp_path):
    root = tmp_path / "project"
    project = make_project(root, duration=1.0, aspect="9:16")  # 24 frames
    board, images = make_board(root, project, [(12, 3, "hold"), (12, 0, "zoom_out")])
    available = available_shots(board, images, [0])
    output = root / "renders" / "preview-v001.mp4"

    report = P.build_preview(root, project, board, available, output, root / "work")

    assert (report["width"], report["height"]) == (360, 640)
    video = video_stream(output)
    assert (int(video["width"]), int(video["height"])) == (360, 640)
    assert video_frames(output) == 24
    assert report["placeholder_shots"] == ["shot-1"]
    assert report["actual_shots"] == ["shot-0"]


def test_build_preview_placeholders_are_labelled_and_deterministic(tmp_path):
    root = tmp_path / "project"
    project = make_project(root, duration=1.5)
    board, images = make_board(
        root, project, [(12, 4, "zoom_in"), (12, 0, "pan_left"), (12, 0, "hold")]
    )
    # Only one still is available: two shots must be explicit placeholders.
    available = available_shots(board, images, [0])
    workdir = root / "work"

    first = P.build_preview(
        root, project, board, available, root / "renders" / "preview-v001.mp4", workdir
    )
    assert first["placeholder_shots"] == ["shot-1", "shot-2"]
    assert first["actual_shots"] == ["shot-0"]

    size = P.PREVIEW_DIMENSIONS["16:9"]
    placeholders = {
        shot_id: workdir
        / "preview-inputs"
        / f"{P._plate_key('placeholder', board.shots[index], size, '')}.png"
        for index, shot_id in ((1, "shot-1"), (2, "shot-2"))
    }
    actual = (
        workdir
        / "preview-inputs"
        / f"{P._plate_key('actual', board.shots[0], size, file_hash(images[0]))}.png"
    )
    for path in [*placeholders.values(), actual]:
        assert path.is_file()
    # Each missing shot gets its own labelled image; repetition is never passed
    # off as generated work.
    assert placeholders["shot-1"].read_bytes() != placeholders["shot-2"].read_bytes()
    assert all(labelled_placeholder(path) for path in placeholders.values())
    assert placeholders["shot-1"] != actual

    # Rebuilding into a new version reuses the same derived plates.
    mtimes = {path: path.stat().st_mtime_ns for path in [*placeholders.values(), actual]}
    second = P.build_preview(
        root, project, board, available, root / "renders" / "preview-v002.mp4", workdir
    )
    assert second["placeholder_shots"] == first["placeholder_shots"]
    assert (root / "renders" / "preview-v002.mp4").is_file()
    assert {path: path.stat().st_mtime_ns for path in mtimes} == mtimes
