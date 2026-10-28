"""Candidate planning/reporting uses fake local commands, never renderers."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


def load_candidates(monkeypatch):
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "candidate_fixture", scripts / "benchmark_render_candidates.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_candidate_suites_are_replicated_and_warmup_is_explicit(monkeypatch):
    module = load_candidates(monkeypatch)
    software = module.candidate_cases("software")
    assert software[0] == ("warmup", 2, None)
    assert [c for _, c, _ in software[1:]] == [1, 2, 3, 3, 2, 1]
    hardware = module.candidate_cases("hardware")
    assert len(hardware) == 3
    assert all(profile == "videotoolbox-20m" for _, _, profile in hardware[1:])
    assert len(module.candidate_cases("all")) == 9


def test_failed_hardware_experiments_keep_evidence_and_exit_unsuccessfully(tmp_path, monkeypatch):
    module = load_candidates(monkeypatch)
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    assets = baseline / "assets"
    assets.mkdir()
    (assets / "plate.png").write_bytes(b"synthetic fixture")
    chrome = tmp_path / "Chrome"
    chrome.write_text("fixture executable")
    chrome.chmod(0o700)
    module.save(
        baseline / "base-0-warm.request.json",
        {
            "frames": 288,
            "width": 1920,
            "height": 1080,
            "fps": 24,
            "kind": "base",
            "chrome": str(chrome),
            "assetRoot": str(assets),
        },
    )
    output = tmp_path / "evidence"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "benchmark",
            "--baseline-dir",
            str(baseline),
            "--output-dir",
            str(output),
            "--suite",
            "hardware",
            "--budget-seconds",
            "60",
        ],
    )

    def run(command, *, stdout, stderr, timeout):
        assert 0 < timeout <= 60
        if "--input-type=module" in command:
            stdout.write('{"capability_error":"Method not found"}')
            return
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(module, "run_owned", run)
    assert module.main() == 1
    report = json.loads((output / "candidates.json").read_text())
    assert report["status"] == "partial"
    assert len(report["runs"]) == 3
    assert all(row["status"] == "failed" for row in report["runs"])
    assert report["medians"] == {}
    assert len(list(output.glob("*.request.json"))) == 3


@pytest.mark.parametrize("chrome", [None, "", "relative-chrome", "/missing/Chrome"])
def test_candidates_refuse_implicit_browser_before_any_launch(tmp_path, monkeypatch, chrome):
    module = load_candidates(monkeypatch)
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    module.save(
        baseline / "base-0-warm.request.json",
        {
            "frames": 288,
            "width": 1920,
            "height": 1080,
            "fps": 24,
            "kind": "base",
            "chrome": chrome,
        },
    )
    output = tmp_path / "never-created"
    monkeypatch.setattr(
        sys, "argv", ["benchmark", "--baseline-dir", str(baseline), "--output-dir", str(output)]
    )
    monkeypatch.setattr(
        module, "run_owned", lambda *args, **kwargs: pytest.fail("browser launch attempted")
    )
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 2
    assert not output.exists()
