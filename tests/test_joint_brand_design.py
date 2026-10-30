"""The MAHA KALA x VJDJ69 collaboration identity and the ``joint-v1`` design.

Pure-Pillow and JSON tests: no ffmpeg, no project fixture and no provider call.
They pin the properties that make the new brand work — one geometry source, one
identity source, a legacy spec that is untouched, and a closing package that
still fits inside the music.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from mp3_to_videoclip import branding, graphics
from mp3_to_videoclip.models import BrandPackage, Project

FPS = 24
DURATION = 222.8
SIZE = (640, 360)
PRODUCTION_LINE = "A JOINT MAHA KALA & VJDJ69 PRODUCTION"


def _project() -> Project:
    return Project.model_validate(
        {
            "schema_version": 1,
            "slug": "probe",
            "title": "probe",
            "source": "media/song.mp3",
            "source_sha256": "0" * 64,
            "duration": DURATION,
            "aspect": "16:9",
            "fps": FPS,
            "width": SIZE[0],
            "height": SIZE[1],
            "music_mode": "vocal",
            "native_size": [1376, 768],
            "workflow_version": 2,
            "image_model": "google-nano-banana-2-1",
            "style_preset": "photographic-painted-v2",
            "prompt_version": 2,
            "signature_required": True,
        }
    )


def _brand(**overrides) -> dict:
    data = {
        "id": "maha-kala-vjdj69",
        "version": 1,
        "mark": "joint",
        "name": "MAHA KALA  \u00d7  VJDJ69",
        "title": "",
        "duration_seconds": 9.0,
        "foreground": "#F4F1E8",
        "accent": "#D4AE6A",
        "background": "#0B1015",
        "secondary": "#688F9D",
        "plate": False,
    }
    data.update(overrides)
    return data


def _joint_spec() -> dict:
    return {
        "version": 2,
        "demo": False,
        "design": "joint-v1",
        "intro_seconds": 25.0,
        "credits_tail_seconds": 40.0,
        "lockup_seconds": 4.0,
        "intro": {
            "names": "MAHA KALA  \u00d7  VJDJ69",
            "title": "Stof en Stilte",
            "tagline": PRODUCTION_LINE,
            "notes": [],
            "mini_credits": [["MUSIC", "MAHA KALA"], ["FILM DIRECTION", "VJDJ69"]],
            "subtitle": "EEN ODE AAN NEDERHOP",
            "time_line": "OUDE SCHOOL \u00b7 EIGEN STEM",
        },
        "captions": [],
        "credits": {
            "cards": [["MUSIC", "MAHA KALA"], ["FILM DIRECTION", "VJDJ69"]],
            "lockup": PRODUCTION_LINE,
        },
    }


def _root(tmp_path: Path, *, brand: bool = True, spec: dict | None = None) -> Path:
    (tmp_path / "work").mkdir(parents=True, exist_ok=True)
    if brand:
        (tmp_path / "brand.json").write_text(json.dumps(_brand()))
    (tmp_path / "work" / "graphics-spec.json").write_text(json.dumps(spec or _joint_spec()))
    return tmp_path


@pytest.fixture()
def joint(tmp_path: Path) -> dict:
    """The project's spec exactly as ``compose`` sees it: brand already adopted."""
    return graphics.load_spec(_root(tmp_path))


# --------------------------------------------------------------------------- #
# the emblem
# --------------------------------------------------------------------------- #
def test_joint_is_an_offered_mark():
    assert "joint" in branding.MARKS
    assert BrandPackage.model_validate(_brand()).mark == "joint"


def test_joint_plate_draws_ink_and_differs_from_the_other_marks(tmp_path: Path):
    project = _project()
    out = {}
    for mark in ("open-frame", "cutline", "joint"):
        package = BrandPackage.model_validate(_brand(mark=mark))
        path = branding.render_brand_plate(package, project, tmp_path / f"brand-probe-{mark}.png")
        image = Image.open(path)
        assert image.getchannel("A").getbbox() is not None, f"{mark} drew nothing"
        out[mark] = np.asarray(image)
    # The collaboration mark must not be a relabelled open-frame.
    assert not np.array_equal(out["joint"], out["open-frame"])


def test_collaboration_mark_uses_both_colours_and_holds_at_small_size():
    ink, accent = (244, 241, 232), (212, 174, 106)
    for size in (180, 68, 40, 20):
        layer = branding.collaboration_mark_layer(size, ink, accent)
        assert layer.size == (size, size)
        pixels = {tuple(int(v) for v in p[:3]) for p in np.asarray(layer).reshape(-1, 4) if p[3]}
        assert ink in pixels, f"foreground stem missing at {size}px"
        assert accent in pixels, f"accent chevron missing at {size}px"


