"""Shape and invariant tests for the deeper local analysis pass.

The signals here are synthesized with numpy and written as 16-bit PCM with the
stdlib :mod:`wave` module, so nothing depends on ffmpeg, a provider or a paid
call. They assert shape and invariants only: no artistic number is asserted,
because every measurement in :mod:`mp3_to_videoclip.deep_analysis` is relative to
the source and explicitly uncertain.
"""

import wave

import numpy as np
import pytest

from mp3_to_videoclip.deep_analysis import ANALYSIS_VERSION, AVAILABLE_DEPS, deep_analyze

SR = 22050
DURATION = 8.0
# A 2 Hz click train is a 120 BPM pulse; the tones give the chroma some content.
CLICK_INTERVAL_S = 0.5
TONES_HZ = (220.0, 277.18)


def _write_signal(path, *, seconds=DURATION, click_from=0.0, tones=TONES_HZ):
    """Mono 16-bit PCM: a low click train from ``click_from`` plus sustained tones."""
    count = int(SR * seconds)
    signal = np.zeros(count, dtype=np.float64)
    for frequency in tones:
        times = np.arange(count) / SR
        signal += 0.22 * np.sin(2 * np.pi * frequency * times)
    if click_from is not None:
        index = 0
        while click_from + index * CLICK_INTERVAL_S < seconds:
            start = int((click_from + index * CLICK_INTERVAL_S) * SR)
            length = min(300, count - start)
            if length > 0:
                window = np.hanning(length)
                signal[start : start + length] += (
                    0.9 * window * np.sin(2 * np.pi * 60.0 * np.arange(length) / SR)
                )
            index += 1
    pcm = np.clip(signal, -1.0, 1.0)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(SR)
        stream.writeframes((pcm * 32767.0).astype(np.int16).tobytes())
    return path


@pytest.fixture()
def result(tmp_path):
    return deep_analyze(_write_signal(tmp_path / "pulse.wav"), DURATION)


def test_reports_versioned_shape_and_the_backends_it_uses(result):
    assert result["analysis_version"] == ANALYSIS_VERSION == 3
    assert set(AVAILABLE_DEPS) == {"librosa", "numpy"}
    for key in (
        "duration",
        "refined_tempo",
        "downbeats",
        "bar_length_candidates",
        "downbeat_note",
        "key",
        "sections",
        "section_spans",
        "section_note",
        "bass_onsets",
        "vocal_band_onsets",
        "provenance",
        "warnings",
    ):
        assert key in result
    assert result["duration"] == DURATION


def test_refined_tempo_keeps_half_and_double_with_a_bounded_confidence(result):
    tempo = result["refined_tempo"]
    assert tempo["primary_bpm"] > 0
    assert tempo["half_bpm"] == pytest.approx(tempo["primary_bpm"] / 2, abs=0.05)
    assert tempo["double_bpm"] == pytest.approx(tempo["primary_bpm"] * 2, abs=0.05)
    assert 0.0 <= tempo["pulse_confidence"] <= 1.0
    assert isinstance(tempo["ambiguity"], str) and tempo["ambiguity"].strip()
    # The octave is never silently resolved: both readings are named in the note.
    assert "half" in tempo["ambiguity"] and "double" in tempo["ambiguity"]
    assert tempo["candidates"], "the octave candidates behind the estimate are reported"
    assert all(0.0 <= row["score"] <= 1.0 for row in tempo["candidates"])


def test_downbeats_are_ordered_in_range_and_bar_lengths_are_scored(result):
    downbeats = result["downbeats"]
    assert downbeats, "a click train should phase at least one candidate bar grid"
    times = [row["time"] for row in downbeats]
    assert times == sorted(times)
    assert all(0.0 <= time <= DURATION for time in times)
    assert all(0.0 <= row["strength"] <= 1.0 for row in downbeats)
    lengths = result["bar_length_candidates"]
    assert [row["beats_per_bar"] for row in lengths] == [2, 3, 4]
    assert all(row["score"] >= 0.0 for row in lengths)
    assert "candidate" in result["downbeat_note"]
    assert "verified" in result["downbeat_note"]


