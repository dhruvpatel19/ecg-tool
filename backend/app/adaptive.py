from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from .ontology import CONCEPT_BY_ID, PRACTICE_GROUPS
from .retention import due_snapshot
from .source_policy import (
    generic_learner_candidate_policy,
    generic_learner_packet_policy,
    packet_mode_policy,
)
from .storage import LearningStore

# Minimum reliable Tier A/B cases before a concept group / individual concept is shown.
MIN_GROUP_CASES = 5
MIN_CONCEPT_CASES = 3

# Tie-breaker for a brand-new learner. Mastery/error/spacing always win once
# evidence exists, but an all-0.25 profile should begin with the reading scaffold
# rather than whichever pathology happens to sort first in SQLite.
ADAPTIVE_ONBOARDING_ORDER = [
    "normal_ecg",
    "rate",
    "sinus_rhythm",
    "bradycardia",
    "axis_normal",
    "qrs_duration",
    "qt_interval",
    "left_axis_deviation",
    "right_axis_deviation",
    "atrial_fibrillation",
    "right_bundle_branch_block",
    "left_bundle_branch_block",
    "av_block_first_degree",
    "qtc_prolongation",
    "left_ventricular_hypertrophy",
    "st_depression",
    "myocardial_infarction",
    "anterior_mi",
    "inferior_mi",
]


def _teaching_exemplar_rejection_reasons(case: dict[str, Any], concept_id: str | None) -> list[str]:
    """Stricter gate for a canonical guided example than for adaptive practice.

    Tier A/B can be acceptable for varied practice while still being a poor case
    to *introduce* a morphology. Exclude source contradictions, unconfirmed
    reports, borderline signal, and concept warnings that explicitly say the
    morphology evidence is limited.
    """
    reasons: list[str] = []
    if (case.get("signal_quality") or {}).get("status") != "acceptable":
        reasons.append("signal quality is not acceptable for a canonical exemplar")

    report = str((case.get("ptbxl") or {}).get("report") or "").casefold()
    compact = re.sub(r"[^a-zäöüß]+", " ", report)
    if "unbest" in compact and "bericht" in compact:
        reasons.append("source report is marked unconfirmed")
    if concept_id == "right_bundle_branch_block" and (
        "linksschenkelblock" in compact or "left bundle branch block" in compact or " lbbb " in f" {compact} "
    ):
        reasons.append("source report conflicts with the requested RBBB exemplar")
    if concept_id == "left_bundle_branch_block" and (
        "rechtsschenkelblock" in compact or "right bundle branch block" in compact or " rbbb " in f" {compact} "
    ):
        reasons.append("source report conflicts with the requested LBBB exemplar")

    confidence = (case.get("concept_confidence") or {}).get(concept_id or "") or {}
    warnings = " ".join(str(item) for item in confidence.get("warnings", [])).casefold()
    if "morphology support is limited" in warnings:
        reasons.append("morphology support is explicitly limited")
    return reasons


class CaseRepositoryLike(Protocol):
    def candidates(self, concept_id: str | None = None) -> list[dict[str, Any]]: ...
    def get_case(self, case_id: str) -> dict[str, Any] | None: ...
    def group_reliable_count(self, concept_ids: list[str]) -> int: ...


def _selector_candidates(
    repo: CaseRepositoryLike,
    concept_id: str | None,
    selector_context: Literal["generic", "rapid"],
) -> list[dict[str, Any]]:
    """Apply the cheap summary-level gate appropriate to this selector."""

    return [
        candidate
        for candidate in repo.candidates(concept_id)
        if selector_context == "rapid"
        or generic_learner_candidate_policy(candidate).allowed
    ]


def case_summary_from_packet(case: dict[str, Any]) -> dict[str, Any]:
    from .data_sources import case_summary

    return case_summary(case)


def concept_availability(repo: CaseRepositoryLike) -> list[dict[str, Any]]:
    counts = repo.concept_ab_counts() if hasattr(repo, "concept_ab_counts") else {}
    results = []
    for group in PRACTICE_GROUPS:
        concept_rows = []
        for concept_id in group["concepts"]:
            if concept_id not in CONCEPT_BY_ID:
                continue
            n = int(counts.get(concept_id, 0))
            concept_rows.append(
                {
                    "id": concept_id,
                    "label": CONCEPT_BY_ID[concept_id].label,
                    "reliableCaseCount": n,
                    "available": n >= MIN_CONCEPT_CASES,
                }
            )
        reliable = repo.group_reliable_count(list(group["concepts"]))
        available_concepts = [c for c in concept_rows if c["available"]]
        enabled = bool(available_concepts) and reliable >= MIN_GROUP_CASES
        results.append(
            {
                "id": group["id"],
                "label": group["label"],
                "concepts": concept_rows,
                "reliableCaseCount": reliable,
                "availableConceptCount": len(available_concepts),
                "enabled": enabled,
                "reason": ""
                if enabled
                else f"Needs ≥{MIN_CONCEPT_CASES} reliable cases for at least one subskill (group has {reliable}).",
            }
        )
    return results