def test_collaboration_mark_at_zero_alpha_draws_nothing():
    layer = branding.collaboration_mark_layer(120, (244, 241, 232), (212, 174, 106), 0.0)
    assert layer.getchannel("A").getbbox() is None


def test_collaboration_mark_is_anti_aliased():
    # Pillow polygons are not anti-aliased, so the mark is drawn supersampled and
    # reduced; its diagonals must therefore contain partial coverage.
    layer = branding.collaboration_mark_layer(96, (244, 241, 232), (212, 174, 106))
    alpha = np.asarray(layer)[..., 3]
    partial = ((alpha > 0) & (alpha < 255)).sum()
    assert partial > 50, "mark edges are hard; supersampling is not being applied"


def test_collaboration_mark_has_one_stroke_weight():
    # A logo whose parts carry different weights stops looking drawn.
    assert branding.MONOGRAM_STEM == branding.MONOGRAM_ARM


def test_collaboration_mark_fills_the_requested_width():
    size = 120
    layer = branding.collaboration_mark_layer(size, (244, 241, 232), (212, 174, 106))
    # Measure solid coverage: the reduced tile carries a few pixels of faint kernel
    # bleed beyond the geometry, which is not the mark's extent.
    solid = np.asarray(layer)[..., 3] > 128
    cols = np.where(solid.any(axis=0))[0]
    rows = np.where(solid.any(axis=1))[0]
    # The grid's ink bounds map to the tile horizontally, so the mark spans the
    # full requested width...
    assert cols.min() == 0 and cols.max() == size - 1
    # ...and keeps its aspect vertically, so the tile carries a small inset rather
    # than a stretched or cropped letterform.
    expected = (
        size
        * (branding.MONOGRAM_VERTEX - branding.MONOGRAM_TOP)
        / (branding.MONOGRAM_RIGHT - branding.MONOGRAM_LEFT)
    )
    assert abs((rows.max() - rows.min() + 1) - expected) <= 3


def test_paste_collaboration_mark_centres_and_does_not_overrun():
    canvas = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    branding.paste_collaboration_mark(canvas, 200, 200, 80, (244, 241, 232), (212, 174, 106), 1.0)
    alpha = np.asarray(canvas)[..., 3]
    rows, cols = np.where(alpha > 0)
    assert cols.min() >= 200 - 81 and cols.max() <= 200 + 81
    assert rows.min() >= 200 - 81 and rows.max() <= 200 + 81
    # Nothing is drawn outside the requested half-width.
    assert alpha[:, 200 + 90].max() == 0
    assert alpha[200 - 90, :].max() == 0


def test_brand_package_plate_defaults_on_and_can_be_declined():
    assert BrandPackage.model_validate({"id": "x"}).plate is True
    assert BrandPackage.model_validate(_brand()).plate is False


# --------------------------------------------------------------------------- #
# one identity source
# --------------------------------------------------------------------------- #
def test_resolve_design_is_optional_and_validated():
    assert graphics.resolve_design({}) is None
    assert graphics.resolve_design({"design": "joint-v1"}) == graphics.DESIGN_JOINT
    with pytest.raises(graphics.ComposeError):
        graphics.resolve_design({"design": "not-a-design"})


def test_joint_spec_adopts_the_brand_palette_and_emblem(tmp_path: Path):
    spec = graphics.load_spec(_root(tmp_path))
    palette = graphics.resolve_palette(spec)
    assert palette["ink"] == (244, 241, 232)
    assert palette["accent"] == (212, 174, 106)
    assert palette["night"] == (11, 16, 21)
    assert palette["secondary"] == (104, 143, 157)
    assert graphics.resolve_mark(spec)["kind"] == "joint"


def test_an_explicit_spec_palette_still_wins_over_the_brand(tmp_path: Path):
    spec = _joint_spec()
    spec["palette"] = dict(graphics.DEFAULT_PALETTE)
    loaded = graphics.load_spec(_root(tmp_path, spec=spec))
    assert graphics.resolve_palette(loaded)["accent"] != (212, 174, 106)


def test_joint_design_without_a_brand_is_refused(tmp_path: Path):
    with pytest.raises(graphics.ComposeError):
        graphics.load_spec(_root(tmp_path, brand=False))


def test_a_spec_without_a_design_needs_no_brand(tmp_path: Path):
    # The legacy Signal layout must keep working with no brand package at all.
    legacy = _joint_spec()
    legacy.pop("design")
    legacy["palette"] = dict(graphics.DEFAULT_PALETTE)
    legacy["intro"]["mark"] = {"kind": "signal"}
    loaded = graphics.load_spec(_root(tmp_path, brand=False, spec=legacy))
    assert graphics.resolve_design(loaded) is None
    assert graphics.resolve_mark(loaded) == {"kind": "signal", "ring": True}