def test_key_reports_a_tonic_mode_and_a_visible_runner_up(result):
    key = result["key"]
    assert key["tonic"] in (
        "C",
        "C#",
        "D",
        "D#",
        "E",
        "F",
        "F#",
        "G",
        "G#",
        "A",
        "A#",
        "B",
    )
    assert key["mode"] in ("major", "minor")
    assert -1.0 <= key["best_correlation"] <= 1.0
    assert key["best_correlation"] >= key["runner_up"]["correlation"]
    assert key["runner_up"]["mode"] in ("major", "minor")
    assert key["margin"] == pytest.approx(
        key["best_correlation"] - key["runner_up"]["correlation"], abs=1e-6
    )
    assert len(key["chroma_share"]) == 12
    assert sum(key["chroma_share"]) == pytest.approx(1.0, abs=1e-3)
    assert "not" in key["note"] and "verified" in key["note"]


def test_sections_are_ordered_candidates_inside_the_source(tmp_path):
    path = _write_signal(tmp_path / "two-part.wav", click_from=4.0)
    result = deep_analyze(path, DURATION)
    sections = result["sections"]
    assert sections[0]["time"] == 0.0
    assert sections[0]["kind"] == "start_anchor"
    times = [row["time"] for row in sections]
    assert times == sorted(times)
    assert all(0.0 <= time <= DURATION for time in times)
    assert all(0.0 <= row["strength"] <= 1.0 for row in sections)
    assert all(row["reviewed"] is False for row in sections)
    spans = result["section_spans"]
    assert spans and spans[-1]["end"] == DURATION
    assert all(spans[index]["end"] == spans[index + 1]["start"] for index in range(len(spans) - 1))
    assert "candidate" in result["section_note"]


def test_band_onsets_are_ordered_inside_the_source(result):
    for key in ("bass_onsets", "vocal_band_onsets"):
        rows = result[key]
        assert len(rows) >= 4, f"{key} should find the click train entries"
        times = [row["time"] for row in rows]
        assert times == sorted(times)
        assert all(0.0 <= time < DURATION for time in times)
        assert all(0.0 <= row["strength"] <= 1.0 for row in rows)


def test_provenance_and_warnings_state_units_and_uncertainty(result):
    provenance = result["provenance"]
    assert provenance["sample_rate_hz"] == SR
    assert provenance["stft_n_fft"] and provenance["stft_hop_length"]
    assert provenance["kick_band_hz"] and provenance["bass_onset_band_hz"]
    assert provenance["vocal_onset_band_hz"]
    assert provenance["units"] and provenance["librosa_calls"]
    assert all(unit for unit in provenance["units"].values())
    assert result["warnings"]
    assert all(isinstance(warning, str) and warning for warning in result["warnings"])
    joined = " ".join(result["warnings"]).lower()
    assert "half/double" in joined and "unverified" in joined


def test_measurement_is_deterministic(tmp_path):
    path = _write_signal(tmp_path / "repeat.wav")
    assert deep_analyze(path, DURATION) == deep_analyze(path, DURATION)


def test_silence_invents_no_tempo_downbeat_key_or_onset(tmp_path):
    path = tmp_path / "silent.wav"
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(SR)
        stream.writeframes(np.zeros(int(SR * 2), dtype=np.int16).tobytes())
    result = deep_analyze(path, 2.0)
    assert result["analysis_version"] == 3
    assert result["refined_tempo"]["primary_bpm"] is None
    assert result["refined_tempo"]["pulse_confidence"] == 0.0
    assert result["downbeats"] == []
    assert result["key"]["tonic"] is None and result["key"]["runner_up"] is None
    assert result["bass_onsets"] == [] and result["vocal_band_onsets"] == []
    assert [row["score"] for row in result["bar_length_candidates"]] == [0.0, 0.0, 0.0]
    assert result["warnings"] and result["provenance"]
