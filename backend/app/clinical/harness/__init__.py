"""The Clinical Decisions validation harness (storyboard §16B/§16F honesty spine).

``run_harness(item, packet, prior_packet)`` runs every check and returns a
:class:`HarnessReport`. The item passes only if no hard-stop check fails. Build the
harness FIRST and gate item promotion (and the nano generator) on a green report.
"""

from __future__ import annotations

from typing import Any, Callable

from ..schemas import ClinicalCaseItem
from . import (
    acuity_checks,
    causal_checks,
    compound_parser,
    display_checks,
    evidence_binding,
    quality_checks,
    scoring_schema,
)
from .result import CheckResult, HarnessReport

# Ordered so compound_parser runs first (it populates option.parsed, which the
# required-safety check reads).
CheckFn = Callable[[ClinicalCaseItem, dict[str, Any], dict[str, Any] | None], CheckResult]

CHECKS: list[CheckFn] = [
    compound_parser.check,
    evidence_binding.check,
    evidence_binding.measurement_claim_binding,
    causal_checks.acute_temporal,
    causal_checks.symptom_causality,
    causal_checks.transient_event,
    acuity_checks.required_safety_action,
    acuity_checks.acuity_cap,
    acuity_checks.option_action_urgency_cap,
    quality_checks.distractor_leak,
    quality_checks.click_stem_leak,
    quality_checks.clinical_numeric_semantics,
    quality_checks.disease_history_provenance,
    quality_checks.option_class_action_consistency,
    scoring_schema.check,
    display_checks.check,
]


def run_harness(
    item: ClinicalCaseItem,
    packet: dict[str, Any],
    prior_packet: dict[str, Any] | None = None,
) -> HarnessReport:
    report = HarnessReport(item_id=item.item_id)
    for check in CHECKS:
        try:
            report.results.append(check(item, packet, prior_packet))
        except Exception as exc:  # a check crashing is itself a hard-stop failure
            report.results.append(
                CheckResult(
                    check=getattr(check, "__name__", "unknown"),
                    passed=False,
                    hard_stop=True,
                    messages=[f"check raised {type(exc).__name__}: {exc}"],
                )
            )
    return report


__all__ = ["run_harness", "HarnessReport", "CheckResult", "CHECKS"]
