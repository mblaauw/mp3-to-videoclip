"""Real-FFmpeg tests for the optional start/end camera path.

Tiny local plates (192x108 / 108x192) at 24fps with a non-central coloured
subject prove that a custom path overrides the coarse ``camera`` selector, hits
its start/end focus and that its easing changes the mid-path framing. Everything
is local: no network, no paid services.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw

from mp3_to_videoclip import render as R
from mp3_to_videoclip.models import CameraPath, Framing, Project, RenderShot, Shot
from mp3_to_videoclip.storage import digest, file_hash

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg and ffprobe are required for the real camera-path tests",
)

FPS = 24
SIZES = {"16:9": (192, 108), "9:16": (108, 192)}
ONE_FRAME = 1.0 / FPS


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def make_project(root: Path, *, duration: float, aspect: str = "16:9") -> Project:
    width, height = SIZES[aspect]
    return Project(
        slug="demo",
        title="Demo",
        source_sha256="0" * 64,
        duration=duration,
        aspect=aspect,
        fps=FPS,
        width=width,
        height=height,
    )


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


def make_subject(path: Path, size: tuple[int, int], *, vertical: bool = False) -> Path:
    """Red and blue blocks pinned to opposite edges of the frame."""
    width, height = size
    image = Image.new("RGB", size, (16, 16, 16))
    draw = ImageDraw.Draw(image)
    if vertical:
        draw.rectangle([0, 0, width, height // 6], fill=(255, 0, 0))
        draw.rectangle([0, height - height // 6, width, height], fill=(0, 0, 255))
    else:
        draw.rectangle([0, 0, width // 6, height], fill=(255, 0, 0))
        draw.rectangle([width - width // 6, 0, width, height], fill=(0, 0, 255))
    image.save(path)
    return path


def make_shot(
    image: Path,
    *,
    camera: str = "hold",
    camera_path: CameraPath | None = None,
    duration_frames: int = 24,
    shot_id: str = "shot-0",
) -> RenderShot:
    return RenderShot(
        shot=Shot(
            id=shot_id,
            start_frame=0,
            duration_frames=duration_frames,
            purpose="test",
            image_prompt="test",
            camera=camera,  # type: ignore[arg-type]
            camera_path=camera_path,
        ),
        image=str(image),
    )


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


def video_frames(path: Path) -> int:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=nb_read_frames",
            "-of",
            "default=nokey=1:noprint_wrappers=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return int(out.strip())


def mean_abs_diff(a: Path, b: Path) -> float:
    with Image.open(a).convert("L") as left, Image.open(b).convert("L") as right:
        diff = ImageChops.difference(left, right)
        return sum(i * c for i, c in enumerate(diff.histogram())) / (diff.width * diff.height)


def _count(path: Path, x_range, y_range, predicate) -> int:
    with Image.open(path).convert("RGB") as image:
        px = image.load()
        return sum(
            1 for x in x_range(image.width) for y in y_range(image.height) if predicate(px[x, y])
        )


def left_red(path: Path) -> int:
    return _count(
        path,
        lambda w: range(w // 6),
        lambda h: range(0, h, 4),
        lambda p: p[0] > 120 and p[1] < 80 and p[2] < 80,
    )


def right_blue(path: Path) -> int:
    return _count(
        path,
        lambda w: range(w - w // 6, w),
        lambda h: range(0, h, 4),
        lambda p: p[2] > 120 and p[0] < 80 and p[1] < 80,
    )


def top_red(path: Path) -> int:
    with Image.open(path).convert("RGB") as image:
        px = image.load()
        return sum(
            1
            for y in range(image.height // 6)
            for x in range(0, image.width, 4)
            if px[x, y][0] > 120 and px[x, y][2] < 80
        )


def bottom_blue(path: Path) -> int:
    with Image.open(path).convert("RGB") as image:
        px = image.load()
        return sum(
            1
            for y in range(image.height - image.height // 6, image.height)
            for x in range(0, image.width, 4)
            if px[x, y][2] > 120 and px[x, y][0] < 80
        )


def legacy_key(rs: RenderShot, project: Project) -> str:
    """The exact pre-camera-path plate key payload, computed independently."""
    return digest(
        {
            "version": R.PLATE_CACHE_VERSION,
            "shot": rs.shot.id,
            "camera": rs.shot.camera,
            "duration_frames": rs.shot.duration_frames,
            "dissolve_frames": rs.shot.dissolve_frames,
            "width": project.width,
            "height": project.height,
            "fps": project.fps,
            "image_sha256": file_hash(Path(rs.image)),
        }
    )[:32]


# --------------------------------------------------------------------------- #
# tests
# --------------------------------------------------------------------------- #
def test_camera_path_overrides_selector_and_hits_both_endpoints(tmp_path):
    project = make_project(tmp_path, duration=1.0)
    plate = make_subject(tmp_path / "subject.png", SIZES["16:9"])
    audio = make_audio(tmp_path / "a.wav", 1.0)
    path = CameraPath(
        start=Framing(zoom=1.5, x=0.0, y=0.5),
        end=Framing(zoom=2.0, x=1.0, y=0.5),
        easing="linear",
    )
    # ``hold`` must be superseded by the explicit camera path.
    shots = [make_shot(plate, camera="hold", camera_path=path)]

    report = R.render(project, shots, audio, tmp_path / "out.mp4", tmp_path / "work")
    assert video_frames(tmp_path / "out.mp4") == 24
    assert report["shots"][0]["camera"] == "hold"
    assert report["shots"][0]["camera_path"]["start"] == {"zoom": 1.5, "x": 0.0, "y": 0.5}
    assert report["shots"][0]["camera_path"]["easing"] == "linear"

    first = extract_frame(tmp_path / "out.mp4", 0, tmp_path / "f0.png")
    last = extract_frame(tmp_path / "out.mp4", 23, tmp_path / "f23.png")

    # Start framing focuses the left red block; the end focuses the blue right one.
    assert left_red(first) > 0 and right_blue(first) == 0
    assert right_blue(last) > 0 and left_red(last) == 0
    # A real move, i.e. not the static ``hold`` we passed as the legacy camera.
    assert mean_abs_diff(first, last) > 5.0


def test_camera_path_portrait_moves_vertically(tmp_path):
    project = make_project(tmp_path, duration=1.0, aspect="9:16")
    plate = make_subject(tmp_path / "subject.png", SIZES["9:16"], vertical=True)
    audio = make_audio(tmp_path / "a.wav", 1.0)
    path = CameraPath(
        start=Framing(zoom=1.5, x=0.5, y=0.0),
        end=Framing(zoom=2.0, x=0.5, y=1.0),
        easing="linear",
    )
    shots = [make_shot(plate, camera="pan_left", camera_path=path)]

    R.render(project, shots, audio, tmp_path / "out.mp4", tmp_path / "work")
    info = json.loads(
        subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_streams",
                str(tmp_path / "out.mp4"),
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == (108, 192)

    first = extract_frame(tmp_path / "out.mp4", 0, tmp_path / "f0.png")
    last = extract_frame(tmp_path / "out.mp4", 23, tmp_path / "f23.png")
    assert top_red(first) > 0 and bottom_blue(first) == 0
    assert bottom_blue(last) > 0 and top_red(last) == 0


def test_camera_path_easing_changes_midpath_only(tmp_path):
    project = make_project(tmp_path, duration=1.0)
    plate = make_subject(tmp_path / "subject.png", SIZES["16:9"])
    audio = make_audio(tmp_path / "a.wav", 1.0)

    def path(easing: str) -> CameraPath:
        return CameraPath(
            start=Framing(zoom=1.5, x=0.0, y=0.5),
            end=Framing(zoom=2.0, x=1.0, y=0.5),
            easing=easing,  # type: ignore[arg-type]
        )

    for easing in ("linear", "smoothstep"):
        shots = [make_shot(plate, camera="hold", camera_path=path(easing))]
        R.render(
            project,
            shots,
            audio,
            tmp_path / f"{easing}.mp4",
            tmp_path / f"work-{easing}",
        )

    def frames_for(easing: str, number: int) -> Path:
        return extract_frame(
            tmp_path / f"{easing}.mp4", number, tmp_path / f"{easing}-{number}.png"
        )

    # Identical endpoints: the easing only reshapes the interpolation between them.
    assert mean_abs_diff(frames_for("linear", 0), frames_for("smoothstep", 0)) < 1.0
    assert mean_abs_diff(frames_for("linear", 23), frames_for("smoothstep", 23)) < 1.0
    # Smoothstep lags linear at the quarter point (0.156 vs 0.25 progress), so its
    # crop is still further left and shows more of the left red block.
    linear_quarter = frames_for("linear", 6)
    smooth_quarter = frames_for("smoothstep", 6)
    assert left_red(smooth_quarter) > left_red(linear_quarter)
    assert mean_abs_diff(linear_quarter, smooth_quarter) > 2.0


def test_camera_path_cache_reuse_and_invalidation(tmp_path):
    project = make_project(tmp_path, duration=1.0)
    plate = make_subject(tmp_path / "subject.png", SIZES["16:9"])
    audio = make_audio(tmp_path / "a.wav", 1.0)

    def path(end_x: float) -> CameraPath:
        return CameraPath(
            start=Framing(zoom=1.5, x=0.0, y=0.5),
            end=Framing(zoom=2.0, x=end_x, y=0.5),
            easing="linear",
        )

    first = R.render(
        project,
        [make_shot(plate, camera="hold", camera_path=path(1.0))],
        audio,
        tmp_path / "one.mp4",
        tmp_path / "work",
    )
    assert [p["cached"] for p in first["plates"]] == [False]

    repeated = R.render(
        project,
        [make_shot(plate, camera="hold", camera_path=path(1.0))],
        audio,
        tmp_path / "two.mp4",
        tmp_path / "work",
    )
    assert [p["cached"] for p in repeated["plates"]] == [True]
    assert repeated["plates"][0]["cache_key"] == first["plates"][0]["cache_key"]

    # A different end framing must not reuse the previous plate.
    changed = R.render(
        project,
        [make_shot(plate, camera="hold", camera_path=path(0.25))],
        audio,
        tmp_path / "three.mp4",
        tmp_path / "work",
    )
    assert [p["cached"] for p in changed["plates"]] == [False]
    assert changed["plates"][0]["cache_key"] != first["plates"][0]["cache_key"]

    # Same path, other easing: distinct plates as well.
    eased = R.render(
        project,
        [
            make_shot(
                plate,
                camera="hold",
                camera_path=CameraPath(
                    start=Framing(zoom=1.5, x=0.0, y=0.5),
                    end=Framing(zoom=2.0, x=1.0, y=0.5),
                    easing="smoothstep",
                ),
            )
        ],
        audio,
        tmp_path / "four.mp4",
        tmp_path / "work",
    )
    assert eased["plates"][0]["cache_key"] != first["plates"][0]["cache_key"]


def test_legacy_camera_key_and_report_are_unchanged_without_camera_path(tmp_path):
    project = make_project(tmp_path, duration=1.0)
    plate = make_subject(tmp_path / "subject.png", SIZES["16:9"])
    audio = make_audio(tmp_path / "a.wav", 1.0)
    legacy = make_shot(plate, camera="zoom_in")
    assert legacy.shot.camera_path is None

    # The key payload for legacy shots is byte-identical to the pre-path scheme.
    assert R._plate_key(legacy, project) == legacy_key(legacy, project)
    # And it does not depend on the (absent) camera path field.
    explicit_none = make_shot(plate, camera="zoom_in", camera_path=None)
    assert R._plate_key(explicit_none, project) == R._plate_key(legacy, project)

    with_path = make_shot(
        plate,
        camera="zoom_in",
        camera_path=CameraPath(start=Framing(zoom=1.2), end=Framing(zoom=1.8)),
    )
    assert R._plate_key(with_path, project) != R._plate_key(legacy, project)

    report = R.render(project, [legacy], audio, tmp_path / "legacy.mp4", tmp_path / "work")
    assert "camera_path" not in report["shots"][0]
    assert report["video"]["frames"] == 24
