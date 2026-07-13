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

from .objectives import OBJECTIVES, ObjectiveDefinition
from .ontology import concept_label
from .retention import DURABLE_DISTINCT_SUCCESSFUL_ECGS, competency_state
from .subskill_tasks import training_independent_receipt_available


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
    explicitly objective-level.  A structured Rapid sweep is such a task for
    authored synthesis objectives; Training tasks currently close exact corpus
    concepts only.  Clinical application remains formative pending named
    clinician sign-off and therefore cannot enter this mastery queue.
    """
    if subskill == "synthesize":
        return "rapid" if case_concept in definition.case_concepts else None
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
        _ONBOARDING_RANK.get(cell["caseConcept"], len(_ONBOARDING_RANK) + 1),
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
        return (
            f"{label} · {skill} is {round(cell['independentMastery'] * 100)}% on independent evidence across "
            f"{cell['distinctSuccessfulEcgs']} successful distinct ECG(s)."
        )
    if cell["attempts"]:
        return f"{label} · {skill} has formative evidence but still needs an independent transfer check."
    return f"{label} · {skill} has not yet been observed; begin with an eligible real ECG."


def _stage(
    cell: dict[str, Any], *, order: int, stage_kind: str
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
            "purpose": "Complete the exact server-graded task, then clear it on an unannounced transfer ECG without a hint.",
            "href": (
                f"/train?concept={quote(concept)}&receiptConcept={quote(objective)}"
                f"&subskill={quote(subskill)}&returnTo=%2Freview"
            ),
            "suggestedLength": 25,
            "receiptConcept": objective,
            "receiptSubskill": subskill,
            "evidenceKind": "independent_transfer",
        }
    return {
        "order": order,
        "stageKind": stage_kind,
        "status": "current",
        "mode": "rapid",
        "title": (
            f"Build {label} · complete-read synthesis"
            if subskill == "synthesize"
            else f"Check {label} · independent recognition"
        ),
        "purpose": (
            "Complete every sweep field, commit an evidence-limited synthesis, and avoid unsupported calls on a blinded real ECG."
            if subskill == "synthesize"
            else "Make an explicit finding selection on a blinded, source-contracted real ECG; the server records both successes and focused misses."
        ),
        "href": (
            f"/rapid?focus={quote(concept)}&receiptConcept={quote(objective)}"
            f"&subskill={quote(subskill)}&returnTo=%2Freview"
        ),
        "suggestedLength": 10,
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
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Build a transparent, actionable plan without inventing mastery."""
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
    independent_count = sum(cell["independentAttempts"] for cell in ranked)
    due_count = sum(1 for cell in ranked if cell["isDue"])
    overdue_count = sum(1 for cell in ranked if cell["dueState"] == "overdue")
    high_confidence_misses = sum(cell["highConfidenceWrong"] for cell in ranked)
    baseline_needed = independent_count == 0
    primary = ranked[0] if ranked else None

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
        stages.append(_stage(primary, order=1, stage_kind=plan_stage))

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
                f"&receiptConcept={quote(synthesis_target['objectiveId'])}"
                "&subskill=synthesize&returnTo=%2Freview"
            ),
        }

    now = (as_of or datetime.now(UTC)).astimezone(UTC).isoformat()
    return {
        "generatedAt": now,
        "plannerKind": "verified_competency_scheduler",
        "generativeTutorUsed": False,
        "basis": {
            "independentAttempts": independent_count,
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
        "integration": integration,
        "integrationReadiness": {
            "unlocked": integration_unlocked,
            "reason": (
                "Unlocked after both concepts have repeated independent success and neither is due."
                if integration_unlocked
                else "Complete baseline/consolidation evidence on two concepts before cross-concept integration unlocks."
            ),
        },
        "explanation": (
            "No independently assessable competency evidence exists yet, so the first step is the highest-priority exact receipt task."
            if baseline_needed
            else "The queue is due-first, then high-confidence errors, low independent mastery, diversity gaps, and unseen competencies with an implemented independent receipt path."
        ),
    }
