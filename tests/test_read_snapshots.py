"""Operation-local read savings without weakening content-bound approval checks."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from pathlib import Path
from threading import Barrier, Event

import pytest
from api_support import add_assets, api_client, make_api_project
from test_creative_production import jpeg

from mp3_to_videoclip import production as P
from mp3_to_videoclip.storage import (
    digest,
    file_hash,
    read_json,
    read_snapshot,
    snapshot_read,
    state_lock,
    state_mutation,
    write_json,
)


def test_snapshot_cleanup_and_private_values(tmp_path):
    path = tmp_path / "value.json"
    write_json(path, {"items": []})
    with pytest.raises(RuntimeError), read_snapshot(tmp_path):
        value = read_json(path)
        value["items"].append("not saved")
        assert read_json(path) == {"items": []}
        raise RuntimeError("abort")
    path.write_text('{"items": ["new"]}')
    assert read_json(path) == {"items": ["new"]}


def test_source_and_reference_changes_are_seen_between_operations(tmp_path):
    root = make_api_project(tmp_path)
    shot = P.load_board(root).shots[0]
    with read_snapshot(root):
        before = digest(P.image_spec(root, shot))
    ref = P.load_brief(root).creative.references[0]
    jpeg(root / ref.path, colour=(200, 10, 20))
    with read_snapshot(root):
        assert digest(P.image_spec(root, shot)) != before
    (root / "media/song.mp3").write_bytes(b"changed source")
    with read_snapshot(root), pytest.raises(ValueError, match="copied source changed"):
        P.image_spec(root, shot)


def test_cached_and_uncached_approval_hashes_match(tmp_path):
    root = make_api_project(tmp_path)
    add_assets(root)
    stages = ("analysis", "lyrics", "brief", "storyboard", "proof")
    expected = {stage: P.stage_hash(root, stage) for stage in stages}
    with read_snapshot(root):
        assert {stage: P.stage_hash(root, stage) for stage in stages} == expected
        board = P.load_board(root)
        board.shots[0].image_prompt = "not saved"
        assert P.load_board(root).shots[0].image_prompt != "not saved"


def test_writer_boundary_retires_cache_before_validation(tmp_path):
    path = tmp_path / "value.json"
    write_json(path, {"n": 1})

    @state_mutation
    def mutate(root):
        assert read_json(path) == {"n": 2}
        write_json(path, {"n": 3})

    with read_snapshot(tmp_path):
        assert read_json(path) == {"n": 1}
        path.write_text('{"n": 2}')
        mutate(tmp_path)
        assert read_json(path) == {"n": 3}
        write_json(path, {"n": 4})
        assert read_json(path) == {"n": 4}


def test_copied_context_does_not_share_thread_cache(tmp_path):
    path = tmp_path / "value.json"
    write_json(path, {"n": 1})
    with read_snapshot(tmp_path), ThreadPoolExecutor(max_workers=1) as pool:
        assert read_json(path) == {"n": 1}
        context = copy_context()
        path.write_text('{"n": 2}')
        assert pool.submit(context.run, read_json, path).result() == {"n": 2}
        assert read_json(path) == {"n": 1}


@pytest.mark.parametrize("exceptional", [False, True])
def test_copied_context_cannot_reuse_cache_after_scope_exit(tmp_path, exceptional):
    path = tmp_path / "value.json"
    write_json(path, {"n": 1})
    context = None
    try:
        with read_snapshot(tmp_path):
            assert read_json(path) == {"n": 1}
            context = copy_context()
            if exceptional:
                raise RuntimeError("abort")
    except RuntimeError:
        pass
    path.write_text('{"n": 2}')
    assert context.run(read_json, path) == {"n": 2}


def test_nested_root_writer_retires_parent_and_child(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    write_json(a / "value.json", {"n": 1})
    write_json(b / "value.json", {"n": 1})
    with read_snapshot(a):
        assert read_json(a / "value.json") == {"n": 1}
        with read_snapshot(b):
            assert read_json(b / "value.json") == {"n": 1}
            write_json(a / "value.json", {"n": 2})
            write_json(b / "value.json", {"n": 2})
            assert read_json(b / "value.json") == {"n": 2}
        assert read_json(a / "value.json") == {"n": 2}
    with read_snapshot(b), pytest.raises(RuntimeError, match="sorted path order"):
        with read_snapshot(a):
            pass


def test_concurrent_local_plate_publication_is_atomic(tmp_path, monkeypatch):
    import inspect

    from PIL import Image

    from mp3_to_videoclip import localplate
    from mp3_to_videoclip.api.images import get_plate

    assert not inspect.iscoroutinefunction(get_plate)
    root = make_api_project(tmp_path)
    project = P.load_project(root)
    shot = P.load_board(root).shots[0].model_copy(update={"kind": "card"})
    barrier = Barrier(2)

    def compose(*args, **kwargs):
        barrier.wait(timeout=2)
        return Image.new("RGB", (16, 16), (10, 20, 30))

    monkeypatch.setattr(localplate, "_compose", compose)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(localplate.render, root, project, shot) for _ in range(2)]
        paths = [future.result(timeout=3) for future in futures]
    assert paths[0] == paths[1]
    with Image.open(paths[0]) as image:
        image.verify()
    assert not list(paths[0].parent.glob("*.tmp"))


def test_state_writer_cannot_split_a_snapshot(tmp_path):
    path = tmp_path / "value.json"
    write_json(path, {"n": 1})
    started, finished = Event(), Event()

    def writer():
        started.set()
        with state_lock(tmp_path):
            write_json(path, {"n": 2})
        finished.set()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with read_snapshot(tmp_path):
            future = pool.submit(writer)
            assert started.wait(1)
            assert not finished.wait(0.02)
            assert read_json(path) == {"n": 1}
        future.result(timeout=2)
    assert read_json(path) == {"n": 2}


def test_approval_graph_failures_are_memoized_only_in_scope(tmp_path):
    calls = []

    @snapshot_read
    def fail(root, stage):
        calls.append(stage)
        raise ValueError("missing approval")

    with read_snapshot(tmp_path):
        for _ in range(3):
            with pytest.raises(ValueError, match="missing approval"):
                fail(tmp_path, "brief")
    assert calls == ["brief"]
    with pytest.raises(ValueError):
        fail(tmp_path, "brief")
    assert calls == ["brief", "brief"]


@pytest.mark.parametrize("shot_count", [4, 79])
def test_images_hash_and_copy_counts_scale_linearly(tmp_path, monkeypatch, shot_count):
    root = make_api_project(tmp_path)
    project = read_json(root / "project.json")
    project["duration"] = shot_count * 12 / project["fps"]
    write_json(root / "project.json", project)
    board = read_json(root / "work/storyboard.json")
    template = board["shots"][0]
    board["shots"] = [
        {**template, "id": f"s{i + 1:03}", "start_frame": i * 12, "duration_frames": 12}
        for i in range(shot_count)
    ]
    board["total_frames"] = shot_count * 12
    write_json(root / "work/storyboard.json", board)
    add_assets(root, versions=1)
    write_json(root / "work/reviews.json", [])
    calls = Counter()
    json_reads = Counter()
    board_copies = []
    original_deepcopy = P.Storyboard.__deepcopy__

    def copied_board(value, memo=None):
        board_copies.append(len(value.shots))
        return original_deepcopy(value, memo)

    monkeypatch.setattr(P.Storyboard, "__deepcopy__", copied_board)
    original = file_hash.__wrapped__
    original_read_text = Path.read_text

    def read_text(path, *args, **kwargs):
        json_reads[path.resolve()] += 1
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)

    # Keep the memoizing wrapper in place; count actual hash computations only.
    import mp3_to_videoclip.storage as storage

    def counted(path):
        calls[Path(path).resolve()] += 1
        return original(path)

    hashed = snapshot_read(counted)
    monkeypatch.setattr(P, "file_hash", hashed)
    from mp3_to_videoclip import reviews

    monkeypatch.setattr(reviews, "file_hash", hashed)
    monkeypatch.setattr(storage, "file_hash", hashed)
    with api_client(tmp_path) as client:
        for _ in range(2):
            calls.clear()
            json_reads.clear()
            board_copies.clear()
            response = client.get("/api/projects/production/images")
            assert response.status_code == 200, response.text
            assert len(response.json()["shots"]) == shot_count
            assert board_copies == [shot_count, shot_count]  # two board copies, not N+1
            assert calls[(root / "media/song.mp3").resolve()] == 1
            assert max(calls.values()) == 1
            # Fixture references share the same imported, content-addressed file.
            assert len(calls) == shot_count + 2  # source + images + 1 unique reference
            for relative in (
                "brief.json",
                "work/storyboard.json",
                "work/assets.json",
                "work/reviews.json",
            ):
                assert json_reads[(root / relative).resolve()] == 1
            # project_root/archive guards also parse metadata outside the engine
            # snapshot. They do not verify or hash the audio source.
            assert json_reads[(root / "project.json").resolve()] <= 4
