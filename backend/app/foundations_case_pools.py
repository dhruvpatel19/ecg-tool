"""Private M01 case-role allocation and deterministic preference ordering.

Raw corpus identifiers stay on the server. The browser sends only an
allowlisted scene slot; the generic selector remains the safety fallback when a
preferred pool is absent, exhausted, or cannot satisfy the requested concept.
"""

from __future__ import annotations

import hashlib
import hmac


FOUNDATIONS_CASE_ALLOCATION_REVISION = "m01-foundations-cases-v1"

_ROLE_CASE_IDS: dict[str, tuple[str, ...]] = {
    "modeled": ("3", "279"),
    "guided": ("10", "108", "102"),
    "immediate_integration": ("14", "222"),
    "equivalent_retry": ("2", "282", "286", "1516"),
    "component_contrast": (
        "21", "12", "548", "307", "191", "209", "172",
        "195", "41", "103", "3514", "38", "100",
    ),
}

_SLOT_ROLE: dict[str, str] = {
    "foundations:S5:component": "component_contrast",
    "foundations:S6:component": "component_contrast",
    "foundations:S7:component": "component_contrast",
    "foundations:S8:component": "component_contrast",
    "foundations:S9:component": "component_contrast",
    "foundations:S10:modeled": "modeled",
    "foundations:S11:guided": "guided",
    "foundations:S12:integration": "immediate_integration",
    "foundations:equivalent-retry": "equivalent_retry",
}


def foundations_case_pool_summary() -> tuple[dict[str, object], ...]:
    """Return answer-free role counts for validation and operator diagnostics."""

    return tuple(
        {"role": role, "count": len(case_ids)}
        for role, case_ids in _ROLE_CASE_IDS.items()
    )


def validate_foundations_case_pools() -> None:
    ids = [case_id for case_ids in _ROLE_CASE_IDS.values() for case_id in case_ids]
    if len(ids) != 24 or len(set(ids)) != len(ids):
        raise RuntimeError("Foundations case-role allocation must contain 24 unique cases")
    if set(_SLOT_ROLE.values()) - set(_ROLE_CASE_IDS):
        raise RuntimeError("Foundations case slot references an unknown role")


def preferred_foundations_case_ids(
    slot: str | None,
    *,
    learner_id: str,
    secret: str,
) -> tuple[str, ...] | None:
    """Resolve an allowlisted slot to a learner-stable private preference order."""

    if slot is None:
        return None
    role = _SLOT_ROLE.get(slot)
    if role is None:
        raise ValueError("unknown_foundations_case_pool")
    case_ids = _ROLE_CASE_IDS[role]
    domain = f"{FOUNDATIONS_CASE_ALLOCATION_REVISION}\x00{learner_id}\x00{slot}\x00".encode()
    return tuple(sorted(
        case_ids,
        key=lambda case_id: hmac.new(
            secret.encode(), domain + case_id.encode(), hashlib.sha256
        ).digest(),
    ))


validate_foundations_case_pools()
