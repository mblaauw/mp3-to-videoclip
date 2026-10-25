"""Preview/final service wiring; the renderer itself is faked, no browser or FFmpeg."""

from __future__ import annotations

from pathlib import Path

from api_support import add_assets, make_api_project

from mp3_to_videoclip import production as P
from mp3_to_videoclip import services
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
