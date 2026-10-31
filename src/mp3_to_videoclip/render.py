"""Local FFmpeg animated-stills renderer for an approved still set.

Timeline model
--------------
Every shot owns exactly ``duration_frames`` of the final output. A shot with
``dissolve_frames = d`` additionally carries ``d`` *handle* frames that are only
consumed while cross-fading into the next shot, so a transition can never
shorten the film:

* each plate is built with ``duration_frames + dissolve_frames`` frames;
* a cross-fade starts exactly at the next shot's allocated start frame, i.e. the
  cumulative sum of the preceding ``duration_frames`` (the canonical timeline
  boundary);
* a zero-dissolve boundary is a plain concatenation of two full plates.

Because ``sum(duration_frames + dissolve_frames) - sum(dissolve_frames) ==
sum(duration_frames)``, the assembled film is exactly ``project.total_frames``
long, with no gaps and no shortened transitions.

The renderer is local: no network, no paid services. It only ever *reads* the
source music, writes an immutable per-plate cache into ``workdir`` and produces
the final MP4 by temporary file + atomic replace. Captions, sound effects and
program fades are out of scope; only the requested dissolves blend shots.

An optional, versioned brand package adds a static opening plate over the first
seconds of the rendered video. The plate is composited *after* every camera
transform and *before* the preview marking mark, it is cached as a
content-keyed PNG in ``workdir/brand`` and it never touches the audio: no
pre-roll, no added sound, no delay and no shortened song.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .branding import BRAND_RENDER_VERSION, brand_plate_key, pack_hash, render_brand_plate
from .models import BrandPackage, CameraPath, Project, RenderShot, Storyboard
from .storage import digest, file_hash

# Bump when the plate filtergraph or cache key semantics change so stale plates
# are never reused across renderer revisions.
PLATE_CACHE_VERSION = "plate-v2-limited-range"

# Only part of a custom camera-path plate key: legacy (``camera_path is None``)
# keys stay byte-identical, so this version is mixed in exclusively for
# ``camera_path`` shots and never touches PLATE_CACHE_VERSION.
CAMERA_PATH_CACHE_VERSION = "camera-path-v1"

# Restrained moves: never crop into more than this fraction of the plate.
ZOOM_RANGE = 0.08
# Working upscale before zoompan keeps sub-pixel pans/zooms from jittering.
PLATE_UPSCALE = 3

PLATE_PRESET = "veryfast"
FINAL_PRESET = "medium"
FINAL_CRF = 18
AUDIO_BITRATE = "192k"
#: Sample rate used to count a source's audio; the count is what matters, not fidelity.
DURATION_SAMPLE_RATE = 8000

_DEFAULT_THREADS_CAP = 4
_TOLERANT_FRAME_SLACK = 1

_MOVES = ("hold", "zoom_in", "zoom_out", "pan_left", "pan_right")

# Brand plate fades are short and clamped to a third of the identity's own
# duration; the overlay itself is only visible inside the brand window.
BRAND_PLATE_FADE_SECONDS = 0.5


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
    out = _run(
        [
            _binary("ffprobe"),
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
        ]
    ).strip()
    try:
        return int(out)
    except ValueError as e:
        raise ValueError(f"could not read frame count from {path}") from e


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


def _plate_key(rs: RenderShot, project: Project) -> str:
    payload = {
        "version": PLATE_CACHE_VERSION,
        "shot": rs.shot.id,
        "camera": rs.shot.camera,
        "duration_frames": rs.shot.duration_frames,
        "dissolve_frames": rs.shot.dissolve_frames,
        "width": project.width,
        "height": project.height,
        "fps": project.fps,
        "image_sha256": file_hash(Path(rs.image)),
    }
    # ``camera_path`` is only mixed in when set, so legacy keys retain their
    # exact original bytes and the legacy plate cache keeps being reused.
    if rs.shot.camera_path is not None:
        payload["camera_path_version"] = CAMERA_PATH_CACHE_VERSION
        payload["camera_path"] = rs.shot.camera_path.model_dump()
    return digest(payload)[:32]


def _plate_frames(rs: RenderShot) -> int:
    return rs.shot.duration_frames + rs.shot.dissolve_frames


# --------------------------------------------------------------------------- #
# plates
# --------------------------------------------------------------------------- #
def _zoompan(filter_frames: int, camera: str) -> str:
    if camera not in _MOVES:
        raise ValueError(f"unsupported camera {camera!r}")
    last = max(filter_frames - 1, 1)
    centre_x = "(iw-iw/zoom)/2"
    centre_y = "(ih-ih/zoom)/2"
    if camera == "hold":
        z, x = "1", centre_x
    elif camera == "zoom_in":
        z, x = f"1+{ZOOM_RANGE}*on/{last}", centre_x
    elif camera == "zoom_out":
        z, x = f"1+{ZOOM_RANGE}-{ZOOM_RANGE}*on/{last}", centre_x
    elif camera == "pan_left":
        z, x = f"1+{ZOOM_RANGE}", f"(iw-iw/zoom)*(1-on/{last})"
    else:  # pan_right
        z, x = f"1+{ZOOM_RANGE}", f"(iw-iw/zoom)*on/{last}"
    return f"zoompan=z='{z}':x='{x}':y='{centre_y}':d={filter_frames}:s={{w}}x{{h}}:fps={{fps}}"


def _camera_path_zoompan(filter_frames: int, path: CameraPath) -> str:
    """Explicit start/end crop framing, interpolated across the plate.

    ``x``/``y`` are normalized positions inside the *available* crop overflow
    (0 = left/top edge of what the current zoom exposes, 1 = right/bottom), so
    the normalized values stay meaningful at every zoom level. Progress runs
    0..1 over the allocated plate handle frames (duration + dissolve), matching
    the legacy ``_zoompan`` convention, and is optionally shaped by smoothstep.
    """
    last = max(filter_frames - 1, 1)
    linear = f"(on/{last})"
    progress = f"({linear}*{linear}*(3-2*{linear}))" if path.easing == "smoothstep" else linear

    start, end = path.start, path.end
    zoom_expression = f"{start.zoom}+({end.zoom}-{start.zoom})*{progress}"
    # zoompan x/y are absolute offsets from the left/top edge; the normalized
    # position is scaled by the overflow the current zoom exposes.
    x_expression = f"(iw-iw/zoom)*({start.x}+({end.x}-{start.x})*{progress})"
    y_expression = f"(ih-ih/zoom)*({start.y}+({end.y}-{start.y})*{progress})"
    return (
        f"zoompan=z='{zoom_expression}':x='{x_expression}':y='{y_expression}'"
        f":d={filter_frames}:s={{w}}x{{h}}:fps={{fps}}"
    )


def _plate_filter(rs: RenderShot, project: Project) -> str:
    frames = _plate_frames(rs)
    up_w = project.width * PLATE_UPSCALE
    up_h = project.height * PLATE_UPSCALE
    # A custom camera path supersedes the coarse legacy camera selector.
    if rs.shot.camera_path is not None:
        expression = _camera_path_zoompan(frames, rs.shot.camera_path)
    else:
        expression = _zoompan(frames, rs.shot.camera)
    zoompan = expression.format(w=project.width, h=project.height, fps=project.fps)
    return (
        f"scale={up_w}:{up_h}:force_original_aspect_ratio=increase:out_range=tv,"
        f"crop={up_w}:{up_h},format=yuv420p,{zoompan},setparams=range=limited"
    )


def _build_plate(rs: RenderShot, project: Project, plate: Path) -> None:
    frames = _plate_frames(rs)
    threads = _max_threads()
    tmp = plate.with_name(f".{plate.name}.{os.getpid()}.tmp.mp4")
    argv = [
        _binary("ffmpeg"),
        "-nostdin",
        "-y",
        "-loglevel",
        "error",
        "-filter_threads",
        str(threads),
        "-filter_complex_threads",
        str(threads),
        "-i",
        rs.image,
        "-vf",
        _plate_filter(rs, project),
        "-frames:v",
        str(frames),
        "-c:v",
        "libx264",
        "-preset",
        PLATE_PRESET,
        "-crf",
        "16",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(project.fps),
        "-an",
        "-threads",
        str(threads),
        str(tmp),
    ]
    try:
        _run(argv)
        produced = _count_frames(tmp)
        if produced != frames:
            raise RuntimeError(f"plate {rs.shot.id}: expected {frames} frames, got {produced}")
        os.replace(tmp, plate)
    finally:
        tmp.unlink(missing_ok=True)


def _plate_valid(plate: Path, rs: RenderShot, project: Project) -> bool:
    if not plate.is_file() or plate.stat().st_size == 0:
        return False
    try:
        info = probe(plate)
        stream = _video_stream(info)
        if (
            stream.get("codec_name") != "h264"
            or stream.get("pix_fmt") != "yuv420p"
            or int(stream.get("width", 0)) != project.width
            or int(stream.get("height", 0)) != project.height
        ):
            return False
        return _count_frames(plate) == _plate_frames(rs)
    except (RuntimeError, ValueError, OSError):
        return False


# --------------------------------------------------------------------------- #
# brand plate
# --------------------------------------------------------------------------- #
def _brand_plate_valid(plate: Path, project: Project) -> bool:
    if not plate.is_file() or plate.stat().st_size == 0:
        return False
    try:
        with Image.open(plate) as image:
            return image.mode == "RGBA" and image.size == (project.width, project.height)
    except (OSError, ValueError):
        return False


def _brand_plate(brand: BrandPackage, project: Project, workdir: Path) -> Path:
    """Deterministic full-frame plate cache; the source image is never written."""
    cache = workdir / "brand"
    cache.mkdir(parents=True, exist_ok=True)
    plate = cache / f"{brand_plate_key(brand, project.width, project.height)}.png"
    if not _brand_plate_valid(plate, project):
        render_brand_plate(brand, project, plate)
    return plate


def _brand_overlay(filters: str, label: str, brand_index: int, seconds: float) -> tuple[str, str]:
    """Overlay the cached plate for exactly the first ``seconds`` of the film.

    The plate is looped at the project frame rate and bounded with ``-t`` at the
    input, so the looped image stream is finite; the final stream is limited to
    the project frame count. ``lt(t, seconds)`` ends the overlay on the frame
    boundary instead of one frame later.
    """
    fade = min(BRAND_PLATE_FADE_SECONDS, seconds / 3)
    fade_out_at = max(0.0, seconds - fade)
    filters += (
        f";[{brand_index}:v]format=rgba,"
        f"fade=t=in:st=0:d={fade:.6f}:alpha=1,"
        f"fade=t=out:st={fade_out_at:.6f}:d={fade:.6f}:alpha=1,"
        f"setpts=PTS-STARTPTS[brand_plate]"
        f";[{label}][brand_plate]overlay=0:0:eof_action=repeat:"
        f"enable='lt(t,{seconds:.6f})'[branded]"
        f";[branded]format=yuv420p,setparams=range=limited[branded_plate]"
    )
    return filters, "branded_plate"


# --------------------------------------------------------------------------- #
# assembly
# --------------------------------------------------------------------------- #
def _normalise(index: int, project: Project) -> str:
    return f"[{index}:v]settb=AVTB,fps={project.fps},format=yuv420p,setparams=range=limited,setpts=PTS-STARTPTS[p{index}]"


def _assembly_filter(shots: list[RenderShot], project: Project) -> tuple[str, str]:
    """Return ``(filter_complex, final_label)`` for the whole timeline."""
    fps = project.fps
    filters = [_normalise(i, project) for i in range(len(shots))]
    current = "p0"
    for i in range(1, len(shots)):
        outgoing = shots[i - 1].shot.dissolve_frames
        offset_frames = shots[i].shot.start_frame
        raw = f"j{i}"
        if outgoing > 0:
            filters.append(
                f"[{current}][p{i}]xfade=transition=fade:duration={outgoing / fps}"
                f":offset={offset_frames / fps}[{raw}]"
            )
        else:
            filters.append(f"[{current}][p{i}]concat=n=2:v=1:a=0[{raw}]")
        label = f"c{i}"
        # concat resets frame-rate metadata; xfade requires matching constant FPS.
        filters.append(
            f"[{raw}]settb=AVTB,fps={fps},format=yuv420p,setparams=range=limited,setpts=PTS-STARTPTS[{label}]"
        )
        current = label
    return ";".join(filters), current


def _finalize(
    filters: str,
    label: str,
    plates: list[Path],
    audio: Path,
    output: Path,
    project: Project,
    *,
    brand_plate: Path | None = None,
    brand_seconds: float = 0.0,
) -> None:
    threads = _max_threads()
    argv = [
        _binary("ffmpeg"),
        "-nostdin",
        "-y",
        "-loglevel",
        "error",
        "-filter_threads",
        str(threads),
        "-filter_complex_threads",
        str(threads),
    ]
    for plate in plates:
        argv += ["-i", str(plate)]
    # The brand plate is a real extra input (never a path inside a filter
    # string) so it is passed positionally here; the audio index follows it.
    if brand_plate is not None:
        argv += [
            "-loop",
            "1",
            "-framerate",
            str(project.fps),
            "-t",
            f"{brand_seconds:.6f}",
            "-i",
            str(brand_plate),
        ]
    audio_index = len(plates) + (1 if brand_plate is not None else 0)
    argv += ["-i", str(audio)]
    argv += [
        "-filter_complex",
        filters,
        "-map",
        f"[{label}]",
        "-map",
        f"{audio_index}:a:0",
        "-c:v",
        "libx264",
        "-preset",
        FINAL_PRESET,
        "-crf",
        str(FINAL_CRF),
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(project.fps),
    ]
    if brand_plate is not None:
        # The looped plate can never lengthen the film past the timeline.
        argv += ["-frames:v", str(project.total_frames)]
    argv += [
        "-movflags",
        "+faststart",
        "-c:a",
        "aac",
        "-b:a",
        AUDIO_BITRATE,
        "-max_muxing_queue_size",
        "1024",
        "-threads",
        str(threads),
        str(output),
    ]
    _run(argv)


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
def _validate_output(
    path: Path, project: Project, source_audio: Path, expected_audio_duration: float
) -> dict:
    info = probe(path)
    video = _video_stream(info)
    audio = _audio_stream(info)

    frames = _count_frames(path)
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


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def render(
    project: Project,
    shots: list[RenderShot],
    audio: Path,
    output: Path,
    workdir: Path,
    *,
    preview_banner: bool = False,
    preview_placeholders: tuple[str, ...] = (),
    brand: BrandPackage | None = None,
    titles: dict | None = None,
    capture: dict | None = None,
    reuse_chunks: bool = False,
) -> dict:
    """Render an approved still set to an MP4 on the project's exact timeline.

    Returns a JSON-serialisable report containing the real, probed metadata of
    the written file. Refuses to overwrite an existing render; the final file
    only appears via an atomic rename of a fully validated temporary MP4.

    ``brand`` is optional and never required: without it, plate cache keys and
    the report are byte-identical to the brandless renderer. With it, the
    package's opening plate is composited over the first ``duration_seconds``
    of video only — the source music, the timeline and every shot allocation
    stay exactly the same. ``titles`` (Remotion only) draws the planned titles
    in the same pass.
    """
    output = Path(output)
    audio = Path(audio)
    workdir = Path(workdir)

    if project.uses_remotion:
        from .remotion import render_base

        return render_base(
            project,
            shots,
            audio,
            output,
            workdir,
            preview_banner=preview_banner,
            preview_placeholders=preview_placeholders,
            brand=brand,
            titles=titles,
            capture=capture,
            reuse_chunks=reuse_chunks,
        )
    if titles is not None:
        raise ValueError("titles in the film require the Remotion backend")
    if any(rs.shot.camera_keyframes or rs.shot.post_effects or rs.shot.transition for rs in shots):
        raise ValueError("keyframes, effects and transition types require the Remotion backend")
    _validate_shots(project, shots)
    if not audio.is_file():
        raise FileNotFoundError(f"source audio not found: {audio}")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing render: {output}")
    if brand is not None and (
        brand.duration_seconds > project.duration
        or round(brand.duration_seconds * project.fps) > project.total_frames
    ):
        raise ValueError(f"brand intro ({brand.duration_seconds}s) does not fit the song timeline")

    cache = workdir / "plates"
    cache.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)

    source_audio_duration = audio_seconds(audio)

    plate_paths: list[Path] = []
    plate_report: list[dict] = []
    for rs in shots:
        key = _plate_key(rs, project)
        plate = cache / f"{key}.mp4"
        expected = _plate_frames(rs)
        cached = _plate_valid(plate, rs, project)
        if not cached:
            _build_plate(rs, project, plate)
        plate_paths.append(plate)
        plate_report.append(
            {
                "id": rs.shot.id,
                "cache_key": key,
                "cached": cached,
                "frames": expected,
                "path": str(plate),
            }
        )

    brand_plate: Path | None = None
    if brand is not None and brand.plate:
        # Rendered at the *output* dimensions, so previews scale the real brand.
        brand_plate = _brand_plate(brand, project, workdir)

    filters, label = _assembly_filter(shots, project)
    if brand_plate is not None:
        # After every camera transform, before any preview marking.
        filters, label = _brand_overlay(filters, label, len(plate_paths), brand.duration_seconds)
    if preview_banner:
        # Applied after all camera transforms so zooms/pans cannot crop it away.
        filters += (
            f";[{label}]drawtext=text='PREVIEW / NOT FINAL':x=10:y=h-th-10:"
            "fontsize=18:fontcolor=yellow:box=1:boxcolor=black@0.85[marked_preview]"
        )
        label = "marked_preview"
        for i, rs in enumerate(shots):
            shot = rs.shot
            caption = (
                "PLACEHOLDER - NOT GENERATED" if shot.id in preview_placeholders else "STILL"
            ) + f" / {shot.id}"
            next_label = f"preview_shot_{i}"
            filters += (
                f";[{label}]drawtext=text='{caption}':x=10:y=10:fontsize=14:"
                f"fontcolor=white:box=1:boxcolor=black@0.85:enable='gte(n,{shot.start_frame})*"
                f"lt(n,{shot.start_frame + shot.duration_frames})'[{next_label}]"
            )
            label = next_label

    fd, tmp_name = tempfile.mkstemp(prefix=f".{output.stem}-", suffix=".tmp.mp4", dir=output.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        if brand_plate is None:
            _finalize(filters, label, plate_paths, audio, tmp, project)
        else:
            _finalize(
                filters,
                label,
                plate_paths,
                audio,
                tmp,
                project,
                brand_plate=brand_plate,
                brand_seconds=brand.duration_seconds,
            )
        media = _validate_output(tmp, project, audio, source_audio_duration)
        # Atomic publication without overwriting a render created during encoding.
        os.link(tmp, output)
        tmp.unlink()
    finally:
        tmp.unlink(missing_ok=True)

    shot_report: list[dict] = []
    for rs in shots:
        entry = {
            "id": rs.shot.id,
            "start_frame": rs.shot.start_frame,
            "duration_frames": rs.shot.duration_frames,
            "dissolve_frames": rs.shot.dissolve_frames,
            "camera": rs.shot.camera,
        }
        # Omitted for legacy shots so their reports stay byte-identical.
        if rs.shot.camera_path is not None:
            entry["camera_path"] = rs.shot.camera_path.model_dump()
        shot_report.append(entry)

    return {
        "output": str(output),
        "slug": project.slug,
        "aspect": project.aspect,
        "width": project.width,
        "height": project.height,
        "fps": project.fps,
        "total_frames": project.total_frames,
        "duration": media["duration"],
        "video": media["video"],
        "audio": media["audio"],
        "source_audio": {"path": str(audio), "duration": source_audio_duration},
        "plates": plate_report,
        "shots": shot_report,
        **_brand_report(brand, brand_plate, project),
    }


def _brand_report(brand: BrandPackage | None, brand_plate: Path | None, project: Project) -> dict:
    """Brand payload/hash/version, or nothing at all for a brandless render."""
    if brand is None or brand_plate is None:
        return {}
    return {
        "brand": {
            "package": brand.model_dump(),
            "hash": pack_hash(brand),
            "implementation": BRAND_RENDER_VERSION,
            "duration_seconds": brand.duration_seconds,
            "frames": round(brand.duration_seconds * project.fps),
            "plate": str(brand_plate),
        }
    }


# --------------------------------------------------------------------------- #
# contact sheet
# --------------------------------------------------------------------------- #
def _thumbnail(path: str, width: int) -> Image.Image:
    try:
        with Image.open(path) as opened:
            image = opened.convert("RGB")
            height = max(1, round(image.height * (width / image.width)))
            return image.resize((width, height), Image.Resampling.LANCZOS)
    except (OSError, ValueError):
        placeholder = Image.new("RGB", (width, round(width * 9 / 16)), (32, 32, 32))
        ImageDraw.Draw(placeholder).text((8, 8), "unreadable", fill=(200, 120, 120))
        return placeholder


def _label(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str) -> None:
    x, y, width, _ = box
    font = ImageFont.load_default()
    available = width - 8
    rendered = text
    while rendered and draw.textlength(rendered, font=font) > available:
        rendered = rendered[:-1]
    draw.text((x + 4, y + 4), rendered, fill=(240, 240, 240), font=font)


def contact_sheet(shots: list[RenderShot], output: Path, *, labels=None) -> Path:
    """Write a labelled PNG overview of the shot set and return its path.

    Rendering is defensive: unreadable source images become placeholders rather
    than aborting the sheet.
    """
    if not shots:
        raise ValueError("contact sheet requires at least one shot")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    thumb_width = 320
    label_height = 54 if labels else 18
    gap = 8
    thumbs = [_thumbnail(rs.image, thumb_width) for rs in shots]
    cell_height = max(t.height for t in thumbs) + label_height
    columns = min(4, len(shots))
    rows = math.ceil(len(shots) / columns)

    sheet = Image.new(
        "RGB",
        (
            columns * thumb_width + (columns + 1) * gap,
            rows * cell_height + (rows + 1) * gap,
        ),
        (16, 16, 16),
    )
    draw = ImageDraw.Draw(sheet)
    for index, (rs, thumb) in enumerate(zip(shots, thumbs, strict=True)):
        col = index % columns
        row = index // columns
        x = gap + col * (thumb_width + gap)
        y = gap + row * (cell_height + gap)
        sheet.paste(thumb, (x, y))
        _label(
            draw,
            (x, y + thumb.height, thumb_width, 18),
            f"{rs.shot.id} [{rs.shot.camera}]",
        )
        if labels:
            for line_index, line in enumerate(labels.get(rs.shot.id, [])[:2], start=1):
                _label(draw, (x, y + thumb.height + line_index * 18, thumb_width, 18), line)
    sheet.save(output)
    return output
