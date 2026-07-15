"""Shared executable assessment contracts.

The registry may describe a curriculum objective without implying that every
mode can assess it independently.  Predicates here are imported by both the
adaptive planner and the serving/grading route so a recommended path cannot
diverge from the contract enforced at submission time.
"""

from __future__ import annotations

from typing import Any, Iterable

from .source_policy import eligible_packet_objectives, packet_allows_learning_evidence


RAPID_SYNTHESIS_RECEIPT_UNAVAILABLE_REASON = (
    "Rapid complete reads are formative-only until deterministic per-domain "
    "synthesis grading is implemented."
)


RAPID_TESTED_OBJECTIVE_MANIFEST_VERSION = "rapid-tested-objectives-v2"

# Broad Rapid cases are multi-label packets, but a learner cannot reasonably be
# treated as having missed every incidental label.  This is the same clinical
# ordering used by the deterministic grader: distinctive/high-priority findings
# precede ubiquitous measurements and normal descriptors.
RAPID_RECOGNITION_PRIORITY: tuple[str, ...] = (
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
)


def _ordered_rapid_recognition_objectives(packet: dict[str, Any]) -> list[str]:
    eligible = set(eligible_packet_objectives(packet, "rapid", "recognize"))
    confidence = packet.get("concept_confidence") or {}
    priority = {
        objective_id: index
        for index, objective_id in enumerate(RAPID_RECOGNITION_PRIORITY)
    }

    def sort_key(objective_id: str) -> tuple[int, int, float, str]:
        evidence = confidence.get(objective_id) or {}
        tier_rank = 0 if evidence.get("tier") == "A" else 1
        return (
            tier_rank,
            priority.get(objective_id, len(priority)),
            -float(evidence.get("score") or 0.0),
            objective_id,
        )

    return sorted(eligible, key=sort_key)


def _tested_entry(
    objective_id: str,
    subskill: str,
    *,
    role: str,
    source: str,
    lapse_eligible: bool,
) -> dict[str, Any]:
    return {
        "objectiveId": objective_id,
        "subskill": subskill,
        "role": role,
        "source": source,
        "lapseEligible": lapse_eligible,
        # Unsupported overcalls are calibration evidence for this task. They
        # are not negative evidence for the overcalled pathology unless a
        # future, reviewed contrast task explicitly opts into that contract.
        "negativeDiscrimination": False,
    }


def rapid_tested_objective_manifest(
    packet: dict[str, Any],
    *,
    assessment_scope: str,
    focus_concept: str | None = None,
    focus_subskill: str | None = None,
    receipt_concept: str | None = None,
    synthesis_allowed: bool = False,
) -> dict[str, Any]:
    """Freeze the server-owned competency targets for one Rapid item.

    The manifest is stored with the pending item but stripped from every
    learner-facing pending payload. Only its required entries may generate
    either positive or negative competency evidence. Incidental selections are
    feedback-only, even when the packet supports them.
    """

    focused = bool(focus_concept)
    task_kind = (
        "focused_handoff"
        if focused
        else "dominant_finding"
        if assessment_scope == "dominant_finding"
        else "full_read"
    )
    objectives: list[dict[str, Any]] = []
    if focused:
        requested_subskill = focus_subskill or "recognize"
        requested_objective = (receipt_concept or focus_concept or "").strip()
        # Keep the compatibility argument but do not allow a caller-provided
        # flag to bypass the global synthesis evidence boundary.
        _ = synthesis_allowed
        if requested_subskill == "recognize" and requested_objective:
            source = packet_allows_learning_evidence(
                packet, "rapid", requested_objective, "recognize"
            )
            if source.allowed:
                objectives.append(
                    _tested_entry(
                        requested_objective,
                        "recognize",
                        role="required",
                        source="focused_handoff",
                        lapse_eligible=True,
                    )
                )
    else:
        limit = 1 if assessment_scope == "dominant_finding" else 3
        source = "dominant_finding" if limit == 1 else "full_read"
        objectives.extend(
            _tested_entry(
                objective_id,
                "recognize",
                role="required",
                source=source,
                lapse_eligible=True,
            )
            for objective_id in _ordered_rapid_recognition_objectives(packet)[:limit]
        )

    return {
        "version": RAPID_TESTED_OBJECTIVE_MANIFEST_VERSION,
        "caseId": str(packet.get("case_id") or packet.get("caseId") or ""),
        "assessmentScope": assessment_scope,
        "taskKind": task_kind,
        "objectives": objectives,
        # Compatibility fields remain explicit so old clients can render the
        # released manifest, but success-only incidental receipt targets are no
        # longer added after the learner submits.
        "allowSelectedExtras": False,
        "selectedSupportedExtras": [],
        "overcallPolicy": "blocks_frozen_target_success_without_scoring_overcalled_pathology",
    }


