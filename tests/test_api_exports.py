"""Export provenance without rendering or modifying a real production."""

import pytest
from api_support import add_assets, api_client, make_api_project

from mp3_to_videoclip import graphics, services, signature
from mp3_to_videoclip import production as P
from mp3_to_videoclip.domain import exports
from mp3_to_videoclip.storage import file_hash, read_json, read_snapshot, write_json


@pytest.mark.parametrize(
    "case,classification,ready",
    [
        ("base", "base", False),
        ("preview", "preview", False),
        ("final", "final", True),
        ("missing", "unknown", False),
        ("corrupt", "unknown", False),
        ("mismatch", "unknown", False),
        ("content", "unknown", False),
        ("input", "final", False),
        ("graphics", "final", False),
    ],
)
def test_export_reports(tmp_path, monkeypatch, case, classification, ready):
    root = make_api_project(tmp_path)
    monkeypatch.setattr(exports, "_current_input_hash", lambda root: "current")
    movie = root / "renders/production-final-v001.mp4"
    movie.parent.mkdir(exist_ok=True)
    movie.write_bytes(b"movie")
    report = {
        "output": "/portable/copy/" + movie.name,
        "verified": True,
        "delivery_ready": case not in ("base", "preview"),
        "input_hash": "stale" if case == "input" else "current",
        "final_output_sha256": file_hash(movie),
    }
    if case == "preview":
        report["render_kind"] = "preview"
    if case == "mismatch":
        report["output"] = "another.mp4"
    if case == "content":
        report["final_output_sha256"] = "bad"
    if case == "graphics":
        report["graphics_approval_hash"] = "old"
        write_json(root / "work/approvals.json", {"graphics": {"hash": "new"}})
        monkeypatch.setattr(P, "stage_hash", lambda root, stage: "current-graphics")
    if case != "missing":
        write_json(movie.with_suffix(".json"), report)
    if case == "corrupt":
        movie.with_suffix(".json").write_text("{broken")
    with api_client(tmp_path) as client:
        response = client.get("/api/projects/production/exports")
        assert response.status_code == 200
        value = response.json()
        assert value["exports"] == [movie.name]
        assert value["previews"] == []
        item = value["files"][0]
        assert item["classification"] == classification
        assert item["delivery_ready"] is ready
        assert client.get(f"/api/projects/production/film/renders/{movie.name}").status_code == 200


def test_metadata_staleness(tmp_path, monkeypatch):
    root = make_api_project(tmp_path)
    monkeypatch.setattr(exports, "_current_input_hash", lambda root: "current")
    movie = root / "renders/production-v001.mp4"
    movie.parent.mkdir(exist_ok=True)
    movie.write_bytes(b"movie")
    write_json(
        movie.with_suffix(".json"),
        {
            "output": str(movie),
            "render_kind": "final",
            "verified": True,
            "delivery_ready": True,
            "output_sha256": file_hash(movie),
            "input_hash": "current",
            "input_metadata_hash": exports.input_metadata_hash(root),
        },
    )
    write_json(root / "work/edit.json", {"changed": True})
    with api_client(tmp_path) as client:
        item = client.get("/api/projects/production/exports").json()["files"][0]
    assert item["current"] is False
    assert item["delivery_ready"] is False


def test_metadata_tracks_root_brand_but_not_budget(tmp_path):
    root = make_api_project(tmp_path)
    before = exports.input_metadata_hash(root)
    project = read_json(root / "project.json")
    project["budget"] = {"cap_usd": 999, "history": ["topup"]}
    write_json(root / "project.json", project)
    assert exports.input_metadata_hash(root) == before
    write_json(root / "brand.json", {"name": "Changed brand"})
    assert exports.input_metadata_hash(root) != before


def test_selected_bytes_are_current_not_saved_approval(tmp_path):
    root = make_api_project(tmp_path)
    add_assets(root)
    current = signature.current_input_hash(root)
    write_json(root / "work/approvals.json", {"stills": {"hash": "saved"}})
    movie = root / "renders/film.mp4"
    movie.parent.mkdir(exist_ok=True)
    movie.write_bytes(b"movie")
    write_json(
        movie.with_suffix(".json"),
        {
            "output": str(movie),
            "render_kind": "final",
            "verified": True,
            "delivery_ready": True,
            "input_hash": current,
            "output_sha256": file_hash(movie),
        },
    )
    with api_client(tmp_path) as client:
        assert client.get("/api/projects/production/exports").json()["files"][0]["delivery_ready"]
        selected = next(iter(read_json(root / "work/assets.json").values()))["versions"][0]["path"]
        (root / selected).write_bytes(b"changed selected bytes")
        assert not client.get("/api/projects/production/exports").json()["files"][0][
            "delivery_ready"
        ]


@pytest.mark.parametrize("composed", [False, True])
def test_render_captures_old_provenance_and_rejects_mid_render_change(
    tmp_path, monkeypatch, composed
):
    root = make_api_project(tmp_path)
    add_assets(root)
    project = read_json(root / "project.json")
    project["signature_required"] = composed
    write_json(root / "project.json", project)
    monkeypatch.setattr(P, "require_approval", lambda *args: None)
    monkeypatch.setattr(signature, "current_input_hash", lambda root: "before-input")
    graphics_hash = ["before-graphics"]
    monkeypatch.setattr(P, "stage_hash", lambda root, stage: graphics_hash[0])
    old_metadata = exports.input_metadata_hash(root)
    base = root / "renders/base.mp4"
    base.parent.mkdir(exist_ok=True)
    base.write_bytes(b"reviewed base")
    monkeypatch.setattr(signature, "validate_review", lambda *args: {"base": "renders/base.mp4"})

    def change(output):
        # Rendering must not run under the snapshot's state lock/cache.
        from mp3_to_videoclip.storage import _read_cache

        assert _read_cache() is None
        output.parent.mkdir(exist_ok=True)
        output.write_bytes(b"old pixels")
        if composed:
            graphics_hash[0] = "after-graphics"
        else:
            write_json(root / "work/edit.json", {"changed-during-render": True})
        return {"output": str(output), "verified": True}

    monkeypatch.setattr(
        services.render,
        "_render",
        lambda project, shots, audio, output, *args, **kwargs: change(output),
    )
    monkeypatch.setattr(graphics, "compose", lambda root, base, output: change(output))
    output = root / "renders/final.mp4"
    report = services.render.render_final(root, output)
    assert output.read_bytes() == b"old pixels"
    assert report["input_metadata_hash"] == old_metadata
    assert report["input_hash"] == "before-input"
    if composed:
        assert report["graphics_approval_hash"] == "before-graphics"
    assert report["current"] is False
    assert report["delivery_ready"] is False
    with read_snapshot(root):
        assert exports.describe(root, "renders", output.name)["delivery_ready"] is False
