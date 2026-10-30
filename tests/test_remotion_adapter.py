"""Derived rendering contracts; no paid providers, no automatic Node installs."""

import base64
from pathlib import Path

import pytest

from mp3_to_videoclip import graphics, remotion
from mp3_to_videoclip.branding import filmstrip_svg
from mp3_to_videoclip.models import Project, Shot
from mp3_to_videoclip.storage import read_json, write_json


@pytest.fixture
def base_cache(tmp_path, monkeypatch):
    from PIL import Image

    from mp3_to_videoclip import render
    from mp3_to_videoclip.models import RenderShot

    image = tmp_path / "selected.png"
    Image.new("RGB", (160, 90), "red").save(image)
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"audio")
    project = Project(
        slug="cache",
        title="Cache",
        source_sha256="a" * 64,
        duration=1,
        width=160,
        height=90,
    )
    shots = [RenderShot(shot=shot(), image=str(image))]
    calls = []
    monkeypatch.setattr(remotion, "implementation_hash", lambda: "revision")
    monkeypatch.setattr(render, "_validate_shots", lambda *a: None)
    monkeypatch.setattr(render, "_count_frames", lambda *a: project.total_frames)
    monkeypatch.setattr(render, "_binary", lambda x: x)
    monkeypatch.setattr(render, "audio_seconds", lambda *a: 1)
    monkeypatch.setattr(render, "_validate_output", lambda *a: {"video": {"frames": 24}})
    monkeypatch.setattr(render, "_run", lambda argv: Path(argv[-1]).write_bytes(b"mux"))

    def invoke(*args):
        calls.append(args)
        args[1].write_bytes(b"movie")
        write_json(Path(f"{args[1]}.render.json"), {"timings": "historical"})

    monkeypatch.setattr(remotion, "invoke", invoke)

    def run(**kwargs):
        return remotion.render_base(
            project,
            shots,
            audio,
            tmp_path / f"out-{len(list(tmp_path.glob('out-*')))}.mp4",
            tmp_path / "work",
            **kwargs,
        )

    return project, shots, calls, run


def test_budget_only_reuses_silent_cache_and_labels_historical_timers(base_cache):
    project, _, calls, run = base_cache
    first = run()
    project.budget.append({"amount": 50, "reason": "top-up"})
    second = run()
    assert len(calls) == 1
    assert first["input_hash"] == second["input_hash"]
    assert second["visual_cache_hit"] is True
    assert second["renderer_report"] is None
    assert second["historical_renderer_report"] == first["renderer_report"]


