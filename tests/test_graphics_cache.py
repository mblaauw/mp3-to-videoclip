"""Real-FFmpeg tests for per-element overlay caching, cache validation and preflight.

Self-contained, like ``tests/test_graphics.py``: a tiny 640x360 / 40 s base is
synthesized with lavfi and the package module is driven through its own loader
path in a ``tmp_path`` project. No ``projects/`` script is imported, no provider
or paid call is ever made, and no source media is written.

The pure key tests (element/track sensitivity) run without ffmpeg; everything
that composes a film or a preflight still is marked as requiring it.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from conftest import run_ffmpeg
from PIL import Image

from mp3_to_videoclip import graphics, timeline

FPS = 24
DURATION = 40.0
SIZE = (640, 360)
BASE_FRAMES = 960
INTRO_SECONDS = 6.0
CREDITS_TAIL = 12.0
LOCKUP_SECONDS = 3.0
CREDITS_START = DURATION - CREDITS_TAIL
#: Three contiguous shots covering all 960 frames: s001 0-14 s, s002 14-26 s, s003 26-40 s.
SHOT_FRAMES = (336, 288, 336)
#: A shot-bound caption filling exactly the legacy c1 window [8.0, 10.0) of s001.
C1_OFFSET = 192
C1_FRAMES = 48

FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
requires_ffmpeg = pytest.mark.skipif(
    not FFMPEG, reason="ffmpeg and ffprobe are required for the real composite tests"
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _spec() -> dict:
    """A fresh spec; callers mutate their own copy only."""
    return {
        "version": 1,
        "demo": True,
        "intro_seconds": INTRO_SECONDS,
        "credits_tail_seconds": CREDITS_TAIL,
        "lockup_seconds": LOCKUP_SECONDS,
        "palette": dict(graphics.DEFAULT_PALETTE),
        "intro": {
            "mark": {"kind": "signal"},
            "names": "MAHA KALA",
            "title": "THE SIGNAL",
            "time_line": "02:47 AM",
        },
        "captions": [
            {"id": "c1", "start": 8.0, "end": 10.0, "style": "caption", "text": "FIRST LINE"},
            {
                "id": "c2",
                "start": 14.0,
                "end": 16.0,
                "style": "sfx",
                "text": "BOOM",
                "x": 0.68,
                "y": 0.30,
                "rotation": -8,
            },
        ],
        "credits": {"lockup": "A JOINT PRODUCTION", "cards": [["MUSIC", "MAHA KALA"]]},
    }


def _shot_bound_spec() -> dict:
    """The same spec with c1 bound to the exact [8.0, 10.0) frames of shot s001."""
    spec = _spec()
    spec["captions"][0] = {
        "id": "c1",
        "style": "caption",
        "text": "SHOT BOUND",
        "shot_id": "s001",
        "offset_frames": C1_OFFSET,
        "duration_frames": C1_FRAMES,
    }
    return spec


def _write_board(root: Path, *, alias: dict | None = None) -> None:
    """Write a storyboard matching the fixture project (24 fps, 960 frames)."""
    shots, cursor = [], 0
    for index, duration in enumerate(SHOT_FRAMES):
        shots.append(
            {
                "id": f"s{index + 1:03d}",
                "start_frame": cursor,
                "duration_frames": duration,
                "purpose": f"shot {index + 1}",
                "image_prompt": f"prompt for shot {index + 1}",
                "asset_shot_id": (alias or {}).get(f"s{index + 1:03d}"),
            }
        )
        cursor += duration
    board = {
        "schema_version": 1,
        "aspect": "16:9",
        "fps": FPS,
        "total_frames": cursor,
        "shots": shots,
    }
    (root / "work" / "storyboard.json").write_text(json.dumps(board, indent=2) + "\n")


def _write_assets(root: Path, shot_id: str = "s001") -> None:
    """A recorded asset index: selected v002 with its recorded sha (files absent)."""
    assets = {
        shot_id: {
            "selected": 2,
            "versions": [
                {"version": 1, "path": f"assets/{shot_id}/v001.jpg", "sha256": "1" * 64},
                {"version": 2, "path": f"assets/{shot_id}/v002.jpg", "sha256": "a" * 64},
            ],
        }
    }
    (root / "work" / "assets.json").write_text(json.dumps(assets, indent=2) + "\n")


def _write_spec(root: Path, spec: dict) -> None:
    (root / "work" / "graphics-spec.json").write_text(json.dumps(spec, indent=2) + "\n")


def _clip(report: dict, clip_id: str) -> dict:
    return next(clip for clip in report["clips"] if clip["id"] == clip_id)


def _spy_writes(monkeypatch, calls: list) -> None:
    """Record every overlay write (a cache miss) while still writing for real."""
    original = graphics._write_overlay

    def wrapper(path, frames, canvas, fps):
        calls.append(Path(path))
        return original(path, frames, canvas, fps)

    monkeypatch.setattr(graphics, "_write_overlay", wrapper)


# --------------------------------------------------------------------------- #
# pure cache keys: scope and sensitivity
# --------------------------------------------------------------------------- #
def _element_key(
    kind: str,
    spec: dict,
    part: dict,
    *,
    palette=None,
    canvas=SIZE,
    fps=FPS,
    frames=None,
    revision="rev",
) -> str:
    content = graphics.element_content(kind, spec, part)
    resolved = graphics.resolve_palette(spec) if palette is None else palette
    return graphics.element_key(
        kind,
        content,
        resolved,
        canvas,
        fps,
        part.get("frames", 48) if frames is None else frames,
        revision=revision,
    )


def test_caption_key_moves_only_with_its_own_render_inputs():
    spec = _spec()
    cap = dict(spec["captions"][0])
    part = {"kind": "caption", "id": "c1", "caption": cap}
    key = _element_key("caption", spec, part)

    # Unrelated spec edits must not invalidate the caption element.
    unrelated = copy.deepcopy(spec)
    unrelated["intro"]["title"] = "ANOTHER TITLE"
    unrelated["intro_seconds"] = INTRO_SECONDS + 1.0
    unrelated["credits"]["lockup"] = "ANOTHER LOCKUP"
    unrelated["credits"]["cards"][0][1] = "SOMEONE ELSE"
    unrelated["captions"][1]["text"] = "CHANGED ELSEWHERE"
    unrelated["palette"] = dict(graphics.DEFAULT_PALETTE)
    assert _element_key("caption", unrelated, part) == key

    # ...while its own content, window, binding, canvas, fps, frame count,
    # palette and implementation revision all move it.
    assert _element_key("caption", spec, {**part, "caption": {**cap, "text": "SECOND"}}) != key
    assert (
        _element_key("caption", spec, {**part, "caption": {**cap, "start": 8.5, "end": 10.5}})
        != key
    )
    assert (
        _element_key(
            "caption",
            spec,
            {**part, "caption": {**cap, "style": "sfx", "x": 0.5, "y": 0.5}},
        )
        != key
    )
    bound = {**cap, "shot_id": "s001", "start_frame": C1_OFFSET, "end_frame": C1_OFFSET + C1_FRAMES}
    assert _element_key("caption", spec, {**part, "caption": bound}) != key
    assert _element_key("caption", spec, part, canvas=(1280, 720)) != key
    assert _element_key("caption", spec, part, fps=30) != key
    assert _element_key("caption", spec, part, frames=49) != key
    palette = graphics.resolve_palette(spec)
    assert _element_key("caption", spec, part, palette={**palette, "accent": (0, 0, 0)}) != key
    assert _element_key("caption", spec, part, revision="other") != key
    # The caption's id is identity, not a rendering input.
    assert _element_key("caption", spec, {**part, "id": "renamed"}) == key
    # Unchanged inputs are stable.
    assert _element_key("caption", spec, part) == key


def test_intro_card_and_lockup_keys_ignore_a_caption_edit():
    spec = _spec()
    caption_edit = copy.deepcopy(spec)
    caption_edit["captions"][0]["text"] = "EDITED CAPTION"
    intro = {"kind": "intro", "id": "intro", "frames": 144}
    card = {"kind": "card", "id": "card-01", "card": ["MUSIC", "MAHA KALA"]}

    assert _element_key("intro", caption_edit, intro) == _element_key("intro", spec, intro)
    assert _element_key("card", caption_edit, card) == _element_key("card", spec, card)

    # The intro key follows the intro's own fields and its frame budget.
    renamed = copy.deepcopy(spec)
    renamed["intro"]["title"] = "A NEW TITLE"
    assert _element_key("intro", renamed, intro) != _element_key("intro", spec, intro)
    assert _element_key("intro", spec, {**intro, "frames": 145}) != _element_key(
        "intro", spec, intro
    )
    # The card key follows role/name only.
    other_card = {**card, "card": ["MUSIC", "SOMEONE ELSE"]}
    assert _element_key("card", spec, other_card) != _element_key("card", spec, card)
    assert _element_key("card", renamed, card) == _element_key("card", spec, card)

    # The lockup key follows the lockup line, the names and the mark.
    lockup = _element_key("lockup", spec, {"kind": "lockup", "id": "lockup"})
    other_lockup = copy.deepcopy(spec)
    other_lockup["credits"]["lockup"] = "ANOTHER LINE"
    assert _element_key("lockup", other_lockup, {"kind": "lockup", "id": "lockup"}) != lockup
    marked = copy.deepcopy(spec)
    marked["intro"]["mark"] = {"kind": "cat_ears"}
    assert _element_key("lockup", marked, {"kind": "lockup", "id": "lockup"}) != lockup
    names = copy.deepcopy(spec)
    names["intro"]["names"] = "SOMEONE ELSE"
    assert _element_key("lockup", names, {"kind": "lockup", "id": "lockup"}) != lockup
    assert _element_key("lockup", caption_edit, {"kind": "lockup", "id": "lockup"}) == lockup


def test_track_key_binds_clip_hashes_timing_canvas_and_fps():
    parts = [
        {"kind": "intro", "id": "intro", "start": 0.0, "frames": 144, "sha256": "a" * 64},
        {"kind": "caption", "id": "c1", "start": 8.0, "frames": 48, "sha256": "b" * 64},
    ]
    key = graphics.track_key(parts, SIZE, FPS, revision="rev")
    assert graphics.track_key([dict(part) for part in parts], SIZE, FPS, revision="rev") == key

    # A clip's content hash moves the track even with identical ids and timing.
    changed = [dict(parts[0]), {**parts[1], "sha256": "c" * 64}]
    assert graphics.track_key(changed, SIZE, FPS, revision="rev") != key
    # Exact frame timing matters: one frame later is a different track.
    assert (
        graphics.track_key(
            [dict(parts[0]), {**parts[1], "start": 8.0 + 1 / FPS}], SIZE, FPS, revision="rev"
        )
        != key
    )
    # A sub-frame float that lands on the same frame is the same track.
    assert (
        graphics.track_key(
            [dict(parts[0]), {**parts[1], "start": 8.0 + 1e-9}], SIZE, FPS, revision="rev"
        )
        == key
    )
    assert (
        graphics.track_key([dict(parts[0]), {**parts[1], "frames": 49}], SIZE, FPS, revision="rev")
        != key
    )
    # Order, canvas, fps and the implementation revision are all bound in.
    assert graphics.track_key(list(reversed(parts)), SIZE, FPS, revision="rev") != key
    assert graphics.track_key(parts, (1280, 720), FPS, revision="rev") != key
    assert graphics.track_key(parts, SIZE, 30, revision="rev") != key
    assert graphics.track_key(parts, SIZE, FPS, revision="other") != key


# --------------------------------------------------------------------------- #
# per-element caching through a real compose
# --------------------------------------------------------------------------- #
@requires_ffmpeg
def test_caption_content_edit_rebuilds_only_that_element(project_root, base, monkeypatch):
    first = graphics.compose(project_root, base, project_root / "renders" / "v001.mp4")
    # The fixture is a legacy spec: no storyboard is needed or read.
    assert not (project_root / "work" / "storyboard.json").exists()

    spec = graphics.load_spec(project_root)
    spec["captions"][1]["text"] = "CRASH"
    _write_spec(project_root, spec)

    written: list[Path] = []
    _spy_writes(monkeypatch, written)
    second = graphics.compose(project_root, base, project_root / "renders" / "v002.mp4")

    edited = Path(_clip(second, "c2")["cached"])
    assert written == [edited]
    assert edited != Path(_clip(first, "c2")["cached"])
    assert _clip(second, "c2")["sha256"] != _clip(first, "c2")["sha256"]
    for clip_id in ("intro", "c1", "card-01", "lockup"):
        assert Path(_clip(second, clip_id)["cached"]) == Path(_clip(first, clip_id)["cached"])
        assert _clip(second, clip_id)["sha256"] == _clip(first, clip_id)["sha256"]
    assert Path(second["output"]).is_file() and Path(first["output"]).is_file()


@requires_ffmpeg
def test_palette_change_rebuilds_every_element(project_root, base, monkeypatch):
    first = graphics.compose(project_root, base, project_root / "renders" / "v001.mp4")
    spec = graphics.load_spec(project_root)
    spec["palette"]["accent"] = "#00FF00"
    _write_spec(project_root, spec)

    written: list[Path] = []
    _spy_writes(monkeypatch, written)
    second = graphics.compose(project_root, base, project_root / "renders" / "v002.mp4")

    ids = [clip["id"] for clip in first["clips"]]
    assert ids == ["intro", "c1", "c2", "card-01", "lockup"]
    expected = [Path(_clip(second, clip_id)["cached"]) for clip_id in ids]
    assert sorted(written) == sorted(expected)
    for clip_id in ids:
        assert Path(_clip(second, clip_id)["cached"]) != Path(_clip(first, clip_id)["cached"])
        assert _clip(second, clip_id)["sha256"] != _clip(first, clip_id)["sha256"]


# --------------------------------------------------------------------------- #
# cached artifacts are validated, never silently reused
# --------------------------------------------------------------------------- #
@requires_ffmpeg
def test_corrupt_cached_overlay_is_rejected_not_reused(project_root, base):
    first = graphics.compose(project_root, base, project_root / "renders" / "v001.mp4")
    intro = _clip(first, "intro")
    clip_path = Path(intro["cached"])
    original_bytes = clip_path.read_bytes()

    # 1. Bytes that are not a video at all.
    clip_path.write_bytes(b"this is not an overlay")
    with pytest.raises(graphics.ComposeError, match="ffprobe failed"):
        graphics.compose(project_root, base, project_root / "renders" / "v002.mp4")

    # 2. A real overlay at the wrong canvas size.
    clip_path.unlink()
    graphics._write_overlay(
        clip_path,
        (Image.new("RGBA", (320, 180), (0, 0, 0, 0)) for _ in range(intro["frames"])),
        (320, 180),
        FPS,
    )
    with pytest.raises(graphics.ComposeError, match="is not 640x360"):
        graphics.compose(project_root, base, project_root / "renders" / "v003.mp4")

    # 3. A real overlay with the wrong frame count.
    clip_path.unlink()
    graphics._write_overlay(
        clip_path,
        (Image.new("RGBA", SIZE, (0, 0, 0, 0)) for _ in range(intro["frames"] - 1)),
        SIZE,
        FPS,
    )
    with pytest.raises(graphics.ComposeError, match="frame count mismatch"):
        graphics.compose(project_root, base, project_root / "renders" / "v004.mp4")

    # 4. A corrupt cached track is rejected too: with every clip intact the only
    #    remaining cache hit is the assembled alpha track.
    clip_path.unlink()
    clip_path.write_bytes(original_bytes)
    track = next((project_root / "work" / "graphics" / graphics.VERSION).glob("alpha-track-*.mov"))
    track.write_bytes(b"still not a track")
    with pytest.raises(graphics.ComposeError, match="ffprobe failed"):
        graphics.compose(project_root, base, project_root / "renders" / "v005.mp4")


@requires_ffmpeg
def test_valid_format_cache_pixel_corruption_is_rejected(project_root, base):
    first = graphics.compose(project_root, base, project_root / "renders/v001.mp4")
    intro = _clip(first, "intro")
    path = Path(intro["cached"])
    original = path.read_bytes()
    path.unlink()
    graphics._write_overlay(
        path, (Image.new("RGBA", SIZE) for _ in range(intro["frames"])), SIZE, FPS
    )
    with pytest.raises(graphics.ComposeError, match="cached bytes changed"):
        graphics.compose(project_root, base, project_root / "renders/v002.mp4")
    path.write_bytes(original)
    track = next((project_root / "work/graphics" / graphics.VERSION).glob("alpha-track-*.mov"))
    track.unlink()
    graphics._write_overlay(track, (Image.new("RGBA", SIZE) for _ in range(2)), SIZE, FPS)
    with pytest.raises(graphics.ComposeError, match="frame count mismatch"):
        graphics.compose(project_root, base, project_root / "renders/v003.mp4")


@requires_ffmpeg
def test_preflight_rejects_wrong_base_rate_even_if_frame_count_matches(project_root, base):
    wrong = project_root / "work/wrong-fps.mp4"
    run_ffmpeg(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(base),
            "-vf",
            "setpts=PTS/2",
            "-r",
            "48",
            "-frames:v",
            str(BASE_FRAMES),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            str(wrong),
        ]
    )
    assert graphics._count_frames(wrong) == BASE_FRAMES
    with pytest.raises(graphics.ComposeError, match="base fps does not match"):
        graphics.preflight_frames(project_root, wrong, project_root / "work/check", [1])


def test_caption_ids_are_validated(project_root):
    spec = _spec()
    del spec["captions"][0]["id"]
    _write_spec(project_root, spec)
    with pytest.raises(graphics.ComposeError, match="caption needs a non-empty string id"):
        graphics.load_spec(project_root)


@requires_ffmpeg
def test_successful_publish_leaves_no_partial_files(project_root, base):
    report = graphics.compose(project_root, base, project_root / "renders" / "v001.mp4")
    output = Path(report["output"])
    assert output.is_file()
    # The published file is the only name left for its inode: the partial
    # hardlink was removed after the link succeeded.
    assert os.stat(output).st_nlink == 1
    assert [path for path in project_root.rglob(".*partial*")] == []
    assert [path for path in (project_root / "work" / "graphics").rglob(".*")] == []
    assert (
        json.loads(output.with_suffix(".json").read_text())["output_sha256"]
        == report["output_sha256"]
    )


# --------------------------------------------------------------------------- #
# shot-bound captions through compose
# --------------------------------------------------------------------------- #
@requires_ffmpeg
def test_shot_bound_caption_lands_on_exact_shot_frames(project_root, base):
    _write_board(project_root)
    _write_spec(project_root, _shot_bound_spec())
    report = graphics.compose(project_root, base, project_root / "renders" / "v001.mp4")

    windows = {cap["id"]: cap for cap in report["windows"]["captions"]}
    assert windows["c1"]["start"] == C1_OFFSET / FPS == 8.0
    assert windows["c1"]["end"] == (C1_OFFSET + C1_FRAMES) / FPS == 10.0
    assert windows["c1"]["frames"] == C1_FRAMES
    # The legacy absolute caption in the same spec keeps its declared seconds.
    assert windows["c2"]["start"] == 14.0 and windows["c2"]["end"] == 16.0
    timeline_report = report["timeline"]
    assert timeline_report["shot_bound_captions"] == ["c1"]
    assert timeline_report["storyboard"] == str(project_root / "work" / "storyboard.json")
    resolved = timeline_report["captions"][0]
    assert (resolved["shot_id"], resolved["start_frame"], resolved["end_frame"]) == (
        "s001",
        C1_OFFSET,
        C1_OFFSET + C1_FRAMES,
    )
    # The window is the same length in frames as the legacy declaration, and the
    # composed timeline is unchanged: nothing was stretched.
    assert report["video"]["frames"] == BASE_FRAMES
    assert Path(_clip(report, "c1")["cached"]).is_file()


@requires_ffmpeg
@pytest.mark.parametrize(
    "caption",
    [
        {
            "id": "c1",
            "style": "caption",
            "text": "X",
            "shot_id": "s001",
            "offset_frames": 300,
            "duration_frames": 48,
        },
        {
            "id": "c1",
            "style": "caption",
            "text": "X",
            "shot_id": "s001",
            "offset_frames": C1_OFFSET,
            "duration_frames": SHOT_FRAMES[0],
        },
        {
            "id": "c1",
            "style": "caption",
            "text": "X",
            "shot_id": "s999",
            "duration_frames": C1_FRAMES,
        },
    ],
)
def test_shot_caption_past_its_shot_or_unknown_is_rejected(project_root, base, caption):
    _write_board(project_root)
    spec = _spec()
    spec["captions"][0] = caption
    _write_spec(project_root, spec)
    with pytest.raises(graphics.ComposeError, match="caption timeline resolution failed"):
        graphics.compose(project_root, base, project_root / "renders" / "v001.mp4")
    assert not (project_root / "renders").exists()


@requires_ffmpeg
def test_shot_bound_caption_without_a_storyboard_is_rejected(project_root, base):
    _write_spec(project_root, _shot_bound_spec())
    with pytest.raises(graphics.ComposeError, match="need a storyboard"):
        graphics.compose(project_root, base, project_root / "renders" / "v001.mp4")
    assert not (project_root / "renders").exists()


@requires_ffmpeg
def test_storyboard_mismatch_and_invalid_board_are_rejected(project_root, base):
    _write_board(project_root)
    board_path = project_root / "work" / "storyboard.json"
    board = json.loads(board_path.read_text())
    board["total_frames"] = BASE_FRAMES + 24
    board["shots"][-1]["duration_frames"] += 24
    board_path.write_text(json.dumps(board))
    _write_spec(project_root, _shot_bound_spec())
    with pytest.raises(graphics.ComposeError, match="does not match the project"):
        graphics.compose(project_root, base, project_root / "renders" / "v001.mp4")

    board_path.write_text("{not json")
    with pytest.raises(graphics.ComposeError, match="invalid storyboard"):
        graphics.compose(project_root, base, project_root / "renders" / "v002.mp4")


# --------------------------------------------------------------------------- #
# preflight stills
# --------------------------------------------------------------------------- #
@requires_ffmpeg
def test_preflight_stamps_exact_labels_and_versions_the_directory(project_root, base):
    target = project_root / "renders" / "preflight"
    report = graphics.preflight_frames(project_root, base, target, [1.0, 9.0, 15.0])

    assert report["mode"] == "preflight" and report["reviewed"] is False
    assert report["truncated"] is False
    # Exact frames: floor(seconds * fps), and the overlay of that frame's window.
    assert [entry["frame"] for entry in report["frames"]] == [24, 216, 360]
    assert [entry["overlay_id"] for entry in report["frames"]] == [
        "intro:intro",
        "caption:c1",
        "caption:c2",
    ]
    assert report["frames"][1]["local_seconds"] == pytest.approx(1.0)
    # No board and no asset index: shot and selection metadata are marked absent.
    assert all(entry["shot_id"] is None for entry in report["frames"])
    assert all(entry["owner_shot_id"] is None for entry in report["frames"])
    assert all(entry["source"] is None for entry in report["frames"])
    assert all("unavailable" in entry["label"] for entry in report["frames"])

    pngs = sorted(Path(report["output"]).glob("*.png"))
    assert len(pngs) == 3
    for png, entry in zip(pngs, report["frames"], strict=True):
        assert Path(entry["image"]) == png and png.stat().st_size > 0
        with Image.open(png) as still:
            # The label footer is appended below the frame, never over it.
            assert still.width == SIZE[0] and still.height > SIZE[1]
    sidecar = json.loads(Path(report["sidecar"]).read_text())
    assert sidecar["frames"] == report["frames"]
    assert sidecar["output"] == report["output"]

    # A second run never overwrites: the directory is versioned.
    second = graphics.preflight_frames(project_root, base, target, [1.0, 9.0, 15.0])
    assert second["output"].endswith("-v002")
    assert Path(report["output"]).is_dir() and Path(second["output"]).is_dir()
    assert len(list(Path(report["output"]).glob("*.png"))) == 3


@requires_ffmpeg
def test_preflight_default_samples_cover_every_phase_and_overlay(project_root, base):
    report = graphics.preflight_frames(project_root, base, project_root / "renders" / "default")
    entries = report["frames"]
    # 10 named intro phases + 2 captions + 1 card + 1 lockup, all below the cap.
    assert len(entries) == len(graphics.INTRO_PHASES) + 4
    assert len(entries) <= graphics.PREFLIGHT_MAX_SAMPLES
    assert {entry["phase"] for entry in entries if entry["phase"] is not None} == set(
        graphics.INTRO_PHASES
    )
    phases = {phase["phase"]: phase for phase in graphics.intro_phase_samples(INTRO_SECONDS)}
    for entry in entries:
        if entry["phase"] is not None:
            assert entry["frame"] == timeline.frame_number(
                phases[entry["phase"]]["sample_seconds"], FPS
            )
    # Each overlay midpoint is sampled in its own window.
    midpoints = {entry["overlay_id"] for entry in entries if entry["overlay_kind"] != "intro"}
    assert midpoints == {"caption:c1", "caption:c2", "card:card-01", "lockup:lockup"}
    for entry in entries:
        if entry["overlay_kind"] == "caption" and entry["overlay_id"] == "caption:c1":
            assert entry["frame"] == round(8.0 * FPS) + 48 // 2
    assert report["timeline"]["storyboard"] is None


@requires_ffmpeg
def test_preflight_with_board_and_assets_stamps_shot_owner_and_selection(project_root, base):
    _write_board(project_root)
    _write_assets(project_root, "s001")
    _write_spec(project_root, _shot_bound_spec())
    report = graphics.preflight_frames(
        project_root, base, project_root / "renders" / "stamped", [9.0]
    )
    entry = report["frames"][0]

    assert entry["overlay_id"] == "caption:c1"
    assert entry["shot_id"] == "s001" and entry["owner_shot_id"] == "s001"
    assert entry["shot_interval"] == {"start_frame": 0, "end_frame": SHOT_FRAMES[0]}
    # The label reports the recorded selection, and says it is not re-verified.
    assert entry["source"]["version"] == 2
    assert entry["source"]["sha256"] == "a" * 64
    assert entry["source"]["path"] == "assets/s001/v002.jpg"
    assert "recorded selection" in entry["label"]
    assert "not re-verified" in entry["label"]
    assert report["assets"]["selection_verified"] is False
    assert "still v2" in entry["label"]
    assert entry["frame"] == 216 and entry["seconds"] == 216 / FPS
    assert entry["requested_seconds"] == 9.0

    # The still really is the actual base frame with that overlay composited on
    # top: the picture area differs from the bare base frame, in the overlay's
    # own region rather than everywhere.
    with Image.open(entry["image"]) as still:
        picture = np.asarray(still.convert("RGB"))[: SIZE[1], :, :].astype(int)
    bare = np.asarray(graphics._base_frame(base, 216, SIZE, {"color_range": "tv"}))[..., :3]
    difference = np.abs(picture - bare.astype(int)).max(axis=2)
    assert difference.max() > 12
    assert (difference > 12).mean() < 0.5
    # The caption sits in the lower-left of the frame, not across the whole picture.
    assert (difference > 12)[: int(SIZE[1] * 0.5), :].mean() < 1e-3


@requires_ffmpeg
def test_preflight_refuses_bad_targets_and_times(project_root, base):
    target = project_root / "renders" / "preflight"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("not a directory")
    with pytest.raises(graphics.ComposeError, match="must be a directory"):
        graphics.preflight_frames(project_root, base, target, [1.0])

    with pytest.raises(graphics.ComposeError, match="outside the film"):
        graphics.preflight_frames(
            project_root, base, project_root / "renders" / "other", [DURATION]
        )
    with pytest.raises(graphics.ComposeError, match="outside the film"):
        graphics.preflight_frames(project_root, base, project_root / "renders" / "other", [-1.0])
    with pytest.raises(graphics.ComposeError, match="not finite"):
        graphics.preflight_frames(
            project_root, base, project_root / "renders" / "other", [float("nan")]
        )
    # Source media is never a preflight target, and nothing was created there.
    with pytest.raises(graphics.ComposeError, match="source media"):
        graphics.preflight_frames(project_root, base, project_root / "media" / "preflight", [1.0])
    assert not (project_root / "renders" / "other").exists()
    assert not (project_root / "media" / "preflight").exists()


def test_parse_times_rejects_bad_input():
    assert graphics._parse_times("1, 2.5,3") == [1.0, 2.5, 3.0]
    for text in ("", "1,,2", "a", "1,x"):
        with pytest.raises(graphics.ComposeError):
            graphics._parse_times(text)


@requires_ffmpeg
def test_sparse_alpha_track_covers_the_whole_timeline(project_root, base):
    """The track is sparse (gaps are timestamp jumps), so frame count != film frames.

    The invariant that matters is temporal coverage: its probed duration must span
    the whole film, and a late card window must still change pixels.
    """
    report = graphics.compose(project_root, base, project_root / "renders/v001.mp4")
    track = next((project_root / "work/graphics" / graphics.VERSION).glob("alpha-track-*.mov"))
    info = json.loads(
        subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(track),
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    assert float(info["format"]["duration"]) >= DURATION - 1 / FPS
    assert graphics._count_frames(track) < BASE_FRAMES  # sparse by design, not truncated by time
    composed = project_root / "work" / "late-frame.png"
    run_ffmpeg(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(report["output"]),
            "-vf",
            f"select=eq(n\\,{round(31.5 * FPS)})",
            "-frames:v",
            "1",
            "-y",
            str(composed),
        ]
    )
    late = np.asarray(Image.open(composed).convert("RGB"), dtype=int)
    before = np.asarray(graphics._base_frame(base, round(31.5 * FPS), SIZE, {"color_range": "tv"}))[
        ..., :3
    ].astype(int)
    assert np.abs(late - before).max() > 20  # the credits window really is composited
