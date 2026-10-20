"""Local measurements, deliberately not automatic lyrical/creative interpretation."""

from pathlib import Path

import librosa
import numpy as np

# Bump when the measured fields below change shape or meaning.
ANALYSIS_VERSION = 2
_N_FFT = 2048
_HOP = 512
_FINE_WINDOW_S = 0.5
_SUMMARY_WINDOW_S = 8.0
_PULSE_WINDOW_S = 24.0
_NOVELTY_HALF_WINDOW_S = 4.0
_NOVELTY_MIN_SEPARATION_S = 6.0
_NOVELTY_STEP_S = 2.0
# Lag search range for local pulse candidates (seconds) -> 50-200 BPM.
_PULSE_LAG_RANGE_S = (0.30, 1.20)
_LOW_BASS_HZ = (35.0, 150.0)
_HIGH_HZ = 4000.0
_EPS = 1e-9


def _finite_mean(values) -> float:
    if values.size == 0:
        return 0.0
    clean = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
    return float(clean.mean())


def _window_spans(duration: float, window_s: float, hop_s: float):
    spans = []
    start = 0.0
    while start < duration - _EPS:
        spans.append((start, min(start + window_s, duration)))
        start += hop_s
    return spans


def _frame_slice(times, start: float, end: float):
    return int(np.searchsorted(times, start, "left")), int(np.searchsorted(times, end, "left"))


def _pulse_record(onset, times, sr: int, start: float, end: float):
    i0, i1 = _frame_slice(times, start, end)
    segment = onset[i0:i1]
    if segment.size < 8:
        return None
    segment = segment - float(segment.mean())
    if not np.any(segment):
        return None
    correlation = np.correlate(segment, segment, mode="full")[segment.size - 1 :]
    if correlation[0] <= _EPS:
        return None
    correlation = correlation / correlation[0]
    lag_min = max(1, int(round(_PULSE_LAG_RANGE_S[0] * sr / _HOP)))
    lag_max = min(correlation.size - 2, int(round(_PULSE_LAG_RANGE_S[1] * sr / _HOP)))
    if lag_max <= lag_min:
        return None
    peak = lag_min + int(np.argmax(correlation[lag_min : lag_max + 1]))
    offset = 0.0
    if 0 < peak < correlation.size - 1:
        left, middle, right = (float(correlation[peak + d]) for d in (-1, 0, 1))
        denominator = left - 2 * middle + right
        if abs(denominator) > _EPS:
            offset = float(np.clip(0.5 * (left - right) / denominator, -1.0, 1.0))
    lag_frames = peak + offset
    period = lag_frames * _HOP / sr
    if lag_frames <= 0 or period <= 0:
        return None
    primary = 60.0 / period
    return {
        "start": round(start, 3),
        "end": end,
        "period_s": round(period, 4),
        "primary_bpm": round(primary, 2),
        "half_bpm": round(primary / 2.0, 2),
        "double_bpm": round(primary * 2.0, 2),
        "confidence": round(float(np.clip(correlation[peak], 0.0, 1.0)), 3),
    }


