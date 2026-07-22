"""Server-authoritative context for completed Focused Practice set debriefs.

The browser holds only a reference to a completed campaign. Every aggregate
shown to Luna is rebuilt from owner-bound saved results. Answer keys, canonical
ECG ids, and browser-provided summaries never enter the tutor context. For the
formal interpretation workflow, only the bounded saved interpretation and its
server-derived review are included so Luna can discuss the learner's own work.
"""

from __future__ import annotations

from collections import Counter
import json
from typing import Any, Final
from urllib.parse import parse_qs

from .competency_taxonomy import COMPETENCY_SKILLS
from .objectives import objective_definition
from .ontology import concept_label
from .subskill_tasks import SYSTEMATIC_INTERPRETATION_KEYS


CONTEXT_VERSION: Final[str] = "training-set-debrief-v1"
ECG_CONTEXT_VERSION: Final[str] = "training-ecg-debrief-v1"
RECENT_OUTCOME_LIMIT: Final[int] = 25
MAX_CAMPAIGN_LENGTH: Final[int] = 5000


class TrainingTutorContextError(RuntimeError):
    pass


class TrainingTutorContextNotFound(TrainingTutorContextError):
    pass


class TrainingTutorContextNotReady(TrainingTutorContextError):
    pass


class TrainingTutorContextInvalid(TrainingTutorContextError):
    pass


def _bounded_misconceptions(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > 20:
        raise TrainingTutorContextInvalid(
            "Focused Practice outcome contains an invalid misconception list."
        )
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item) > 200:
            raise TrainingTutorContextInvalid(
                "Focused Practice outcome contains an invalid misconception."
            )
        result.append(item.strip())
    return result


def _rank_misconceptions(counter: Counter[str]) -> list[dict[str, Any]]:
    return [
        {"tag": tag, "count": count}
        for tag, count in sorted(
            counter.items(), key=lambda item: (-item[1], item[0])
        )[:8]
    ]


