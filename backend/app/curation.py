from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .ontology import CONCEPTS
from .schemas import ConceptConfidence


TIER_ORDER = {"A": 4, "B": 3, "C": 2, "D": 1}
MI_TERRITORY_LEADS = {
    "anterior_mi": ["V1", "V2", "V3", "V4"],
    "septal_mi": ["V1", "V2"],
    "lateral_mi": ["I", "aVL", "V5", "V6"],
    "inferior_mi": ["II", "III", "aVF"],
}
ABNORMAL_CONCEPTS = {
    "atrial_fibrillation",
    "atrial_flutter",
    "supraventricular_tachycardia",
    "wide_complex_tachycardia",
    "bradycardia",
    "av_block_first_degree",
    "av_block_second_degree_mobitz_i",
    "av_block_second_degree_mobitz_ii",
    "av_block_third_degree",
    "left_axis_deviation",
    "right_axis_deviation",
    "right_bundle_branch_block",
    "left_bundle_branch_block",
    "incomplete_right_bundle_branch_block",
    "nonspecific_intraventricular_conduction_delay",
    "left_anterior_fascicular_block",
    "left_posterior_fascicular_block",
    "wolff_parkinson_white",
    "paced_rhythm",
    "premature_ventricular_complex",
    "premature_atrial_complex",
    "left_ventricular_hypertrophy",
    "right_ventricular_hypertrophy",
    "atrial_enlargement",
    "st_elevation",
    "st_depression",
    "t_wave_inversion",
    "nonspecific_st_t_change",
    "myocardial_ischemia",
    "pathologic_q_waves",
    "myocardial_infarction",
    "anterior_mi",
    "inferior_mi",
    "lateral_mi",
    "septal_mi",
    "posterior_mi",
    "qtc_prolongation",
    "electrolyte_drug_pattern",
    "pericarditis_pattern",
}


# Keywords are matched (substring) against the report + the INDEPENDENT PTB-XL+ 12SL
# statements (clinical English), so a hit is genuine cross-source concordance with the
# PTB-XL cardiologist SCP label — the second evidence source for Tier A.
CONCEPT_KEYWORDS: dict[str, list[str]] = {
    "normal_ecg": ["normal ecg", "normal sinus rhythm", "normal"],
    "rate": ["rate", "heart rate"],
    "sinus_rhythm": ["sinus rhythm", "normal sinus"],
    "atrial_fibrillation": ["atrial fibrillation", "afib"],
    "atrial_flutter": ["atrial flutter", "flutter"],
    "supraventricular_tachycardia": ["supraventricular tachycardia", "svt", "paroxysmal supraventricular"],
    "wide_complex_tachycardia": ["wide complex tachycardia"],  # VT/VF absent from PTB-XL (no SCP code)
    "bradycardia": ["bradycardia"],
    "av_block_first_degree": ["first degree", "1st degree", "prolonged pr"],
    "av_block_second_degree_mobitz_i": ["mobitz i", "wenckebach"],
    "av_block_second_degree_mobitz_ii": ["mobitz ii", "second degree"],
    "av_block_third_degree": ["third degree", "complete heart block", "complete av block"],
    "axis_normal": ["normal axis"],
    "left_axis_deviation": ["left axis deviation", "left axis"],
    "right_axis_deviation": ["right axis deviation", "right axis"],
    "qrs_duration": ["qrs duration", "wide qrs", "qrs widening"],
    "right_bundle_branch_block": ["right bundle branch block", "rbbb"],
    "left_bundle_branch_block": ["left bundle branch block", "lbbb"],
    "incomplete_right_bundle_branch_block": ["incomplete right bundle"],
    "nonspecific_intraventricular_conduction_delay": [
        "nonspecific intraventricular conduction",
        "intraventricular conduction delay",
        "ivcd",
    ],
    "left_anterior_fascicular_block": ["anterior fascicular", "fascicular block", "monofascicular"],
    "left_posterior_fascicular_block": ["posterior fascicular"],
    "wolff_parkinson_white": ["wolff-parkinson", "wolff parkinson", "wpw", "pre-excitation", "preexcitation"],
    "paced_rhythm": ["pacing", "pacemaker", "paced"],
    "premature_ventricular_complex": ["ventricular premature", "premature ventricular"],
    "premature_atrial_complex": ["atrial premature", "premature atrial", "supraventricular premature"],
    "r_wave_progression": ["r wave progression", "poor r wave"],
    "left_ventricular_hypertrophy": ["left ventricular hypertrophy", "ventricular hypertrophy", "voltage criteria"],
    "right_ventricular_hypertrophy": ["right ventricular hypertrophy"],
    "atrial_enlargement": ["atrial enlargement", "atrial overload", "atrial abnormality"],
    "st_elevation": ["st elevation", "elevated st"],
    "st_depression": ["st depression", "depressed st"],
    "t_wave_inversion": ["t wave inversion", "inverted t", "t-wave inversion"],
    "nonspecific_st_t_change": ["nonspecific st", "st-t abnormality", "st segment change", "st-t change", "t wave abnormal", "nonspecific t"],
    "myocardial_ischemia": ["ischemi", "ischaemi"],
    "pathologic_q_waves": ["q wave", "q-wave", "pathologic q"],
    "myocardial_infarction": ["myocardial infarction", "infarction", "infarct"],
    "anterior_mi": ["anterior infarct", "anterior myocardial", "anteroseptal infarct", "anteroseptal myocardial"],
    "inferior_mi": ["inferior infarct", "inferior myocardial"],
    "lateral_mi": ["lateral infarct", "lateral myocardial"],
    "septal_mi": ["septal infarct", "septal myocardial", "anteroseptal"],
    "posterior_mi": ["posterior infarct", "posterior myocardial"],
    "qt_interval": ["qt interval", "qtc"],
    "qtc_prolongation": ["prolonged qt", "long qt", "qt prolongation", "prolonged qtc"],
    "electrolyte_drug_pattern": ["electrolyt", "digitalis", "digoxin", "hyperkal", "hypokal", "drug effect"],
    "pericarditis_pattern": ["pericarditis", "diffuse st elevation", "pr depression"],
}


