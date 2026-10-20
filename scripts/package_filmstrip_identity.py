"""Export the selected transparent filmstrip identity without touching v1."""

import json
import subprocess
from pathlib import Path

from PIL import Image

from mp3_to_videoclip.branding import filmstrip_svg
from mp3_to_videoclip.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "brand/releases/mh-vj-filmstrip-v2"


def publish(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != data:
        raise ValueError(f"refusing to replace released artwork: {path}")
    path.write_bytes(data)


def main():
    entries = []
    for name, colour in (
        ("gold", "#D4AE6A"),
        ("dark-gold", "#9A6F28"),
        ("white", "#F4F1E8"),
        ("black", "#12181E"),
    ):
        svg = DEST / f"filmstrip-{name}.svg"
        publish(svg, filmstrip_svg(colour).encode())
        entries.append(svg)
        for width in (156, 624, 2496):
            png = DEST / f"filmstrip-{name}-{width}.png"
            rendered = subprocess.run(
                ["rsvg-convert", "-w", str(width), str(svg)], check=True, capture_output=True
            ).stdout
            publish(png, rendered)
            with Image.open(png) as image:
                alpha = image.convert("RGBA").getchannel("A")
                assert alpha.getextrema() == (0, 255)
                assert alpha.getpixel((0, 0)) == 0
            entries.append(png)
    publish(
        DEST / "manifest.json",
        (
            json.dumps(
                {
                    "release": "mh-vj-filmstrip-v2",
                    "source": "src/mp3_to_videoclip/branding.py:filmstrip_svg",
                    "intent": "User-supplied preferred gold filmstrip/negative-monogram reference; black background excluded.",
                    "scope": "Authored vector reconstruction, not pixel-identical extraction; actual film proof remains reviewable.",
                    "wordmark": "MAHA KALA  ◆  VJDJ69",
                    "assets": [
                        {"path": str(p.relative_to(DEST)), "sha256": file_hash(p)} for p in entries
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        ).encode(),
    )
    print(DEST, len(entries), "transparent vector/raster assets")


if __name__ == "__main__":
    main()
