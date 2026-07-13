"""Compute ECG measurements + fiducial ROIs from a raw 12-lead waveform.

Grounds supplementary datasets (STAFF III, MIMIC-IV-ECG) that lack the PTB-XL+
precomputed feature/fiducial companion. Pure numpy/scipy. Outputs match the shapes
``ingest/pipeline`` and ``curation`` expect:

    {"values": {"heart_rate":.., "axis_deg":.., "qrs_ms":.., "sokolow_lyon_mv":..,
                "cornell_mv":..},
     "per_lead_st_mv": {"V2": 0.05, ...},
     "rois": [ {neutral segment ROI}, ... ],
     "median_beats": {"available": True, ...}}

Transparent, inspectable rules (the plan's "signal-processing service"): R-peak
detection (Pan-Tompkins-style), net-QRS-area axis, J-point ST, R/S voltage criteria.
Deliberately conservative — emits only what it can measure, leaving the rest unset so
curation degrades gracefully rather than asserting a wrong number.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np
from scipy.signal import butter, filtfilt, find_peaks

from .measurements import LEADS

# Neutral segment ROI windows the viewer renders, relative to the R-peak (seconds).
# These are anatomical locations on any beat, not diagnostic claims.
_ROI_LEADS = ("II", "V2", "V5")


def _bandpass(sig: np.ndarray, fs: float, lo: float, hi: float) -> np.ndarray:
    nyq = 0.5 * fs
    hi = min(hi, nyq * 0.99)
    b, a = butter(2, [lo / nyq, hi / nyq], btype="band")
    return filtfilt(b, a, sig)


def _as_array(signal_by_lead: Mapping[str, Sequence[float]], lead: str) -> np.ndarray:
    return np.asarray(signal_by_lead.get(lead) or [], dtype=float)


def detect_r_peaks(lead: np.ndarray, fs: float) -> np.ndarray:
    """Pan-Tompkins-style QRS detection: bandpass 5-15 Hz, derivative, square,
    moving-window integrate, then peak-pick with a refractory distance."""
    if lead.size < int(fs):  # need >= ~1 s
        return np.array([], dtype=int)
    filtered = _bandpass(lead, fs, 5.0, 15.0)
    deriv = np.ediff1d(filtered, to_begin=0.0)
    squared = deriv ** 2
    win = max(1, int(0.15 * fs))
    integrated = np.convolve(squared, np.ones(win) / win, mode="same")
    thresh = float(np.mean(integrated) + 0.5 * np.std(integrated))
    peaks, _ = find_peaks(integrated, distance=int(0.3 * fs), height=max(thresh, 1e-9))
    # Snap each detection to the local |signal| max (the actual R) within +/-60 ms.
    out = []
    half = int(0.06 * fs)
    for p in peaks:
        lo, hi = max(0, p - half), min(lead.size, p + half)
        if hi > lo:
            out.append(lo + int(np.argmax(np.abs(lead[lo:hi]))))
    return np.array(sorted(set(out)), dtype=int)


def _heart_rate(peaks: np.ndarray, fs: float) -> float | None:
    if peaks.size < 2:
        return None
    rr = np.diff(peaks) / fs
    rr = rr[(rr > 0.25) & (rr < 2.5)]  # 24-240 bpm plausibility
    if rr.size == 0:
        return None
    return round(float(60.0 / np.median(rr)), 1)


def _qrs_axis(signal_by_lead: Mapping[str, Sequence[float]], peaks: np.ndarray, fs: float) -> float | None:
    """Net QRS deflection in leads I and aVF -> frontal axis (degrees)."""
    lead_i = _as_array(signal_by_lead, "I")
    lead_avf = _as_array(signal_by_lead, "aVF")
    if lead_i.size == 0 or lead_avf.size == 0 or peaks.size == 0:
        return None
    half = int(0.05 * fs)

    def net(sig: np.ndarray) -> float:
        vals = []
        for p in peaks:
            lo, hi = max(0, p - half), min(sig.size, p + half)
            seg = sig[lo:hi]
            if seg.size:
                vals.append(float(seg.sum()))
        return float(np.median(vals)) if vals else 0.0

    ni, nf = net(lead_i), net(lead_avf)
    if abs(ni) < 1e-9 and abs(nf) < 1e-9:
        return None
    return round(float(np.degrees(np.arctan2(nf, ni))), 1)


def _qrs_ms(lead: np.ndarray, peaks: np.ndarray, fs: float) -> float | None:
    """Approximate QRS duration: width around the R where |derivative| stays high."""
    if peaks.size == 0:
        return None
    deriv = np.abs(np.ediff1d(lead, to_begin=0.0))
    thr = float(np.mean(deriv) + 0.5 * np.std(deriv))
    widths = []
    span = int(0.08 * fs)
    for p in peaks:
        lo = p
        while lo > max(0, p - span) and deriv[lo] > thr:
            lo -= 1
        hi = p
        while hi < min(lead.size - 1, p + span) and deriv[hi] > thr:
            hi += 1
        widths.append((hi - lo) / fs * 1000.0)
    if not widths:
        return None
    return round(float(np.median(widths)), 1)


def _per_lead_st(signal_by_lead: Mapping[str, Sequence[float]], peaks: np.ndarray, fs: float) -> dict[str, float]:
    """ST level (mV) at the J-point + 60 ms, median across beats, baseline-corrected
    to the PR segment (~80 ms before R)."""
    out: dict[str, float] = {}
    if peaks.size == 0:
        return out
    j_off = int(0.06 * fs)  # ~J point after R
    st_off = int(0.12 * fs)  # J + 60 ms
    base_off = int(0.08 * fs)  # PR baseline before R
    for lead in LEADS:
        sig = _as_array(signal_by_lead, lead)
        if sig.size == 0:
            continue
        vals = []
        for p in peaks:
            st_idx, base_idx = p + st_off, p - base_off
            if 0 <= base_idx and st_idx < sig.size:
                vals.append(float(sig[st_idx] - sig[base_idx]))
        if vals:
            out[lead] = round(float(np.median(vals)), 3)
    return out


def _voltage_criteria(signal_by_lead: Mapping[str, Sequence[float]], peaks: np.ndarray, fs: float) -> dict[str, float]:
    """Sokolow-Lyon (|S_V1| + max(R_V5,R_V6)) and Cornell (R_aVL + |S_V3|) in mV."""
    half = int(0.05 * fs)

    def amp(lead: str, kind: str) -> float | None:
        sig = _as_array(signal_by_lead, lead)
        if sig.size == 0 or peaks.size == 0:
            return None
        vals = []
        for p in peaks:
            lo, hi = max(0, p - half), min(sig.size, p + half)
            seg = sig[lo:hi]
            if seg.size:
                vals.append(float(seg.max()) if kind == "R" else float(seg.min()))
        return float(np.median(vals)) if vals else None

    out: dict[str, float] = {}
    s_v1, r_v5, r_v6 = amp("V1", "S"), amp("V5", "R"), amp("V6", "R")
    if s_v1 is not None and (r_v5 is not None or r_v6 is not None):
        out["sokolow_lyon_mv"] = round(abs(s_v1) + max(abs(r_v5 or 0.0), abs(r_v6 or 0.0)), 3)
    r_avl, s_v3 = amp("aVL", "R"), amp("V3", "S")
    if r_avl is not None and s_v3 is not None:
        out["cornell_mv"] = round(abs(r_avl) + abs(s_v3), 3)
    return out


def _median_beat(signal_by_lead: Mapping[str, Sequence[float]], peaks: np.ndarray, fs: float) -> dict[str, Any]:
    """Average aligned beat (~700 ms window centered on R) per lead, resampled to 100 Hz."""
    if peaks.size < 2:
        return {"available": False}
    pre, post = int(0.3 * fs), int(0.4 * fs)
    target = 70  # 700 ms at 100 Hz
    beats: dict[str, list[float]] = {}
    for lead in LEADS:
        sig = _as_array(signal_by_lead, lead)
        if sig.size == 0:
            continue
        stack = [sig[p - pre:p + post] for p in peaks if p - pre >= 0 and p + post < sig.size]
        stack = [s for s in stack if s.size == pre + post]
        if not stack:
            continue
        mean_beat = np.mean(np.vstack(stack), axis=0)
        idx = np.linspace(0, mean_beat.size - 1, target)
        beats[lead] = np.interp(idx, np.arange(mean_beat.size), mean_beat).round(4).tolist()
    if not beats:
        return {"available": False}
    return {
        "available": True,
        "samplingFrequency": 100,
        "durationMs": 700,
        "leads": list(beats.keys()),
        "beats": beats,
        "source": "computed_from_waveform_signal_processing",
    }


def _rois(signal_by_lead: Mapping[str, Sequence[float]], peaks: np.ndarray, fs: float, duration_sec: float) -> list[dict[str, Any]]:
    """Neutral segment-location ROIs (p_wave, qrs_complex, st_segment, t_wave, pr_interval,
    qt_segment) anchored on a representative mid-record beat, for the leads the viewer parses."""
    if peaks.size == 0:
        return []
    r = int(peaks[len(peaks) // 2])  # a representative middle beat
    t0 = r / fs

    def win(start_off: float, end_off: float) -> tuple[float, float]:
        return (max(0.0, t0 + start_off), min(duration_sec, t0 + end_off))

    segments = {
        "p_wave": (-0.20, -0.10), "pr_interval": (-0.16, 0.0), "qrs_complex": (-0.05, 0.05),
        "st_segment": (0.05, 0.12), "t_wave": (0.12, 0.36), "qt_segment": (-0.04, 0.36),
    }
    labels = {
        "p_wave": "P wave", "pr_interval": "PR interval", "qrs_complex": "QRS complex",
        "st_segment": "ST segment", "t_wave": "T wave", "qt_segment": "QT segment",
    }
    out: list[dict[str, Any]] = []
    for lead in _ROI_LEADS:
        sig = _as_array(signal_by_lead, lead)
        if sig.size == 0:
            continue
        for concept, (a, b) in segments.items():
            start, end = win(a, b)
            if end <= start:
                continue
            lo, hi = int(start * fs), int(min(end * fs, sig.size))
            seg = sig[lo:hi] if hi > lo else np.array([0.0])
            out.append({
                "lead": lead, "concept": concept, "label": labels[concept],
                "timeStartSec": round(start, 3), "timeEndSec": round(end, 3),
                "ampMinMv": round(float(seg.min()) - 0.05, 3), "ampMaxMv": round(float(seg.max()) + 0.05, 3),
                "source": "computed", "confidence": "medium",
            })
    return out


def compute_signal_features(
    signal_by_lead: Mapping[str, Sequence[float]], fs: float, duration_sec: float = 10.0
) -> dict[str, Any]:
    """Full feature/fiducial extraction for a 12-lead waveform (mV, at sampling rate ``fs``)."""
    primary = _as_array(signal_by_lead, "II")
    if primary.size == 0:
        primary = _as_array(signal_by_lead, "V5")
    peaks = detect_r_peaks(primary, fs)

    values: dict[str, float] = {}
    hr = _heart_rate(peaks, fs)
    if hr is not None:
        values["heart_rate"] = hr
    axis = _qrs_axis(signal_by_lead, peaks, fs)
    if axis is not None:
        values["axis_deg"] = axis
    qrs = _qrs_ms(primary, peaks, fs)
    if qrs is not None:
        values["qrs_ms"] = qrs
    values.update(_voltage_criteria(signal_by_lead, peaks, fs))

    per_lead_st = _per_lead_st(signal_by_lead, peaks, fs)
    return {
        "values": values,
        "per_lead_st_mv": per_lead_st,
        "rois": _rois(signal_by_lead, peaks, fs, duration_sec),
        "median_beats": _median_beat(signal_by_lead, peaks, fs),
        "r_peaks": peaks.tolist(),
    }
