from __future__ import annotations

import re
from typing import Any

from .ontology import concept_label
from .schemas import AttemptRequest, StructuredInterpretation

# Negation cues that, when they immediately precede a matched keyword, suppress it
# (so "no MI", "rule out STEMI", "without ST elevation" do not register the finding).
_NEGATIONS = (
    "no ", "not ", "non-", "without ", "rule out ", "r/o ", "ruled out ",
    "denies ", "absent ", "no evidence of ", "negative for ", "rather than ", "versus ",
)


ANSWER_KEYWORDS = {
    "normal_ecg": ["normal"],
    "rate": ["bpm", "beats per minute", "heart rate", "rate"],
    "sinus_rhythm": ["sinus"],
    "atrial_fibrillation": ["atrial fibrillation", "afib", "irregularly irregular"],
    "atrial_flutter": ["flutter"],
    "supraventricular_tachycardia": ["supraventricular tachycardia", "svt", "narrow complex tachycardia"],
    "wide_complex_tachycardia": ["wide complex tachycardia", "ventricular tachycardia", "vt"],
    "ventricular_tachycardia": [
        "ventricular tachycardia",
        "monomorphic ventricular tachycardia",
        "monomorphic vt",
        "vtach",
        "v tach",
        "vt",
    ],
    "polymorphic_ventricular_tachycardia": [
        "polymorphic ventricular tachycardia",
        "polymorphic vt",
        "torsades de pointes",
        "torsades",
    ],
    "ventricular_flutter": ["ventricular flutter"],
    "ventricular_fibrillation": [
        "ventricular fibrillation",
        "v fib",
        "vfib",
        "vf",
    ],
    "bradycardia": ["brady"],
    "av_block_first_degree": ["first degree av block", "first-degree av block", "1st degree av block", "prolonged pr"],
    "av_block_second_degree_mobitz_i": ["mobitz i", "mobitz 1", "wenckebach"],
    "av_block_second_degree_mobitz_ii": ["mobitz ii", "mobitz 2"],
    "av_block_third_degree": ["third degree av block", "third-degree av block", "complete heart block", "av dissociation"],
    "right_bundle_branch_block": ["rbbb", "right bundle"],
    "left_bundle_branch_block": ["lbbb", "left bundle"],
    "incomplete_right_bundle_branch_block": ["incomplete rbbb", "incomplete right bundle"],
    "nonspecific_intraventricular_conduction_delay": ["ivcd", "intraventricular conduction delay"],
    "left_anterior_fascicular_block": ["lafb", "left anterior fascicular"],
    "left_posterior_fascicular_block": ["lpfb", "left posterior fascicular"],
    "wolff_parkinson_white": ["wolff parkinson white", "wolff-parkinson-white", "wpw", "delta wave", "pre-excitation"],
    "paced_rhythm": ["paced rhythm", "ventricular pacing", "atrial pacing", "pacemaker"],
    "premature_ventricular_complex": ["pvc", "premature ventricular"],
    "premature_atrial_complex": ["pac", "premature atrial"],
    "qrs_duration": ["wide qrs", "qrs", "wide complex"],
    "left_axis_deviation": ["left axis", "lad"],
    "right_axis_deviation": ["right axis", "rad"],
    "axis_normal": ["normal axis"],
    "r_wave_progression": ["r wave progression", "r-wave progression", "poor r wave progression"],
    "st_elevation": ["st elevation", "stemi", "elevated st"],
    "st_depression": ["st depression"],
    "t_wave_inversion": ["t wave inversion", "inverted t"],
    "nonspecific_st_t_change": ["nonspecific st", "non-specific st", "nonspecific repolarization"],
    "myocardial_infarction": ["mi", "myocardial infarction", "infarction", "stemi"],
    "anterior_mi": ["anterior"],
    "inferior_mi": ["inferior"],
    "lateral_mi": ["lateral"],
    "septal_mi": ["septal"],
    "posterior_mi": ["posterior mi", "posterior infarct"],
    "myocardial_ischemia": ["myocardial ischemia", "ischaemia", "ischemic", "ischaemic"],
    "pathologic_q_waves": ["pathologic q", "pathological q", "q waves"],
    "left_ventricular_hypertrophy": ["lvh", "left ventricular hypertrophy"],
    "right_ventricular_hypertrophy": ["rvh", "right ventricular hypertrophy"],
    "atrial_enlargement": ["atrial enlargement", "left atrial abnormality", "right atrial abnormality", "lae", "rae"],
    "qtc_prolongation": ["long qt", "prolonged qtc", "qt prolongation"],
    "qt_interval": ["qt"],
    "electrolyte_drug_pattern": ["electrolyte", "drug effect", "medication effect"],
    "pericarditis_pattern": ["pericarditis"],
}


