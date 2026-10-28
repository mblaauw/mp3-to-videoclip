"""Diagnostics are additive reports, never new renderer settings."""

from pathlib import Path

from mp3_to_videoclip import remotion
from mp3_to_videoclip.storage import write_json


def test_invoke_propagates_sidecar_without_changing_request(tmp_path, monkeypatch):
    engine = tmp_path / "engine"
    (engine / "node_modules/@remotion/renderer").mkdir(parents=True)
    monkeypatch.setattr(remotion, "ENGINE", engine)
    monkeypatch.setattr(remotion, "implementation_hash", lambda: "revision")
    output = tmp_path / "out.mp4"
    expected = {"diagnostics": {"encodedDoneIn": None, "renderedDoneIn": 123}}

    def run(argv, target, progress, frames):
        target.write_bytes(b"local-fake-output")
        write_json(Path(f"{target}.render.json"), expected)
        return "{}", ""

    monkeypatch.setattr(remotion, "_run_streaming", run)
    result = remotion.invoke("base", output, tmp_path, (1920, 1080), 24, 24, {"shots": []})
    assert result["renderer_report"] == expected
    assert result["invoke_seconds"] >= 0
    request = remotion.request("base", output, tmp_path, (1920, 1080), 24, 24, {})
    assert "diagnostics" not in request
    assert "concurrency" not in request
