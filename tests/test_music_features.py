import wave

import numpy as np

from mp3_to_videoclip.analysis import ANALYSIS_VERSION, analyze

SR = 22050


def _write(path, samples):
    ints = np.clip(np.round(samples * 32767), -32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(SR)
        stream.writeframes(ints.tobytes())
    return path


def _tone(freq, duration, amplitude=0.3):
    t = np.arange(int(SR * duration)) / SR
    return amplitude * np.sin(2 * np.pi * freq * t)


def _click_train(duration, step_s, amplitude=0.9, width=40):
    samples = np.zeros(int(SR * duration))
    for offset in range(0, samples.size, int(SR * step_s)):
        samples[offset : offset + width] = amplitude
    return samples


def test_silence_and_short_sources_are_bounded_and_finite(tmp_path):
    result = analyze(_write(tmp_path / "silent.wav", np.zeros(SR * 2)), 2)
    assert result["analysis_version"] == ANALYSIS_VERSION
    assert result["candidate_changes"] == []
    assert result["pulse_candidates"] == []
    assert result["fine_windows"]
    assert "units" in result["provenance"] and "level_db" in result["provenance"]["units"]
    for row in result["fine_windows"]:
        assert row["time"] < row["end"] <= 2
        for key in (
            "rms_db",
            "level_db",
            "low_bass_share",
            "high_share",
            "spectral_centroid_hz",
            "onset_activity",
            "onset_density_per_s",
        ):
            assert np.isfinite(row[key]), (key, row)
        assert row["low_bass_share"] == 0 and row["high_share"] == 0
        assert row["onset_density_per_s"] == 0

    # A zero-length source is guarded rather than crashing on empty frames.
    empty = analyze(_write(tmp_path / "empty.wav", np.zeros(0)), 0)
    assert empty["fine_windows"] == [] and empty["estimated_tempo_bpm"] is None


def test_known_pulse_and_spectral_change_are_detected(tmp_path):
    low = _tone(100, 6, amplitude=0.2) + _click_train(6, 0.5)
    rng = np.random.default_rng(0)
    bright = 0.2 * rng.standard_normal(SR * 6) + _click_train(6, 0.5)
    result = analyze(_write(tmp_path / "pulses.wav", np.concatenate([low, bright])), 12.0)

    assert result["candidate_changes"], "a level/spectral change should be reported"
    near_transition = [c for c in result["candidate_changes"] if 4 <= c["time"] <= 8]
    assert near_transition, result["candidate_changes"]
    assert any(c["high_share_after"] > c["high_share_before"] for c in near_transition)

    # Clicks land every 0.5 s (120 BPM); the half/double readings stay available.
    bpms = {
        round(value, 1)
        for row in result["pulse_candidates"]
        for value in (row["primary_bpm"], row["half_bpm"], row["double_bpm"])
    }
    assert bpms, "expected a local pulse candidate"
    assert any(abs(bpm - 120) < 6 for bpm in bpms), sorted(bpms)


def test_low_and_bright_bands_are_measured_separately(tmp_path):
    low = analyze(_write(tmp_path / "low.wav", _tone(80, 4, amplitude=0.5)), 4.0)
    high = analyze(_write(tmp_path / "high.wav", _tone(8000, 4, amplitude=0.5)), 4.0)
    low_row = max(low["fine_windows"], key=lambda row: row["level_db"])
    high_row = max(high["fine_windows"], key=lambda row: row["level_db"])

    assert low_row["low_bass_share"] > 0.8 and low_row["high_share"] < 0.05
    assert high_row["high_share"] > 0.8 and high_row["low_bass_share"] < 0.05
    assert high_row["spectral_centroid_hz"] > low_row["spectral_centroid_hz"]


def test_windows_are_time_ordered_and_within_source_bounds(tmp_path):
    signal = np.concatenate([_tone(200, 5, amplitude=0.3), _tone(400, 5, amplitude=0.3)])
    duration = 10.0
    result = analyze(_write(tmp_path / "ordered.wav", signal), duration)

    for key in ("fine_windows", "summary_windows", "candidate_changes", "pulse_candidates"):
        starts = [row.get("time", row.get("start")) for row in result[key]]
        assert starts == sorted(starts), key
        for row in result[key]:
            assert 0 <= row.get("time", row.get("start"))
            assert row.get("end", row.get("time")) <= duration
    assert result["beats"] == sorted(result["beats"])


def test_energy_and_onset_density_are_separate_fields(tmp_path):
    loud = _tone(200, 2, amplitude=0.8)
    quiet = _click_train(2, 0.125, amplitude=0.1, width=20)
    result = analyze(_write(tmp_path / "energy.wav", np.concatenate([loud, quiet])), 4.0)

    loud_window = max(result["fine_windows"], key=lambda row: row["level_db"])
    quiet_window = min(result["fine_windows"], key=lambda row: row["level_db"])
    assert "level_db" in loud_window and "onset_density_per_s" in quiet_window
    assert loud_window["level_db"] > quiet_window["level_db"]
    assert quiet_window["onset_density_per_s"] > loud_window["onset_density_per_s"]
