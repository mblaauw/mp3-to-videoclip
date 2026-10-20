"""Deeper local music measurements, still relative to this track and still unreviewed.

Same discipline as :mod:`mp3_to_videoclip.analysis`, only finer: every number here
is a measurement of *this* recording and nothing else.

* Tempo, downbeat phase, key and section boundaries stay explicitly uncertain.
  Tempo keeps its half/double ambiguity, the downbeat phase is a candidate
  derived from a low-frequency onset envelope, key is a Krumhansl-Schmuckler
  correlation candidate with its runner-up reported next to it, and sections are
  novelty candidates.
* No genre, instrument, mood, language, meter, time signature, verse/chorus or
  lyric claim is produced. Nothing here approves an artifact.
* Only :mod:`librosa`, :mod:`numpy` and the standard library are used: no
  network, no provider, no heavy source-separation backend, no paid call, no
  file write and no RNG. The caller decodes once and passes the decoded duration
  in, exactly as :func:`analysis.analyze` does.
"""

from pathlib import Path

import librosa
import numpy as np

# Bump when the measured fields below change shape or meaning.
ANALYSIS_VERSION = 3

# This module deliberately never imports a heavy separation/transcription backend,
# so it reports the acoustic backends it actually computes with.
AVAILABLE_DEPS = {
    "librosa": "STFT, band flux, onset detection, tempogram, PLP pulse, chroma, self-similarity",
    "numpy": "array maths, correlations and deterministic peak picking",
}

_DECODE_SR = 22050
_N_FFT = 2048
_HOP = 512
_EPS = 1e-9

# Tempo search range kept wide enough to hold both readings of an octave pair.
_TEMPO_RANGE_BPM = (50.0, 210.0)
_TEMPO_WINDOW_S = 8.0
_PLP_TEMPO_RANGE_BPM = (30.0, 300.0)
_PLP_MIN_PEAKS = 4
# librosa's own PLP window, halved when the source is too short to hold it.
_PLP_WINDOW_FRAMES = 384
# Onsets used for edit binding: a little above the default threshold, with a
# minimum gap, so a quiet band does not report one onset per analysis frame.
_ONSET_DELTA = 0.08
_ONSET_MIN_GAP_FRAMES = 4
# A rival octave counts as competing when it is within this fraction of a bpm.
_OCTAVE_TOLERANCE = 0.03
_PLP_AGREEMENT_TOLERANCE = 0.05
_MIN_TEMPO_FRAMES = 64

# Low band for candidate bar starts (kick/bass energy), and the two onset bands.
_KICK_HZ = (35.0, 150.0)
_BASS_ONSET_HZ = (30.0, 150.0)
_VOCAL_ONSET_HZ = (300.0, 3400.0)

# Self-similarity novelty: 1 s coarse frames, 3 s checkerboard half width.
_SECTION_HOP_S = 1.0
_SECTION_HALF_WINDOW_S = 3.0
_SECTION_MIN_SEPARATION_S = 6.0
_SECTION_STRENGTH_FLOOR = 0.25

_BEATS_PER_BAR_CANDIDATES = (2, 3, 4)

_PITCH_CLASSES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
# Krumhansl & Kessler (1982) key profiles, used as a fixed reference rotation.
_KS_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_KS_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def _finite_mean(values) -> float:
    if values.size == 0:
        return 0.0
    clean = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
    return float(clean.mean())


def _frame_slice(times, start: float, end: float):
    return int(np.searchsorted(times, start, "left")), int(np.searchsorted(times, end, "left"))


def _pearson(left, right) -> float:
    """Deterministic Pearson correlation; a flat vector scores 0.0, never NaN."""
    a = np.nan_to_num(np.asarray(left, dtype=float))
    b = np.nan_to_num(np.asarray(right, dtype=float))
    a = a - a.mean()
    b = b - b.mean()
    denominator = float(np.sqrt((a * a).sum() * (b * b).sum()))
    if denominator <= _EPS:
        return 0.0
    return float(np.clip((a * b).sum() / denominator, -1.0, 1.0))


