from __future__ import annotations

import math
import random
from copy import deepcopy
from typing import Any

from .curation import curate_case
from .schemas import LEADS


LEAD_GAIN = {
    "I": 0.72,
    "II": 1.0,
    "III": 0.55,
    "aVR": -0.55,
    "aVL": 0.38,
    "aVF": 0.75,
    "V1": 0.45,
    "V2": 0.7,
    "V3": 0.95,
    "V4": 1.15,
    "V5": 1.05,
    "V6": 0.85,
}


def _gaussian(x: float, center: float, width: float, amplitude: float) -> float:
    return amplitude * math.exp(-((x - center) ** 2) / (2 * width * width))


def _beat_value(phase: float, lead: str, morphology: str, st_shift: float, t_inversion: bool) -> float:
    gain = LEAD_GAIN[lead]
    p_wave = 0.08 * gain * _gaussian(phase, 0.18, 0.035, 1.0)
    q_wave = -0.10 * abs(gain) * _gaussian(phase, 0.36, 0.012, 1.0)
    r_wave = 1.05 * gain * _gaussian(phase, 0.39, 0.014, 1.0)
    s_wave = -0.22 * abs(gain) * _gaussian(phase, 0.43, 0.018, 1.0)
    t_amp = (-0.24 if t_inversion else 0.28) * gain
    t_wave = t_amp * _gaussian(phase, 0.66, 0.085, 1.0)

    if morphology == "rbbb" and lead in {"V1", "V2"}:
        r_wave += 0.55 * _gaussian(phase, 0.47, 0.022, 1.0)
        s_wave -= 0.1 * _gaussian(phase, 0.51, 0.03, 1.0)
    if morphology == "rbbb" and lead in {"I", "V5", "V6"}:
        s_wave -= 0.38 * _gaussian(phase, 0.50, 0.032, 1.0)
    if morphology == "lbbb" and lead in {"I", "aVL", "V5", "V6"}:
        r_wave += 0.35 * _gaussian(phase, 0.46, 0.04, 1.0)
        q_wave = 0
    if morphology == "lbbb" and lead in {"V1", "V2"}:
        r_wave *= 0.25
        s_wave -= 0.45 * _gaussian(phase, 0.48, 0.04, 1.0)
    if morphology == "lvh" and lead in {"V4", "V5", "V6"}:
        r_wave *= 1.65
        t_wave *= -0.4
    if morphology == "af":
        p_wave = 0.0
        p_wave += 0.035 * math.sin(phase * 2 * math.pi * 6)
    if morphology == "complete_block":
        # The atrial rhythm is added independently in ``_make_waveform``. Keeping
        # it out of the ventricular template is what makes P waves march through
        # the slower escape rhythm instead of falsely preserving 1:1 conduction.
        p_wave = 0.0

    st_segment = st_shift if 0.46 <= phase <= 0.58 else 0.0
    return p_wave + q_wave + r_wave + s_wave + t_wave + st_segment


def _make_waveform(
    case_id: str,
    rate_bpm: int,
    morphology: str = "normal",
    st_by_lead: dict[str, float] | None = None,
    t_inversions: set[str] | None = None,
    irregular: bool = False,
    noise: float = 0.012,
    atrial_rate_bpm: int | None = None,
) -> dict[str, Any]:
    fs = 100
    duration = 10
    samples = fs * duration
    rng = random.Random(case_id)
    rr = 60.0 / rate_bpm
    atrial_rr = 60.0 / atrial_rate_bpm if atrial_rate_bpm else None
    beats = [0.15]
    while beats[-1] < duration + rr:
        jitter = rng.uniform(-0.18, 0.18) if irregular else rng.uniform(-0.02, 0.02)
        beats.append(beats[-1] + max(0.42, rr + jitter))

    signal: dict[str, list[float]] = {lead: [] for lead in LEADS}
    for i in range(samples):
        t = i / fs
        beat_start = max((beat for beat in beats if beat <= t), default=beats[0])
        phase = (t - beat_start) / rr
        atrial_phase = (t % atrial_rr) / atrial_rr if atrial_rr else None
        baseline = 0.025 * math.sin(2 * math.pi * 0.27 * t)
        for lead in LEADS:
            st_shift = (st_by_lead or {}).get(lead, 0.0)
            value = baseline
            if 0 <= phase < 1.0:
                value += _beat_value(phase, lead, morphology, st_shift, lead in (t_inversions or set()))
            if atrial_phase is not None:
                value += 0.08 * LEAD_GAIN[lead] * _gaussian(atrial_phase, 0.18, 0.035, 1.0)
            value += rng.uniform(-noise, noise)
            signal[lead].append(round(value, 4))
    return {
        "sampling_frequency": fs,
        "duration_sec": duration,
        "leads": LEADS.copy(),
        "signal": signal,
    }


