"""Package the approved SVG identity; local rendering only, no production edits."""

import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "brand/logo-design"
DEST = ROOT / "brand/releases/mh-vj-v1"
NS = "{http://www.w3.org/2000/svg}"


def publish(path, data):
    if path.exists() and path.read_bytes() != data:
        raise ValueError(f"refusing to replace a different release asset: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def main():
    entries = []
    for form, source in (("logo", "ligature"), ("badge", "seal")):
        for variant, suffix in (
            ("dark", "bare"),
            ("light", "on-light"),
            ("white", "mono-dark"),
            ("black", "mono-light"),
        ):
            master = SOURCE / f"{source}-{suffix}.svg"
            tree = ET.fromstring(master.read_bytes())
            # Remove only the full-canvas field, never a stem or badge element.
            for child in list(tree):
                if (
                    child.tag == NS + "rect"
                    and child.get("width") == child.get("height") == "120.0"
                ):
                    tree.remove(child)
            data = ET.tostring(tree, encoding="utf-8", xml_declaration=True)
            svg = DEST / f"svg/{form}-{variant}.svg"
            publish(svg, data)
            entries.append(
                {"file": str(svg.relative_to(DEST)), "source": str(master.relative_to(ROOT))}
            )
            for size in (64, 256, 1024):
                png = DEST / f"png/{form}-{variant}-{size}.png"
                result = subprocess.run(
                    ["rsvg-convert", "-w", str(size), "-h", str(size), str(svg)],
                    capture_output=True,
                    check=True,
                )
                publish(png, result.stdout)
                with Image.open(png) as image:
                    assert image.size == (size, size) and image.mode == "RGBA"
                    assert image.getpixel((0, 0))[3] == 0
                    assert image.getchannel("A").getextrema() == (0, 255)
                entries.append(
                    {"file": str(png.relative_to(DEST)), "size": size, "transparent": True}
                )
    for entry in entries:
        entry["sha256"] = hashlib.sha256((DEST / entry["file"]).read_bytes()).hexdigest()
    publish(
        DEST / "manifest.json",
        (
            json.dumps(
                {
                    "identity": "MAHA KALA × VJDJ69",
                    "release": "mh-vj-v1",
                    "approval": "User: fantastic, keep this. love it.",
                    "canvas": "Original 120×120 design grid, padding preserved; not runtime-tight tile bounds.",
                    "assets": entries,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        ).encode(),
    )
    print(json.dumps({"directory": str(DEST), "assets": len(entries)}))


if __name__ == "__main__":
    main()
