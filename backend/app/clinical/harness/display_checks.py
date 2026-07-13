"""§16E — display checks. A rhythm-strip-only screen silently narrows the construct for
axis / territory / BBB / old-new; it is allowed only when ``tested_scope == 'rhythm_only'``
AND every tested concept is a rhythm-class concept."""

from __future__ import annotations

from typing import Any

from .. import grounding
from ..schemas import ClinicalCaseItem
from .result import CheckResult

# Concepts a single rhythm strip can legitimately test (rate/rhythm/AV relationship).
RHYTHM_OK_CONCEPTS = {
    "rate",
    "sinus_rhythm",
    "atrial_fibrillation",
    "atrial_flutter",
    "supraventricular_tachycardia",
    "wide_complex_tachycardia",
    "bradycardia",
    "premature_ventricular_complex",
    "premature_atrial_complex",
    "paced_rhythm",
    "av_block_first_degree",
    "av_block_second_degree_mobitz_i",
    "av_block_second_degree_mobitz_ii",
    "av_block_third_degree",
    "normal_ecg",
}


def check(item: ClinicalCaseItem, packet: dict[str, Any], prior_packet: dict[str, Any] | None) -> CheckResult:
    messages: list[str] = []
    # Display spec and item tested_scope must agree.
    if item.display_spec.tested_scope != item.tested_scope:
        messages.append(
            f"display_spec.tested_scope '{item.display_spec.tested_scope}' disagrees with item "
            f"tested_scope '{item.tested_scope}'."
        )
    if item.tested_scope == "rhythm_only":
        non_rhythm = sorted(c for c in grounding.supported_objectives(packet) if c not in RHYTHM_OK_CONCEPTS)
        if non_rhythm:
            messages.append(
                f"tested_scope 'rhythm_only' but supported findings include non-rhythm concepts "
                f"{non_rhythm} that a rhythm strip cannot show (axis/territory/BBB). Use full 12-lead."
            )
    # oldnew comparability already enforced in scoring_schema; here ensure non-zoom display
    # for multi-lead question types.
    if item.question_type in {"oldnew"} and item.display_spec.mode != "stacked_twelve_lead":
        messages.append("oldnew requires display_spec.mode 'stacked_twelve_lead'.")
    return CheckResult("display_checks", passed=not messages, hard_stop=True, messages=messages)
