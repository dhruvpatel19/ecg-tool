"""Map raw PTB-XL+ feature columns to canonical measurement keys.

The V1 audit found that QT/QTc/PR/axis were present in every record but never
mapped, because the old alias map could not match the real 12SL column names
(``QT_IntCorr_Global``, ``PR_Int_Global``, ``R_AxisFrontal_Global`` ...). This
module maps from the actual column names, with documented fallbacks, and derives
hypertrophy voltages (Sokolow-Lyon, Cornell) and per-lead ST elevation.

All canonical measurements are returned in clinician-facing units:
- intervals/durations in milliseconds (ms)
- heart rate in beats per minute (bpm)
- axis in degrees
- voltages / ST levels in millivolts (mV)

NOTE: PTB-XL+ 12SL amplitude columns (``R_Amp_*``, ``S_Amp_*``, ``ST_Elev_*``) are
ALREADY in millivolts in this dataset — they are stored as-is, NOT divided by 1000.
(Calibration: Sokolow-Lyon values land ~2-4 mV and ST ~0.1-0.3 mV, which a µV→mV
conversion would make 1000× too small.)
"""

from __future__ import annotations

from numbers import Real
from typing import Any, Mapping

LEADS = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]

# Canonical key -> ordered list of source columns to try (first numeric hit wins).
# Names are the real PTB-XL+ 12SL / ECGDeli column headers.
MEASUREMENT_SOURCES: dict[str, list[str]] = {
    "heart_rate": ["HR_Ventr_Global", "HR__Global", "HR_Atrial_Global"],
    "qrs_ms": ["QRS_Dur_Global"],
    "qt_ms": ["QT_Int_Global"],
    "qtc_ms": ["QT_IntCorr_Global", "QT_IntBazett_Global", "QT_IntFridericia_Global"],
    "pr_ms": ["PR_Int_Global", "PQ_Int_Global"],
    "axis_deg": ["R_AxisFrontal_Global", "QRS_AxisFront_Global"],
    "p_axis_deg": ["P_AxisFront_Global"],
    "t_axis_deg": ["T_AxisFront_Global"],
}

# Amplitude columns (microvolts) used to derive hypertrophy voltage criteria.
_AMP_UV = ("R_Amp_{lead}", "S_Amp_{lead}")


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, Real):
        f = float(value)
        # PTB-XL+ uses NaN sentinels; reject them.
        if f != f:  # NaN
            return None
        return f
    if isinstance(value, str):
        try:
            f = float(value)
            return None if f != f else f
        except ValueError:
            return None
    return None


def _first(raw: Mapping[str, Any], columns: list[str]) -> float | None:
    for column in columns:
        value = _num(raw.get(column))
        if value is not None:
            return value
    return None


def _amp_mv(raw: Mapping[str, Any], wave: str, lead: str) -> float | None:
    """Return a per-lead amplitude in mV (PTB-XL+ 12SL amplitudes are in mV)."""
    return _num(raw.get(f"{wave}_Amp_{lead}"))


def extract_measurements(raw_features: Mapping[str, Any]) -> dict[str, Any]:
    """Return canonical measurements + provenance from a raw PTB-XL+ feature row.

    ``raw_features`` is the merged 12SL/ECGDeli column->value mapping for one ECG.
    The return shape is::

        {
          "values": {"qtc_ms": 431.0, "pr_ms": 162.0, ...},   # canonical scalars
          "per_lead_st_mv": {"V2": 0.18, ...},                 # ST elevation per lead (mV)
          "sources": {"qtc_ms": "QT_IntCorr_Global", ...},     # provenance per canonical key
        }
    """
    values: dict[str, float] = {}
    sources: dict[str, str] = {}

    for canonical, columns in MEASUREMENT_SOURCES.items():
        for column in columns:
            value = _num(raw_features.get(column))
            if value is not None:
                values[canonical] = round(value, 3)
                sources[canonical] = column
                break

    # Derive heart rate from RR interval if no direct rate column was usable.
    if "heart_rate" not in values:
        rr = _num(raw_features.get("RR_Mean_Global"))
        if rr and rr > 0:
            values["heart_rate"] = round(60000.0 / rr, 1)
            sources["heart_rate"] = "derived_from_RR_Mean_Global"

    # Hypertrophy voltage criteria (mV).
    s_v1 = _amp_mv(raw_features, "S", "V1")
    r_v5 = _amp_mv(raw_features, "R", "V5")
    r_v6 = _amp_mv(raw_features, "R", "V6")
    if s_v1 is not None and (r_v5 is not None or r_v6 is not None):
        sokolow = abs(s_v1) + max(abs(r_v5 or 0.0), abs(r_v6 or 0.0))
        values["sokolow_lyon_mv"] = round(sokolow, 3)
        sources["sokolow_lyon_mv"] = "derived_S_Amp_V1+max(R_Amp_V5,R_Amp_V6)"

    r_avl = _amp_mv(raw_features, "R", "aVL")
    s_v3 = _amp_mv(raw_features, "S", "V3")
    if r_avl is not None and s_v3 is not None:
        values["cornell_mv"] = round(abs(r_avl) + abs(s_v3), 3)
        sources["cornell_mv"] = "derived_R_Amp_aVL+S_Amp_V3"

    # Per-lead ST elevation (mV) from ECGDeli ST_Elev_<lead> (microvolts).
    per_lead_st: dict[str, float] = {}
    for lead in LEADS:
        st = _num(raw_features.get(f"ST_Elev_{lead}"))
        if st is not None:
            per_lead_st[lead] = round(st, 3)  # ST_Elev_<lead> is already in mV

    return {"values": values, "per_lead_st_mv": per_lead_st, "sources": sources}


# --- Signal quality from PTB-XL's real noise annotations ------------------------

_NOISE_FIELDS = ("static_noise", "burst_noise", "baseline_drift", "electrodes_problems")


def _noise_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().strip(",").strip()
    return "" if text.lower() in {"", "nan", "none"} else text


def derive_signal_quality(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Derive signal quality from PTB-XL's actual noise fields.

    Replaces the audited heuristic that keyed off human-validation metadata.
    ``electrodes_problems`` / ``burst_noise`` => poor; ``static_noise`` /
    ``baseline_drift`` => borderline; otherwise acceptable. Affected leads are
    captured from the annotation text (e.g. "static_noise: I-V1").
    """
    reasons: list[str] = []
    affected_leads: list[str] = []
    status = "acceptable"

    severe = []
    mild = []
    for field in _NOISE_FIELDS:
        text = _noise_text(metadata.get(field))
        if not text:
            continue
        if field in ("electrodes_problems", "burst_noise"):
            severe.append((field, text))
        else:
            mild.append((field, text))
        for token in text.replace(";", ",").split(","):
            token = token.strip()
            if token and token not in affected_leads:
                affected_leads.append(token)

    if severe:
        status = "poor"
        reasons.extend(f"{field} present ({text})." for field, text in severe)
    elif mild:
        status = "borderline"
        reasons.extend(f"{field} present ({text})." for field, text in mild)

    # Provenance (NOT a quality signal): record validation status separately.
    validated = bool(metadata.get("validated_by_human"))
    return {
        "status": status,
        "reasons": reasons or (["No PTB-XL noise annotations recorded."] if status == "acceptable" else []),
        "affected_leads": affected_leads,
        "human_validated": validated,
    }
