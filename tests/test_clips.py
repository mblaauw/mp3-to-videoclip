"""A clip is a journaled asset beside its still. Every client here is a fake; the bytes are real."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from api_support import add_assets, make_api_project
from test_creative_production import approve_prerequisites, jpeg

from mp3_to_videoclip import budget, clips, edits, remotion
from mp3_to_videoclip import generation as G
from mp3_to_videoclip import production as P
from mp3_to_videoclip.providers import ProviderError, RunwareClient
from mp3_to_videoclip.storage import file_hash, read_json, write_json


def schema(task="videoInference", status="live"):
    return {
        "info": {"x-status": status, "x-air-id": "klingai:6@0", "x-pricing": {"rates": []}},
        "components": {
            "schemas": {
                "RequestBody": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["taskType", "taskUUID", "model", "positivePrompt"],
                        "additionalProperties": False,
                        "properties": {
                            "taskType": {"const": task},
                            "taskUUID": {"type": "string"},
                            "model": {"const": "klingai:6@0"},
                            "positivePrompt": {"type": "string"},
                            "duration": {"enum": [5, 10]},
                            "outputType": {"enum": ["URL"]},
                            "outputFormat": {"enum": ["MP4"]},
                            "deliveryMethod": {"type": "string"},
                            "includeCost": {"type": "boolean"},
                            "inputs": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {"frameImages": {"type": "array"}},
                            },
                        },
                    },
                }
            }
        },
    }


def make_clip(path: Path, seconds=2, fps=24, codec="libx264") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
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
            f"testsrc=duration={seconds}:size=320x180:rate={fps}",
            "-c:v",
            codec,
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],  # fmt: skip
        check=True,
    )
    return path


class FakeClient:
    def __init__(self, *, polls=0, seconds=2):
        self.polls = polls
        self.seconds = seconds
        self.submitted = []
        self.asked = 0
        self.downloads = 0

    def schema(self, slug):
        return schema()

    def reference_image(self, path):
        return "data:image/jpeg;base64,AAAA"

    def _done(self, uuid):
        return {"taskUUID": uuid, "videoURL": "https://x.test/a.mp4", "cost": 0.21}

    def submit_video(self, request):
        self.submitted.append(request)
        return {"taskUUID": request["taskUUID"]}

    def recover_video(self, uuid):
        self.asked += 1
        return self._done(uuid) if self.asked > self.polls else None

    def download_video(self, url, path):
        self.downloads += 1
        make_clip(Path(path), seconds=self.seconds)

    def close(self):
        pass


@pytest.fixture
def film(tmp_path):
    root = make_api_project(tmp_path)
    add_assets(root, versions=2)
    write_json(root / "work/tasks.json", {})
    budget.set_budget(root, "5.00", "test budget")
    approve_prerequisites(root)
    P.approve(root, "storyboard", "test user approved shots")
    return root


def _quote(root, client=None):
    return clips.quote_clips(
        root, ["s001"], model="kling", reserve_per_second="0.10", client=client or FakeClient()
    )


def _authorized(root):
    quote = _quote(root)
    G.authorize(
        root, quote["id"], quote["reserve_total_usd"], "owner", via="studio", review_confirmed=True
    )
    return quote


def _bought(root, **options):
    quote = _authorized(root)
    client = FakeClient(**options)
    result = clips.generate_clips(root, quote["id"], client=client, sleep=lambda _: None)
    assert result["done"] == ["s001"]
    return quote, client


def _other_still(root) -> int:
    """A different picture from the same prompt, as a redo gives."""
    assets = read_json(root / "work/assets.json")
    chosen = next(
        v for v in assets["s001"]["versions"] if v["version"] == assets["s001"]["selected"]
    )
    path = root / "assets/s001/v009-other.jpg"
    jpeg(path, colour=(1, 200, 9))
    P.record_asset(root, "s001", 9, path, chosen["input_hash"], "other-task")
    return 9


def test_a_quote_reserves_seconds_and_spends_nothing(film):
    quote = _quote(film)
    task = quote["tasks"][0]
    assert quote["kind"] == "clip"
    assert quote["reserve_total_usd"] == "0.50"
    assert task["request"]["duration"] == 5
    assert task["request"]["taskType"] == "videoInference"
    assert read_json(film / "work/tasks.json") == {}


def test_a_model_that_is_not_video_is_refused(film):
    class Wrong(FakeClient):
        def schema(self, slug):
            return schema(task="imageInference")

    with pytest.raises(ValueError, match="not a video model"):
        _quote(film, Wrong())


def test_a_clip_needs_a_chosen_model_and_a_still_of_its_own(film, monkeypatch):
    with pytest.raises(ValueError, match="choose shots"):
        clips.quote_clips(film, ["nope"], model="kling", client=FakeClient())
    from mp3_to_videoclip import config

    monkeypatch.setattr(config, "load_settings", lambda: config.Settings())
    with pytest.raises(ValueError, match="video model in Settings"):
        clips.quote_clips(film, ["s001"], client=FakeClient())


def test_nothing_is_bought_without_authorization(film):
    quote = _quote(film)
    client = FakeClient()
    with pytest.raises(ValueError):
        clips.generate_clips(film, quote["id"], client=client)
    assert client.submitted == []


def test_buying_journals_first_keeps_the_still_and_selects_nothing(film):
    still_before = read_json(film / "work/assets.json")["s001"]["selected"]
    _, client = _bought(film)
    assert client.submitted[0]["inputs"]["frameImages"][0].startswith("data:image/")
    entry = read_json(film / "work/assets.json")["s001"]
    assert entry["selected"] == still_before
    assert "clip" not in entry
    clip = entry["clips"][0]
    assert clip["media"] == "video"
    assert clip["frames"] == 48 and clip["fps"] == 24
    assert clip["path"].endswith(".mp4")
    task = read_json(film / "work/tasks.json")[clip["task_id"]]
    assert task["status"] == "ready" and task["cost_usd"] == "0.21"
    assert P.resolved_assets(film, ["s001"])[0].clip is None


def test_polling_gives_up_and_recovery_never_buys_again(film, monkeypatch):
    monkeypatch.setattr(clips, "POLL_LIMIT_SECONDS", 10.0)
    quote = _authorized(film)
    client = FakeClient(polls=100)
    result = clips.generate_clips(film, quote["id"], client=client, sleep=lambda _: None)
    assert result["pending"] == ["s001"]
    assert len(client.submitted) == 1
    uuid = quote["tasks"][0]["uuid"]
    assert read_json(film / "work/tasks.json")[uuid]["status"] == "submitted"
    with pytest.raises(ValueError, match="recover"):
        clips.generate_clips(film, quote["id"], client=client, sleep=lambda _: None)
    assert G.recover(film, uuid, FakeClient()) is True
    assert len(client.submitted) == 1
    assert read_json(film / "work/assets.json")["s001"]["clips"]


def test_a_clip_that_is_not_h264_keeps_its_cost_and_is_not_indexed(film):
    class Vp9(FakeClient):
        def download_video(self, url, path):
            make_clip(Path(path), codec="mpeg4")

    quote = _authorized(film)
    with pytest.raises(ValueError, match="H.264"):
        clips.generate_clips(film, quote["id"], client=Vp9(), sleep=lambda _: None)
    task = read_json(film / "work/tasks.json")[quote["tasks"][0]["uuid"]]
    assert task["status"] == "result" and task["cost_usd"] == "0.21"
    assert "clips" not in read_json(film / "work/assets.json")["s001"]


def test_a_changed_still_stops_the_purchase(film):
    quote = _authorized(film)
    P.select_asset(film, "s001", _other_still(film))
    client = FakeClient()
    with pytest.raises(ValueError, match="estimate again|changed"):
        clips.generate_clips(film, quote["id"], client=client, sleep=lambda _: None)
    assert client.submitted == []


def test_using_a_clip_moves_the_stills_hash_and_going_back_restores_it(film):
    from mp3_to_videoclip.production.approvals import stage_hash

    before = stage_hash(film, "stills")
    _bought(film)
    assert stage_hash(film, "stills") == before
    version = read_json(film / "work/assets.json")["s001"]["clips"][0]["version"]
    clips.select_clip(film, "s001", version)
    assert P.resolved_assets(film, ["s001"])[0].clip.frames == 48
    assert stage_hash(film, "stills") != before
    clips.select_clip(film, "s001", None)
    assert stage_hash(film, "stills") == before


def test_a_clip_of_another_still_is_never_played(film):
    _bought(film)
    assets = read_json(film / "work/assets.json")
    version = assets["s001"]["clips"][0]["version"]
    clips.select_clip(film, "s001", version)
    P.select_asset(film, "s001", _other_still(film))
    assert P.resolved_assets(film, ["s001"])[0].clip is None
    with pytest.raises(ValueError, match="another still"):
        clips.select_clip(film, "s001", version)


def test_a_sharper_copy_is_the_same_picture_to_a_clip(film):
    entry = {
        "selected": 3,
        "clip": 4,
        "versions": [
            {"version": 1, "sha256": "a"},
            {"version": 3, "sha256": "b", "derived_from": {"version": 1, "sha256": "a"}},
        ],
        "clips": [{"version": 4, "still_root": "a"}],
    }
    assert P.selected_clip(entry)["version"] == 4


def test_compiled_entries_carry_the_clip_only_when_one_is_used(film, tmp_path):
    work = film / "work"
    assets_dir = tmp_path / "staged"
    assets_dir.mkdir()
    plain = remotion.compile_shots(P.resolved_assets(film, ["s001"]), work, assets_dir)
    assert "clip" not in plain[0]
    _bought(film)
    version = read_json(film / "work/assets.json")["s001"]["clips"][0]["version"]
    clips.select_clip(film, "s001", version)
    used = remotion.compile_shots(P.resolved_assets(film, ["s001"]), work, assets_dir)
    clip = used[0]["clip"]
    assert clip["file"] == f"{clip['sha256']}.mp4"
    assert {"frames": clip["frames"], "fps": clip["fps"]} == {"frames": 48, "fps": 24}
    assert file_hash(assets_dir / clip["file"]) == clip["sha256"]
    published = remotion.selected_asset_root(used, assets_dir)
    assert (published / clip["file"]).is_file()
    from mp3_to_videoclip.chunks import film_chunks

    project = P.load_project(film)
    args = ((project.width, project.height), project.fps, "revision")
    assert film_chunks({"shots": plain}, *args)[0].key != film_chunks({"shots": used}, *args)[0].key


def test_a_clip_much_shorter_than_its_shot_is_reported(film):
    _bought(film)
    version = read_json(film / "work/assets.json")["s001"]["clips"][0]["version"]
    clips.select_clip(film, "s001", version)
    edit = edits.seed_edit(film)
    edits.save_edit(film, edit)
    report = edits.report(film)
    length = (
        next(s for s in edit.shots if s.shot_id == "s001").duration_frames
        / P.load_project(film).fps
    )
    found = [w for w in report["warnings"] if w["code"] == "clip_short"]
    assert bool(found) == (length - 2.0 > 1.0)


def test_the_client_reads_a_video_result_and_refuses_a_bad_one():
    done = {"taskUUID": "u", "videoURL": "https://im.runware.ai/a.mp4", "cost": 0.21}
    assert RunwareClient._video_result(done, "u")["cost"] == 0.21
    assert RunwareClient._video_result({"status": "processing"}, "u") is None
    assert RunwareClient._video_result({"taskUUID": "u"}, "u") is None
    with pytest.raises(ProviderError):
        RunwareClient._video_result({**done, "cost": None}, "u")
    from mp3_to_videoclip.providers import _check_video

    with pytest.raises(ProviderError):
        _check_video(b"not a video at all")
    _check_video(b"\x00\x00\x00\x18ftypmp42")


def test_a_film_without_a_clip_keeps_its_exact_bytes(film):
    entry = read_json(film / "work/assets.json")["s001"]
    assert "clips" not in entry and "clip" not in entry
    assert "clip" not in P.resolved_assets(film, ["s001"])[0].model_dump(exclude_none=True)
