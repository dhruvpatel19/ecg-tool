"""§16A2 — per-question-type scoring-schema validation (the model is NOT universal).

  - click: ROI geometry, not answer classes → must have a roi_target and no answer-class options.
  - oldnew: ternary + comparison_validity → keying "old/unchanged" requires a stacked
    full-12-lead display and a prior ECG (else the answer is unprovable).
  - triage: recognition is inferred (pattern_threshold_hit), not observed (warn if it
    scores "ecg_recognition" as if stated).
"""

from __future__ import annotations

from typing import Any

from ..schemas import ClinicalCaseItem
from .result import CheckResult

_OLD_VALUES = {"old", "old_unchanged", "unchanged"}


def check(item: ClinicalCaseItem, packet: dict[str, Any], prior_packet: dict[str, Any] | None) -> CheckResult:
    messages: list[str] = []
    warnings: list[str] = []
    qt = item.question_type

    if qt == "click":
        if item.roi_target is None:
            messages.append("click item has no roi_target (click items grade by ROI geometry).")
        if item.options:
            messages.append("click item carries answer-class options; clicks must grade by ROI, not classes.")

    elif qt == "spoterror":
        if not item.machine_read or not any(line.bad for line in item.machine_read):
            messages.append("spoterror item has no machine_read line flagged bad to audit.")
        if item.roi_target is None:
            messages.append("spoterror item has no roi_target for the proof-on-trace click.")

    elif qt == "oldnew":
        values = {(o.value or "").lower() for o in item.options}
        if not ({"new"} & values) or not (_OLD_VALUES & values) or "cannot_determine" not in values:
            warnings.append("oldnew item should offer ternary values new / old_unchanged / cannot_determine.")
        old_keyed = any(
            (o.value or "").lower() in _OLD_VALUES and o.answer_class in {"ideal", "acceptable"}
            for o in item.options
        )
        if old_keyed and not (item.display_spec.mode == "stacked_twelve_lead" and item.prior_ecg_id):
            messages.append(
                "oldnew keys 'old/unchanged' as correct but lacks a stacked full-12-lead display + "
                "prior_ecg_id; comparison_validity is unprovable, so the key is invalid (§16A2)."
            )

    elif qt == "triage":
        if any("ecg_recognition" in (o.axis_scores or {}) for o in item.options):
            warnings.append(
                "triage scores 'ecg_recognition' as if stated; use 'pattern_threshold_hit' (inferred)."
            )

    results_failed = bool(messages)
    # Emit warnings as a non-hard-stop note by appending to messages but marking soft if no hard fail.
    if warnings and not messages:
        return CheckResult("scoring_schema", passed=False, hard_stop=False, messages=warnings)
    return CheckResult("scoring_schema", passed=not results_failed, hard_stop=True, messages=messages + warnings)