def _candidate_changes(times, arrays, duration: float):
    if duration < 2 * _NOVELTY_HALF_WINDOW_S or times.size < 8:
        return []
    rows = np.vstack(
        [
            arrays["level_db"],
            arrays["low_share"],
            arrays["high_share"],
            np.log1p(arrays["centroid"]),
        ]
    )
    scaled = (rows - rows.mean(axis=1, keepdims=True)) / np.maximum(
        rows.std(axis=1, keepdims=True), _EPS
    )
    scored = []
    for t in np.arange(
        _NOVELTY_HALF_WINDOW_S,
        duration - _NOVELTY_HALF_WINDOW_S + _EPS,
        _NOVELTY_STEP_S,
    ):
        a0, a1 = _frame_slice(times, t - _NOVELTY_HALF_WINDOW_S, t)
        b0, b1 = _frame_slice(times, t, t + _NOVELTY_HALF_WINDOW_S)
        if a1 <= a0 or b1 <= b0:
            continue
        before, after = scaled[:, a0:a1].mean(axis=1), scaled[:, b0:b1].mean(axis=1)
        change = float(np.linalg.norm(after - before) / np.sqrt(scaled.shape[0]))
        level_before = _finite_mean(arrays["level_db"][a0:a1])
        level_after = _finite_mean(arrays["level_db"][b0:b1])
        if change < 1e-6 and abs(level_after - level_before) < 0.05:
            continue
        scored.append(
            {
                "time": round(float(t), 3),
                "spectral_change": round(change, 4),
                "level_db_before": round(level_before, 2),
                "level_db_after": round(level_after, 2),
                "delta_level_db": round(level_after - level_before, 2),
                "low_bass_share_before": round(_finite_mean(arrays["low_share"][a0:a1]), 4),
                "low_bass_share_after": round(_finite_mean(arrays["low_share"][b0:b1]), 4),
                "high_share_before": round(_finite_mean(arrays["high_share"][a0:a1]), 4),
                "high_share_after": round(_finite_mean(arrays["high_share"][b0:b1]), 4),
                "reviewed": False,
            }
        )
    kept = []
    for item in sorted(scored, key=lambda row: -row["spectral_change"]):
        if all(abs(item["time"] - other["time"]) >= _NOVELTY_MIN_SEPARATION_S for other in kept):
            kept.append(item)
    limit = min(10, max(1, int(round(duration / 25.0))))
    return sorted(
        sorted(kept, key=lambda row: -row["spectral_change"])[:limit],
        key=lambda row: row["time"],
    )