def test_same_visual_cache_is_serialized_across_processes(base_cache, tmp_path, monkeypatch):
    import multiprocessing
    import os

    from mp3_to_videoclip import render
    from mp3_to_videoclip.storage import file_hash

    project, shots, _, _ = base_cache
    ctx = multiprocessing.get_context("fork")  # Supported on both Linux and macOS.
    rendering = ctx.Event()
    contending = ctx.Event()
    muxing = ctx.Barrier(2)
    mux_probe = ctx.Lock()
    results = ctx.Queue()
    flock = remotion.fcntl.flock
    work = tmp_path / "work"

    def synchronized_flock(handle, operation):
        locks = list(work.glob("remotion-base-*.lock"))
        if (
            multiprocessing.current_process().name == "cache-second"
            and locks
            and os.fstat(handle.fileno()).st_ino == locks[0].stat().st_ino
        ):
            # Prove the first renderer still owns the lock before unblocking it.
            with pytest.raises(BlockingIOError):
                flock(handle, operation | remotion.fcntl.LOCK_NB)
            contending.set()
        return flock(handle, operation)

    def invoke(kind, movie, selected, canvas, fps, frames, inputs):
        with (tmp_path / "invocations").open("a") as log:
            log.write(f"{selected}\n")
        rendering.set()
        assert contending.wait(10), "second process never contended for the cache"
        with movie.open("xb") as handle:
            handle.write(b"one immutable movie")

    def mux(argv):
        # Muxing must happen after releasing the visual lock.
        muxing.wait(timeout=10)
        with mux_probe, next(work.glob("remotion-base-*.lock")).open("a") as handle:
            flock(handle, remotion.fcntl.LOCK_EX | remotion.fcntl.LOCK_NB)
        with Path(argv[-1]).open("xb") as handle:
            handle.write(b"mux")

    def worker(index):
        try:
            report = remotion.render_base(
                project,
                shots,
                tmp_path / "audio.mp3",
                tmp_path / f"final-{index}.mp4",
                work,
            )
            results.put(("ok", report))
        except Exception as error:
            results.put(("error", repr(error)))
            raise

    monkeypatch.setattr(remotion.fcntl, "flock", synchronized_flock)
    monkeypatch.setattr(remotion, "invoke", invoke)
    monkeypatch.setattr(render, "_run", mux)
    first = ctx.Process(target=worker, args=(1,), name="cache-first")
    second = ctx.Process(target=worker, args=(2,), name="cache-second")
    try:
        first.start()
        assert rendering.wait(10)
        second.start()
        messages = [results.get(timeout=15), results.get(timeout=15)]
        for process in (first, second):
            process.join(timeout=10)
            assert process.exitcode == 0
    finally:
        for process in (first, second):
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
    assert all(status == "ok" for status, _ in messages), messages
    reports = [report for _, report in messages]
    assert sorted(report["visual_cache_hit"] for report in reports) == [False, True]
    assert all(report["verified"] for report in reports)
    assert len((tmp_path / "invocations").read_text().splitlines()) == 1
    movie = next(work.glob("remotion-base-*.mp4"))
    key = reports[0]["input_hash"]
    compiled = remotion.compile_shots(shots, work, work / "remotion-assets")
    expected = remotion.visual_identity(
        project,
        {"shots": compiled, "preview_banner": False, "preview_placeholders": []},
        "revision",
    )
    assert key == expected == reports[1]["input_hash"]
    selected = remotion.selected_asset_root(compiled, work / "remotion-assets")
    assert (tmp_path / "invocations").read_text() == f"{selected}\n"
    assert read_json(movie.with_suffix(".cache.json")) == {"sha256": file_hash(movie), "key": key}
    assert all(report["visual_sha256"] == file_hash(movie) for report in reports)
    assert movie.read_bytes() == b"one immutable movie"
    assert all((tmp_path / f"final-{index}.mp4").read_bytes() == b"mux" for index in (1, 2))


@pytest.mark.parametrize("damage", ["movie", "missing", "malformed", "key", "list"])
def test_silent_cache_corruption_fails_closed_preserving_evidence(base_cache, damage):
    _, _, calls, run = base_cache
    run()
    movie = calls[0][1]
    sidecar = movie.with_suffix(".cache.json")
    if damage == "movie":
        movie.write_bytes(b"tampered")
    elif damage == "missing":
        sidecar.rename(sidecar.with_suffix(".saved"))
    elif damage == "malformed":
        sidecar.write_text("{")
    elif damage == "list":
        write_json(sidecar, [])
    else:
        record = read_json(sidecar)
        record["key"] = "wrong"
        write_json(sidecar, record)
    before = movie.read_bytes()
    with pytest.raises(ValueError, match="cache corruption"):
        run()
    assert len(calls) == 1 and movie.read_bytes() == before


@pytest.mark.parametrize(
    "field,value", [("width", 162), ("height", 92), ("fps", 30), ("duration", 2)]
)
def test_visual_identity_canvas_timing_invalidation(base_cache, field, value):
    project, _, _, _ = base_cache
    before = remotion.visual_identity(project, {"shots": []}, "rev")
    changed = project.model_copy(update={field: value})
    assert remotion.visual_identity(changed, {"shots": []}, "rev") != before


@pytest.mark.parametrize(
    "change",
    [
        {"camera": {"zoom": 1.1}},
        {"grade": {"contrast": 1.1}},
        {"text": "new"},
        {"image_sha256": "new"},
        {"brand_plate": "data:new"},
        {"preview_banner": True},
        {"preview_placeholders": ["s1"]},
        {"start_frame": 1},
        {"duration_frames": 25},
    ],
)
def test_visual_identity_binds_all_compiled_inputs(base_cache, change):
    project, _, _, _ = base_cache
    before = remotion.visual_identity(project, {"shots": []}, "rev")
    assert remotion.visual_identity(project, {"shots": [], **change}, "rev") != before
    assert remotion.visual_identity(project, {"shots": []}, "new-rev") != before


