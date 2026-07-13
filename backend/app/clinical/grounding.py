"""Read-only accessors over a grounded case packet, shared by the harness + grader.

The small concept→ROI / territory maps and the affirmative-assertion helper mirror
``app.llm`` (cross-referenced below). They are duplicated here deliberately so the
clinical harness has no import dependency on the tutor/LLM module; keep them in sync
if the llm.py versions change.
"""

from __future__ import annotations

import operator
import re
from typing import Any

# Mirrors app.llm._TERRITORY_LEADS — contiguous-lead territories.
TERRITORY_LEADS: dict[str, list[str]] = {
    "anterior_mi": ["V2", "V3", "V4", "V1"],
    "septal_mi": ["V2", "V1"],
    "lateral_mi": ["V5", "V6", "I", "aVL"],
    "inferior_mi": ["II", "III", "aVF"],
    "st_elevation": ["V2", "V5", "II"],
    "st_depression": ["V2", "V5", "II"],
}

# Mirrors app.llm._CONCEPT_TO_ROI — concept → the neutral segment ROI that anchors it.
CONCEPT_TO_ROI: dict[str, str] = {
    "qrs_duration": "qrs_complex",
    "right_bundle_branch_block": "qrs_complex",
    "left_bundle_branch_block": "qrs_complex",
    "nonspecific_intraventricular_conduction_delay": "qrs_complex",
    "left_ventricular_hypertrophy": "qrs_complex",
    "right_ventricular_hypertrophy": "qrs_complex",
    "wide_complex_tachycardia": "qrs_complex",
    "st_elevation": "st_segment",
    "st_depression": "st_segment",
    "nonspecific_st_t_change": "st_segment",
    "myocardial_infarction": "st_segment",
    "anterior_mi": "st_segment",
    "inferior_mi": "st_segment",
    "lateral_mi": "st_segment",
    "septal_mi": "st_segment",
    "posterior_mi": "st_segment",
    "myocardial_ischemia": "st_segment",
    "t_wave_inversion": "t_wave",
    "qt_interval": "qt_segment",
    "qtc_prolongation": "qt_segment",
    "av_block_first_degree": "pr_interval",
    "atrial_enlargement": "p_wave",
    "sinus_rhythm": "p_wave",
    "atrial_fibrillation": "p_wave",
    "atrial_flutter": "p_wave",
}


# --- packet accessors -------------------------------------------------------------
def supported_objectives(packet: dict[str, Any]) -> set[str]:
    return set(packet.get("supported_objectives") or [])


def features(packet: dict[str, Any]) -> dict[str, Any]:
    return (packet.get("ptbxl_plus") or {}).get("features") or {}


def rois(packet: dict[str, Any]) -> list[dict[str, Any]]:
    return ((packet.get("ptbxl_plus") or {}).get("fiducials") or {}).get("rois") or []


def roi_leads_for_concept(packet: dict[str, Any], roi_concept: str) -> set[str]:
    """Leads on which a given neutral ROI concept is grounded for this case."""
    return {r.get("lead") for r in rois(packet) if r.get("concept") == roi_concept}


def acceptable_roi_concepts(concept: str) -> set[str]:
    """ROI concept names that can anchor a clinical concept: the neutral segment ROI
    (real curated cases) AND the concept's own name (the synthetic fixtures key ROIs by
    pathology, e.g. 'right_bundle_branch_block')."""
    out = {concept}
    mapped = CONCEPT_TO_ROI.get(concept)
    if mapped:
        out.add(mapped)
    return out


def has_territory_support(packet: dict[str, Any], concept: str, claimed_leads: list[str]) -> bool:
    """True if the claimed leads for a territory concept have a matching grounded ROI."""
    grounded: set[str] = set()
    for roi_concept in acceptable_roi_concepts(concept):
        grounded |= roi_leads_for_concept(packet, roi_concept)
    if not CONCEPT_TO_ROI.get(concept) and concept not in {r.get("concept") for r in rois(packet)}:
        return True  # concept isn't lead-localized and has no ROI of its own; nothing to verify
    if not claimed_leads:
        return bool(grounded)
    return any(lead in grounded for lead in claimed_leads)


# --- threshold evaluation ---------------------------------------------------------
_COMPARATORS = [
    (">=", operator.ge),
    ("<=", operator.le),
    (">", operator.gt),
    ("<", operator.lt),
    ("==", operator.eq),
]
_THRESHOLD_RE = re.compile(r"^\s*([a-zA-Z_][\w]*)\s*(>=|<=|>|<|==)\s*(-?\d+(?:\.\d+)?)\s*$")


def evaluate_threshold(threshold: str, feats: dict[str, Any]) -> tuple[bool, str | None]:
    """Evaluate a "feature>=value" threshold against packet features.

    Returns (ok, reason_if_not_ok). Unparseable thresholds or missing/None features
    are treated as NOT satisfied (the claim is unbound) so the harness flags them.
    """
    match = _THRESHOLD_RE.match(threshold or "")
    if not match:
        return False, f"unparseable threshold '{threshold}'"
    key, comp, raw = match.group(1), match.group(2), match.group(3)
    if key not in feats or feats.get(key) is None:
        return False, f"feature '{key}' absent from packet"
    try:
        actual = float(feats[key])
    except (TypeError, ValueError):
        return False, f"feature '{key}' is non-numeric"
    op = dict(_COMPARATORS)[comp]
    if op(actual, float(raw)):
        return True, None
    return False, f"{key}={actual} fails {comp}{raw}"


# --- affirmative-assertion helper (mirrors app.llm._asserts_finding) --------------
_REFUSAL_CUES = (
    "no ", "not ", "n't", "without", "rule out", "ruled out", "evidence for",
    "don't have", "do not have", "won't", "cannot", "can't", "absent", "rather than",
    "no grounded", "unsupported", "isn't", "is not", "versus", "vs ", "instead of",
)


def asserts_phrase(text: str, cue: str) -> bool:
    """True if ``cue`` appears affirmatively (not inside a refusal/negation window)."""
    lowered = (text or "").lower()
    start = 0
    while True:
        idx = lowered.find(cue, start)
        if idx == -1:
            return False
        window = lowered[max(0, idx - 45): idx + len(cue) + 12]
        if not any(refusal in window for refusal in _REFUSAL_CUES):
            return True
        start = idx + len(cue)
