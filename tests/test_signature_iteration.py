"""New signature contracts and single-image journal; providers are always fake."""

from pathlib import Path

import pytest
from PIL import Image
from test_creative_production import (
    approve_prerequisites,
    approve_through_proof,
    make_root,
    record_stills,
    write_preview_report,
)
from test_native_size import init, synth_source
from test_production_defaults import Nano

from mp3_to_videoclip import calibration as C
from mp3_to_videoclip import production as P
from mp3_to_videoclip import profiles, signature
from mp3_to_videoclip.cli import execute, parser
from mp3_to_videoclip.models import Project, Shot
from mp3_to_videoclip.providers import ProviderError
from mp3_to_videoclip.storage import digest, file_hash, read_json, write_json


class Control(Nano):
    def download(self, _, path):
        if self.fail_download:
            raise ProviderError("network_error")
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1376, 768), (40, 80, 120)).save(path)


def test_exact_control_does_not_contaminate_reusable_style():
    text = (
        Path(__file__).parents[1]
        / ".opencode/skills/clip-music-director/references/successful-manual-test.md"
    ).read_text()
    supplied = text.split("```text\n", 1)[1].split("```", 1)[0].strip()
    assert profiles.ROOFTOP_CONTROL_PROMPT == supplied
    assert all(
        t in profiles.DEFAULT_STYLE
        for t in (
            "Alex Ross",
            "Gabriele Dell'Otto",
            "subsurface scattering",
            "natural colour science",
            "35mm",
            "photograph",
        )
    )
    assert not any(
        t in profiles.DEFAULT_STYLE for t in ("rooftop", "rain streak", "50mm", "THE LAST LIGHT")
    )
    benchmark = profiles.STYLE_BENCHMARK
    assert digest(profiles.DEFAULT_STYLE) == benchmark["style_core_hash"]
    assert digest(profiles.ROOFTOP_CONTROL_PROMPT) == benchmark["prompt_hash"]
    assert digest(profiles.default_settings()) == benchmark["settings_hash"]
    assert benchmark["status"] == "user-approved"
    assert benchmark["reference_upload_authorized"] is False


@pytest.mark.parametrize(
    "content",
    [
        "An adult woman in a dry yellow parka crosses a sunlit alpine meadow, wide establishing view, 24mm f/8.",
        "Two adults repair a red bicycle in a bright kitchen, medium two-shot, 35mm f/4.",
        "An empty underwater research station with no people, wide interior and blue ambient light.",
        "Close-up of a weathered wooden violin resting on linen in afternoon window light, 85mm f/2.8.",
    ],
)
def test_different_story_shots_keep_exact_style_without_control_scene(tmp_path, content):
    root = tmp_path / "new-film"
    init(root, synth_source(tmp_path))
    brief = read_json(root / "brief.json")
    brief["creative"]["look"] += (
        "\n\nFilm palette: ochre, pale blue and natural daylight; retain the rendering core."
    )
    write_json(root / "brief.json", brief)
    shot = Shot(
        id="different-story",
        start_frame=0,
        duration_frames=24,
        purpose="Different subject and setting",
        image_prompt=content,
    )
    spec = P.image_spec(root, shot)
    prompt = spec["positivePrompt"]
    assert prompt.startswith(profiles.DEFAULT_STYLE) and prompt.count(profiles.DEFAULT_STYLE) == 1
    assert content in prompt
    assert not any(
        x in prompt
        for x in ("lone adult man", "wet rooftop", "THE LAST LIGHT", "50mm lens at f/2.0")
    )
    assert "no cover border" in prompt
    assert spec["references"] == []  # Golden image is a local comparison, not an auto-upload.
    assert spec["generation"]["settings"] == profiles.default_settings()


