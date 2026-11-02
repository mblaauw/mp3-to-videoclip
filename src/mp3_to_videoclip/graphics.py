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

import hashlib
import json
import math
import subprocess
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import titles
from .branding import load_brand, paste_collaboration_mark
from .models import Storyboard
from .timeline import (
    frame_number,
)

VERSION = "graphics-v1"
#: Bumped whenever the overlay/track cache-key recipe changes incompatibly.
CACHE_SCHEMA = 2
#: Modules whose bytes can change a rendered element or its resolved timing.
#: ``branding.py`` owns the collaboration mark's geometry, which this module
#: draws, so its bytes change rendered pixels just as much as our own do.
IMPLEMENTATION_MODULES = ("graphics.py", "timeline.py", "titles.py", "branding.py")
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
DESIGN_JOINT = titles.DESIGN_JOINT
DESIGNS = (DESIGN_JOINT,)

MIN_CAPTION_GAP = titles.MIN_CAPTION_GAP
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
    short = spec.get("package") == "title-v1"
    if short:
        from .signature import check_short_titles

        try:
            check_short_titles(spec)
        except ValueError as exc:
            raise ComposeError(str(exc)) from exc
    else:
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
    if not short and (not spec["credits"].get("cards") or not spec["credits"].get("lockup")):
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


def _timing_board(root: Path, project: dict) -> Storyboard:
    """The storyboard with the edit's timing applied, as shot-bound captions see it."""
    board = _load_storyboard(root, project)
    try:
        return titles.timing_board(root, board)
    except (OSError, ValueError) as exc:
        raise ComposeError(f"invalid edit for caption timing: {exc}") from exc


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
    phases = (
        []
        if spec.get("package") == "title-v1"
        else intro_phase_samples(float(spec["intro_seconds"]), resolve_design(spec))
    )
    for phase in phases:
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
    "credit_frame",
    "element_content",
    "implementation_revision",
    "intro_frame",
    "intro_phase_samples",
    "load_spec",
    "lockup_frame",
    "resolve_font",
    "resolve_mark",
    "resolve_palette",
    "sfx_geometry",
]
