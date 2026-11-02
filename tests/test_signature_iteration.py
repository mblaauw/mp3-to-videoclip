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

from mp3_to_videoclip import production as P
from mp3_to_videoclip import profiles, signature
from mp3_to_videoclip.legacy import graphics_review
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
    text = (Path(__file__).parent / "fixtures/successful-manual-test.md").read_text()
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
    assert prompt.startswith(content) and prompt.count(profiles.DEFAULT_STYLE) == 1
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
    result = init(root, source, "--title", "The Last Light", "--titles", "joint-v1")
    assert result["title"] == "The Last Light" and result["source_filename"] == source.name
    assert result["prompt_version"] == 3 and result["signature_required"] is True
    spec = read_json(root / signature.SPEC)
    assert (spec["intro_seconds"], spec["credits_tail_seconds"]) == (25, 40)
    assert spec["credits"]["cards"] == []
    with pytest.raises(ValueError, match="factual credit roles"):
        signature.validate_spec(root, P.load_project(root))


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
    record_stills(root, ["s003"], reviewed=True)
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

    root = signature_root(tmp_path)
    review_fixture(root)
    monkeypatch.setattr(graphics_review, "implementation_revision", lambda: "different-renderer")
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


def test_a_titles_approval_needs_the_samples_inspected(tmp_path):
    root = signature_root(tmp_path)
    review_fixture(root)
    with pytest.raises(ValueError, match="--inspected"):
        P.approve(root, "graphics", "not inspected")
    P.approve(root, "graphics", "test actual graphics samples inspected", inspected=True)


def test_portrait_signature_blocked_before_brief_spending(tmp_path):
    root = make_root(tmp_path)
    project = Project.model_validate(
        {**P.load_project(root).model_dump(), "aspect": "9:16", "width": 108, "height": 192}
    )
    with pytest.raises(ValueError, match="resolve portrait graphics before brief"):
        signature.validate_spec(root, project)