# --------------------------------------------------------------------------- #
# tempo: tempogram profile, PLP cross-check, explicit octave ambiguity
# --------------------------------------------------------------------------- #
def _tempo_profile(onset, sr: int, hop: int, win_length: int):
    """Onset-weighted global tempo profile plus its (hyperbolic) bpm axis."""
    tempogram = np.nan_to_num(
        librosa.feature.tempogram(
            onset_envelope=onset, sr=sr, hop_length=hop, win_length=win_length
        )
    )
    axis = librosa.tempo_frequencies(tempogram.shape[0], hop_length=hop, sr=sr)
    weights = np.nan_to_num(onset[: tempogram.shape[1]])
    total = float(weights.sum())
    if total <= _EPS:
        weights = np.full(tempogram.shape[1], 1.0 / max(tempogram.shape[1], 1))
    else:
        weights = weights / total
    return tempogram @ weights, axis


def _profile_value(profile, axis, bpm: float) -> float:
    """Strongest profile value within :data:`_OCTAVE_TOLERANCE` of ``bpm``."""
    if not np.isfinite(bpm) or bpm <= 0:
        return 0.0
    window = (axis >= bpm * (1.0 - _OCTAVE_TOLERANCE)) & (axis <= bpm * (1.0 + _OCTAVE_TOLERANCE))
    window &= np.isfinite(axis)
    if not np.any(window):
        return 0.0
    return float(np.max(profile[window]))


def _refine_peak_bpm(profile, axis, index: int, sr: int, hop: int) -> float:
    """Parabolic refinement in lag space; the tempogram bpm axis is hyperbolic."""
    if index <= 0 or index >= profile.size - 1:
        return float(axis[index])
    left, middle, right = (float(profile[index + d]) for d in (-1, 0, 1))
    denominator = left - 2 * middle + right
    offset = 0.0
    if abs(denominator) > _EPS:
        offset = float(np.clip(0.5 * (left - right) / denominator, -1.0, 1.0))
    lag_frames = index + offset
    if lag_frames <= _EPS:
        return float(axis[index])
    return 60.0 * sr / (hop * lag_frames)


