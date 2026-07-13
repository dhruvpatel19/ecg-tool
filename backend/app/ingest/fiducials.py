"""Parse PTB-XL+ ECGDeli fiducials into all-12-lead ROIs + a median beat.

Reads the per-record GLOBAL ``.atr`` once (it carries the full fiducial cycle:
p-wave onset/peak/offset, QRS onset, Q/R/S peak, QRS offset, "L point (for STEMI)"
= J point, t-wave onset/peak/offset) and projects the timing onto all 12 leads,
computing amplitude bounds from each lead's actual signal. The same fiducials'
R-peaks are used to build a median beat per lead by windowed averaging.

Annotation samples are 500 Hz; ROI/median times are in seconds, mapping directly
onto the 10 s viewer timeline regardless of the 100 Hz signal.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

FIDUCIAL_FS = 500
LEADS = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
DEFAULT_FIDUCIAL_LEADS = LEADS  # ROIs now cover all 12 leads via the global fiducials

_P_ON, _P_OFF = "p-wave onset", "p-wave offset"
_QRS_ON, _QRS_OFF = "QRS onset", "QRS offset"
_R = "R peak"
_J = "L point (for STEMI)"
_T_ON, _T_OFF = "t-wave onset", "t-wave offset"

# Per-lead morphology ROIs. Concepts are NEUTRAL SEGMENT LOCATIONS (where the
# wave is), NOT diagnostic findings — these windows exist on every beat regardless
# of pathology, so they must not be read as evidence of a finding. Curation derives
# findings from labels/statements/measurements, not from ROI presence.
_LEAD_ROIS = [
    ("P wave", "p_wave", _P_ON, _P_OFF, "medium"),
    ("QRS complex", "qrs_complex", _QRS_ON, _QRS_OFF, "high"),
    ("ST segment", "st_segment", _J, _T_ON, "medium"),
    ("T wave", "t_wave", _T_ON, _T_OFF, "medium"),
]
# Interval ROIs (timing, lead-agnostic) built on a single representative lead.
_INTERVAL_ROIS = [
    ("PR interval", "pr_interval", _P_ON, _QRS_ON, "medium"),
    ("QT interval", "qt_segment", _QRS_ON, _T_OFF, "medium"),
]
_INTERVAL_LEAD = "II"

# Median beat window around each R peak (seconds).
_MED_PRE, _MED_POST = 0.25, 0.45
_MED_LEN_100HZ = int((_MED_PRE + _MED_POST) * 100)  # 70 samples


def _padded(ecg_id: str | int) -> str:
    digits = "".join(ch for ch in str(ecg_id) if ch.isdigit())
    return f"{int(digits):05d}" if digits else str(ecg_id)


def _bucket(ecg_id: str | int) -> str:
    digits = "".join(ch for ch in str(ecg_id) if ch.isdigit())
    return f"{(int(digits) // 1000) * 1000:05d}" if digits else "00000"


def _read_global(plus_root: Path, ecg_id: str | int) -> list[tuple[int, str]]:
    base = plus_root / "fiducial_points" / "ecgdeli" / _bucket(ecg_id) / f"{_padded(ecg_id)}_points_global"
    if not base.with_suffix(".atr").exists():
        return []
    try:
        import wfdb  # type: ignore

        ann = wfdb.rdann(str(base), "atr")
    except Exception:
        return []
    return [(int(s), str(n).strip()) for s, n in zip(ann.sample, ann.aux_note or []) if str(n).strip()]


def _segment_beats(annotations: Sequence[tuple[int, str]]) -> list[dict[str, int]]:
    beats: list[dict[str, int]] = []
    current: dict[str, int] = {}
    for sample, label in annotations:
        if label in current:
            beats.append(current)
            current = {}
        current[label] = sample
    if current:
        beats.append(current)
    return beats


def _pick_beat(beats: list[dict[str, int]]) -> dict[str, int] | None:
    complete = [b for b in beats if _QRS_ON in b and _QRS_OFF in b and _T_OFF in b]
    if complete:
        return complete[len(complete) // 2]
    return beats[len(beats) // 2] if beats else None


def _amp_bounds(signal: Sequence[float] | None, start_s: float, end_s: float) -> tuple[float, float]:
    if not signal:
        return (-1.5, 1.5)
    lo = max(0, int(start_s * 100))
    hi = min(len(signal), max(lo + 1, int(end_s * 100)))
    window = signal[lo:hi]
    if not window:
        return (-1.5, 1.5)
    return (round(min(window) - 0.15, 3), round(max(window) + 0.15, 3))


def _build_rois(
    beat: dict[str, int],
    signal_by_lead: Mapping[str, Sequence[float]] | None,
    per_lead_st_mv: Mapping[str, float],
) -> list[dict[str, Any]]:
    rois: list[dict[str, Any]] = []
    for lead in LEADS:
        signal = (signal_by_lead or {}).get(lead)
        specs = list(_LEAD_ROIS)
        if lead == _INTERVAL_LEAD:
            specs = specs + _INTERVAL_ROIS
        for label, concept, start_label, end_label, confidence in specs:
            if start_label not in beat or end_label not in beat:
                continue
            start_s = beat[start_label] / FIDUCIAL_FS
            end_s = beat[end_label] / FIDUCIAL_FS
            if end_s <= start_s:
                continue
            amp_min, amp_max = _amp_bounds(signal, start_s, end_s)
            roi = {
                "lead": lead,
                "timeStartSec": round(start_s, 3),
                "timeEndSec": round(end_s, 3),
                "ampMinMv": amp_min,
                "ampMaxMv": amp_max,
                "label": label,
                "concept": concept,
                "source": "ptbxl_plus_ecgdeli_fiducial",
                "confidence": confidence,
            }
            if label == "ST segment" and lead in per_lead_st_mv:
                roi["stElevationMv"] = per_lead_st_mv[lead]
            rois.append(roi)
    return rois


def _compute_median(
    beats: list[dict[str, int]],
    signal_by_lead: Mapping[str, Sequence[float]] | None,
) -> dict[str, list[float]]:
    """Median beat per lead: average of fixed windows around each R peak (100 Hz)."""
    if not signal_by_lead:
        return {}
    r_times = [b[_R] / FIDUCIAL_FS for b in beats if _R in b]
    if not r_times:
        return {}
    pre, length = int(_MED_PRE * 100), _MED_LEN_100HZ
    median: dict[str, list[float]] = {}
    for lead, signal in signal_by_lead.items():
        if not signal:
            continue
        stacks: list[list[float]] = []
        for r in r_times:
            center = int(r * 100)
            lo, hi = center - pre, center - pre + length
            if lo < 0 or hi > len(signal):
                continue
            stacks.append(list(signal[lo:hi]))
        if not stacks:
            continue
        median[lead] = [round(sum(col) / len(col), 4) for col in zip(*stacks)]
    return median


def parse_fiducials_to_rois(
    plus_root: str | Path,
    ecg_id: str | int,
    leads: Sequence[str] = LEADS,
    signal_by_lead: Mapping[str, Sequence[float]] | None = None,
    signal_fs: int = 100,
    per_lead_st_mv: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Return ``{rois, fiducials_by_lead, median}`` for one ECG (all 12 leads)."""
    plus_root = Path(plus_root)
    per_lead_st_mv = per_lead_st_mv or {}
    annotations = _read_global(plus_root, ecg_id)
    beats = _segment_beats(annotations)
    beat = _pick_beat(beats)
    if not beat:
        return {"rois": [], "fiducials_by_lead": {}, "median": {}}
    rois = _build_rois(beat, signal_by_lead, per_lead_st_mv)
    median = _compute_median(beats, signal_by_lead)
    fiducials_by_lead = {
        "global": {label: round(sample / FIDUCIAL_FS, 3) for label, sample in beat.items()}
    }
    return {"rois": rois, "fiducials_by_lead": fiducials_by_lead, "median": median}