MISCONCEPTIONS = {
    "missed_af": "missing AF because of focusing only on rate",
    "overcalled_mi": "overcalling MI from nonspecific ST-T changes",
    "mi_localization": "recognizing ST elevation but localizing incorrectly",
    "bundle_confusion": "confusing LBBB and RBBB",
    "qt_vs_qtc": "measuring QT instead of QTc",
    "axis_lead_misuse": "misusing limb leads for axis",
    "missed_wide_qrs": "missing wide QRS",
    "high_confidence_wrong": "high-confidence wrong answer",
}


def grade_attempt(case: dict[str, Any], attempt: AttemptRequest) -> dict[str, Any]:
    expected = _core_expected_objectives(case, attempt.focusObjective)
    if attempt.assessmentScope == "dominant_finding":
        # The quick-look explicitly asks for one dominant finding. Omitting
        # incidental rate/sinus/QT labels must not create false high-confidence
        # errors or negative mastery updates.
        expected = expected[:1]
    selected_concepts = set(attempt.structuredAnswer.selectedConcepts)
    answer_concepts = set(selected_concepts)
    answer_concepts.update(_concepts_from_answer(attempt.structuredAnswer, attempt.freeTextAnswer))

    # Rate is a measurement competency, not a keyword competency. A previous
    # shortcut awarded full credit to any integer from 20–300 (e.g. 299 on a
    # grounded 64-bpm tracing). When rate is tested, require agreement with the
    # packet's measured rate or the correct brady/normal/tachy category.
    if "rate" in expected:
        structured_rate = (attempt.structuredAnswer.rate or "").strip()
        rate_text = structured_rate or attempt.freeTextAnswer
        if _rate_answer_matches(case, rate_text, require_rate_context=not bool(structured_rate)):
            answer_concepts.add("rate")
        else:
            answer_concepts.discard("rate")

    correct = sorted(set(expected) & answer_concepts)
    missed = sorted(set(expected) - answer_concepts)
    confidence = case.get("concept_confidence") or {}
    supported_ab = {
        concept
        for concept, evidence in confidence.items()
        if (evidence or {}).get("tier") in {"A", "B"}
    }
    # Only explicit finding selections are calibrated as overcalls. Narrative
    # keyword extraction can help deterministic recall grading, but it must not
    # turn an incidental phrase into a clinical overcall. Conversely, every
    # selected label without A/B packet support counts, including unknown or
    # weakly supported labels—not only entries explicitly tagged C/D.
    overcalled = sorted(selected_concepts - supported_ab)

    if expected:
        score = len(correct) / len(expected)
        if overcalled:
            score = max(0.0, score - min(0.35, len(overcalled) * 0.12))
    else:
        score = 0.0

    misconceptions = _misconceptions(case, expected, answer_concepts, missed, overcalled, attempt.confidence)
    mastery_delta = _mastery_delta(expected, correct, missed, attempt.confidence, attempt.hintsUsed)
    feedback_parts = []
    if correct:
        feedback_parts.append(f"Matched: {', '.join(concept_label(item) for item in correct)}.")
    if missed:
        feedback_parts.append(f"Review: {', '.join(concept_label(item) for item in missed)}.")
    if overcalled:
        feedback_parts.append(f"Overcalled or unsupported here: {', '.join(concept_label(item) for item in overcalled)}.")
    if not feedback_parts:
        feedback_parts.append("This case has limited student-facing objectives; review the grounded teaching points.")

    return {
        "caseId": case["case_id"],
        "score": round(score, 3),
        "correctObjectives": correct,
        "missedObjectives": missed,
        "overcalledObjectives": overcalled,
        "misconceptions": misconceptions,
        "masteryDelta": mastery_delta,
        "feedback": " ".join(feedback_parts),
        "teachingPoints": case.get("teaching_points", []),
        "revealedDiagnosis": case.get("ptbxl", {}).get("report", ""),
        "assessmentScope": attempt.assessmentScope,
    }