# Full PTB-XL SCP-ECG vocabulary -> concepts. Presence-based (PTB-XL records form/
# rhythm codes at likelihood 0, so a likelihood filter would delete the entire ST-T
# vocabulary — the V1 zero-coverage bug, compounded by a "STE" vs real "STE_" typo).
SCP_TO_CONCEPTS: dict[str, list[str]] = {
    # --- normal / rhythm ---
    "NORM": ["normal_ecg", "sinus_rhythm"],
    "SR": ["sinus_rhythm"],
    "SBRAD": ["bradycardia", "sinus_rhythm"],
    "SARRH": ["sinus_rhythm"],
    "AFIB": ["atrial_fibrillation"],
    "AFLT": ["atrial_flutter"],
    "SVTAC": ["supraventricular_tachycardia"],
    "PSVT": ["supraventricular_tachycardia"],
    "PACE": ["paced_rhythm"],
    "PVC": ["premature_ventricular_complex"],
    "PAC": ["premature_atrial_complex"],
    # --- AV conduction ---
    "1AVB": ["av_block_first_degree"],
    "LPR": ["av_block_first_degree"],
    "2AVB": ["av_block_second_degree_mobitz_ii"],
    "3AVB": ["av_block_third_degree"],
    # --- intraventricular conduction ---
    "CRBBB": ["right_bundle_branch_block", "qrs_duration"],
    "IRBBB": ["incomplete_right_bundle_branch_block"],
    "CLBBB": ["left_bundle_branch_block", "qrs_duration"],
    "ILBBB": ["left_bundle_branch_block"],
    "IVCD": ["nonspecific_intraventricular_conduction_delay", "qrs_duration"],
    "LAFB": ["left_anterior_fascicular_block", "left_axis_deviation"],
    "LPFB": ["left_posterior_fascicular_block", "right_axis_deviation"],
    "WPW": ["wolff_parkinson_white"],
    # --- hypertrophy / chambers ---
    "LVH": ["left_ventricular_hypertrophy"],
    "VCLVH": ["left_ventricular_hypertrophy"],
    "SEHYP": ["left_ventricular_hypertrophy"],
    "RVH": ["right_ventricular_hypertrophy"],
    "LAO/LAE": ["atrial_enlargement"],
    "RAO/RAE": ["atrial_enlargement"],
    # --- MI by territory (PTB-XL infarcts are overwhelmingly OLD/established) ---
    "IMI": ["myocardial_infarction", "inferior_mi"],
    "AMI": ["myocardial_infarction", "anterior_mi"],
    "ASMI": ["myocardial_infarction", "anterior_mi", "septal_mi"],
    "ALMI": ["myocardial_infarction", "anterior_mi", "lateral_mi"],
    "ILMI": ["myocardial_infarction", "inferior_mi", "lateral_mi"],
    "LMI": ["myocardial_infarction", "lateral_mi"],
    "PMI": ["myocardial_infarction", "posterior_mi"],
    "IPMI": ["myocardial_infarction", "inferior_mi", "posterior_mi"],
    "IPLMI": ["myocardial_infarction", "inferior_mi", "posterior_mi", "lateral_mi"],
    "QWAVE": ["pathologic_q_waves"],
    # --- ischemia / injury (ST-T ischemia, NOT an established infarct label) ---
    "ISC_": ["myocardial_ischemia"],
    "ISCAL": ["myocardial_ischemia"],
    "ISCAS": ["myocardial_ischemia"],
    "ISCIL": ["myocardial_ischemia"],
    "ISCIN": ["myocardial_ischemia"],
    "ISCLA": ["myocardial_ischemia"],
    "ISCAN": ["myocardial_ischemia"],
    "INJAS": ["myocardial_ischemia"],
    "INJAL": ["myocardial_ischemia"],
    "INJIN": ["myocardial_ischemia"],
    "INJIL": ["myocardial_ischemia"],
    "INJLA": ["myocardial_ischemia"],
    # --- ST-T form findings (all likelihood-0 in PTB-XL; presence-based) ---
    "STE_": ["st_elevation"],
    "STD_": ["st_depression"],
    "INVT": ["t_wave_inversion"],
    "NT_": ["nonspecific_st_t_change"],
    "TAB_": ["nonspecific_st_t_change"],
    "LOWT": ["nonspecific_st_t_change"],
    "NDT": ["nonspecific_st_t_change"],
    "NST_": ["nonspecific_st_t_change"],
    "ANEUR": ["nonspecific_st_t_change"],
    # --- repolarization / electrolyte / drug ---
    "LNGQT": ["qt_interval", "qtc_prolongation"],
    "EL": ["electrolyte_drug_pattern"],
    "DIG": ["electrolyte_drug_pattern"],
}


