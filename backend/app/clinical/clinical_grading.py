"""Per-question-type grader for Clinical Decisions (§16A2 + §16B5/6 + §16C).

A SEPARATE grader from ``grading.grade_attempt`` (which is a concept-set intersection
the Foundations loop depends on). This one grades the answer-class model with the 3 axes,
compound-option parsing, the required-safety/acuity caps applied at grade time, and the
confidence upside-cap. Its output preserves the common ``grade`` shape for
attempt history and feedback, but this automated-screened bank is formative:
it never emits legacy objective-mastery deltas. Exact Clinical observations are
recorded separately as formative concept x subskill events by the shift writer.
"""

from __future__ import annotations

import math
import re
from typing import Any

from ..grading import ANSWER_KEYWORDS, grade_click_answer
from ..ontology import concept_label
from . import grounding
from .constants import CLICK_TOLERANCE_MS, UNJUSTIFIED_INSUFFICIENT_DATA_CAP, confidence_band
from .content_tables import REQUIRED_SAFETY_ACTIONS
from .harness.compound_parser import parse_option_text
from .schemas import ClinicalAnswer, ClinicalCaseItem, Option

# Base credit by answer class (before confidence + safety/acuity caps).
# round-3 audit: over_triage_safe must NOT count as "correct" (it was gameable at 0.6), and
# wrong-low-confidence no longer keeps full credit (confidence was a shield).
BASE_CREDIT: dict[str, float] = {
    "ideal": 1.0,
    "acceptable": 0.8,
    "over_triage_safe": 0.5,
    "under_triage": 0.25,
    "insufficient_data": 0.25,
    "unsafe": 0.0,
}
_CORRECT_CLASSES = {"ideal", "acceptable"}
_CORRECT_MULT = {"high": 1.0, "medium": 0.85, "low": 0.65}
_WRONG_MULT = {"high": 0.0, "medium": 0.35, "low": 0.6}


def _cap(text: str) -> str:
    """Capitalize the first character for display (action intents are stored lowercase)."""
    text = (text or "").strip()
    return text[:1].upper() + text[1:] if text else text


def _stem_disclosed_objectives(item: ClinicalCaseItem, objectives: list[str]) -> list[str]:
    """Objectives the vignette gives away before the learner uses the ECG.

    A management answer must not inflate visual ECG mastery when the stem already
    states the rhythm/rate or its defining phrase (the v0 AF fixture disclosed
    "irregularly irregular" and ~118, then credited AF + rate mastery).
    """
    chips_text = " ".join(str(value) for value in item.chips.model_dump().values() if value is not None)
    source_text = " ".join((item.stem or "", item.prompt or "", chips_text)).lower()
    disclosed: list[str] = list(item.disclosed_objectives)
    for objective in objectives:
        if objective in disclosed:
            continue
        if objective == "rate" and re.search(
            r"\b(?:rate|heart\s*rate|hr|pulse|tachycardic(?:\s+at)?|bradycardic(?:\s+at)?)\b\D{0,8}\d{2,3}\b"
            r"|\b\d{2,3}\s*(?:bpm|beats\s+per\s+minute)\b",
            source_text,
        ):
            disclosed.append(objective)
            continue
        for keyword in ANSWER_KEYWORDS.get(objective, []):
            if re.search(r"(?<![a-z])" + re.escape(keyword.lower()) + r"(?![a-z])", source_text):
                disclosed.append(objective)
                break
    return list(dict.fromkeys(disclosed))


def _tested_objectives(item: ClinicalCaseItem, packet: dict[str, Any]) -> list[str]:
    supported = grounding.supported_objectives(packet)
    manifested = [c.objective_id for c in item.evidence_manifest.ecg_supports if c.objective_id in supported]
    candidates = manifested or sorted(supported)[:1]
    disclosed = set(_stem_disclosed_objectives(item, candidates))
    return [objective for objective in candidates if objective not in disclosed]


