"""The compositor the Studio no longer composes with, kept for the CLI and its old reviews.

Titles are drawn in the film now. This burned them over a finished base with FFmpeg, and only ``cli.py``
may import it: a test holds the Studio's own layers to that.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

from .. import operations, titles
from ..graphics import (
    CACHE_SCHEMA,
    LEGACY_PALETTE,
    PREFLIGHT_MAX_SAMPLES,
    STORYBOARD_PATH,
    VERSION,
    ComposeError,
    _audio_packet_hash,
    _count_frames,
    _digest,
    _file_hash,
    _font,
    _ink,
    _is_faststart,
    _joint_identity_frame,
    _load_project,
    _locate_part,
    _parse_times,
    _preflight_samples,
    _probe,
    _run,
    _run_bytes,
    _selected_stills,
    _slug,
    _timing_board,
    caption_frame,
    credit_frame,
    element_content,
    implementation_revision,
    intro_frame,
    load_spec,
    lockup_frame,
    resolve_design,
    resolve_palette,
)
from ..remotion import digest, implementation_hash, invoke, title_assets
from ..storage import write_json
from ..timeline import (
    TimelineError,
    is_shot_bound,
    label_at_frame,
    resolve_captions,
)


def graphics_clip(part, spec, palette, canvas, fps, output: Path) -> None:
    """Render one alpha element; existing compositor retains audio packet copying."""
    inputs = {"part": part, **title_assets(spec, palette)}
    invoke(
        "graphics", output, output.parent / "remotion-assets", canvas, fps, part["frames"], inputs
    )


def overlay_clip(part, spec, palette, canvas, fps, directory: Path) -> Path:
    """Alpha cache compatible with the current sparse qtrle track builder."""
    key = digest(
        {
            "part": part,
            "spec": spec,
            "palette": palette,
            "canvas": canvas,
            "fps": fps,
            "renderer_revision": implementation_hash(),
        }
    )[:24]
    path = directory / f"remotion-overlay-{key}.mov"
    if path.exists():
        _validate_overlay(path, canvas, part["frames"])
        _cache_integrity(path, created=False)
        return path
    alpha = directory / f"remotion-prores-{key}.mov"
    if not alpha.exists():
        graphics_clip(part, spec, palette, canvas, fps, alpha)
        _cache_integrity(alpha, created=True)
    else:
        _cache_integrity(alpha, created=False)
    temp = path.with_name(f".{path.stem}.partial.mov")
    conversion_started = time.perf_counter()
    try:
        _run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-n",
                "-i",
                str(alpha),
                "-an",
                "-c:v",
                "qtrle",
                "-pix_fmt",
                "argb",
                str(temp),
            ]
        )
        conversion_seconds = time.perf_counter() - conversion_started
        verification_started = time.perf_counter()
        _validate_overlay(temp, canvas, part["frames"])
        verification_seconds = time.perf_counter() - verification_started
        os.link(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    _cache_integrity(path, created=True)
    write_json(
        path.with_suffix(".timings.json"),
        {
            "conversion_seconds": conversion_seconds,
            "output_verification_seconds": verification_seconds,
        },
    )
    return path


def overlay_frame(clip: Path, local_frame: int) -> Image.Image:
    """Decode an actual cached Remotion frame; never substitute Pillow samples."""
    import io

    from ..ffmpeg import _binary

    result = subprocess.run(
        [
            _binary("ffmpeg"),
            "-v",
            "error",
            "-i",
            str(clip),
            "-vf",
            f"select=eq(n\\,{local_frame})",
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "png",
            "-",
        ],
        check=True,
        capture_output=True,
    )
    return Image.open(io.BytesIO(result.stdout)).convert("RGBA")


def _overlay_frame(part, spec, palette, canvas, fps: int, local_seconds: float) -> Image.Image:
    """One overlay frame for a planned window at ``local_seconds`` into it."""
    if spec.get("renderer") == "remotion":
        raise ComposeError(
            "Remotion preflight must decode the actual alpha clip, not Pillow frames"
        )
    if part["kind"] == "intro":
        return intro_frame(spec, palette, local_seconds, canvas)
    if part["kind"] == "caption":
        return caption_frame(part["caption"], palette, local_seconds, part["frames"] / fps, canvas)
    if part["kind"] == "identity":
        return _joint_identity_frame(spec, palette, local_seconds, part["frames"] / fps, canvas)
    if part["kind"] == "card":
        return credit_frame(
            part["card"], palette, local_seconds, part["frames"] / fps, canvas, spec=spec
        )
    return lockup_frame(spec, palette, local_seconds, part["frames"] / fps, canvas)


def _part_frames(part, spec, palette, canvas, fps: int):
    """The frame generator for one planned overlay window."""
    return (
        _overlay_frame(part, spec, palette, canvas, fps, index / fps)
        for index in range(part["frames"])
    )


def element_key(
    kind: str,
    content: dict,
    palette: dict,
    canvas,
    fps: int,
    frames: int,
    *,
    revision: str | None = None,
) -> str:
    """Content key for one overlay clip.

    Inputs: the element's own rendering content, the palette, the canvas, the
    fps, the clip's frame count and the implementation revision. Nothing else.
    """
    return _digest(
        {
            "cache_schema": CACHE_SCHEMA,
            "kind": kind,
            "content": content,
            "palette": {name: list(value) for name, value in palette.items()},
            "canvas": [int(canvas[0]), int(canvas[1])],
            "fps": int(fps),
            "frames": int(frames),
            "implementation": revision or implementation_revision(),
        }
    )[:16]


def track_key(parts, canvas, fps: int, *, revision: str | None = None) -> str:
    """Content key for the assembled alpha track.

    Every ordered clip's content hash and exact frame timing is bound in, so a
    cached track is only reused when the same clips sit at the same frames on
    the same canvas at the same fps.
    """
    return _digest(
        {
            "cache_schema": CACHE_SCHEMA,
            "canvas": [int(canvas[0]), int(canvas[1])],
            "fps": int(fps),
            "implementation": revision or implementation_revision(),
            "clips": [
                {
                    "kind": part["kind"],
                    "id": part["id"],
                    "start_frame": round(float(part["start"]) * fps),
                    "frames": int(part["frames"]),
                    "sha256": part["sha256"],
                }
                for part in parts
            ],
        }
    )[:16]


def _write_overlay(path: Path, frames, canvas, fps: int) -> None:
    if path.exists():
        return
    partial = path.with_name(f".{path.stem}.partial{path.suffix}")
    partial.unlink(missing_ok=True)
    proc = subprocess.Popen(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-n",
            "-f",
            "rawvideo",
            "-pixel_format",
            "rgba",
            "-video_size",
            f"{canvas[0]}x{canvas[1]}",
            "-framerate",
            str(fps),
            "-i",
            "pipe:0",
            "-c:v",
            "qtrle",
            "-pix_fmt",
            "argb",
            "-movflags",
            "+faststart",
            "-f",
            "mov",
            str(partial),
        ],
        stdin=subprocess.PIPE,
    )
    try:
        for frame in frames:
            proc.stdin.write(frame.tobytes())
        proc.stdin.close()
        if proc.wait() != 0:
            raise ComposeError("local overlay encoding failed")
    finally:
        if proc.stdin and not proc.stdin.closed:
            proc.stdin.close()
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    try:
        _run(["ffprobe", "-v", "error", str(partial)])
        os.link(partial, path)
    finally:
        partial.unlink(missing_ok=True)


def _validate_overlay(path: Path, canvas, frames: int) -> dict:
    info = _probe(path)
    videos = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    audio = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    if len(videos) != 1 or audio:
        raise ComposeError(f"{path} must carry exactly one video stream and no audio")
    video = videos[0]
    if video.get("codec_name") != "qtrle" or video.get("pix_fmt") != "argb":
        raise ComposeError(f"{path} is not a qtrle/ARGB alpha overlay")
    if (int(video["width"]), int(video["height"])) != tuple(canvas):
        raise ComposeError(f"{path} is not {canvas[0]}x{canvas[1]}")
    if _count_frames(path) != frames:
        raise ComposeError(f"{path} frame count mismatch")
    return {"path": str(path), "frames": frames, "sha256": _file_hash(path)}


def _validate_track(path: Path, canvas, frames: int) -> dict:
    """Same contract as a clip: one qtrle/ARGB video at canvas size, expected frames."""
    return _validate_overlay(path, canvas, frames)


def _cache_integrity(path: Path, *, created: bool):
    """A valid codec is not evidence of intact pixels. Bind cached bytes once."""
    from ..storage import write_json

    sidecar = path.with_suffix(path.suffix + ".json")
    actual = _file_hash(path)
    if created:
        write_json(sidecar, {"sha256": actual})
        return
    try:
        recorded = json.loads(sidecar.read_text())
    except (OSError, ValueError) as exc:
        raise ComposeError(
            f"cache integrity metadata missing/invalid: {path}; explicitly rebuild this cache"
        ) from exc
    if recorded.get("sha256") != actual:
        raise ComposeError(f"cached bytes changed: {path}; explicitly rebuild this cache")


def _validate_base(base: Path, project: dict) -> dict:
    info = _probe(base)
    videos = [s for s in info["streams"] if s.get("codec_type") == "video"]
    audios = [s for s in info["streams"] if s.get("codec_type") == "audio"]
    if len(videos) != 1 or len(audios) != 1:
        raise ComposeError("base must carry exactly one video and one audio stream")
    video, audio = videos[0], audios[0]
    width, height = int(video["width"]), int(video["height"])
    if width * 9 != height * 16:
        raise ComposeError(f"base {width}x{height} is not 16:9")
    if width > int(project["width"]) or height > int(project["height"]):
        raise ComposeError("base is larger than the project output")
    fps = int(project["fps"])
    if video.get("codec_name") != "h264" or audio.get("codec_name") != "aac":
        raise ComposeError("base must be H.264 video with AAC audio")
    rate = str(video.get("avg_frame_rate", "0/1"))
    try:
        numerator, denominator = (int(part) for part in rate.split("/", 1))
        base_fps = round(numerator / denominator) if denominator else 0
    except (ValueError, ZeroDivisionError):
        base_fps = 0
    if base_fps != fps:
        raise ComposeError("base fps does not match the project")
    total = math.ceil(float(project["duration"]) * fps)
    frames = _count_frames(base)
    if frames != total:
        raise ComposeError(f"base has {frames} frames, expected {total}")
    audio_duration = float(audio.get("duration") or info["format"]["duration"])
    if audio_duration + 1 / fps + 1e-3 < float(project["duration"]):
        raise ComposeError("base audio is shorter than the source music")
    return {
        "frames": frames,
        "duration": float(info["format"]["duration"]),
        "sha256": _file_hash(base),
        "audio_packet_hash": _audio_packet_hash(base),
    }


def _unique_output(output: Path) -> Path:
    if not output.exists():
        return output
    index = 2
    while True:
        candidate = output.with_name(f"{output.stem}-v{index:03d}{output.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def _plan_parts(spec: dict, duration: float, fps: int, captions=None):
    """The compositor's view of :func:`titles.plan_titles`: ``start`` in seconds.

    ``start`` is exactly ``start_frame / fps``, so every placement that rounds
    ``start * fps`` lands on the planned frame.
    """
    resolve_design(spec)
    try:
        windows, total = titles.plan_titles(spec, fps=fps, duration=duration, captions=captions)
    except titles.TitleError as exc:
        raise ComposeError(str(exc)) from exc
    parts = []
    for window in windows:
        part = {key: value for key, value in window.items() if key not in ("start_frame", "index")}
        part["start"] = window["start_frame"] / fps
        parts.append(part)
    return parts, total


def _build_track(parts, directory: Path, canvas, fps: int) -> Path:
    key = track_key(parts, canvas, fps)
    track = directory / f"alpha-track-{key}.mov"
    cursor = 0.0
    expected_frames = 0
    for part in parts:
        expected_frames += part["frames"] + int(part["start"] - cursor > 0.02)
        cursor = part["start"] + part["frames"] / fps
    if track.exists():
        _validate_track(track, canvas, expected_frames)
        _cache_integrity(track, created=False)
        return track
    blank = directory / f"blank-{canvas[0]}x{canvas[1]}-{fps}-v{CACHE_SCHEMA}.mov"
    if not blank.exists():
        _write_overlay(
            blank, (Image.new("RGBA", tuple(canvas), (0, 0, 0, 0)) for _ in range(1)), canvas, fps
        )
        _cache_integrity(blank, created=True)
    _validate_overlay(blank, canvas, 1)
    _cache_integrity(blank, created=False)
    lines = ["ffconcat version 1.0"]
    cursor = 0.0
    for part in parts:
        gap = part["start"] - cursor
        if gap > 0.02:
            lines += [f"file '{blank.resolve()}'", f"duration {gap:.9f}"]
        lines += [
            f"file '{Path(part['path']).resolve()}'",
            f"duration {part['frames'] / fps:.9f}",
        ]
        cursor = part["start"] + part["frames"] / fps
    listing = directory / f"alpha-track-{key}.ffconcat"
    listing.write_text("\n".join(lines) + "\n")
    partial = track.with_name(f".{track.stem}.partial.mov")
    partial.unlink(missing_ok=True)
    try:
        _run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-n",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(listing),
                "-map",
                "0:v:0",
                "-c:v",
                "copy",
                "-an",
                "-video_track_timescale",
                "24000",
                "-movflags",
                "+faststart",
                str(partial),
            ]
        )
        os.link(partial, track)
    finally:
        # Publish or fail atomically: the partial hardlink never survives.
        partial.unlink(missing_ok=True)
    _validate_track(track, canvas, expected_frames)
    _cache_integrity(track, created=True)
    return track


@operations.progress_scope(stage="final-composite")
def compose(
    root: Path | str,
    base: Path | str,
    output: Path | str,
    *,
    source: Path | str | None = None,
    spec_path: Path | str | None = None,
) -> dict:
    """Composite the spec intro, captions and credits onto the base still film."""
    root = Path(root).resolve()
    base = Path(base).resolve()
    output = Path(output).resolve()
    project = _load_project(root)
    spec = load_spec(root, Path(spec_path) if spec_path else None)
    palette = resolve_palette(spec)
    if not base.is_file():
        raise ComposeError(f"base render not found: {base}")
    base_facts = _validate_base(base, project)
    source_path = Path(source).resolve() if source else (root / project["source"]).resolve()
    if not source_path.is_file():
        raise ComposeError(f"project source not found: {source_path}")
    if _file_hash(source_path) != project["source_sha256"]:
        raise ComposeError("project source bytes do not match the declared source identity")

    fps, duration = int(project["fps"]), float(project["duration"])
    canvas = (int(project["width"]), int(project["height"]))
    board = (
        _timing_board(root, project)
        if any(is_shot_bound(cap) for cap in spec["captions"])
        else None
    )
    try:
        captions = resolve_captions(spec["captions"], board, fps)
    except TimelineError as exc:
        raise ComposeError(f"caption timeline resolution failed: {exc}") from exc
    parts, total = _plan_parts(spec, duration, fps, captions)
    revision = implementation_revision()
    directory = root / "work" / "graphics" / VERSION
    directory.mkdir(parents=True, exist_ok=True)

    graphics_started = time.perf_counter()
    for part_index, part in enumerate(parts, 1):
        content = element_content(part["kind"], spec, part)
        if spec.get("renderer") == "remotion":
            with operations.progress_scope(
                part=f"{part['kind']} {part['id']}", part_index=part_index, part_total=len(parts)
            ):
                clip = overlay_clip(part, spec, palette, canvas, fps, directory)
            part.update({"path": str(clip), "sha256": _file_hash(clip), "key": clip.stem})
            continue
        key = element_key(
            part["kind"], content, palette, canvas, fps, part["frames"], revision=revision
        )
        clip = directory / f"{part['kind']}-{part['id']}-{key}.mov"
        created = not clip.exists()
        if created:
            with operations.progress_scope(
                part=f"{part['kind']} {part['id']}", part_index=part_index, part_total=len(parts)
            ):
                _write_overlay(clip, _part_frames(part, spec, palette, canvas, fps), canvas, fps)
        part["path"] = clip
        part["key"] = key
        part["sha256"] = _validate_overlay(clip, canvas, part["frames"])["sha256"]
        _cache_integrity(clip, created=created)

    operations.phase("assembling-graphics")
    graphics_seconds = time.perf_counter() - graphics_started
    assembly_started = time.perf_counter()
    track = _build_track(parts, directory, canvas, fps)
    assembly_seconds = time.perf_counter() - assembly_started
    output = _unique_output(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.stem}.partial{output.suffix}")
    temporary.unlink(missing_ok=True)
    try:
        operations.phase("compositing")
        composite_started = time.perf_counter()
        _run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-i",
                str(base),
                "-i",
                str(track),
                "-filter_complex",
                "[0:v]setpts=PTS-STARTPTS[base];[1:v]setpts=PTS-STARTPTS[alpha];"
                "[base][alpha]overlay=0:0:format=auto:eof_action=pass[final]",
                "-map",
                "[final]",
                "-map",
                "0:a:0",
                "-frames:v",
                str(total),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "17",
                "-pix_fmt",
                "yuv420p",
                "-r",
                str(fps),
                "-c:a",
                "copy",
                "-movflags",
                "+faststart",
                "-max_muxing_queue_size",
                "1024",
                str(temporary),
            ]
        )
        operations.phase("verifying-output")
        composite_seconds = time.perf_counter() - composite_started
        verification_started = time.perf_counter()
        _probe(temporary)
        final_frames = _count_frames(temporary)
        if final_frames != base_facts["frames"]:
            raise ComposeError(
                f"composed film has {final_frames} frames, expected {base_facts['frames']}"
            )
        final_audio = _audio_packet_hash(temporary)
        if final_audio != base_facts["audio_packet_hash"]:
            raise ComposeError("composed audio packets differ from the base film")
        if not _is_faststart(temporary):
            raise ComposeError("composed film is not faststart")
        if _file_hash(base) != base_facts["sha256"]:
            raise ComposeError("base changed during composition")
        verification_seconds = time.perf_counter() - verification_started
        os.link(temporary, output)
    finally:
        # Published or not, the partial hardlink is always removed.
        temporary.unlink(missing_ok=True)

    report = {
        "version": VERSION,
        "timings_seconds": {
            "graphics_elements": graphics_seconds,
            "track_assembly": assembly_seconds,
            "composite": composite_seconds,
            "output_verification": verification_seconds,
        },
        "output": str(output),
        "output_sha256": _file_hash(output),
        "base": {"path": str(base), **base_facts},
        "source": {"path": str(source_path), "sha256": project["source_sha256"]},
        "spec_sha256": _digest(spec),
        "implementation_sha256": _file_hash(Path(__file__)),
        "implementation_revision": revision,
        "video": {
            "width": canvas[0],
            "height": canvas[1],
            "fps": fps,
            "frames": base_facts["frames"],
            "duration_seconds": base_facts["duration"],
        },
        "music": {
            "duration_seconds": duration,
            "audio_packet_hash": base_facts["audio_packet_hash"],
            "base_and_final_audio_identical": True,
        },
        "windows": {
            "intro": {"start": 0.0, "end": parts[0]["frames"] / fps, "frames": parts[0]["frames"]},
            "captions": [
                {
                    "id": p["id"],
                    "start": p["start"],
                    "end": p["start"] + p["frames"] / fps,
                    "frames": p["frames"],
                    "text": p["caption"]["text"],
                    "style": p["caption"]["style"],
                }
                for p in parts
                if p["kind"] == "caption"
            ],
            "credits": [
                {
                    "id": p["id"],
                    "role": p["card"][0],
                    "name": p["card"][1],
                    "start": p["start"],
                    "end": p["start"] + p["frames"] / fps,
                    "frames": p["frames"],
                }
                for p in parts
                if p["kind"] == "card"
            ],
            "lockup": {
                "line": spec["credits"]["lockup"],
                "start": parts[-1]["start"],
                "end": parts[-1]["start"] + parts[-1]["frames"] / fps,
                "frames": parts[-1]["frames"],
            },
        },
        "timeline": {
            "storyboard": str(root / STORYBOARD_PATH) if board is not None else None,
            "storyboard_sha256": _file_hash(root / STORYBOARD_PATH) if board is not None else None,
            "shot_bound_captions": [
                cap["id"]
                for cap, original in zip(captions, spec["captions"], strict=True)
                if is_shot_bound(original)
            ],
            "captions": [
                {
                    "id": cap.get("id"),
                    "shot_id": cap.get("shot_id"),
                    "start_frame": cap.get("start_frame"),
                    "end_frame": cap.get("end_frame"),
                    "start": cap["start"],
                    "end": cap["end"],
                }
                for cap in captions
            ],
        },
        "demo_credits": bool(spec.get("demo", True)),
        "clips": [
            {
                "id": p["id"],
                "kind": p["kind"],
                "frames": p["frames"],
                "key": p.get("key"),
                "sha256": p.get("sha256"),
                "cached": str(p.get("path")),
            }
            for p in parts
        ],
        "note": "Local Pillow/qtrle graphics; no provider call, no AI lettering for the composited text.",
    }
    report_path = output.with_suffix(".json")
    if report_path.exists():
        raise ComposeError(f"report already exists; refusing to overwrite {report_path}")
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    report["report"] = str(report_path)
    return report


def _preflight_base_facts(base: Path, project: dict, fps: int) -> dict:
    """Video-only base facts: exactly the canvas and frame count preflight needs."""
    info = _probe(base)
    videos = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    if len(videos) != 1:
        raise ComposeError("base must carry exactly one video stream")
    video = videos[0]
    from fractions import Fraction

    try:
        if Fraction(video.get("avg_frame_rate", "0/1")) != fps:
            raise ComposeError("base fps does not match the project")
    except (ValueError, ZeroDivisionError) as exc:
        raise ComposeError("base fps does not match the project") from exc
    width, height = int(video["width"]), int(video["height"])
    if width * 9 != height * 16:
        raise ComposeError(f"base {width}x{height} is not 16:9")
    if width > int(project["width"]) or height > int(project["height"]):
        raise ComposeError("base is larger than the project output")
    total = math.ceil(float(project["duration"]) * fps)
    frames = _count_frames(base)
    if frames != total:
        raise ComposeError(f"base has {frames} frames, expected {total}")
    return {"canvas": (width, height), "frames": frames, "video": video}


def _base_frame(base: Path, frame: int, canvas, video: dict) -> Image.Image:
    """The exact base frame ``frame`` as RGBA, converted like the composite pass."""
    width, height = canvas
    # FFmpeg's YUV-to-RGB conversion already expands limited range. Expanding
    # again after format=rgb24 clips shadows/highlights in review frames.
    chain = f"select=eq(n\\,{frame}),format=rgb24"
    raw = _run_bytes(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(base),
            "-vf",
            chain,
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "pipe:1",
        ]
    )
    expected = width * height * 3
    if len(raw) != expected:
        raise ComposeError(f"base frame {frame} decoded to {len(raw)} bytes, expected {expected}")
    return Image.frombytes("RGB", canvas, raw).convert("RGBA")


def _stamp_label(image: Image.Image, lines: list[str]) -> Image.Image:
    """Append the label as a footer band, never drawn over the composited picture."""
    width, height = image.size
    size = max(10, round(height * 0.026))
    font = _font("regular", size)
    draw = ImageDraw.Draw(image)
    for _ in range(8):
        ink = max(_ink(draw, line, font)[0] for line in lines)
        if ink <= width - 16 or size <= 8:
            break
        size = max(8, int(size * 0.85))
        font = _font("regular", size)
    line_height = max(_ink(draw, line, font)[1] for line in lines) + 4
    footer = line_height * len(lines) + 8
    stamped = Image.new("RGB", (width, height + footer), LEGACY_PALETTE["night"])
    stamped.paste(image.convert("RGB"), (0, 0))
    sdraw = ImageDraw.Draw(stamped)
    for index, line in enumerate(lines):
        sdraw.text(
            (8, height + 4 + index * line_height), line, font=font, fill=LEGACY_PALETTE["ink"]
        )
    return stamped


def preflight_frames(
    root: Path | str,
    base: Path | str,
    output: Path | str,
    times=None,
    *,
    spec_path: Path | str | None = None,
) -> dict:
    """Render representative composited stills from the real base frames.

    ``output`` is a directory; a new versioned directory is created instead of
    overwriting anything. Every still is the exact base frame (ffmpeg ``select``)
    with the same local overlay frame builder the film uses, plus a footer band
    carrying frame, seconds, shot id, alias owner, the recorded selected still
    and the overlay id. The same labels are written to ``preflight.json``. The
    recorded selection is metadata from ``work/assets.json`` and is not
    re-verified byte-for-byte, so nothing here is a review or QC verdict. No
    encode, no source media write, no provider call.
    """
    root = Path(root).resolve()
    base = Path(base).resolve()
    output = Path(output).resolve()
    project = _load_project(root)
    spec = load_spec(root, Path(spec_path) if spec_path else None)
    palette = resolve_palette(spec)
    if not base.is_file():
        raise ComposeError(f"base render not found: {base}")
    if output.is_file():
        raise ComposeError(f"preflight output must be a directory, not a file: {output}")
    media = (root / "media").resolve()
    if output == media or media in output.parents:
        raise ComposeError("preflight refuses to write inside the project's source media directory")
    fps, duration = int(project["fps"]), float(project["duration"])
    facts = _preflight_base_facts(base, project, fps)
    canvas = facts["canvas"]
    needs_board = any(is_shot_bound(cap) for cap in spec["captions"])
    board = None
    if needs_board or (root / STORYBOARD_PATH).exists():
        try:
            board = _timing_board(root, project)
        except ComposeError:
            if needs_board:
                raise
            # Absolute legacy overlays do not require a current storyboard;
            # label shot metadata unavailable instead of trusting a stale map.
            board = None
    try:
        captions = resolve_captions(spec["captions"], board, fps)
    except TimelineError as exc:
        raise ComposeError(f"caption timeline resolution failed: {exc}") from exc
    parts, _total = _plan_parts(spec, duration, fps, captions)
    samples = _preflight_samples(spec, parts, fps, facts["frames"], times)
    truncated = False
    if len(samples) > PREFLIGHT_MAX_SAMPLES:
        truncated = True
        samples = samples[:PREFLIGHT_MAX_SAMPLES]
    directory = _unique_output(output)
    try:
        directory.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise ComposeError(f"preflight directory already exists: {directory}") from exc
    selected = _selected_stills(root, board)
    entries = []
    for index, sample in enumerate(samples, start=1):
        frame = sample["frame"]
        part, local = _locate_part(parts, fps, frame)
        if sample["phase"] is not None and (part is None or part["kind"] != "intro"):
            raise ComposeError(
                f"intro phase {sample['phase']!r} sample frame {frame} is outside the intro window"
            )
        label = label_at_frame(board, frame) if board is not None else None
        source = selected.get(label["shot_id"]) if label else None
        overlay_id = f"{part['kind']}:{part['id']}" if part is not None else "none"
        still = _base_frame(base, frame, canvas, facts["video"])
        if part is not None and local is not None:
            if spec.get("renderer") == "remotion":
                cache = root / "work" / "graphics" / "cache"
                cache.mkdir(parents=True, exist_ok=True)
                clip = overlay_clip(part, spec, palette, canvas, fps, cache)
                overlay = overlay_frame(clip, max(0, min(part["frames"] - 1, round(local * fps))))
            else:
                overlay = _overlay_frame(part, spec, palette, canvas, fps, local)
            still = Image.alpha_composite(still, overlay)
        shot_text = (
            f"{label['shot_id']} (owner {label['owner_shot_id']})" if label else "unavailable"
        )
        if source:
            still_text = (
                f"still v{source['version']} sha256:{str(source['sha256'])[:12]} "
                "(recorded selection, not re-verified)"
            )
        else:
            still_text = "still metadata unavailable"
        footer = [
            f"frame {frame} @ {frame / fps:.3f}s | shot {shot_text}",
            f"overlay {overlay_id} | {still_text}",
            "UNREVIEWED preflight still - local composite only",
        ]
        png = directory / f"{index:03d}-f{frame:05d}-{_slug(overlay_id)}.png"
        _stamp_label(still, footer).save(png, format="PNG")
        entries.append(
            {
                "index": index,
                "image": str(png),
                "frame": frame,
                "seconds": frame / fps,
                "overlay_id": overlay_id,
                "overlay_kind": part["kind"] if part is not None else "none",
                "phase": sample["phase"],
                "requested_seconds": sample["requested_seconds"],
                "local_seconds": local,
                "shot_id": label["shot_id"] if label else None,
                "owner_shot_id": label["owner_shot_id"] if label else None,
                "shot_interval": (
                    {"start_frame": label["start_frame"], "end_frame": label["end_frame"]}
                    if label
                    else None
                ),
                "source": source,
                "label": " | ".join(footer[:2]),
                "reviewed": False,
            }
        )
    report = {
        "version": VERSION,
        "mode": "preflight",
        "output": str(directory),
        "sidecar": str(directory / "preflight.json"),
        "base": {
            "path": str(base),
            "sha256": _file_hash(base),
            "frames": facts["frames"],
            "width": canvas[0],
            "height": canvas[1],
        },
        "spec_sha256": _digest(spec),
        "implementation_revision": implementation_revision(),
        "video": {"fps": fps, "frames": facts["frames"], "duration_seconds": duration},
        "timeline": {
            "storyboard": str(root / STORYBOARD_PATH) if board is not None else None,
            "resolved_captions": [
                {
                    "id": cap.get("id"),
                    "shot_id": cap.get("shot_id"),
                    "start_frame": cap.get("start_frame"),
                    "end_frame": cap.get("end_frame"),
                    "start": cap["start"],
                    "end": cap["end"],
                }
                for cap in captions
            ],
        },
        "assets": {
            "index": str(root / "work" / "assets.json")
            if (root / "work" / "assets.json").is_file()
            else None,
            "selection_verified": False,
            "note": "recorded selection only; asset bytes were not re-verified against the index",
        },
        "frames": entries,
        "truncated": truncated,
        "reviewed": False,
        "note": "Local preflight stills for inspection: exact base frames with overlay "
        "composites. No encode, no provider call, no review verdict.",
    }
    (directory / "preflight.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=None)
    parser.add_argument("--spec", type=Path, default=None)
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="render representative composited stills from real base frames; "
        "--output is a new directory and no film is encoded",
    )
    parser.add_argument(
        "--times",
        default=None,
        help="comma-separated sample seconds for --preflight; default: each intro "
        "phase and each caption/card/lockup midpoint",
    )
    args = parser.parse_args(argv)
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        print("ffmpeg and ffprobe are required", file=sys.stderr)
        return 2
    times = None
    if args.times is not None:
        if not args.preflight:
            parser.error("--times is only used with --preflight")
        try:
            times = _parse_times(args.times)
        except ComposeError as exc:
            parser.error(str(exc))
    try:
        if args.preflight:
            report = preflight_frames(args.root, args.base, args.output, times, spec_path=args.spec)
        else:
            report = compose(
                args.root, args.base, args.output, source=args.source, spec_path=args.spec
            )
    except ComposeError as exc:
        print(f"{'preflight' if args.preflight else 'compose'} failed: {exc}", file=sys.stderr)
        return 1
    if args.preflight:
        print(
            json.dumps(
                {
                    "output": report["output"],
                    "sidecar": report["sidecar"],
                    "stills": len(report["frames"]),
                },
                indent=2,
            )
        )
    else:
        print(json.dumps({k: report[k] for k in ("output", "output_sha256", "report")}, indent=2))
    return 0
