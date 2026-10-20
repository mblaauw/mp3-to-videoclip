import io
import subprocess

import numpy as np
import pytest
from PIL import Image
from test_render import make_audio, make_project

from mp3_to_videoclip.branding import brand_hash, load_brand, render_brand_plate
from mp3_to_videoclip.models import BrandPackage, RenderShot, Shot, Storyboard
from mp3_to_videoclip.preview import build_preview
from mp3_to_videoclip.render import probe, render
from mp3_to_videoclip.storage import file_hash, write_json


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
def test_brand_intro_preserves_full_music_and_disappears_after_window(tmp_path, aspect):
    project = make_project(tmp_path, duration=6, aspect=aspect)
    audio = make_audio(tmp_path / "song.wav", 6)
    image = tmp_path / "still.png"
    Image.new("RGB", (project.width, project.height), (8, 8, 8)).save(image)
    source_hashes = file_hash(audio), file_hash(image)
    shot = Shot(
        id="s001",
        start_frame=0,
        duration_frames=144,
        purpose="Local test",
        image_prompt="Local test",
        camera="hold",
    )
    shots = [RenderShot(shot=shot, image=str(image))]
    brand = BrandPackage(id="test-brand", duration_seconds=5, title="THE SIGNAL")
    output = tmp_path / "branded.mp4"
    report = render(project, shots, audio, output, tmp_path / "work", brand=brand)
    assert report["video"]["frames"] == 144
    assert report["audio"]["duration"] >= 6 - 1 / 24
    assert len(probe(output)["streams"]) == 2
    assert report["brand"]["hash"]
    during = np.any(np.asarray(frame(output, 2)) > 100, axis=-1).sum()
    after = np.any(np.asarray(frame(output, 5.5)) > 100, axis=-1).sum()
    assert during > 20 and after == 0
    assert (file_hash(audio), file_hash(image)) == source_hashes
    with pytest.raises(FileExistsError):
        render(project, shots, audio, output, tmp_path / "work", brand=brand)
    plain = render(project, shots, audio, tmp_path / "plain.mp4", tmp_path / "work")
    assert "brand" not in plain and all(p["cached"] for p in plain["plates"])
    with pytest.raises(ValueError, match="does not fit"):
        render(
            project,
            shots,
            audio,
            tmp_path / "too-long.mp4",
            tmp_path / "work",
            brand=brand.model_copy(update={"duration_seconds": 8}),
        )


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


def test_brand_is_rendered_and_bound_in_real_preview(tmp_path):
    project = make_project(tmp_path, duration=6)
    project = project.model_copy(update={"source": "media/song.wav"})
    (tmp_path / "media").mkdir()
    make_audio(tmp_path / project.source, 6)
    board = Storyboard(
        aspect=project.aspect,
        fps=24,
        total_frames=144,
        shots=[
            Shot(
                id="s001",
                start_frame=0,
                duration_frames=144,
                purpose="Draft",
                image_prompt="Draft",
                camera="hold",
            )
        ],
    )
    assert load_brand(tmp_path) is None and brand_hash(tmp_path) is None
    brand = BrandPackage(id="test", title="THE SIGNAL", duration_seconds=5)
    write_json(tmp_path / "brand.json", brand.model_dump())
    first = build_preview(tmp_path, project, board, [], tmp_path / "first.mp4", tmp_path / "work")
    assert first["brand_hash"] == brand_hash(tmp_path) == first["brand"]["hash"]
    write_json(tmp_path / "brand.json", brand.model_copy(update={"mark": "cutline"}).model_dump())
    second = build_preview(tmp_path, project, board, [], tmp_path / "second.mp4", tmp_path / "work")
    assert (
        first["input_hash"] != second["input_hash"] and first["brand_hash"] != second["brand_hash"]
    )
