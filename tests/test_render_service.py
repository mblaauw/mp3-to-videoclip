"""Preview/final service wiring; the renderer itself is faked, no browser or FFmpeg."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from api_support import add_assets, make_api_project

from mp3_to_videoclip import graphics, services, signature
from mp3_to_videoclip import production as P
from mp3_to_videoclip.storage import file_hash, read_json, write_json


def _fake_render(calls):
    def fake(project, shots, audio, output, workdir, **kwargs):
        calls.append({"project": project, "shots": shots, "output": output, **kwargs})
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_bytes(b"fake preview bytes")
        return {
            "renderer_revision": "revision-1",
            "input_hash": "b" * 64,
            "verified": True,
        }

    return fake


def test_preview_job_writes_the_report_the_approval_binds(tmp_path, monkeypatch):
    root = make_api_project(tmp_path)
    add_assets(root)
    calls = []
    monkeypatch.setattr(services.render, "_render", _fake_render(calls))
    output = root / "previews" / "preview-v001.mp4"

    report = services.render.render_preview(root, output)

    assert report["approval_ready"] is True
    assert calls[0]["preview_banner"] is True
    review = read_json(root / "work" / "preview-review.json")
    assert review == {
        "movie": "previews/preview-v001.mp4",
        "movie_sha256": file_hash(output),
        "storyboard_hash": P.preview_board_hash(root),
        "proof_hash": P.stage_hash(root, "proof"),
        "brand_hash": None,
        "input_hash": "b" * 64,
        "renderer_revision": "revision-1",
    }
    assert report["review"]["movie_sha256"] == file_hash(output)


def test_preview_and_final_pass_the_brand_package(tmp_path, monkeypatch):
    root = make_api_project(tmp_path)
    add_assets(root)
    write_json(
        root / "brand.json",
        {
            "id": "test-brand",
            "mark": "filmstrip",
            "name": "TEST FILM",
            "duration_seconds": 8,
            "plate": False,
        },
    )
    calls = []
    monkeypatch.setattr(services.render, "_render", _fake_render(calls))
    monkeypatch.setattr(P, "require_approval", lambda root, stage: None)
    monkeypatch.setattr(services.render.P, "resolved_assets", lambda root, ids=None: [])

    services.render.render_preview(root, root / "previews" / "brand-v001.mp4")
    services.render.render_final(root, root / "renders" / "brand-v001.mp4")

    assert calls[0]["brand"] is not None
    assert calls[1]["brand"] is not None
    assert read_json(root / "work" / "preview-review.json")["brand_hash"] == P.brand_hash(root)


def test_the_report_written_by_the_preview_job_passes_the_preview_gate(tmp_path, monkeypatch):
    from test_creative_production import approve_through_proof

    from mp3_to_videoclip import remotion

    monkeypatch.setattr(remotion, "implementation_hash", lambda: "revision-1")

    root = make_api_project(tmp_path)
    add_assets(root)
    from mp3_to_videoclip import reviews

    for shot_id in P.proof_ids(P.load_board(root), P.load_brief(root)):
        reviews.record_review(
            root,
            shot_id,
            1,
            "accept",
            note="Inspected this exact proof still",
            reviewer="studio",
            inspected=True,
        )
    approve_through_proof(root)
    monkeypatch.setattr(services.render, "_render", _fake_render([]))

    services.render.render_preview(root, root / "previews" / "gated-v001.mp4")

    P.approve(
        root,
        "preview",
        "Watched the whole preview with the actual music",
        via="studio",
        review_confirmed=True,
        preview_watched=True,
    )
    P.require_approval(root, "preview")


def test_signature_final_requires_graphics_before_compose(tmp_path, monkeypatch):
    root = make_api_project(tmp_path)
    add_assets(root)
    stored = read_json(root / "project.json")
    stored["signature_required"] = True
    write_json(root / "project.json", stored)
    composed = []

    def gate(_root, stage):
        if stage == "graphics":
            raise ValueError("graphics needs current user approval")

    monkeypatch.setattr(services.render.P, "require_approval", gate)
    monkeypatch.setattr(
        graphics,
        "compose",
        lambda *args, **kwargs: composed.append((args, kwargs)) or {},
    )

    with pytest.raises(ValueError, match="graphics needs current user approval"):
        services.render.render_final(root, root / "renders" / "final-v001.mp4")
    assert composed == []


def test_signature_final_composes_the_reviewed_base(tmp_path, monkeypatch):
    root = make_api_project(tmp_path)
    add_assets(root)
    stored = read_json(root / "project.json")
    stored["signature_required"] = True
    write_json(root / "project.json", stored)
    base = root / "renders" / "base-v001.mp4"
    base.parent.mkdir()
    base.write_bytes(b"reviewed base")
    approvals = []
    calls = []

    def compose(root_arg, base_arg, output_arg):
        calls.append((root_arg, base_arg, output_arg))
        output_arg.write_bytes(b"composed film")
        return {"output": str(output_arg), "delivery_ready": False}

    monkeypatch.setattr(
        services.render.P, "require_approval", lambda _root, stage: approvals.append(stage)
    )
    monkeypatch.setattr(
        signature, "validate_review", lambda _root, _project: {"base": "renders/base-v001.mp4"}
    )
    monkeypatch.setattr(signature, "current_input_hash", lambda _root: "c" * 64)
    monkeypatch.setattr(services.render.P, "stage_hash", lambda _root, _stage: "g" * 64)
    monkeypatch.setattr(graphics, "compose", compose)

    report = services.render.render_final(root, root / "renders" / "final-v001.mp4")

    assert approvals == ["stills", "graphics"]
    assert calls[0][1] == base
    assert report["delivery_ready"] is True
    assert report["graphics_approval_hash"] == "g" * 64
    sidecar = read_json(root / "renders" / "final-v001.json")
    assert sidecar["delivery_ready"] is True
    assert sidecar["input_hash"] == "c" * 64


def test_base_writes_the_report_and_leaves_the_titles_review_alone(tmp_path, monkeypatch):
    root = make_api_project(tmp_path)
    add_assets(root)
    stored = read_json(root / "project.json")
    stored["signature_required"] = True
    write_json(root / "project.json", stored)
    output = root / "renders" / "base-v001.mp4"
    calls = []

    monkeypatch.setattr(services.render.P, "require_approval", lambda *_args: None)
    monkeypatch.setattr(services.render, "_render", _fake_render(calls))
    monkeypatch.setattr(signature, "current_input_hash", lambda _root: "b" * 64)

    def no_review(*_args):
        raise AssertionError("a base must not prepare or replace the titles review")

    monkeypatch.setattr(signature, "prepare_review", no_review)
    monkeypatch.setattr(signature, "prepare_titles_review", no_review)

    report = services.render.render_base(root, output)

    assert report["delivery_ready"] is False
    assert "graphics_review" not in report
    sidecar = read_json(output.with_suffix(".json"))
    assert sidecar["input_hash"] == "b" * 64
    assert sidecar["delivery_ready"] is False


def test_every_render_path_receives_the_excerpt_audio(tmp_path, monkeypatch):
    root = make_api_project(tmp_path)
    add_assets(root)
    sentinel = root / "work" / "audio" / "excerpt-test.wav"
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_bytes(b"derived excerpt")
    calls = []

    def fake(project, shots, audio, output, workdir, **kwargs):
        calls.append(Path(audio))
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_bytes(b"fake movie")
        return {"renderer_revision": "revision-1", "input_hash": "b" * 64, "verified": True}

    monkeypatch.setattr(services.render, "_render", fake)
    monkeypatch.setattr(P, "render_audio", lambda root, project=None: sentinel)

    services.render.render_preview(root, root / "previews" / "excerpt-v001.mp4")
    assert calls == [sentinel]


def test_working_renders_use_jpeg_and_reuse_and_a_final_does_neither(tmp_path, monkeypatch):
    from mp3_to_videoclip.remotion import WORKING_CAPTURE

    calls = []
    root = tmp_path / "film"
    root.mkdir()
    project = SimpleNamespace(slug="film")
    monkeypatch.setattr(services.render.P, "require_approval", lambda *_a: None)
    monkeypatch.setattr(services.render.P, "load_project", lambda _r: project)
    monkeypatch.setattr(services.render.P, "resolved_assets", lambda _r: [])
    monkeypatch.setattr(services.render.P, "load_brand", lambda _r: None)
    monkeypatch.setattr(services.render.P, "render_audio", lambda _r, _p: tmp_path / "a.mp3")
    monkeypatch.setattr(services.render.P, "requires_signature", lambda _r, _p: False)
    monkeypatch.setattr(services.render, "_provenance", lambda *_a, **_k: {})
    monkeypatch.setattr(services.render, "_render", _fake_render(calls))
    services.render.render_base(root)
    services.render.render_final(root)
    assert calls[0]["capture"] == WORKING_CAPTURE and calls[0]["reuse_chunks"] is True
    assert "capture" not in calls[1] and "reuse_chunks" not in calls[1]
