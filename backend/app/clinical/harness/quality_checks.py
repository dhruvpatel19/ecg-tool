"""Clinical/pedagogical quality checks (round-4 generation audit).

These close the harness blind spot the audit exposed: clinically-wrong PROSE or wrong SCORING
TAGS attached to otherwise-grounded ECG facts. The earlier checks verify "is the ECG label
grounded?"; these verify "is the clinical claim / tag / question internally correct?".
"""

from __future__ import annotations

from typing import Any

from .. import grounding
from ..constants import parse_action_urgency
from ..schemas import ClinicalCaseItem
from .result import CheckResult

# --- distractor self-refutation (the option tells the learner why it's wrong) ------
_LEAK_PHRASES = (
    "despite", "solely because", "based solely on", "even though",
    "although the patient is stable", "because the ecg is chronic", "no acute symptoms",
)


def distractor_leak(item: ClinicalCaseItem, packet: dict[str, Any], prior: dict[str, Any] | None) -> CheckResult:
    msgs: list[str] = []
    for o in item.options:
        low = o.text.lower()
        hit = next((p for p in _LEAK_PHRASES if p in low), None)
        if hit:
            msgs.append(f"Option '{o.id}' self-refutes via '{hit}' — a distractor must not signal its own wrongness.")
    return CheckResult("distractor_leak", passed=not msgs, hard_stop=True, messages=list(dict.fromkeys(msgs)))


# --- click stem leaks the assessment task (should be clinical context only) --------
_CLICK_LEAK = ("learner", "click", "for this question", "the following objective",
               "best matches the objective", "correct finding", "is asked to", "on the trace")


def click_stem_leak(item: ClinicalCaseItem, packet: dict[str, Any], prior: dict[str, Any] | None) -> CheckResult:
    if item.question_type != "click":
        return CheckResult("click_stem_leak", True)
    low = item.stem.lower()
    hits = [p for p in _CLICK_LEAK if p in low]
    if hits:
        return CheckResult("click_stem_leak", passed=False, hard_stop=True,
                           messages=[f"Click stem leaks task language {hits}; write only clinical context (the prompt owns the task)."])
    return CheckResult("click_stem_leak", True)


# --- clinical numeric semantics: QTc "prolonged" must be true for the sex, and QT is
# unreliable in AF/flutter (round-4 audit: ECG 321 keyed QTc 437 in a woman as prolonged) --
def _sex(packet: dict[str, Any]) -> str | None:
    raw = (packet.get("ptbxl") or {}).get("metadata", {}).get("sex")
    return {0: "male", 1: "female", "0": "male", "1": "female", "M": "male", "F": "female"}.get(raw)


def clinical_numeric_semantics(item: ClinicalCaseItem, packet: dict[str, Any], prior: dict[str, Any] | None) -> CheckResult:
    feats = grounding.features(packet)
    supported = grounding.supported_objectives(packet)
    targets = {c.objective_id for c in item.evidence_manifest.ecg_supports}
    prose = " ".join([item.stem, item.evidence_manifest.action_rationale, *[o.text for o in item.options]]).lower()
    claims_prolonged = "qtc_prolongation" in targets or any(
        p in prose for p in ("prolonged qt", "long qt", "qtc prolong", "prolonged qtc")
    )
    if not claims_prolonged:
        return CheckResult("clinical_numeric_semantics", True)
    msgs: list[str] = []
    if supported & {"atrial_fibrillation", "atrial_flutter"}:
        msgs.append("QT/QTc is unreliable in AF/flutter (irregular rhythm) — do not key QTc prolongation.")
    else:
        qtc = feats.get("qtc_ms")
        threshold = 470 if _sex(packet) == "male" else 480  # CCS: ≥470 male / ≥480 female = prolonged
        if qtc is not None and float(qtc) < threshold:
            msgs.append(f"Keys prolonged QTc but QTc={qtc} < {threshold} ms ({_sex(packet) or 'female-threshold default'}).")
    return CheckResult("clinical_numeric_semantics", passed=not msgs, hard_stop=True, messages=msgs)


# --- ECG pattern must not be stated as documented disease history -------------------
_DISEASE_HISTORY_PHRASES = (
    "known prior mi", "documented mi", "documented myocardial infarction",
    "prior mi history", "known coronary artery disease", "history of myocardial infarction",
)


def disease_history_provenance(item: ClinicalCaseItem, packet: dict[str, Any], prior: dict[str, Any] | None) -> CheckResult:
    prose = " ".join([item.stem, item.evidence_manifest.action_rationale, *[o.text for o in item.options]]).lower()
    msgs = [f"Prose asserts documented history '{p}' from an ECG pattern alone (use 'old-MI pattern')."
            for p in _DISEASE_HISTORY_PHRASES if p in prose]
    return CheckResult("disease_history_provenance", passed=not msgs, hard_stop=True, messages=list(dict.fromkeys(msgs)))


# --- option class ↔ action-intensity consistency (catches the triage/stepwise inversion) --
def option_class_action_consistency(item: ClinicalCaseItem, packet: dict[str, Any], prior: dict[str, Any] | None) -> CheckResult:
    # Only meaningful where options are management ACTIONS. Triage classes come from the value
    # ordinal; oldnew options are new/old/cannot-determine (not actions) — skip both.
    if item.question_type not in {"mcq", "stepwise"}:
        return CheckResult("option_class_action_consistency", True)
    msgs: list[str] = []
    for o in item.options:
        if o.answer_class == "ideal":
            continue
        # Only the unambiguous direction: an unmistakably aggressive action (ICU/cath/cardiovert/
        # immediate/ED-now) cannot be "doing too little". (The reverse — over-treatment via a low-key
        # drug — isn't reliably detectable, so we don't flag it and risk false positives.)
        if parse_action_urgency(o.text) in {"act_now", "urgent"} and o.answer_class == "under_triage":
            msgs.append(f"Option '{o.id}': an aggressive/urgent action is tagged under_triage — that is OVER-triage.")
    return CheckResult("option_class_action_consistency", passed=not msgs, hard_stop=True, messages=msgs)
