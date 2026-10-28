"""Spec-driven intro, caption and credit graphics for a rendered still film.

This is the reusable package port of the private The Signal v2 compositor. Every
element is drawn locally with Pillow into one sparse RGBA alpha track (qtrle)
that is composited over the rendered base film in a single ffmpeg pass: the
original song, its timing and the base video frame count are untouched and the
base AAC packets are copied verbatim (``-c:a copy``).

A single JSON spec (``work/graphics-spec.json`` by default) drives every text,
colour and window. The spec is backwards compatible with the private script:
without a ``palette`` key the approved Signal colours are used verbatim, without
``intro.mark`` the Signal mark is drawn, and without ``intro.subtitle`` the
intro layout is unchanged.

The SFX starburst measures the text with the chosen font and sizes the star
around it, so a long phrase always sits fully inside the solid fill with a clear
margin; the centre is clamped to keep the whole star inside the frame and an
impossible fit raises rather than drawing broken text. Caption scrims and credit
cards follow the same discipline: text is measured, the box is sized from it,
and an impossible fit raises.

Nothing here calls a provider, uploads anything or approves anything: it is a
local graphics pass over an already-approved base render.

Each overlay window is cached on its own content key (its own rendering inputs,
the palette, canvas, fps, frame count and the implementation revision), so
editing one caption rebuilds only that element; the alpha track is keyed on the
ordered clip hashes and their exact frame timing. A spec may bind a caption to a
storyboard shot (``shot_id`` plus ``offset_frames``/``duration_frames``): the
storyboard is loaded only when such a caption exists and the window is resolved
to frame-accurate seconds by :mod:`mp3_to_videoclip.timeline`. ``--preflight``
writes representative composited stills taken from the real base frames for
inspection and never encodes the film.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import operations
from .branding import load_brand, paste_collaboration_mark
from .models import Storyboard
from .timeline import (
    TimelineError,
    frame_number,
    is_shot_bound,
    label_at_frame,
    resolve_captions,
)

VERSION = "graphics-v1"
#: Bumped whenever the overlay/track cache-key recipe changes incompatibly.
CACHE_SCHEMA = 2
#: Modules whose bytes can change a rendered element or its resolved timing.
#: ``branding.py`` owns the collaboration mark's geometry, which this module
#: draws, so its bytes change rendered pixels just as much as our own do.
IMPLEMENTATION_MODULES = ("graphics.py", "timeline.py", "branding.py")
#: Upper bound on the default representative preflight sample set.
PREFLIGHT_MAX_SAMPLES = 64
#: Storyboard location, relative to the project root.
STORYBOARD_PATH = Path("work") / "storyboard.json"
#: The private compositor's intro is scored against a 25 second reference.
INTRO_REFERENCE_SECONDS = 25.0
#: Named intro phases: (fade-in start, fade-in end, fade-out start, fade-out end)
#: in reference seconds. A phase's sample point is the middle of its
#: full-opacity hold, so a preflight still shows the element at full weight.
INTRO_PHASES = {
    "scrim": (0.8, 2.0, 24.2, 25.0),
    "mark": (0.5, 1.6, 8.4, 9.2),
    "names": (2.25, 3.3, 8.2, 9.0),
    "title": (4.25, 5.4, 10.6, 11.4),
    "time": (8.75, 9.9, 12.3, 13.1),
    "mini_credits_1": (12.4, 13.4, 15.7, 16.5),
    "mini_credits_2": (15.8, 16.8, 19.1, 19.9),
    "tagline": (18.9, 19.9, 21.7, 22.5),
    "notes_1": (21.2, 22.2, 23.7, 24.5),
    "notes_2": (22.4, 23.2, 24.3, 24.9),
}

#: The ``joint-v1`` opening's own choreography, in reference seconds.
#:
#: The legacy table hands the title over to the time line while the title is
#: still ~15% opaque, which reads as a ghosted double exposure rather than a
#: transition. This sequence gives each element a clear window and hands over
#: after the previous one has actually gone.
JOINT_INTRO_PHASES = {
    "scrim": (0.8, 2.0, 24.2, 25.0),
    "mark": (0.6, 1.8, 7.6, 8.8),
    "names": (2.6, 3.8, 7.4, 8.6),
    "title": (8.4, 9.8, 12.1, 13.0),
    "time": (13.1, 14.1, 16.9, 17.7),
    "mini_credits_1": (17.3, 18.2, 19.5, 20.2),
    "mini_credits_2": (19.8, 20.7, 21.9, 22.5),
    "tagline": (22.2, 23.0, 24.3, 24.9),
    "notes_1": (22.9, 23.5, 24.4, 25.0),
    "notes_2": (23.1, 23.7, 24.6, 25.0),
}

#: Palette defaults for a spec that declares ``palette``.
DEFAULT_PALETTE = {
    "night": "#0B0710",
    "ink": "#F4F1F7",
    "accent": "#FF3D8B",
    "secondary": "#7B4DFF",
}

#: The private Signal v2 compositor's colours, used verbatim when a spec has no
#: ``palette`` key so an existing production keeps its approved look.
LEGACY_PALETTE = {
    "night": (10, 12, 16),
    "ink": (244, 241, 232),
    "accent": (216, 255, 62),
    "secondary": (123, 77, 255),
}

MARKS = ("signal", "cat_ears", "joint", "filmstrip")

#: Design variants. ``None`` (no ``design`` key) is the private Signal v2
#: layout, preserved byte-for-byte so existing approved productions are never
#: re-rendered by this change.
DESIGN_JOINT = "joint-v1"
DESIGNS = (DESIGN_JOINT,)

MIN_CAPTION_GAP = 0.25
#: Fraction of the canvas each edge keeps clear of any drawn element. Raised from
#: 0.03 after the Cool Cat typography review found a long SFX burst sitting ~2.5%
#: from the top edge, which is inside broadcast title-safe.
SAFE_MARGIN = 0.07
#: The approved starburst outer/inner radius ratio, kept for the same visual weight.
STAR_RATIO = 0.155 / 0.082
#: Clear margin between the SFX glyph ink and the solid star fill (fraction of height).
SFX_MARGIN = 0.022

FONT_PATH = Path("/System/Library/Fonts/Avenir Next.ttc")
#: Bundled SIL OFL font, so a render is reproducible off this Mac. Chosen only when
#: the approved local face is absent, which keeps existing macOS output unchanged.
FONT_DIR = Path(__file__).with_name("fonts")
BUNDLED_FONTS = {
    "regular": "Inter-Regular.ttf",
    "demi": "Inter-SemiBold.ttf",
    "bold": "Inter-Bold.ttf",
    "heavy": "Inter-Bold.ttf",
}
#: Explicit fallback chain; the chosen face is recorded in the report.
FONT_FALLBACKS = (
    Path("/Library/Fonts/Arial.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    Path("/System/Library/Fonts/Helvetica.ttc"),
)
FACES = {"heavy": 8, "bold": 0, "demi": 2, "regular": 7}


class ComposeError(RuntimeError):
    """Input, geometry or validation failure; nothing is published."""


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def ramp(t: float, start: float, end: float) -> float:
    """Smoothstep 0..1 over [start, end]; identical to the approved study."""
    value = max(0.0, min(1.0, (t - start) / max(end - start, 1e-9)))
    return value * value * (3 - 2 * value)


def _run(argv: list[str]) -> str:
    proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        tail = " | ".join(proc.stderr.strip().splitlines()[-8:])
        raise ComposeError(f"{argv[0]} failed ({proc.returncode}): {tail}")
    return proc.stdout


def _run_bytes(argv: list[str]) -> bytes:
    """Like :func:`_run` but for binary output (raw decoded frames)."""
    proc = subprocess.run(argv, capture_output=True, check=False)
    if proc.returncode != 0:
        tail = " | ".join(proc.stderr.decode(errors="replace").strip().splitlines()[-8:])
        raise ComposeError(f"{argv[0]} failed ({proc.returncode}): {tail}")
    return proc.stdout


def _probe(path: Path) -> dict:
    return json.loads(
        _run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)])
    )


def _count_frames(path: Path) -> int:
    info = json.loads(
        _run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-count_frames",
                "-show_entries",
                "stream=nb_read_frames",
                "-of",
                "json",
                str(path),
            ]
        )
    )
    return int(info["streams"][0]["nb_read_frames"])


def _audio_packet_hash(path: Path) -> str:
    out = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_packets",
            "-show_data_hash",
            "sha256",
            "-show_entries",
            "packet=pts,dts,duration,size,flags,data_hash",
            "-of",
            "compact=p=0",
            str(path),
        ]
    )
    return hashlib.sha256(out.encode()).hexdigest()


def _is_faststart(path: Path) -> bool:
    with path.open("rb") as handle:
        head = handle.read(2 * 1024 * 1024)
    moov, mdat = head.find(b"moov"), head.find(b"mdat")
    return moov != -1 and (mdat == -1 or moov < mdat)


def _digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


@lru_cache(maxsize=1)
def implementation_revision() -> str:
    """Digest of the modules that can change a rendered element or its timing."""
    here = Path(__file__).resolve().parent
    import PIL

    font, faces, _ = resolve_font()
    return _digest(
        {
            "modules": {
                name: _file_hash(here / name)
                for name in IMPLEMENTATION_MODULES
                if (here / name).is_file()
            },
            "font_sha256": _file_hash(font),
            "bundled_fonts": {
                name: _file_hash(FONT_DIR / name)
                for name in sorted(set(BUNDLED_FONTS.values()))
                if (FONT_DIR / name).is_file()
            },
            "faces": faces,
            "pillow": PIL.__version__,
        }
    )


def _ink(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[float, float, float, float]:
    """Measured ink of ``text``: (width, height, left offset, top offset)."""
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1], box[0], box[1]


def _fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    face: str,
    nominal: float,
    max_width: float,
    max_height: float,
) -> ImageFont.FreeTypeFont:
    """Largest font at or below ``nominal`` whose measured ink fits the box.

    The nominal size is used whenever it fits, so approved layouts are unchanged.
    Below the minimum legible size nothing is guessed: an impossible fit raises.
    """
    size = max(6, int(nominal))
    floor = max(6, int(round(size * 0.45)))
    while True:
        font = _font(face, size)
        ink_w, ink_h, _left, _top = _ink(draw, text, font)
        if ink_w <= max_width and ink_h <= max_height:
            return font
        if size <= floor:
            raise ComposeError(
                f"text {text!r} cannot be fitted into {round(max_width)}x{round(max_height)} px "
                "at the minimum legible size"
            )
        size = max(floor, int(size * 0.9))


def _centred(
    draw: ImageDraw.ImageDraw,
    canvas,
    y: float,
    text: str,
    font,
    colour: tuple[int, int, int],
    alpha: float,
) -> None:
    ink_w, _ink_h, ink_left, ink_top = _ink(draw, text, font)
    x = (canvas[0] - ink_w) / 2 - ink_left
    if x < canvas[0] * SAFE_MARGIN or x + ink_w > canvas[0] * (1 - SAFE_MARGIN):
        raise ComposeError(f"text {text!r} breaks the horizontal safe margin")
    draw.text(
        (x, y - ink_top), text, font=font, fill=(*colour, round(255 * max(0.0, min(1.0, alpha))))
    )


# --------------------------------------------------------------------------- #
# fonts: local Avenir Next, explicit recorded fallback, never a silent download
# --------------------------------------------------------------------------- #
def _usable_faces(path: Path) -> dict[str, int]:
    """Face indexes that actually load from ``path`` (a TTC may lack a face)."""
    usable: dict[str, int] = {}
    for face, index in FACES.items():
        try:
            ImageFont.truetype(str(path), size=12, index=index)
        except (OSError, ValueError):  # pragma: no cover - depends on local fonts
            continue
        usable[face] = index
    return usable


@lru_cache(maxsize=1)
def resolve_font() -> tuple[Path, dict[str, int], dict]:
    """The approved local face, else the bundled OFL font, else a documented fallback."""
    if FONT_PATH.is_file():
        usable = _usable_faces(FONT_PATH)
        if usable:
            anchor = usable.get("regular", min(usable.values()))
            resolved = {face: usable.get(face, anchor) for face in FACES}
            return FONT_PATH, resolved, {"source": "local-avenir-next", "path": str(FONT_PATH)}
    bundled = FONT_DIR / BUNDLED_FONTS["regular"]
    if bundled.is_file() and _usable_faces(bundled):
        return (
            bundled,
            {face: 0 for face in FACES},
            {
                "source": "bundled-inter",
                "path": str(bundled),
                "license": "SIL Open Font License 1.1 (fonts/OFL.txt)",
            },
        )
    for candidate in FONT_FALLBACKS:
        if not candidate.is_file():
            continue
        usable = _usable_faces(candidate)
        if not usable:
            continue
        anchor = usable.get("regular", min(usable.values()))
        resolved = {face: usable.get(face, anchor) for face in FACES}
        return (
            candidate,
            resolved,
            {
                "source": "documented-fallback",
                "path": str(candidate),
                "note": f"Avenir Next unavailable; using {candidate.name}",
            },
        )
    raise ComposeError("no local font available; refusing to silently substitute")


@lru_cache(maxsize=32)
def _font(face: str, size: int) -> ImageFont.FreeTypeFont:
    if face not in FACES:
        raise ComposeError(f"unknown font face {face!r}")
    path, indexes, meta = resolve_font()
    index = indexes.get(face, 0)
    if meta.get("source") == "bundled-inter":
        path = FONT_DIR / BUNDLED_FONTS[face]
        index = 0
    return ImageFont.truetype(str(path), size=max(6, int(size)), index=index)


# --------------------------------------------------------------------------- #
# spec: palette, mark and windows
# --------------------------------------------------------------------------- #
def _parse_colour(value, key: str) -> tuple[int, int, int]:
    if isinstance(value, (list, tuple)) and len(value) == 3:
        channels = tuple(int(channel) for channel in value)
        if any(channel < 0 or channel > 255 for channel in channels):
            raise ComposeError(f"palette {key} channel out of range")
        return channels  # type: ignore[return-value]
    if not isinstance(value, str) or len(value.lstrip("#")) != 6:
        raise ComposeError(f"palette {key} must be a #RRGGBB string")
    raw = value.lstrip("#")
    try:
        return (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))
    except ValueError as exc:
        raise ComposeError(f"palette {key}={value!r} is not valid hex") from exc


def resolve_palette(spec: dict) -> dict[str, tuple[int, int, int]]:
    """Resolve the drawing palette, keeping the private colours by default.

    A spec without ``palette`` renders exactly like the private compositor; a
    spec with one gets :data:`DEFAULT_PALETTE` for every key it leaves out.
    """
    raw = spec.get("palette")
    if raw is None:
        return dict(LEGACY_PALETTE)
    if not isinstance(raw, dict):
        raise ComposeError("palette must be an object of #RRGGBB colours")
    unknown = sorted(set(raw) - set(DEFAULT_PALETTE))
    if unknown:
        raise ComposeError(f"unsupported palette keys: {unknown}")
    return {key: _parse_colour(raw.get(key, DEFAULT_PALETTE[key]), key) for key in DEFAULT_PALETTE}


def resolve_design(spec: dict) -> str | None:
    """Resolve the optional ``design`` key; ``None`` keeps the Signal v2 layout."""
    design = spec.get("design")
    if design is None:
        return None
    if design not in DESIGNS:
        raise ComposeError(
            f"unsupported graphics design {design!r}; expected one of {list(DESIGNS)}"
        )
    return design


def _adopt_brand_identity(spec: dict, root: Path) -> None:
    """Make ``brand.json`` the single source of palette and emblem for a design.

    Without this the film's opening and the render-time brand plate each restate
    their own colours and mark, which is how a production ends up with two
    half-identities. An explicit ``palette`` or ``intro.mark`` in the spec still
    wins, so a per-film override remains possible without editing the brand.
    """
    brand = load_brand(Path(root))
    if brand is None:
        raise ComposeError(
            "design 'joint-v1' needs the project's brand.json as its identity source; "
            "create one or drop the design key"
        )
    if spec.get("palette") is None:
        spec["palette"] = {
            "night": brand.background,
            "ink": brand.foreground,
            "accent": brand.accent,
            "secondary": brand.secondary,
        }
    if spec["intro"].get("mark") is None:
        spec["intro"]["mark"] = {"kind": "filmstrip" if brand.mark == "filmstrip" else "joint"}


def resolve_mark(spec: dict) -> dict:
    """Resolve ``intro.mark``; ``{"kind": "signal"}`` is the backwards-compatible default."""
    mark = spec["intro"].get("mark", {"kind": "signal"})
    if mark is None:
        mark = {"kind": "signal"}
    if not isinstance(mark, dict):
        raise ComposeError('intro mark must be an object like {"kind": "signal"}')
    kind = mark.get("kind", "signal")
    if kind == "filmstrip" and spec.get("renderer") != "remotion":
        raise ComposeError("filmstrip graphics require the Remotion renderer")
    if kind not in MARKS:
        raise ComposeError(f"unsupported intro mark kind {kind!r}; expected one of {list(MARKS)}")
    ring = mark.get("ring", True)
    if not isinstance(ring, bool):
        raise ComposeError("intro mark ring must be true or false")
    return {"kind": kind, "ring": ring}


def validate_layout(spec: dict) -> None:
    """An explicit compact layout is Remotion-only; never silently ignore controls."""
    if "layout" not in spec:
        return
    layout = spec["layout"]
    if not isinstance(layout, dict) or layout.get("kind") != "compact-v1":
        raise ComposeError("layout must be an explicit compact-v1 object or omitted")
    if spec.get("renderer") != "remotion":
        raise ComposeError("compact-v1 layout requires Remotion")
    if set(layout) - {"kind", "identity_switch_frame", "handoff_frames"}:
        raise ComposeError("unknown compact layout control")
    switch, fade = layout.get("identity_switch_frame"), layout.get("handoff_frames")
    if ("identity_switch_frame" in layout) != ("handoff_frames" in layout):
        raise ComposeError("compact identity handoff needs both frame controls")
    if "identity_switch_frame" in layout and (
        type(switch) is not int or type(fade) is not int or fade < 1 or switch < fade
    ):
        raise ComposeError("invalid compact handoff frames")


def load_spec(root: Path, path: Path | None = None) -> dict:
    """Load and validate ``root/work/graphics-spec.json`` (or ``path``)."""
    spec_path = Path(path) if path else Path(root) / "work/graphics-spec.json"
    spec = json.loads(spec_path.read_text())
    validate_layout(spec)
    if spec.get("renderer", "pillow") not in ("pillow", "remotion"):
        raise ComposeError("unknown graphics renderer")
    if spec.get("renderer") == "remotion":
        from .remotion import implementation_hash

        spec["renderer_revision"] = implementation_hash()
    for key in (
        "intro_seconds",
        "credits_tail_seconds",
        "lockup_seconds",
        "intro",
        "captions",
        "credits",
    ):
        if key not in spec:
            raise ComposeError(f"graphics spec is missing {key}")
    if not (5 <= float(spec["intro_seconds"]) <= 30):
        raise ComposeError("intro_seconds must be between 5 and 30")
    if not (5 <= float(spec["credits_tail_seconds"]) <= 60):
        raise ComposeError("credits_tail_seconds must be between 5 and 60")
    for key in ("names", "title"):
        if not spec["intro"].get(key):
            raise ComposeError(f"intro needs {key}")
    subtitle = spec["intro"].get("subtitle")
    if subtitle is not None and not isinstance(subtitle, str):
        raise ComposeError("intro subtitle must be a string")
    for cap in spec["captions"]:
        if not isinstance(cap, dict) or not isinstance(cap.get("id"), str) or not cap["id"].strip():
            raise ComposeError("each caption needs a non-empty string id")
        if cap.get("style") not in ("caption", "sfx") or not cap.get("text"):
            raise ComposeError(f"caption {cap.get('id')} needs style caption|sfx and text")
        if cap["style"] == "sfx" and ("x" not in cap or "y" not in cap):
            raise ComposeError(f"sfx caption {cap['id']} needs x and y")
    if not spec["credits"].get("cards") or not spec["credits"].get("lockup"):
        raise ComposeError("credits need cards and a lockup line")
    if resolve_design(spec) == DESIGN_JOINT:
        _adopt_brand_identity(spec, Path(root))
    resolve_palette(spec)
    resolve_mark(spec)
    if len({c["id"] for c in spec["captions"]}) != len(spec["captions"]):
        raise ComposeError("caption ids must be unique")
    return spec


# --------------------------------------------------------------------------- #
# marks: local shapes only, never a generated image
# --------------------------------------------------------------------------- #
def _draw_signal_mark(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    half: float,
    gap: float,
    stroke: int,
    palette: dict,
    alpha: float,
) -> None:
    """The approved Signal mark: two assembling corner forms."""
    first = [(cx - half, cy + half - gap), (cx - half, cy - half), (cx + half - gap, cy - half)]
    second = [
        (cx + half, cy - half + gap),
        (cx + half, cy + half),
        (cx - half + gap, cy + half),
    ]
    draw.line(first, fill=(*palette["ink"], round(255 * alpha)), width=stroke, joint="curve")
    draw.line(second, fill=(*palette["accent"], round(255 * alpha)), width=stroke, joint="curve")


def _draw_cat_ears(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    half: float,
    stroke: int,
    palette: dict,
    alpha: float,
    ring: bool = True,
) -> None:
    """A ring emblem with two cat ears and a sunglasses slit, sized from ``half``.

    Drawn in accent on night: the ears sit on the ring, and the slit bar crosses
    the ring in the night colour so it reads as a pair of sunglasses. Set
    ``ring`` false to keep only the ears and the slit.
    """
    accent = (*palette["accent"], round(255 * alpha))
    night = (*palette["night"], round(255 * alpha))
    ring_r = max(2.0, half * 0.62)
    ring_w = max(2, round(stroke * 0.9))
    if ring:
        draw.ellipse(
            (cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r), outline=accent, width=ring_w
        )
    apex = half * 0.98
    half_span = math.radians(15.0)
    for direction in (-1.0, 1.0):
        mid = math.radians(34.0) * direction - math.pi / 2
        base = [
            (cx + ring_r * math.cos(mid + offset), cy + ring_r * math.sin(mid + offset))
            for offset in (-half_span, half_span)
        ]
        tip = (cx + apex * math.cos(mid), cy + apex * math.sin(mid))
        draw.polygon([*base, tip], fill=accent)
    bar_h = max(3, round(half * 0.20))
    # The slit reads as sunglasses only as two lenses with a bridge; a single
    # full-width bar read as a "no entry" sign in the typography review.
    lens_w = max(4.0, ring_r * 0.46)
    lens_gap = max(2.0, ring_r * 0.16)
    for direction in (-1.0, 1.0):
        cx_lens = cx + direction * (lens_gap + lens_w) / 2
        draw.rounded_rectangle(
            (cx_lens - lens_w / 2, cy - bar_h / 2, cx_lens + lens_w / 2, cy + bar_h / 2),
            radius=bar_h / 2,
            fill=night,
        )
    draw.rounded_rectangle(
        (cx - lens_gap / 2, cy - bar_h / 4, cx + lens_gap / 2, cy + bar_h / 4),
        radius=bar_h / 4,
        fill=night,
    )


def _draw_mark(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    mark: dict,
    cx: float,
    cy: float,
    half: float,
    gap: float,
    stroke: int,
    palette: dict,
    alpha: float,
) -> None:
    """Draw the resolved mark. ``img`` is only needed by the supersampled mark."""
    if mark["kind"] == "cat_ears":
        _draw_cat_ears(draw, cx, cy, half, stroke, palette, alpha, mark["ring"])
    elif mark["kind"] == "joint":
        # Geometry lives in branding.py, composited as its own anti-aliased layer
        # so the brand plate and the film overlay can never show two emblems.
        paste_collaboration_mark(img, cx, cy, half, palette["ink"], palette["accent"], alpha)
    else:
        _draw_signal_mark(draw, cx, cy, half, gap, stroke, palette, alpha)


# --------------------------------------------------------------------------- #
# frame renderers (one Pillow layer per element)
# --------------------------------------------------------------------------- #
def _scrim(draw, box, radius, alpha, palette):
    if alpha > 0:
        draw.rounded_rectangle(
            box, radius=max(2, round(radius)), fill=(*palette["night"], round(alpha))
        )


def _vertical_scrim(draw, canvas, alpha, palette) -> None:
    """A full-width soft vertical band.

    The private layout protects the lettering with a rounded rectangle, whose
    vertical edge can land across a face in the underlying frame. A band that
    spans the whole width and fades smoothly top and bottom has no vertical edge
    to cut anything, so the composition stays intact under the typography.
    """
    if alpha <= 0:
        return
    width, height = canvas
    y0, y1 = height * 0.06, height * 0.97
    span = max(1.0, y1 - y0)
    steps = max(2, round(span / 2))
    night = palette["night"]
    for index in range(steps + 1):
        t = index / steps
        # Ramp in over the first fifth and out over the last fifth: a band with
        # no visible hard top or bottom edge either.
        edge = min(1.0, 5.0 * min(t, 1.0 - t))
        draw.line(
            [(0, y0 + t * span), (width, y0 + t * span)],
            fill=(*night, round(255 * alpha * edge)),
        )


def _centred_fit(
    draw,
    canvas,
    y: float,
    text: str,
    face: str,
    nominal: float,
    colour,
    alpha: float,
    max_ratio: float = 1.0,
) -> None:
    """Centred text that shrinks to stay inside the safe width.

    ``_centred`` refuses to draw text that would cross the safe margin. A long
    but legitimate line (a partnership wordmark, a joint-production sentence)
    should scale down instead of failing the whole composite, so measure first.
    """
    limit = canvas[0] * (1 - 2 * SAFE_MARGIN) * max_ratio
    font = _fit_font(draw, text, face, nominal, limit, nominal * 2.4)
    _centred(draw, canvas, y, text, font, colour, alpha)


def _joint_intro_frame(spec: dict, palette: dict, t: float, canvas: tuple[int, int]) -> Image.Image:
    """The named ``joint-v1`` opening: the collaboration emblem leads.

    The film title and the joint identity each get their own moment rather than
    being stacked into one block, so the emblem — not the film title — is what a
    viewer recognises on a second film from the same two makers.
    """
    width, height = canvas
    img = Image.new("RGBA", canvas, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    intro = spec["intro"]
    k = float(spec["intro_seconds"]) / INTRO_REFERENCE_SECONDS

    def phase(name: str) -> float:
        fade_in_start, fade_in_end, fade_out_start, fade_out_end = JOINT_INTRO_PHASES[name]
        return ramp(t, fade_in_start * k, fade_in_end * k) * (
            1 - ramp(t, fade_out_start * k, fade_out_end * k)
        )

    _vertical_scrim(draw, canvas, 0.62 * phase("scrim"), palette)

    ink, accent, secondary = palette["ink"], palette["accent"], palette["secondary"]
    mark_a, names_a, title_a = phase("mark"), phase("names"), phase("title")
    time_a, tag_a = phase("time"), phase("tagline")

    if mark_a > 0:
        _draw_mark(
            img,
            draw,
            resolve_mark(spec),
            width / 2,
            height * 0.225,
            height * 0.095,
            height * 0.016,
            max(4, round(height * 0.0115)),
            palette,
            mark_a,
        )
    if names_a > 0:
        _centred_fit(
            draw, canvas, height * 0.385, intro["names"], "demi", height * 0.036, ink, names_a, 0.9
        )
    rule_a = max(names_a, title_a)
    if rule_a > 0:
        half = width * 0.042
        y = height * 0.428
        thickness = max(2, round(height * 0.0035))
        draw.rectangle(
            (width / 2 - half, y, width / 2 + half, y + thickness),
            fill=(*accent, round(255 * rule_a)),
        )
    if title_a > 0:
        _centred_fit(
            draw,
            canvas,
            height * 0.512,
            intro["title"],
            "heavy",
            height * 0.098,
            ink,
            title_a,
            0.95,
        )
    subtitle = intro.get("subtitle")
    if title_a > 0 and subtitle:
        tint = tuple(round(ink[i] * 0.70 + secondary[i] * 0.30) for i in range(3))
        _centred_fit(
            draw, canvas, height * 0.612, subtitle, "demi", height * 0.031, tint, title_a, 0.9
        )
    if time_a > 0 and intro.get("time_line"):
        _centred_fit(
            draw,
            canvas,
            height * 0.678,
            intro["time_line"],
            "heavy",
            height * 0.038,
            accent,
            time_a,
            0.9,
        )
    for index, (role, name) in enumerate(intro.get("mini_credits", [])[:2]):
        alpha = phase("mini_credits_1" if index == 0 else "mini_credits_2")
        if alpha <= 0:
            continue
        role_y = height * (0.734 if index == 0 else 0.808)
        _centred_fit(draw, canvas, role_y, role, "bold", height * 0.020, accent, alpha * 0.92, 0.8)
        _centred_fit(
            draw, canvas, role_y + height * 0.034, name, "demi", height * 0.036, ink, alpha, 0.9
        )
    if tag_a > 0 and intro.get("tagline"):
        _centred_fit(
            draw,
            canvas,
            height * 0.902,
            intro["tagline"],
            "regular",
            height * 0.026,
            ink,
            tag_a * 0.9,
        )
    notes = intro.get("notes", [])[:2]
    for index, note in enumerate(notes):
        alpha = phase("notes_1" if index == 0 else "notes_2")
        if alpha > 0:
            _centred_fit(
                draw,
                canvas,
                height * (0.938 if index == 0 else 0.962),
                note,
                "regular",
                height * 0.019,
                ink,
                alpha * 0.8,
            )
    return img


def _joint_identity_frame(
    spec: dict, palette: dict, local_t: float, seconds: float, canvas: tuple[int, int]
) -> Image.Image:
    """The closing partnership card: who made this, before who did what."""
    width, height = canvas
    img = Image.new("RGBA", canvas, (0, 0, 0, 0))
    fade = min(0.6, seconds / 4)
    alpha = ramp(local_t, 0.0, fade) * (1 - ramp(local_t, seconds - fade, seconds))
    if alpha <= 0:
        return img
    draw = ImageDraw.Draw(img)
    _vertical_scrim(draw, canvas, 0.58 * alpha, palette)
    ink, accent = palette["ink"], palette["accent"]
    _draw_mark(
        img,
        draw,
        resolve_mark(spec),
        width / 2,
        height * 0.352,
        height * 0.072,
        height * 0.012,
        max(4, round(height * 0.0088)),
        palette,
        alpha,
    )
    _centred_fit(
        draw,
        canvas,
        height * 0.483,
        spec["intro"]["names"],
        "heavy",
        height * 0.042,
        ink,
        alpha,
        0.9,
    )
    half = width * 0.042
    y = height * 0.530
    thickness = max(2, round(height * 0.0032))
    draw.rectangle(
        (width / 2 - half, y, width / 2 + half, y + thickness),
        fill=(*accent, round(255 * alpha)),
    )
    if spec["intro"].get("tagline"):
        _centred_fit(
            draw,
            canvas,
            height * 0.585,
            spec["intro"]["tagline"],
            "regular",
            height * 0.025,
            ink,
            alpha * 0.85,
        )
    return img


def _joint_credit_frame(
    card, spec: dict, palette: dict, local_t: float, seconds: float, canvas: tuple[int, int]
) -> Image.Image:
    """A closing role card with the emblem, a rule and a real hierarchy."""
    width, height = canvas
    img = Image.new("RGBA", canvas, (0, 0, 0, 0))
    fade = 0.5
    alpha = ramp(local_t, 0.0, fade) * (1 - ramp(local_t, seconds - fade, seconds))
    if alpha <= 0:
        return img
    draw = ImageDraw.Draw(img)
    role, name = card
    _vertical_scrim(draw, canvas, 0.50 * alpha, palette)
    ink, accent = palette["ink"], palette["accent"]
    x = width * SAFE_MARGIN
    limit = width * (1 - 2 * SAFE_MARGIN)
    # The mark sizes the text column: the role line starts clear of the emblem's
    # ink instead of crowding it, and the rule then spans mark plus text.
    mark_half = height * 0.024
    mark_gap = height * 0.026
    text_x = x + 2 * mark_half + mark_gap
    _draw_mark(
        img,
        draw,
        resolve_mark(spec),
        x + mark_half,
        height * 0.575,
        mark_half,
        height * 0.005,
        max(3, round(height * 0.0032)),
        palette,
        alpha,
    )
    role_font = _fit_font(draw, role, "bold", height * 0.022, limit, height * 0.032)
    ink_w = _ink(draw, role, role_font)[0]
    draw.text(
        (text_x, height * 0.560),
        role,
        font=role_font,
        fill=(*accent, round(245 * alpha)),
    )
    rule_y = height * 0.632
    draw.rectangle(
        (x, rule_y, text_x + ink_w, rule_y + max(2, round(height * 0.0032))),
        fill=(*accent, round(215 * alpha)),
    )
    name_y = rule_y + height * 0.030
    name_font = _fit_font(draw, name, "heavy", height * 0.058, limit, height * 0.082)
    draw.text((x, name_y), name, font=name_font, fill=(*ink, round(255 * alpha)))
    return img


def _joint_lockup_frame(
    spec: dict, palette: dict, local_t: float, seconds: float, canvas: tuple[int, int]
) -> Image.Image:
    """The closing signature: emblem, joint line and the film title, resolved."""
    width, height = canvas
    img = Image.new("RGBA", canvas, (0, 0, 0, 0))
    fade = 0.5
    alpha = ramp(local_t, 0.0, fade) * (1 - ramp(local_t, seconds - fade, seconds))
    if alpha <= 0:
        return img
    draw = ImageDraw.Draw(img)
    _vertical_scrim(draw, canvas, 0.60 * alpha, palette)
    ink, accent = palette["ink"], palette["accent"]
    _draw_mark(
        img,
        draw,
        resolve_mark(spec),
        width / 2,
        height * 0.395,
        height * 0.052,
        height * 0.009,
        max(3, round(height * 0.0065)),
        palette,
        alpha,
    )
    _centred_fit(
        draw,
        canvas,
        height * 0.512,
        spec["credits"]["lockup"],
        "heavy",
        height * 0.038,
        ink,
        alpha,
        0.92,
    )
    half = width * 0.030
    y = height * 0.560
    thickness = max(2, round(height * 0.0028))
    draw.rectangle(
        (width / 2 - half, y, width / 2 + half, y + thickness),
        fill=(*accent, round(255 * alpha)),
    )
    _centred_fit(
        draw,
        canvas,
        height * 0.612,
        spec["intro"]["names"],
        "demi",
        height * 0.027,
        ink,
        alpha * 0.9,
    )
    if spec["intro"].get("title"):
        _centred_fit(
            draw,
            canvas,
            height * 0.668,
            spec["intro"]["title"],
            "regular",
            height * 0.028,
            ink,
            alpha * 0.8,
        )
    return img


def intro_frame(spec: dict, palette: dict, t: float, canvas: tuple[int, int]) -> Image.Image:
    """One frame of the comic intro at film time ``t`` (seconds)."""
    if resolve_design(spec) == DESIGN_JOINT:
        return _joint_intro_frame(spec, palette, t, canvas)
    width, height = canvas
    img = Image.new("RGBA", canvas, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    intro = spec["intro"]
    seconds = float(spec["intro_seconds"])
    k = seconds / INTRO_REFERENCE_SECONDS

    def T(x):
        return x * k

    def phase(name: str) -> float:
        fade_in_start, fade_in_end, fade_out_start, fade_out_end = INTRO_PHASES[name]
        return ramp(t, T(fade_in_start), T(fade_in_end)) * (
            1 - ramp(t, T(fade_out_start), T(fade_out_end))
        )

    scrim = 0.32 * phase("scrim")
    mark_a = phase("mark")
    names_a = phase("names")
    title_a = phase("title")
    time_a = phase("time")
    mini1_a = phase("mini_credits_1")
    mini2_a = phase("mini_credits_2")
    tag_a = phase("tagline")
    note1_a = phase("notes_1")
    note2_a = phase("notes_2")

    _scrim(
        draw,
        (width * 0.24, height * 0.19, width * 0.76, height * 0.945),
        height * 0.02,
        scrim * 255,
        palette,
    )

    # Radiating comic burst behind the title.
    if title_a > 0:
        cx, cy = width / 2, height * 0.455
        for i in range(24):
            angle = i * math.pi / 12 + 0.13
            # The ray ring sits between the names and the time line so no ray
            # crosses the lettering block (typography review finding).
            r0 = height * 0.152
            r1 = height * (0.196 + 0.038 * (0.5 + 0.5 * math.sin(i * 2.399)))
            draw.line(
                (
                    cx + r0 * math.cos(angle),
                    cy + r0 * math.sin(angle),
                    cx + r1 * math.cos(angle),
                    cy + r1 * math.sin(angle),
                ),
                fill=(*palette["ink"], round(70 * title_a)),
                width=max(2, round(height * 0.0022)),
            )
        if intro.get("subtitle"):
            # Hold the title block on a clean plate so the burst rays never cut
            # through the lettering (found in the Cool Cat typography review).
            # The plate is a soft stack of bands rather than one hard rectangle,
            # so its edge does not truncate the rays into a straight line.
            for step in range(4):
                inset = width * (0.012 + 0.010 * step)
                _scrim(
                    draw,
                    (
                        width * 0.235 + inset,
                        height * 0.322 + step * height * 0.004,
                        width * 0.765 - inset,
                        height * 0.716 - step * height * 0.004,
                    ),
                    height * 0.02,
                    46 * title_a,
                    palette,
                )
        # Halftone dot band under the title; skipped when a subtitle occupies
        # that band, otherwise the two collide.
        if not intro.get("subtitle"):
            spacing = height * 0.016
            for row in range(3):
                y = height * 0.545 + row * spacing
                steps = int((width * 0.36) / spacing)
                for col in range(steps + 1):
                    x = width / 2 - width * 0.18 + col * spacing + (row % 2) * spacing / 2
                    r = height * 0.0022
                    draw.ellipse(
                        (x - r, y - r, x + r, y + r),
                        fill=(*palette["accent"], round(120 * title_a)),
                    )

    if mark_a > 0:
        _draw_mark(
            img,
            draw,
            resolve_mark(spec),
            width / 2,
            height * 0.265,
            height * 0.075,
            height * 0.0134,
            max(4, round(height * 0.0093)),
            palette,
            mark_a,
        )

    if names_a > 0:
        _centred(
            draw,
            canvas,
            height * 0.360,
            intro["names"],
            _font("demi", height * 0.036),
            palette["ink"],
            names_a,
        )
    if title_a > 0:
        _centred(
            draw,
            canvas,
            height * 0.443,
            intro["title"],
            _font("heavy", height * 0.106),
            palette["ink"],
            title_a,
        )
    subtitle = intro.get("subtitle")
    if title_a > 0 and subtitle:
        ink, secondary = palette["ink"], palette["secondary"]
        # Violet alone washed out over the dark scrim; blend toward the ink so
        # the subtitle stays readable while keeping the violet identity.
        tint = tuple(round(ink[i] * 0.72 + secondary[i] * 0.28) for i in range(3))
        _centred(
            draw,
            canvas,
            height * 0.545,
            subtitle,
            _font("demi", height * 0.034),
            tint,
            title_a,
        )
    if time_a > 0 and intro.get("time_line"):
        _centred(
            draw,
            canvas,
            height * 0.652,
            intro["time_line"],
            _font("heavy", height * 0.042),
            palette["accent"],
            time_a,
        )
    for index, (role, name) in enumerate(intro.get("mini_credits", [])[:2]):
        alpha = mini1_a if index == 0 else mini2_a
        if alpha <= 0:
            continue
        base_y = height * (0.735 if index == 0 else 0.805)
        _centred(
            draw, canvas, base_y, role, _font("bold", height * 0.020), palette["ink"], alpha * 0.85
        )
        _centred(
            draw,
            canvas,
            base_y + height * 0.032,
            name,
            _font("demi", height * 0.034),
            palette["ink"],
            alpha,
        )
    if tag_a > 0 and intro.get("tagline"):
        _centred(
            draw,
            canvas,
            height * 0.60,
            intro["tagline"],
            _font("regular", height * 0.030),
            palette["ink"],
            tag_a,
        )
    for index, note in enumerate(intro.get("notes", [])[:2]):
        alpha = note1_a if index == 0 else note2_a
        if alpha > 0:
            _centred(
                draw,
                canvas,
                height * (0.885 if index == 0 else 0.912),
                note,
                _font("regular", height * 0.021),
                palette["ink"],
                alpha * 0.8,
            )
    return img


def intro_phase_samples(intro_seconds: float, design: str | None = None) -> list[dict]:
    """Every named intro phase with a full-opacity sample time in real seconds.

    The sample point sits between the end of the fade-in and the start of the
    fade-out, so a preflight still shows the phase at full weight rather than
    mid-fade. Times scale with the spec's ``intro_seconds`` exactly like
    :func:`intro_frame` does, and the ``joint-v1`` design is sampled against its
    own choreography so a preflight still never lands mid-handover.
    """
    table = JOINT_INTRO_PHASES if design == DESIGN_JOINT else INTRO_PHASES
    scale = float(intro_seconds) / INTRO_REFERENCE_SECONDS
    samples = []
    for name, (in_start, in_end, out_start, out_end) in table.items():
        samples.append(
            {
                "phase": name,
                "start_seconds": in_start * scale,
                "end_seconds": out_end * scale,
                "sample_seconds": (in_end + out_start) / 2 * scale,
            }
        )
    return samples


def sfx_geometry(draw: ImageDraw.ImageDraw, cap: dict, canvas: tuple[int, int]) -> dict:
    """Star geometry that keeps the measured SFX text inside the solid fill.

    The legacy starburst used a fixed radius while the text used a fixed font
    size, so a long phrase overflowed the fill and the outline cut through the
    glyphs. Here the text ink is measured first: the star's inner radius is the
    ink circumradius plus a clear margin, and the outer radius keeps the approved
    visual ratio. The centre is clamped so the whole star stays inside the frame;
    a frame that cannot fit it raises instead of drawing broken text.
    """
    width, height = canvas
    font = _font("heavy", height * 0.058)
    ink = _ink(draw, cap["text"], font)
    margin = max(4.0, height * SFX_MARGIN)
    inner = math.hypot(ink[0] / 2, ink[1] / 2) + margin
    outer = inner * STAR_RATIO
    # Frame-edge margin: the star's centre clamp must keep the whole burst inside
    # the safe area, not merely clear of the text inset (the review found bursts
    # 23 px from the top edge because only the text inset was used here).
    edge = max(margin, height * SAFE_MARGIN)
    if 2 * (outer + edge) > min(width, height):
        raise ComposeError(
            f"sfx caption {cap.get('id')!r} cannot fit the star around {cap['text']!r} "
            f"inside a {width}x{height} frame"
        )
    centre = (
        min(max(width * float(cap["x"]), outer + edge), width - outer - edge),
        min(max(height * float(cap["y"]), outer + edge), height - outer - edge),
    )
    return {
        "centre": centre,
        "inner": inner,
        "outer": outer,
        "margin": margin,
        "font": font,
        "ink": ink,
    }


def caption_frame(
    cap: dict, palette: dict, local_t: float, seconds: float, canvas: tuple[int, int]
) -> Image.Image:
    """One frame of a caption or SFX burst, ``local_t`` seconds into its window."""
    width, height = canvas
    img = Image.new("RGBA", canvas, (0, 0, 0, 0))
    fade = min(MIN_CAPTION_GAP, seconds / 4)
    alpha = ramp(local_t, 0.0, fade) * (1 - ramp(local_t, seconds - fade, seconds))
    if alpha <= 0:
        return img
    draw = ImageDraw.Draw(img)
    if cap["style"] == "caption":
        pad = height * 0.014
        bar = width * 0.006
        x0, y1 = width * 0.085, height * 0.90
        max_w = width * (1 - SAFE_MARGIN) - x0 - bar - 2 * pad
        max_h = y1 - height * SAFE_MARGIN - 2 * pad
        font = _fit_font(draw, cap["text"], "bold", height * 0.032, max_w, max_h)
        ink_w, ink_h, ink_left, ink_top = _ink(draw, cap["text"], font)
        box_h = ink_h + 2 * pad
        y0 = y1 - box_h
        # Slightly more room on the trailing side: the trailing glyph's
        # sidebearing otherwise makes the bar look right-cramped.
        _scrim(
            draw,
            (x0, y0, x0 + bar + ink_w + pad * 2.25, y1),
            height * 0.008,
            210 * alpha,
            palette,
        )
        draw.rectangle((x0, y0, x0 + bar, y1), fill=(*palette["accent"], round(255 * alpha)))
        draw.text(
            (x0 + bar + pad - ink_left, y0 + (box_h - ink_h) / 2 - ink_top),
            cap["text"],
            font=font,
            fill=(*palette["ink"], round(255 * alpha)),
        )
    else:
        geometry = sfx_geometry(draw, cap, canvas)
        cx, cy = geometry["centre"]
        inner, outer = geometry["inner"], geometry["outer"]
        points = []
        for i in range(32):
            r = outer if i % 2 == 0 else inner
            angle = -math.pi / 2 + i * math.pi / 16
            points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
        draw.polygon(
            points,
            fill=(*palette["accent"], round(230 * alpha)),
            outline=(*palette["night"], round(255 * alpha)),
        )
        ink_w, ink_h, ink_left, ink_top = geometry["ink"]
        draw.text(
            (cx - ink_w / 2 - ink_left, cy - ink_h / 2 - ink_top),
            cap["text"],
            font=geometry["font"],
            fill=(*palette["night"], round(255 * alpha)),
        )
        rotation = float(cap.get("rotation", 0.0))
        if rotation:
            img = img.rotate(rotation, resample=Image.Resampling.BICUBIC, center=(cx, cy))
    return img


def credit_frame(
    card,
    palette: dict,
    local_t: float,
    seconds: float,
    canvas: tuple[int, int],
    spec: dict | None = None,
) -> Image.Image:
    """One frame of a closing credit card, ``local_t`` seconds into its window."""
    if spec is not None and resolve_design(spec) == DESIGN_JOINT:
        return _joint_credit_frame(card, spec, palette, local_t, seconds, canvas)
    width, height = canvas
    img = Image.new("RGBA", canvas, (0, 0, 0, 0))
    fade = 0.35
    alpha = ramp(local_t, 0.0, fade) * (1 - ramp(local_t, seconds - fade, seconds))
    if alpha <= 0:
        return img
    draw = ImageDraw.Draw(img)
    role, name = card
    x = width * 0.085
    yc = height * 0.70
    pad = height * 0.012
    # The scrim hugs the measured text instead of a fixed wide box: the review
    # found the old 0.52-width box holding ~370 px of text with a dead right half.
    max_w = width * (0.52 - 0.085) - width * SAFE_MARGIN
    role_y = yc - height * 0.045
    name_y = yc + height * 0.002
    role_font = _fit_font(draw, role, "bold", height * 0.023, max_w, height * 0.03)
    name_font = _fit_font(draw, name, "heavy", height * 0.052, max_w, height * 0.075)
    role_ink = _ink(draw, role, role_font)
    name_ink = _ink(draw, name, name_font)
    text_top = min(role_y + role_ink[3], name_y + name_ink[3])
    text_bottom = max(role_y + role_ink[3] + role_ink[1], name_y + name_ink[3] + name_ink[1])
    top = min(yc - height * 0.075, text_top - pad)
    bottom = max(yc + height * 0.075, text_bottom + pad)
    box_left = x - pad
    box_right = x + max(role_ink[0], name_ink[0]) + pad * 1.6
    if (
        top < height * SAFE_MARGIN
        or bottom > height * (1 - SAFE_MARGIN)
        or x + max(role_ink[0], name_ink[0]) > width * (1 - SAFE_MARGIN)
    ):
        raise ComposeError(f"credit card {role!r}/{name!r} cannot be fitted inside the frame")
    _scrim(draw, (box_left, top, box_right, bottom), height * 0.012, 150 * alpha, palette)
    draw.rectangle(
        (
            x,
            yc - height * 0.055,
            x + width * 0.045,
            yc - height * 0.055 + max(3, round(height * 0.0035)),
        ),
        fill=(*palette["accent"], round(255 * alpha)),
    )
    draw.text((x, role_y), role, font=role_font, fill=(*palette["accent"], round(235 * alpha)))
    draw.text((x, name_y), name, font=name_font, fill=(*palette["ink"], round(255 * alpha)))
    return img


def lockup_frame(
    spec: dict, palette: dict, local_t: float, seconds: float, canvas: tuple[int, int]
) -> Image.Image:
    """One frame of the closing lockup, ``local_t`` seconds into its window."""
    if resolve_design(spec) == DESIGN_JOINT:
        return _joint_lockup_frame(spec, palette, local_t, seconds, canvas)
    width, height = canvas
    img = Image.new("RGBA", canvas, (0, 0, 0, 0))
    fade = 0.5
    alpha = ramp(local_t, 0.0, fade) * (1 - ramp(local_t, seconds - fade, seconds))
    if alpha <= 0:
        return img
    draw = ImageDraw.Draw(img)
    _scrim(
        draw,
        (width * 0.205, height * 0.44, width * 0.795, height * 0.66),
        height * 0.02,
        165 * alpha,
        palette,
    )
    _draw_mark(
        img,
        draw,
        resolve_mark(spec),
        width / 2,
        height * 0.487,
        height * 0.034,
        height * 0.006,
        max(3, round(height * 0.004)),
        palette,
        alpha,
    )
    _centred(
        draw,
        canvas,
        height * 0.545,
        spec["credits"]["lockup"],
        _font("heavy", height * 0.036),
        palette["ink"],
        alpha,
    )
    _centred(
        draw,
        canvas,
        height * 0.60,
        spec["intro"]["names"],
        _font("demi", height * 0.022),
        palette["ink"],
        alpha * 0.8,
    )
    return img


# --------------------------------------------------------------------------- #
# overlay clips and the sparse alpha track
# --------------------------------------------------------------------------- #
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


def element_content(kind: str, spec: dict, part: dict) -> dict:
    validate_layout(spec)
    content = _element_content(kind, spec, part)
    # Omitted means byte-identical legacy cache content; no opt-in migration.
    if "layout" in spec:
        content["layout"] = spec["layout"]
        if kind == "card":
            content["compact_names"] = spec["intro"]["names"]
        if kind == "lockup":
            content["compact_title"] = spec["intro"].get("title")
    return content


def _element_content(kind: str, spec: dict, part: dict) -> dict:
    """The only spec data that can change one element's pixels or its timing.

    Unrelated spec fields (another caption, a credit card, the source identity)
    are excluded on purpose: editing one caption must not invalidate the intro,
    a card, the lockup or another caption.
    """
    if kind == "intro":
        # intro_frame reads intro_seconds, the design variant and every intro
        # field, mark included.
        return {
            "intro_seconds": float(spec["intro_seconds"]),
            "intro": spec["intro"],
            "design": resolve_design(spec),
        }
    if kind == "caption":
        # A caption's own data only; its id is identity, not a rendering input.
        cap = part["caption"]
        return {
            key: cap[key]
            for key in (
                "style",
                "text",
                "x",
                "y",
                "rotation",
                "start",
                "end",
                "start_frame",
                "end_frame",
                "shot_id",
            )
            if key in cap
        }
    if kind == "card":
        return {"card": [str(value) for value in part["card"]], "design": resolve_design(spec)}
    if kind == "identity":
        return {
            "design": resolve_design(spec),
            "names": spec["intro"]["names"],
            "tagline": spec["intro"].get("tagline"),
            "mark": resolve_mark(spec),
        }
    if kind == "lockup":
        return {
            "design": resolve_design(spec),
            "lockup": spec["credits"]["lockup"],
            "names": spec["intro"]["names"],
            "title": spec["intro"].get("title"),
            "mark": resolve_mark(spec),
        }
    raise ComposeError(f"unknown element kind {kind!r}")


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
    from .storage import write_json

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


def _load_storyboard(root: Path, project: dict) -> Storyboard:
    """Load ``work/storyboard.json`` for a spec that needs exact shot timing."""
    path = root / STORYBOARD_PATH
    if not path.is_file():
        raise ComposeError(f"shot-bound captions need a storyboard at {path}")
    try:
        board = Storyboard.model_validate(json.loads(path.read_text()))
    except (OSError, ValueError) as exc:
        raise ComposeError(f"invalid storyboard {path}: {exc}") from exc
    fps = int(project["fps"])
    expected = (fps, project["aspect"], math.ceil(float(project["duration"]) * fps))
    if (board.fps, board.aspect, board.total_frames) != expected:
        raise ComposeError("storyboard format/duration does not match the project")
    return board


def _selected_stills(root: Path, board: Storyboard | None) -> dict:
    """The recorded selected still per shot, from ``work/assets.json`` when present.

    This reports what the project index records for each shot (alias owner
    included). It deliberately does not re-hash the asset bytes, so a preflight
    label is metadata about the recorded selection, never a QC verdict.
    """
    if board is None:
        return {}
    path = root / "work" / "assets.json"
    if not path.is_file():
        return {}
    try:
        assets = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(assets, dict):
        return {}
    index = {}
    for shot in board.shots:
        owner = shot.asset_shot_id or shot.id
        entry = assets.get(owner)
        if not isinstance(entry, dict):
            continue
        chosen = next(
            (
                version
                for version in entry.get("versions", [])
                if isinstance(version, dict) and version.get("version") == entry.get("selected")
            ),
            None,
        )
        if chosen:
            index[shot.id] = {
                "shot_id": shot.id,
                "owner_shot_id": owner,
                "version": chosen.get("version"),
                "path": chosen.get("path"),
                "sha256": chosen.get("sha256"),
            }
    return index


# --------------------------------------------------------------------------- #
# input validation and assembly
# --------------------------------------------------------------------------- #
def _load_project(root: Path) -> dict:
    path = root / "project.json"
    if not path.is_file():
        raise ComposeError(f"project.json not found at {path}")
    return json.loads(path.read_text())


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
    intro_frames = max(1, round(float(spec["intro_seconds"]) * fps))
    total = math.ceil(duration * fps)
    credits_start = duration - float(spec["credits_tail_seconds"])
    lockup_seconds = float(spec["lockup_seconds"])
    credits_tail = float(spec["credits_tail_seconds"])
    parts = [{"kind": "intro", "id": "intro", "start": 0.0, "frames": intro_frames}]
    planned = list(captions) if captions is not None else list(spec["captions"])
    for cap in sorted(planned, key=lambda c: float(c["start"])):
        start, end = float(cap["start"]), float(cap["end"])
        if start < intro_frames / fps + MIN_CAPTION_GAP:
            raise ComposeError(f"caption {cap['id']} starts inside the intro window")
        if end > credits_start - MIN_CAPTION_GAP:
            raise ComposeError(f"caption {cap['id']} overlaps the credits window")
        parts.append(
            {
                "kind": "caption",
                "id": cap["id"],
                "caption": cap,
                "start": start,
                "frames": max(1, round((end - start) * fps)),
            }
        )
    cursor = credits_start
    cards = spec["credits"]["cards"]
    design = resolve_design(spec)
    # A joint-identity beat opens the closing package, so the partnership reads
    # as a signature rather than as one more name in a list. Its window is
    # capped so a short credit tail degrades to the plain card sequence.
    identity_span = 0.0
    if design == DESIGN_JOINT:
        identity_span = max(0.0, min(6.0, (credits_tail - lockup_seconds) / (len(cards) + 1)))
        if identity_span > 0:
            frames = max(1, round(identity_span * fps))
            parts.append({"kind": "identity", "id": "identity", "start": cursor, "frames": frames})
            cursor += frames / fps
    card_span = (credits_tail - lockup_seconds - identity_span) / len(cards)
    for index, card in enumerate(cards):
        frames = max(1, round(card_span * fps))
        parts.append(
            {
                "kind": "card",
                "id": f"card-{index + 1:02d}",
                "card": list(card),
                "start": cursor,
                "frames": frames,
            }
        )
        cursor += frames / fps
    lock_frames = max(1, total - round(cursor * fps))
    parts.append({"kind": "lockup", "id": "lockup", "start": cursor, "frames": lock_frames})
    parts.sort(key=lambda p: p["start"])
    for a, b in zip(parts, parts[1:], strict=False):
        if b["start"] < a["start"] + a["frames"] / fps - 1e-6:
            raise ComposeError(f"overlay window {b['id']} overlaps {a['id']}")
    if cursor + lock_frames / fps > duration + 2 / fps:
        raise ComposeError("credits extend past the end of the music")
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
        _load_storyboard(root, project)
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

    for part_index, part in enumerate(parts, 1):
        content = element_content(part["kind"], spec, part)
        if spec.get("renderer") == "remotion":
            from .remotion import overlay_clip

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
    track = _build_track(parts, directory, canvas, fps)
    output = _unique_output(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.stem}.partial{output.suffix}")
    temporary.unlink(missing_ok=True)
    try:
        operations.phase("compositing")
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
        os.link(temporary, output)
    finally:
        # Published or not, the partial hardlink is always removed.
        temporary.unlink(missing_ok=True)

    report = {
        "version": VERSION,
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


# --------------------------------------------------------------------------- #
# preflight: representative composited stills from real base frames
# --------------------------------------------------------------------------- #
def _slug(value: str) -> str:
    cleaned = "".join(char if char.isalnum() else "-" for char in value)
    return "-".join(part for part in cleaned.split("-") if part)[:48].lower() or "frame"


def _parse_times(text: str) -> list[float]:
    """Parse ``--times``: one or more comma-separated seconds."""
    parts = [part.strip() for part in text.split(",")]
    if not parts or any(not part for part in parts):
        raise ComposeError("--times needs one or more comma-separated seconds")
    try:
        return [float(part) for part in parts]
    except ValueError as exc:
        raise ComposeError(f"--times is not a list of seconds: {text!r}") from exc


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


def _locate_part(parts, fps: int, frame: int):
    """The planned overlay window that contains ``frame`` and its local seconds."""
    for part in parts:
        start = round(float(part["start"]) * fps)
        if start <= frame < start + part["frames"]:
            return part, (frame - start) / fps
    return None, None


def _preflight_samples(spec: dict, parts, fps: int, total: int, times) -> list[dict]:
    """Sample frames: requested times, or one per intro phase and overlay midpoint."""
    samples = []
    seen = set()
    if times is not None:
        for value in times:
            number = float(value)
            if not math.isfinite(number):
                raise ComposeError(f"preflight time {value!r} is not finite")
            if number < 0 or number >= total / fps:
                raise ComposeError(
                    f"preflight time {value!r}s is outside the film 0..{total / fps:.6f}s"
                )
            frame = frame_number(number, fps)
            if frame >= total:
                raise ComposeError(f"preflight time {value!r}s is past the last frame")
            if frame in seen:
                continue
            seen.add(frame)
            samples.append({"frame": frame, "phase": None, "requested_seconds": number})
        return samples
    for phase in intro_phase_samples(float(spec["intro_seconds"]), resolve_design(spec)):
        frame = frame_number(phase["sample_seconds"], fps)
        if frame in seen:
            continue
        seen.add(frame)
        samples.append({"frame": frame, "phase": phase["phase"], "requested_seconds": None})
    for part in parts:
        if part["kind"] == "intro":
            continue
        frame = round(float(part["start"]) * fps) + part["frames"] // 2
        if frame in seen:
            continue
        seen.add(frame)
        samples.append({"frame": frame, "phase": None, "requested_seconds": None})
    return samples


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
            board = _load_storyboard(root, project)
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
                from .remotion import overlay_clip, overlay_frame

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


__all__ = [
    "CACHE_SCHEMA",
    "ComposeError",
    "DEFAULT_PALETTE",
    "FACES",
    "IMPLEMENTATION_MODULES",
    "INTRO_PHASES",
    "INTRO_REFERENCE_SECONDS",
    "LEGACY_PALETTE",
    "MARKS",
    "PREFLIGHT_MAX_SAMPLES",
    "SAFE_MARGIN",
    "SFX_MARGIN",
    "STAR_RATIO",
    "VERSION",
    "caption_frame",
    "compose",
    "credit_frame",
    "element_content",
    "element_key",
    "implementation_revision",
    "intro_frame",
    "intro_phase_samples",
    "load_spec",
    "lockup_frame",
    "main",
    "preflight_frames",
    "resolve_font",
    "resolve_mark",
    "resolve_palette",
    "sfx_geometry",
]


if __name__ == "__main__":
    raise SystemExit(main())
