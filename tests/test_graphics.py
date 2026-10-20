"""Local, real-FFmpeg tests for the package graphics compositor.

Self-contained: a tiny 640x360 / 85 s base is synthesized with lavfi and the
package module (``mp3_to_videoclip.graphics``) is driven through its own loader
path in a ``tmp_path`` project. No ``projects/`` script is imported, so nothing
here skips in a clean checkout, and no provider or paid call is ever made.

The geometry tests (SFX containment, caption fitting, the cat-ears mark) are
pure Pillow and run without ffmpeg.
"""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import numpy as np
import pytest
from conftest import audio_packet_hash, frame_diff, read_frame
from PIL import Image, ImageDraw

from mp3_to_videoclip import graphics

FPS = 24
DURATION = 85.0
SIZE = (640, 360)
BASE_FRAMES = math.ceil(DURATION * FPS)
INTRO_SECONDS = 25.0
CREDITS_TAIL = 40.0
CREDITS_START = DURATION - CREDITS_TAIL
LOCKUP_SECONDS = 4.0
LONG_SFX = "SIGNAL LOCK"

FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
requires_ffmpeg = pytest.mark.skipif(
    not FFMPEG, reason="ffmpeg and ffprobe are required for the real composite test"
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _dilate(mask: np.ndarray, iterations: int) -> np.ndarray:
    out = mask.copy()
    for _ in range(iterations):
        grown = out.copy()
        grown[1:, :] |= out[:-1, :]
        grown[:-1, :] |= out[1:, :]
        grown[:, 1:] |= out[:, :-1]
        grown[:, :-1] |= out[:, 1:]
        out = grown
    return out


def _erode(mask: np.ndarray, iterations: int) -> np.ndarray:
    return ~_dilate(~mask, iterations)


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    """Everything enclosed by ``mask``: the filled shape, holes included."""
    background = np.zeros_like(mask)
    background[0, :] = background[-1, :] = True
    background[:, 0] = background[:, -1] = True
    background &= ~mask
    while True:
        grown = _dilate(background, 1) & ~mask
        if np.array_equal(grown, background):
            return ~background
        background = grown


def _spec() -> dict:
    return {
        "version": 1,
        "demo": True,
        "intro_seconds": INTRO_SECONDS,
        "credits_tail_seconds": CREDITS_TAIL,
        "lockup_seconds": LOCKUP_SECONDS,
        "palette": dict(graphics.DEFAULT_PALETTE),
        "intro": {
            "mark": {"kind": "signal"},
            "names": "MAHA KALA  \u00d7  VJDJ69",
            "title": "THE SIGNAL",
            "time_line": "02:47 AM \u2014 SECTOR 7",
            "tagline": "A JOINT MAHA KALA & VJDJ69 PRODUCTION",
            "notes": ["RECORDED AFTER MIDNIGHT", "NO RETAKES"],
            "mini_credits": [["DIRECTION", "VJDJ69"], ["MUSIC", "MAHA KALA"]],
        },
        "captions": [
            {
                "id": "c1",
                "start": 27.0,
                "end": 30.0,
                "style": "caption",
                "text": "02:58 AM \u2014 SECTOR 7",
            },
            {
                "id": "c2",
                "start": 33.0,
                "end": 35.0,
                "style": "sfx",
                "text": LONG_SFX,
                "x": 0.68,
                "y": 0.30,
                "rotation": -8,
            },
        ],
        "credits": {
            "lockup": "A JOINT MAHA KALA & VJDJ69 PRODUCTION",
            "cards": [["MUSIC", "MAHA KALA"], ["DIRECTION", "VJDJ69"], ["EDITING", "MAHA KALA"]],
        },
    }


# --------------------------------------------------------------------------- #
# the real composite
# --------------------------------------------------------------------------- #
@requires_ffmpeg
def test_compose_spec_intro_captions_sfx_and_credits(project_root: Path):
    base = project_root / "work" / "base-fixture.mp4"
    spec_path = project_root / "work" / "graphics-spec.json"
    output = project_root / "renders" / "final-v001.mp4"

    # The module's own loader path drives the composite.
    spec = graphics.load_spec(project_root)
    report = graphics.compose(project_root, base, output, spec_path=spec_path)

    assert output.is_file() and report["output"] == str(output)
    assert report["version"] == graphics.VERSION
    assert report["base"]["sha256"] == report["source"]["sha256"]
    assert report["spec_sha256"] == graphics._digest(spec)
    assert report["implementation_sha256"] == graphics._file_hash(Path(graphics.__file__))

    info = graphics._probe(output)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    audio = next(s for s in info["streams"] if s["codec_type"] == "audio")
    assert video["codec_name"] == "h264" and video["pix_fmt"] == "yuv420p"
    assert (int(video["width"]), int(video["height"])) == SIZE
    assert audio["codec_name"] == "aac"

    # Frames, copied audio packets and faststart all survive the pass.
    assert graphics._count_frames(output) == math.ceil(DURATION * FPS) == BASE_FRAMES
    assert graphics._is_faststart(output) is True
    assert (
        audio_packet_hash(output) == audio_packet_hash(base) == report["base"]["audio_packet_hash"]
    )
    assert report["music"]["base_and_final_audio_identical"] is True
    assert float(audio["duration"]) + 1 / FPS >= DURATION

    # Overlay present exactly where the spec places it: intro, caption, SFX,
    # credits and lockup; nothing in the gaps between the windows.
    for seconds in (5.0, 28.0, 34.0, 50.0, 83.0):
        changed = frame_diff(read_frame(base, seconds), read_frame(output, seconds)) > 12
        assert changed.any(), f"no overlay visible at {seconds}s"
        assert changed.mean() < 0.5, f"overlay at {seconds}s looks opaque"
    for seconds in (26.5, 31.5, 44.5):
        difference = frame_diff(read_frame(base, seconds), read_frame(output, seconds))
        # Re-encoding drifts every pixel by a level or two, and that drift varies
        # with the ffmpeg build; an overlay paints ink. Assert ink coverage, not
        # pixel equality: measured gap drift is ~4e-5 of the frame, while the
        # smallest real overlay (a caption) covers ~1e-2.
        assert (difference > 30).mean() < 0.001, f"overlay ink at {seconds}s"
        assert (difference > 12).mean() < 0.02

    windows = report["windows"]
    assert windows["intro"]["start"] == 0.0
    assert windows["intro"]["end"] == pytest.approx(INTRO_SECONDS, abs=1 / FPS)
    assert [c["id"] for c in windows["captions"]] == ["c1", "c2"]
    assert windows["captions"][0]["start"] == pytest.approx(27.0, abs=0.05)
    assert windows["captions"][0]["text"] == "02:58 AM \u2014 SECTOR 7"
    assert windows["captions"][1]["style"] == "sfx"
    assert windows["captions"][1]["text"] == LONG_SFX
    assert windows["credits"][0]["start"] == pytest.approx(CREDITS_START, abs=0.05)
    assert [c["role"] for c in windows["credits"]] == ["MUSIC", "DIRECTION", "EDITING"]
    assert all(card["end"] <= DURATION + 1 / FPS for card in windows["credits"])
    assert windows["lockup"]["start"] == pytest.approx(DURATION - LOCKUP_SECONDS, abs=0.05)
    assert windows["lockup"]["end"] <= DURATION + 1 / FPS
    assert windows["lockup"]["line"].startswith("A JOINT MAHA KALA & VJDJ69")
    assert report["demo_credits"] is True
    assert len(report["clips"]) == 1 + 2 + 3 + 1

    # The report JSON is durable and content-bound.
    report_path = Path(report["report"])
    assert report_path.is_file() and report_path == output.with_suffix(".json")
    assert json.loads(report_path.read_text())["output_sha256"] == report["output_sha256"]


@requires_ffmpeg
def test_compose_never_overwrites_and_versions(project_root: Path):
    base = project_root / "work" / "base-fixture.mp4"
    target = project_root / "renders" / "final-v001.mp4"
    first = graphics.compose(project_root, base, target)
    second = graphics.compose(project_root, base, target)
    assert second["output"].endswith("-v002.mp4")
    assert Path(first["output"]).is_file() and Path(second["output"]).is_file()


# --------------------------------------------------------------------------- #
# SFX containment: the defect this port fixes
# --------------------------------------------------------------------------- #
def test_sfx_text_sits_fully_inside_the_star_fill():
    palette = graphics.resolve_palette(_spec())
    cap = {"id": "sfx-long", "style": "sfx", "text": LONG_SFX, "x": 0.02, "y": 0.98}
    rgba = np.asarray(graphics.caption_frame(cap, palette, 0.5, 2.0, SIZE))
    alpha = rgba[..., 3].astype(int)

    draw = ImageDraw.Draw(Image.new("RGBA", SIZE))
    geometry = graphics.sfx_geometry(draw, cap, SIZE)
    short = graphics.sfx_geometry(draw, {**cap, "text": "BOOM"}, SIZE)

    # The star is sized from the measured text, not from a fixed radius.
    assert geometry["inner"] > short["inner"]
    assert geometry["outer"] > SIZE[1] * 0.155
    # The centre is clamped so the whole star stays inside the frame safe area.
    edge = max(geometry["margin"], SIZE[1] * graphics.SAFE_MARGIN)
    assert geometry["centre"][0] == pytest.approx(geometry["outer"] + edge)
    assert geometry["centre"][1] == pytest.approx(SIZE[1] - geometry["outer"] - edge)

    night = np.array(palette["night"], dtype=int)
    accent = np.array(palette["accent"], dtype=int)
    dark = (alpha > 240) & (np.abs(rgba[..., :3].astype(int) - night).max(axis=2) <= 8)
    fill = (alpha > 200) & (np.abs(rgba[..., :3].astype(int) - accent).max(axis=2) <= 12)
    interior = _fill_holes(fill)
    core = _erode(interior, 2)
    # Every dark pixel inside the star is the glyph ink, and it must sit at
    # least 2 px inside the solid accent fill: the outline may never cut it.
    assert (dark & core).sum() > 0, "no glyph ink was rendered"
    assert (dark & interior & ~core).sum() == 0, "glyph ink touches the fill boundary"
    # ...while the star outline is still drawn, outside the fill interior.
    assert (dark & ~interior).sum() > 0, "the star outline is missing"

    # The whole star is inside the frame, respects the safe-area margin and
    # never touches an edge.
    drawn = alpha > 0
    ys, xs = np.nonzero(drawn)
    radius = np.hypot(xs - geometry["centre"][0], ys - geometry["centre"][1])
    assert radius.max() <= geometry["outer"] + 2
    assert ys.min() >= SIZE[1] * graphics.SAFE_MARGIN - 2
    assert xs.min() >= geometry["margin"] - 2 and ys.min() >= geometry["margin"] - 2
    assert xs.max() <= SIZE[0] - geometry["margin"] + 1
    assert ys.max() <= SIZE[1] - geometry["margin"] + 1


def test_sfx_raises_when_the_frame_cannot_fit_the_star():
    palette = graphics.resolve_palette(_spec())
    cap = {"id": "sfx-too-big", "style": "sfx", "text": LONG_SFX, "x": 0.5, "y": 0.5}
    with pytest.raises(graphics.ComposeError, match="cannot fit"):
        graphics.caption_frame(cap, palette, 0.5, 2.0, (120, 90))


def test_caption_box_raises_when_the_text_cannot_fit():
    palette = graphics.resolve_palette(_spec())
    cap = {"id": "c-long", "style": "caption", "text": "X" * 400}
    with pytest.raises(graphics.ComposeError, match="cannot be fitted"):
        graphics.caption_frame(cap, palette, 0.5, 2.0, (200, 120))


def test_caption_scrim_contains_its_text():
    palette = graphics.resolve_palette(_spec())
    cap = {"id": "c-ok", "style": "caption", "text": "A RATHER LONG CAPTION LINE"}
    rgba = np.asarray(graphics.caption_frame(cap, palette, 0.5, 2.0, SIZE))
    alpha = rgba[..., 3].astype(int)

    night = np.array(palette["night"], dtype=int)
    ink_colour = np.array(palette["ink"], dtype=int)
    glyph = (alpha > 240) & (np.abs(rgba[..., :3].astype(int) - ink_colour).max(axis=2) <= 8)
    scrim = (alpha > 100) & (np.abs(rgba[..., :3].astype(int) - night).max(axis=2) <= 8)
    core = _erode(_fill_holes(scrim), 2)
    assert glyph.sum() > 0, "the caption text was not rendered"
    # No glyph pixel may leave the scrim or reach within 2 px of its edge.
    assert (glyph & ~core).sum() == 0, "caption text reaches the scrim edge"

    drawn = alpha > 0
    ys, xs = np.nonzero(drawn)
    assert xs.min() > 0 and xs.max() < SIZE[0] - 1
    assert ys.min() > 0 and ys.max() < SIZE[1] - 1


# --------------------------------------------------------------------------- #
# marks, palette and the optional subtitle
# --------------------------------------------------------------------------- #
def test_cat_ears_mark_renders_a_sized_emblem():
    spec = _spec()
    spec["intro"]["mark"] = {"kind": "cat_ears"}
    palette = graphics.resolve_palette(spec)
    accent = np.array(palette["accent"], dtype=int)

    def emblem(frame: np.ndarray) -> np.ndarray:
        mask = (frame[..., 3] > 200) & (
            np.abs(frame[..., :3].astype(int) - accent).max(axis=2) <= 12
        )
        return mask[: int(SIZE[1] * 0.40), :]

    ringed = emblem(np.asarray(graphics.intro_frame(spec, palette, 5.0, SIZE)))
    ys, xs = np.nonzero(ringed)
    half = SIZE[1] * 0.075
    assert ys.size > 100, "the cat-ears emblem is not drawn"
    assert abs((xs.min() + xs.max()) / 2 - SIZE[0] / 2) <= 2
    assert 2 * half * 0.55 <= xs.max() - xs.min() + 1 <= 2 * half + 2
    assert half * 0.9 <= ys.max() - ys.min() + 1 <= 2 * half + 2

    spec["intro"]["mark"] = {"kind": "cat_ears", "ring": False}
    bare_frame = np.asarray(graphics.intro_frame(spec, palette, 5.0, SIZE))
    bare = emblem(bare_frame)
    assert (bare_frame[..., 3] > 0).any(), "ears and slit must still be drawn"
    assert 0 < int(bare.sum()) < int(ringed.sum())


def test_palette_and_mark_defaults_stay_backwards_compatible():
    assert graphics.resolve_palette({}) == graphics.LEGACY_PALETTE
    assert graphics.resolve_mark({"intro": {}}) == {"kind": "signal", "ring": True}
    assert graphics.resolve_palette(_spec()) == {
        "night": (11, 7, 16),
        "ink": (244, 241, 247),
        "accent": (255, 61, 139),
        "secondary": (123, 77, 255),
    }
    with pytest.raises(graphics.ComposeError, match="unsupported intro mark kind"):
        graphics.resolve_mark({"intro": {"mark": {"kind": "dog_ears"}}})


def test_optional_subtitle_renders_under_the_title_only_when_present():
    spec = _spec()
    palette = graphics.resolve_palette(spec)
    without = np.asarray(graphics.intro_frame(spec, palette, 5.0, SIZE))
    assert (without[..., 3] > 0).any()
    spec["intro"]["subtitle"] = "AFTER HOURS"
    with_subtitle = np.asarray(graphics.intro_frame(spec, palette, 5.0, SIZE))

    ink = np.array(palette["ink"], dtype=np.int16)
    secondary = np.array(palette["secondary"], dtype=np.int16)
    tint = (ink * 0.55 + secondary * 0.45).round().astype(np.int16)
    band = slice(int(SIZE[1] * 0.50), int(SIZE[1] * 0.585))

    def tint_pixels(frame: np.ndarray) -> int:
        rows = frame[band, :, :3].astype(np.int16)
        return int((np.abs(rows - tint).sum(axis=2) < 40).sum())

    # Subtitle glyphs sit in their own band under the title, in the blended tint;
    # without a subtitle that band holds no glyphs (the halftone dot band is
    # skipped there so the two can never collide).
    assert tint_pixels(without) == 0
    assert tint_pixels(with_subtitle) > 0


def test_bundled_font_keeps_rendering_portable(monkeypatch):
    """Without the approved local face, the bundled OFL font resolves every weight."""
    from pathlib import Path as _Path

    monkeypatch.setattr(graphics, "FONT_PATH", _Path("/nonexistent/Avenir Next.ttc"))
    graphics.resolve_font.cache_clear()
    graphics._font.cache_clear()
    try:
        path, faces, meta = graphics.resolve_font()
        assert meta["source"] == "bundled-inter"
        assert path.name == "Inter-Regular.ttf"
        assert set(faces) == set(graphics.FACES)
        families = {face: graphics._font(face, 24).getname() for face in graphics.FACES}
        assert {name[0] for name in families.values()} == {"Inter"}
        assert families["demi"][1] == "SemiBold"
        assert families["heavy"][1] == "Bold"
        assert (graphics.FONT_DIR / "OFL.txt").is_file(), "licence must travel with the font"
    finally:
        graphics.resolve_font.cache_clear()
        graphics._font.cache_clear()