def test_publication_excludes_history_and_preserves_corruption(base_cache):
    _, shots, calls, run = base_cache
    run()
    selected = calls[0][2]
    assets = selected.parent.parent / "remotion-assets"
    (assets / "historical.png").write_bytes(b"old")
    run()
    assert {p.name for p in selected.iterdir()} == {calls[0][-1]["shots"][0]["image"]}
    target = next(selected.iterdir())
    target.write_bytes(b"corrupt")
    with pytest.raises(remotion.AssetCacheCorruption):
        run()
    assert target.read_bytes() == b"corrupt"
    assert Path(shots[0].image).is_file()


def test_selected_image_bytes_invalidate_cache(base_cache):
    from PIL import Image

    _, shots, calls, run = base_cache
    first = run()
    Image.new("RGB", (160, 90), "blue").save(shots[0].image)
    second = run()
    assert first["input_hash"] != second["input_hash"]
    assert len(calls) == 2 and calls[0][2] != calls[1][2]
    assert len(list(calls[1][2].iterdir())) == 1


def test_native_panes_publish_selected_bytes_and_never_hide_corruption(tmp_path, monkeypatch):
    from PIL import Image

    from mp3_to_videoclip import production
    from mp3_to_videoclip.models import Pane, RenderShot

    assets = tmp_path / "work/remotion-assets"
    assets.mkdir(parents=True)
    images = []
    for index, colour in enumerate(["red", "blue", "green"]):
        image = tmp_path / f"{index}.png"
        Image.new("RGB", (160, 90), colour).save(image)
        images.append(image)
    sources = {"left": images[1], "right": images[2]}
    monkeypatch.setattr(
        production,
        "resolved_assets",
        lambda root, ids: [RenderShot(shot=shot(), image=str(sources[ids[0]]))],
    )
    split = RenderShot(
        shot=shot(kind="split", panes=[Pane(shot_id="left"), Pane(shot_id="right")]),
        image=str(images[0]),
    )
    compiled = remotion.compile_shots([split], tmp_path / "work", assets)
    selected = remotion.selected_asset_root(compiled, assets)
    assert len(list(selected.iterdir())) == 3
    pane = assets / compiled[0]["split_panes"][0]["image"]
    pane.write_bytes(b"tampered")
    with pytest.raises(remotion.AssetCacheCorruption):
        remotion.compile_shots([split], tmp_path / "work", assets)
    assert pane.read_bytes() == b"tampered"


def test_unavailable_native_panes_still_allow_plate_fallback(tmp_path, monkeypatch):
    from PIL import Image

    from mp3_to_videoclip import production
    from mp3_to_videoclip.models import Pane, RenderShot

    assets = tmp_path / "assets"
    assets.mkdir()
    image = tmp_path / "plate.png"
    Image.new("RGB", (160, 90), "red").save(image)

    def unavailable(*args):
        raise ValueError("pane unavailable")

    monkeypatch.setattr(production, "resolved_assets", unavailable)
    compiled = remotion.compile_shots(
        [
            RenderShot(
                shot=shot(kind="split", panes=[Pane(shot_id="left"), Pane(shot_id="right")]),
                image=str(image),
            )
        ],
        tmp_path / "work",
        assets,
    )
    assert "split_panes" not in compiled[0]


def test_concurrent_processes_publish_one_complete_selection(base_cache):
    import multiprocessing

    _, _, calls, run = base_cache
    run()
    compiled = calls[0][-1]["shots"]
    assets = calls[0][2].parent.parent / "remotion-assets"
    # A different manifest publishes a fresh selection concurrently.
    from PIL import Image

    image = assets.parent / "other.png"
    Image.new("RGB", (160, 90), "yellow").save(image)
    name, sha = remotion._stage_asset(image, assets)
    compiled = [{**compiled[0], "image": name, "image_sha256": sha}]
    with multiprocessing.get_context("spawn").Pool(2) as pool:
        roots = pool.starmap(remotion.selected_asset_root, [(compiled, assets)] * 4)
    assert len(set(roots)) == 1
    assert {p.name for p in roots[0].iterdir()} == {name}
    assert (assets / name).is_file()


