"""Adaptive rapid-review sessions.

A review session drives a learner through many grounded cases for one or more
target objectives (e.g. "anterior MI") until they reach a mastery goal or hit a
case cap — the "do 50 anterior-MI tracings until it clicks" workflow. Case
selection prioritizes the weakest target objective, avoids repeats within the
session, and reads mastery (updated by /attempts) to decide completion.
"""

from __future__ import annotations

from typing import Any

from .data_sources import case_summary
from .ontology import CONCEPT_BY_ID, PRACTICE_GROUPS, concept_label
from .source_policy import (
    generic_learner_candidate_policy,
    generic_learner_packet_policy,
)
from .storage import LearningStore

_GROUP_BY_ID = {group["id"]: group for group in PRACTICE_GROUPS}


def _generic_candidates(repo: Any, concept_id: str | None) -> list[dict[str, Any]]:
    return [
        candidate
        for candidate in repo.candidates(concept_id)
        if generic_learner_candidate_policy(candidate).allowed
    ]


def resolve_objectives(concept_id: str | None, group_id: str | None, objectives: list[str] | None) -> list[str]:
    if objectives:
        return [o for o in objectives if o in CONCEPT_BY_ID]
    if group_id and group_id in _GROUP_BY_ID:
        return [c for c in _GROUP_BY_ID[group_id]["concepts"] if c in CONCEPT_BY_ID]
    if concept_id and concept_id in CONCEPT_BY_ID:
        return [concept_id]
    return []


def _mastery_map(store: LearningStore, learner_id: str) -> dict[str, dict[str, Any]]:
    profile = store.ensure_profile(learner_id)
    return {row["objective"]: row for row in profile["mastery"]}


def _progress(objectives: list[str], mastery: dict[str, dict[str, Any]], target: float) -> dict[str, Any]:
    rows = []
    mastered = 0
    for objective in objectives:
        value = float(mastery.get(objective, {}).get("mastery", 0.25))
        attempts = int(mastery.get(objective, {}).get("attempts", 0))
        is_mastered = value >= target
        mastered += int(is_mastered)
        rows.append(
            {
                "objective": objective,
                "label": concept_label(objective),
                "mastery": round(value, 3),
                "attempts": attempts,
                "mastered": is_mastered,
            }
        )
    return {
        "objectives": rows,
        "masteredCount": mastered,
        "totalObjectives": len(objectives),
        "complete": mastered == len(objectives) and objectives != [],
    }


def start_review(
    repo: Any,
    store: LearningStore,
    learner_id: str,
    concept_id: str | None = None,
    group_id: str | None = None,
    objectives: list[str] | None = None,
    target_mastery: float = 0.8,
    max_cases: int = 30,
) -> dict[str, Any]:
    resolved = resolve_objectives(concept_id, group_id, objectives)
    if not resolved:
        return {"error": "No valid objectives for this review session."}
    label = concept_label(resolved[0]) if len(resolved) == 1 else (
        _GROUP_BY_ID.get(group_id, {}).get("label") if group_id else f"{len(resolved)} objectives"
    )
    session_id = store.create_review_session(learner_id, resolved, str(label), target_mastery, max_cases)
    return next_review_case(repo, store, session_id)


def review_status(repo: Any, store: LearningStore, session_id: str) -> dict[str, Any] | None:
    session = store.get_review_session(session_id)
    if not session:
        return None
    mastery = _mastery_map(store, session["learnerId"])
    return {
        "session": session,
        "progress": _progress(session["objectives"], mastery, session["targetMastery"]),
        "casesDone": len(session["served"]),
    }


def next_review_case(repo: Any, store: LearningStore, session_id: str) -> dict[str, Any] | None:
    session = store.get_review_session(session_id)
    if not session:
        return None
    objectives = session["objectives"]
    served = set(session["served"])
    mastery = _mastery_map(store, session["learnerId"])
    progress = _progress(objectives, mastery, session["targetMastery"])

    # Completion checks.
    status = None
    if progress["complete"]:
        status = "mastered"
    elif len(served) >= session["maxCases"]:
        status = "capped"
    if status:
        store.set_review_status(session_id, status)
        return {
            "session": {**session, "status": status},
            "progress": progress,
            "casesDone": len(served),
            "case": None,
            "done": True,
            "reason": "Mastery goal reached." if status == "mastered" else "Reached the case cap for this session.",
        }

    # Target the weakest still-unmastered objective.
    pending = [o for o in objectives if float(mastery.get(o, {}).get("mastery", 0.25)) < session["targetMastery"]]
    pending.sort(key=lambda o: float(mastery.get(o, {}).get("mastery", 0.25)))
    target = pending[0] if pending else objectives[0]

    candidates = [c for c in _generic_candidates(repo, target) if c["case_id"] not in served]
    if not candidates:
        # fall back to any session objective the learner hasn't seen yet
        candidates = [
            c
            for o in objectives
            for c in _generic_candidates(repo, o)
            if c["case_id"] not in served
        ]
    if not candidates:
        # No unseen reliable cases for any objective (covers concepts with zero
        # reliable cases — prevents max() on an empty sequence, the audited 500).
        store.set_review_status(session_id, "exhausted")
        any_existing = any(_generic_candidates(repo, o) for o in objectives)
        return {
            "session": {**session, "status": "exhausted"},
            "progress": progress,
            "casesDone": len(served),
            "case": None,
            "done": True,
            "reason": (
                "No more unseen reliable cases for these objectives."
                if any_existing
                else "No reliable Tier A/B cases exist for these objectives yet."
            ),
        }

    def score(candidate: dict[str, Any]) -> float:
        value = 0.0
        for objective in candidate.get("supported_objectives", []):
            if objective in objectives:
                value += 1.0 - float(mastery.get(objective, {}).get("mastery", 0.25))
        if candidate.get("concept_tier") == "A":
            value += 0.3
        return value

    selected = None
    case = None
    for candidate in sorted(candidates, key=score, reverse=True):
        packet = repo.get_case(candidate["case_id"])
        if generic_learner_packet_policy(packet).allowed:
            selected = candidate
            case = packet
            break
    if selected is None or case is None:
        store.set_review_status(session_id, "exhausted")
        return {
            "session": {**session, "status": "exhausted"},
            "progress": progress,
            "casesDone": len(served),
            "case": None,
            "done": True,
            "reason": "No unseen case passed the broad learner-source contract.",
        }
    store.record_review_served(session_id, selected["case_id"])
    return {
        "session": store.get_review_session(session_id),
        "progress": progress,
        "casesDone": len(served) + 1,
        "case": case_summary(case) if case else None,
        "targetObjective": target,
        "done": False,
        "reason": f"Targeting your weakest objective in this set: {concept_label(target)}.",
    }
