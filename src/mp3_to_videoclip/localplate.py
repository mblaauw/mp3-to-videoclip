"""Deterministic local plates for cards, bridges, splits, logos and end cards.

These are ordinary PNG files the Player and the renderer consume. Nothing here
calls a provider, reserves budget or writes an approval. The file name is a
content key: shot definition, project size, source-image bytes (for splits) and
the plate renderer version. The same inputs always produce the same picture.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .branding import load_brand
from .models import Project, Shot
from .storage import digest, file_hash, inside

LOCAL_PLATE_VERSION = 1
PLATE_DIR = "work/local-plates"
FONT_DIR = Path(__file__).resolve().parent / "fonts"
FONT_FILES = {
    "regular": "Inter-Regular.ttf",
    "demi": "Inter-SemiBold.ttf",
    "bold": "Inter-Bold.ttf",
}
DEFAULT_BACKGROUND = "#101820"
DEFAULT_FOREGROUND = "#F4F1E8"
DEFAULT_ACCENT = "#D8FF3E"


def _font(face: str, size: float) -> ImageFont.FreeTypeFont:
    path = FONT_DIR / FONT_FILES.get(face, FONT_FILES["regular"])
    if not path.is_file():
        return ImageFont.load_default(size=max(8, int(size)))
    return ImageFont.truetype(str(path), max(8, int(size)))


def _rgba(value: str | None, fallback: str, alpha: int = 255):
    raw = (value or fallback).lstrip("#")
    try:
        return (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16), alpha)
    except (ValueError, IndexError):
        raw = fallback.lstrip("#")
        return (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16), alpha)


def _palette(root: Path):
    brand = load_brand(root)
    if brand is None:
        return (
            _rgba(DEFAULT_BACKGROUND, DEFAULT_BACKGROUND),
            _rgba(DEFAULT_FOREGROUND, DEFAULT_FOREGROUND),
            _rgba(DEFAULT_ACCENT, DEFAULT_ACCENT),
        )
    return (
        _rgba(brand.background, DEFAULT_BACKGROUND),
        _rgba(brand.foreground, DEFAULT_FOREGROUND),
        _rgba(brand.accent, DEFAULT_ACCENT),
    )


def _cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(image.convert("RGB"), size, Image.Resampling.LANCZOS)


def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> float:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: float) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if _text_width(draw, candidate, font) <= max_width or not current:
            current = candidate
            continue
        lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines


def _fitted(
    draw: ImageDraw.ImageDraw,
    values: list[str],
    *,
    face: str,
    nominal: float,
    max_width: float,
    max_height: float,
    leading: float = 1.18,
    minimum: float = 12,
):
    size = max(minimum, nominal)
    while size >= minimum:
        font = _font(face, size)
        lines = [line for value in values for line in _wrap(draw, value, font, max_width)]
        height = len(lines) * size * leading
        widest = max((_text_width(draw, line, font) for line in lines), default=0)
        if lines and height <= max_height and widest <= max_width:
            return font, lines, size * leading
        size *= 0.9
    font = _font(face, minimum)
    lines = [line for value in values for line in _wrap(draw, value, font, max_width)]
    return font, lines, minimum * leading


def _draw_lines(draw, lines, font, fill, x: float, y: float, advance: float):
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += advance
    return y


def _asset_image(root: Path, path: str | None) -> Image.Image | None:
    if not path:
        return None
    try:
        target = inside(root, path)
    except ValueError:
        return None
    if not target.is_file():
        return None
    try:
        with Image.open(target) as image:
            image.load()
            return image.convert("RGB")
    except OSError:
        return None


def _brand_logo(root: Path) -> Image.Image | None:
    for suffix in (".png", ".jpg", ".jpeg", ".webp"):
        path = root / "media" / "brand" / f"logo{suffix}"
        if path.is_file():
            return _asset_image(root, path.relative_to(root).as_posix())
    return None


def _dim(image: Image.Image, opacity: float = 0.64) -> Image.Image:
    veil = Image.new("RGBA", image.size, (0, 0, 0, int(255 * opacity)))
    base = image.convert("RGBA")
    base.alpha_composite(veil)
    return base.convert("RGB")


def _card(root: Path, project: Project, shot: Shot) -> Image.Image:
    size = (project.width, project.height)
    background, foreground, accent = _palette(root)
    source = _asset_image(root, shot.asset)
    if source is not None:
        image = _dim(_cover(source, size))
    else:
        image = Image.new("RGB", size, background[:3])
    draw = ImageDraw.Draw(image)
    base = min(size)
    margin = int(base * 0.085)
    values = shot.text or [shot.message]
    font, lines, advance = _fitted(
        draw,
        values,
        face="demi",
        nominal=base * (0.115 if len(values) <= 2 else 0.082),
        max_width=size[0] - 2 * margin,
        max_height=size[1] - 2 * margin - base * 0.12,
    )
    bar_w = max(44, int(base * 0.085))
    bar_h = max(6, int(base * 0.008))
    draw.rectangle([margin, margin, margin + bar_w, margin + bar_h], fill=accent)
    _draw_lines(draw, lines, font, foreground, margin, margin + base * 0.07, advance)
    brand = load_brand(root)
    if brand is not None and brand.name:
        footer_font = _font("regular", base * 0.028)
        draw.text(
            (margin, size[1] - margin - base * 0.03),
            brand.name,
            font=footer_font,
            fill=(*foreground[:3], 210),
        )
    return image


def _bridge(root: Path, project: Project, shot: Shot) -> Image.Image:
    size = (project.width, project.height)
    background, foreground, accent = _palette(root)
    image = Image.new("RGB", size, background[:3])
    draw = ImageDraw.Draw(image)
    base = min(size)
    margin = int(base * 0.09)
    values = shot.text or [shot.message]
    font, lines, advance = _fitted(
        draw,
        values,
        face="demi",
        nominal=base * 0.1,
        max_width=size[0] - 2 * margin,
        max_height=size[1] * 0.6,
    )
    block_h = len(lines) * advance
    y = (size[1] - block_h) / 2
    for line in lines:
        width = _text_width(draw, line, font)
        draw.text(((size[0] - width) / 2, y), line, font=font, fill=foreground)
        y += advance
    rule_w = max(48, int(base * 0.08))
    rule_y = int(size[1] / 2 + block_h / 2 + base * 0.035)
    draw.rectangle(
        [
            (size[0] - rule_w) // 2,
            rule_y,
            (size[0] + rule_w) // 2,
            rule_y + max(5, int(base * 0.006)),
        ],
        fill=accent,
    )
    return image


def _logo(root: Path, project: Project, shot: Shot) -> Image.Image:
    size = (project.width, project.height)
    background, foreground, accent = _palette(root)
    image = Image.new("RGB", size, background[:3])
    draw = ImageDraw.Draw(image)
    base = min(size)
    margin = int(base * 0.09)
    values = shot.text or ([shot.message] if shot.message else [])
    brand = load_brand(root)
    wordmark = values[0] if values else (brand.name if brand is not None else "")
    support = values[1:] if values else []
    logo = _asset_image(root, shot.asset) or _brand_logo(root)
    top = size[1] * 0.32
    if logo is not None:
        target_h = int(base * 0.22)
        fitted = _cover(logo, (int(target_h * logo.width / max(1, logo.height)), target_h))
        image.paste(fitted, ((size[0] - fitted.width) // 2, int(top)))
        top += target_h + base * 0.05
    if wordmark:
        font, lines, advance = _fitted(
            draw,
            [wordmark],
            face="bold",
            nominal=base * 0.12,
            max_width=size[0] - 2 * margin,
            max_height=base * 0.22,
        )
        for line in lines:
            width = _text_width(draw, line, font)
            draw.text(((size[0] - width) / 2, top), line, font=font, fill=foreground)
            top += advance
    if support:
        font, lines, advance = _fitted(
            draw,
            support,
            face="regular",
            nominal=base * 0.042,
            max_width=size[0] - 2 * margin,
            max_height=base * 0.18,
        )
        top += base * 0.02
        for line in lines:
            width = _text_width(draw, line, font)
            draw.text(((size[0] - width) / 2, top), line, font=font, fill=foreground)
            top += advance
    rule_w = max(50, int(base * 0.11))
    rule_y = int(top + base * 0.04)
    draw.rectangle(
        [
            (size[0] - rule_w) // 2,
            rule_y,
            (size[0] + rule_w) // 2,
            rule_y + max(6, int(base * 0.007)),
        ],
        fill=accent,
    )
    return image


def _end_card(root: Path, project: Project, shot: Shot) -> Image.Image:
    size = (project.width, project.height)
    background, foreground, accent = _palette(root)
    image = Image.new("RGB", size, background[:3])
    draw = ImageDraw.Draw(image)
    base = min(size)
    margin = int(base * 0.09)
    values = shot.text or [shot.message]
    headline = values[:1]
    support = values[1:]
    logo = _asset_image(root, shot.asset) or _brand_logo(root)
    start_y = size[1] * 0.27
    if logo is not None:
        target_h = int(base * 0.11)
        fitted = _cover(logo, (int(target_h * logo.width / max(1, logo.height)), target_h))
        image.paste(fitted, (margin, int(start_y)))
        start_y += target_h + base * 0.025
    font, lines, advance = _fitted(
        draw,
        headline,
        face="bold",
        nominal=base * 0.1,
        max_width=size[0] - 2 * margin,
        max_height=base * 0.24,
    )
    y = start_y
    for line in lines:
        draw.text((margin, y), line, font=font, fill=foreground)
        y += advance
    rule_y = int(y + base * 0.035)
    draw.rectangle(
        [margin, rule_y, margin + max(56, int(base * 0.1)), rule_y + max(6, int(base * 0.007))],
        fill=accent,
    )
    y = rule_y + base * 0.075
    if support:
        font, lines, advance = _fitted(
            draw,
            support,
            face="demi",
            nominal=base * 0.052,
            max_width=size[0] - 2 * margin,
            max_height=size[1] * 0.38,
        )
        y = _draw_lines(draw, lines, font, foreground, margin, y, advance)
    brand = load_brand(root)
    if brand is not None and brand.name:
        footer_font = _font("regular", base * 0.026)
        draw.text(
            (margin, size[1] - margin - base * 0.026),
            brand.name,
            font=footer_font,
            fill=(*foreground[:3], 210),
        )
    return image


def _pane_crop(image: Image.Image, crop, size: tuple[int, int]) -> Image.Image:
    width, height = image.size
    zoom = max(1.0, min(2.0, float(crop.zoom)))
    crop_w, crop_h = width / zoom, height / zoom
    centre_x, centre_y = width * crop.x, height * crop.y
    left = max(0, min(width - crop_w, centre_x - crop_w / 2))
    top = max(0, min(height - crop_h, centre_y - crop_h / 2))
    region = image.convert("RGB").crop(
        (round(left), round(top), round(left + crop_w), round(top + crop_h))
    )
    return ImageOps.fit(region, size, Image.Resampling.LANCZOS)


def _split(root: Path, project: Project, shot: Shot, sources: dict[str, Path]) -> Image.Image:
    size = (project.width, project.height)
    background, _, _ = _palette(root)
    image = Image.new("RGB", size, background[:3])
    gap = max(2, int(min(size) * 0.006))
    count = len(shot.panes)
    if count == 2:
        widths = [(size[0] - gap) // 2, size[0] - gap - (size[0] - gap) // 2]
        boxes = [(0, widths[0]), (widths[0] + gap, size[0])]
    else:
        third = (size[0] - 2 * gap) // 3
        boxes = [
            (0, third),
            (third + gap, 2 * third + gap),
            (2 * third + 2 * gap, size[0]),
        ]
    for pane, (left, right) in zip(shot.panes, boxes, strict=False):
        source = sources.get(pane.shot_id)
        if source is None:
            continue
        with Image.open(source) as opened:
            opened.load()
            pane_image = _pane_crop(opened, pane.crop, (right - left, size[1]))
        image.paste(pane_image, (left, 0))
    return image


def _compose(
    root: Path,
    project: Project,
    shot: Shot,
    *,
    asset: Path | None,
    sources: dict[str, Path],
) -> Image.Image:
    if shot.kind == "split":
        return _split(root, project, shot, sources)
    if shot.kind in ("upload", "product") and asset is not None:
        with Image.open(asset) as opened:
            opened.load()
            return _cover(opened, (project.width, project.height))
    if shot.kind == "card":
        return _card(root, project, shot)
    if shot.kind == "bridge":
        return _bridge(root, project, shot)
    if shot.kind == "logo":
        return _logo(root, project, shot)
    if shot.kind == "end_card":
        return _end_card(root, project, shot)
    raise ValueError(f"{shot.kind} is not rendered as a local plate")


def render(
    root: Path,
    project: Project,
    shot: Shot,
    *,
    asset: Path | None = None,
    sources: dict[str, Path] | None = None,
) -> Path:
    """Return the deterministic plate for ``shot``, rendering it if absent."""
    sources = sources or {}
    payload = {
        "version": LOCAL_PLATE_VERSION,
        "shot": shot.model_dump(),
        "width": project.width,
        "height": project.height,
        "sources": {key: file_hash(path) for key, path in sorted(sources.items())},
        "asset": file_hash(asset) if asset is not None else None,
    }
    key = digest(payload)[:24]
    directory = root / PLATE_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{shot.id}-{key}.png"
    if path.is_file():
        try:
            with Image.open(path) as existing:
                existing.verify()
            return path
        except OSError:
            pass
    image = _compose(root, project, shot, asset=asset, sources=sources)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=directory)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            image.save(handle, format="PNG")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path