def _discriminator_actions(item: ClinicalCaseItem, packet: dict[str, Any], tested: list[str]) -> list[dict[str, Any]]:
    """On-trace reason-me-back: highlight the grounded ROI of the discriminating finding
    so feedback points at the evidence on the real tracing (§12 P0-4)."""
    concept = item.roi_target.concept if item.roi_target else (tested[0] if tested else None)
    if not concept:
        return []
    acceptable = grounding.acceptable_roi_concepts(concept)
    all_rois = grounding.rois(packet)
    matched = [r for r in all_rois if r.get("concept") in acceptable]
    # Fall back to the grounded ROIs on the trace (for v0 fixtures the ROI IS the finding;
    # ROI concept names don't always equal the clinical concept, e.g. qt_interval/qtc).
    chosen = matched or all_rois
    actions: list[dict[str, Any]] = []
    for roi in chosen[:2]:
        amp_min = float(roi.get("ampMinMv", -0.5))
        amp_max = float(roi.get("ampMaxMv", 0.6))
        if amp_max <= amp_min:
            amp_max = amp_min + 0.1
        actions.append(
            {
                "type": "highlightROI",
                "lead": roi["lead"],
                "timeStart": float(roi["timeStartSec"]),
                "timeEnd": float(roi["timeEndSec"]),
                "ampMin": amp_min,
                "ampMax": amp_max,
                "label": roi.get("label") or concept.replace("_", " "),
            }
        )
    return actions


def _safety_capped(item: ClinicalCaseItem, option: Option, packet: dict[str, Any]) -> bool:
    """True if an ideal/acceptable option must be capped for missing a required safety action."""
    if option.answer_class not in {"ideal", "acceptable"}:
        return False
    supported = grounding.supported_objectives(packet)
    gated = {c: REQUIRED_SAFETY_ACTIONS[c] for c in supported if c in REQUIRED_SAFETY_ACTIONS}
    if not gated:
        return False
    carried = set(option.required_safety_tokens)
    parsed = option.parsed or parse_option_text(option.text)
    carried |= set(parsed.safety_tokens)
    return any(not (carried & set(required)) for required in gated.values())