def tier_from_score(score: float, hard_limit: str | None = None) -> str:
    if score >= 0.82:
        tier = "A"
    elif score >= 0.58:
        tier = "B"
    elif score >= 0.35:
        tier = "C"
    else:
        tier = "D"
    if hard_limit is not None and TIER_ORDER[tier] > TIER_ORDER[hard_limit]:
        return hard_limit
    return tier


def _flatten_text(case: Mapping[str, Any]) -> str:
    parts: list[str] = []
    ptbxl = case.get("ptbxl", {}) or {}
    ptbxl_plus = case.get("ptbxl_plus", {}) or {}
    for key in ("report", "diagnostic_superclass", "diagnostic_subclass"):
        value = ptbxl.get(key)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(item) for item in value)
    for key in ("statements",):
        value = ptbxl_plus.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
        elif isinstance(value, str):
            parts.append(value)
    return " ".join(parts).lower()


def _scp_concepts(case: Mapping[str, Any]) -> set[str]:
    scp = ((case.get("ptbxl") or {}).get("scp_codes") or {})
    concepts: set[str] = set()
    for code in scp.keys():
        concepts.update(SCP_TO_CONCEPTS.get(str(code).upper(), []))
    return concepts


def _feature(case: Mapping[str, Any], *names: str) -> float | None:
    features = ((case.get("ptbxl_plus") or {}).get("features") or {}) | (
        ((case.get("ptbxl_plus") or {}).get("measurements") or {})
    )
    lowered = {str(key).lower(): value for key, value in features.items()}
    for name in names:
        value = lowered.get(name.lower())
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, dict) and isinstance(value.get("value"), (int, float)):
            return float(value["value"])
    return None


