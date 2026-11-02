"""The labelled plate a preview shows for a shot whose still does not exist yet.

Only a preview may use one: a base or a final refuses a missing still.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .models import Shot

PREVIEW_BANNER = "PREVIEW / NOT FINAL"
PLACEHOLDER_BANNER = "PLACEHOLDER — NOT GENERATED"


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # pragma: no cover - very old Pillow without sized default
        return ImageFont.load_default()


def _text_height(font: ImageFont.ImageFont) -> int:
    box = font.getbbox("Ag")
    return max(1, box[3] - box[1])


def _wrap(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int
) -> list[str]:
    """Greedy word wrap that respects the rendered width of ``font``."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and draw.textlength(candidate, font=font) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    lines.append(current)
    return lines


def _mark_preview(image: Image.Image, headline: str, details: list[str]) -> None:
    """Draw the preview marking onto ``image`` in place.

    Only ever called with an in-memory copy of a source image, so approved
    stills on disk are never modified.
    """
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    margin = max(6, image.width // 64)
    headline_font = _font(max(12, image.width // 20))
    detail_font = _font(max(9, image.width // 34))
    wrapped: list[str] = []
    for text in details:
        wrapped.extend(_wrap(draw, text, detail_font, image.width - 2 * margin))
    line_height = _text_height(detail_font) + 6
    band = margin * 2 + _text_height(headline_font) + 6 + len(wrapped) * line_height
    draw.rectangle([0, 0, image.width, band], fill=(0, 0, 0, 205))
    draw.text((margin, margin), headline, font=headline_font, fill=(255, 214, 0, 255))
    y = margin + _text_height(headline_font) + 6
    for line in wrapped:
        draw.text((margin, y), line, font=detail_font, fill=(255, 255, 255, 255))
        y += line_height
    # A second marker near the bottom survives a crop that trims the top band.
    draw.text(
        (margin, image.height - _text_height(detail_font) - margin),
        headline,
        font=detail_font,
        fill=(255, 214, 0, 255),
    )
    image.paste(Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB"), (0, 0))


def _placeholder_plate(shot: Shot, size: tuple[int, int], destination: Path) -> None:
    """Clearly labelled stand-in for a shot whose still is not available yet."""
    image = Image.new("RGB", size, (26, 26, 34))
    camera = shot.camera
    if shot.camera_path is not None:
        path = shot.camera_path
        camera = f"camera_path {path.easing} zoom {path.start.zoom}->{path.end.zoom}"
    _mark_preview(
        image,
        PREVIEW_BANNER,
        [
            PLACEHOLDER_BANNER,
            f"shot: {shot.id}",
            f"purpose: {shot.purpose}",
            f"framing: {shot.framing or 'unspecified'}",
            f"camera: {camera}",
            "no approved still available for this shot",
        ],
    )
    image.save(destination)
