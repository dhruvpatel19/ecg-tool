"""Fail-closed provenance rules for learner-facing Clinical Decisions items.

Synthetic ``fixture-*`` and ``seed-*`` packets remain useful for deterministic
harness/grader tests, but they are never valid inputs to a learner shift.  This
module is deliberately small and independent of the item generator so the same
contract can be asserted both at startup and immediately before serving/grading.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

from .schemas import ClinicalCaseItem

PacketProvider = Callable[[str], dict[str, Any] | None]

LEARNER_CLINICAL_SOURCES = frozenset({"ptbxl", "prepared_bundle"})
SYNTHETIC_ID_PREFIXES = ("seed-", "fixture-")
LOCKED_OBJECTIVES = frozenset({"wide_complex_tachycardia"})


def _is_synthetic_id(value: str | None) -> bool:
    return bool(value) and str(value).lower().startswith(SYNTHETIC_ID_PREFIXES)


def assert_learner_item_provenance(
    item: ClinicalCaseItem,
    packet_provider: PacketProvider,
) -> dict[str, Any]:
    """Return the grounded packet or raise when an item is unsafe to serve.

    Old/new remains locked until the platform has an authenticated longitudinal
    pair source rather than two unrelated records.  WCT remains locked until an
    appropriately sourced authored case is added.  These checks prevent a stale
    database row from bypassing the startup bank builder.
    """

    identifiers = (item.item_id, item.ecg_id, item.prior_ecg_id)
    if any(_is_synthetic_id(value) for value in identifiers):
        raise RuntimeError(
            f"Learner Clinical item {item.item_id!r} references a synthetic identifier."
        )
    if item.question_type == "oldnew":
        raise RuntimeError(
            f"Learner Clinical item {item.item_id!r} uses old/new without an authenticated longitudinal pair source."
        )
    objectives = {
        claim.objective_id for claim in item.evidence_manifest.ecg_supports
    }
    locked = objectives & LOCKED_OBJECTIVES
    if locked:
        raise RuntimeError(
            f"Learner Clinical item {item.item_id!r} uses locked objective(s): {sorted(locked)}."
        )

    packet = packet_provider(item.ecg_id)
    if packet is None:
        raise RuntimeError(
            f"Learner Clinical item {item.item_id!r} has no grounded packet for ECG {item.ecg_id!r}."
        )
    source = str(packet.get("source") or "").lower()
    if source not in LEARNER_CLINICAL_SOURCES:
        raise RuntimeError(
            f"Learner Clinical item {item.item_id!r} resolved to disallowed source {source!r}."
        )
    if str(packet.get("case_id")) != str(item.ecg_id):
        raise RuntimeError(
            f"Learner Clinical item {item.item_id!r} resolved to the wrong packet id."
        )
    return packet


def assert_serving_bank_provenance(
    items: Iterable[ClinicalCaseItem],
    packet_provider: PacketProvider,
) -> None:
    """Assert the provenance contract for every startup-loaded serving item."""

    for item in items:
        if item.validation_status == "harness_pass":
            assert_learner_item_provenance(item, packet_provider)