def finalize_rapid_tested_objective_manifest(
    manifest: dict[str, Any],
    packet: dict[str, Any],
    selected_concepts: Iterable[str],
) -> dict[str, Any]:
    """Return the frozen manifest without learner-selected receipt targets."""

    # ``packet`` and ``selected_concepts`` remain in the signature because the
    # route calls this at commit time. They may inform feedback elsewhere, but
    # never expand the server-owned independent assessment contract.
    _ = packet, selected_concepts
    return {
        **manifest,
        "objectives": [dict(entry) for entry in manifest.get("objectives") or []],
        "allowSelectedExtras": False,
        "selectedSupportedExtras": [],
    }


def bound_rapid_grade_to_manifest(
    grade: dict[str, Any],
    manifest: dict[str, Any],
    selected_concepts: Iterable[str],
) -> dict[str, Any]:
    """Make recognition feedback describe the frozen task, not every co-label."""

    bounded = {**grade, "testedObjectiveManifest": manifest}
    required = [
        str(entry.get("objectiveId") or "")
        for entry in manifest.get("objectives") or []
        if entry.get("subskill") == "recognize" and entry.get("lapseEligible")
    ]
    required = list(dict.fromkeys(value for value in required if value))
    if not required:
        return bounded

    selected = {str(value) for value in selected_concepts if value}
    grader_correct = {
        str(value) for value in grade.get("correctObjectives") or [] if value
    }
    correct = [
        objective_id
        for objective_id in required
        if objective_id in selected and objective_id in grader_correct
    ]
    missed = [objective_id for objective_id in required if objective_id not in correct]
    overcalled = list(dict.fromkeys(grade.get("overcalledObjectives") or []))
    score = len(correct) / len(required)
    if overcalled:
        # An indiscriminate response cannot pass an independent recognition
        # target merely because the correct label was included in the set.
        score = min(0.49, max(0.0, score - min(0.35, len(overcalled) * 0.12)))

    feedback: list[str] = []
    if correct:
        feedback.append("Matched tested target(s): " + ", ".join(correct) + ".")
    if missed:
        feedback.append("Review tested target(s): " + ", ".join(missed) + ".")
    if overcalled:
        feedback.append(
            "Unsupported selection(s) blocked the task precision gate: "
            + ", ".join(overcalled)
            + "."
        )
    bounded.update(
        {
            "score": round(score, 3),
            "correctObjectives": correct,
            "missedObjectives": missed,
            "feedback": " ".join(feedback) or "No tested recognition target was matched.",
            "testedObjectives": required,
            "selectionPrecisionPassed": not overcalled,
            "supportedSelectedExtras": [],
        }
    )
    return bounded


def rapid_synthesis_contract_available(
    objective_id: str, case_concept: str
) -> bool:
    """Whether Rapid can currently emit independent synthesis evidence.

    A non-empty eight-field sweep proves task completion, not the correctness
    of each interpretation domain. Keep every exact and aliased synthesis cell
    out of executable mastery plans until those domains have deterministic,
    packet-grounded grading contracts.
    """

    _ = objective_id, case_concept
    return False
