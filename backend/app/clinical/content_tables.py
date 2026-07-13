"""The danger/acuity dimension for Clinical Decisions (task #6), as typed data.

EDUCATIONAL USE ONLY. Every value below is a teaching signal, NOT a patient risk score.
Authored from standard ACLS/AHA teaching references; it is NOT individually clinician-
reviewed (no formal clinician review is planned) — treat the values as best-effort defaults
to tune by playtest, and keep the platform's educational-only disclaimer visible. Keyed by
ontology concept ids; an import-time assertion guarantees coverage stays consistent with the
ontology.

Consumed by the harness (acuity-cap + required-safety + symptom-causality checks) and by
the grader. Concepts with no entry default conservatively (cap=workup, no required safety
actions) — they can never be keyed as urgent without explicit evidence.
"""

from __future__ import annotations

from typing import Callable

from ..ontology import CONCEPT_BY_ID
from .constants import SAFETY_TOKENS, SYMPTOMS
from .schemas import AcuityTier, ActionUrgency, Strength

# --- base acuity per concept (the inherent teaching danger) -----------------------
ACUITY_BASE: dict[str, AcuityTier] = {
    "normal_ecg": "none",
    "rate": "none",
    "sinus_rhythm": "none",
    "axis_normal": "none",
    "left_axis_deviation": "low",
    "right_axis_deviation": "low",
    "r_wave_progression": "low",
    "atrial_fibrillation": "moderate",
    "atrial_flutter": "moderate",
    "supraventricular_tachycardia": "moderate",
    "wide_complex_tachycardia": "high",
    "bradycardia": "low",
    "av_block_first_degree": "low",
    "av_block_second_degree_mobitz_i": "low",
    "av_block_second_degree_mobitz_ii": "moderate_high",
    "av_block_third_degree": "high",
    "qrs_duration": "low",
    "right_bundle_branch_block": "low",
    "left_bundle_branch_block": "moderate",
    "incomplete_right_bundle_branch_block": "low",
    "nonspecific_intraventricular_conduction_delay": "low",
    "left_anterior_fascicular_block": "low",
    "left_posterior_fascicular_block": "low",
    "wolff_parkinson_white": "moderate",
    "paced_rhythm": "low",
    "premature_ventricular_complex": "low",
    "premature_atrial_complex": "none",
    "left_ventricular_hypertrophy": "low",
    "right_ventricular_hypertrophy": "low",
    "atrial_enlargement": "low",
    "st_elevation": "high",
    "st_depression": "moderate",
    "t_wave_inversion": "low",
    "nonspecific_st_t_change": "low",
    "myocardial_infarction": "moderate",
    "anterior_mi": "moderate",
    "inferior_mi": "moderate",
    "lateral_mi": "moderate",
    "septal_mi": "moderate",
    "posterior_mi": "moderate",
    "myocardial_ischemia": "moderate",
    "pathologic_q_waves": "low",
    "qt_interval": "low",
    "qtc_prolongation": "moderate",
    "electrolyte_drug_pattern": "moderate",
    "pericarditis_pattern": "moderate",
}

# --- §16B6 acuity cap: the highest action urgency a concept may be keyed to without
# extra evidence (serial change / acute dataset). On the chronic corpus, MI/ischemia
# concepts cap at workup — they cannot key cath-lab activation. ----------------------
ACUITY_CAP_BY_CONCEPT: dict[str, ActionUrgency] = {
    "normal_ecg": "routine",
    "rate": "routine",
    "sinus_rhythm": "routine",
    "axis_normal": "routine",
    "left_axis_deviation": "routine",
    "right_axis_deviation": "routine",
    "r_wave_progression": "routine",
    "premature_atrial_complex": "routine",
    "premature_ventricular_complex": "workup",
    "atrial_fibrillation": "admit",
    "atrial_flutter": "admit",
    "supraventricular_tachycardia": "urgent",
    "wide_complex_tachycardia": "act_now",
    "bradycardia": "admit",
    "av_block_first_degree": "routine",
    "av_block_second_degree_mobitz_i": "workup",
    "av_block_second_degree_mobitz_ii": "urgent",
    "av_block_third_degree": "act_now",
    "qrs_duration": "routine",
    "right_bundle_branch_block": "workup",
    "left_bundle_branch_block": "workup",
    "incomplete_right_bundle_branch_block": "routine",
    "nonspecific_intraventricular_conduction_delay": "workup",
    "left_anterior_fascicular_block": "routine",
    "left_posterior_fascicular_block": "workup",
    "wolff_parkinson_white": "admit",
    "paced_rhythm": "workup",
    "left_ventricular_hypertrophy": "workup",
    "right_ventricular_hypertrophy": "workup",
    "atrial_enlargement": "routine",
    # ST/MI/ischemia: chronic corpus → workup ceiling unless acute evidence upgrades it.
    "st_elevation": "urgent",
    "st_depression": "admit",
    "t_wave_inversion": "workup",
    "nonspecific_st_t_change": "workup",
    "myocardial_infarction": "workup",
    "anterior_mi": "workup",
    "inferior_mi": "workup",
    "lateral_mi": "workup",
    "septal_mi": "workup",
    "posterior_mi": "workup",
    "myocardial_ischemia": "admit",
    "pathologic_q_waves": "workup",
    "qt_interval": "routine",
    "qtc_prolongation": "admit",
    "electrolyte_drug_pattern": "admit",
    "pericarditis_pattern": "admit",
}

