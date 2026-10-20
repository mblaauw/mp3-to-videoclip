"""Local low-resolution animatic preview of a storyboard.

A preview is a *review aid*, never a final export and never a paid asset. It
reuses the exact shot timeline, cameras/dissolves and the real local renderer,
but renders at a small review format (640x360 / 360x640) with the original full
audio. Every frame is conspicuously marked ``PREVIEW / NOT FINAL`` and every shot
without an available approved still is replaced by a labelled
``PLACEHOLDER — NOT GENERATED`` image that names the stable shot ID, purpose and
framing, so a repeated placeholder is never mistaken for generated work.

The whole function is local: it reads the project's own source audio and the
already-approved stills. It never uploads, never calls a provider, and never
requires an approval gate; the parent CLI owns the storyboard gate, the choice
of available proof stills and output versioning. Source images are only read —
the marked copies live in the caller's working directory, keyed by content.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .branding import load_brand, pack_hash
from .models import Project, RenderShot, Shot, Storyboard
from .render import render
from .storage import digest, file_hash, inside

# Bump to invalidate derived preview plates when the marking/placeholder changes.
PREVIEW_VERSION = "preview-v1"
PREVIEW_BANNER = "PREVIEW / NOT FINAL"
PLACEHOLDER_BANNER = "PLACEHOLDER — NOT GENERATED"

# Review formats only; the approved project dimensions are never rewritten.
PREVIEW_DIMENSIONS = {"16:9": (640, 360), "9:16": (360, 640)}

INPUTS_DIRNAME = "preview-inputs"


# --------------------------------------------------------------------------- #
# image marking helpers
# --------------------------------------------------------------------------- #
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


def _reusable(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        with Image.open(path) as image:
            image.verify()
        return True
    except (OSError, ValueError):
        return False


def _actual_plate(rs: RenderShot, destination: Path) -> None:
    """Marked copy of an available approved still; the source is only read."""
    with Image.open(rs.image) as opened:
        image = opened.convert("RGB")
    _mark_preview(
        image,
        PREVIEW_BANNER,
        [f"shot: {rs.shot.id}", f"available still: {Path(rs.image).name}"],
    )
    image.save(destination)


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


def _plate_key(kind: str, shot: Shot, size: tuple[int, int], image_sha256: str) -> str:
    return digest(
        {
            "preview_version": PREVIEW_VERSION,
            "kind": kind,
            "image_sha256": image_sha256,
            "shot": shot.id,
            "purpose": shot.purpose,
            "framing": shot.framing,
            "camera": shot.camera,
            "camera_path": shot.camera_path.model_dump() if shot.camera_path else None,
            "width": size[0],
            "height": size[1],
        }
    )[:32]


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def build_preview(
    root: Path,
    project: Project,
    board: Storyboard,
    available: list[RenderShot],
    output: Path,
    workdir: Path,
) -> dict:
    """Render a local, conspicuously marked preview of ``board``.

    ``available`` is the explicit set of shots with a current still (the parent
    CLI decides the scope: proof IDs for new creative work, everything for the
    legacy pilot). Every other storyboard shot becomes a labelled placeholder.
    Returns the normal renderer report plus preview metadata; it neither checks
    nor creates approvals and never touches a network or paid service.

    A ``root/brand.json`` package, when present, is loaded and rendered as the
    real brand plate at the review format, and its content hash is bound into
    ``input_hash`` so a brand change always invalidates an earlier review. A
    project without a brand package keeps the exact legacy report and hash.
    """
    root = Path(root)
    output = Path(output)
    workdir = Path(workdir)

    audio = inside(root, project.source)
    if not audio.is_file():
        raise FileNotFoundError(f"source audio not found: {audio}")
    board.check_project(project)

    # Opt-in identity: never generated, never approved and never a pre-roll.
    brand = load_brand(root)

    size = PREVIEW_DIMENSIONS[project.aspect]
    preview_project = project.model_copy(update={"width": size[0], "height": size[1]})

    by_id: dict[str, RenderShot] = {}
    for rs in available:
        if rs.shot.id in by_id:
            raise ValueError(f"duplicate available shot {rs.shot.id}")
        by_id[rs.shot.id] = rs

    shots_by_id = {shot.id: shot for shot in board.shots}
    for shot_id, rs in by_id.items():
        known = shots_by_id.get(shot_id)
        if known is None:
            raise ValueError(f"available shot {shot_id} is not part of the storyboard")
        if known != rs.shot:
            raise ValueError(f"available shot {shot_id} does not match the storyboard")
        if not Path(rs.image).is_file():
            raise FileNotFoundError(f"shot {shot_id}: missing available still {rs.image}")

    inputs = workdir / INPUTS_DIRNAME
    inputs.mkdir(parents=True, exist_ok=True)

    preview_shots: list[RenderShot] = []
    placeholder_ids: list[str] = []
    actual_ids: list[str] = []
    for shot in board.shots:
        rs = by_id.get(shot.id)
        if rs is None:
            key = _plate_key("placeholder", shot, size, "")
            plate = inputs / f"{key}.png"
            if not _reusable(plate):
                _placeholder_plate(shot, size, plate)
            placeholder_ids.append(shot.id)
        else:
            key = _plate_key("actual", shot, size, file_hash(Path(rs.image)))
            plate = inputs / f"{key}.png"
            if not _reusable(plate):
                _actual_plate(rs, plate)
            actual_ids.append(shot.id)
        preview_shots.append(RenderShot(shot=shot, image=str(plate)))

    report = render(
        preview_project,
        preview_shots,
        audio,
        output,
        workdir,
        preview_banner=True,
        preview_placeholders=tuple(placeholder_ids),
        brand=brand,
    )

    report["preview"] = True
    report["preview_version"] = PREVIEW_VERSION
    report["placeholder_shots"] = placeholder_ids
    report["actual_shots"] = actual_ids
    bound_inputs = {
        "storyboard": board.model_dump(),
        "available": [
            {"id": rs.shot.id, "image_sha256": file_hash(Path(rs.image))} for rs in available
        ],
    }
    if brand is not None:
        report["brand_hash"] = pack_hash(brand)
        # Changing the brand package (or the plate implementation) must stale
        # any earlier review of this exact input set.
        bound_inputs["brand_hash"] = report["brand_hash"]
    report["input_hash"] = digest(bound_inputs)
    report["approved_dimensions"] = {"width": project.width, "height": project.height}
    report["audio_path"] = str(audio)
    report["audio_sha256"] = file_hash(audio)
    return report


__all__ = [
    "PREVIEW_BANNER",
    "PREVIEW_DIMENSIONS",
    "PREVIEW_VERSION",
    "build_preview",
]