def test_tampered_staging_cache_is_not_repaired_or_hidden(base_cache):
    _, _, calls, run = base_cache
    run()
    assets = calls[0][2].parent.parent / "remotion-assets"
    staged = assets / calls[0][-1]["shots"][0]["image"]
    staged.write_bytes(b"tampered staging")
    with pytest.raises(remotion.AssetCacheCorruption):
        run()
    assert staged.read_bytes() == b"tampered staging"


def shot(**changes):
    return Shot(
        id="s1", start_frame=0, duration_frames=24, purpose="test", image_prompt="test", **changes
    )


def test_new_controls_are_opt_in_and_old_shot_payload_is_stable():
    payload = shot().model_dump()
    assert not {"post_effects", "camera_keyframes", "transition"} & payload.keys()
    project = Project(
        slug="old", title="Old", source_sha256="a" * 64, duration=1, width=192, height=108
    )
    assert "renderer_backend" not in project.model_dump()


@pytest.mark.parametrize(
    "settings",
    [
        {"transition": "wipe_left"},
        {"post_effects": {"brightness": 5}},
        {"post_effects": {"unexpected": True}},
        {"camera_keyframes": [{"frame": 1}, {"frame": 20}]},
        {"camera_keyframes": [{"frame": 0}, {"frame": 24}]},
        {"camera_keyframes": [{"frame": 0}, {"frame": 2}, {"frame": 2}]},
    ],
)
def test_controls_reject_invalid_or_silent_effects(settings):
    with pytest.raises(ValueError):
        shot(**settings)


def test_filmstrip_transparency_and_colour_validation():
    svg = filmstrip_svg()
    assert "<mask " in svg and 'mask="url(#cut)"' in svg
    assert '<rect width="156" height="90" fill="black"' not in svg
    assert svg.count('width="9" height="8"') == 14
    with pytest.raises(ValueError):
        filmstrip_svg('"/><script/>')


def test_remotion_graphics_uses_single_brand_geometry(tmp_path, monkeypatch):
    calls = []
    font = tmp_path / "font.ttc"
    font.write_bytes(b"testfont")
    monkeypatch.setattr(graphics, "resolve_font", lambda: (font, {}, "fixture"))
    monkeypatch.setattr(remotion, "invoke", lambda *args: calls.append(args))
    palette = {
        "ink": (244, 241, 232),
        "accent": (212, 174, 106),
        "night": (11, 16, 21),
        "secondary": (110, 139, 153),
    }
    spec = {"intro": {"mark": {"kind": "filmstrip"}}}
    part = {"kind": "identity", "frames": 48}
    remotion.graphics_clip(part, spec, palette, (1920, 1080), 24, tmp_path / "alpha.mov")
    inputs = calls[0][-1]
    actual = base64.b64decode(inputs["logo"].split(",", 1)[1]).decode()
    assert actual == filmstrip_svg("#d4ae6a")
    assert calls[0][0] == "graphics" and calls[0][5] == 48


def test_corrupt_alpha_cache_never_reused(tmp_path, monkeypatch):
    monkeypatch.setattr(remotion, "implementation_hash", lambda: "revision")
    # Exercise the real existing cache-integrity guard rather than trusting path existence.
    clip = tmp_path / "cached.mov"
    clip.write_bytes(b"first")
    graphics._cache_integrity(clip, created=True)
    clip.write_bytes(b"different")
    with pytest.raises(graphics.ComposeError):
        graphics._cache_integrity(clip, created=False)


def test_changed_post_effects_invalidates_proof_preview(tmp_path):
    from test_creative_production import make_root

    from mp3_to_videoclip import production

    root = make_root(tmp_path)
    before = production.preview_board_hash(root)
    board = read_json(root / "work/storyboard.json")
    board["shots"][0]["post_effects"] = {"contrast": 1.04}
    write_json(root / "work/storyboard.json", board)
    assert before != production.preview_board_hash(root)


def test_backend_change_does_not_rewrite_upstream_analysis_identity(tmp_path):
    from test_creative_production import make_root

    from mp3_to_videoclip import production

    root = make_root(tmp_path)
    before = production.stage_hash(root, "analysis")
    project = read_json(root / "project.json")
    project["renderer_backend"] = "remotion"
    write_json(root / "project.json", project)
    assert production.stage_hash(root, "analysis") == before