def _median_beat_excerpt(waveform: dict[str, Any], leads: tuple[str, ...] = ("II", "V2")) -> dict[str, Any]:
    fs = int(waveform["sampling_frequency"])
    start_idx = int(0.15 * fs)
    end_idx = int(0.95 * fs)
    step = max(1, (end_idx - start_idx) // 80)
    beats = {}
    for lead in leads:
        values = waveform["signal"].get(lead, [])
        beats[lead] = {
            "timeStartSec": round(start_idx / fs, 3),
            "timeEndSec": round(end_idx / fs, 3),
            "samplingFrequency": fs,
            "samplesMv": values[start_idx:end_idx:step],
            "source": "fixture_synthetic_median_beat",
        }
    return {
        "source": "fixture_synthetic",
        "description": "Synthetic median-beat excerpt derived from the fixture waveform for local product verification.",
        "artifact_refs": [],
        "beats": beats,
    }


def _rois_for_st_elevation(leads: list[str], concept: str = "st_elevation") -> list[dict[str, Any]]:
    return [
        {
            "lead": lead,
            "timeStartSec": 2.46,
            "timeEndSec": 2.58,
            "ampMinMv": 0.0,
            "ampMaxMv": 0.55,
            "label": "ST segment elevation",
            "concept": concept,
            "source": "fixture_curated",
            "confidence": "high",
        }
        for lead in leads
    ]


def _base_case(
    case_id: str,
    display_id: str,
    report: str,
    scp_codes: dict[str, float],
    superclass: list[str],
    subclass: list[str],
    statements: list[str],
    features: dict[str, Any],
    waveform: dict[str, Any],
    rois: list[dict[str, Any]] | None = None,
    signal_quality: str = "acceptable",
    stem: str = "A medical student is reviewing a teaching ECG.",
    teaching_points: list[str] | None = None,
) -> dict[str, Any]:
    case: dict[str, Any] = {
        "case_id": case_id,
        "display_id": display_id,
        "clinical_stem": stem,
        "waveform": {
            "path": None,
            "sampling_frequency": waveform["sampling_frequency"],
            "duration_sec": waveform["duration_sec"],
            "leads": waveform["leads"],
            "source": "fixture",
        },
        "waveform_data": waveform["signal"],
        "ptbxl": {
            "scp_codes": scp_codes,
            "diagnostic_superclass": superclass,
            "diagnostic_subclass": subclass,
            "report": report,
            "fold": 1,
            "metadata": {"fixture": True, "non_clinical_demo_data": True},
        },
        "ptbxl_plus": {
            "statements": statements,
            "features": features,
            "fiducials": {"rois": rois or []},
            "median_beats": _median_beat_excerpt(waveform),
            "measurements": features,
        },
        "signal_quality": {
            "status": signal_quality,
            "reasons": [] if signal_quality == "acceptable" else ["Synthetic noise/discordance fixture."],
        },
        "teaching_points": teaching_points or statements,
        "source": "fixture",
    }
    case.update(curate_case(case))
    return case


def build_fixture_cases() -> list[dict[str, Any]]:
    cases = [
        _base_case(
            "fixture-normal-001",
            "Demo Normal 001",
            "Normal sinus rhythm. Normal ECG.",
            {"NORM": 100.0, "SR": 100.0},
            ["NORM"],
            ["NORM"],
            ["Normal ECG", "Sinus rhythm", "Normal axis"],
            {
                "heart_rate": 72,
                "pr_ms": 160,
                "qrs_ms": 92,
                "qt_ms": 380,
                "qtc_ms": 416,
                "axis_deg": 48,
            },
            _make_waveform("fixture-normal-001", 72),
            stem="Healthy adult with no cardiopulmonary symptoms.",
            teaching_points=[
                "Rate is about 72 bpm with regular R-R intervals.",
                "P waves precede each QRS in lead II, supporting sinus rhythm.",
                "Intervals and axis are in the normal teaching range.",
            ],
        ),
        _base_case(
            "fixture-anterior-mi-001",
            "Demo Anterior MI 001",
            "Anterior myocardial infarction with ST elevation in V2-V4.",
            {"AMI": 100.0, "ASMI": 80.0, "STE": 100.0},
            ["MI", "STTC"],
            ["AMI", "ASMI"],
            ["Anterior myocardial infarction", "ST elevation in anterior precordial leads"],
            {
                "heart_rate": 86,
                "pr_ms": 158,
                "qrs_ms": 94,
                "qt_ms": 386,
                "qtc_ms": 462,
                "axis_deg": 35,
                "st_elevation_v2_mv": 0.32,
                "st_elevation_v3_mv": 0.36,
                "st_elevation_v4_mv": 0.25,
            },
            _make_waveform(
                "fixture-anterior-mi-001",
                86,
                st_by_lead={"V2": 0.28, "V3": 0.34, "V4": 0.26},
                t_inversions={"V2", "V3"},
            ),
            rois=_rois_for_st_elevation(["V2", "V3", "V4"], "anterior_mi"),
            stem="A patient has acute chest pressure. This fixture is for education only.",
            teaching_points=[
                "The strongest deterministic teaching signal is anterior ST elevation.",
                "Use the precordial leads V2-V4 for localization in this demo case.",
                "The tutor may highlight ST segments, but diagnosis comes from the case packet.",
            ],
        ),
        _base_case(
            "fixture-inferior-mi-001",
            "Demo Inferior MI 001",
            "Inferior myocardial infarction with ST elevation in II, III, and aVF.",
            {"IMI": 100.0, "STE": 90.0},
            ["MI", "STTC"],
            ["IMI"],
            ["Inferior myocardial infarction", "ST elevation in inferior leads"],
            {
                "heart_rate": 64,
                "pr_ms": 170,
                "qrs_ms": 96,
                "qt_ms": 392,
                "qtc_ms": 405,
                "axis_deg": 72,
                "st_elevation_ii_mv": 0.25,
                "st_elevation_iii_mv": 0.28,
                "st_elevation_avf_mv": 0.24,
            },
            _make_waveform(
                "fixture-inferior-mi-001",
                64,
                st_by_lead={"II": 0.25, "III": 0.28, "aVF": 0.24, "aVL": -0.08},
            ),
            rois=_rois_for_st_elevation(["II", "III", "aVF"], "inferior_mi"),
            stem="Chest discomfort with inferior lead ST-segment changes in a teaching fixture.",
            teaching_points=[
                "Inferior localization uses contiguous leads II, III, and aVF.",
                "Small reciprocal depression is represented in aVL in this synthetic waveform.",
            ],
        ),
        _base_case(
            "fixture-rbbb-001",
            "Demo RBBB 001",
            "Sinus rhythm with complete right bundle branch block.",
            {"SR": 100.0, "CRBBB": 100.0},
            ["CD"],
            ["CRBBB"],
            ["Right bundle branch block", "QRS duration is prolonged"],
            {
                "heart_rate": 78,
                "pr_ms": 166,
                "qrs_ms": 142,
                "qt_ms": 410,
                "qtc_ms": 467,
                "axis_deg": 92,
            },
            _make_waveform("fixture-rbbb-001", 78, morphology="rbbb"),
            rois=[
                {
                    "lead": "V1",
                    "timeStartSec": 2.36,
                    "timeEndSec": 2.52,
                    "ampMinMv": -0.2,
                    "ampMaxMv": 1.2,
                    "label": "Wide terminal R' pattern",
                    "concept": "right_bundle_branch_block",
                    "source": "fixture_curated",
                    "confidence": "high",
                },
                {
                    "lead": "V6",
                    "timeStartSec": 2.38,
                    "timeEndSec": 2.56,
                    "ampMinMv": -0.7,
                    "ampMaxMv": 0.8,
                    "label": "Broad terminal S wave",
                    "concept": "right_bundle_branch_block",
                    "source": "fixture_curated",
                    "confidence": "high",
                },
            ],
            stem="Routine ECG with widened QRS.",
            teaching_points=[
                "QRS duration is wide at 142 ms.",
                "V1 and V6 are useful teaching leads for RBBB morphology.",
            ],
        ),
        _base_case(
            "fixture-af-001",
            "Demo AF 001",
            "Atrial fibrillation with rapid ventricular response.",
            {"AFIB": 100.0},
            ["HYP"],
            ["AFIB"],
            ["Atrial fibrillation", "Irregularly irregular rhythm", "No consistent P waves"],
            {
                "heart_rate": 118,
                "pr_ms": None,
                "qrs_ms": 88,
                "qt_ms": 320,
                "qtc_ms": 449,
                "axis_deg": 52,
                "rr_irregularity_index": 0.32,
            },
            _make_waveform("fixture-af-001", 118, morphology="af", irregular=True, noise=0.018),
            stem="Palpitations in a teaching-only rhythm fixture.",
            teaching_points=[
                "The teaching target is rhythm: irregularly irregular timing without consistent P waves.",
                "Do not measure PR interval when no consistent P wave is available.",
            ],
        ),
        _base_case(
            "fixture-long-qtc-001",
            "Demo Long QTc 001",
            "Sinus rhythm with prolonged QTc.",
            {"SR": 100.0, "LNGQT": 100.0},
            ["STTC"],
            ["LNGQT"],
            ["Prolonged QTc interval", "Sinus rhythm"],
            {
                "heart_rate": 68,
                "pr_ms": 154,
                "qrs_ms": 86,
                "qt_ms": 510,
                "qtc_ms": 542,
                "axis_deg": 38,
            },
            _make_waveform("fixture-long-qtc-001", 68),
            rois=[
                {
                    "lead": "II",
                    "timeStartSec": 2.36,
                    "timeEndSec": 2.86,
                    "ampMinMv": -0.3,
                    "ampMaxMv": 1.1,
                    "label": "QT interval",
                    "concept": "qt_interval",
                    "source": "fixture_curated",
                    "confidence": "high",
                }
            ],
            stem="Medication review ECG in a teaching-only QT fixture.",
            teaching_points=[
                "QTc is prolonged in the grounded fixture measurements.",
                "The tutor can discuss QTc only because the case packet includes a QTc value.",
            ],
        ),
        _base_case(
            "fixture-lvh-001",
            "Demo LVH 001",
            "Sinus rhythm with left ventricular hypertrophy voltage pattern.",
            {"SR": 100.0, "LVH": 100.0},
            ["HYP"],
            ["LVH"],
            ["Left ventricular hypertrophy", "High voltage in lateral precordial leads"],
            {
                "heart_rate": 74,
                "pr_ms": 162,
                "qrs_ms": 98,
                "qt_ms": 396,
                "qtc_ms": 438,
                "axis_deg": -18,
                "sokolow_lyon_mv": 4.2,
            },
            _make_waveform("fixture-lvh-001", 74, morphology="lvh", t_inversions={"V5", "V6"}),
            stem="Hypertension history in a teaching-only voltage fixture.",
            teaching_points=[
                "High lateral precordial voltage supports LVH practice.",
                "Voltage alone is taught cautiously and not as a clinical diagnosis.",
            ],
        ),
        _base_case(
            "fixture-uncertain-noisy-001",
            "Demo Uncertain 001",
            "Noisy tracing with discordant automated statements.",
            {"NORM": 50.0, "ISC_": 50.0},
            ["NORM", "STTC"],
            ["NST"],
            ["Normal ECG", "Nonspecific ST-T abnormality"],
            {
                "heart_rate": 91,
                "qrs_ms": 104,
                "axis_deg": 20,
            },
            _make_waveform("fixture-uncertain-noisy-001", 91, noise=0.08),
            signal_quality="poor",
            stem="Internal fixture used to demonstrate exclusion from student workflows.",
            teaching_points=[
                "This case should be withheld from default student workflows because evidence is discordant.",
            ],
        ),
    ]
    return [deepcopy(case) for case in cases]