def grade_click_answer(case: dict[str, Any], lead: str, time_sec: float, amplitude_mv: float, concept: str | None = None) -> dict[str, Any]:
    rois = ((case.get("ptbxl_plus") or {}).get("fiducials") or {}).get("rois") or []
    if not rois:
        return {
            "correct": False,
            "noTarget": True,
            "feedback": "This case has no grounded ROI to grade clicks against; use the structured read instead.",
            "matchedRoi": None,
        }
    # If a concept target was requested but no such ROI exists anywhere on this case,
    # that is a missing-target condition, not a wrong answer.
    if concept and not any(roi.get("concept") == concept for roi in rois):
        return {
            "correct": False,
            "noTarget": True,
            "feedback": f"No grounded {concept_label(concept)} target exists on this case.",
            "matchedRoi": None,
        }
    candidates = [roi for roi in rois if roi.get("lead") == lead and (concept is None or roi.get("concept") == concept)]
    features = ((case.get("ptbxl_plus") or {}).get("features") or {})
    heart_rate = features.get("heart_rate")
    irregular_objectives = {
        "atrial_fibrillation", "premature_atrial_complex", "premature_ventricular_complex",
        "av_block_second_degree_mobitz_i", "av_block_second_degree_mobitz_ii",
    }
    irregular = bool(irregular_objectives & set(case.get("supported_objectives", [])))
    rr_sec = (
        60.0 / float(heart_rate)
        if not irregular and isinstance(heart_rate, (int, float)) and heart_rate > 0
        else None
    )
    for roi in candidates:
        start = float(roi["timeStartSec"])
        end = float(roi["timeEndSec"])
        tolerance_sec = {
            "p_wave": 0.04,
            "qrs_complex": 0.06,
            "pr_interval": 0.05,
            "st_segment": 0.06,
            "t_wave": 0.08,
            "qt_segment": 0.06,
        }.get(str(roi.get("concept")), 0.06)
        if rr_sec:
            relative = ((time_sec - (start - tolerance_sec)) % rr_sec + rr_sec) % rr_sec
            time_match = relative <= (end - start) + 2 * tolerance_sec
        else:
            time_match = start - tolerance_sec <= time_sec <= end + tolerance_sec
        amp_min = float(roi.get("ampMinMv", -2.5))
        amp_max = float(roi.get("ampMaxMv", 2.5))
        amp_margin = max(0.15, (amp_max - amp_min) * 0.25)
        amplitude_match = amp_min - amp_margin <= amplitude_mv <= amp_max + amp_margin
        # Require proximity to the component's amplitude envelope so a click at
        # the top of the panel cannot pass merely because its x-coordinate aligns.
        if time_match and amplitude_match:
            return {
                "correct": True,
                "noTarget": False,
                "feedback": f"Good eye: that lands in a homologous {roi['label']} window in {roi['lead']}.",
                "matchedRoi": roi,
            }
        if time_match and not amplitude_match:
            return {
                "correct": False,
                "noTarget": False,
                "feedback": "The timing is close, but the point is too far from the waveform component.",
                "matchedRoi": None,
            }
    if irregular and candidates:
        return {
            "correct": False,
            "noTarget": True,
            "feedback": (
                "This irregular tracing has only a representative fiducial, so projecting it by average heart rate "
                "would be unsafe. This click is not scored; use per-beat landmarks or a reviewed target."
            ),
            "matchedRoi": None,
        }
    nearest = next((roi for roi in rois if roi.get("lead") == lead and (concept is None or roi.get("concept") == concept)), None)
    hint = f" Look for the same phase of another beat in {lead}, using the component's onset and end." if nearest else ""
    return {
        "correct": False,
        "noTarget": False,
        "feedback": f"That click did not land inside the target.{hint}",
        "matchedRoi": None,
    }


