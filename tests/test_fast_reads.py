"""Views read no source bytes, and the library's state is exact."""

from __future__ import annotations

from pathlib import Path

from api_support import api_client, make_api_project

from mp3_to_videoclip import production as P
from mp3_to_videoclip import storage
from mp3_to_videoclip.production import stage_state
from mp3_to_videoclip.storage import file_hash, file_hash_cached, read_json, write_json


def _count_source_reads(monkeypatch, root: Path) -> list[Path]:
    """Every whole-file hash of an MP3, however it is reached."""
    reads: list[Path] = []
    real = file_hash

    def counting(path):
        if Path(path).suffix == ".mp3":
            reads.append(Path(path))
        return real(path)

    monkeypatch.setattr(storage, "file_hash", counting)
    return reads


def test_a_cached_hash_reads_the_file_once_and_again_when_it_changes(tmp_path, monkeypatch):
    path = tmp_path / "a.mp3"
    path.write_bytes(b"one")
    reads = _count_source_reads(monkeypatch, tmp_path)
    first = file_hash_cached(path)
    assert file_hash_cached(path) == first
    assert len(reads) == 1
    path.write_bytes(b"other")
    assert file_hash_cached(path) != first
    assert len(reads) == 2


def test_a_library_listing_reads_no_source_bytes(tmp_path, monkeypatch):
    for name in ("one", "two", "three"):
        make_api_project(tmp_path, name)
    storage._HASHES.clear()
    with api_client(tmp_path) as client:
        assert len(client.get("/api/projects").json()) == 3
        reads = _count_source_reads(monkeypatch, tmp_path)
        # The state each film just computed holds, so nothing is hashed from here.
        assert len(client.get("/api/projects").json()) == 3
        assert client.get("/api/projects/one").status_code == 200
    assert reads == []


def test_a_replaced_source_is_still_refused_where_it_matters(tmp_path):
    root = make_api_project(tmp_path)
    P.load_project(root)
    source = root / P.load_project(root, verify_source=False).source
    source.write_bytes(source.read_bytes() + b"changed")
    try:
        P.load_project(root)
    except ValueError as exc:
        assert "source changed" in str(exc)
    else:
        raise AssertionError("a replaced source was accepted")


def test_a_missing_source_still_shows_as_a_problem_in_the_library(tmp_path):
    root = make_api_project(tmp_path)
    (root / P.load_project(root, verify_source=False).source).unlink()
    with api_client(tmp_path) as client:
        film = client.get("/api/projects").json()[0]
    assert "could not be loaded" in film["error"]


def _approve(root: Path, stage: str) -> dict:
    approvals_path = root / "work/approvals.json"
    approvals = read_json(approvals_path) if approvals_path.is_file() else {}
    approvals[stage] = {"hash": P.stage_hash(root, stage), "at": "2026-11-01T00:00:00+00:00"}
    write_json(approvals_path, approvals)
    return approvals


def test_a_touched_file_with_the_same_bytes_is_not_a_change(tmp_path):
    import os

    root = make_api_project(tmp_path)
    approvals = _approve(root, "brief")
    assert stage_state.stale(root, approvals)["brief"] is False
    later = (root / "brief.json").stat().st_mtime + 600
    os.utime(root / "brief.json", (later, later))
    assert stage_state.stale(root, approvals)["brief"] is False


def test_a_real_change_is_a_change(tmp_path):
    root = make_api_project(tmp_path)
    approvals = _approve(root, "brief")
    assert stage_state.stale(root, approvals)["brief"] is False
    brief = read_json(root / "brief.json")
    brief["direction"] = "something else entirely"
    write_json(root / "brief.json", brief)
    assert stage_state.stale(root, approvals)["brief"] is True


def test_the_answer_is_remembered_until_a_file_moves(tmp_path, monkeypatch):
    root = make_api_project(tmp_path)
    approvals = _approve(root, "brief")
    stage_state.stale(root, approvals)
    calls = []
    monkeypatch.setattr(stage_state, "stage_hash", lambda *a: calls.append(a) or "x")
    assert stage_state.stale(root, approvals)["brief"] is False
    assert calls == []
    write_json(root / "work/section-map.json", {"sections": None})
    stage_state.stale(root, approvals)
    assert calls


def test_opening_the_library_writes_nothing_into_a_film(tmp_path):
    root = make_api_project(tmp_path)
    before = sorted(str(path) for path in root.rglob("*") if path.is_file())
    with api_client(tmp_path) as client:
        client.get("/api/projects")
    assert sorted(str(path) for path in root.rglob("*") if path.is_file()) == before


def test_no_gate_reads_the_view(tmp_path):
    root = make_api_project(tmp_path)
    approvals = _approve(root, "brief")
    stage_state.stale(root, approvals)
    path = stage_state.state_path(root)
    write_json(path, {"fingerprint": stage_state.fingerprint(root), "stale": {"brief": True}})
    assert stage_state.stale(root, approvals)["brief"] is True
    assert P.stage_hash(root, "brief") == approvals["brief"]["hash"]
