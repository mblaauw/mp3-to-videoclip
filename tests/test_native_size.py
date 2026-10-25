"""Declared native image sizes: model rules, legacy defaults and the init flag.

Everything here is local; no provider call and no credential is needed.
"""

import json
import subprocess

import pytest
from test_creative_production import make_root

from mp3_to_videoclip import production as P
from mp3_to_videoclip.cli import execute, parser
from mp3_to_videoclip.models import Project
from mp3_to_videoclip.storage import read_json, write_json


def project(**overrides) -> Project:
    values = {
        "slug": "native",
        "title": "Native",
        "source_sha256": "0" * 64,
        "duration": 4.0,
        "aspect": "16:9",
        "fps": 24,
        "width": 1920,
        "height": 1080,
    }
    values.update(overrides)
    return Project(**values)


def portrait(**overrides) -> Project:
    return project(aspect="9:16", width=1080, height=1920, **overrides)


def synth_source(tmp_path):
    source = tmp_path / "source.mp3"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=duration=0.5", str(source)],
        check=True,
    )
    return source


def init(root, source, *extra):
    return execute(
        parser().parse_args(["init", str(root), "--mp3", str(source), "--slug", root.name, *extra])
    )


# --------------------------------------------------------------------------- #
# model rules
# --------------------------------------------------------------------------- #
def test_valid_native_sizes_are_accepted():
    assert project(native_size=[1376, 768]).image_size == (1376, 768)
    assert project(native_size=[2752, 1536]).image_size == (2752, 1536)
    assert portrait(native_size=[768, 1376]).image_size == (768, 1376)


@pytest.mark.parametrize(
    "value, message",
    [
        ([1376], "exactly"),
        ([1376, 768, 16], "exactly"),
        ([1380, 768], "multiples of 16"),
        ([1376, 770], "multiples of 16"),
        ([512, 400], "512..4096"),
        ([1376, 8192], "512..4096"),
        ([1024, 1024], "aspect ratio"),
        ([2048, 2048], "aspect ratio"),
    ],
)
def test_unusable_native_sizes_are_rejected_with_the_offending_value(value, message):
    with pytest.raises(ValueError, match=message) as excinfo:
        project(native_size=value)
    assert f"{value[0]}x{value[-1]}" in str(excinfo.value) or str(value) in str(excinfo.value)


def test_portrait_productions_reject_landscape_sizes():
    with pytest.raises(ValueError, match="aspect ratio") as excinfo:
        portrait(native_size=[1376, 768])
    assert "1376x768" in str(excinfo.value)


def test_declared_size_never_changes_the_written_shape_when_absent():
    assert "native_size" not in project().model_dump()
    assert "native_size" not in P.project_payload(project())
    assert project(native_size=[1376, 768]).model_dump()["native_size"] == [1376, 768]


# --------------------------------------------------------------------------- #
# legacy defaults
# --------------------------------------------------------------------------- #
def test_image_size_falls_back_to_the_legacy_defaults():
    assert project().image_size == (1536, 864)
    assert portrait().image_size == (864, 1536)


# --------------------------------------------------------------------------- #
# clip init --native-size
# --------------------------------------------------------------------------- #
def test_cli_init_writes_the_declared_native_size(tmp_path):
    source = synth_source(tmp_path)
    root = tmp_path / "native"
    result = init(root, source, "--native-size", "1376x768")
    assert result["native_size"] == [1376, 768]
    stored = json.loads((root / "project.json").read_text())
    assert stored["native_size"] == [1376, 768]
    assert stored["workflow_version"] == 2
    assert P.load_project(root, verify_source=False).image_size == (1376, 768)


def test_cli_init_accepts_an_uppercase_separator(tmp_path):
    source = synth_source(tmp_path)
    root = tmp_path / "upper"
    assert init(root, source, "--native-size", "2752X1536")["native_size"] == [2752, 1536]


def test_cli_init_persists_preset_size_when_the_flag_is_absent(tmp_path):
    source = synth_source(tmp_path)
    root = tmp_path / "legacy"
    result = init(root, source)
    assert result["native_size"] == [1376, 768]
    stored = json.loads((root / "project.json").read_text())
    assert stored["image_model"] == "google-nano-banana-2-1"
    assert stored["image_settings"]["thinkingLevel"] == "minimal"
    assert P.load_project(root, verify_source=False).image_size == (1376, 768)


def test_new_productions_are_always_workflow_2_remotion(tmp_path):
    source = synth_source(tmp_path)
    root = tmp_path / "modern"
    init(root, source)
    stored = json.loads((root / "project.json").read_text())
    assert stored["schema_version"] == 3
    assert stored["workflow_version"] == 2
    assert stored["prompt_version"] == 2
    assert stored["renderer_backend"] == "remotion"
    assert stored["signature_required"] is True
    assert stored["source_filename"] == "source.mp3"


@pytest.mark.parametrize(
    "extra",
    [("--workflow-version", "1"), ("--renderer", "ffmpeg")],
)
def test_removed_legacy_creation_flags_are_rejected_before_writing(tmp_path, extra):
    source = synth_source(tmp_path)
    root = tmp_path / "legacy-refused"
    with pytest.raises(SystemExit):
        init(root, source, *extra)
    assert not root.exists()


def test_existing_legacy_projects_remain_readable(tmp_path):
    """Compatibility readers stay; only new legacy creation is retired."""
    root = tmp_path / "existing-legacy"
    (root / "media").mkdir(parents=True)
    (root / "media/song.mp3").write_bytes(b"existing project")
    stored = {
        "slug": "existing",
        "title": "Existing",
        "source_sha256": "0" * 64,
        "duration": 4.0,
        "aspect": "16:9",
        "fps": 24,
        "width": 1920,
        "height": 1080,
    }
    (root / "project.json").write_text(json.dumps(stored))
    project = P.load_project(root, verify_source=False)
    assert project.workflow_version is None
    assert project.renderer_backend is None
    assert project.image_size == (1536, 864)


@pytest.mark.parametrize("value", ["1376*768", "1376 x 768", "1376", "WxH", "0x0", "-1376x768"])
def test_cli_init_rejects_malformed_values_before_writing(tmp_path, value):
    source = synth_source(tmp_path)
    root = tmp_path / "bad"
    with pytest.raises(ValueError, match="--native-size|native_size"):
        init(root, source, f"--native-size={value}")
    assert not root.exists()


def test_cli_init_rejects_a_ratio_the_production_cannot_use(tmp_path):
    source = synth_source(tmp_path)
    root = tmp_path / "mismatch"
    with pytest.raises(ValueError, match="aspect ratio"):
        init(root, source, "--native-size", "1024x1024")
    assert not root.exists()


# --------------------------------------------------------------------------- #
# the declared size reaches image generation unchanged
# --------------------------------------------------------------------------- #
def test_image_spec_carries_the_declared_size(tmp_path):
    root = make_root(tmp_path)
    config = read_json(root / "project.json")
    config["native_size"] = [1376, 768]
    write_json(root / "project.json", config)
    prompts = execute(parser().parse_args(["prompts", str(root), "--shots", "s001"]))
    assert prompts["shots"][0]["spec"]["size"] == [1376, 768]
