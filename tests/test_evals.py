"""Eval harness: the invariant report catches what it claims to catch."""

from pathlib import Path

from mp3_to_videoclip import evals

ROOT = Path(__file__).resolve().parents[1]


def test_repository_passes_its_own_invariants():
    report = evals.run(ROOT)
    failed = [check for check in report["checks"] if not check["ok"]]
    assert report["ok"] is True, failed
    names = {check["name"] for check in report["checks"]}
    assert {"command-registry", "mcp-surface", "pages-offline", "loop-length"} <= names


def test_external_calls_are_detected(tmp_path):
    bad = tmp_path / "page.html"
    bad.write_text('<script src="https://cdn.example/x.js"></script>')
    good = tmp_path / "good.html"
    good.write_text("<html><body>ok</body></html>")
    result = evals.check_pages_offline([good, bad])
    assert result["ok"] is False and "https://" in result["detail"]
    assert evals.check_pages_offline([good])["ok"] is True


def test_sidecar_mismatch_is_detected(tmp_path):
    page = tmp_path / "p.html"
    page.write_text("<html></html>")
    (tmp_path / "p.json").write_text('{"html_sha256": "deadbeef"}')
    result = evals.check_sidecars([page])
    assert result["ok"] is False and "hash mismatch" in result["detail"]


def test_missing_sidecar_is_detected(tmp_path):
    page = tmp_path / "p.html"
    page.write_text("<html></html>")
    assert evals.check_sidecars([page])["ok"] is False


def test_loop_length_is_enforced(tmp_path):
    (tmp_path / "LOOP.md").write_text("\n".join(["line"] * 150))
    assert evals.check_loop_length(tmp_path)["ok"] is False
    (tmp_path / "LOOP.md").write_text("\n".join(["line"] * 100))
    assert evals.check_loop_length(tmp_path)["ok"] is True


def test_bar_claims_without_an_approved_grid_are_detected(tmp_path):
    project = tmp_path / "projects" / "one"
    (project / "work/dashboard").mkdir(parents=True)
    (project / "work/dashboard" / "board-v001.html").write_text("<th>Bars</th>")
    assert evals.check_no_bar_claims_without_grid(tmp_path)["ok"] is False
    (project / "work/music-grid.json").write_text('{"approved": true}')
    assert evals.check_no_bar_claims_without_grid(tmp_path)["ok"] is True


def test_unapproved_grid_still_forbids_bar_claims(tmp_path):
    project = tmp_path / "projects" / "one"
    (project / "work/dashboard").mkdir(parents=True)
    (project / "work/dashboard" / "board-v001.html").write_text("bar 12")
    (project / "work/music-grid.json").write_text('{"approved": false}')
    assert evals.check_no_bar_claims_without_grid(tmp_path)["ok"] is False