def test_default_style_cannot_be_summarized_but_explicit_custom_look_is_allowed(tmp_path):
    root = make_root(tmp_path)
    config = read_json(root / "project.json")
    config.update(style_preset=profiles.STYLE_PRESET_ID, prompt_version=2)
    write_json(root / "project.json", config)
    with pytest.raises(ValueError, match="preserve the approved DEFAULT_STYLE"):
        P.image_spec(root, P.load_board(root).shots[0])
    with pytest.raises(ValueError, match="preserve the approved DEFAULT_STYLE"):
        approve_prerequisites(root)
    config["style_preset"] = "custom"
    write_json(root / "project.json", config)
    assert P.image_spec(root, P.load_board(root).shots[0])["positivePrompt"].startswith(
        "LOOK: muted teal"
    )


def test_new_title_and_signature_draft_are_not_source_filename(tmp_path):
    source = synth_source(tmp_path)
    root = tmp_path / "the-last-light"
    result = init(root, source, "--title", "The Last Light")
    assert result["title"] == "The Last Light" and result["source_filename"] == source.name
    assert result["prompt_version"] == 2 and result["signature_required"] is True
    spec = read_json(root / signature.SPEC)
    assert (spec["intro_seconds"], spec["credits_tail_seconds"]) == (25, 40)
    assert spec["credits"]["cards"] == []
    with pytest.raises(ValueError, match="factual credit roles"):
        signature.validate_spec(root, P.load_project(root))


def test_cli_derives_film_slug_and_rejects_unintended_source_folder(tmp_path):
    source = synth_source(tmp_path)
    root = tmp_path / "the-last-light"
    args = ["init", str(root), "--mp3", str(source), "--title", "The Last Light"]
    result = execute(parser().parse_args(args))
    assert result["slug"] == "the-last-light" and result["title"] == "The Last Light"
    wrong = tmp_path / "source-master-v55"
    with pytest.raises(ValueError, match="derives folder 'the-last-light'"):
        execute(
            parser().parse_args(
                ["init", str(wrong), "--mp3", str(source), "--title", "The Last Light"]
            )
        )
    assert not wrong.exists()


def test_style_first_versioning_preserves_old_image_spec(tmp_path):
    root = make_root(tmp_path)
    shot = P.load_board(root).shots[0]
    old = P.image_spec(root, shot)
    assert old["positivePrompt"].startswith(shot.image_prompt)
    project = read_json(root / "project.json")
    assert not any(
        k in Project.model_validate(project).model_dump()
        for k in ("prompt_version", "signature_required", "source_filename")
    )
    project["prompt_version"] = 2
    write_json(root / "project.json", project)
    new = P.image_spec(root, shot)
    assert new["positivePrompt"].startswith(P.load_brief(root).creative.look)
    assert new["positivePrompt"].count(P.load_brief(root).creative.look) == 1
    project.pop("prompt_version")
    write_json(root / "project.json", project)
    assert P.image_spec(root, shot) == old


def test_single_control_journaled_no_fake_film_or_resubmit(tmp_path):
    root = tmp_path / "calibration"
    fake = Control(root)
    q = C.quote_control(root, client=fake)
    assert fake.submissions == []
    assert not (root / "project.json").exists() and not (root / "media").exists()
    assert not (root / "work/approvals.json").exists()
    out = C.run_control(root, q["id"], "0.10", "test explicit single-control authority", fake)
    assert out["status"] == "ready" and out["user_style_approval"] is False
    assert len(fake.submissions) == 1
    assert fake.submissions[0]["positivePrompt"] == profiles.ROOFTOP_CONTROL_PROMPT
    assert "inputs" not in fake.submissions[0]
    C.run_control(root, q["id"], "0.10", "test same quote resume", fake)
    assert len(fake.submissions) == 1
    with pytest.raises(ValueError, match="one control already"):
        C.quote_control(root, client=fake)