def _measure(y, sr: int, duration: float) -> dict:
    """Windowed level/band/onset measurements from an already-decoded mono signal."""
    magnitude = np.abs(librosa.stft(y, n_fft=_N_FFT, hop_length=_HOP))
    frequencies = librosa.fft_frequencies(sr=sr, n_fft=_N_FFT)
    low_band = magnitude[(frequencies >= _LOW_BASS_HZ[0]) & (frequencies < _LOW_BASS_HZ[1])]
    high_band = magnitude[frequencies >= _HIGH_HZ]
    # Band shares via einsum avoid materialising a full power spectrogram.
    total = np.maximum(np.einsum("ij,ij->j", magnitude, magnitude), _EPS)
    low_share = np.einsum("ij,ij->j", low_band, low_band) / total
    high_share = np.einsum("ij,ij->j", high_band, high_band) / total
    centroid = librosa.feature.spectral_centroid(S=magnitude, sr=sr)[0]
    rms = librosa.feature.rms(y=y, hop_length=_HOP)[0]
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=_HOP)
    count = min(len(rms), magnitude.shape[1], len(centroid), len(onset))
    times = librosa.frames_to_time(np.arange(count), sr=sr, hop_length=_HOP)
    rms = np.nan_to_num(rms[:count], nan=0.0, posinf=0.0, neginf=0.0)
    peak = max(float(rms.max()), _EPS)
    arrays = {
        "rms_db": 20.0 * np.log10(np.maximum(rms, _EPS)),
        "level_db": 20.0 * np.log10(np.maximum(rms, _EPS) / peak),
        "low_share": np.nan_to_num(low_share[:count]),
        "high_share": np.nan_to_num(high_share[:count]),
        "centroid": np.nan_to_num(centroid[:count], nan=0.0),
        "onset": np.nan_to_num(onset[:count], nan=0.0),
    }
    onset_frames = librosa.onset.onset_detect(onset_envelope=onset[:count], sr=sr, hop_length=_HOP)
    onset_times = librosa.frames_to_time(onset_frames, sr=sr, hop_length=_HOP)
    onset_times = onset_times[(onset_times >= 0) & (onset_times < duration + _EPS)]

    fine_windows = []
    for start, end in _window_spans(duration, _FINE_WINDOW_S, _FINE_WINDOW_S):
        i0, i1 = _frame_slice(times, start, end)
        if i1 <= i0:
            continue
        o0, o1 = _frame_slice(onset_times, start, end)
        span = max(end - start, _EPS)
        fine_windows.append(
            {
                "time": round(start, 3),
                "end": end,
                "rms_db": round(_finite_mean(arrays["rms_db"][i0:i1]), 2),
                "level_db": round(_finite_mean(arrays["level_db"][i0:i1]), 2),
                "low_bass_share": round(_finite_mean(arrays["low_share"][i0:i1]), 4),
                "high_share": round(_finite_mean(arrays["high_share"][i0:i1]), 4),
                "spectral_centroid_hz": round(_finite_mean(arrays["centroid"][i0:i1]), 1),
                "onset_activity": round(_finite_mean(arrays["onset"][i0:i1]), 4),
                "onset_density_per_s": round((o1 - o0) / span, 3),
            }
        )

    summary_windows = []
    for start, end in _window_spans(duration, _SUMMARY_WINDOW_S, _SUMMARY_WINDOW_S):
        i0, i1 = _frame_slice(times, start, end)
        if i1 <= i0:
            continue
        o0, o1 = _frame_slice(onset_times, start, end)
        levels = arrays["level_db"][i0:i1]
        summary_windows.append(
            {
                "start": round(start, 3),
                "end": end,
                "level_db_mean": round(_finite_mean(levels), 2),
                "level_db_min": round(float(np.nan_to_num(levels).min()), 2),
                "level_db_max": round(float(np.nan_to_num(levels).max()), 2),
                "rms_db_mean": round(_finite_mean(arrays["rms_db"][i0:i1]), 2),
                "low_bass_share_mean": round(_finite_mean(arrays["low_share"][i0:i1]), 4),
                "high_share_mean": round(_finite_mean(arrays["high_share"][i0:i1]), 4),
                "spectral_centroid_hz_mean": round(_finite_mean(arrays["centroid"][i0:i1]), 1),
                "onset_activity_mean": round(_finite_mean(arrays["onset"][i0:i1]), 4),
                "onset_density_per_s": round((o1 - o0) / max(end - start, _EPS), 3),
            }
        )

    pulse_candidates = []
    for start, end in _window_spans(duration, _PULSE_WINDOW_S, _PULSE_WINDOW_S):
        if end - start < 2.0:
            continue
        record = _pulse_record(arrays["onset"], times, sr, start, end)
        if record is not None:
            pulse_candidates.append(record)
    return {
        "fine_windows": fine_windows,
        "summary_windows": summary_windows,
        "candidate_changes": _candidate_changes(times, arrays, duration),
        "pulse_candidates": pulse_candidates,
    }


def _provenance(sr: int) -> dict:
    return {
        "analysis_version": ANALYSIS_VERSION,
        "decoding": "librosa.load(sr=22050, mono=True); decoded once and reused for every measurement",
        "sample_rate_hz": int(sr),
        "stft_n_fft": _N_FFT,
        "stft_hop_length": _HOP,
        "fine_window_s": _FINE_WINDOW_S,
        "summary_window_s": _SUMMARY_WINDOW_S,
        "pulse_window_s": _PULSE_WINDOW_S,
        "novelty_half_window_s": _NOVELTY_HALF_WINDOW_S,
        "novelty_min_separation_s": _NOVELTY_MIN_SEPARATION_S,
        "low_bass_hz": [_LOW_BASS_HZ[0], _LOW_BASS_HZ[1]],
        "high_hz": _HIGH_HZ,
        "units": {
            "time": "seconds from source start",
            "rms_db": "dBFS of the decoded mono signal",
            "level_db": "dB relative to the loudest measured frame in this track (0 = that peak)",
            "low_bass_share": "fraction of window STFT power in 35-150 Hz",
            "high_share": "fraction of window STFT power at or above 4000 Hz",
            "spectral_centroid_hz": "power-weighted mean frequency (Hz)",
            "onset_activity": "mean onset-strength envelope value (dimensionless)",
            "onset_density_per_s": "detected onset events per second",
            "bpm": "beats per minute from local onset autocorrelation; half/double both retained",
        },
        "notes": [
            "Measurements are relative to this track; the audio was not normalized.",
            "No genre, instrument, mood, meter, downbeat or section label is inferred.",
        ],
    }