def grade_region_answer(
    case: dict[str, Any],
    lead: str,
    time_start_sec: float,
    time_end_sec: float,
    amp_min_mv: float,
    amp_max_mv: float,
    concept: str | None = None,
) -> dict[str, Any]:
    """Grade a learner-drawn bounding region against validated lead-level ROIs.

    Region grading is deliberately stricter than a click: the box must cover most
    of the grounded target while remaining meaningfully localized. We do not
    project a representative ROI across irregular rhythms; a scene without a
    directly visible target is neutral/not-assessable rather than an invented miss.
    """
    rois = ((case.get("ptbxl_plus") or {}).get("fiducials") or {}).get("rois") or []
    candidates = [
        roi for roi in rois
        if roi.get("lead") == lead and (concept is None or roi.get("concept") == concept)
    ]
    if concept and not any(roi.get("concept") == concept for roi in rois):
        return {
            "correct": False,
            "noTarget": True,
            "feedback": f"No grounded {concept_label(concept)} region exists on this case.",
            "matchedRoi": None,
            "targetCoverage": 0.0,
            "selectionPrecision": 0.0,
        }
    if not candidates:
        return {
            "correct": False,
            "noTarget": not bool(rois),
            "feedback": (
                f"No grounded target is available in {lead} for this task."
                if rois else "This case has no grounded regions to grade."
            ),
            "matchedRoi": None,
            "targetCoverage": 0.0,
            "selectionPrecision": 0.0,
        }

    user_t0, user_t1 = sorted((float(time_start_sec), float(time_end_sec)))
    user_a0, user_a1 = sorted((float(amp_min_mv), float(amp_max_mv)))
    user_area = max(1e-8, (user_t1 - user_t0) * (user_a1 - user_a0))
    best: tuple[float, float, dict[str, Any]] | None = None
    for roi in candidates:
        target_t0, target_t1 = sorted((float(roi["timeStartSec"]), float(roi["timeEndSec"])))
        target_a0, target_a1 = sorted((float(roi.get("ampMinMv", -2.5)), float(roi.get("ampMaxMv", 2.5))))
        intersection_t = max(0.0, min(user_t1, target_t1) - max(user_t0, target_t0))
        intersection_a = max(0.0, min(user_a1, target_a1) - max(user_a0, target_a0))
        intersection = intersection_t * intersection_a
        target_area = max(1e-8, (target_t1 - target_t0) * (target_a1 - target_a0))
        coverage = intersection / target_area
        precision = intersection / user_area
        if best is None or coverage * precision > best[0] * best[1]:
            best = (coverage, precision, roi)

    assert best is not None
    coverage, precision, matched = best
    correct = coverage >= 0.55 and precision >= 0.12
    if correct:
        feedback = f"Your region contains the grounded {matched['label']} in {lead} without reducing the task to the whole panel."
    elif coverage < 0.55:
        feedback = "The box misses too much of the target waveform. Include the full onset-to-end feature."
    else:
        feedback = "The target is inside the box, but the box is too broad. Tighten it around the waveform evidence."
    return {
        "correct": correct,
        "noTarget": False,
        "feedback": feedback,
        "matchedRoi": matched if correct else None,
        "targetCoverage": round(coverage, 3),
        "selectionPrecision": round(precision, 3),
    }


_PRIORITY = [
    "ventricular_fibrillation",
    "ventricular_flutter",
    "polymorphic_ventricular_tachycardia",
    "ventricular_tachycardia",
    "atrial_fibrillation",
    "atrial_flutter",
    "right_bundle_branch_block",
    "left_bundle_branch_block",
    "myocardial_infarction",
    "anterior_mi",
    "inferior_mi",
    "lateral_mi",
    "septal_mi",
    "posterior_mi",
    "st_elevation",
    "st_depression",
    "t_wave_inversion",
    "qtc_prolongation",
    "left_ventricular_hypertrophy",
    "right_ventricular_hypertrophy",
    "atrial_enlargement",
    "av_block_first_degree",
    "left_axis_deviation",
    "right_axis_deviation",
    "bradycardia",
    "normal_ecg",
    "sinus_rhythm",
    "axis_normal",
    "qrs_duration",
    "qt_interval",
    "rate",
]