def test_explicit_style_approval_is_durable_bound_and_network_free(tmp_path):
    root = tmp_path / "calibration"
    fake = Control(root)
    q = C.quote_control(root, client=fake)
    C.run_control(root, q["id"], "0.10", "test explicit single-control authority", fake)
    args = parser().parse_args(
        [
            "style-test",
            "approve",
            str(root),
            "--task",
            q["uuid"],
            "--note",
            "User: the style is perfect",
        ]
    )
    approved = execute(args)
    assert approved["user_style_approval"] is True and approved["candidate_only"] is False
    before = (root / C.APPROVAL).read_bytes()
    execute(args)
    assert (root / C.APPROVAL).read_bytes() == before
    assert C.recover_control(root, q["uuid"], fake)["user_style_approval"] is True
    assert len(fake.submissions) == 1 and fake.polls == []
    image = root / approved["path"]
    Image.new("RGB", (1376, 768), (0, 0, 0)).save(image)
    assert C._result(root, q["uuid"])["user_style_approval"] is False
    with pytest.raises(ValueError, match="intact completed"):
        C.approve_control(root, q["uuid"], "User approved original, not changed bytes")


def test_pending_control_cannot_be_approved(tmp_path):
    root = tmp_path / "calibration"
    fake = Control(root, pending=True)
    q = C.quote_control(root, client=fake)
    C.run_control(root, q["id"], "0.10", "test scope", fake)
    with pytest.raises(ValueError, match="intact completed"):
        C.approve_control(root, q["uuid"], "Not yet inspected by user")
    assert not (root / C.APPROVAL).exists()


def test_pending_recovery_never_resubmits(tmp_path):
    root = tmp_path / "calibration"
    fake = Control(root, pending=True)
    q = C.quote_control(root, client=fake)
    assert C.run_control(root, q["id"], "0.10", "test scope", fake)["status"] == "submitted"
    with pytest.raises(ValueError, match="already submitted"):
        C.run_control(root, q["id"], "0.10", "not a retry", fake)
    fake.pending = False
    assert C.recover_control(root, q["uuid"], fake)["status"] == "ready"
    assert len(fake.submissions) == 1 and fake.polls == [q["uuid"]]


def test_tampering_and_excess_cap_stop_before_submission(tmp_path):
    root = tmp_path / "calibration"
    fake = Control(root)
    q = C.quote_control(root, client=fake)
    with pytest.raises(ValueError, match="up to USD"):
        C.run_control(root, q["id"], "1", "test oversized", fake)
    q["request"]["positivePrompt"] = "not the control"
    q["input_hash"] = digest(q["request"])
    write_json(root / f"work/quotes/{q['id']}.json", q)
    with pytest.raises(ValueError, match="exact authorized"):
        C.run_control(root, q["id"], "0.10", "test edited", fake)
    assert not fake.submissions and not read_json(root / "work/tasks.json")
    assert (
        parser().parse_args(["style-test", "recover", str(root), "--task", q["uuid"]]).operation
        == "recover"
    )


def confirmed_spec(root, project):
    spec = signature.draft_spec(project.title)
    spec["credit_roles_confirmed"] = True
    spec["credits"]["cards"] = [["MUSIC", "User-supplied name"]]
    write_json(root / signature.SPEC, spec)
    return spec


def signature_root(tmp_path):
    root = make_root(tmp_path)
    project = Project.model_validate(
        {**P.load_project(root).model_dump(), "duration": 172.4, "signature_required": True}
    )
    write_json(root / "project.json", project.model_dump())
    board = read_json(root / "work/storyboard.json")
    board["total_frames"] = project.total_frames
    board["shots"][-1]["duration_frames"] = project.total_frames - board["shots"][-1]["start_frame"]
    write_json(root / "work/storyboard.json", board)
    events = read_json(root / "work/events.json")
    events["total_frames"] = project.total_frames
    write_json(root / "work/events.json", events)
    music = read_json(root / "work/music.json")
    music["duration"] = project.duration
    write_json(root / "work/music.json", music)
    confirmed_spec(root, project)
    approve_through_proof(root)
    record_stills(root, ["s003"])
    write_preview_report(root)
    P.approve(root, "preview", "test inspected sequence")
    P.approve(root, "stills", "test accepted still set")
    return root


