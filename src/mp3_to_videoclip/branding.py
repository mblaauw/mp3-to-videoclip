"""Local, opt-in brand plate for the opening seconds of a render.

A brand package is typeset and composited **locally** with Pillow from plain
shapes and the bundled basic font: no downloaded fonts, no generative model and
no producer name invented from a filename or a project slug. The plate is a
full-frame transparent RGBA PNG that the renderer overlays over the first
``duration_seconds`` of the already-approved video. It is never an approval,
never a pre-roll and never a new audio source: the source music and the render
timeline are untouched.

The package is content-bound: :func:`brand_hash` mixes the validated package
with :data:`BRAND_RENDER_VERSION`, so a brand change *or* a plate-rendering
revision invalidates any review/approval that recorded the old hash. Loading is
read-only and never mutates the project or creates an approval.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .models import BrandPackage, Project
from .storage import digest, read_json

BRAND_FILENAME = "brand.json"

# Bump when the plate layout, marks or text fitting change: it is mixed into
# ``brand_hash`` so stale review bindings can never reuse an older plate.
BRAND_RENDER_VERSION = "brand-plate-v2"

MARKS = ("open-frame", "cutline", "monogram", "joint", "filmstrip")


def filmstrip_svg(accent: str = "#D4AE6A") -> str:
    """Transparent gold filmstrip with negative monogram/perforations.

    Authored vector reconstruction of the selected reference, not extracted pixels
    or a black-background plate. The cutouts are genuinely transparent.
    """
    import re

    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", accent):
        raise ValueError("filmstrip ink must be a six-digit hex colour")
    holes = "".join(
        f'<rect x="{x}" y="{y}" width="9" height="8" rx="1" fill="black"/>'
        for y in (10, 72)
        for x in (16, 35, 54, 73, 92, 111, 130)
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 156 90">'
        '<defs><mask id="cut" maskUnits="userSpaceOnUse" x="0" y="0" width="156" height="90">'
        '<rect width="156" height="90" fill="white"/>'
        + holes
        + '<path d="M29 65V25H44L78 51L112 25H127V65H112V44L78 69L44 44V65Z" fill="black"/>'
        "</mask></defs>"
        f'<rect x="4" y="3" width="148" height="84" rx="6" fill="{accent}" mask="url(#cut)"/>'
        "</svg>"
    )


# --------------------------------------------------------------------------- #
# the collaboration monogram
# --------------------------------------------------------------------------- #
#: The mark is defined on this square grid, so its proportions and its stroke
#: weight scale together and the artwork is reproducible from numbers rather than
#: from a raster file. Values mirror ``brand/logo-design/generate.py`` exactly:
#: that file is the design source and this is the same geometry in code.
MONOGRAM_GRID = 120.0
MONOGRAM_LEFT = 16.0
MONOGRAM_RIGHT = 104.0
MONOGRAM_TOP = 24.0
MONOGRAM_BASE = 96.0
#: The chevron's vertex overshoots the baseline: a sharp point without overshoot
#: reads optically short beside flat-terminated stems.
MONOGRAM_VERTEX = 102.0
MONOGRAM_NOTCH = 74.0
#: One stroke weight throughout, chosen so the counters stay open at 18 px.
MONOGRAM_STEM = 15.0
MONOGRAM_ARM = 15.0
#: Pillow does not anti-alias polygons and this mark has long diagonals, so it is
#: drawn supersampled and reduced to get clean edges at every projected size.
MARK_SUPERSAMPLE = 4

# A restrained dark scrim keeps the typeset identity legible over any plate.
_SCRIM_ALPHA = 64


# --------------------------------------------------------------------------- #
# loading and identity
# --------------------------------------------------------------------------- #
def load_brand(root: Path) -> BrandPackage | None:
    """Return the validated ``root/brand.json`` package, or ``None`` if absent.

    The brand package is opt-in: a project without ``brand.json`` keeps the
    legacy brandless behaviour exactly. An unreadable or invalid package raises
    (``pydantic.ValidationError`` is a ``ValueError``) rather than being guessed
    at, and this function never writes, approves or mutates anything.
    """
    path = Path(root) / BRAND_FILENAME
    if not path.is_file():
        return None
    return BrandPackage.model_validate(read_json(path))


def pack_hash(brand: BrandPackage) -> str:
    """Content hash of a validated package plus the plate implementation version."""
    return digest({"brand": brand.model_dump(), "render_version": BRAND_RENDER_VERSION})


def brand_hash(root: Path) -> str | None:
    """Content hash bound to the review/approval chain, or ``None`` without a brand."""
    brand = load_brand(root)
    return None if brand is None else pack_hash(brand)


def brand_plate_key(brand: BrandPackage, width: int, height: int) -> str:
    """Deterministic cache key for the full-frame plate at ``width``x``height``."""
    return digest({"brand_hash": pack_hash(brand), "width": width, "height": height})[:32]


# --------------------------------------------------------------------------- #
# colour, font and text fitting helpers
# --------------------------------------------------------------------------- #
def _rgba(value: str, alpha: int = 255) -> tuple[int, int, int, int]:
    raw = value.lstrip("#")
    return (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16), alpha)


def _font(size: int) -> ImageFont.ImageFont:
    """Bundled basic font only; nothing is downloaded and nothing is embedded."""
    size = max(6, int(size))
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # pragma: no cover - Pillow without a sized default font
        return ImageFont.load_default()


def _ink_box(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont):
    return draw.textbbox((0, 0), text, font=font)


def _ink_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> float:
    box = _ink_box(draw, text, font)
    return box[2] - box[0]


def _line_advance(draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont) -> int:
    box = _ink_box(draw, "Ag", font)
    return max(1, round((box[3] - box[1]) * 1.35))


def _break_word(
    draw: ImageDraw.ImageDraw, word: str, font: ImageFont.ImageFont, max_width: float
) -> list[str]:
    """Split a single over-long word by characters so it can never overflow."""
    pieces: list[str] = []
    rest = word
    while rest and _ink_width(draw, rest, font) > max_width and len(rest) > 1:
        cut = len(rest)
        while cut > 1 and _ink_width(draw, rest[:cut], font) > max_width:
            cut -= 1
        pieces.append(rest[:cut])
        rest = rest[cut:]
    pieces.append(rest)
    return pieces


def fit_lines(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: float
) -> list[str]:
    """Greedy Unicode-aware wrap; every returned line fits inside ``max_width``.

    Explicit newlines are kept, over-long words are broken by character, and
    nothing is dropped or invented. Text is measured with the rendered font, so
    any alphabet the bundled basic font can draw is handled.
    """
    if max_width <= 0 or not text:
        return []
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if _ink_width(draw, candidate, font) <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = ""
            pieces = _break_word(draw, word, font, max_width)
            lines.extend(pieces[:-1])
            current = pieces[-1]
        lines.append(current)
    return lines


# --------------------------------------------------------------------------- #
# marks: local shapes only, never a generated image
# --------------------------------------------------------------------------- #
def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _draw_open_frame(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int],
    foreground: tuple[int, int, int, int],
    accent: tuple[int, int, int, int],
    stroke: int,
) -> None:
    """A rectangle whose top-right corner has been displaced outward."""
    x0, y0, size = box
    displaced = max(stroke, round(size * 0.14))
    fx0, fy0 = x0, y0 + displaced
    fx1, fy1 = x0 + size - displaced, y0 + size
    draw.line([fx0, fy0, fx0, fy1], fill=foreground, width=stroke)
    draw.line([fx0, fy1, fx1, fy1], fill=foreground, width=stroke)
    draw.line([fx0, fy0, _lerp(fx0, fx1, 0.55), fy0], fill=foreground, width=stroke)
    draw.line([fx1, fy1, fx1, _lerp(fy0, fy1, 0.55)], fill=foreground, width=stroke)
    shifted_x0 = _lerp(fx0, fx1, 0.70) + displaced
    draw.line([shifted_x0, y0, x0 + size, y0], fill=accent, width=stroke)
    draw.line([x0 + size, y0, x0 + size, _lerp(fy0, fy1, 0.40)], fill=accent, width=stroke)


def _draw_cutline(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int],
    foreground: tuple[int, int, int, int],
    accent: tuple[int, int, int, int],
    stroke: int,
) -> None:
    """A framed slash cut in two: a crisp editorial 'cut' mark."""
    x0, y0, size = box
    frame = max(1, round(stroke * 0.5))
    draw.rectangle(
        [x0 + frame, y0 + frame, x0 + size - frame, y0 + size - frame],
        outline=foreground,
        width=frame,
    )
    ax, ay = _lerp(x0, x0 + size, 0.24), _lerp(y0, y0 + size, 0.76)
    bx, by = _lerp(x0, x0 + size, 0.76), _lerp(y0, y0 + size, 0.24)
    for start, end in ((0.0, 0.40), (0.56, 1.0)):
        draw.line(
            [
                _lerp(ax, bx, start),
                _lerp(ay, by, start),
                _lerp(ax, bx, end),
                _lerp(ay, by, end),
            ],
            fill=accent,
            width=stroke,
        )


def collaboration_mark_layer(
    size: int,
    ink: tuple[int, int, int],
    accent: tuple[int, int, int],
    alpha: float = 1.0,
    supersample: int = MARK_SUPERSAMPLE,
) -> Image.Image:
    """The monogram as a square RGBA tile, anti-aliased, filling the tile width.

    One M whose outer stems are ink and whose counter is a V in the accent: two
    names carried by a single letterform. Ink bounds of the grid are mapped to the
    tile, so a caller asking for ``2 * half`` pixels of mark gets exactly that,
    and the renderer never depends on a raster file staying in step with the
    design.
    """
    size = max(2, int(round(size)))
    scale = max(0.0, min(1.0, float(alpha)))
    factor = max(1, int(supersample))
    big = size * factor
    tile = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tile)

    coverage = round(255 * scale)
    fill_ink = (*ink, coverage)
    fill_accent = (*accent, coverage)

    span_x = MONOGRAM_RIGHT - MONOGRAM_LEFT
    span_y = MONOGRAM_VERTEX - MONOGRAM_TOP
    k = big / max(span_x, span_y)
    pad_y = (big - span_y * k) / 2

    def X(value: float) -> float:
        return (value - MONOGRAM_LEFT) * k

    def Y(value: float) -> float:
        return pad_y + (value - MONOGRAM_TOP) * k

    stem, arm = MONOGRAM_STEM, MONOGRAM_ARM
    draw.rectangle(
        [X(MONOGRAM_LEFT), Y(MONOGRAM_TOP), X(MONOGRAM_LEFT + stem), Y(MONOGRAM_BASE)],
        fill=fill_ink,
    )
    draw.rectangle(
        [X(MONOGRAM_RIGHT - stem), Y(MONOGRAM_TOP), X(MONOGRAM_RIGHT), Y(MONOGRAM_BASE)],
        fill=fill_ink,
    )
    draw.polygon(
        [
            (X(MONOGRAM_LEFT + stem), Y(MONOGRAM_TOP)),
            (X(MONOGRAM_GRID / 2), Y(MONOGRAM_VERTEX)),
            (X(MONOGRAM_RIGHT - stem), Y(MONOGRAM_TOP)),
            (X(MONOGRAM_RIGHT - stem - arm), Y(MONOGRAM_TOP)),
            (X(MONOGRAM_GRID / 2), Y(MONOGRAM_NOTCH)),
            (X(MONOGRAM_LEFT + stem + arm), Y(MONOGRAM_TOP)),
        ],
        fill=fill_accent,
    )
    if factor > 1:
        tile = tile.resize((size, size), Image.LANCZOS)
    return tile


def paste_collaboration_mark(
    image: Image.Image,
    cx: float,
    cy: float,
    half: float,
    ink: tuple[int, int, int],
    accent: tuple[int, int, int],
    alpha: float = 1.0,
    supersample: int = MARK_SUPERSAMPLE,
) -> None:
    """Composite the monogram centred on ``(cx, cy)`` at ``2 * half`` pixels wide.

    Takes the image rather than a draw handle because the mark is rendered
    supersampled in its own layer and reduced, which a draw handle cannot express.
    Geometry then lives in exactly one place, so the brand plate and the film's
    intro, cards and lockup can never drift into two different emblems.
    """
    if alpha <= 0:
        return
    size = max(2, int(round(2 * half)))
    layer = collaboration_mark_layer(size, ink, accent, alpha, supersample)
    image.alpha_composite(layer, (int(round(cx - size / 2)), int(round(cy - size / 2))))


def _monogram_font(
    draw: ImageDraw.ImageDraw, text: str, max_width: float, max_height: float
) -> ImageFont.ImageFont:
    size = max(10, int(max_height))
    while size > 8:
        font = _font(size)
        box = _ink_box(draw, text, font)
        if (box[2] - box[0]) <= max_width and (box[3] - box[1]) <= max_height:
            return font
        size = int(size * 0.9)
    return _font(8)


def _draw_monogram(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int],
    letters: str,
    foreground: tuple[int, int, int, int],
    accent: tuple[int, int, int, int],
    stroke: int,
) -> None:
    """One to four approved characters, typeset from the bundled font."""
    x0, y0, size = box
    if not letters:
        return
    font = _monogram_font(draw, letters, size * 0.92, size * 0.62)
    left, top, right, bottom = _ink_box(draw, letters, font)
    width, height = right - left, bottom - top
    draw.text(
        (x0 + (size - width) / 2 - left, y0 + (size - height) / 2 - top),
        letters,
        font=font,
        fill=foreground,
    )
    rule = max(1, round(stroke * 0.5))
    half = min(max(rule, round(size * 0.30)), size // 2 - stroke)
    cx = x0 + size // 2
    ry = y0 + size - rule - max(1, round(size * 0.06))
    draw.line([cx - half, ry, cx + half, ry], fill=accent, width=rule)


_DRAW_MARKS = {
    "open-frame": _draw_open_frame,
    "cutline": _draw_cutline,
}

#: Marks drawn from a corner box rather than the monogram text path. The
#: collaboration mark is deliberately absent: it is composited as its own
#: supersampled layer, not stroked into the caller's draw handle.
_BOX_MARKS = ("open-frame", "cutline")
_BOX_MARKS_DRAW = {**_DRAW_MARKS}


def _draw_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    left: float,
    width: float,
    top: float,
    fill: tuple[int, int, int, int],
) -> None:
    box = _ink_box(draw, text, font)
    draw.text(
        (left + (width - (box[2] - box[0])) / 2 - box[0], top - box[1]), text, font=font, fill=fill
    )


# --------------------------------------------------------------------------- #
# public plate renderer
# --------------------------------------------------------------------------- #
def render_brand_plate(brand: BrandPackage, project: Project, output: Path) -> Path:
    """Write the full-frame transparent RGBA brand plate and return its path.

    The plate respects the package's safe margin on both 16:9 and 9:16 frames,
    fits/wraps the optional name and title inside that area and draws the mark
    from local shapes only. Nothing is fetched, generated or approved here; the
    same package, size and implementation version always produce the same PNG.
    """
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    width, height = project.width, project.height
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    margin_x = max(1, round(brand.safe_margin * width))
    margin_y = max(1, round(brand.safe_margin * height))
    safe_w = max(1, width - 2 * margin_x)
    safe_h = max(1, height - 2 * margin_y)
    base = min(safe_w, safe_h)

    foreground = _rgba(brand.foreground)
    accent = _rgba(brand.accent)
    name = brand.name.strip()
    title = brand.title.strip()

    scale = 1.0
    mark_size = 8
    stroke = 2
    pad = 2
    gap = 2
    name_font = _font(8)
    title_font = _font(8)
    name_lines: list[str] = []
    title_lines: list[str] = []
    name_advance = 0
    title_advance = 0
    # Shrink the whole block rather than dropping a single approved character.
    while True:
        mark_size = max(8, round(base * 0.30 * scale))
        stroke = max(2, round(mark_size * 0.09))
        pad = max(stroke, round(mark_size * 0.16))
        gap = max(2, round(base * 0.05 * scale))
        name_font = _font(max(6, round(base * 0.13 * scale)))
        title_font = _font(max(6, round(base * 0.095 * scale)))
        name_lines = fit_lines(draw, name, name_font, safe_w)
        title_lines = fit_lines(draw, title, title_font, safe_w)
        name_advance = _line_advance(draw, name_font) if name_lines else 0
        title_advance = _line_advance(draw, title_font) if title_lines else 0
        block_h = mark_size + 2 * pad
        if name_lines:
            block_h += gap + len(name_lines) * name_advance
        if title_lines:
            block_h += gap + len(title_lines) * title_advance
        if block_h <= safe_h or scale <= 0.25:
            break
        scale = round(scale - 0.05, 2)

    text_width = max([_ink_width(draw, line, name_font) for line in name_lines] or [0])
    text_width = max(
        text_width, max([_ink_width(draw, line, title_font) for line in title_lines] or [0])
    )
    block_w = min(safe_w, max(mark_size + 2 * pad, round(text_width)))

    left = round(margin_x + (safe_w - block_w) / 2)
    top = round(margin_y + (safe_h - block_h) / 2)

    scrim = max(2, round(base * 0.03))
    draw.rounded_rectangle(
        [
            max(margin_x, left - scrim),
            max(margin_y, top - scrim),
            min(width - 1 - margin_x, left + block_w + scrim),
            min(height - 1 - margin_y, top + block_h + scrim),
        ],
        radius=max(2, round(base * 0.04)),
        fill=(0, 0, 0, _SCRIM_ALPHA),
    )

    mark_left = round(left + (block_w - mark_size - 2 * pad) / 2 + pad)
    mark_top = round(top + pad)
    mark_box = (mark_left, mark_top, mark_size)
    if brand.mark == "monogram":
        _draw_monogram(
            draw, mark_box, brand.monogram.strip().upper()[:4], foreground, accent, stroke
        )
    elif brand.mark == "joint":
        paste_collaboration_mark(
            image,
            mark_left + mark_size / 2,
            mark_top + mark_size / 2,
            mark_size / 2,
            foreground[:3],
            accent[:3],
            alpha=foreground[3] / 255 if len(foreground) > 3 else 1.0,
        )
    else:
        _BOX_MARKS_DRAW[brand.mark](draw, mark_box, foreground, accent, stroke)

    cursor = top + mark_size + 2 * pad
    if name_lines:
        cursor += gap
        for line in name_lines:
            if line:
                _draw_centered(draw, line, name_font, left, block_w, cursor, foreground)
            cursor += name_advance
    if title_lines:
        cursor += gap
        for line in title_lines:
            if line:
                _draw_centered(draw, line, title_font, left, block_w, cursor, foreground)
            cursor += title_advance

    fd, tmp_name = tempfile.mkstemp(prefix=".brand-", suffix=".png", dir=output.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        image.save(tmp, format="PNG")
        os.replace(tmp, output)
    finally:
        tmp.unlink(missing_ok=True)
    return output


__all__ = [
    "BRAND_FILENAME",
    "BRAND_RENDER_VERSION",
    "MARKS",
    "brand_hash",
    "brand_plate_key",
    "collaboration_mark_layer",
    "fit_lines",
    "load_brand",
    "pack_hash",
    "paste_collaboration_mark",
    "render_brand_plate",
]
