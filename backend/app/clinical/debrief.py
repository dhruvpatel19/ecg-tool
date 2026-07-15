"""Deterministic, receipt-grounded Clinical shift debriefs.

The debrief is deliberately built from durable server grades plus the learner's
exact independent competency cells.  It never consumes browser summaries and it
never upgrades formative Clinical work into independent mastery.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from ..adaptive import independent_subskill_index, priority_exact_row
from ..ontology import concept_label
from .provenance import assert_learner_item_provenance


def _grade_objectives(answer: dict[str, Any]) -> tuple[list[str], list[str]]:
    grade = answer.get("grade") if isinstance(answer.get("grade"), dict) else {}
    correct = [str(value) for value in grade.get("correctObjectives") or [] if value]
    missed = [str(value) for value in grade.get("missedObjectives") or [] if value]
    return list(dict.fromkeys(correct)), list(dict.fromkeys(missed))


def _independent_need(
    exact_by_concept: dict[str, list[dict[str, Any]]], concept: str
) -> dict[str, Any]:
    row = priority_exact_row(
        exact_by_concept.get(concept, []),
        as_of=datetime.now(UTC),
        preferred_subskills={"recognize", "synthesize", "measure", "localize"},
    )
    if not row:
        return {
            "subskill": None,
            "independentAttempts": 0,
            "independentMastery": 0.0,
            "highConfidenceWrong": 0,
            "isDue": False,
            "dueState": "unseen",
        }
    return {
        "subskill": row.get("subskill"),
        "independentAttempts": int(row.get("independentAttempts", 0)),
        "independentMastery": float(row.get("independentMastery", 0.0)),
        "highConfidenceWrong": int(row.get("highConfidenceWrong", 0)),
        "isDue": bool(row.get("isDue", False)),
        "dueState": str(row.get("dueState", "scheduled")),
    }


def build_shift_debrief(
    session: dict[str, Any],
    answers: list[dict[str, Any]],
    profile: dict[str, Any],
    item_store,
    packet_provider=None,
) -> dict[str, Any]:
    """Build a learner-facing bridge and valid follow-up destinations.

    Concepts enter this object only when they occur in a completed server grade.
    The next Clinical proposal additionally requires a different, currently
    serving real-ECG item in the same lane that explicitly assesses the concept's
    ``apply_in_context`` cell.
    """

    correct_counts: Counter[str] = Counter()
    missed_counts: Counter[str] = Counter()
    case_counts: Counter[str] = Counter()
    co_occurrence: dict[str, Counter[str]] = defaultdict(Counter)
    concept_case_ids: dict[str, set[str]] = defaultdict(set)
    served_items = {str(answer.get("itemId") or "") for answer in answers}
    served_ecgs = {str(answer.get("ecgId") or "") for answer in answers}

    for answer in answers:
        correct, missed = _grade_objectives(answer)
        evidenced = list(dict.fromkeys([*correct, *missed]))
        for concept in correct:
            correct_counts[concept] += 1
        for concept in missed:
            missed_counts[concept] += 1
        for concept in evidenced:
            case_counts[concept] += 1
            concept_case_ids[concept].add(str(answer.get("ecgId") or ""))
            for other in evidenced:
                if other != concept:
                    co_occurrence[concept][other] += 1

    exact_by_concept = independent_subskill_index(profile)
    concepts: list[dict[str, Any]] = []
    for concept in sorted(case_counts):
        independent = _independent_need(exact_by_concept, concept)
        # Session misses lead.  Due/high-confidence/weak independent evidence
        # breaks ties; a successful formative Clinical answer cannot manufacture
        # an independent mastery increase.
        priority_score = (
            missed_counts[concept] * 4.0
            + (2.0 if independent["isDue"] else 0.0)
            + (1.0 - independent["independentMastery"]) * 1.5
            + min(1.0, independent["highConfidenceWrong"] * 0.2)
            + (0.35 if independent["independentAttempts"] == 0 else 0.0)
        )
        concepts.append(
            {
                "concept": concept,
                "label": concept_label(concept),
                "caseCount": case_counts[concept],
                "distinctEcgs": len(concept_case_ids[concept] - {""}),
                "correctCount": correct_counts[concept],
                "missedCount": missed_counts[concept],
                "priorityScore": round(priority_score, 3),
                "independentEvidence": independent,
            }
        )
    concepts.sort(
        key=lambda row: (
            -float(row["priorityScore"]),
            -int(row["missedCount"]),
            str(row["concept"]),
        )
    )

    candidates_by_concept: dict[str, int] = Counter()
    lane = str(session.get("lane") or "clinic")
    for item in item_store.list_for_serving(situation=lane, status="harness_pass"):
        if packet_provider is not None:
            assert_learner_item_provenance(item, packet_provider)
        if item.item_id in served_items or item.ecg_id in served_ecgs:
            continue
        for concept in item.application_objectives:
            candidates_by_concept[concept] += 1

    proposal_row = next(
        (
            row
            for row in concepts
            if candidates_by_concept.get(str(row["concept"]), 0) > 0
        ),
        None,
    )
    next_case = None
    if proposal_row:
        concept = str(proposal_row["concept"])
        next_case = {
            "concept": concept,
            "label": proposal_row["label"],
            "subskill": "apply_in_context",
            "lane": lane,
            "eligibleUnseenCases": int(candidates_by_concept[concept]),
            "href": (
                f"/practice?focus={quote(concept)}&subskill=apply_in_context"
                f"&lane={quote(lane)}"
            ),
            "reason": (
                f"{proposal_row['label']} is the highest-priority concept evidenced in this shift "
                "with a different real ECG available in the same setting."
            ),
            "learningEvidence": "formative_only",
        }

    primary = proposal_row or (concepts[0] if concepts else None)
    secondary = None
    if primary:
        primary_id = str(primary["concept"])
        paired = co_occurrence.get(primary_id, Counter())
        secondary = next(
            (
                row
                for concept, _ in paired.most_common()
                for row in concepts
                if row["concept"] == concept
            ),
            None,
        )
        if secondary is None:
            secondary = next(
                (row for row in concepts if row["concept"] != primary_id),
                None,
            )

    bridge = None
    if primary and secondary:
        bridge = {
            "primaryConcept": primary["concept"],
            "primaryLabel": primary["label"],
            "secondaryConcept": secondary["concept"],
            "secondaryLabel": secondary["label"],
            "prompt": (
                f"Compare {primary['label']} with {secondary['label']} across the ECGs you just completed. "
                "For each, name the trace evidence separately from the authored patient context, then explain "
                "how the distinction changed the safest next action."
            ),
            "grounding": "completed_server_grades_only",
        }

    rapid_href = (
        f"/rapid?focus={quote(str(primary['concept']))}"
        f"&receiptConcept={quote(str(primary['concept']))}"
        "&subskill=recognize&returnTo=%2Fpractice"
        if primary
        else None
    )
    ai_prompt = (
        "Use only the server-owned completed-shift evidence. Identify one recurring reasoning pattern, "
        "walk me through the cross-concept bridge if one is present, and ask one concise transfer question. "
        "Do not add diagnoses, measurements, or mastery claims."
    )
    return {
        "evidenceBoundary": "completed_server_grades_plus_independent_competency_state",
        "clinicalEvidence": "formative_only",
        "conceptEvidence": concepts,
        "priorityConcept": primary,
        "crossConceptBridge": bridge,
        "nextCaseProposal": next_case,
        "destinations": {
            "clinical": next_case,
            "rapid": (
                {
                    "href": rapid_href,
                    "concept": primary["concept"],
                    "label": primary["label"],
                    "purpose": "Recheck recognition on blinded real ECGs before returning to context.",
                }
                if primary and rapid_href
                else None
            ),
            "adaptiveReview": {"href": "/review", "purpose": "Rebuild the full due-first mastery plan."},
        },
        "aiPrompt": ai_prompt,
    }


__all__ = ["build_shift_debrief"]
