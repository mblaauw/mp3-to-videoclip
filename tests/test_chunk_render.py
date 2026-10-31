"""Shot chunks render, join, resume and repair, with real encoding and a fake renderer."""

import subprocess

import numpy as np
import pytest
from PIL import Image

from mp3_to_videoclip import framecheck, remotion, render
from mp3_to_videoclip.storage import read_json, write_json


def _picture(seed: int) -> np.ndarray:
    y, x = np.mgrid[0:54, 0:96].astype(np.float32)
    return np.clip(128 + 90 * np.sin(x / 13 + seed) * np.cos(y / 9 + seed), 0, 255)


def _frames(seed: int, count: int) -> np.ndarray:
    return np.stack([np.roll(_picture(seed), i // 4, axis=1) for i in range(count)])


def _tile(frame: np.ndarray) -> np.ndarray:
    return np.tile(frame[:18, :32], (3, 3))


def _shot(name, start, length, image=None):
    return {
        "id": name,
        "start_frame": start,
        "duration_frames": length,
        "image_sha256": image or name,
    }


def _film():
    return {"shots": [_shot("a", 0, 24), _shot("b", 24, 36), _shot("c", 60, 24)]}


def _encode(frames, path):
    process = subprocess.Popen(
        "ffmpeg -nostdin -v error -f rawvideo -pix_fmt gray -s 96x54 -r 24 -i - "
        f"-c:v libx264 -crf 12 -pix_fmt yuv420p '{path}'",
        shell=True,
        stdin=subprocess.PIPE,
    )
    process.communicate(frames.astype(np.uint8).tobytes())
    assert process.returncode == 0


class FakeRenderer:
    """Renders chunks from pictures, and can spoil named film frames."""

    def __init__(self, film):
        self.film = film
        self.rendered: list[list[int]] = []
        self.spoil: list[set[int]] = []
        self.fail_after = None
        self.reused: list[int] = []

    def _sound(self, frame):
        for offset, shot in enumerate(self.film["shots"]):
            if shot["start_frame"] <= frame < shot["start_frame"] + shot["duration_frames"]:
                seed = sum(map(ord, shot["image_sha256"])) % 7 + offset * 0
                return _frames(seed, shot["duration_frames"])[frame - shot["start_frame"]]
        raise AssertionError(frame)

    def __call__(
        self, kind, output, selected, canvas, fps, frames, inputs, chunks=None, chunks_reused=0
    ):
        if kind == "stills":
            output.mkdir()
            stills = []
            for frame in inputs["still_frames"]:
                name = f"f{frame:05d}.png"
                Image.fromarray(self._sound(frame).astype(np.uint8)).save(output / name)
                stills.append({"frame": frame, "file": name})
            return {"renderer_report": {"stills": stills}}
        spoiled = self.spoil.pop(0) if self.spoil else set()
        self.rendered.append([chunk["start"] for chunk in chunks])
        self.reused.append(chunks_reused)
        for done, chunk in enumerate(chunks):
            if self.fail_after == done:
                raise ValueError("the renderer died")
            start = chunk["start"]
            pictures = np.stack([self._sound(start + i) for i in range(chunk["frames"])])
            for frame in spoiled:
                if start <= frame < start + chunk["frames"]:
                    pictures[frame - start] = _tile(pictures[frame - start])
            _encode(pictures, chunk["output"])
        return {}


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setattr(remotion, "implementation_hash", lambda: "revision")
    film = _film()
    fake = FakeRenderer(film)
    monkeypatch.setattr(remotion, "invoke", fake)

    def run(name="silent", reuse=True):
        silent = tmp_path / f"{name}.mp4"
        remotion._render_silent("base", silent, None, (96, 54), 24, 84, film, reuse)
        return silent, read_json(silent.with_suffix(".frames.json"))

    return film, fake, run, tmp_path


def test_a_film_renders_shot_by_shot_and_joins_exactly(rig):
    film, fake, run, _ = rig
    silent, check = run()
    assert fake.rendered == [[0, 24, 60]]
    assert render._count_frames(silent) == 84
    assert check["broken"] == [] and check["scanned"] == 84 and check["reused"] == 0
    # Each frame of the joined movie is the right picture.
    frames = framecheck.small_frames(silent)
    for frame in (0, 23, 24, 59, 60, 83):
        assert not framecheck.disagrees(frames[frame], fake._sound(frame))


def test_only_a_changed_shot_renders_again(rig):
    film, fake, run, tmp = rig
    run("first")
    film["shots"][1]["image_sha256"] = "changed"
    untouched = sorted(p.stat().st_ino for p in (tmp / "remotion-chunks").glob("*.mp4"))
    silent, check = run("second")
    assert fake.rendered[1:] == [[24]]
    assert fake.reused == [0, 2]
    assert check["reused"] == 2 and check["scanned"] == 36
    assert set(untouched) <= {p.stat().st_ino for p in (tmp / "remotion-chunks").glob("*.mp4")}
    frames = framecheck.small_frames(silent)
    assert not framecheck.disagrees(frames[30], fake._sound(30))
    assert not framecheck.disagrees(frames[70], fake._sound(70))


def test_an_interrupted_render_resumes(rig):
    film, fake, run, tmp = rig
    fake.fail_after = 2
    with pytest.raises(ValueError, match="died"):
        run()
    assert len(list((tmp / "remotion-chunks").glob("*.mp4"))) == 2
    assert not list((tmp / "remotion-chunks").glob("*.chunk.json"))
    fake.fail_after = None
    silent, check = run()
    # The two finished chunks were checked and kept; only the third rendered.
    assert fake.rendered[1:] == [[60]]
    assert check["scanned"] == 84
    assert render._count_frames(silent) == 84


def test_a_broken_frame_is_rendered_again_and_kept_to_inspect(rig):
    film, fake, run, tmp = rig
    fake.spoil = [{30}]
    silent, check = run()
    assert fake.rendered == [[0, 24, 60], [24]]
    assert check["broken"] == [30]
    assert len(list((tmp / "remotion-chunks").glob("*.broken-*.mp4"))) == 1
    frames = framecheck.small_frames(silent)
    assert framecheck.suspects(frames) == []


def test_a_broken_frame_that_returns_fails_and_names_it(rig):
    film, fake, run, tmp = rig
    fake.spoil = [{30}, {30}]
    with pytest.raises(ValueError, match=r"broken frames at \[30\]"):
        run()
    assert not (tmp / "silent.mp4").exists()


def test_a_final_never_reuses_and_leaves_nothing_behind(rig):
    film, fake, run, tmp = rig
    run("working")
    silent, check = run("final", reuse=False)
    assert fake.rendered[1:] == [[0, 24, 60]]
    assert check["reused"] == 0
    assert render._count_frames(silent) == 84
    assert not list((tmp / "remotion-chunks").glob("fresh-*"))


def test_a_damaged_chunk_fails_closed(rig):
    film, fake, run, tmp = rig
    run("first")
    chunk = next((tmp / "remotion-chunks").glob("*.mp4"))
    chunk.chmod(0o644)
    chunk.write_bytes(b"damaged")
    with pytest.raises(ValueError, match="chunk cache corruption"):
        run("second")
    assert chunk.read_bytes() == b"damaged"


def test_a_receipt_for_another_key_fails_closed(rig):
    film, fake, run, tmp = rig
    run("first")
    receipt = next((tmp / "remotion-chunks").glob("*.chunk.json"))
    write_json(receipt, {**read_json(receipt), "key": "another"})
    with pytest.raises(ValueError, match="chunk cache corruption"):
        run("second")


def test_identical_shots_share_one_chunk(rig):
    film, fake, run, tmp = rig
    film["shots"][:] = [
        _shot("a", 0, 24),
        _shot("b", 24, 24, image="same"),
        _shot("c", 48, 36),
    ]
    silent, _ = run()
    assert render._count_frames(silent) == 84


def test_uneven_timing_refuses_the_join(tmp_path):
    _encode(_frames(1, 24), tmp_path / "a.mp4")
    remotion._require_even_timing(tmp_path / "a.mp4", 24)
    with pytest.raises(ValueError, match="uneven timing"):
        remotion._require_even_timing(tmp_path / "a.mp4", 30)


def test_progress_says_how_many_shots_and_how_many_were_reused():
    assert remotion._shots_line({"phase": "bundling-assets"}) is None
    assert remotion._shots_line({"chunks_done": 3, "chunks_total": 38}) == "3 of 38 shots"
    line = remotion._shots_line({"chunks_done": 30, "chunks_total": 38, "chunks_reused": 26})
    assert line == "30 of 38 shots, 26 reused"
