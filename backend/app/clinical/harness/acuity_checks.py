"""§16B5–6 — the danger/acuity enforcement point.

  - required_safety_action: an ideal/acceptable option for a high-acuity concept must
    carry a required safety token, else it is capped at under-triage ("atropine-only ≠
    acceptable for symptomatic complete block").
  - acuity_cap_by_concept: the item's acuity may not exceed the ceiling derived from the
    supported concepts (with measurement bumps), so acuity follows the *finding*, not the
    *story* (catches isolated 1°AVB keyed as an admit).
"""

from __future__ import annotations

from typing import Any

from .. import grounding
from ..constants import acuity_rank, ACUITY_TIER_ORDER, parse_action_urgency, urgency_rank
from ..content_tables import (
    ACUITY_BASE,
    ACUITY_CAP_BY_CONCEPT,
    ACUITY_MEASUREMENT_ADJUST,
    REQUIRED_SAFETY_ACTIONS,
)
from ..schemas import ClinicalCaseItem
from .result import CheckResult


def required_safety_action(item: ClinicalCaseItem, packet: dict[str, Any], prior_packet: dict[str, Any] | None) -> CheckResult:
    supported = grounding.supported_objectives(packet)
    gated = {c: REQUIRED_SAFETY_ACTIONS[c] for c in supported if c in REQUIRED_SAFETY_ACTIONS}
    if not gated:
        return CheckResult("required_safety_action", True)
    messages: list[str] = []
    for option in item.options:
        if option.answer_class not in {"ideal", "acceptable"}:
            continue
        carried = set(option.required_safety_tokens)
        if option.parsed:
            carried |= set(option.parsed.safety_tokens)
        for concept, required in gated.items():
            if not (carried & set(required)):
                messages.append(
                    f"Option '{option.id}' is tagged {option.answer_class} for high-acuity "
                    f"'{concept}' but carries none of the required safety actions {required} "
                    f"(carried: {sorted(carried) or 'none'})."
                )
    return CheckResult("required_safety_action", passed=not messages, hard_stop=True, messages=messages)


def effective_acuity_tier(supported: set[str], feats: dict[str, Any]) -> str:
    """Highest acuity TIER the supported findings justify (base + measurement bumps).

    Tier-vs-tier is the robust gate: the per-concept urgency caps in
    ACUITY_CAP_BY_CONCEPT live on a different scale and are consumed by the grader for
    per-option urgency, not for this ceiling.
    """
    if not supported:
        return "low"
    base_rank = max((acuity_rank(ACUITY_BASE.get(c, "low")) for c in supported), default=1)
    bump = sum(rule(feats, supported) for rule in ACUITY_MEASUREMENT_ADJUST)
    eff_rank = min(base_rank + bump, len(ACUITY_TIER_ORDER) - 1)
    return ACUITY_TIER_ORDER[eff_rank]


def acuity_cap(item: ClinicalCaseItem, packet: dict[str, Any], prior_packet: dict[str, Any] | None) -> CheckResult:
    supported = grounding.supported_objectives(packet)
    feats = grounding.features(packet)
    eff_tier = effective_acuity_tier(supported, feats)
    if acuity_rank(item.acuity_tier) > acuity_rank(eff_tier):
        return CheckResult(
            "acuity_cap_by_concept",
            passed=False,
            hard_stop=True,
            messages=[
                f"Item acuity '{item.acuity_tier}' exceeds the ceiling '{eff_tier}' derived from "
                f"supported findings {sorted(supported)}. Acuity is following the story, not the finding."
            ],
        )
    return CheckResult("acuity_cap_by_concept", True)


def option_action_urgency_cap(item: ClinicalCaseItem, packet: dict[str, Any], prior_packet: dict[str, Any] | None) -> CheckResult:
    """§round-3 audit: a grounded ECG fact must not license an ungrounded high-acuity ACTION.
    Each ideal/acceptable option's parsed action-urgency must not exceed the per-concept
    action ceiling (ACUITY_CAP_BY_CONCEPT). Catches e.g. 'ICU + transvenous pacing' keyed as
    ideal for an isolated first-degree AV block."""
    supported = grounding.supported_objectives(packet)
    if not supported:
        return CheckResult("option_action_urgency_cap", True)
    ceiling = max((ACUITY_CAP_BY_CONCEPT.get(c, "workup") for c in supported), key=urgency_rank)
    messages: list[str] = []
    for option in item.options:
        if option.answer_class not in {"ideal", "acceptable"}:
            continue
        urgency = parse_action_urgency(option.text)
        if urgency_rank(urgency) > urgency_rank(ceiling):
            messages.append(
                f"Option '{option.id}' ({option.answer_class}) implies action urgency '{urgency}', "
                f"exceeding the ceiling '{ceiling}' for supported findings {sorted(supported)} — "
                f"a grounded ECG fact does not license that action without extra evidence."
            )
    return CheckResult("option_action_urgency_cap", passed=not messages, hard_stop=True, messages=messages)