def _plp_pulse_bpm(onset, sr: int, hop: int):
    """Predominant-local-pulse cross-check from the same onset envelope."""
    curve = np.nan_to_num(
        librosa.beat.plp(
            onset_envelope=onset,
            sr=sr,
            hop_length=hop,
            win_length=min(_PLP_WINDOW_FRAMES, max(8, onset.size // 2)),
            tempo_min=_PLP_TEMPO_RANGE_BPM[0],
            tempo_max=_PLP_TEMPO_RANGE_BPM[1],
        )
    )
    if curve.size < 3:
        return None
    threshold = float(curve.mean())
    peaks = np.flatnonzero(
        (curve[1:-1] > curve[:-2]) & (curve[1:-1] >= curve[2:]) & (curve[1:-1] > threshold)
    )
    peaks = peaks + 1
    if peaks.size < _PLP_MIN_PEAKS:
        return None
    intervals = np.diff(peaks) * hop / sr
    intervals = intervals[intervals > _EPS]
    if intervals.size == 0:
        return None
    median_interval = float(np.median(intervals))
    if median_interval <= _EPS:
        return None
    return {
        "bpm": 60.0 / median_interval,
        "median_interval_s": median_interval,
        "peak_count": int(peaks.size),
    }


def _octave_agreement(bpm: float, plp_bpm) -> float:
    """1.0 when ``bpm`` matches the PLP pulse, 0.5 for a rival octave, else 0.0."""
    if not plp_bpm:
        return 0.0
    for factor, weight in ((1.0, 1.0), (2.0, 0.5), (0.5, 0.5)):
        target = plp_bpm * factor
        if abs(bpm - target) <= _PLP_AGREEMENT_TOLERANCE * target:
            return weight
    return 0.0


def _refined_tempo(onset, sr: int, hop: int) -> dict:
    """Global tempo estimate that keeps half/double visible instead of guessing it."""
    if onset.size < _MIN_TEMPO_FRAMES:
        return _empty_tempo("Too few onset frames for a tempogram; tempo was not estimated.")
    win_length = max(8, min(int(round(_TEMPO_WINDOW_S * sr / hop)), onset.size // 2))
    profile, axis = _tempo_profile(onset, sr, hop, win_length)
    in_range = np.isfinite(axis) & (axis >= _TEMPO_RANGE_BPM[0]) & (axis <= _TEMPO_RANGE_BPM[1])
    if not np.any(in_range):
        return _empty_tempo("Tempogram range held no usable bpm bin; tempo was not estimated.")
    peak_index = int(np.flatnonzero(in_range)[int(np.argmax(profile[in_range]))])
    peak_bpm = _refine_peak_bpm(profile, axis, peak_index, sr, hop)
    peak_value = _profile_value(profile, axis, peak_bpm)
    if peak_value <= _EPS:
        return _empty_tempo("Tempogram peak carried no onset support; tempo was not estimated.")
    trough = float(np.median(profile[in_range]))

    plp = _plp_pulse_bpm(onset, sr, hop)
    plp_bpm = float(plp["bpm"]) if plp else None

    # Candidates are the tempogram peak and both of its octave neighbours, plus the
    # independent PLP rate. Scoring blends how much onset support a bpm has with
    # whether the local pulse agrees, so the octave is chosen by evidence, not taste.
    # The two halves carry equal weight: a lag comb matches 2T as well as T, so the
    # global profile alone cannot separate the octave; the PLP tracker is a second,
    # independently computed opinion on which octave the onsets actually pulse at.
    candidates = [peak_bpm]
    for factor in (0.5, 2.0):
        candidate = peak_bpm * factor
        if _TEMPO_RANGE_BPM[0] <= candidate <= _TEMPO_RANGE_BPM[1]:
            candidates.append(candidate)
    if plp_bpm is not None and _TEMPO_RANGE_BPM[0] <= plp_bpm <= _TEMPO_RANGE_BPM[1]:
        candidates.append(plp_bpm)
    scored = []
    for candidate in candidates:
        if not _TEMPO_RANGE_BPM[0] <= candidate <= _TEMPO_RANGE_BPM[1]:
            continue
        support = _profile_value(profile, axis, candidate) / peak_value
        agreement = _octave_agreement(candidate, plp_bpm)
        distance = abs(candidate - plp_bpm) if plp_bpm is not None else 0.0
        scored.append(
            {
                "bpm": candidate,
                "support": support,
                "plp_agreement": agreement,
                "score": 0.5 * support + 0.5 * agreement,
                "distance_to_plp": distance,
            }
        )
    if not scored:
        return _empty_tempo("No tempo candidate fell inside the searched range.", peak_bpm=peak_bpm)
    scored.sort(
        key=lambda row: (-row["score"], row["distance_to_plp"], -row["support"], row["bpm"])
    )
    chosen = scored[0]
    primary = float(chosen["bpm"])
    half_bpm = primary / 2.0
    double_bpm = primary * 2.0

    rival = max(_profile_value(profile, axis, half_bpm), _profile_value(profile, axis, double_bpm))
    rival_ratio = float(np.clip(rival / max(peak_value, _EPS), 0.0, 1.0))
    peakiness = float(np.clip((peak_value - trough) / max(peak_value, _EPS), 0.0, 1.0))
    # Confidence is evidence-based: a sharp profile, no competing octave and an
    # agreeing local pulse raise it; the ambiguity note below survives either way.
    confidence = float(
        np.clip(
            0.40 * peakiness + 0.35 * (1.0 - rival_ratio) + 0.25 * chosen["plp_agreement"],
            0.0,
            1.0,
        )
    )
    ambiguity = (
        f"Primary reading {primary:.2f} BPM; {half_bpm:.2f} BPM (half) and {double_bpm:.2f} BPM "
        f"(double) stay consistent with the same onset autocorrelation, whose rival octave reaches "
        f"{rival_ratio:.2f} of the primary peak. The metrical level is therefore unresolved, not "
        "guessed: choosing it would need a verified downbeat or meter, and neither exists here."
    )
    if plp_bpm is not None:
        ambiguity += (
            f" Independent predominant-local-pulse cross-check: {plp_bpm:.2f} BPM over "
            f"{plp['peak_count']} pulse peaks (median interval {plp['median_interval_s']:.4f} s); "
            "the PLP has its own octave ambiguity."
        )
    else:
        ambiguity += " No independent PLP cross-check was available for this source."
    return {
        "primary_bpm": round(primary, 2),
        "half_bpm": round(half_bpm, 2),
        "double_bpm": round(double_bpm, 2),
        "pulse_confidence": round(confidence, 3),
        "ambiguity": ambiguity,
        "tempogram_peak_bpm": round(peak_bpm, 2),
        "tempogram_peak_value": round(peak_value, 6),
        "octave_rival_ratio": round(rival_ratio, 3),
        "profile_peakiness": round(peakiness, 3),
        "plp_pulse_bpm": round(plp_bpm, 2) if plp_bpm is not None else None,
        "candidates": [
            {
                "bpm": round(row["bpm"], 2),
                "support": round(row["support"], 4),
                "plp_agreement": row["plp_agreement"],
                "score": round(row["score"], 4),
            }
            for row in scored
        ],
        "reviewed": False,
    }


def _empty_tempo(note: str, peak_bpm=None) -> dict:
    return {
        "primary_bpm": None,
        "half_bpm": None,
        "double_bpm": None,
        "pulse_confidence": 0.0,
        "ambiguity": note,
        "tempogram_peak_bpm": round(peak_bpm, 2) if peak_bpm is not None else None,
        "tempogram_peak_value": None,
        "octave_rival_ratio": None,
        "profile_peakiness": None,
        "plp_pulse_bpm": None,
        "candidates": [],
        "reviewed": False,
    }


# --------------------------------------------------------------------------- #
# downbeats: candidate bar starts from a low-frequency onset envelope
# --------------------------------------------------------------------------- #
def _band_flux(magnitude, frequencies, band, sr: int, hop: int):
    rows = (frequencies >= band[0]) & (frequencies < band[1])
    if not np.any(rows):
        return None
    band_energy = np.einsum("ij,ij->j", magnitude[rows], magnitude[rows])
    envelope = librosa.onset.onset_strength(S=np.log1p(band_energy), sr=sr, hop_length=hop)
    return np.nan_to_num(envelope, nan=0.0, posinf=0.0, neginf=0.0)


def _peak_strength(envelope, times, time_s: float) -> float:
    peak = max(float(envelope.max()), _EPS)
    if times.size == 0 or envelope.size == 0:
        return 0.0
    value = float(np.interp(time_s, times, envelope))
    return float(np.clip(value / peak, 0.0, 1.0))


def _grid_phase(envelope, frames_per_period: float):
    """Best-fitting grid phase (in frames) for a fixed beat period."""
    positions = np.arange(envelope.size, dtype=float)
    best_offset = 0.0
    best_score = -np.inf
    for offset in np.arange(0.0, frames_per_period, 1.0):
        grid = np.arange(offset, envelope.size, frames_per_period)
        if grid.size < 3:
            continue
        score = float(np.mean(np.interp(grid, positions, envelope)))
        if score > best_score + _EPS:
            best_offset, best_score = float(offset), score
    if not np.isfinite(best_score):
        return None
    return best_offset


def _compound_onsets(envelope, sr: int, hop: int, duration: float):
    """Detected onset times with a track-relative strength, always ordered and in-range."""
    if envelope is None or envelope.size < 3 or float(envelope.max()) <= _EPS:
        return []
    frames = librosa.onset.onset_detect(
        onset_envelope=envelope,
        sr=sr,
        hop_length=hop,
        delta=_ONSET_DELTA,
        wait=_ONSET_MIN_GAP_FRAMES,
    )
    times = librosa.frames_to_time(frames, sr=sr, hop_length=hop)
    frame_times = librosa.frames_to_time(np.arange(envelope.size), sr=sr, hop_length=hop)
    records = []
    for time_s in times:
        if time_s < 0 or time_s >= duration + _EPS:
            continue
        records.append(
            {
                "time": round(float(time_s), 3),
                "strength": round(_peak_strength(envelope, frame_times, float(time_s)), 3),
            }
        )
    return records


def _downbeats(envelope, sr: int, hop: int, duration: float, period_s) -> dict:
    """Candidate bar starts plus scored bar-length hypotheses from a low-band envelope."""
    candidates = [
        {"beats_per_bar": beats, "score": 0.0, "reviewed": False}
        for beats in _BEATS_PER_BAR_CANDIDATES
    ]
    record = {
        "downbeats": [],
        "bar_length_candidates": candidates,
        "period_s": round(period_s, 4) if period_s else None,
        "phase_offset_s": None,
        "note": (
            "Downbeat phase is a candidate inferred from the low-frequency onset envelope, not a "
            "verified meter or time signature; bar length is scored, not decided."
        ),
        "reviewed": False,
    }
    if envelope is None or envelope.size < 4 or float(envelope.max()) <= _EPS:
        record["note"] = "No usable low-frequency onset envelope; no bar candidates were measured."
        return record
    if not period_s or period_s <= 0:
        record["note"] = "No usable tempo period; no bar candidates were measured."
        return record
    frames_per_period = period_s * sr / hop
    if frames_per_period < 2:
        record["note"] = "Tempo period is shorter than two analysis frames; no bar candidates."
        return record
    offset = _grid_phase(envelope, frames_per_period)
    if offset is None:
        record["note"] = "Too few beat positions at this period to phase a bar grid."
        return record
    grid = np.arange(offset, envelope.size, frames_per_period)
    times = librosa.frames_to_time(grid, sr=sr, hop_length=hop)
    frame_times = librosa.frames_to_time(np.arange(envelope.size), sr=sr, hop_length=hop)
    keep = (times >= 0) & (times < duration)
    times, grid = times[keep], grid[keep]
    if times.size < 4:
        record["note"] = "Too few beat positions inside the source to phase a bar grid."
        return record
    strengths = np.array([_peak_strength(envelope, frame_times, float(time_s)) for time_s in times])
    mean_strength = float(strengths.mean())
    scores = []
    for beats in _BEATS_PER_BAR_CANDIDATES:
        picked = strengths[np.arange(strengths.size) % beats == 0]
        score = (
            float(picked.mean() / mean_strength) if mean_strength > _EPS and picked.size else 0.0
        )
        scores.append({"beats_per_bar": beats, "score": round(score, 3), "reviewed": False})
    record.update(
        {
            "downbeats": [
                {"time": round(float(time_s), 3), "strength": round(float(strength), 3)}
                for time_s, strength in zip(times, strengths)
            ],
            "bar_length_candidates": scores,
            "phase_offset_s": round(
                float(librosa.frames_to_time(offset, sr=sr, hop_length=hop)), 4
            ),
            "note": (
                "Bar starts are every Nth beat of a beat grid phased on low-frequency onsets; the "
                "score of a bar length is its downbeat-vs-beat strength ratio, so 1.0 means no "
                "preference. This is a candidate phase, not a verified meter, time signature or "
                "verse/chorus structure."
            ),
        }
    )
    return record


# --------------------------------------------------------------------------- #
# key: Krumhansl-Schmuckler correlation, with the runner-up kept visible
# --------------------------------------------------------------------------- #
def _key(chroma) -> dict:
    if chroma.size == 0:
        return _empty_key("No chroma was measured; no key candidate was produced.")
    vector = np.nan_to_num(chroma.mean(axis=1))
    if float(np.abs(vector).sum()) <= _EPS:
        return _empty_key("Chroma carried no energy; no key candidate was produced.")
    scored = []
    for tonic in range(12):
        for mode, profile in (("major", _KS_MAJOR), ("minor", _KS_MINOR)):
            scored.append(
                {
                    "tonic": _PITCH_CLASSES[tonic],
                    "mode": mode,
                    "correlation": _pearson(vector, np.roll(profile, tonic)),
                }
            )
    scored.sort(key=lambda row: (-row["correlation"], row["tonic"], row["mode"]))
    best, runner_up = scored[0], scored[1]
    margin = best["correlation"] - runner_up["correlation"]
    note = (
        f"Best Krumhansl-Schmuckler correlation {best['correlation']:.3f} against a runner-up "
        f"{runner_up['correlation']:.3f} ({runner_up['tonic']} {runner_up['mode']}). "
    )
    if margin < 0.05:
        note += (
            "The winner is within 0.05 of the runner-up, so this is a weak key candidate rather "
            "than an established key; modulation, tuning and mix balance are not resolved. "
        )
    note += (
        "Key is an unverified candidate: chroma correlation cannot confirm tonal centre, and "
        "relative major/minor pairs are especially close here."
    )
    chroma_share = vector / max(float(vector.sum()), _EPS)
    return {
        "tonic": best["tonic"],
        "mode": best["mode"],
        "best_correlation": round(best["correlation"], 4),
        "runner_up": {
            "tonic": runner_up["tonic"],
            "mode": runner_up["mode"],
            "correlation": round(runner_up["correlation"], 4),
        },
        "margin": round(margin, 4),
        "chroma_share": [round(float(value), 4) for value in chroma_share],
        "note": note,
        "reviewed": False,
    }


def _empty_key(note: str) -> dict:
    return {
        "tonic": None,
        "mode": None,
        "best_correlation": None,
        "runner_up": None,
        "margin": None,
        "chroma_share": [],
        "note": note,
        "reviewed": False,
    }


# --------------------------------------------------------------------------- #
# sections: self-similarity novelty, candidate boundaries only
# --------------------------------------------------------------------------- #
def _integral(image):
    return np.pad(image.cumsum(axis=0).cumsum(axis=1), ((1, 0), (1, 0)))


def _block_sum(integral, r0: int, r1: int, c0: int, c1: int) -> float:
    return float(integral[r1, c1] - integral[r0, c1] - integral[r1, c0] + integral[r0, c0])


def _coarse_features(chroma, mfcc, sr: int, hop: int):
    """Mean features on a coarse grid, so a long track never builds a huge matrix."""
    stack = np.vstack([np.nan_to_num(chroma), np.nan_to_num(mfcc)])
    block = max(1, int(round(_SECTION_HOP_S * sr / hop)))
    count = stack.shape[1] // block
    if count < 2:
        return None, None
    trimmed = stack[:, : count * block]
    blocks = trimmed.reshape(stack.shape[0], count, block).mean(axis=2)
    times = librosa.frames_to_time(np.arange(count) * block, sr=sr, hop_length=hop)
    scaled = (blocks - blocks.mean(axis=1, keepdims=True)) / np.maximum(
        blocks.std(axis=1, keepdims=True), _EPS
    )
    return scaled, times


def _sections(chroma, mfcc, sr: int, hop: int, duration: float) -> dict:
    """Novelty candidates from a checkerboard kernel over an affinity self-similarity."""
    anchor = {
        "time": 0.0,
        "strength": 1.0,
        "kind": "start_anchor",
        "reviewed": False,
    }
    note = (
        "Section boundaries are candidate changes from self-similarity novelty; they are not "
        "verse/chorus labels and were not verified against a listening pass."
    )
    features, times = _coarse_features(chroma, mfcc, sr, hop)
    if features is None:
        return {"sections": [anchor], "section_spans": [], "note": note, "reviewed": False}
    half = max(1, int(round(_SECTION_HALF_WINDOW_S / _SECTION_HOP_S)))
    count = features.shape[1]
    if count <= 2 * half:
        return {"sections": [anchor], "section_spans": [], "note": note, "reviewed": False}
    similarity = np.nan_to_num(
        librosa.segment.recurrence_matrix(features, mode="affinity", sym=True, metric="cosine")
    )
    integral = _integral(similarity)
    novelty = np.zeros(count)
    for index in range(half, count - half):
        inside_before = _block_sum(integral, index - half, index, index - half, index)
        inside_after = _block_sum(integral, index, index + half, index, index + half)
        across_after = _block_sum(integral, index - half, index, index, index + half)
        across_before = _block_sum(integral, index, index + half, index - half, index)
        novelty[index] = (inside_before + inside_after - across_after - across_before) / (
            4 * half * half
        )
    peak = float(novelty.max())
    if peak <= _EPS:
        return {"sections": [anchor], "section_spans": [], "note": note, "reviewed": False}
    strengths = np.clip(novelty / peak, 0.0, 1.0)
    scored = []
    for index in range(half, count - half):
        left = strengths[index - 1] if index > 0 else 0.0
        right = strengths[index + 1] if index + 1 < count else 0.0
        if strengths[index] < _SECTION_STRENGTH_FLOOR:
            continue
        if strengths[index] < left or strengths[index] < right:
            continue
        scored.append({"time": float(times[index]), "strength": float(strengths[index])})
    kept = []
    for item in sorted(scored, key=lambda row: (-row["strength"], row["time"])):
        if all(abs(item["time"] - other["time"]) >= _SECTION_MIN_SEPARATION_S for other in kept):
            kept.append(item)
    boundaries = [anchor]
    boundaries += [
        {
            "time": round(item["time"], 3),
            "strength": round(item["strength"], 3),
            "kind": "candidate_boundary",
            "reviewed": False,
        }
        for item in sorted(kept, key=lambda row: row["time"])
        if 0 < item["time"] < duration
    ]
    spans = []
    for start, end in zip(boundaries, boundaries[1:] + [{"time": duration}]):
        spans.append(
            {
                "start": start["time"],
                "end": round(float(min(end["time"], duration)), 3),
                "novelty_strength": start["strength"],
                "label": "candidate_span",
                "reviewed": False,
            }
        )
    return {"sections": boundaries, "section_spans": spans, "note": note, "reviewed": False}


# --------------------------------------------------------------------------- #
# provenance, empty result and the public entry point
# --------------------------------------------------------------------------- #
def _provenance(sr: int) -> dict:
    return {
        "analysis_version": ANALYSIS_VERSION,
        "available_deps": sorted(AVAILABLE_DEPS),
        "decoding": "librosa.load(sr=22050, mono=True) by the caller; decoded once and reused",
        "sample_rate_hz": int(sr),
        "stft_n_fft": _N_FFT,
        "stft_hop_length": _HOP,
        "tempo_window_s": _TEMPO_WINDOW_S,
        "tempo_range_bpm": [_TEMPO_RANGE_BPM[0], _TEMPO_RANGE_BPM[1]],
        "plp_tempo_range_bpm": [_PLP_TEMPO_RANGE_BPM[0], _PLP_TEMPO_RANGE_BPM[1]],
        "plp_window_frames": _PLP_WINDOW_FRAMES,
        "onset_delta": _ONSET_DELTA,
        "onset_min_gap_frames": _ONSET_MIN_GAP_FRAMES,
        "octave_tolerance_fraction": _OCTAVE_TOLERANCE,
        "plp_agreement_tolerance_fraction": _PLP_AGREEMENT_TOLERANCE,
        "kick_band_hz": [_KICK_HZ[0], _KICK_HZ[1]],
        "bass_onset_band_hz": [_BASS_ONSET_HZ[0], _BASS_ONSET_HZ[1]],
        "vocal_onset_band_hz": [_VOCAL_ONSET_HZ[0], _VOCAL_ONSET_HZ[1]],
        "section_hop_s": _SECTION_HOP_S,
        "section_half_window_s": _SECTION_HALF_WINDOW_S,
        "section_min_separation_s": _SECTION_MIN_SEPARATION_S,
        "section_strength_floor": _SECTION_STRENGTH_FLOOR,
        "beats_per_bar_candidates": list(_BEATS_PER_BAR_CANDIDATES),
        "key_profiles": "Krumhansl & Kessler (1982) major/minor profiles, rotated over 12 tonics",
        "units": {
            "time": "seconds from source start",
            "bpm": "beats per minute from a tempogram/PLP pulse estimate; half/double both retained",
            "pulse_confidence": "0-1 blend of profile peakiness, octave rivalry and PLP agreement",
            "octave_rival_ratio": "rival octave profile strength divided by the primary peak (0-1)",
            "support": "profile value at that bpm divided by the primary peak (0-1)",
            "strength": "relative to the loudest value measured in the same envelope (0=quietest, 1=peak)",
            "bar_length_score": "mean downbeat strength divided by mean beat strength for that bar length",
            "correlation": "Pearson correlation between the mean chroma vector and a key profile (-1..1)",
            "chroma_share": "mean chroma value per pitch class divided by the 12-class total (sums to 1)",
            "novelty_strength": "checkerboard novelty at that boundary divided by the strongest boundary (0-1)",
        },
        "librosa_calls": [
            "librosa.feature.tempogram(onset_envelope=..., sr=sr, hop_length=512, win_length=min(8 s, half the onset frames))",
            "librosa.tempo_frequencies(n_bins, hop_length=512, sr=sr)",
            "librosa.beat.plp(onset_envelope=..., sr=sr, hop_length=512, win_length=min(384, half the onset frames), tempo_min=30, tempo_max=300)",
            "librosa.onset.onset_strength(S=np.log1p(band energy), sr=sr, hop_length=512)",
            "librosa.onset.onset_detect(onset_envelope=..., sr=sr, hop_length=512, delta=0.08, wait=4)",
            "librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=512)",
            "librosa.feature.mfcc(y=y, sr=sr, hop_length=512, n_mfcc=13)",
            "librosa.segment.recurrence_matrix(features, mode='affinity', sym=True, metric='cosine')",
            "librosa.frames_to_time(frames, sr=sr, hop_length=512)",
        ],
        "notes": [
            "Measurements are relative to this track; the audio was not normalized.",
            "No genre, instrument, mood, language, meter, time signature or verse/chorus label is inferred.",
            "Only librosa, numpy and the standard library are used: no torch/demucs/madmom/essentia, no network.",
        ],
    }


def _empty_result(duration: float) -> dict:
    return {
        "duration": duration,
        "analysis_version": ANALYSIS_VERSION,
        "refined_tempo": _empty_tempo("Source decoded to zero samples; tempo was not estimated."),
        "downbeats": [],
        "bar_length_candidates": [
            {"beats_per_bar": beats, "score": 0.0, "reviewed": False}
            for beats in _BEATS_PER_BAR_CANDIDATES
        ],
        "downbeat_note": "Source decoded to zero samples; no bar candidates were measured.",
        "key": _empty_key("Source decoded to zero samples; no key candidate was produced."),
        "sections": [],
        "section_spans": [],
        "section_note": "Source decoded to zero samples; no boundaries were measured.",
        "bass_onsets": [],
        "vocal_band_onsets": [],
        "provenance": _provenance(_DECODE_SR),
        "warnings": ["Source decoded to zero samples; no measurements were possible."],
    }


def deep_analyze(source: Path, duration: float) -> dict:
    """Deeper local measurements for one source; never an approval or a creative claim."""
    y, sr = librosa.load(source, sr=_DECODE_SR, mono=True)
    if y.size == 0 or not np.isfinite(duration) or duration <= 0:
        return _empty_result(duration)

    magnitude = np.abs(librosa.stft(y, n_fft=_N_FFT, hop_length=_HOP))
    frequencies = librosa.fft_frequencies(sr=sr, n_fft=_N_FFT)
    onset = np.nan_to_num(librosa.onset.onset_strength(y=y, sr=sr, hop_length=_HOP))

    tempo = _refined_tempo(onset, sr, _HOP)
    period_s = 60.0 / tempo["primary_bpm"] if tempo["primary_bpm"] else None

    kick = _band_flux(magnitude, frequencies, _KICK_HZ, sr, _HOP)
    bars = _downbeats(kick, sr, _HOP, duration, period_s)

    bass = _band_flux(magnitude, frequencies, _BASS_ONSET_HZ, sr, _HOP)
    vocal = _band_flux(magnitude, frequencies, _VOCAL_ONSET_HZ, sr, _HOP)

    chroma = np.nan_to_num(librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=_HOP))
    mfcc = np.nan_to_num(librosa.feature.mfcc(y=y, sr=sr, hop_length=_HOP, n_mfcc=13))
    key = _key(chroma)
    sections = _sections(chroma, mfcc, sr, _HOP, duration)

    return {
        "duration": duration,
        "analysis_version": ANALYSIS_VERSION,
        "refined_tempo": tempo,
        "downbeats": bars["downbeats"],
        "bar_length_candidates": bars["bar_length_candidates"],
        "downbeat_note": bars["note"],
        "downbeat_period_s": bars["period_s"],
        "downbeat_phase_offset_s": bars["phase_offset_s"],
        "key": key,
        "sections": sections["sections"],
        "section_spans": sections["section_spans"],
        "section_note": sections["note"],
        "bass_onsets": _compound_onsets(bass, sr, _HOP, duration),
        "vocal_band_onsets": _compound_onsets(vocal, sr, _HOP, duration),
        "onset_frame_count": int(onset.size),
        "provenance": _provenance(sr),
        "warnings": [
            "Tempo, downbeat phase, key and section boundaries are unverified estimates needing "
            "review; none of them approves a storyboard, prompt or still.",
            "Tempo keeps its half/double ambiguity: the onset autocorrelation supports the rival "
            "octave, so the metrical level was not guessed.",
            "Downbeat phase and bar length are candidates from a low-frequency onset envelope, not "
            "a verified meter or time signature.",
            "Key is a Krumhansl-Schmuckler correlation candidate whose runner-up is reported next "
            "to it; a small margin is not musical certainty and relatives stay close.",
            "Section boundaries are novelty candidates, not verse/chorus labels, and were not "
            "confirmed by a listening pass.",
            "Band onsets are relative measurements of this track and do not identify instruments; "
            "no genre, language or mood was inferred.",
        ],
    }