def _core_expected_objectives(case: dict[str, Any], focus: str | None = None) -> list[str]:
    """Objectives a learner is expected to call, distinctive/high-yield first.

    Orders supported (Tier A/B) objectives by clinical salience so a case's
    distinctive finding (e.g. anterior MI) is graded ahead of the ubiquitous
    foundational ones (rate, sinus rhythm), and pins an optional focus objective
    (used by concept-specific review) to the front.
    """
    confidence = case["concept_confidence"]
    supported = [
        concept_id
        for concept_id, conf in confidence.items()
        if conf["tier"] in {"A", "B"} and conf["score"] >= 0.58
    ]
    priority_index = {concept: index for index, concept in enumerate(_PRIORITY)}

    def sort_key(concept_id: str) -> tuple[int, int, float]:
        conf = confidence.get(concept_id, {})
        tier_rank = 0 if conf.get("tier") == "A" else 1
        return (tier_rank, priority_index.get(concept_id, len(_PRIORITY)), -float(conf.get("score", 0)))

    # Deliberate concept practice should grade the competency the learner chose,
    # not penalize them for omitting three incidental labels on a multi-label ECG.
    if focus and focus in supported:
        return [focus]

    ordered: list[str] = []
    for concept_id in sorted(supported, key=sort_key):
        if concept_id not in ordered:
            ordered.append(concept_id)
    return ordered[:4]


# Which concepts each structured-interpretation field can legitimately express.
# Prevents cross-field misfires (e.g. "normal" in the RATE field must not register
# normal_ecg). The synthesis / free-text fields can express any concept.
FIELD_CONCEPTS: dict[str, set[str] | None] = {
    "rate": {
        "rate", "bradycardia", "supraventricular_tachycardia",
        "wide_complex_tachycardia", "ventricular_tachycardia",
        "polymorphic_ventricular_tachycardia", "ventricular_flutter",
    },
    "rhythm": {
        "sinus_rhythm", "atrial_fibrillation", "atrial_flutter",
        "supraventricular_tachycardia", "wide_complex_tachycardia", "paced_rhythm",
        "premature_ventricular_complex", "premature_atrial_complex",
        "ventricular_tachycardia", "polymorphic_ventricular_tachycardia",
        "ventricular_flutter", "ventricular_fibrillation",
    },
    "axis": {"axis_normal", "left_axis_deviation", "right_axis_deviation"},
    "intervals": {
        "av_block_first_degree", "av_block_second_degree_mobitz_i",
        "av_block_second_degree_mobitz_ii", "av_block_third_degree",
        "qt_interval", "qtc_prolongation", "wolff_parkinson_white",
    },
    "conduction": {
        "qrs_duration", "right_bundle_branch_block", "left_bundle_branch_block",
        "incomplete_right_bundle_branch_block", "nonspecific_intraventricular_conduction_delay",
        "left_anterior_fascicular_block", "left_posterior_fascicular_block",
        "wolff_parkinson_white", "r_wave_progression",
    },
    "st_t": {
        "st_elevation", "st_depression", "t_wave_inversion", "nonspecific_st_t_change",
        "myocardial_infarction", "anterior_mi", "inferior_mi", "lateral_mi", "septal_mi",
        "posterior_mi", "myocardial_ischemia", "pathologic_q_waves", "pericarditis_pattern",
    },
    "hypertrophy": {"left_ventricular_hypertrophy", "right_ventricular_hypertrophy", "atrial_enlargement"},
    "synthesis": None,  # any concept
}


def _match_concepts(text: str, allowed: set[str] | None) -> set[str]:
    """Word-boundary keyword matching + negation guard, optionally scoped to a field."""
    hits: set[str] = set()
    lowered = (text or "").lower()
    if not lowered:
        return hits
    for concept, keywords in ANSWER_KEYWORDS.items():
        if allowed is not None and concept not in allowed:
            continue
        for keyword in keywords:
            pattern = r"(?<![a-z])" + re.escape(keyword.lower()) + r"(?![a-z])"
            if any(
                not any(neg in lowered[max(0, m.start() - 18):m.start()] for neg in _NEGATIONS)
                for m in re.finditer(pattern, lowered)
            ):
                hits.add(concept)
                break
    return hits