def _grade_dict(
    item: ClinicalCaseItem,
    score: float,
    tested: list[str],
    correct: bool,
    feedback: str,
    *,
    answer_class: str | None = None,
    axes: dict[str, float] | None = None,
    confidence: int | None = None,
    safety_flags: list[str] | None = None,
    calibration: dict[str, Any] | None = None,
    timed_out: bool = False,
    viewer_actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    manifested = [claim.objective_id for claim in item.evidence_manifest.ecg_supports]
    stem_disclosed = _stem_disclosed_objectives(item, manifested)
    return {
        "caseId": item.item_id,
        "score": round(max(0.0, min(1.0, score)), 3),
        "correctObjectives": tested if correct else [],
        "missedObjectives": [] if correct else tested,
        "overcalledObjectives": [],
        "misconceptions": [],
        # Fail closed: the currently served authored bank is pending named
        # clinician sign-off, so neither a correct answer nor a miss/timeout may
        # move the legacy objective summary. A future reviewed-independent bank
        # must use a separate server-authorized exact-receipt path; changing an
        # item status or client payload is deliberately insufficient.
        "masteryDelta": {},
        "feedback": feedback,
        "teachingPoints": [_cap(item.evidence_manifest.action_rationale)] if item.evidence_manifest.action_rationale else [],
        # clinical extras
        "answerClass": answer_class,
        "axisScores": axes or {},
        "safetyFlags": safety_flags or [],
        "calibrationEvent": calibration or {},
        "timedOut": timed_out,
        "viewerActions": viewer_actions or [],
        "stemDisclosedObjectives": stem_disclosed,
        "ecgRecognitionSuppressed": bool(stem_disclosed),
        # Clinical application in this harness-screened authored bank is always
        # formative. It must never be interpreted as independent application
        # mastery, regardless of timing or confidence.
        "clinicalApplicationEvidence": "formative_only",
    }


def _grade_option_based(item: ClinicalCaseItem, packet: dict[str, Any], answer: ClinicalAnswer) -> dict[str, Any]:
    tested = _tested_objectives(item, packet)
    if answer.timed_out:
        return _grade_dict(
            item, 0.0, tested, correct=False,
            feedback="Time. Here is the safest interpretation — review the discriminating feature.",
            answer_class=None, confidence=answer.confidence, timed_out=True,
            axes={"clinical_decision": 0.0},
            calibration={"timedOut": True, "confidence": answer.confidence},
        )
    option = next((o for o in item.options if o.id == answer.selected_option_id), None)
    if option is None:
        return _grade_dict(
            item,
            0.0,
            tested,
            correct=False,
            feedback="No option selected.",
            axes={"clinical_decision": 0.0},
        )

    base = BASE_CREDIT.get(option.answer_class, 0.0)
    safety_flags: list[str] = []
    capped = _safety_capped(item, option, packet)
    # §16B5 grade-time cap: ideal/acceptable lacking the required safety action drops to under_triage.
    if capped:
        base = min(base, BASE_CREDIT["under_triage"])
        safety_flags.append("missing_required_safety_action")
    # §16C / round-3: unjustified insufficient_data on a determined item earns little unless it
    # bundles a parallel safety action; an intentionally-underdetermined item rewards it fully.
    if option.answer_class == "insufficient_data":
        if item.evidence_manifest.epistemic_status == "intentionally_underdetermined":
            base = 1.0
        elif option.parsed and option.parsed.safety_action_present and not option.parsed.action_delayed:
            base = UNJUSTIFIED_INSUFFICIENT_DATA_CAP  # 0.40 — got more data WHILE acting
        else:
            base = 0.10

    correct = option.answer_class in _CORRECT_CLASSES and not capped
    band = confidence_band(answer.confidence)
    score = base * (_CORRECT_MULT[band] if correct else _WRONG_MULT[band])
    high_conf_wrong = (not correct) and band == "high"

    label = ", ".join(concept_label(o) for o in tested) or "the finding"
    # Headline only — the ideal action is surfaced once, separately, via teachingPoints (avoid repeating it).
    if correct:
        feedback = f"{option.answer_class.replace('_', ' ').title()}."
    else:
        feedback = f"That choice is {option.answer_class.replace('_', ' ')}. Discriminator: {label}."
    calibration = {
        "answerClass": option.answer_class,
        "overTriage": option.answer_class == "over_triage_safe",
        "underTriage": option.answer_class == "under_triage",
        "unsafe": option.answer_class == "unsafe",
        "insufficientData": option.answer_class == "insufficient_data",
        "highConfidenceWrong": high_conf_wrong,
        "confidence": answer.confidence,
    }
    axes = {
        **option.axis_scores,
        "clinical_decision": round(base, 3),
        "safety": 0.0 if capped or option.answer_class in {"under_triage", "unsafe"} else 1.0,
    }
    return _grade_dict(
        item, score, tested, correct, feedback,
        answer_class=option.answer_class, axes=axes, confidence=answer.confidence,
        safety_flags=safety_flags, calibration=calibration,
        viewer_actions=_discriminator_actions(item, packet, tested),
    )


def periodic_click_match(packet: dict[str, Any], concept: str, lead: str, time_sec: float, tol_ms: float = CLICK_TOLERANCE_MS) -> dict | None:
    """Periodic ROI match (the authored ROI sits on one beat; accept the same window on
    any beat). ``concept`` is the clinical concept; ROIs may be keyed by the neutral
    segment name or the pathology name. Returns the matched ROI dict or None."""
    feats = grounding.features(packet)
    hr = feats.get("heart_rate") or 60
    rr = 60.0 / float(hr) if hr else 1.0
    tol = tol_ms / 1000.0
    acceptable = grounding.acceptable_roi_concepts(concept)
    for roi in grounding.rois(packet):
        if roi.get("lead") != lead or roi.get("concept") not in acceptable:
            continue
        start, end = float(roi["timeStartSec"]), float(roi["timeEndSec"])
        # phase of the click relative to the ROI window, modulo RR
        rel = ((time_sec - (start - tol)) % rr + rr) % rr
        if rel <= (end - start) + 2 * tol:
            return roi
    return None


def _grade_click(item: ClinicalCaseItem, packet: dict[str, Any], answer: ClinicalAnswer) -> dict[str, Any]:
    tested = _tested_objectives(item, packet)
    if answer.timed_out or answer.click is None or item.roi_target is None:
        return _grade_dict(item, 0.0, tested, correct=False,
                           feedback="No click registered.", timed_out=answer.timed_out)
    matched = periodic_click_match(packet, item.roi_target.concept, answer.click.lead, answer.click.time_sec)
    correct = matched is not None
    # §16A2: click items grade by ROI geometry; axes are click-specific, no calibration.
    axes = {
        "concept_identification": 1.0 if correct else 0.0,
        "lead_selection": 1.0 if answer.click.lead in (item.roi_target.leads or []) else 0.0,
        "region_accuracy": 1.0 if correct else 0.0,
    }
    feedback = (
        f"Correct — that lands inside the {item.roi_target.concept.replace('_', ' ')} window."
        if correct
        else f"Not inside the target {item.roi_target.concept.replace('_', ' ')}; check the anchor points."
    )
    return _grade_dict(item, 1.0 if correct else 0.0, tested, correct, feedback,
                       answer_class=None, axes=axes, confidence=answer.confidence,
                       viewer_actions=_discriminator_actions(item, packet, tested))


def _grade_fillin(
    item: ClinicalCaseItem, packet: dict[str, Any], answer: ClinicalAnswer
) -> dict[str, Any]:
    """Grade a unit-aware numeric response against the exact packet served.

    The target value is never copied into the learner payload.  A response
    within the authored tolerance is successful; a near miss earns visible
    partial practice credit but is still recorded as a miss for the exact
    formative measurement cell.
    """

    tested = _tested_objectives(item, packet)
    task = item.fill_in_task
    if answer.timed_out or answer.fill_in_value is None or task is None:
        return _grade_dict(
            item,
            0.0,
            tested,
            correct=False,
            feedback="Time." if answer.timed_out else "No measurement was entered.",
            axes={"measurement_accuracy": 0.0},
            confidence=answer.confidence,
            timed_out=answer.timed_out,
            calibration={"timedOut": answer.timed_out, "confidence": answer.confidence},
        )

    expected_raw = grounding.features(packet).get(task.expected_feature)
    try:
        expected = float(expected_raw)
        submitted = float(answer.fill_in_value)
    except (TypeError, ValueError):
        expected = math.nan
        submitted = math.nan
    if not math.isfinite(expected) or not math.isfinite(submitted):
        return _grade_dict(
            item,
            0.0,
            tested,
            correct=False,
            feedback="This measurement could not be graded from the grounded ECG packet.",
            axes={"measurement_accuracy": 0.0},
            confidence=answer.confidence,
        )

    error = abs(submitted - expected)
    correct = error <= task.tolerance
    score = 1.0 if correct else (0.5 if error <= 2 * task.tolerance else 0.0)
    submitted_text = f"{submitted:g} {task.unit}"
    expected_text = f"{expected:g} {task.unit}"
    feedback = (
        f"Within range — {submitted_text} is within ±{task.tolerance:g} {task.unit} "
        f"of the packet measurement ({expected_text})."
        if correct
        else f"Your estimate was {submitted_text}; the packet measurement is {expected_text}. "
        "Recheck QRS onset, T-wave end, and the ECG grid scale."
    )
    high_conf_wrong = bool(not correct and confidence_band(answer.confidence) == "high")
    return _grade_dict(
        item,
        score,
        tested,
        correct,
        feedback,
        answer_class=None,
        axes={"measurement_accuracy": score},
        confidence=answer.confidence,
        calibration={
            "measurementError": round(error, 3),
            "highConfidenceWrong": high_conf_wrong,
            "confidence": answer.confidence,
        },
        viewer_actions=_discriminator_actions(item, packet, tested),
    )


def _grade_matching(
    item: ClinicalCaseItem, packet: dict[str, Any], answer: ClinicalAnswer
) -> dict[str, Any]:
    """Grade a source-boundary mapping without manufacturing pathology mastery."""

    task = item.matching_task
    if task is None:
        return _grade_dict(
            item,
            0.0,
            [],
            correct=False,
            feedback="This matching task could not be graded.",
            axes={"evidence_source_matching": 0.0},
            confidence=answer.confidence,
        )

    axis_by_source = {
        "ecg_support": "ecg_evidence",
        "authored_context": "authored_context_boundary",
        "unsupported_claim": "unsupported_claim_boundary",
    }
    valid_choice_ids = {choice.id for choice in task.choices}
    expected_row_ids = {row.id for row in task.rows}
    submitted_row_ids = set(answer.matches)
    complete_shape = (
        submitted_row_ids == expected_row_ids
        and all(choice_id in valid_choice_ids for choice_id in answer.matches.values())
        and len(set(answer.matches.values())) == len(expected_row_ids)
    )
    row_results: list[dict[str, Any]] = []
    axes: dict[str, float] = {}
    for row in task.rows:
        submitted = answer.matches.get(row.id)
        row_correct = bool(
            not answer.timed_out
            and complete_shape
            and submitted == row.correct_choice_id
        )
        axes[axis_by_source[row.source_type]] = 1.0 if row_correct else 0.0
        row_results.append(
            {
                "rowId": row.id,
                "submittedChoiceId": submitted,
                "correctChoiceId": row.correct_choice_id,
                "correct": row_correct,
            }
        )
    score = sum(1.0 for result in row_results if result["correct"]) / len(row_results)
    correct = bool(row_results) and all(result["correct"] for result in row_results)
    axes["evidence_source_matching"] = round(score, 3)
    if answer.timed_out:
        feedback = "Time. Review which facts come from the ECG, the vignette, or neither."
    elif not complete_shape:
        feedback = "Complete one valid evidence source for every clause."
    elif correct:
        feedback = "All three evidence boundaries are correct."
    else:
        correct_count = sum(1 for result in row_results if result["correct"])
        feedback = f"{correct_count} of {len(row_results)} evidence boundaries are correct."
    result = _grade_dict(
        item,
        score,
        [],
        correct=correct,
        feedback=feedback,
        answer_class=None,
        axes=axes,
        confidence=answer.confidence,
        calibration={
            "highConfidenceWrong": bool(
                not correct and confidence_band(answer.confidence) == "high"
            ),
            "confidence": answer.confidence,
            "matchingComplete": complete_shape,
        },
        timed_out=answer.timed_out,
    )
    result["matchingResults"] = row_results
    result["matchingCorrect"] = correct
    return result


def _grade_spoterror(item: ClinicalCaseItem, packet: dict[str, Any], answer: ClinicalAnswer) -> dict[str, Any]:
    tested = _tested_objectives(item, packet)
    if answer.timed_out:
        return _grade_dict(item, 0.0, tested, correct=False, feedback="Time.", timed_out=True)
    bad_ids = {ln.id for ln in item.machine_read if ln.bad}
    line_ok = answer.machine_line_id in bad_ids
    click_ok = False
    if answer.click is not None and item.roi_target is not None:
        click_ok = periodic_click_match(packet, item.roi_target.concept, answer.click.lead, answer.click.time_sec) is not None
    score = 0.5 * (1.0 if line_ok else 0.0) + 0.5 * (1.0 if click_ok else 0.0)
    correct = score >= 0.75
    axes = {"machine_audit": 1.0 if line_ok else 0.0, "proof_on_trace": 1.0 if click_ok else 0.0}
    feedback = (
        "You caught the wrong machine line and proved it on the trace."
        if correct
        else "Audit the machine read line-by-line, then click the part of the trace that disproves it."
    )
    return _grade_dict(item, score, tested, correct, feedback, axes=axes, confidence=answer.confidence,
                       viewer_actions=_discriminator_actions(item, packet, tested))


def _grade_stepwise(item: ClinicalCaseItem, packet: dict[str, Any], answer: ClinicalAnswer) -> dict[str, Any]:
    """Grade the ECG sequence separately from the downstream clinical action."""
    action_grade = _grade_option_based(item, packet, answer)
    if answer.timed_out:
        # The option grader has already produced the uniform timeout result.
        # Never re-score prefilled/late step answers after the authoritative
        # clock expired, or a timeout could manufacture ECG mastery.
        action_grade.update({
            "stepResults": [False for _ in item.steps],
            "axisScores": {
                **(action_grade.get("axisScores") or {}),
                "ecg_sequence": 0.0,
                "clinical_decision": 0.0,
            },
            "clinicalApplicationEvidence": "formative_only",
        })
        return action_grade
    step_results = []
    for index, step in enumerate(item.steps):
        selected = answer.step_answers[index] if index < len(answer.step_answers) else -1
        step_results.append(
            0 <= selected < len(step.options) and bool(step.options[selected].correct)
        )
    sequence_score = sum(step_results) / len(step_results) if step_results else 0.0
    sequence_correct = bool(step_results) and all(step_results)
    action_correct = action_grade.get("answerClass") in _CORRECT_CLASSES and not action_grade.get("safetyFlags")
    combined = 0.55 * sequence_score + 0.45 * float(action_grade["score"])
    tested = _tested_objectives(item, packet)
    overall_correct = sequence_correct and action_correct
    action_grade.update(
        {
            "score": round(combined, 3),
            "correctObjectives": tested if sequence_correct else [],
            "missedObjectives": [] if sequence_correct else tested,
            # Sequence performance remains visible in the formative axes and
            # exact event history, but this unreviewed item cannot move mastery.
            "masteryDelta": {},
            "axisScores": {
                **(action_grade.get("axisScores") or {}),
                "ecg_sequence": round(sequence_score, 3),
                "clinical_decision": round(
                    float(
                        (action_grade.get("axisScores") or {}).get(
                            "clinical_decision", action_grade["score"]
                        )
                    ),
                    3,
                ),
            },
            "stepResults": step_results,
            "clinicalApplicationEvidence": "formative_only",
        }
    )
    if sequence_correct and not action_correct:
        action_grade["feedback"] = "ECG sequence correct; reconsider the clinical decision."
    elif not sequence_correct and action_correct:
        action_grade["feedback"] = "The action may be safe, but rebuild the ECG sequence before naming the pattern."
    elif overall_correct:
        action_grade["feedback"] = "ECG sequence and clinical decision are aligned."
    return action_grade


def grade_clinical_answer(item: ClinicalCaseItem, packet: dict[str, Any], answer: ClinicalAnswer) -> dict[str, Any]:
    if item.question_type == "click":
        grade = _grade_click(item, packet, answer)
    elif item.question_type == "fillin":
        grade = _grade_fillin(item, packet, answer)
    elif item.question_type == "matching":
        grade = _grade_matching(item, packet, answer)
    elif item.question_type == "spoterror":
        grade = _grade_spoterror(item, packet, answer)
    elif item.question_type == "stepwise":
        grade = _grade_stepwise(item, packet, answer)
    else:
        grade = _grade_option_based(item, packet, answer)
    grade["firstLookAssessment"] = _first_look_assessment(item, packet, answer)
    return grade


def _first_look_assessment(
    item: ClinicalCaseItem, packet: dict[str, Any], answer: ClinicalAnswer
) -> dict[str, Any]:
    """Score only the broad pre-context category as formative evidence.

    A category agreement is useful calibration/debrief data, but it cannot award
    exact pathology recognition because the learner did not name or prove an
    objective-specific finding.
    """
    supported = {
        claim.objective_id
        for claim in item.evidence_manifest.ecg_supports
        if claim.objective_id in grounding.supported_objectives(packet)
    }
    expected: set[str] = set()
    for objective in supported:
        if objective == "normal_ecg":
            expected.add("normal_or_no_dominant_abnormality")
        elif objective in {
            "rate", "sinus_rhythm", "bradycardia", "atrial_fibrillation", "atrial_flutter",
            "supraventricular_tachycardia", "paced_rhythm", "premature_atrial_complex",
            "premature_ventricular_complex",
        }:
            expected.add("rate_or_rhythm")
        elif any(token in objective for token in (
            "block", "bundle", "fascicular", "qrs", "qt", "preexc", "wolff", "axis"
        )):
            expected.add("conduction_or_interval")
        elif any(token in objective for token in (
            "st_", "ischemia", "infarction", "_mi", "t_wave", "pericarditis"
        )):
            expected.add("st_t_or_ischemia")
        elif any(token in objective for token in (
            "hypertrophy", "enlargement", "voltage", "r_wave_progression"
        )):
            expected.add("chamber_or_voltage")
    if not expected:
        expected.add("uncertain")
    submitted = answer.first_look_finding
    return {
        "submittedCategory": submitted,
        "confidence": answer.first_look_confidence,
        "expectedCategories": sorted(expected),
        "agreement": submitted in expected if submitted is not None else None,
        "formativeOnly": True,
        "exactPathologyMasterySuppressed": True,
    }
