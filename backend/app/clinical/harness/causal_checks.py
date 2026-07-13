"""§16B1–3 — the causal/temporal bridge checks the 4-axis validator misses.

These verify the *bridge* between the authored vignette and the real tracing, not the
plausibility of each in isolation:
  - acute_temporal_causality: acute/evolving language needs serial/acute/prior evidence.
  - symptom_causality: a finding may not be keyed as the cause of a symptom it must-not-explain.
  - transient_event_evidence: torsades/VT-run/telemetry claims need rhythm-strip evidence.
"""

from __future__ import annotations

from typing import Any

from .. import grounding
from ..constants import (
    ACUTE_EVIDENCE_TOKENS,
    SYMPTOM_SYNONYMS,
    TEMPORAL_ACUITY_CUES,
    TRANSIENT_EVENT_CUES,
    TRANSIENT_EVIDENCE_TOKENS,
)
from ..content_tables import SYMPTOM_CAUSALITY
from ..schemas import ClinicalCaseItem
from .result import CheckResult

_ESCALATION_CUES = (
    "admit", "pacing", "transvenous", "urgent", "activate", "cardiology", "icu", "escalat",
)


def _manifest_blob(item: ClinicalCaseItem) -> str:
    parts = [item.stem, *item.evidence_manifest.stem_adds, *item.evidence_manifest.acceptable_range]
    parts.extend(c.source_type for c in item.evidence_manifest.ecg_supports)
    return " ".join(parts).lower()


def _vignette_text(item: ClinicalCaseItem) -> str:
    """The authored clinical vignette (stem + stem_adds) — where an acuity/temporal overclaim lives."""
    return " ".join([item.stem, *item.evidence_manifest.stem_adds]).lower()


def _keyed_option_text(item: ClinicalCaseItem) -> str:
    """Text of the ideal/acceptable options only. A transient-event claim there means the KEYED
    action depends on the event; a distractor merely mentioning it (or a cautionary rationale)
    is testing judgment, not asserting the event — so those are deliberately not scanned."""
    return " ".join(o.text for o in item.options if o.answer_class in {"ideal", "acceptable"}).lower()


def _item_symptom(item: ClinicalCaseItem) -> str | None:
    """The item's symptom from the chip, else recovered from a stem synonym (round-3 audit:
    repair used to silently null an unmapped symptom like 'blackouts')."""
    sym = item.chips.symptom
    if sym and sym not in {"none", "asymptomatic"}:
        return sym
    blob = (item.stem + " " + " ".join(item.evidence_manifest.stem_adds)).lower()
    for phrase, canon in SYMPTOM_SYNONYMS.items():
        if phrase in blob:
            return canon
    return None


def acute_temporal(item: ClinicalCaseItem, packet: dict[str, Any], prior_packet: dict[str, Any] | None) -> CheckResult:
    stem_blob = _vignette_text(item)
    # Negation-aware: "no dynamic changes" / "without acute features" is the CHRONIC framing we want,
    # not an acute claim — only count a cue that is affirmatively asserted (round-3 false-positive fix).
    hits = [cue for cue in TEMPORAL_ACUITY_CUES if grounding.asserts_phrase(stem_blob, cue)]
    if not hits:
        return CheckResult("acute_temporal_causality", True)
    # Acceptable only with newness (a prior), an acute-dataset/serial token, or explicit evidence.
    blob = _manifest_blob(item)
    has_evidence = prior_packet is not None or any(tok in blob for tok in ACUTE_EVIDENCE_TOKENS)
    if has_evidence:
        return CheckResult("acute_temporal_causality", True)
    return CheckResult(
        "acute_temporal_causality",
        passed=False,
        hard_stop=True,
        messages=[
            f"Stem uses acute temporal language {hits} but the chronic tracing has no serial "
            f"change, acute-dataset provenance, or prior comparison to support acuity."
        ],
    )


def symptom_causality(item: ClinicalCaseItem, packet: dict[str, Any], prior_packet: dict[str, Any] | None) -> CheckResult:
    sym = _item_symptom(item)
    if not sym or sym in {"none", "asymptomatic"}:
        return CheckResult("symptom_causality", True)
    supported = grounding.supported_objectives(packet)
    relevant = [c for c in supported if c in SYMPTOM_CAUSALITY and sym in SYMPTOM_CAUSALITY[c]]
    if not relevant:
        return CheckResult("symptom_causality", True)  # no causality data → cannot judge
    explains = [c for c in relevant if SYMPTOM_CAUSALITY[c][sym] == "may_explain"]
    must_not = [c for c in relevant if SYMPTOM_CAUSALITY[c][sym] == "must_not_explain"]
    if must_not and not explains:
        # Does the item key an escalating ideal/acceptable action (treating it as causal)?
        keyed = [
            o for o in item.options
            if o.answer_class in {"ideal", "acceptable"}
            and any(cue in o.text.lower() for cue in _ESCALATION_CUES)
        ]
        if keyed:
            return CheckResult(
                "symptom_causality",
                passed=False,
                hard_stop=True,
                messages=[
                    f"Item keys an escalating action for '{sym}' but the supported finding(s) "
                    f"{must_not} must-not-explain '{sym}' without extra evidence "
                    f"(e.g. extreme PR / pauses / high-grade block / rhythm correlation)."
                ],
            )
    return CheckResult("symptom_causality", True)


def transient_event(item: ClinicalCaseItem, packet: dict[str, Any], prior_packet: dict[str, Any] | None) -> CheckResult:
    blob = _vignette_text(item) + " " + _keyed_option_text(item)
    hits = [cue for cue in TRANSIENT_EVENT_CUES if cue in blob]
    if not hits:
        return CheckResult("transient_event_evidence", True)
    manifest_blob = _manifest_blob(item)
    has_evidence = item.tested_scope == "rhythm_only" or any(
        tok in manifest_blob for tok in TRANSIENT_EVIDENCE_TOKENS
    )
    if has_evidence:
        return CheckResult("transient_event_evidence", True)
    return CheckResult(
        "transient_event_evidence",
        passed=False,
        hard_stop=True,
        messages=[
            f"Stem claims a transient event {hits} but a resting 12-lead provides no rhythm-strip / "
            f"telemetry / authored-data-layer evidence; do not grade it as ECG recognition."
        ],
    )
