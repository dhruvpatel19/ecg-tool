"""Server-authoritative context for completed Rapid-round debriefs.

Only answer-free, bounded projections leave the durable Rapid ledger. Browser
summaries are never inputs to this builder and chat can never mutate mastery.
"""

from __future__ import annotations

from collections import Counter
import json
import math
from typing import Any, Final

from .ontology import concept_label


CONTEXT_VERSION: Final[str] = "rapid-round-debrief-v1"
RECENT_RECEIPT_LIMIT: Final[int] = 25


class RapidTutorContextError(RuntimeError):
    pass


class RapidTutorContextNotFound(RapidTutorContextError):
    pass


class RapidTutorContextNotReady(RapidTutorContextError):
    pass


class RapidTutorContextInvalid(RapidTutorContextError):
    pass


def _strings(value: Any, *, maximum: int = 100) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum:
        raise RapidTutorContextInvalid("Rapid result contains an invalid list.")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item) > 200:
            raise RapidTutorContextInvalid("Rapid result contains an invalid label.")
        result.append(item.strip())
    return result


def _rank(counter: Counter[str], *, limit: int = 8) -> list[dict[str, Any]]:
    return [
        {"concept": concept, "label": concept_label(concept), "count": count}
        for concept, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def _deterministic_debrief(
    *,
    completed: int,
    correct: list[dict[str, Any]],
    missed: list[dict[str, Any]],
) -> dict[str, Any]:
    strongest = correct[0] if correct else None
    priority = missed[0] if missed else None
    if priority:
        pattern = (
            f"Across {completed} completed ECGs, {priority['label']} was the most frequent "
            f"miss ({priority['count']} occurrence(s))."
        )
    elif strongest:
        pattern = (
            f"Across {completed} completed ECGs, {strongest['label']} was the most "
            f"consistent recognized concept ({strongest['count']} occurrence(s))."
        )
    else:
        pattern = (
            f"The {completed} completed ECGs do not support a recurring concept-specific "
            "pattern yet."
        )

    secondary = None
    if priority and strongest and priority["concept"] != strongest["concept"]:
        secondary = strongest
    elif len(missed) > 1:
        secondary = missed[1]
    bridge = None
    if priority and secondary:
        bridge = {
            "primaryConcept": priority["concept"],
            "primaryLabel": priority["label"],
            "secondaryConcept": secondary["concept"],
            "secondaryLabel": secondary["label"],
            "prompt": (
                f"Compare {priority['label']} with {secondary['label']}: name one shared "
                "feature and the discriminator that separates them before committing."
            ),
        }
    question = (
        f"What visible discriminator would make you commit to {priority['label']} on the next unannounced ECG?"
        if priority
        else "Which step in your fixed ECG sequence will you verify first on the next unannounced tracing?"
    )
    return {
        "recurringPattern": pattern,
        "crossConceptBridge": bridge,
        "nextStepQuestion": question,
        "suggestedNextStep": "Use one new eligible ECG and state the discriminator before naming the finding.",
    }


def build_rapid_round_tutor_context(
    store: Any,
    *,
    learner_id: str,
    round_id: str,
    answer_count: int,
    version: str,
) -> dict[str, Any]:
    """Reconstruct a completed round from protected server rows.

    The join to ``attempts`` proves every projected answer belongs to this
    round's owner and committed Rapid path. Raw responses, grades, answer keys,
    packet measurements, and free text never enter the tutor context.
    """

    if version != CONTEXT_VERSION:
        raise RapidTutorContextInvalid("Rapid debrief context version is invalid.")
    if not isinstance(answer_count, int) or isinstance(answer_count, bool) or not 1 <= answer_count <= 5000:
        raise RapidTutorContextInvalid("Rapid debrief answer count is invalid.")

    with store.connect() as conn:
        round_row = conn.execute(
            "SELECT learner_id, pace, length, assessment_scope, position, status, "
            "pending_case_id FROM rapid_rounds WHERE round_id = ?",
            (round_id,),
        ).fetchone()
        if round_row is None or str(round_row["learner_id"]) != learner_id:
            raise RapidTutorContextNotFound("Rapid round debrief not found.")
        length = int(round_row["length"])
        position = int(round_row["position"])
        if (
            str(round_row["status"]) != "complete"
            or round_row["pending_case_id"] is not None
            or position != length
        ):
            raise RapidTutorContextNotReady("Finish the Rapid round before opening its debrief.")
        if answer_count != length:
            raise RapidTutorContextInvalid("Rapid debrief answer count does not match the completed round.")
        rows = conn.execute(
            "SELECT answers.id, answers.case_id, answers.result_json, "
            "answers.receipts_json, answers.integrity_status, attempts.learner_id "
            "AS attempt_owner, attempts.case_id AS attempt_case, attempts.mode AS attempt_mode "
            "FROM rapid_round_answers AS answers JOIN attempts "
            "ON attempts.id = answers.attempt_id WHERE answers.round_id = ? "
            "ORDER BY answers.id",
            (round_id,),
        ).fetchall()

    if len(rows) != length:
        raise RapidTutorContextInvalid("Rapid answer ledger is incomplete.")

    correct_counts: Counter[str] = Counter()
    missed_counts: Counter[str] = Counter()
    overcall_counts: Counter[str] = Counter()
    misconception_counts: Counter[str] = Counter()
    scores: list[float] = []
    response_times: list[int] = []
    timed_out_count = 0
    safe_rows: list[dict[str, Any]] = []

    for row in rows:
        case_id = str(row["case_id"])
        if (
            str(row["integrity_status"]) != "atomic_v1"
            or str(row["attempt_owner"]) != learner_id
            or str(row["attempt_case"]) != case_id
            or str(row["attempt_mode"]) != "rapid_practice"
        ):
            raise RapidTutorContextInvalid("Rapid answer ownership or integrity is invalid.")
        try:
            result = json.loads(row["result_json"])
            receipts = json.loads(row["receipts_json"] or "[]")
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RapidTutorContextInvalid("Rapid answer ledger contains invalid JSON.") from exc
        if not isinstance(result, dict) or str(result.get("caseId") or "") != case_id:
            raise RapidTutorContextInvalid("Rapid result does not match its stored ECG.")
        score = result.get("score")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(float(score)) or not 0 <= float(score) <= 1:
            raise RapidTutorContextInvalid("Rapid result score is invalid.")
        timed_out = result.get("timedOut")
        if not isinstance(timed_out, bool):
            raise RapidTutorContextInvalid("Rapid result timeout state is invalid.")
        response_ms = result.get("responseMs")
        if response_ms is not None and (
            isinstance(response_ms, bool) or not isinstance(response_ms, int) or response_ms < 0
        ):
            raise RapidTutorContextInvalid("Rapid result response time is invalid.")
        correct = _strings(result.get("correctObjectives") or [])
        missed = _strings(result.get("missedObjectives") or [])
        overcalled = _strings(result.get("overcalledObjectives") or [])
        misconceptions = _strings(result.get("misconceptions") or [])
        if not isinstance(receipts, list) or not receipts or len(receipts) > 100:
            raise RapidTutorContextInvalid("Rapid evidence receipt ledger is invalid.")
        safe_receipts: list[dict[str, Any]] = []
        for receipt in receipts:
            if not isinstance(receipt, dict):
                raise RapidTutorContextInvalid("Rapid evidence receipt is invalid.")
            concept = str(receipt.get("concept") or "").strip()
            subskill = str(receipt.get("subskill") or "").strip()
            if not concept or len(concept) > 160 or not subskill or len(subskill) > 80:
                raise RapidTutorContextInvalid("Rapid evidence receipt target is invalid.")
            safe_receipts.append({
                "concept": concept,
                "subskill": subskill,
                "accepted": bool(receipt.get("accepted")),
                "correct": bool(receipt.get("correct")) if receipt.get("accepted") else None,
                "evidenceLevel": str(receipt.get("evidenceLevel") or "none")[:40],
            })
        correct_counts.update(correct)
        missed_counts.update(missed)
        overcall_counts.update(overcalled)
        misconception_counts.update(misconceptions)
        scores.append(float(score))
        timed_out_count += int(timed_out)
        if response_ms is not None:
            response_times.append(response_ms)
        safe_rows.append({
            # The model needs sequence and performance evidence, never a
            # public-dataset lookup key that it could echo to the learner.
            "caseNumber": len(safe_rows) + 1,
            "score": round(float(score), 4),
            "timedOut": timed_out,
            "responseMs": response_ms,
            "correct": correct,
            "missed": missed,
            "overcalled": overcalled,
            "misconceptions": misconceptions,
            "evidenceReceipts": safe_receipts,
        })

    common_correct = _rank(correct_counts)
    common_missed = _rank(missed_counts)
    common_overcalls = _rank(overcall_counts)
    deterministic = _deterministic_debrief(
        completed=length,
        correct=common_correct,
        missed=common_missed,
    )
    context_id = f"rapid-round:{round_id}:{length}"
    return {
        "reference": {
            "contextId": context_id,
            "roundId": round_id,
            "answerCount": length,
            "version": CONTEXT_VERSION,
        },
        "context": {
            "kind": "rapid_round_debrief",
            "version": CONTEXT_VERSION,
            "round": {
                "pace": str(round_row["pace"]),
                "assessmentScope": str(round_row["assessment_scope"]),
                "completedCaseCount": length,
            },
            "aggregate": {
                "averageScore": round(sum(scores) / len(scores), 4),
                "averageResponseMs": (
                    round(sum(response_times) / len(response_times)) if response_times else None
                ),
                "timedOutCount": timed_out_count,
                "commonCorrect": common_correct,
                "commonMissed": common_missed,
                "commonOvercalls": common_overcalls,
                "commonMisconceptions": [
                    {"tag": tag, "count": count}
                    for tag, count in sorted(
                        misconception_counts.items(), key=lambda item: (-item[1], item[0])
                    )[:8]
                ],
            },
            "recentReceipts": safe_rows[-RECENT_RECEIPT_LIMIT:],
            "testedConcepts": sorted(
                set(correct_counts) | set(missed_counts) | set(overcall_counts)
                | {receipt["concept"] for item in safe_rows for receipt in item["evidenceReceipts"]}
            ),
            "deterministicDebrief": deterministic,
            "governance": {
                "source": "owner_bound_completed_rapid_round",
                "browserSummariesAccepted": False,
                "chatCanWriteMastery": False,
                "objectiveUpdatesAllowed": False,
                "viewerActionsAllowed": False,
            },
        },
    }


def deterministic_rapid_tutor_response(context: dict[str, Any]) -> dict[str, Any]:
    """Return the always-available debrief when live AI cannot be displayed."""

    deterministic = (
        context.get("deterministicDebrief")
        if isinstance(context.get("deterministicDebrief"), dict)
        else {}
    )
    bridge = (
        deterministic.get("crossConceptBridge")
        if isinstance(deterministic.get("crossConceptBridge"), dict)
        else None
    )
    pattern = str(
        deterministic.get("recurringPattern")
        or "The completed server record does not support a recurring pattern yet."
    )
    return {
        "tutorMessage": f"{pattern} {bridge.get('prompt')}" if bridge else pattern,
        "feedback": "This debrief was reconstructed from the owner-bound completed Rapid ledger; browser summaries were ignored.",
        "viewerActions": [],
        "objectiveUpdates": [],
        "misconceptions": [],
        "uncertaintyWarnings": [
            "Chat can explain this completed round but cannot score it or change mastery."
        ],
        "suggestedNextStep": str(
            deterministic.get("suggestedNextStep")
            or "Use a new eligible ECG for the next independent check."
        ),
        "socraticQuestion": str(
            deterministic.get("nextStepQuestion")
            or "Which discriminator will you verify first on the next ECG?"
        ),
        "citedEvidence": [
            value
            for value in (
                pattern,
                bridge.get("prompt") if bridge else None,
                "Owner-bound completed Rapid answer and receipt ledger",
            )
            if value
        ][:3],
        "onLessonTopic": True,
    }


__all__ = [
    "CONTEXT_VERSION",
    "RapidTutorContextInvalid",
    "RapidTutorContextNotFound",
    "RapidTutorContextNotReady",
    "build_rapid_round_tutor_context",
    "deterministic_rapid_tutor_response",
]
