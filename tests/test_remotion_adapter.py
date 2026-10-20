"""Derived rendering contracts; no paid providers, no automatic Node installs."""

import base64

import pytest

from mp3_to_videoclip import graphics, remotion
from mp3_to_videoclip.branding import filmstrip_svg
from mp3_to_videoclip.models import Project, Shot
from mp3_to_videoclip.storage import read_json, write_json


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