def next_case(
    repo: CaseRepositoryLike,
    store: LearningStore,
    learner_id: str = "demo",
    concept_id: str | None = None,
    teaching_exemplar: bool = False,
    exclude_case_ids: set[str] | None = None,
    subskill_id: str | None = None,
    as_of: datetime | None = None,
    selector_context: Literal["generic", "rapid"] = "generic",
) -> dict[str, Any]:
    schedule_time = (as_of or datetime.now(UTC)).astimezone(UTC)
    profile = store.ensure_profile(learner_id)
    recent = set(store.recent_case_ids(learner_id)) | set(exclude_case_ids or set())
    mastery = {row["objective"]: row for row in profile["mastery"]}
    subskill_mastery = {
        (row["concept"], row["subskill"]): row
        for row in profile.get("subskillMastery", [])
    }

    # Choose one explicit competency for an unscoped session. This prevents the
    # old policy from rewarding highly multi-label cases simply because summing
    # weakness across 15 findings produced a larger score. On a new account the
    # profile order naturally starts with foundational objectives; later it is
    # driven by mastery, high-confidence errors, and spacing.
    target_objective = concept_id
    if target_objective is None:
        onboarding_rank = {objective: index for index, objective in enumerate(ADAPTIVE_ONBOARDING_ORDER)}

        def retention_priority(objective: str) -> tuple[int, float]:
            if subskill_id:
                row = subskill_mastery.get((objective, subskill_id))
                return tuple(due_snapshot(row or {}, as_of=schedule_time)["duePriority"])
            rows = [row for (concept, _), row in subskill_mastery.items() if concept == objective]
            if not rows:
                return (1, 0.0)
            return min(
                tuple(due_snapshot(row, as_of=schedule_time)["duePriority"])
                for row in rows
            )

        ranked_objectives = sorted(
            profile["mastery"],
            key=lambda row: (
                retention_priority(row["objective"]),
                float(subskill_mastery.get((row["objective"], subskill_id), {}).get("independentMastery", 0.15))
                if subskill_id else float(row.get("mastery", 0.25)),
                -int(subskill_mastery.get((row["objective"], subskill_id), {}).get("highConfidenceWrong", 0))
                if subskill_id else -int(row.get("highConfidenceWrong", 0)),
                int(subskill_mastery.get((row["objective"], subskill_id), {}).get("independentAttempts", 0))
                if subskill_id else int(row.get("attempts", 0)),
                -_stale_bonus(subskill_mastery.get((row["objective"], subskill_id), {}).get("lastPracticedAt"))
                if subskill_id else -_stale_bonus(row.get("lastPracticedAt")),
                onboarding_rank.get(row["objective"], len(onboarding_rank) + 1),
            ),
        )
        if hasattr(repo, "concept_ab_counts"):
            available_counts = repo.concept_ab_counts()
            target_objective = next(
                (row["objective"] for row in ranked_objectives if int(available_counts.get(row["objective"], 0)) > 0),
                None,
            )
        else:
            target_objective = next(
                (
                    row["objective"]
                    for row in ranked_objectives
                    if _selector_candidates(repo, row["objective"], selector_context)
                ),
                None,
            )

    candidates = _selector_candidates(
        repo, target_objective or concept_id, selector_context
    )
    requested_unavailable = bool(concept_id) and not candidates
    if not candidates and concept_id is None:
        # A raw corpus count can include a specialist source that is intentionally
        # unavailable to this broad selector. Do not describe the unrelated
        # fallback as targeting that objective.
        target_objective = None
    if not candidates:
        candidates = _selector_candidates(repo, None, selector_context)
    if not candidates:
        return {
            "case": None,
            "reason": "No reliable Tier A/B cases are available yet.",
            "targetObjectives": [],
            "requestedConceptUnavailable": requested_unavailable,
        }
    retention_row = (
        subskill_mastery.get((target_objective, subskill_id), {})
        if target_objective and subskill_id
        else {}
    )
    retention_status = due_snapshot(retention_row, as_of=schedule_time)

    # For an exact competency, prefer a new real ECG until the available pool is
    # exhausted. This prevents repeated use of one tracing from masquerading as
    # transfer across cases.
    if target_objective and subskill_id:
        prior_retention_cases = set(
            store.retention_case_ids(learner_id, target_objective, subskill_id)
        )
        distinct_candidates = [
            candidate for candidate in candidates
            if candidate["case_id"] not in prior_retention_cases
        ]
        if distinct_candidates:
            candidates = distinct_candidates
    # Avoid an immediate repeat whenever the corpus has any unseen alternative.
    fresh_candidates = [candidate for candidate in candidates if candidate["case_id"] not in recent]
    if fresh_candidates:
        candidates = fresh_candidates

    def score(candidate: dict[str, Any]) -> float:
        value = 0.0
        supported = candidate.get("supported_objectives", [])
        if target_objective and target_objective in supported:
            target_row = mastery.get(target_objective, {})
            exact_row = subskill_mastery.get((target_objective, subskill_id), {}) if subskill_id else {}
            target_level = float(exact_row.get("independentMastery", 0.15)) if subskill_id else float(target_row.get("mastery", 0.25))
            value += (1.0 - target_level) * 3.0
            value += min(0.8, int(target_row.get("highConfidenceWrong", 0)) * 0.2)
            if subskill_id:
                value += min(0.8, int(exact_row.get("highConfidenceWrong", 0)) * 0.2)
                value += _stale_bonus(exact_row.get("lastPracticedAt"))
            else:
                value += _stale_bonus(target_row.get("lastPracticedAt"))

        # Secondary coverage is useful, but only as a small tie-breaker. Average
        # the three weakest co-objectives rather than summing every label.
        secondary_needs: list[float] = []
        for objective in supported:
            if objective == target_objective:
                continue
            row = mastery.get(objective, {})
            mastery_score = float(row.get("mastery", 0.25))
            secondary_needs.append(1.0 - mastery_score)
        if secondary_needs:
            value += sum(sorted(secondary_needs, reverse=True)[:3]) / min(3, len(secondary_needs)) * 0.35

        # Prefer interpretable teaching cases over pathological label density.
        # Four supported objectives is already enough for a full rapid read.
        value -= max(0, len(supported) - 4) * 0.14
        if candidate["case_id"] in recent:
            value -= 5.0
        if candidate.get("concept_tier") == "A":
            value += 0.35
        if candidate.get("source") == "fixture":
            value -= 0.1
        return value

    ranked = sorted(candidates, key=score, reverse=True)
    selected = ranked[0]
    case = None
    exemplar_rejections: list[dict[str, Any]] = []
    candidate_pool = ranked[:200]
    for candidate in candidate_pool:
        packet = repo.get_case(candidate["case_id"])
        if packet is None:
            continue
        source_decision = (
            packet_mode_policy(packet, "rapid")
            if selector_context == "rapid"
            else generic_learner_packet_policy(packet)
        )
        if not source_decision.allowed:
            exemplar_rejections.append(
                {"caseId": candidate["case_id"], "reasons": [source_decision.reason]}
            )
            continue
        reasons = _teaching_exemplar_rejection_reasons(packet, target_objective) if teaching_exemplar else []
        if reasons:
            exemplar_rejections.append({"caseId": candidate["case_id"], "reasons": reasons})
            continue
        selected = candidate
        case = packet
        break
    if case is None:
        return {
            "case": None,
            "reason": (
                "No case passed the stricter teaching-exemplar quality and source-agreement gate."
                if teaching_exemplar
                else "Selected case could not be loaded."
            ),
            "targetObjectives": [],
            "exemplarRejections": exemplar_rejections[:10],
        }
    supported_objectives = case.get("supported_objectives", [])
    weak_objectives = [
        objective
        for objective in supported_objectives
        if float(mastery.get(objective, {}).get("mastery", 0.25)) < 0.55
    ]
    targets = []
    if target_objective and target_objective in supported_objectives:
        targets.append(target_objective)
    targets.extend(objective for objective in weak_objectives if objective not in targets)
    reason = (
        f"No reliable cases for '{CONCEPT_BY_ID[concept_id].label}' yet — showing a high-yield case instead."
        if requested_unavailable and concept_id in CONCEPT_BY_ID
        else (
            f"Focused on {CONCEPT_BY_ID[target_objective].label}"
            f"{(' · ' + subskill_id.replace('_', ' ')) if subskill_id else ''}: "
            f"{('retention review is ' + retention_status['dueState'] + ', ') if retention_status['isDue'] else ''}"
            "low mastery, case diversity, spacing, and recent-case avoidance."
            if target_objective in CONCEPT_BY_ID
            else "Selected by low mastery, spacing, case clarity, and recent-case avoidance."
        )
    )
    return {
        "case": case_summary_from_packet(case),
        "reason": reason,
        "targetObjectives": targets[:3] or supported_objectives[:3],
        "requestedConceptUnavailable": requested_unavailable,
        "exemplarRejections": exemplar_rejections[:10],
        "retention": {
            "dueState": retention_status["dueState"],
            "isDue": retention_status["isDue"],
            "overdueDays": retention_status["overdueDays"],
            "nextDueAt": retention_row.get("nextDueAt"),
            "stabilityDays": float(retention_row.get("stabilityDays", 0.0)),
        },
    }


def _stale_bonus(value: str | None) -> float:
    if not value:
        return 0.4
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return 0.2
    days = (datetime.now(UTC) - dt).days
    return min(0.5, max(0.0, days / 14 * 0.5))