def _concepts_from_answer(structured: StructuredInterpretation, free_text: str) -> set[str]:
    """Field-aware concept inference across the structured interpretation + free text."""
    hits: set[str] = set()
    for field, allowed in FIELD_CONCEPTS.items():
        hits |= _match_concepts(getattr(structured, field, ""), allowed)
    hits |= _match_concepts(free_text, None)
    if "incomplete_right_bundle_branch_block" in hits:
        hits.discard("right_bundle_branch_block")
    return hits


def _grounded_rate(case: dict[str, Any]) -> float | None:
    features = ((case.get("ptbxl_plus") or {}).get("features") or {})
    value = features.get("heart_rate")
    if not isinstance(value, (int, float)):
        value = (case.get("features") or {}).get("heart_rate")
    return float(value) if isinstance(value, (int, float)) and value > 0 else None


def _rate_answer_matches(case: dict[str, Any], text: str, require_rate_context: bool = False) -> bool:
    truth = _grounded_rate(case)
    if truth is None:
        return False
    lowered = (text or "").lower()
    if require_rate_context:
        bound_patterns = (
            r"\b(?:rate|heart\s*rate|hr|pulse)\b\s*(?:is|of|=|:|~|approximately|about)?\s*(\d{2,3}(?:\.\d+)?)\b",
            r"\b(\d{2,3}(?:\.\d+)?)\s*(?:bpm|beats\s+per\s+minute)\b",
        )
        number_tokens = [match for pattern in bound_patterns for match in re.findall(pattern, lowered)]
    else:
        number_tokens = re.findall(r"(?<!\d)(\d{2,3}(?:\.\d+)?)(?!\d)", lowered)
    numbers = [float(item) for item in number_tokens]
    plausible = [value for value in numbers if 20 <= value <= 300]
    if plausible:
        # Contradictory numeric answers are not rescued by a coincidental second
        # number (for example "rate 299" plus "QRS 64 ms").
        if len({round(value, 3) for value in plausible}) > 1:
            return False
        tolerance = max(5.0, truth * 0.10)
        return any(abs(value - truth) <= tolerance for value in plausible)
    category = "brady" if truth < 60 else "tachy" if truth > 100 else "normal"
    if category == "brady":
        return any(token in lowered for token in ("brady", "slow"))
    if category == "tachy":
        return any(token in lowered for token in ("tachy", "fast"))
    return "normal" in lowered and "rate" in lowered


def _misconceptions(
    case: dict[str, Any],
    expected: list[str],
    answer_concepts: set[str],
    missed: list[str],
    overcalled: list[str],
    confidence: int,
) -> list[str]:
    tags: list[str] = []
    if "atrial_fibrillation" in missed:
        tags.append(MISCONCEPTIONS["missed_af"])
    if "myocardial_infarction" in overcalled or (
        "nonspecific_st_t_change" in expected and "myocardial_infarction" in answer_concepts
    ):
        tags.append(MISCONCEPTIONS["overcalled_mi"])
    if "st_elevation" in answer_concepts and any(item in missed for item in ["anterior_mi", "inferior_mi", "lateral_mi"]):
        tags.append(MISCONCEPTIONS["mi_localization"])
    if {"right_bundle_branch_block", "left_bundle_branch_block"} & set(expected) and {
        "right_bundle_branch_block",
        "left_bundle_branch_block",
    } & answer_concepts and not (set(expected) & answer_concepts):
        tags.append(MISCONCEPTIONS["bundle_confusion"])
    if "qtc_prolongation" in missed and "qt_interval" in answer_concepts:
        tags.append(MISCONCEPTIONS["qt_vs_qtc"])
    if "qrs_duration" in missed and any(item in expected for item in ["right_bundle_branch_block", "left_bundle_branch_block"]):
        tags.append(MISCONCEPTIONS["missed_wide_qrs"])
    if confidence >= 4 and missed:
        tags.append(MISCONCEPTIONS["high_confidence_wrong"])
    return sorted(set(tags))


def _mastery_delta(expected: list[str], correct: list[str], missed: list[str], confidence: int, hints_used: int) -> dict[str, float]:
    deltas: dict[str, float] = {}
    for objective in expected:
        if objective in correct:
            deltas[objective] = 0.08 if hints_used == 0 else 0.04
        elif objective in missed:
            deltas[objective] = -0.1 if confidence >= 4 else -0.06
    return deltas