def review_fixture(root):
    from mp3_to_videoclip import graphics

    spec = read_json(root / signature.SPEC)
    resolved_hash = digest(graphics.load_spec(root))
    revision = graphics.implementation_revision()
    base = root / "base.mp4"
    base.write_bytes(b"test-base")
    sample = root / "sample.png"
    sample.write_bytes(b"test-sample")
    preflight = root / "preflight.json"
    write_json(
        preflight,
        {
            "base": {"sha256": file_hash(base)},
            "spec_sha256": resolved_hash,
            "implementation_revision": revision,
            "truncated": False,
            "frames": [{"image": str(sample)}],
        },
    )
    inputs = signature.current_input_hash(root)
    write_json(base.with_suffix(".json"), {"input_hash": inputs})
    write_json(
        root / signature.REVIEW,
        {
            "base": "base.mp4",
            "base_sha256": file_hash(base),
            "base_input_hash": inputs,
            "spec_hash": digest(spec),
            "resolved_spec_hash": resolved_hash,
            "implementation_revision": revision,
            "preflight": "preflight.json",
            "preflight_sha256": file_hash(preflight),
            "samples": {"sample.png": file_hash(sample)},
        },
    )
    return sample


def test_signature_review_binds_spec_base_and_sample_bytes(tmp_path):
    root = signature_root(tmp_path)
    project = P.load_project(root)
    sample = review_fixture(root)
    signature.validate_review(root, project)
    sample.write_bytes(b"edited")
    with pytest.raises(ValueError, match="sample changed"):
        signature.validate_review(root, project)


def test_graphics_review_rejects_implementation_change(tmp_path, monkeypatch):
    from mp3_to_videoclip import graphics

    root = signature_root(tmp_path)
    review_fixture(root)
    monkeypatch.setattr(graphics, "implementation_revision", lambda: "different-renderer")
    with pytest.raises(ValueError, match="graphics implementation changed"):
        signature.validate_review(root, P.load_project(root))


def test_graphics_review_rejects_resolved_identity_change(tmp_path, monkeypatch):
    from mp3_to_videoclip import graphics

    root = signature_root(tmp_path)
    review_fixture(root)
    original = graphics.load_spec

    def changed(root, path=None):
        spec = original(root, path)
        spec["palette"] = {"accent": "#112233"}
        return spec

    monkeypatch.setattr(graphics, "load_spec", changed)
    with pytest.raises(ValueError, match="graphics identity changed"):
        signature.validate_review(root, P.load_project(root))


def test_obsolete_base_cannot_be_approved_after_upstream_reapproval(tmp_path):
    root = signature_root(tmp_path)
    review_fixture(root)
    board = read_json(root / "work/storyboard.json")
    board["shots"][0]["camera"] = "zoom_out"
    write_json(root / "work/storyboard.json", board)
    P.approve(root, "storyboard", "test explicit camera revision")
    P.approve(root, "proof", "test renewed proof")
    write_preview_report(root)
    P.approve(root, "preview", "test renewed preview")
    P.approve(root, "stills", "test renewed still set")
    with pytest.raises(ValueError, match="obsolete storyboard"):
        P.approve(root, "graphics", "test old graphics cannot bless obsolete base", inspected=True)


def test_cli_requires_inspected_graphics_and_composes_not_base(tmp_path, monkeypatch):
    import mp3_to_videoclip.graphics as graphics

    root = signature_root(tmp_path)
    review_fixture(root)
    with pytest.raises(ValueError, match="graphics needs"):
        execute(parser().parse_args(["render", str(root)]))
    with pytest.raises(ValueError, match="--inspected"):
        execute(parser().parse_args(["approve", str(root), "graphics", "--note", "not inspected"]))
    execute(
        parser().parse_args(
            [
                "approve",
                str(root),
                "graphics",
                "--inspected",
                "--note",
                "test actual graphics samples inspected",
            ]
        )
    )
    calls = []

    def compose(_root, base, output):
        calls.append((base, output))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"test composite")
        return {"output": str(output)}

    monkeypatch.setattr(graphics, "compose", compose)
    result = execute(parser().parse_args(["render", str(root)]))
    assert result["delivery_ready"] is True
    assert calls[0][0] == root / "base.mp4"
    assert calls[0][1].name == "creative-stills-v001.mp4"


