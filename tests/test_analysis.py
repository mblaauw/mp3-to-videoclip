import wave

import numpy as np
import pytest

from mp3_to_videoclip.analysis import analyze


@pytest.mark.parametrize("silent", [True, False])
def test_short_and_silent_sources_are_finite_and_do_not_invent_meter(tmp_path, silent):
    sr = 22050
    y = np.zeros(sr * 2, dtype=np.int16)
    if not silent:
        for offset in range(0, len(y), sr // 2):
            y[offset : offset + 100] = 10000
    path = tmp_path / "audio.wav"
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sr)
        stream.writeframes(y.tobytes())
    result = analyze(path, 2)
    assert result["duration"] == 2
    assert result["sections"][0]["start"] == 0
    assert result["sections"][-1]["end"] == 2
    assert all(np.isfinite(row["energy"]) for row in result["energy_curve"])
    assert "downbeats" not in result and "time_signature" not in result
    if silent:
        assert result["estimated_tempo_bpm"] is None