# --- §16B5 required safety actions: for these high-acuity concepts, an ideal/acceptable
# option MUST carry at least one of these tokens, else the harness/grader caps it at
# under_triage. (Encodes "atropine-only ≠ acceptable for symptomatic complete block".) -
REQUIRED_SAFETY_ACTIONS: dict[str, list[str]] = {
    "av_block_third_degree": ["pacing_pads", "tcp_ready", "call_help", "bedside_now"],
    "av_block_second_degree_mobitz_ii": ["tcp_ready", "call_help", "bedside_now"],
    "wide_complex_tachycardia": ["synchronized_cardioversion", "defib_pads", "act_now"],
}

# --- §16B2 symptom-causality matrix: per concept, which symptoms it may explain /
# may contextualize / must-not-explain (without extra evidence). The harness fails an
# item whose ideal option keys a must_not_explain finding as the symptom's cause. ------
SYMPTOM_CAUSALITY: dict[str, dict[str, Strength]] = {
    "av_block_third_degree": {
        "syncope": "may_explain",
        "presyncope": "may_explain",
        "dizziness": "may_explain",
        "lightheadedness": "may_explain",
        "fatigue": "may_contextualize",
    },
    "av_block_second_degree_mobitz_ii": {
        "syncope": "may_explain",
        "presyncope": "may_explain",
        "dizziness": "may_explain",
    },
    "av_block_first_degree": {
        "syncope": "must_not_explain",
        "presyncope": "must_not_explain",
        "palpitations": "must_not_explain",
        "dizziness": "may_contextualize",
    },
    "bradycardia": {
        "syncope": "may_contextualize",
        "presyncope": "may_contextualize",
        "dizziness": "may_contextualize",
        "fatigue": "may_contextualize",
    },
    "wide_complex_tachycardia": {
        "palpitations": "may_explain",
        "lightheadedness": "may_explain",
        "presyncope": "may_explain",
        "syncope": "may_explain",
        "chest_pain": "may_contextualize",
        "dyspnea": "may_contextualize",
    },
    "supraventricular_tachycardia": {
        "palpitations": "may_explain",
        "lightheadedness": "may_explain",
        "presyncope": "may_explain",
    },
    "atrial_fibrillation": {
        "palpitations": "may_explain",
        "dyspnea": "may_contextualize",
        "lightheadedness": "may_contextualize",
    },
    "atrial_flutter": {
        "palpitations": "may_explain",
        "dyspnea": "may_contextualize",
    },
    "qtc_prolongation": {
        "syncope": "may_contextualize",
        "presyncope": "may_contextualize",
        "palpitations": "may_contextualize",
    },
    "st_depression": {
        "chest_pain": "may_contextualize",
        "dyspnea": "may_contextualize",
    },
    "myocardial_ischemia": {
        "chest_pain": "may_contextualize",
    },
    "nonspecific_st_t_change": {
        "chest_pain": "may_contextualize",
    },
}

# --- §3 measurement-driven acuity adjustment: bump the derived acuity tier when the
# packet features show a dangerous rate, etc. Each rule reads (features, concepts) and
# returns a tier-rank delta. -------------------------------------------------------
AdjustRule = Callable[[dict, set], int]


def _afib_flutter_fast(features: dict, concepts: set) -> int:
    hr = features.get("heart_rate") or 0
    fast_rhythms = {"atrial_fibrillation", "atrial_flutter", "supraventricular_tachycardia"}
    return 1 if (concepts & fast_rhythms and hr >= 150) else 0


def _severe_bradycardia(features: dict, concepts: set) -> int:
    hr = features.get("heart_rate")
    return 1 if (hr is not None and hr <= 40) else 0


def _markedly_prolonged_qtc(features: dict, concepts: set) -> int:
    qtc = features.get("qtc_ms") or 0
    return 1 if ("qtc_prolongation" in concepts and qtc >= 500) else 0


ACUITY_MEASUREMENT_ADJUST: list[AdjustRule] = [
    _afib_flutter_fast,
    _severe_bradycardia,
    _markedly_prolonged_qtc,
]


# --- import-time coverage assertions (keep tables consistent with the ontology) ----
def _validate_tables() -> None:
    for name, table in (("ACUITY_BASE", ACUITY_BASE), ("ACUITY_CAP_BY_CONCEPT", ACUITY_CAP_BY_CONCEPT)):
        unknown = [k for k in table if k not in CONCEPT_BY_ID]
        if unknown:
            raise ValueError(f"{name} has non-ontology concepts: {unknown}")
    # ACUITY_BASE must cover every concept so the harness always has a base tier.
    missing = [c for c in CONCEPT_BY_ID if c not in ACUITY_BASE]
    if missing:
        raise ValueError(f"ACUITY_BASE is missing concepts: {missing}")
    for concept, tokens in REQUIRED_SAFETY_ACTIONS.items():
        if concept not in CONCEPT_BY_ID:
            raise ValueError(f"REQUIRED_SAFETY_ACTIONS has non-ontology concept: {concept}")
        bad = [t for t in tokens if t not in SAFETY_TOKENS]
        if bad:
            raise ValueError(f"REQUIRED_SAFETY_ACTIONS[{concept}] has unknown tokens: {bad}")
    for concept, mapping in SYMPTOM_CAUSALITY.items():
        if concept not in CONCEPT_BY_ID:
            raise ValueError(f"SYMPTOM_CAUSALITY has non-ontology concept: {concept}")
        bad = [s for s in mapping if s not in SYMPTOMS]
        if bad:
            raise ValueError(f"SYMPTOM_CAUSALITY[{concept}] has unknown symptoms: {bad}")


_validate_tables()
