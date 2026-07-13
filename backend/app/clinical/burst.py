"""Short-burst generation against REAL corpus cases, for the iterate-and-inspect workflow.

Generate N items from real PTB-XL tracings, harness-gate them, and return everything needed to
rigorously inspect a burst (the accepted items in full, the rejects with reasons, diversity, and
per-concept spread) before scaling up. Deliberately small + observable — no auto-serving.
"""

from __future__ import annotations

from typing import Any, Callable

from .action_library import has_actions
from .generator import generate_and_vet, generate_skeleton_and_vet
from .grounding import features, supported_objectives
from .harness.acuity_checks import effective_acuity_tier

PacketProvider = Callable[[str], dict[str, Any] | None]

_ACUITY_TO_SITUATION = {
    "high": "ed",
    "moderate_high": "ed",
    "moderate": "ward",
    "low": "clinic",
    "none": "clinic",
}


def situation_for(packet: dict[str, Any]) -> str:
    """Frame the lane from the finding's acuity so the situation is grounded, not arbitrary."""
    eff = effective_acuity_tier(supported_objectives(packet), features(packet))
    return _ACUITY_TO_SITUATION.get(eff, "clinic")


def _candidate_case_ids(repo, concept: str | None, n: int) -> list[str]:
    seen: set[str] = set()
    ids: list[str] = []
    for cand in repo.candidates(concept):
        cid = str(cand["case_id"])
        if cid in seen:
            continue
        seen.add(cid)
        ids.append(cid)
        if len(ids) >= n:
            break
    return ids


def run_burst(
    repo,
    packet_provider: PacketProvider,
    provider: Any,
    n: int = 10,
    question_type: str = "mcq",
    concept: str | None = None,
) -> dict[str, Any]:
    case_ids = _candidate_case_ids(repo, concept, n)
    # Two-layer skeleton generation for MCQ on concepts we have an action library for.
    use_skeleton = question_type == "mcq" and concept is not None and has_actions(concept)
    results: list[dict[str, Any]] = []
    for i, cid in enumerate(case_ids):
        packet = packet_provider(cid)
        if packet is None:
            results.append({"ecg_id": cid, "accepted": False, "reason": "no_packet", "item": None, "report": None})
            continue
        situation = situation_for(packet)
        if use_skeleton:
            outcome = generate_skeleton_and_vet(packet, concept, provider, situation, seed=i)
        else:
            outcome = generate_and_vet(packet, situation, question_type, provider)
        outcome["ecg_id"] = cid
        outcome["situation"] = situation
        outcome["packet"] = packet
        results.append(outcome)

    accepted = [r for r in results if r["accepted"]]
    reasons: dict[str, int] = {}
    for r in results:
        if not r["accepted"]:
            reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
    signatures = {(r["item"].ecg_id, r["item"].question_type) for r in accepted}
    concepts_covered: dict[str, int] = {}
    for r in accepted:
        for c in {claim.objective_id for claim in r["item"].evidence_manifest.ecg_supports}:
            concepts_covered[c] = concepts_covered.get(c, 0) + 1
    return {
        "results": results,
        "accepted": accepted,
        "summary": {
            "attempts": len(results),
            "accepted": len(accepted),
            "accept_rate": round(len(accepted) / len(results), 3) if results else 0.0,
            "distinct_signatures": len(signatures),
            "reject_reasons": reasons,
            "concepts_covered": concepts_covered,
        },
    }
