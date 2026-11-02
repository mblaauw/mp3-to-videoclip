"""The package beside a final. Real FFmpeg on a small real MP4; a final is never rewritten."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from api_support import api_client
from test_first_cut import _film

from mp3_to_videoclip import delivery, edits
from mp3_to_videoclip.api import film as film_api
from mp3_to_videoclip.models import EditSection
from mp3_to_videoclip.storage import file_hash, write_json


def _final(root: Path, name="production-final-v001.mp4", seconds=4, kind="final") -> Path:
    film = root / "renders" / name
    film.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            shutil.which("ffmpeg"),
            "-nostdin",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=duration={seconds}:size=320x180:rate=24",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(film),
        ],  # fmt: skip
        check=True,
    )
    write_json(
        film.with_suffix(".json"),
        {
            "render_kind": kind,
            "verified": True,
            "output": str(film),
            "output_sha256": file_hash(film),
            "video": {"frames": seconds * 24},
        },
    )
    return film


@pytest.fixture
def film(tmp_path):
    root = _film(tmp_path)
    edit = edits.seed_edit(root)
    edits.save_edit(root, edit)
    return root


def test_chapters_start_at_zero_and_skip_ones_too_short_for_a_platform(film):
    edit = edits.load_edit(film)
    sections = [
        EditSection(id="a", start_frame=48, feel="Slow open. Then more."),
        EditSection(id="b", start_frame=96, feel="Too soon"),
        EditSection(id="c", start_frame=480, feel="The turn"),
    ]
    edits.save_edit(film, edit.model_copy(update={"sections": sections}))
    rows = delivery.chapter_list(film)
    assert [row["start_frame"] for row in rows] == [0, 480]
    assert rows[0]["title"] == "Slow open"
    assert delivery.chapters_text(rows, 24) == "00:00 Slow open\n00:20 The turn\n"


def test_ffmetadata_runs_to_the_end_and_escapes():
    text = delivery.ffmetadata(
        [{"start_frame": 0, "title": "A=B"}, {"start_frame": 240, "title": "C"}], 24, 480
    )
    assert text.startswith(";FFMETADATA1\n[CHAPTER]")
    assert "START=0\nEND=10000\ntitle=A\\=B\n" in text
    assert "START=10000\nEND=20000\ntitle=C\n" in text


def test_a_package_adds_files_and_never_touches_the_final(film):
    final = _final(film)
    before = file_hash(final)
    value = delivery.make_package(film, final)
    assert file_hash(final) == before
    assert value["final_sha256"] == before
    names = set(value["files"])
    assert any(name.endswith(".png") and ".poster-f" in name for name in names)
    assert any(name.endswith(".jpg") and ".poster-f" in name for name in names)
    assert "production-final-v001.contact.png" in names
    for name, sha in value["files"].items():
        assert file_hash(final.parent / name) == sha
    assert set(delivery.listing(final)) >= names


def test_a_chosen_frame_adds_a_poster_and_keeps_the_first(film):
    final = _final(film)
    first = delivery.make_package(film, final, frame=0)
    second = delivery.make_package(film, final, frame=24)
    assert first["poster_frame"] == 0 and second["poster_frame"] == 24
    assert (final.parent / "production-final-v001.poster-f000000.png").is_file()
    assert (final.parent / "production-final-v001.poster-f000024.png").is_file()
    assert delivery.newest_poster(film).endswith(".jpg")
    with pytest.raises(ValueError, match="not in this film"):
        delivery.make_package(film, final, frame=9999)


def test_only_a_verified_final_has_a_package(film):
    base = _final(film, "production-base-v001.mp4", kind="base")
    with pytest.raises(ValueError, match="only a final"):
        delivery.make_package(film, base)
    final = _final(film)
    final.write_bytes(final.read_bytes() + b"x")
    with pytest.raises(ValueError, match="not the final"):
        delivery.make_package(film, final)


def test_the_route_serves_only_package_files(film):
    final = _final(film)
    delivery.make_package(film, final, frame=0)
    client = api_client(film.parent)
    name = "production-final-v001.poster-f000000.jpg"
    assert client.get(f"/api/projects/{film.name}/film/package/{name}").status_code == 200
    bad = f"/api/projects/{film.name}/film/package/production-final-v001.json"
    assert client.get(bad).status_code == 404


def test_a_chapter_takes_the_name_of_a_section_a_frame_away(film, monkeypatch):
    from mp3_to_videoclip import song_map

    edit = edits.load_edit(film)
    sections = [
        EditSection(id="a", start_frame=0, feel="beat"),
        EditSection(id="b", start_frame=481, feel="beat"),
    ]
    edits.save_edit(film, edit.model_copy(update={"sections": sections}))
    monkeypatch.setattr(
        song_map,
        "song_map",
        lambda root: {
            "sections": [{"start_frame": 0, "name": "Hook"}, {"start_frame": 480, "name": "World"}]
        },
    )
    assert [row["title"] for row in delivery.chapter_list(film)] == ["Hook", "World"]


def test_the_studio_can_queue_a_package_and_a_version():
    """Both routes name their own render kinds; the runner once refused them before any work."""
    from mp3_to_videoclip.jobs.runner import RENDER_KINDS

    source = (Path(film_api.__file__)).read_text()
    named = set(re.findall(r'render_kind="([a-z]+)"', source))
    assert {"variant", "package"} <= named <= set(RENDER_KINDS)