# --------------------------------------------------------------------------- #
# the closing package
# --------------------------------------------------------------------------- #
def test_joint_closing_opens_with_an_identity_beat_and_still_fits():
    spec = _joint_spec()
    parts, total = graphics._plan_parts(spec, DURATION, FPS)
    kinds = [p["kind"] for p in parts]
    assert kinds[0] == "intro"
    assert kinds[1] == "identity", "the joint closing must open with a partnership card"
    assert kinds[2:] == ["card", "card", "lockup"]

    tail_start = DURATION - spec["credits_tail_seconds"]
    package = [p for p in parts if p["kind"] in ("identity", "card", "lockup")]
    # Windows are whole frames; the package opens on the frame the tail starts in.
    frame = [round(p["start"] * FPS) for p in package]
    assert frame[0] == round(tail_start * FPS)
    assert frame[-1] + package[-1]["frames"] == total
    # Contiguous: no gap and no overlap anywhere in the package.
    for index, (earlier, later) in enumerate(zip(package, package[1:], strict=False)):
        assert frame[index] + earlier["frames"] == frame[index + 1]
        assert later["start"] == frame[index + 1] / FPS
    assert total == round(DURATION * FPS) or total == 5348


def test_a_legacy_spec_has_no_identity_beat():
    spec = _joint_spec()
    spec.pop("design")
    parts, _ = graphics._plan_parts(spec, DURATION, FPS)
    assert "identity" not in [p["kind"] for p in parts]


def test_a_short_credit_tail_degrades_to_the_plain_card_sequence():
    spec = _joint_spec()
    spec["credits_tail_seconds"] = 5.0
    spec["lockup_seconds"] = 5.0
    parts, _ = graphics._plan_parts(spec, DURATION, FPS)
    assert "identity" not in [p["kind"] for p in parts]


def test_joint_intro_phases_are_sampled_against_its_own_choreography():
    legacy = graphics.intro_phase_samples(25.0)
    joint = graphics.intro_phase_samples(25.0, graphics.DESIGN_JOINT)
    assert {s["phase"] for s in legacy} == {s["phase"] for s in joint}
    assert [s["sample_seconds"] for s in legacy] != [s["sample_seconds"] for s in joint]
    # The title must be at full weight no later than the time line starts.
    by_phase = {s["phase"]: s for s in joint}
    assert by_phase["title"]["sample_seconds"] < by_phase["time"]["sample_seconds"]


def test_element_content_binds_the_design_so_caches_cannot_be_reused(joint: dict):
    spec = joint
    intro = graphics.element_content("intro", spec, {"kind": "intro"})
    card = graphics.element_content("card", spec, {"card": ["MUSIC", "MAHA KALA"]})
    lockup = graphics.element_content("lockup", spec, {})
    identity = graphics.element_content("identity", spec, {})
    for content in (intro, card, lockup, identity):
        assert content["design"] == graphics.DESIGN_JOINT
    assert identity["names"] == spec["intro"]["names"]
    assert identity["mark"]["kind"] == "joint"


# --------------------------------------------------------------------------- #
# the frames actually render
# --------------------------------------------------------------------------- #
def test_every_joint_closing_beat_renders_visible_ink(joint: dict):
    spec = joint
    palette = graphics.resolve_palette(spec)
    identity = graphics._joint_identity_frame(spec, palette, 1.0, 6.0, SIZE)
    card = graphics._joint_credit_frame(["MUSIC", "MAHA KALA"], spec, palette, 1.0, 15.0, SIZE)
    lockup = graphics._joint_lockup_frame(spec, palette, 1.0, 4.0, SIZE)
    for name, frame in (("identity", identity), ("card", card), ("lockup", lockup)):
        assert frame.getchannel("A").getbbox() is not None, f"{name} drew nothing"


def test_the_joint_intro_renders_the_emblem_and_the_title(joint: dict):
    spec = joint
    palette = graphics.resolve_palette(spec)
    at_mark = np.asarray(graphics.intro_frame(spec, palette, 4.7, SIZE))
    assert at_mark[..., 3].max() > 0
    # Both emblem colours are actually drawn, and they are the brand's.
    pixels = {tuple(int(v) for v in p[:3]) for p in at_mark.reshape(-1, 4) if p[3]}
    assert (212, 174, 106) in pixels, "the accent bracket is missing"
    assert (244, 241, 232) in pixels, "the ink bracket is missing"


def test_the_joint_scrim_has_no_vertical_edge(joint: dict):
    # A full-width band: its left and right columns are drawn identically, which
    # is what removes the panel edge that could cut a face in the base frame.
    canvas = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    graphics._vertical_scrim(ImageDraw.Draw(canvas), SIZE, 0.6, graphics.resolve_palette(joint))
    alpha = np.asarray(canvas)[..., 3]
    assert alpha.max() > 0
    assert np.array_equal(alpha[:, 0], alpha[:, -1])