def _has_lead_roi(case: Mapping[str, Any], concept_id: str) -> bool:
    rois = ((case.get("ptbxl_plus") or {}).get("fiducials") or {}).get("rois") or []
    return any(roi.get("concept") == concept_id for roi in rois if isinstance(roi, dict))


def _keyword_hit(text: str, concept_id: str) -> bool:
    # Start-of-word boundary so a keyword can't match mid-word: critical for
    # "ventricular tachycardia" NOT matching "supraVENTRICULAR tachycardia" (and "af"
    # not matching "shaft", "rad" not matching "gradient"). No end-boundary, so stems
    # like "infarct"/"ischemi" still match "infarction"/"ischemic".
    for keyword in CONCEPT_KEYWORDS.get(concept_id, []):
        if re.search(r"(?<![a-z])" + re.escape(keyword), text):
            return True
    return False


def _score_concept(case: Mapping[str, Any], concept_id: str) -> ConceptConfidence:
    text = _flatten_text(case)
    scp_hits = _scp_concepts(case)
    signal = (case.get("signal_quality") or {}).get("status", "acceptable")
    features = ((case.get("ptbxl_plus") or {}).get("features") or {}) | (
        ((case.get("ptbxl_plus") or {}).get("measurements") or {})
    )
    evidence: list[str] = []
    warnings: list[str] = []
    score = 0.0
    hard_limit: str | None = None

    if signal == "acceptable":
        score += 0.18
        evidence.append("acceptable_signal_quality")
    elif signal == "borderline":
        # Localized/mild noise (e.g. static noise in a few leads) is flagged but
        # does not by itself cap the tier: a strong, concordant concept can still
        # be a high-confidence teaching case. Per-lead ROI teaching should still
        # be cautious, which downstream warnings convey.
        score += 0.12
        warnings.append("Borderline signal quality (localized noise); be cautious with fine-grained lead claims.")
    else:
        warnings.append("Poor signal quality prevents student-facing use.")
        hard_limit = "C"

    # The PTB-XL SCP label is cardiologist ground truth: a single mapped label is enough
    # for Tier B (student-facing, with caution); an independent 12SL-statement keyword
    # (or a measurement, below) is the concordant second source that earns Tier A.
    if concept_id in scp_hits:
        score += 0.40
        evidence.append("ptbxl_scp_label")
    if _keyword_hit(text, concept_id):
        score += 0.24
        evidence.append("report_or_statement_keyword")

    if concept_id in {
        "rate",
        "sinus_rhythm",
        "atrial_fibrillation",
        "atrial_flutter",
        "supraventricular_tachycardia",
        "wide_complex_tachycardia",
        "bradycardia",
    }:
        rate = _feature(case, "heart_rate", "rate_bpm", "ventricular_rate")
        if rate is not None:
            score += 0.2
            evidence.append("rate_measurement")
            if concept_id == "rate":
                # Rate is a foundational, directly-measured concept: a reliable
                # rate measurement is sufficient grounding (the German PTB-XL
                # reports never contain the English keyword "rate").
                score += 0.3
                evidence.append("rate_quantified")
        if concept_id == "bradycardia" and rate is not None and rate < 60:
            score += 0.18
            evidence.append("rate_threshold")
        if concept_id in {"supraventricular_tachycardia", "wide_complex_tachycardia"} and rate is not None and rate > 140:
            score += 0.1
            evidence.append("tachycardia_rate_context")

    if concept_id in {"axis_normal", "left_axis_deviation", "right_axis_deviation"}:
        axis = _feature(case, "axis_deg", "qrs_axis_deg", "frontal_axis")
        if axis is not None:
            score += 0.22
            evidence.append("axis_measurement")
            if concept_id == "axis_normal" and -30 <= axis <= 90:
                score += 0.2
                evidence.append("axis_range_normal")
            if concept_id == "left_axis_deviation" and axis < -30:
                score += 0.2
                evidence.append("axis_range_left")
            if concept_id == "right_axis_deviation" and axis > 90:
                score += 0.2
                evidence.append("axis_range_right")

    # Fascicular blocks: the frontal-axis measurement is the concordant second source
    # (LAFB -> marked left axis; LPFB -> right axis), on top of the SCP label.
    if concept_id in {"left_anterior_fascicular_block", "left_posterior_fascicular_block"}:
        axis = _feature(case, "axis_deg", "qrs_axis_deg", "frontal_axis")
        if axis is not None:
            if concept_id == "left_anterior_fascicular_block" and axis <= -45:
                score += 0.2
                evidence.append("left_axis_concordance")
            elif concept_id == "left_posterior_fascicular_block" and axis >= 90:
                score += 0.2
                evidence.append("right_axis_concordance")

    if concept_id in {
        "qrs_duration",
        "right_bundle_branch_block",
        "left_bundle_branch_block",
        "nonspecific_intraventricular_conduction_delay",
    }:
        direct_conduction_label = concept_id in scp_hits or _keyword_hit(text, concept_id)
        report_text = str(((case.get("ptbxl") or {}).get("report") or "")).casefold()
        if concept_id == "right_bundle_branch_block" and (
            "linksschenkelblock" in report_text or "left bundle branch block" in report_text
        ):
            warnings.append("PTB-XL report names LBBB while another source supports RBBB; source contradiction.")
            hard_limit = "D"
        if concept_id == "left_bundle_branch_block" and (
            "rechtsschenkelblock" in report_text or "right bundle branch block" in report_text
        ):
            warnings.append("PTB-XL report names RBBB while another source supports LBBB; source contradiction.")
            hard_limit = "D"
        if (
            concept_id == "right_bundle_branch_block"
            and "incomplete_right_bundle_branch_block" in scp_hits
            and "right_bundle_branch_block" not in scp_hits
        ):
            warnings.append("PTB-XL SCP label is incomplete RBBB; do not promote a conflicting complete-RBBB statement.")
            hard_limit = "C" if hard_limit is None or TIER_ORDER[hard_limit] > TIER_ORDER["C"] else hard_limit
        qrs = _feature(case, "qrs_ms", "qrs_duration_ms")
        if qrs is not None:
            score += 0.24
            evidence.append("qrs_duration_measurement")
            if concept_id == "qrs_duration":
                score += 0.1
            if concept_id != "qrs_duration" and qrs >= 120 and direct_conduction_label:
                score += 0.16
                evidence.append("wide_qrs_threshold")
            elif concept_id in {"right_bundle_branch_block", "left_bundle_branch_block"} and qrs >= 120:
                warnings.append("Wide QRS alone is insufficient to teach a specific bundle branch block.")
                hard_limit = "D"
        if concept_id in {"right_bundle_branch_block", "left_bundle_branch_block"} and not direct_conduction_label:
            hard_limit = "D"
        if not _has_lead_roi(case, concept_id) and concept_id in {
            "right_bundle_branch_block",
            "left_bundle_branch_block",
        }:
            warnings.append("Morphology support is limited; avoid over-specific lead claims.")
            hard_limit = hard_limit or "B"

    if concept_id in {
        "av_block_first_degree",
        "av_block_second_degree_mobitz_i",
        "av_block_second_degree_mobitz_ii",
        "av_block_third_degree",
    }:
        pr = _feature(case, "pr_ms")
        direct_av_label = concept_id in scp_hits or _keyword_hit(text, concept_id)
        if pr is not None:
            score += 0.18
            evidence.append("pr_measurement")
            if concept_id == "av_block_first_degree" and pr >= 200:
                score += 0.24
                evidence.append("pr_prolonged_threshold")
        elif concept_id == "av_block_first_degree":
            warnings.append("PR interval measurement unavailable; cannot confirm first-degree AV block.")
            hard_limit = hard_limit or "C"
        # Higher-degree AV block needs an explicit rhythm label; PR alone is insufficient.
        if concept_id in {
            "av_block_second_degree_mobitz_i",
            "av_block_second_degree_mobitz_ii",
            "av_block_third_degree",
        } and not direct_av_label:
            hard_limit = "D"

    if concept_id in {"qt_interval", "qtc_prolongation"}:
        qt = _feature(case, "qt_ms")
        qtc = _feature(case, "qtc_ms", "qtc_bazett_ms")
        if qt is not None:
            score += 0.16
            evidence.append("qt_measurement")
        if qtc is not None:
            score += 0.22
            evidence.append("qtc_measurement")
            if concept_id == "qtc_prolongation" and qtc >= 480:
                score += 0.22
                evidence.append("qtc_threshold")
            if concept_id == "qt_interval":
                score += 0.08
        if qtc is None:
            warnings.append("QTc measurement unavailable.")
            hard_limit = "D" if concept_id == "qtc_prolongation" else hard_limit

    if concept_id in {
        "st_elevation",
        "st_depression",
        "t_wave_inversion",
        "nonspecific_st_t_change",
        "myocardial_ischemia",
        "pathologic_q_waves",
        "myocardial_infarction",
        "anterior_mi",
        "inferior_mi",
        "lateral_mi",
        "septal_mi",
        "posterior_mi",
    }:
        # An ST-T/MI finding needs a real diagnostic label or an independent 12SL statement —
        # never the always-present geometric ROI (V1 audit). MI territory is driven by the
        # cardiologist label + statement concordance, NOT by ST magnitude: PTB-XL infarcts are
        # overwhelmingly OLD/established and ST features do not discriminate them (deep-research
        # literature + direct distribution test). Per-lead ST corroborates ONLY the ST-FORM
        # concepts themselves, where it measures exactly what the label asserts.
        direct = concept_id in scp_hits or _keyword_hit(text, concept_id)
        if not direct:
            warnings.append("No diagnostic label or independent statement supports this ST-T/MI finding; not student-facing.")
            hard_limit = "C"
        else:
            per_lead_st = (case.get("ptbxl_plus") or {}).get("per_lead_st_mv") or {}
            st_values = [float(v or 0) for v in per_lead_st.values()]
            if concept_id == "st_elevation" and st_values and max(st_values) >= 0.1:
                score += 0.14
                evidence.append("st_elevation_magnitude")
            elif concept_id == "st_depression" and st_values and min(st_values) <= -0.1:
                score += 0.14
                evidence.append("st_depression_magnitude")

    if concept_id in {"left_ventricular_hypertrophy", "right_ventricular_hypertrophy", "atrial_enlargement"}:
        voltage = _feature(case, "sokolow_lyon_mv", "cornell_mv", "rvh_voltage_mv")
        if voltage is not None:
            score += 0.2
            evidence.append("voltage_feature_support")
            if concept_id == "left_ventricular_hypertrophy":
                sokolow = _feature(case, "sokolow_lyon_mv")
                cornell = _feature(case, "cornell_mv")
                if (sokolow is not None and sokolow >= 3.5) or (cornell is not None and cornell >= 2.8):
                    score += 0.18
                    evidence.append("voltage_threshold")
        if not evidence or evidence == ["acceptable_signal_quality"]:
            hard_limit = "C"

    if concept_id == "normal_ecg":
        rate = _feature(case, "heart_rate", "rate_bpm")
        qrs = _feature(case, "qrs_ms", "qrs_duration_ms")
        qtc = _feature(case, "qtc_ms", "qtc_bazett_ms")
        axis = _feature(case, "axis_deg", "qrs_axis_deg")
        abnormal_hits = [concept for concept in ABNORMAL_CONCEPTS if concept in scp_hits or _keyword_hit(text, concept)]
        if not abnormal_hits:
            score += 0.18
            evidence.append("no_major_abnormal_labels")
        else:
            score -= 0.3
            warnings.append(f"Conflicting abnormal evidence: {', '.join(abnormal_hits[:4])}.")
            hard_limit = "C"
        if rate is not None and 50 <= rate <= 100:
            score += 0.08
            evidence.append("normal_rate_range")
        if qrs is not None and qrs < 120:
            score += 0.08
            evidence.append("normal_qrs_range")
        if qtc is not None and qtc < 470:
            score += 0.08
            evidence.append("normal_qtc_range")
        if axis is not None and -30 <= axis <= 90:
            score += 0.08
            evidence.append("normal_axis_range")

    if concept_id == "r_wave_progression":
        if _has_lead_roi(case, concept_id):
            score += 0.26
            evidence.append("precordial_roi_support")
        else:
            warnings.append("Precordial R-wave progression support is limited.")
            hard_limit = hard_limit or "C"

    score = max(0.0, min(1.0, score))
    tier = tier_from_score(score, hard_limit)
    # Tier A is the high-confidence teaching tier: require clean signal AND
    # concordance across at least two independent concept-level evidence sources
    # (label / statement-text / measurement / ROI), not a single strong label.
    if tier == "A":
        concept_evidence = [e for e in evidence if e != "acceptable_signal_quality"]
        if signal != "acceptable" or len(concept_evidence) < 2:
            tier = "B"
            warnings.append("Downgraded from Tier A: needs clean signal and multi-source concordance.")
    if not evidence:
        warnings.append("No reliable autonomous evidence for this concept.")
    return ConceptConfidence(score=round(score, 3), tier=tier, evidence=evidence, warnings=warnings)


