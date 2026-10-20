"""Generate the MAHA KALA x VJDJ69 identity as SVG masters.

Authored as geometry here and rendered with librsvg, so this is real vector art
rather than an imitation of it drawn with Pillow primitives. Nothing here touches
a production, uploads anything or spends.

Directions:

1. ``ligature`` the monogram: an M whose central V is the second identity, so one
   letterform carries two names.
2. ``seal``     the monogram badged in a container with one corner cut open, for
   small sizes and avatar duty.

``interlock`` (two chevrons woven through each other) was built and rejected: it
resolved as an X/butterfly, the crossing left a stray dark diamond, and it said
nothing about either name. It is not carried forward.

A brand has to work on both fields, so the palette is field-specific rather than
one set of colours: gold on night is legible, gold on cream is not. The light
field gets a deeper accent for real contrast.
"""

from __future__ import annotations

from pathlib import Path

INK = "#F4F1E8"
GOLD = "#D4AE6A"
NIGHT = "#0B1015"

PAPER = "#EFEAE0"
INK_ON_LIGHT = "#12181E"
GOLD_ON_LIGHT = "#9A6F28"

VIEW = 120.0
OUT = Path(__file__).resolve().parent


def _svg(body: str, *, background: str | None = None, size: int = 120) -> str:
    bg = f'<rect width="{VIEW}" height="{VIEW}" fill="{background}"/>' if background else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEW} {VIEW}" '
        f'width="{size}" height="{size}">{bg}{body}</svg>'
    )


def _poly(points, fill: str, opacity: float = 1.0) -> str:
    pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    alpha = "" if opacity >= 1 else f' fill-opacity="{opacity:.3f}"'
    return f'<polygon points="{pts}" fill="{fill}"{alpha}/>'


def _rect(x, y, w, h, fill, r=0.0) -> str:
    radius = f' rx="{r:.2f}"' if r else ""
    return f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" fill="{fill}"{radius}/>'


# --------------------------------------------------------------------------- #
# shared construction: the monogram
# --------------------------------------------------------------------------- #
STEM = 15.0
ARM = 15.0
TOP, BASE = 24.0, 96.0
# A pointed vertex overshoots the baseline: without it a sharp form reads short.
VERTEX = 102.0
NOTCH = 74.0
LEFT = 16.0
RIGHT = VIEW - 16.0


def monogram(*, ink: str, accent: str) -> str:
    """An M whose outer stems are ink and whose counter is a V in the accent.

    The chevron's outer edges run from the inner top corners down to the vertex,
    and its inner edges meet higher, so the arms taper and the joint is a true
    mitre rather than a blunt end. One stroke weight throughout: a logo that
    changes weight between its parts stops looking drawn and starts looking
    assembled.
    """
    left_stem = _rect(LEFT, TOP, STEM, BASE - TOP, ink)
    right_stem = _rect(RIGHT - STEM, TOP, STEM, BASE - TOP, ink)
    chevron = _poly(
        [
            (LEFT + STEM, TOP),
            (VIEW / 2, VERTEX),
            (RIGHT - STEM, TOP),
            (RIGHT - STEM - ARM, TOP),
            (VIEW / 2, NOTCH),
            (LEFT + STEM + ARM, TOP),
        ],
        accent,
    )
    return left_stem + right_stem + chevron


# --------------------------------------------------------------------------- #
# 1. ligature
# --------------------------------------------------------------------------- #
def ligature(*, ink: str, accent: str) -> str:
    return monogram(ink=ink, accent=accent)


# --------------------------------------------------------------------------- #
# 2. seal
# --------------------------------------------------------------------------- #
def seal(*, ink: str, accent: str, field: str) -> str:
    """The monogram badged, with one corner cut open.

    The clipped corner keeps the pipeline's open-frame motif without repeating it
    literally, and gives the badge a silhouette that survives an avatar crop.
    """
    r = 21.0
    stroke = 6.0
    cut = 25.0
    left, top, right, bottom = r, r, VIEW - r, VIEW - r
    outline = (
        f"M {left} {top} L {right - cut} {top} L {right} {top + cut} "
        f"L {right} {bottom - r} A {r} {r} 0 0 1 {right - r} {bottom} "
        f"L {left + r} {bottom} A {r} {r} 0 0 1 {left} {bottom - r} "
        f"L {left} {top + r} A {r} {r} 0 0 1 {left + r} {top} Z"
    )
    frame = (
        f'<path d="{outline}" fill="none" stroke="{ink}" stroke-width="{stroke}" '
        f'stroke-linejoin="miter"/>'
    )
    opening = (
        f'<path d="M {right - cut} {top} L {right} {top + cut}" fill="none" '
        f'stroke="{accent}" stroke-width="{stroke}"/>'
    )
    # Optically centred: the monogram carries its own overshoot, so it is nudged
    # up a touch rather than dropped in by pure arithmetic.
    scale = 0.54
    width = VIEW * scale
    offset_x = (VIEW - width) / 2
    offset_y = (VIEW - width) / 2 - 1.5
    inner = (
        f'<g transform="translate({offset_x:.2f},{offset_y:.2f}) scale({scale})">'
        f"{monogram(ink=ink, accent=accent)}</g>"
    )
    del field
    return frame + opening + inner


FULL = {
    "ligature": lambda: ligature(ink=INK, accent=GOLD),
    "seal": lambda: seal(ink=INK, accent=GOLD, field=NIGHT),
}
ON_LIGHT = {
    "ligature": lambda: ligature(ink=INK_ON_LIGHT, accent=GOLD_ON_LIGHT),
    "seal": lambda: seal(ink=INK_ON_LIGHT, accent=GOLD_ON_LIGHT, field=PAPER),
}
MONO_DARK = {
    "ligature": lambda: ligature(ink=INK, accent=INK),
    "seal": lambda: seal(ink=INK, accent=INK, field=NIGHT),
}
MONO_LIGHT = {
    "ligature": lambda: ligature(ink=INK_ON_LIGHT, accent=INK_ON_LIGHT),
    "seal": lambda: seal(ink=INK_ON_LIGHT, accent=INK_ON_LIGHT, field=PAPER),
}


def main() -> None:
    for name in FULL:
        (OUT / f"{name}-on-dark.svg").write_text(_svg(FULL[name](), background=NIGHT))
        (OUT / f"{name}-on-light.svg").write_text(_svg(ON_LIGHT[name](), background=PAPER))
        (OUT / f"{name}-mono-dark.svg").write_text(_svg(MONO_DARK[name]()))
        (OUT / f"{name}-mono-light.svg").write_text(_svg(MONO_LIGHT[name]()))
        (OUT / f"{name}-bare.svg").write_text(_svg(FULL[name]()))
    print("wrote:", ", ".join(sorted(FULL)))
    print("dark field  ink", INK, "accent", GOLD)
    print("light field ink", INK_ON_LIGHT, "accent", GOLD_ON_LIGHT)


if __name__ == "__main__":
    main()