def _bounded_systematic_interpretation(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise TrainingTutorContextInvalid(
            "Focused Practice systematic interpretation is invalid."
        )
    result: dict[str, str] = {}
    for key in SYSTEMATIC_INTERPRETATION_KEYS:
        item = value.get(key)
        if not isinstance(item, str):
            raise TrainingTutorContextInvalid(
                "Focused Practice systematic interpretation is invalid."
            )
        bounded = item.strip()
        limit = 2_000 if key == "synthesis" else 750
        if not bounded or len(bounded) > limit:
            raise TrainingTutorContextInvalid(
                "Focused Practice systematic interpretation is invalid."
            )
        result[key] = bounded
    if len(result["synthesis"]) < 12:
        raise TrainingTutorContextInvalid(
            "Focused Practice systematic synthesis is invalid."
        )
    return result


def _bounded_reviewed_framework(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) != len(SYSTEMATIC_INTERPRETATION_KEYS):
        raise TrainingTutorContextInvalid(
            "Focused Practice reviewed framework is invalid."
        )
    result: list[dict[str, Any]] = []
    for expected_key, row in zip(SYSTEMATIC_INTERPRETATION_KEYS, value, strict=True):
        if not isinstance(row, dict) or row.get("key") != expected_key:
            raise TrainingTutorContextInvalid(
                "Focused Practice reviewed framework is invalid."
            )
        label = row.get("label")
        review = row.get("review")
        grounded = row.get("grounded")
        if (
            not isinstance(label, str)
            or not label.strip()
            or len(label) > 200
            or not isinstance(review, str)
            or not review.strip()
            or len(review) > 2_000
            or not isinstance(grounded, bool)
        ):
            raise TrainingTutorContextInvalid(
                "Focused Practice reviewed framework is invalid."
            )
        result.append(
            {
                "key": expected_key,
                "label": label.strip(),
                "review": review.strip(),
                "grounded": grounded,
            }
        )
    return result


def _skill_label(subskill: str) -> str:
    definition = COMPETENCY_SKILLS.get(subskill)
    return definition.label if definition else subskill.replace("_", " ").title()


def _deterministic_debrief(
    *,
    objective_concept: str,
    case_concept: str,
    subskill: str,
    completed: int,
    skill_correct: int,
    classification_correct: int,
    full_task_correct: int,
    high_confidence_wrong: int,
    independent_receipts: int,
) -> dict[str, Any]:
    objective_definition_value = objective_definition(objective_concept)
    objective_name = (
        objective_definition_value.label
        if objective_definition_value is not None
        else concept_label(objective_concept)
    )
    case_concept_name = concept_label(case_concept)
    skill_name = _skill_label(subskill)
    skill_rate = skill_correct / completed
    classification_rate = classification_correct / completed

    if skill_rate < classification_rate:
        behavior = (
            f"In this set, the selected {skill_name.lower()} task was correct on "
            f"{skill_correct} of {completed} ECGs, compared with {classification_correct} of "
            f"{completed} correct initial topic decisions."
        )
        impact = (
            "The main opportunity is carrying recognition into the selected skill, rather "
            "than adding more labels without showing the required evidence."
        )
    elif classification_rate < skill_rate:
        behavior = (
            f"In this set, you made {classification_correct} of {completed} correct "
            f"initial topic decisions and {skill_correct} of {completed} correct "
            f"{skill_name.lower()} tasks."
        )
        impact = (
            "The main opportunity is deciding whether the concept is actually present before "
            "applying a skill that may be performed correctly in isolation."
        )
    else:
        behavior = (
            f"In this set, you completed {skill_correct} of {completed} correct "
            f"{skill_name.lower()} tasks and {classification_correct} of {completed} correct "
            "initial topic decisions."
        )
        impact = (
            "The classification and selected-skill outcomes are moving together, so the next "
            "useful check is the same reasoning sequence on a new unrevealed ECG."
        )

    case_family_clause = (
        ""
        if objective_concept == case_concept
        else f", using reviewed {case_concept_name} ECGs for the selected task"
    )
    situation = (
        f"In this completed {completed}-ECG Focused Practice set on {objective_name}"
        f"{case_family_clause}, the selected competency was {skill_name}."
    )
    if high_confidence_wrong:
        impact += (
            f" {high_confidence_wrong} incorrect response(s) were submitted with high "
            "confidence, so an explicit discriminator check is especially valuable."
        )
    next_step = (
        f"On one new reviewed ECG, decide whether the relevant {objective_name.lower()} "
        "evidence is present, then state the "
        f"observable evidence required for {skill_name.lower()} before checking your answer."
    )
    question = (
        f"What single visible discriminator will you verify first when checking for "
        f"{objective_name.lower()} on the next ECG?"
    )
    return {
        "sbiNext": {
            "situation": situation,
            "behavior": behavior,
            "impact": impact,
            "next": next_step,
        },
        "nextStepQuestion": question,
        "suggestedNextStep": next_step,
        "fullTaskCorrectCount": full_task_correct,
        "independentReceiptCount": independent_receipts,
    }


def build_training_set_tutor_context(
    campaign_store: Any,
    *,
    learner_id: str,
    campaign_id: str,
    answer_count: int,
    version: str,
) -> dict[str, Any]:
    """Reconstruct one completed Focused Practice campaign from durable rows."""

    if version != CONTEXT_VERSION:
        raise TrainingTutorContextInvalid(
            "Focused Practice debrief context version is invalid."
        )
    if (
        not isinstance(answer_count, int)
        or isinstance(answer_count, bool)
        or not 1 <= answer_count <= MAX_CAMPAIGN_LENGTH
    ):
        raise TrainingTutorContextInvalid(
            "Focused Practice debrief answer count is invalid."
        )

    with campaign_store.connect() as conn:
        campaign = conn.execute(
            "SELECT learner_id, concept_id, subskill, length, position, status, "
            "pending_case_id, context_key FROM training_campaigns WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()
        if campaign is None or str(campaign["learner_id"]) != learner_id:
            raise TrainingTutorContextNotFound(
                "Focused Practice set debrief not found."
            )
        length = int(campaign["length"])
        if (
            str(campaign["status"]) != "complete"
            or int(campaign["position"]) != length
            or campaign["pending_case_id"] is not None
        ):
            raise TrainingTutorContextNotReady(
                "Finish the Focused Practice set before opening its debrief."
            )
        if answer_count != length:
            raise TrainingTutorContextInvalid(
                "Focused Practice debrief answer count does not match the completed set."
            )
        case_concept = str(campaign["concept_id"])
        subskill = str(campaign["subskill"])
        context_values = parse_qs(
            str(campaign["context_key"] or ""), keep_blank_values=False
        )
        receipt_concept = str(
            (context_values.get("receiptConcept") or [case_concept])[0]
        ).strip()
        definition = objective_definition(receipt_concept)
        if (
            not receipt_concept
            or len(receipt_concept) > 160
            or definition is None
            or subskill not in definition.allowed_subskills
            or case_concept not in definition.case_concepts
        ):
            raise TrainingTutorContextInvalid(
                "Focused Practice receipt objective contract is invalid."
            )
        rows = conn.execute(
            "SELECT answers.ordinal, answers.case_id, answers.summary_json, "
            "answers.receipt_json, answers.response_json, answers.grade_json, "
            "answers.integrity_status, "
            "attempts.learner_id AS attempt_owner, attempts.case_id AS attempt_case, "
            "attempts.mode AS attempt_mode, slots.phase AS slot_phase, "
            "slots.status AS slot_status, events.id AS event_id, "
            "events.learner_id AS event_owner, events.module_id AS event_module, "
            "events.case_id AS event_case, events.concept AS event_concept, "
            "events.subskills_json AS event_subskills_json, "
            "events.effective_evidence_level AS event_evidence_level "
            "FROM training_campaign_answers AS answers "
            "JOIN attempts ON attempts.id = answers.attempt_id "
            "JOIN training_campaign_slots AS slots ON slots.campaign_id = answers.campaign_id "
            "AND slots.ordinal = answers.ordinal AND slots.case_id = answers.case_id "
            "JOIN guided_learning_events AS events ON events.event_key = "
            "'train:' || answers.campaign_id || ':' || answers.ordinal || ':' || "
            "answers.case_id || ':' || ? "
            "WHERE answers.campaign_id = ? ORDER BY answers.ordinal",
            (str(campaign["subskill"]), campaign_id),
        ).fetchall()
        mastery = conn.execute(
            "SELECT formative_score, independent_mastery, attempts, "
            "independent_attempts, correct, high_confidence_wrong, next_due_at, "
            "stability_days, lapses, spaced_retrievals, distinct_eligible_ecgs, "
            "distinct_successful_ecgs, last_independent_at, last_independent_correct "
            "FROM subskill_mastery WHERE learner_id = ? AND concept = ? AND subskill = ?",
            (
                learner_id,
                receipt_concept,
                subskill,
            ),
        ).fetchone()

    if len(rows) != length:
        raise TrainingTutorContextInvalid(
            "Focused Practice answer ledger is incomplete."
        )

    skill_correct = 0
    classification_correct = 0
    full_task_correct = 0
    independent_receipts = 0
    high_confidence_wrong = 0
    hints_used_count = 0
    misconception_counts: Counter[str] = Counter()
    confidence_counts: Counter[int] = Counter()
    safe_outcomes: list[dict[str, Any]] = []

    for expected_ordinal, row in enumerate(rows):
        ordinal = int(row["ordinal"])
        case_id = str(row["case_id"])
        phase = str(row["slot_phase"])
        if (
            ordinal != expected_ordinal
            or str(row["integrity_status"]) != "atomic_v2"
            or str(row["attempt_owner"]) != learner_id
            or str(row["attempt_case"]) != case_id
            or str(row["attempt_mode"]) != "concept_practice"
            or str(row["slot_status"]) != "answered"
        ):
            raise TrainingTutorContextInvalid(
                "Focused Practice answer ownership or integrity is invalid."
            )
        try:
            summary = json.loads(row["summary_json"])
            receipt = json.loads(row["receipt_json"])
            event_subskills = json.loads(row["event_subskills_json"])
            response = (
                json.loads(row["response_json"])
                if subskill == "synthesize"
                else None
            )
            grade = (
                json.loads(row["grade_json"])
                if subskill == "synthesize"
                else None
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise TrainingTutorContextInvalid(
                "Focused Practice answer ledger contains invalid JSON."
            ) from exc
        if not isinstance(summary, dict) or not isinstance(receipt, dict):
            raise TrainingTutorContextInvalid(
                "Focused Practice answer ledger contains an invalid outcome."
            )
        if (
            summary.get("position") != ordinal
            or str(summary.get("caseId") or "") != case_id
            or str(summary.get("phase") or "") != phase
        ):
            raise TrainingTutorContextInvalid(
                "Focused Practice outcome does not match its stored slot."
            )
        for key in ("correct", "classificationCorrect"):
            if not isinstance(summary.get(key), bool):
                raise TrainingTutorContextInvalid(
                    "Focused Practice outcome correctness is invalid."
                )
        confidence = summary.get("confidence")
        hints_used = summary.get("hintsUsed")
        if (
            (
                confidence is not None
                and (
                    not isinstance(confidence, int)
                    or isinstance(confidence, bool)
                    or not 1 <= confidence <= 5
                )
            )
            or not isinstance(hints_used, int)
            or isinstance(hints_used, bool)
            or not 0 <= hints_used <= 10
        ):
            raise TrainingTutorContextInvalid(
                "Focused Practice outcome confidence or hint count is invalid "
                f"at position {ordinal}: confidence={confidence!r}, hints={hints_used!r}."
            )
        receipt_rows = receipt.get("receipts")
        receipt_event_id = receipt.get("eventId")
        evidence_level = str(receipt.get("effectiveEvidenceLevel") or "")
        event_concept = str(row["event_concept"] or "")
        stored_receipt_concept = (
            str(receipt_rows[0].get("concept") or "")
            if isinstance(receipt_rows, list)
            and len(receipt_rows) == 1
            and isinstance(receipt_rows[0], dict)
            else ""
        )
        if (
            not isinstance(receipt_event_id, int)
            or isinstance(receipt_event_id, bool)
            or receipt_event_id != int(row["event_id"])
            or not isinstance(receipt_rows, list)
            or len(receipt_rows) != 1
            or not isinstance(receipt_rows[0], dict)
            or not stored_receipt_concept
            or stored_receipt_concept != event_concept
            or event_concept != receipt_concept
            or str(receipt_rows[0].get("subskill") or "") != subskill
            or str(receipt_rows[0].get("evidenceLevel") or "") != evidence_level
            or evidence_level not in {"guided", "independent_transfer"}
            or str(summary.get("evidenceLevel") or "") != evidence_level
            or str(row["event_owner"]) != learner_id
            or str(row["event_module"]) != "train"
            or str(row["event_case"]) != case_id
            or event_subskills != [subskill]
            or str(row["event_evidence_level"]) != evidence_level
        ):
            raise TrainingTutorContextInvalid(
                "Focused Practice evidence receipt is invalid."
            )

        misconceptions = _bounded_misconceptions(
            summary.get("misconceptions") or []
        )
        selected_skill_correct = bool(summary["correct"])
        selected_classification_correct = bool(summary["classificationCorrect"])
        selected_full_task_correct = (
            selected_skill_correct and selected_classification_correct
        )
        skill_correct += int(selected_skill_correct)
        classification_correct += int(selected_classification_correct)
        full_task_correct += int(selected_full_task_correct)
        independent_receipts += int(evidence_level == "independent_transfer")
        high_confidence_wrong += int(
            confidence is not None
            and confidence >= 4
            and not selected_full_task_correct
        )
        hints_used_count += int(hints_used > 0)
        misconception_counts.update(misconceptions)
        if confidence is not None:
            confidence_counts.update((confidence,))
        safe_outcome = {
            "caseNumber": ordinal + 1,
            "skillCorrect": selected_skill_correct,
            "classificationCorrect": selected_classification_correct,
            "fullTaskCorrect": selected_full_task_correct,
            "hintUsed": hints_used > 0,
            "misconceptions": misconceptions,
        }
        if subskill == "calibrate_confidence":
            safe_outcome["confidence"] = confidence
        if subskill == "synthesize":
            if not isinstance(response, dict) or not isinstance(grade, dict):
                raise TrainingTutorContextInvalid(
                    "Focused Practice systematic review ledger is invalid."
                )
            task_result = grade.get("trainingSubskillTaskResult")
            if (
                not isinstance(task_result, dict)
                or task_result.get("systematicInterpretationComplete") is not True
            ):
                raise TrainingTutorContextInvalid(
                    "Focused Practice systematic review ledger is invalid."
                )
            systematic = _bounded_systematic_interpretation(
                response.get("structuredInterpretation")
            )
            if _bounded_systematic_interpretation(
                task_result.get("systematicInterpretation")
            ) != systematic:
                raise TrainingTutorContextInvalid(
                    "Focused Practice systematic review does not match its submission."
                )
            safe_outcome["systematicInterpretationComplete"] = True
            safe_outcome["systematicInterpretation"] = systematic
            safe_outcome["reviewedFramework"] = _bounded_reviewed_framework(
                task_result.get("reviewedFramework")
            )
        safe_outcomes.append(safe_outcome)

    deterministic = _deterministic_debrief(
        objective_concept=receipt_concept,
        case_concept=case_concept,
        subskill=subskill,
        completed=length,
        skill_correct=skill_correct,
        classification_correct=classification_correct,
        full_task_correct=full_task_correct,
        high_confidence_wrong=high_confidence_wrong,
        independent_receipts=independent_receipts,
    )
    progression = None if mastery is None else {
        "formativeScore": round(float(mastery["formative_score"]), 4),
        "independentMastery": round(float(mastery["independent_mastery"]), 4),
        "attemptCount": int(mastery["attempts"]),
        "independentAttemptCount": int(mastery["independent_attempts"]),
        "correctCount": int(mastery["correct"]),
        "highConfidenceWrongCount": int(mastery["high_confidence_wrong"]),
        "nextDueAt": str(mastery["next_due_at"]) if mastery["next_due_at"] else None,
        "stabilityDays": round(float(mastery["stability_days"]), 4),
        "lapseCount": int(mastery["lapses"]),
        "spacedRetrievalCount": int(mastery["spaced_retrievals"]),
        "distinctEligibleEcgCount": int(mastery["distinct_eligible_ecgs"]),
        "distinctSuccessfulEcgCount": int(mastery["distinct_successful_ecgs"]),
        "lastIndependentAt": (
            str(mastery["last_independent_at"])
            if mastery["last_independent_at"] else None
        ),
        "lastIndependentCorrect": (
            bool(mastery["last_independent_correct"])
            if mastery["last_independent_correct"] is not None else None
        ),
    }
    context_id = f"training-set:{campaign_id}:{length}"
    return {
        "reference": {
            "contextId": context_id,
            "campaignId": campaign_id,
            "answerCount": length,
            "version": CONTEXT_VERSION,
        },
        "context": {
            "kind": "training_set_debrief",
            "version": CONTEXT_VERSION,
            "focus": {
                "concept": receipt_concept,
                "conceptLabel": definition.label,
                "receiptConcept": receipt_concept,
                "receiptConceptLabel": definition.label,
                "caseConcept": case_concept,
                "caseConceptLabel": concept_label(case_concept),
                "subskill": subskill,
                "subskillLabel": _skill_label(subskill),
                "completedCaseCount": length,
            },
            "aggregate": {
                "skillCorrectCount": skill_correct,
                "classificationCorrectCount": classification_correct,
                "fullTaskCorrectCount": full_task_correct,
                "independentReceiptCount": independent_receipts,
                "hintedCaseCount": hints_used_count,
                "commonMisconceptions": _rank_misconceptions(
                    misconception_counts
                ),
                **(
                    {
                        "highConfidenceWrongCount": high_confidence_wrong,
                        "confidenceDistribution": [
                            {
                                "confidence": value,
                                "count": confidence_counts.get(value, 0),
                            }
                            for value in range(1, 6)
                        ],
                    }
                    if subskill == "calibrate_confidence"
                    else {}
                ),
            },
            "progression": progression,
            "recentOutcomes": safe_outcomes[-RECENT_OUTCOME_LIMIT:],
            "deterministicDebrief": deterministic,
            "governance": {
                "source": "owner_bound_completed_training_campaign",
                "browserSummariesAccepted": False,
                "chatCanWriteMastery": False,
                "objectiveUpdatesAllowed": False,
                "viewerActionsAllowed": False,
            },
        },
    }


def build_training_ecg_tutor_context(
    campaign_store: Any,
    *,
    learner_id: str,
    campaign_id: str,
    case_id: str,
) -> dict[str, Any]:
    """Rebuild one current postcommit Focused ECG debrief from durable rows."""

    with campaign_store.connect() as conn:
        row = conn.execute(
            "SELECT campaigns.learner_id, campaigns.concept_id, "
            "campaigns.subskill, campaigns.context_key, "
            "campaigns.feedback_case_id, answers.ordinal, "
            "answers.response_json, answers.grade_json, answers.summary_json, "
            "answers.integrity_status, attempts.learner_id AS attempt_owner, "
            "attempts.case_id AS attempt_case, attempts.mode AS attempt_mode "
            "FROM training_campaigns AS campaigns "
            "JOIN training_campaign_answers AS answers "
            "ON answers.campaign_id = campaigns.campaign_id "
            "JOIN attempts ON attempts.id = answers.attempt_id "
            "WHERE campaigns.campaign_id = ? AND answers.case_id = ? "
            "ORDER BY answers.id DESC LIMIT 1",
            (campaign_id, case_id),
        ).fetchone()
    if row is None or str(row["learner_id"]) != learner_id:
        raise TrainingTutorContextNotFound("Focused Practice ECG debrief not found.")
    if (
        str(row["feedback_case_id"] or "") != case_id
        or str(row["integrity_status"]) != "atomic_v2"
        or str(row["attempt_owner"]) != learner_id
        or str(row["attempt_case"]) != case_id
        or str(row["attempt_mode"]) != "concept_practice"
    ):
        raise TrainingTutorContextNotReady(
            "Commit this Focused Practice ECG before opening its debrief."
        )
    try:
        response = json.loads(row["response_json"])
        grade = json.loads(row["grade_json"])
        summary = json.loads(row["summary_json"])
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TrainingTutorContextInvalid(
            "Focused Practice ECG debrief contains invalid JSON."
        ) from exc
    if not all(isinstance(value, dict) for value in (response, grade, summary)):
        raise TrainingTutorContextInvalid(
            "Focused Practice ECG debrief is invalid."
        )
    concept = str(row["concept_id"])
    subskill = str(row["subskill"])
    context_values = parse_qs(str(row["context_key"] or ""), keep_blank_values=False)
    receipt_concept = str(
        (context_values.get("receiptConcept") or [concept])[0]
    ).strip()
    definition = objective_definition(receipt_concept)
    if (
        definition is None
        or subskill not in definition.allowed_subskills
        or concept not in definition.case_concepts
        or not isinstance(summary.get("correct"), bool)
        or not isinstance(summary.get("classificationCorrect"), bool)
    ):
        raise TrainingTutorContextInvalid(
            "Focused Practice ECG debrief contract is invalid."
        )
    context: dict[str, Any] = {
        "kind": "training_ecg_debrief",
        "version": ECG_CONTEXT_VERSION,
        "phase": "post_feedback",
        "focus": {
            "concept": receipt_concept,
            "conceptLabel": definition.label,
            "caseConcept": concept,
            "caseConceptLabel": concept_label(concept),
            "subskill": subskill,
            "subskillLabel": _skill_label(subskill),
            "caseNumber": int(row["ordinal"]) + 1,
        },
        "outcome": {
            "skillCorrect": bool(summary["correct"]),
            "classificationCorrect": bool(summary["classificationCorrect"]),
        },
        "storedFeedback": {
            "feedback": (
                "The saved Focused Practice response met the selected skill task."
                if bool(summary["correct"])
                else "The saved Focused Practice response needs review in the selected skill."
            )
        },
        "governance": {
            "source": "owner_bound_committed_training_answer",
            "browserSubmissionAccepted": False,
            "chatCanWriteMastery": False,
        },
    }
    if subskill == "synthesize":
        task_result = grade.get("trainingSubskillTaskResult")
        if (
            not isinstance(task_result, dict)
            or task_result.get("systematicInterpretationComplete") is not True
        ):
            raise TrainingTutorContextInvalid(
                "Focused Practice systematic ECG review is invalid."
            )
        systematic = _bounded_systematic_interpretation(
            response.get("structuredInterpretation")
        )
        if _bounded_systematic_interpretation(
            task_result.get("systematicInterpretation")
        ) != systematic:
            raise TrainingTutorContextInvalid(
                "Focused Practice systematic ECG review does not match its submission."
            )
        context.update(
            {
                "systematicInterpretationComplete": True,
                "systematicInterpretation": systematic,
                "reviewedFramework": _bounded_reviewed_framework(
                    task_result.get("reviewedFramework")
                ),
            }
        )
    return context


def deterministic_training_tutor_response(context: dict[str, Any]) -> dict[str, Any]:
    """Return a safe set reflection when live AI is unavailable or malformed."""

    deterministic = (
        context.get("deterministicDebrief")
        if isinstance(context.get("deterministicDebrief"), dict)
        else {}
    )
    sbi_next = (
        deterministic.get("sbiNext")
        if isinstance(deterministic.get("sbiNext"), dict)
        else {}
    )
    message = " ".join(
        f"{label}: {str(sbi_next.get(key) or '').strip()}"
        for label, key in (
            ("Situation", "situation"),
            ("Behavior", "behavior"),
            ("Impact", "impact"),
            ("Next", "next"),
        )
        if str(sbi_next.get(key) or "").strip()
    )
    return {
        "tutorMessage": message or (
            "The completed Focused Practice record is available, but it does not "
            "support a more specific set-level learning claim."
        ),
        "feedback": (
            "This reflection is grounded in your completed Focused Practice results."
        ),
        "viewerActions": [],
        "objectiveUpdates": [],
        "misconceptions": [],
        "uncertaintyWarnings": [
            "Chat can explain this completed set but cannot score it or change mastery."
        ],
        "suggestedNextStep": str(
            deterministic.get("suggestedNextStep")
            or "Use a new eligible ECG for the next check."
        ),
        "socraticQuestion": str(
            deterministic.get("nextStepQuestion")
            or "Which discriminator will you verify first on the next ECG?"
        ),
        "citedEvidence": ["Completed Focused Practice results"],
        "onLessonTopic": True,
    }


__all__ = [
    "CONTEXT_VERSION",
    "ECG_CONTEXT_VERSION",
    "TrainingTutorContextInvalid",
    "TrainingTutorContextNotFound",
    "TrainingTutorContextNotReady",
    "build_training_ecg_tutor_context",
    "build_training_set_tutor_context",
    "deterministic_training_tutor_response",
]