def curate_case(case: Mapping[str, Any]) -> dict[str, Any]:
    concept_confidence = {
        concept.id: _score_concept(case, concept.id).model_dump() for concept in CONCEPTS
    }
    supported = [
        concept_id
        for concept_id, confidence in concept_confidence.items()
        if confidence["tier"] in {"A", "B"} and confidence["score"] >= 0.58
    ]
    unsupported = [
        concept_id
        for concept_id, confidence in concept_confidence.items()
        if confidence["tier"] in {"C", "D"}
    ]
    best_tier = "D"
    for confidence in concept_confidence.values():
        if TIER_ORDER[confidence["tier"]] > TIER_ORDER[best_tier]:
            best_tier = confidence["tier"]
    global_tier = best_tier if supported else "C"
    if (case.get("signal_quality") or {}).get("status") == "poor":
        global_tier = "C"

    inclusion_reasons = []
    if supported:
        inclusion_reasons.append("At least one concept reached Tier A/B autonomous confidence.")
    if (case.get("waveform") or {}).get("source"):
        inclusion_reasons.append("Waveform source is available.")

    exclusion_reasons = []
    if not supported:
        exclusion_reasons.append("No concept reached student-facing autonomous confidence.")
    if global_tier in {"C", "D"}:
        exclusion_reasons.append("Case is withheld from default student workflows.")

    allowed_claims = []
    forbidden_claims = []
    features = ((case.get("ptbxl_plus") or {}).get("features") or {}) | (
        ((case.get("ptbxl_plus") or {}).get("measurements") or {})
    )
    for name in ("heart_rate", "qrs_ms", "qt_ms", "qtc_ms", "axis_deg", "pr_ms"):
        if name in features:
            allowed_claims.append(f"May cite {name} from PTB-XL+ or fixture measurements.")
        else:
            forbidden_claims.append(f"Do not invent {name}; it is unavailable.")
    if not ((case.get("ptbxl_plus") or {}).get("fiducials") or {}).get("rois"):
        forbidden_claims.append("Do not invent lead-level ROIs or fiducials.")

    return {
        "concept_confidence": concept_confidence,
        "supported_objectives": supported,
        "unsupported_objectives": unsupported,
        "teaching_tier": global_tier,
        "global_tier": global_tier,
        "inclusion_reasons": inclusion_reasons,
        "exclusion_reasons": exclusion_reasons,
        "llm_allowed_claims": allowed_claims,
        "llm_forbidden_claims": forbidden_claims,
    }