def test_cli_preview_retains_renderer_revision(tmp_path, monkeypatch):
    from test_signature_iteration import signature_root

    from mp3_to_videoclip import cli

    root = signature_root(tmp_path)

    def preview(root, project, board, available, output, workdir):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"review-fixture")
        return {
            "input_hash": "input",
            "placeholder_shots": [],
            "actual_shots": [],
            "renderer_revision": "exact-remotion-revision",
        }

    monkeypatch.setattr(cli, "build_preview", preview)
    cli.execute(cli.parser().parse_args(["preview", str(root), "--scope", "proof"]))
    assert (
        read_json(root / "work/preview-review.json")["renderer_revision"]
        == "exact-remotion-revision"
    )


def test_first_base_creates_nested_destination_before_rendering(tmp_path, monkeypatch):
    from PIL import Image

    from mp3_to_videoclip.models import RenderShot

    image = tmp_path / "image.png"
    Image.new("RGB", (160, 90), "red").save(image)
    project = Project(
        slug="fresh",
        title="Fresh",
        source_sha256="a" * 64,
        duration=1,
        width=160,
        height=90,
        renderer_backend="remotion",
    )
    output = tmp_path / "not-yet-existing/renders/new.mp4"
    monkeypatch.setattr(remotion, "implementation_hash", lambda: "revision")

    def invoke(*args):
        assert output.parent.is_dir()
        raise RuntimeError("stopped after destination check")

    monkeypatch.setattr(remotion, "invoke", invoke)
    with pytest.raises(RuntimeError, match="destination check"):
        remotion.render_base(
            project,
            [RenderShot(shot=shot(), image=str(image))],
            tmp_path / "audio.mp3",
            output,
            tmp_path / "work",
        )


def test_approval_revision_does_not_read_the_browser(tmp_path, monkeypatch):
    first = remotion.implementation_hash()
    chrome = tmp_path / "Chrome"
    chrome.write_bytes(b"browser version one")
    monkeypatch.setenv("REMOTION_CHROME", str(chrome))
    assert remotion.implementation_hash() == first
    chrome.write_bytes(b"browser version two after a security update")
    assert remotion.implementation_hash() == first
    monkeypatch.setenv("REMOTION_CHROME", str(tmp_path / "not-installed"))
    assert remotion.implementation_hash() == first


def test_schema_three_uses_remotion_without_a_legacy_backend_flag(tmp_path, monkeypatch):
    project = Project(
        slug="new-film",
        schema_version=3,
        title="New",
        source_sha256="a" * 64,
        duration=1,
        width=192,
        height=108,
    )
    legacy = Project(
        slug="old-film",
        title="Old",
        source_sha256="a" * 64,
        duration=1,
        width=192,
        height=108,
    )
    assert project.uses_remotion is True
    assert legacy.uses_remotion is False
    monkeypatch.setattr(remotion, "implementation_hash", lambda: "revision")
    assert remotion.renderer_binding(project) == {
        "renderer_backend": "remotion",
        "renderer_revision": "revision",
    }
    assert remotion.renderer_binding(legacy) == {}

    from mp3_to_videoclip import render as R

    monkeypatch.setattr(
        "mp3_to_videoclip.remotion.render_base", lambda *args, **kwargs: {"sentinel": True}
    )
    result = R.render(project, [], tmp_path / "audio.mp3", tmp_path / "out.mp4", tmp_path)
    assert result == {"sentinel": True}


def test_titles_join_the_base_pass_and_its_cache_key_only_when_given(base_cache):
    _project, _shots, calls, run = base_cache
    plain = run()
    assert "titles" not in calls[-1][-1]
    assert plain["titles"] == []

    titles = {
        "spec": {"intro": {"names": "A", "title": "Cache"}},
        "intro": {"names": "A", "title": "Cache"},
        "palette": {"accent": "#ffffff"},
        "logo": "data:image/svg+xml;base64,PHN2Zy8+",
        "font": None,
        "windows": [{"kind": "intro", "id": "intro", "start_frame": 0, "frames": 24}],
    }
    titled = run(titles=titles)
    assert calls[-1][-1]["titles"] == titles
    assert titled["titles"] == ["intro"]
    assert titled["input_hash"] != plain["input_hash"]
    assert len(calls) == 2, "a titled pass never reuses the untitled visual cache"
