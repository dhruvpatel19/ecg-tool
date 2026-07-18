"""Evidence-led adaptive study plans.

This scheduler is deliberately separate from the conversational tutor.  It
does not ask a language model to guess what a learner needs: it ranks only
server-verified concept × subskill receipts, retention timing, calibration
errors, case diversity, and the currently eligible real-ECG inventory.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Iterable
from urllib.parse import quote

from .assessment_contracts import rapid_synthesis_contract_available
from .objectives import OBJECTIVES, ObjectiveDefinition
from .ontology import concept_label
from .rapid_rhythm_supplement import RUNTIME_OBJECTIVE_IDS
from .retention import DURABLE_DISTINCT_SUCCESSFUL_ECGS, competency_state
from .subskill_tasks import training_independent_receipt_available


_STUDY_PLAN_RETURN = quote("/home?panel=plan", safe="")
_TRAINING_STAGE_LENGTH = 25
_RAPID_STAGE_LENGTH = 10
_BASELINE_RAPID_STAGE_LENGTH = 5
_RAPID_PACES = {"untimed", "ward", "emergency"}
_EMERGENCY_RHYTHM_CONCEPTS = RUNTIME_OBJECTIVE_IDS


# Each destination is an authored, routable scene in the production Guided
# curriculum.  The planner never fabricates a lesson from corpus labels: it can
# only offer one of these reviewed concept -> scene repairs, and the resulting
# work remains formative regardless of completion or score.
_GUIDED_REMEDIATION_DESTINATIONS: dict[str, tuple[str, str, str]] = {
    "normal_ecg": ("leads-vectors", "M02.S1", "Why one beat looks different in twelve leads"),
    "rate": ("rhythm-ectopy", "M03.S3", "Rate when rhythm is not tidy"),
    "sinus_rhythm": ("rhythm-ectopy", "M03.S4", "Sinus is a source, not a speed"),
    "axis_normal": ("leads-vectors", "M02.S10", "Axis quadrants from QRS polarity"),
    "left_axis_deviation": ("leads-vectors", "M02.S10", "Axis quadrants from QRS polarity"),
    "right_axis_deviation": ("leads-vectors", "M02.S10", "Axis quadrants from QRS polarity"),
    "premature_atrial_complex": ("rhythm-ectopy", "M03.S7", "Find the early P wave in a PAC"),
    "premature_ventricular_complex": ("rhythm-ectopy", "M03.S8", "PVC timing and altered activation"),
    "bradycardia": ("av-brady", "m04-s9", "Separate the bradycardia tracing from perfusion"),
    "av_block_first_degree": ("av-brady", "m04-s3", "Every P conducts, but slowly"),
    "av_block_second_degree_mobitz_i": ("av-brady", "m04-s4", "Recognize grouped beating and progressive delay"),
    "av_block_second_degree_mobitz_ii": ("av-brady", "m04-s5", "A dropped QRS without progressive delay"),
    "av_block_third_degree": ("av-brady", "m04-s7", "Recognize two uncoupled clocks"),
    "atrial_fibrillation": ("tachyarrhythmias", "m06-s5", "Build atrial-fibrillation evidence"),
    "atrial_flutter": ("tachyarrhythmias", "m06-s4", "Find flutter hidden behind 2:1 conduction"),
    "supraventricular_tachycardia": ("tachyarrhythmias", "m06-s2", "Separate sinus tachycardia from regular narrow SVT"),
    "wide_complex_tachycardia": ("tachyarrhythmias", "m06-s7", "Reason safely through regular wide-complex tachycardia"),
    "ventricular_tachycardia": ("tachyarrhythmias", "m06-s7", "Reason safely through ventricular tachycardia"),
    "polymorphic_ventricular_tachycardia": ("tachyarrhythmias", "m06-s7", "Distinguish polymorphic ventricular tachycardia from close mimics"),
    "ventricular_flutter": ("tachyarrhythmias", "m06-s7", "Compare organized ventricular flutter with ventricular fibrillation"),
    "ventricular_fibrillation": ("tachyarrhythmias", "m06-s7", "Recognize ventricular fibrillation and respect the patient-state boundary"),
    "qrs_duration": ("ventricular-conduction", "m05-s0", "Keep QRS width separate from morphology"),
    "right_bundle_branch_block": ("ventricular-conduction", "m05-s2", "Prove RBBB with paired-lead anchors"),
    "incomplete_right_bundle_branch_block": ("ventricular-conduction", "m05-s2", "Use width and paired-lead RBBB anchors"),
    "left_bundle_branch_block": ("ventricular-conduction", "m05-s3", "Prove LBBB with paired-lead anchors"),
    "nonspecific_intraventricular_conduction_delay": ("ventricular-conduction", "m05-s4", "Separate right, left, and nonspecific delay"),
    "left_anterior_fascicular_block": ("ventricular-conduction", "m05-s5", "Derive a fascicular axis shift"),
    "left_posterior_fascicular_block": ("ventricular-conduction", "m05-s5", "Derive a fascicular axis shift"),
    "wolff_parkinson_white": ("ventricular-conduction", "m05-s7", "Connect short PR, delta wave, and fused QRS"),
    "paced_rhythm": ("ventricular-conduction", "m05-s8", "Link each pacing spike to its response"),
    "atrial_enlargement": ("chambers-voltage", "m07-s1", "Use P-wave shape as atrial evidence"),
    "left_ventricular_hypertrophy": ("chambers-voltage", "m07-s2", "Assemble the LVH evidence bundle"),
    "right_ventricular_hypertrophy": ("chambers-voltage", "m07-s3", "Assemble right-ventricular evidence"),
    "qt_interval": ("repolarization-safety", "m08-s3", "Measure QT instead of accepting a machine label"),
    "qtc_prolongation": ("repolarization-safety", "m08-s4", "Understand rate correction as a model"),
    "electrolyte_drug_pattern": ("repolarization-safety", "m08-s7", "Keep ion patterns separate from lab results"),
    "nonspecific_st_t_change": ("repolarization-safety", "m08-s8", "Compare ST–T distributions, not slogans"),
    "pericarditis_pattern": ("repolarization-safety", "m08-s8", "Compare nonischemic ST–T distributions"),
    "r_wave_progression": ("leads-vectors", "M02.S12", "Rebuild R-wave progression and transition"),
    "st_depression": ("ischemia-infarction", "m09-s5", "Rank ST depression without binary overcall"),
    "st_elevation": ("ischemia-infarction", "m09-s1", "Use contiguous and reciprocal ST geography"),
    "t_wave_inversion": ("ischemia-infarction", "m09-s5", "Rank T-wave inversion without binary overcall"),
    "myocardial_ischemia": ("ischemia-infarction", "m09-s5", "Separate ischemia concern from close alternatives"),
    "myocardial_infarction": ("ischemia-infarction", "m09-s6", "Use Q-wave criteria and territory"),
    "anterior_mi": ("ischemia-infarction", "m09-s2", "Build precordial and lateral geography"),
    "lateral_mi": ("ischemia-infarction", "m09-s2", "Build precordial and lateral geography"),
    "septal_mi": ("ischemia-infarction", "m09-s2", "Build precordial and lateral geography"),
    "inferior_mi": ("ischemia-infarction", "m09-s3", "Build inferior geography before extension"),
    "posterior_mi": ("ischemia-infarction", "m09-s4", "Test a posterior mirror pattern"),
    "pathologic_q_waves": ("ischemia-infarction", "m09-s6", "Use Q-wave criteria and territory"),
}


_ONBOARDING = (
    "normal_ecg",
    "rate",
    "sinus_rhythm",
    "axis_normal",
    "qrs_duration",
    "qt_interval",
    "bradycardia",
    "atrial_fibrillation",
    "right_bundle_branch_block",
    "left_bundle_branch_block",
    "qtc_prolongation",
    "myocardial_infarction",
)
_ONBOARDING_RANK = {concept: index for index, concept in enumerate(_ONBOARDING)}
_FOUNDATION_ONBOARDING = (
    "normal_ecg",
    "rate",
    "sinus_rhythm",
    "axis_normal",
    "qrs_duration",
    "qt_interval",
)
_GOAL_ONBOARDING: dict[str, tuple[str, ...]] = {
    "build_fundamentals": _ONBOARDING,
    "exam_prep": (
        "normal_ecg", "rate", "sinus_rhythm", "axis_normal",
        "atrial_fibrillation", "right_bundle_branch_block",
        "left_bundle_branch_block", "myocardial_infarction", "qtc_prolongation",
    ),
    "clinical_reading": (
        "normal_ecg", "rate", "sinus_rhythm", "atrial_fibrillation",
        "qrs_duration", "myocardial_infarction", "qtc_prolongation",
    ),
    "emergency_prioritization": (
        "wide_complex_tachycardia", "bradycardia", "st_elevation",
        "myocardial_infarction", "atrial_fibrillation", "rate", "qtc_prolongation",
    ),
    "medication_safety": (
        "qtc_prolongation", "qt_interval", "bradycardia",
        "av_block_first_degree", "electrolyte_drug_pattern",
        "atrial_fibrillation", "qrs_duration",
    ),
}
_SUBSKILL_RANK = {
    "recognize": 0,
    "discriminate": 1,
    "localize": 2,
    "measure": 3,
    "explain_mechanism": 4,
    "synthesize": 5,
    "apply_in_context": 6,
    "calibrate_confidence": 7,
}

_TRAINING_RECEIPT_SUBSKILLS = {
    "localize",
    "measure",
    "discriminate",
    "explain_mechanism",
    "calibrate_confidence",
}


def _receipt_mode(
    definition: ObjectiveDefinition, case_concept: str, subskill: str
) -> str | None:
    """Return the mode with an implemented independent receipt contract.

    Proxy objective-to-case mappings stay formative unless the task itself is
    explicitly objective-level. Rapid synthesis is also formative until every
    sweep domain has deterministic grading; Training tasks currently close
    exact corpus concepts only. Clinical application remains formative pending
    named clinician sign-off and therefore cannot enter this mastery queue.
    """
    if subskill == "synthesize":
        return "rapid" if rapid_synthesis_contract_available(
            definition.id, case_concept
        ) else None
    if definition.id != case_concept:
        return None
    if subskill == "recognize":
        return "rapid"
    if subskill in _TRAINING_RECEIPT_SUBSKILLS:
        if not training_independent_receipt_available(case_concept, subskill):
            return None
        return "train"
    return None


def _best_case_concept(definition: ObjectiveDefinition, counts: dict[str, int]) -> str | None:
    # A plan presented as a path to durable mastery must be capable of meeting
    # the same distinct-ECG gate as the retention model. A one-positive family
    # can remain formative, but cannot appear in this durable receipt queue.
    available = [
        concept for concept in definition.case_concepts
        if int(counts.get(concept, 0)) >= DURABLE_DISTINCT_SUCCESSFUL_ECGS
    ]
    if not available:
        return None
    # Preserve the authored mapping order; count only breaks ties between
    # aliases with the same priority.
    return max(available, key=lambda concept: (int(counts.get(concept, 0)), -definition.case_concepts.index(concept)))


def _priority(cell: dict[str, Any]) -> tuple[Any, ...]:
    observed = cell["independentAttempts"] > 0 or cell["attempts"] > 0
    due_state = cell["dueState"]
    if observed and due_state == "overdue":
        lane = 0
    elif observed and cell["isDue"]:
        lane = 1
    elif observed and cell["highConfidenceWrong"] > 0:
        lane = 2
    elif cell["independentAttempts"] > 0 and cell["independentMastery"] < 0.55:
        lane = 3
    elif observed and cell["state"] != "durable":
        lane = 4
    else:
        lane = 5
    return (
        lane,
        -cell["overdueDays"],
        -cell["highConfidenceWrong"],
        cell["independentMastery"] if cell["independentAttempts"] else 0.0,
        cell["distinctSuccessfulEcgs"],
        int(cell.get(
            "preferenceRank",
            _ONBOARDING_RANK.get(cell["caseConcept"], len(_ONBOARDING_RANK) + 1),
        )),
        _SUBSKILL_RANK.get(cell["subskill"], 99),
        cell["objectiveId"],
    )


def _reason(cell: dict[str, Any]) -> str:
    label = cell["label"]
    skill = cell["subskill"].replace("_", " ")
    if cell["dueState"] == "overdue":
        return f"{label} · {skill} is overdue for retrieval by {cell['overdueDays']:.1f} days."
    if cell["isDue"]:
        return f"{label} · {skill} is due now; a fresh ECG will test retention."
    if cell["highConfidenceWrong"]:
        return f"{label} · {skill} has {cell['highConfidenceWrong']} high-confidence miss(es), so calibration and close mimics take priority."
    if cell["independentAttempts"]:
        checks = int(cell["independentAttempts"])
        successful_ecgs = int(cell["distinctSuccessfulEcgs"])
        estimate = round(cell["independentMastery"] * 100)
        prefix = (
            f"After {checks} independent check{'s' if checks != 1 else ''}, the current mastery "
            f"estimate for {label} · {skill} is {estimate}%"
        )
        if successful_ecgs == 0:
            return f"{prefix}; no successful ECG has been recorded yet."
        return (
            f"{prefix}, with success on {successful_ecgs} different "
            f"ECG{'s' if successful_ecgs != 1 else ''}."
        )
    if cell["attempts"]:
        return f"You have practiced {label} · {skill} with support but have not yet completed an unassisted check."
    return f"{label} · {skill} has not yet been checked; begin with a real ECG."


def _guided_remediation_reason(cell: dict[str, Any]) -> str | None:
    """Return an evidence-backed conceptual-repair reason, never a prior.

    Unseen work alone is not proof that a learner lacks understanding. Guided
    remediation is prescribed only after an observed high-confidence miss,
    repeated low independent performance, or repeated lapses.
    """

    if cell["highConfidenceWrong"] > 0:
        return (
            f"{cell['highConfidenceWrong']} high-confidence miss(es) suggest that the underlying "
            "rule should be rebuilt before another unannounced check."
        )
    if cell["independentAttempts"] >= 2 and cell["independentMastery"] < 0.45:
        return (
            f"Unassisted performance is {round(cell['independentMastery'] * 100)}% after "
            f"{cell['independentAttempts']} checks, which supports a short concept repair."
        )
    if cell["lapses"] >= 2:
        return (
            f"{cell['lapses']} retrieval lapses suggest that the concept model needs a brief rebuild "
            "before another transfer check."
        )
    return None


def _guided_remediation(
    cell: dict[str, Any] | None, *, before_stage_order: int | None
) -> dict[str, Any] | None:
    if not cell:
        return None
    destination = _GUIDED_REMEDIATION_DESTINATIONS.get(cell["caseConcept"])
    trigger = _guided_remediation_reason(cell)
    if not destination or not trigger:
        return None
    module_id, scene_id, scene_title = destination
    return {
        "mode": "guided",
        "title": f"Rebuild {cell['label']} before the next check",
        "purpose": (
            f"Work through the authored “{scene_title}” scene, then return for the unannounced ECG check. "
            "This lesson is supportive practice and does not count as independent mastery evidence."
        ),
        "href": f"/learn/{quote(module_id)}?scene={quote(scene_id)}",
        "moduleId": module_id,
        "sceneId": scene_id,
        "concept": cell["caseConcept"],
        "evidenceKind": "formative_guided",
        "updatesIndependentMastery": False,
        "beforeStageOrder": before_stage_order,
        "reason": trigger,
    }


def _preferred_session_contract(
    preferences: dict[str, Any] | None,
) -> tuple[int, int, str]:
    """Map learner defaults onto lengths each mode can actually deliver."""

    if not preferences:
        return _TRAINING_STAGE_LENGTH, _RAPID_STAGE_LENGTH, "untimed"
    requested = preferences.get("defaultSessionLength", _RAPID_STAGE_LENGTH)
    if isinstance(requested, bool) or requested not in {5, 10, 25, 50}:
        requested = _RAPID_STAGE_LENGTH
    training_length = 10 if int(requested) == 5 else int(requested)
    rapid_pace = str(preferences.get("rapidPace") or "untimed")
    if rapid_pace not in _RAPID_PACES:
        rapid_pace = "untimed"
    return training_length, int(requested), rapid_pace


def _preferred_onboarding_rank(
    preferences: dict[str, Any] | None,
) -> dict[str, int]:
    """Use stated context only to break evidence-free priority ties.

    Due work, confident misses, and observed performance still own the higher
    priority lanes. A preference can decide which *unseen* skill establishes a
    baseline first; it can never overwrite or invent competency evidence.
    """

    if not preferences:
        return _ONBOARDING_RANK
    goal = str(preferences.get("primaryGoal") or "build_fundamentals")
    goal_order = _GOAL_ONBOARDING.get(goal, _ONBOARDING)
    stage = str(preferences.get("trainingStage") or "not_set")
    ordered = (
        (*_FOUNDATION_ONBOARDING, *goal_order, *_ONBOARDING)
        if stage == "preclinical"
        else (*goal_order, *_ONBOARDING)
    )
    unique = tuple(dict.fromkeys(ordered))
    return {concept: index for index, concept in enumerate(unique)}


def _stage(
    cell: dict[str, Any], *, order: int, stage_kind: str,
    training_length: int, rapid_length: int, rapid_pace: str,
) -> dict[str, Any]:
    concept = cell["caseConcept"]
    objective = cell["objectiveId"]
    label = cell["label"]
    subskill = cell["subskill"]
    mode = cell["receiptMode"]
    if mode == "train":
        return {
            "order": order,
            "stageKind": stage_kind,
            "status": "current",
            "mode": "train",
            "title": f"Build {label} · {subskill.replace('_', ' ')}",
            "purpose": (
                "Practice this specific skill, then check it again on an unannounced ECG without a hint. "
                "Only the unassisted check counts toward independent mastery."
            ),
            "href": (
                f"/train?concept={quote(concept)}&receiptConcept={quote(objective)}"
                f"&subskill={quote(subskill)}&suggestedLength={training_length}"
                f"&returnTo={_STUDY_PLAN_RETURN}"
            ),
            "suggestedLength": training_length,
            "receiptConcept": objective,
            "receiptSubskill": subskill,
            "evidenceKind": "independent_transfer",
        }
    # The first Rapid stage is a bounded diagnostic, not a full study session.
    # Keep it short and untimed so an evidence-free learner can establish a
    # useful starting point without their longer-session or urgency preference
    # turning onboarding into a high-pressure assessment. Once independent
    # evidence exists, the learner's saved Rapid length and pace apply again.
    effective_rapid_length = (
        _BASELINE_RAPID_STAGE_LENGTH
        if stage_kind == "baseline"
        else rapid_length
    )
    effective_rapid_pace = (
        "untimed"
        if stage_kind == "baseline"
        else "ward"
        if subskill == "synthesize" and rapid_pace == "emergency"
        else rapid_pace
    )
    emergency_rhythm = concept in _EMERGENCY_RHYTHM_CONCEPTS
    return {
        "order": order,
        "stageKind": stage_kind,
        "status": "current",
        "mode": "rapid",
        "title": (
            f"Build {label} · complete-read synthesis"
            if subskill == "synthesize"
            else f"Check {label} · emergency-rhythm recognition"
            if emergency_rhythm
            else f"Check {label} · independent recognition"
        ),
        "purpose": (
            "Complete every step of the systematic read, commit an evidence-limited synthesis, and avoid unsupported calls on an unannounced real ECG."
            if subskill == "synthesize"
            else "Name the rhythm on a new source-author-labelled single-lead fragment. Patient state and management remain separately contextualized and formative."
            if emergency_rhythm
            else "Choose the finding on an unannounced real ECG. Both correct checks and focused misses shape what you practice next."
        ),
        "href": (
            f"/rapid?focus={quote(concept)}&receiptConcept={quote(objective)}"
            f"&subskill={quote(subskill)}&suggestedLength={effective_rapid_length}"
            f"&pace={quote(effective_rapid_pace)}"
            f"{'&practiceMode=emergency' if emergency_rhythm else ''}"
            f"&returnTo={_STUDY_PLAN_RETURN}"
        ),
        "suggestedLength": effective_rapid_length,
        "suggestedPace": effective_rapid_pace,
        "receiptConcept": objective,
        "receiptSubskill": subskill,
        "evidenceKind": "independent_transfer",
    }


def build_mastery_plan(
    profile: dict[str, Any],
    concept_counts: dict[str, int],
    *,
    definitions: Iterable[ObjectiveDefinition] | None = None,
    runtime_evidence: dict[str, str] | None = None,
    runtime_subskills: dict[str, set[str]] | None = None,
    clinical_concepts: set[str] | None = None,
    preferences: dict[str, Any] | None = None,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Build a transparent, actionable plan without inventing mastery."""
    preferred_onboarding = _preferred_onboarding_rank(preferences)
    observed = {
        (row["concept"], row["subskill"]): row
        for row in profile.get("subskillMastery", [])
    }
    candidates: list[dict[str, Any]] = []
    for definition in definitions or OBJECTIVES.values():
        evidence_ceiling = (runtime_evidence or {}).get(
            definition.id, definition.evidence_ceiling
        )
        if evidence_ceiling != "eligible_real_case":
            continue
        case_concept = _best_case_concept(definition, concept_counts)
        if not case_concept:
            continue
        for subskill in definition.allowed_subskills:
            if (
                runtime_subskills is not None
                and definition.id in runtime_subskills
                and subskill not in runtime_subskills[definition.id]
            ):
                continue
            actual = observed.get((definition.id, subskill), {})
            receipt_mode = _receipt_mode(definition, case_concept, subskill)
            if receipt_mode is None:
                continue
            candidates.append({
                "objectiveId": definition.id,
                "label": definition.label,
                "domain": definition.domain,
                "caseConcept": case_concept,
                "eligibleDistinct": int(concept_counts.get(case_concept, 0)),
                "subskill": subskill,
                "receiptMode": receipt_mode,
                "state": "unseen" if not actual else competency_state(actual),
                "attempts": int(actual.get("attempts", 0)),
                "independentAttempts": int(actual.get("independentAttempts", 0)),
                "independentMastery": float(actual.get("independentMastery", 0.0)) if actual else 0.0,
                "highConfidenceWrong": int(actual.get("highConfidenceWrong", 0)),
                "isDue": bool(actual.get("isDue", False)),
                "dueState": str(actual.get("dueState", "unseen")),
                "overdueDays": float(actual.get("overdueDays", 0.0)),
                "nextDueAt": actual.get("nextDueAt"),
                "stabilityDays": float(actual.get("stabilityDays", 0.0)),
                "distinctSuccessfulEcgs": int(actual.get("distinctSuccessfulEcgs", 0)),
                "distinctModes": int(actual.get("distinctModes", 0)),
                "lapses": int(actual.get("lapses", 0)),
                "preferenceRank": preferred_onboarding.get(
                    case_concept,
                    len(preferred_onboarding) + _ONBOARDING_RANK.get(
                        case_concept, len(_ONBOARDING_RANK) + 1
                    ),
                ),
            })

    # Alias objectives can map to the same runnable concept/subskill. Keep the
    # one with real learner evidence, otherwise the canonical concept objective.
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for cell in candidates:
        key = (cell["caseConcept"], cell["subskill"])
        previous = deduped.get(key)
        if previous is None:
            deduped[key] = cell
            continue
        score = (
            int(cell["attempts"] > 0),
            int(cell["objectiveId"] == cell["caseConcept"]),
            -_priority(cell)[0],
        )
        previous_score = (
            int(previous["attempts"] > 0),
            int(previous["objectiveId"] == previous["caseConcept"]),
            -_priority(previous)[0],
        )
        if score > previous_score:
            deduped[key] = cell

    ranked = sorted(deduped.values(), key=_priority)
    # This is a competency-cell observation count, not a distinct ECG count:
    # one complete Rapid read can emit evidence for several exact skills. Keep
    # the legacy field as an additive compatibility alias, but state the unit
    # explicitly so UI and plan-coach language cannot call it an ECG total.
    independent_count = sum(cell["independentAttempts"] for cell in ranked)
    due_count = sum(1 for cell in ranked if cell["isDue"])
    overdue_count = sum(1 for cell in ranked if cell["dueState"] == "overdue")
    high_confidence_misses = sum(cell["highConfidenceWrong"] for cell in ranked)
    baseline_needed = independent_count == 0
    primary = ranked[0] if ranked else None
    training_length, rapid_length, rapid_pace = _preferred_session_contract(preferences)

    priorities = []
    used_concepts: set[str] = set()
    for cell in ranked:
        if cell["caseConcept"] in used_concepts and len(priorities) >= 3:
            continue
        priorities.append({**cell, "reason": _reason(cell)})
        used_concepts.add(cell["caseConcept"])
        if len(priorities) == 6:
            break

    if baseline_needed:
        plan_stage = "baseline"
    elif primary and primary["isDue"]:
        plan_stage = "retention"
    elif primary and (
        primary["highConfidenceWrong"] > 0
        or primary["independentMastery"] < 0.55
    ):
        plan_stage = "remediation"
    elif primary and primary["state"] != "durable":
        plan_stage = "consolidation"
    else:
        plan_stage = "extension"

    stages: list[dict[str, Any]] = []
    if primary:
        stages.append(
            _stage(
                primary,
                order=1,
                stage_kind=plan_stage,
                training_length=training_length,
                rapid_length=rapid_length,
                rapid_pace=rapid_pace,
            )
        )

    guided_remediation = _guided_remediation(
        primary, before_stage_order=stages[0]["order"] if stages else None
    )

    secondary = next(
        (
            cell for cell in ranked
            if primary and cell["caseConcept"] != primary["caseConcept"] and cell["domain"] != primary["domain"]
        ),
        None,
    )
    synthesis_target = next(
        (
            cell for cell in ranked
            if primary
            and cell["caseConcept"] == primary["caseConcept"]
            and cell["subskill"] == "synthesize"
            and cell["receiptMode"] == "rapid"
        ),
        None,
    )
    def integration_ready(cell: dict[str, Any] | None) -> bool:
        return bool(
            cell
            and cell["independentAttempts"] >= 2
            and cell["independentMastery"] >= 0.6
            and cell["distinctSuccessfulEcgs"] >= 2
            and not cell["isDue"]
        )

    integration_unlocked = bool(
        not baseline_needed
        and synthesis_target
        and integration_ready(primary)
        and integration_ready(secondary)
    )
    integration = None
    if integration_unlocked and primary and secondary and synthesis_target:
        integration_pace = "ward" if rapid_pace == "emergency" else rapid_pace
        integration = {
            "primaryConcept": primary["caseConcept"],
            "secondaryConcept": secondary["caseConcept"],
            "receiptConcept": synthesis_target["objectiveId"],
            "receiptSubskill": "synthesize",
            "prompt": (
                f"On a mixed ECG, connect {concept_label(primary['caseConcept'])} with "
                f"{concept_label(secondary['caseConcept'])}: state the evidence for each, then explain how one changes "
                "your synthesis without allowing it to replace the complete sweep."
            ),
            "href": (
                f"/rapid?focus={quote(primary['caseConcept'])}"
                f"&secondaryConcept={quote(secondary['caseConcept'])}"
                f"&receiptConcept={quote(synthesis_target['objectiveId'])}"
                f"&subskill=synthesize&suggestedLength={rapid_length}"
                f"&pace={quote(integration_pace)}"
                f"&returnTo={_STUDY_PLAN_RETURN}"
            ),
            "suggestedLength": rapid_length,
            "suggestedPace": integration_pace,
        }

    # Clinical application is a useful *formative* transfer after the exact
    # receipt task, but it must never be inserted into the independent mastery
    # stages above.  Offer it separately only when the serving bank has an item
    # that explicitly assesses apply_in_context for that exact case concept.
    clinical_target = next(
        (
            cell
            for cell in ranked
            if cell["caseConcept"] in (clinical_concepts or set())
        ),
        None,
    )
    clinical_application = None
    if clinical_target:
        clinical_application = {
            "mode": "clinical",
            "title": f"Apply {clinical_target['label']} in a patient-care decision",
            "purpose": (
                "Use a different real ECG inside an authored patient scenario after the pattern check. "
                "The result shapes later recommendations but remains formative."
            ),
            "href": (
                f"/practice?focus={quote(clinical_target['caseConcept'])}"
                f"&subskill=apply_in_context&returnTo={_STUDY_PLAN_RETURN}"
            ),
            "concept": clinical_target["caseConcept"],
            "subskill": "apply_in_context",
            "evidenceKind": "formative_application",
            "afterStageOrder": stages[0]["order"] if stages else None,
            "reason": (
                f"{clinical_target['label']} is your highest-priority current skill that also has "
                "a matching patient case."
            ),
        }

    now = (as_of or datetime.now(UTC)).astimezone(UTC).isoformat()
    return {
        "generatedAt": now,
        "plannerKind": "verified_competency_scheduler",
        "generativeTutorUsed": False,
        "preferenceContext": ({
            "trainingStage": preferences.get("trainingStage", "not_set"),
            "primaryGoal": preferences.get("primaryGoal", "build_fundamentals"),
            "defaultSessionLength": rapid_length,
            "rapidPace": rapid_pace,
            "guidanceLevel": preferences.get("guidanceLevel", "balanced"),
        } if preferences is not None else None),
        "basis": {
            "independentCompetencyObservations": independent_count,
            "independentAttempts": independent_count,
            "independentAttemptUnit": "competency_observation",
            "dueCompetencies": due_count,
            "overdueCompetencies": overdue_count,
            "highConfidenceMisses": high_confidence_misses,
            "eligibleConcepts": len({cell["caseConcept"] for cell in ranked}),
            "baselineNeeded": baseline_needed,
            "planStage": plan_stage,
            "minimumDistinctEcgsForDurable": DURABLE_DISTINCT_SUCCESSFUL_ECGS,
        },
        "primary": ({**primary, "reason": _reason(primary)} if primary else None),
        "priorities": priorities,
        "stages": stages,
        "guidedRemediation": guided_remediation,
        "integration": integration,
        "clinicalApplication": clinical_application,
        "integrationReadiness": {
            "unlocked": integration_unlocked,
            "reason": (
                "Unlocked after repeated unassisted success on both concepts while neither is due for review."
                if integration_unlocked
                else "Cross-concept synthesis remains formative until deterministic per-domain grading is available."
                if synthesis_target is None
                else "Complete unassisted checks on two concepts before cross-concept integration opens."
            ),
        },
        "explanation": (
            "No independent ECG checks are available yet, so the first step establishes a focused starting point."
            + (
                " Your saved training stage and goal decide which unseen skill is checked first."
                if preferences is not None else ""
            )
            if baseline_needed
            else "The plan puts due skills first, followed by confident misses, lower independent performance, limited ECG variety, and skills not yet checked. Saved preferences only break ties between otherwise equal unseen skills."
            if preferences is not None
            else "The plan puts due skills first, followed by confident misses, lower independent performance, limited ECG variety, and skills not yet checked."
        ),
    }