def test_portrait_signature_blocked_before_brief_spending(tmp_path):
    root = make_root(tmp_path)
    project = Project.model_validate(
        {**P.load_project(root).model_dump(), "aspect": "9:16", "width": 108, "height": 192}
    )
    with pytest.raises(ValueError, match="resolve portrait graphics before brief"):
        signature.validate_spec(root, project)


def test_new_skeleton_defaults_do_not_change_old_film_cadence(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    calls = []

    def skeleton(_root, target, timing, **bounds):
        calls.append((target, timing, bounds))
        return P.load_board(root)

    monkeypatch.setattr(P, "skeleton", skeleton)
    execute(parser().parse_args(["skeleton", str(root), "--timing", "adaptive"]))
    assert calls[-1] == (8, "adaptive", {"min_seconds": 4, "max_seconds": 12})
    config = read_json(root / "project.json")
    config["prompt_version"] = 2
    write_json(root / "project.json", config)
    execute(parser().parse_args(["skeleton", str(root)]))
    # No model on this synthetic fixture: explicitly choose adaptive as in new init.
    execute(parser().parse_args(["skeleton", str(root), "--timing", "adaptive"]))
    assert calls[-1] == (5, "adaptive", {"min_seconds": 1.5, "max_seconds": 7})


@pytest.mark.parametrize("renderer_binding", [False, True])
def test_base_render_prepares_review_but_is_never_delivery(tmp_path, monkeypatch, renderer_binding):
    import mp3_to_videoclip.cli as cli
    import mp3_to_videoclip.graphics as graphics

    root = signature_root(tmp_path)
    if renderer_binding:
        from mp3_to_videoclip import remotion

        monkeypatch.setattr(
            remotion, "renderer_binding", lambda project: {"renderer_revision": "test-renderer"}
        )
    calls = []

    def render(_project, _shots, _source, output, _work, **_kwargs):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"test base movie")
        return {"output": str(output)}

    def preflight(_root, base, output):
        calls.append(base)
        output.mkdir(parents=True)
        image = output / "sample.png"
        image.write_bytes(b"test composited sample")
        sidecar = output / "preflight.json"
        write_json(
            sidecar,
            {
                "base": {"sha256": file_hash(base)},
                "implementation_revision": graphics.implementation_revision(),
                "spec_sha256": digest(graphics.load_spec(_root)),
                "truncated": False,
                "frames": [{"image": str(image)}],
            },
        )
        return {"sidecar": str(sidecar)}

    monkeypatch.setattr(cli, "render", render)
    monkeypatch.setattr(graphics, "preflight_frames", preflight)
    result = execute(parser().parse_args(["render", str(root), "--base-only"]))
    assert result["delivery_ready"] is False and len(calls) == 1
    assert Path(result["output"]).name == "creative-base-v001.mp4"
    signature.validate_review(root, P.load_project(root))
    with pytest.raises(ValueError, match="graphics needs"):
        execute(parser().parse_args(["render", str(root)]))


def test_billed_download_failure_recovers_same_request(tmp_path):
    root = tmp_path / "calibration"
    fake = Control(root, fail_download=True)
    quote = C.quote_control(root, client=fake)
    with pytest.raises(ProviderError):
        C.run_control(root, quote["id"], "0.10", "test single control authority", fake)
    task = read_json(root / "work/tasks.json")[quote["uuid"]]
    assert task["status"] == "result" and task["cost_usd"] is not None
    fake.fail_download = False
    assert C.recover_control(root, quote["uuid"], fake)["status"] == "ready"
    assert len(fake.submissions) == 1 and fake.polls == []