def _empty_result(duration: float) -> dict:
    return {
        "duration": duration,
        "analysis_version": ANALYSIS_VERSION,
        "estimated_tempo_bpm": None,
        "beats": [],
        "energy_curve": [],
        "sections": [],
        "fine_windows": [],
        "summary_windows": [],
        "candidate_changes": [],
        "pulse_candidates": [],
        "provenance": _provenance(22050),
        "warnings": ["Source decoded to zero samples; no measurements were possible."],
    }


def analyze(source: Path, duration: float) -> dict:
    y, sr = librosa.load(source, sr=22050, mono=True)
    if y.size == 0 or not np.isfinite(duration) or duration <= 0:
        return _empty_result(duration)
    hop = 512
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    tempo, frames = librosa.beat.beat_track(onset_envelope=onset, sr=sr, hop_length=hop)
    beats = librosa.frames_to_time(frames, sr=sr, hop_length=hop)
    beats = beats[(beats >= 0) & (beats < duration)]
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)
    lo, hi = np.percentile(rms, [5, 95])
    energy = np.clip((rms - lo) / max(float(hi - lo), 1e-9), 0, 1)
    # Summarize per second, rather than assume a time signature or beat phase.
    curve = []
    for start in np.arange(0, duration, 1):
        values = energy[(times >= start) & (times < start + 1)]
        curve.append(
            {"time": round(float(start), 3), "energy": float(values.mean()) if len(values) else 0}
        )
    boundaries = [0.0, duration]
    if len(frames) >= 8 and hi > 1e-6:
        chroma = librosa.feature.chroma_stft(y=y, sr=sr, hop_length=hop)
        mfcc = librosa.feature.mfcc(y=y, sr=sr, hop_length=hop, n_mfcc=13)
        features = librosa.util.normalize(
            np.vstack([librosa.util.sync(chroma, frames), librosa.util.sync(mfcc, frames)]), axis=1
        )
        count = min(max(2, round(duration / 25)), len(frames), features.shape[1])
        changes = librosa.segment.agglomerative(features, count)
        boundaries = sorted(
            {0.0, duration}
            | {float(beats[b]) for b in changes if 0 < b < len(beats) and 0 < beats[b] < duration}
        )
    sections = []
    for start, end in zip(boundaries, boundaries[1:]):
        values = energy[(times >= start) & (times < end)]
        sections.append(
            {
                "start": round(start, 3),
                "end": min(duration, round(end, 3)),
                "energy": float(values.mean()) if len(values) else 0,
                "label": "unreviewed",
            }
        )
    bpm = float(np.atleast_1d(tempo)[0])
    measured = _measure(y, sr, duration)
    return {
        "duration": duration,
        "analysis_version": ANALYSIS_VERSION,
        "estimated_tempo_bpm": round(bpm, 2) if bpm > 0 and len(beats) else None,
        "beats": [round(float(t), 3) for t in beats],
        "energy_curve": curve,
        "sections": sections,
        "fine_windows": measured["fine_windows"],
        "summary_windows": measured["summary_windows"],
        "candidate_changes": measured["candidate_changes"],
        "pulse_candidates": measured["pulse_candidates"],
        "provenance": _provenance(sr),
        "warnings": [
            "Beat/tempo and section boundaries are estimates requiring review.",
            "No time signature, downbeat phase, verse/chorus, language or genre was inferred.",
            "Tempo may be half/double the perceived pulse; energy is relative within this track.",
            "Band shares, centroids and pulse candidates are relative measurements, not genre, "
            "instrument or mood labels; pulse candidates retain half/double ambiguity.",
        ],
    }
