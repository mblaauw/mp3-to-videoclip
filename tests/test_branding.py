import io
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from mp3_to_videoclip.branding import render_brand_plate
from mp3_to_videoclip.models import BrandPackage, Project
from mp3_to_videoclip.storage import file_hash

FPS = 24
SIZES = {"16:9": (192, 108), "9:16": (108, 192)}


def make_project(
    root: Path, *, duration: float, aspect: str = "16:9", slug: str = "demo"
) -> Project:
    width, height = SIZES[aspect]
    return Project(
        slug=slug,
        title="Demo",
        source_sha256="0" * 64,
        duration=duration,
        aspect=aspect,
        fps=FPS,
        width=width,
        height=height,
    )


def frame(path, at):
    output = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-ss",
            str(at),
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "png",
            "pipe:1",
        ],
        check=True,
        capture_output=True,
    ).stdout
    return Image.open(io.BytesIO(output)).convert("RGB")


@pytest.mark.parametrize("aspect", ["16:9", "9:16"])
@pytest.mark.parametrize("mark", ["open-frame", "cutline", "monogram"])
def test_local_brand_marks_are_deterministic_rgba_and_inside_safe_area(tmp_path, aspect, mark):
    project = make_project(tmp_path, duration=6, aspect=aspect)
    brand = BrandPackage(
        id="test", mark=mark, monogram="XX", name="Working Identity", title="THE SIGNAL"
    )
    path = render_brand_plate(brand, project, tmp_path / "mark.png")
    before = file_hash(path)
    render_brand_plate(brand, project, path)
    assert file_hash(path) == before
    with Image.open(path) as image:
        assert image.mode == "RGBA" and image.size == (project.width, project.height)
        alpha = image.getchannel("A")
        bounds = alpha.getbbox()
        mx, my = round(brand.safe_margin * project.width), round(brand.safe_margin * project.height)
        assert bounds and bounds[0] >= mx and bounds[1] >= my
        assert bounds[2] <= project.width - mx and bounds[3] <= project.height - my
