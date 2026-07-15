"""§16A2 — per-question-type scoring-schema validation (the model is NOT universal).

  - click: ROI geometry, not answer classes → must have a roi_target and no answer-class options.
  - fillin: a single unit-aware packet-feature measurement, with no choice key.
  - matching: each key is bound to one exact packet-manifest evidence boundary.
  - oldnew: ternary + comparison_validity → keying "old/unchanged" requires a stacked
    full-12-lead display and a prior ECG (else the answer is unprovable).
  - triage: recognition is inferred (pattern_threshold_hit), not observed (warn if it
    scores "ecg_recognition" as if stated).
"""

from __future__ import annotations

from typing import Any

from ...ontology import concept_label
from .. import grounding
from ..schemas import ClinicalCaseItem
from .result import CheckResult

_OLD_VALUES = {"old", "old_unchanged", "unchanged"}
_MATCHING_TARGETS = {
    "ecg_support": ("ecg", "Supported by this ECG packet"),
    "authored_context": ("context", "Provided only by the authored vignette"),
    "unsupported_claim": ("unsupported", "Not established by this ECG or vignette"),
}


def check(item: ClinicalCaseItem, packet: dict[str, Any], prior_packet: dict[str, Any] | None) -> CheckResult:
    messages: list[str] = []
    warnings: list[str] = []
    qt = item.question_type

    if qt == "click":
        if item.roi_target is None:
            messages.append("click item has no roi_target (click items grade by ROI geometry).")
        if item.options:
            messages.append("click item carries answer-class options; clicks must grade by ROI, not classes.")

    elif qt == "fillin":
        task = item.fill_in_task
        if task is None:
            messages.append("fillin item has no fill_in_task.")
        else:
            features = ((packet.get("ptbxl_plus") or {}).get("features") or {})
            expected = features.get(task.expected_feature)
            if expected is None:
                messages.append(
                    f"fillin target feature {task.expected_feature!r} is missing from the grounded packet."
                )
            else:
                try:
                    numeric = float(expected)
                except (TypeError, ValueError):
                    messages.append(
                        f"fillin target feature {task.expected_feature!r} is not numeric."
                    )
                else:
                    if not task.min_value <= numeric <= task.max_value:
                        messages.append(
                            f"fillin target {numeric:g} falls outside the authored response range."
                        )
            manifested = {claim.objective_id for claim in item.evidence_manifest.ecg_supports}
            if task.objective_id not in manifested:
                messages.append("fillin objective is not declared in the evidence manifest.")
        if item.options or item.steps or item.machine_read or item.roi_target is not None:
            messages.append(
                "fillin item carries another interaction key; numeric evidence tasks must have one response surface."
            )

    elif qt == "matching":
        task = item.matching_task
        if task is None:
            messages.append("matching item has no matching_task.")
        else:
            choice_labels = {choice.id: choice.label for choice in task.choices}
            expected_labels = {target_id: label for target_id, label in _MATCHING_TARGETS.values()}
            if choice_labels != expected_labels:
                messages.append(
                    "matching choices must use the reviewed ECG / vignette / unsupported evidence targets."
                )

            manifested = {claim.objective_id for claim in item.evidence_manifest.ecg_supports}
            packet_supported = grounding.supported_objectives(packet)
            rows_by_source = {row.source_type: row for row in task.rows}
            if set(rows_by_source) != set(_MATCHING_TARGETS) or len(rows_by_source) != len(task.rows):
                messages.append("matching task must contain exactly one row for each evidence source.")
            if {row.id for row in task.rows} != {"clause-a", "clause-b", "clause-c"}:
                messages.append("matching row ids must be neutral clause handles that do not reveal a source key.")
            for source_type, (expected_choice, _label) in _MATCHING_TARGETS.items():
                row = rows_by_source.get(source_type)
                if row is None:
                    continue
                if row.correct_choice_id != expected_choice:
                    messages.append(
                        f"matching row {row.id!r} has a key that disagrees with its {source_type!r} source."
                    )
                if source_type == "ecg_support":
                    objective = row.objective_id
                    if not objective or objective not in manifested:
                        messages.append("matching ECG row objective is not declared in the evidence manifest.")
                    if not objective or objective not in packet_supported:
                        messages.append("matching ECG row objective is not supported by the exact packet.")
                    if objective and row.source_reference != objective:
                        messages.append("matching ECG row source_reference must equal its objective_id.")
                    if objective and row.clause != concept_label(objective):
                        messages.append("matching ECG row clause must be the reviewed label of its objective_id.")
                elif source_type == "authored_context":
                    expected_reference = f"authored setting: {item.chips.setting}"
                    if row.source_reference != expected_reference:
                        messages.append("matching vignette row must reference the exact authored setting fact.")
                    if row.source_reference not in item.evidence_manifest.stem_adds:
                        messages.append("matching vignette row reference is absent from stem_adds.")
                    if row.clause != f"Encounter setting: {item.chips.setting}":
                        messages.append("matching vignette row clause does not match the authored setting.")
                else:
                    if row.source_reference not in item.evidence_manifest.forbidden_claims:
                        messages.append("matching unsupported row is not an exact forbidden_claims entry.")
                    if row.clause != f"Claim: {row.source_reference}":
                        messages.append("matching unsupported row clause must quote its forbidden claim exactly.")

        if (
            item.options
            or item.steps
            or item.machine_read
            or item.roi_target is not None
            or item.fill_in_task is not None
        ):
            messages.append(
                "matching item carries another interaction key; mapping tasks must have one response surface."
            )
        if item.application_objectives:
            messages.append("matching evidence-boundary tasks must not award clinical application objectives.")

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

    if qt != "fillin" and item.fill_in_task is not None:
        messages.append("non-fillin item carries a hidden fill_in_task key.")
    if qt != "matching" and item.matching_task is not None:
        messages.append("non-matching item carries a hidden matching_task key.")

    results_failed = bool(messages)
    # Emit warnings as a non-hard-stop note by appending to messages but marking soft if no hard fail.
    if warnings and not messages:
        return CheckResult("scoring_schema", passed=False, hard_stop=False, messages=warnings)
    return CheckResult("scoring_schema", passed=not results_failed, hard_stop=True, messages=messages + warnings)
