"""§16B4 — the evidence-binding linter (cheapest, highest-value honesty check).

Every ``ecg_supports`` claim must bind to a curation objective the packet actually
supports, an evaluable measurement threshold, and (for a lead-localized finding) a
matching grounded ROI. Unbound territory/causal adjectives ("inferolateral",
"reciprocal", "territorial") in the stem/options are banned unless a matching ROI
backs them. Stops "non-specific ST-T" inflating into "inferolateral dynamic NSTEMI".
"""

from __future__ import annotations

import re
from typing import Any

from .. import grounding
from ..constants import (
    FEATURE_WORD_MAP,
    MEASUREMENT_CLAIM_RE,
    MI_DIAGNOSIS_CUES,
    PROSE_COMPARATORS,
    TERRITORY_CLAIM_CUES,
)
from ..schemas import ClinicalCaseItem
from .result import CheckResult


def check(item: ClinicalCaseItem, packet: dict[str, Any], prior_packet: dict[str, Any] | None) -> CheckResult:
    messages: list[str] = []
    supported = grounding.supported_objectives(packet)
    feats = grounding.features(packet)

    for idx, claim in enumerate(item.evidence_manifest.ecg_supports):
        tag = f"ecg_supports[{idx}] '{claim.objective_id}'"
        # 1. The claimed objective must be a curation-supported finding for this ECG.
        if claim.source_type in {"measured", "curated_label"} and claim.objective_id not in supported:
            messages.append(f"{tag}: not in the packet's supported_objectives.")
            continue
        if claim.source_type == "authored_context":
            messages.append(
                f"{tag}: source_type 'authored_context' does not belong in ecg_supports "
                f"(authored context goes in stem_adds)."
            )
            continue
        # 2. A measured claim must carry a threshold that actually holds against features.
        if claim.threshold:
            ok, reason = grounding.evaluate_threshold(claim.threshold, feats)
            if not ok:
                messages.append(f"{tag}: threshold '{claim.threshold}' unmet — {reason}.")
        elif claim.source_type == "measured":
            messages.append(f"{tag}: source_type 'measured' but no threshold to bind it to a feature.")
        # 3. A lead-localized territory claim needs a matching grounded ROI.
        if claim.leads and not grounding.has_territory_support(packet, claim.objective_id, claim.leads):
            messages.append(
                f"{tag}: claims leads {claim.leads} but no grounded ROI supports that territory."
            )

    # 4. Ban unbound territory/causal adjectives in the stem + option text.
    prose = " ".join(
        [item.stem, item.evidence_manifest.action_rationale, *[o.text for o in item.options]]
    ).lower()
    for cue in TERRITORY_CLAIM_CUES:
        if cue in prose:
            # Allowed only if some supported MI/ST concept has a grounded ROI in its territory.
            territory_concepts = [c for c in supported if c in grounding.TERRITORY_LEADS]
            backed = any(
                grounding.has_territory_support(packet, c, grounding.TERRITORY_LEADS[c])
                for c in territory_concepts
            )
            if not backed:
                messages.append(
                    f"Unbound territory/causal term '{cue}' in prose without a grounded territory ROI."
                )

    # 5. Diagnosis claims (OMI/occlusion MI/STEMI/territory infarct) must be supported findings —
    # a grounded ST-depression ROI does not license an "occlusion MI" diagnosis.
    for cue, concept in MI_DIAGNOSIS_CUES.items():
        if concept not in supported and grounding.asserts_phrase(prose, cue):
            messages.append(f"Prose asserts '{cue.strip()}' ({concept}) which is not a curation-supported finding.")

    return CheckResult("evidence_binding", passed=not messages, hard_stop=True, messages=messages)


def _measurement_holds(actual: float, op: str, value: float) -> bool:
    if op == ">":
        return actual > value
    if op == ">=":
        return actual >= value
    if op == "<":
        return actual < value
    if op == "<=":
        return actual <= value
    return abs(actual - value) <= max(0.15 * abs(value), 15)  # "~" approximate equality


def measurement_claim_binding(item: ClinicalCaseItem, packet: dict[str, Any], prior_packet: dict[str, Any] | None) -> CheckResult:
    """§round-3 audit (anti-laundering): a numeric measurement claim in ANY free text is EVALUATED
    against the tracing's real features — a true "rate of 140" passes, a laundered "PR over 300"
    (when it is 214) or a claim about a feature the tracing lacks is rejected."""
    feats = grounding.features(packet)
    texts = [item.stem, item.evidence_manifest.action_rationale, *item.evidence_manifest.stem_adds]
    texts += [o.text for o in item.options]
    messages: list[str] = []
    for text in texts:
        if not text:
            continue
        for m in MEASUREMENT_CLAIM_RE.finditer(text):
            key = FEATURE_WORD_MAP.get(m.group(1).lower())
            if not key:
                continue
            op = PROSE_COMPARATORS.get(m.group(2).lower(), "~")
            value = float(m.group(3))
            actual = feats.get(key)
            if actual is None:
                messages.append(f"Claim '{m.group(0).strip()}' references {key}, which this tracing does not provide.")
            elif not _measurement_holds(float(actual), op, value):
                messages.append(f"Claim '{m.group(0).strip()}' contradicts the tracing ({key}={actual}).")
    return CheckResult("measurement_claim_binding", passed=not messages, hard_stop=True, messages=list(dict.fromkeys(messages)))
