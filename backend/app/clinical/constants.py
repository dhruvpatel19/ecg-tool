"""Pilot numbers + canonical vocabularies for the Clinical Decisions mode.

Everything here is a tunable default (storyboard §16G) — clock seconds, credit
weights, and caps are starting points to be tuned by playtest, centralized so one
edit retunes the whole mode. The frozensets/tuples are canonical vocabularies the
schema + harness validate against.
"""

from __future__ import annotations

# --- §16D clock spec --------------------------------------------------------------
# (orient_sec, decide_sec) keyed by "situation:question_type"; "situation:*" is the
# lane default. Learn mode is untimed (handled in code, not here). Returned to the
# frontend per item so the timer is server-described, not hardcoded in two places.
CLOCK_SPEC: dict[str, tuple[int, int]] = {
    "clinic:*": (15, 90),
    "clinic:click": (20, 70),
    "*:oldnew": (20, 100),
    "ward:*": (10, 65),
    "ward:telemetry": (10, 50),
    "ed:*": (8, 37),
    "triage:*": (5, 12),
    "code:*": (5, 10),
}
DEFAULT_CLOCK: tuple[int, int] = (12, 60)
ACCOMMODATION_SCALE = 1.5  # generous scaled timers; scored separately, not as lower skill


def clock_for(situation: str, question_type: str) -> tuple[int, int]:
    """Resolve the (orient, decide) seconds for a lane + question type (§16D)."""
    for key in (f"{situation}:{question_type}", f"*:{question_type}", f"{situation}:*"):
        if key in CLOCK_SPEC:
            return CLOCK_SPEC[key]
    return DEFAULT_CLOCK


# --- §16C confidence upside-cap ---------------------------------------------------
# Low confidence caps max credit even when correct; high-confidence-wrong is penalized
# and flagged. Keyed by (correct?, confidence-band).
CONFIDENCE_CREDIT: dict[tuple[str, str], float] = {
    ("correct", "high"): 1.0,
    ("correct", "medium"): 0.85,
    ("correct", "low"): 0.65,
    ("wrong", "low"): 0.25,
    ("wrong", "medium"): 0.0,
    ("wrong", "high"): 0.0,
}
HIGH_CONF_WRONG = ("wrong", "high")  # flag this combination
# Avoidance: unjustified "cannot determine / insufficient data" caps credit (§16C).
UNJUSTIFIED_INSUFFICIENT_DATA_CAP = 0.40


def confidence_band(confidence: int | None) -> str:
    """Map a 1–5 confidence slider to low/medium/high bands."""
    if confidence is None:
        return "medium"
    if confidence <= 2:
        return "low"
    if confidence >= 4:
        return "high"
    return "medium"


# --- click matching ---------------------------------------------------------------
CLICK_TOLERANCE_MS = 80  # periodic ROI click tolerance (the prototype's value)

# --- acuity ordering (§16B6) ------------------------------------------------------
ACUITY_TIER_ORDER = ["none", "low", "moderate", "moderate_high", "high"]
ACTION_URGENCY_ORDER = ["routine", "workup", "admit", "urgent", "act_now"]


def acuity_rank(tier: str) -> int:
    return ACUITY_TIER_ORDER.index(tier) if tier in ACUITY_TIER_ORDER else 0


def urgency_rank(urgency: str) -> int:
    return ACTION_URGENCY_ORDER.index(urgency) if urgency in ACTION_URGENCY_ORDER else 0


# Map an acuity tier to the highest action urgency it can justify on its own. The
# content-table caps refine this per concept; this is the coarse tier→urgency floor.
ACUITY_TIER_MAX_URGENCY: dict[str, str] = {
    "none": "routine",
    "low": "workup",
    "moderate": "admit",
    "moderate_high": "urgent",
    "high": "act_now",
}


# --- canonical vocabularies -------------------------------------------------------
# Safety-action tokens an option/manifest may carry (§16B5). Closed set so typos in
# REQUIRED_SAFETY_ACTIONS / Option.required_safety_tokens are caught at import.
SAFETY_TOKENS = frozenset(
    {
        "pacing_pads",
        "tcp_ready",
        "defib_pads",
        "call_help",
        "bedside_now",
        "iv_access",
        "continuous_monitoring",
        "twelve_lead",
        "synchronized_cardioversion",
        "act_now",
        "atropine",
        "transvenous_pacing",
        "magnesium",
        "hold_qt_drugs",
        "check_electrolytes",
        "vagal_maneuver",
        "adenosine",
        "rate_control",
        "anticoagulation_assessment",
    }
)

# Symptoms a stem/chip may name (§16B2 keys). Closed so the causality matrix lookups
# never silently miss a typo'd symptom.
SYMPTOMS = frozenset(
    {
        "none",
        "asymptomatic",
        "chest_pain",
        "dizziness",
        "presyncope",
        "syncope",
        "palpitations",
        "lightheadedness",
        "dyspnea",
        "fatigue",
    }
)

# --- prose cue sets for the honesty checks ---------------------------------------
# Acute TEMPORAL language in a stem implies an evolving event a resting/chronic ECG
# cannot prove (§16B1). "new" alone is intentionally excluded — it is the legitimate
# answer in old-or-new items; we match "new-onset"/"new onset" instead.
TEMPORAL_ACUITY_CUES = (
    "acute onset",
    "acute-onset",
    "acutely",
    "escalating",
    "evolving",
    "ongoing chest",
    "dynamic st",
    "dynamic change",
    "dynamic ischemic",
    "serial change",
    "crushing",
    "diaphoresis",
    "diaphoretic",
    "rising troponin",
    "new-onset",
    "new onset",
    "hyperacute",
    "worsening",
    "sudden onset",
    "started 20 minutes ago",
    "minutes ago",
    # round-3 audit: common paraphrases that dodge the literal cues above. Keyword matching
    # is a stopgap — the durable fix is a structured symptom_onset/course field + extraction.
    "came on",
    "coming on",
    "started during",
    "started while",
    "since this morning",
    "since getting",
    "now spreading",
    "spreading to",
    "radiating",
    "radiates",
    "moving to",
    "moved to",
)
# Evidence that legitimizes acute temporal language (must be present somewhere).
ACUTE_EVIDENCE_TOKENS = ("serial", "prior comparison", "acute_dataset", "staff_iii", "telemetry")

# Territory/causal claim adjectives that need a matching-lead ROI to be defensible
# (§16B4). Bare "anterior/inferior/lateral" are allowed when that MI concept is
# supported; these compound/implied ones are not, on a chronic tracing, without ROI.
TERRITORY_CLAIM_CUES = (
    "territorial",
    "reciprocal",
    "inferolateral",
    "anterolateral",
    "anteroseptal infarct",
    "inferoposterior",
    # round-3 audit: territory/occlusion aliases that escaped the original list.
    "high-lateral",
    "high lateral",
    "lateral wall",
    "posterior infarct",
    "posterolateral",
    "occlusion mi",
    "occlusion myocardial",
    " omi",
    "right ventricular infarct",
    "rv infarct",
    "basal inferior",
)

# Diagnosis-claim cues → the concept they assert. If the prose asserts one and that concept
# is NOT in supported_objectives, it is an ungrounded diagnosis (round-3 audit: "high-lateral
# OMI" slipped past the territory-adjective check because some ST ROI existed).
MI_DIAGNOSIS_CUES: dict[str, str] = {
    "occlusion mi": "myocardial_infarction",
    " omi ": "myocardial_infarction",
    "occlusion myocardial": "myocardial_infarction",
    "stemi": "st_elevation",
    "nstemi": "myocardial_infarction",
    "anterior mi": "anterior_mi",
    "anterior infarct": "anterior_mi",
    "inferior mi": "inferior_mi",
    "inferior infarct": "inferior_mi",
    "lateral mi": "lateral_mi",
    "lateral infarct": "lateral_mi",
    "septal mi": "septal_mi",
    "septal infarct": "septal_mi",
    "posterior mi": "posterior_mi",
    "posterior infarct": "posterior_mi",
}

# Transient-event claims requiring rhythm-strip / telemetry evidence (§16B3).
TRANSIENT_EVENT_CUES = (
    "torsades",
    "vt run",
    "runs of",
    "nonsustained vt",
    "pause",
    "telemetry showed",
    "monitor showed",
    "captured",
    "syncopal episode on the monitor",
    # round-3 audit: transient-event aliases (also now scanned in options + rationale).
    "salvo",
    "burst",
    "self-terminating",
    "self terminating",
    "polymorphic",
    "near torsades",
    "twisting",
)
TRANSIENT_EVIDENCE_TOKENS = ("rhythm_strip", "telemetry", "authored_data_layer")


# --- round-3 audit: option action-urgency parsing -------------------------------
# Maps option text → an ACTION_URGENCY_ORDER level. Conservative: only unambiguously
# aggressive tokens raise the level, so a benign option defaults to "routine" and is
# never wrongly rejected. Closes "grounded ECG fact → ungrounded high-acuity action".
ACTION_URGENCY_CUES: dict[str, tuple[str, ...]] = {
    "act_now": (
        "icu", "critical care", "transvenous", "pacing pad", "pacer pad", "tcp",
        "cardiovert", "cardioversion", "cath lab", "activate cath", "defibrillat",
        "intubat", "central line", "vasopressor", "pressor", "magnesium for torsades",
    ),
    "urgent": ("urgent", "stat", "same-day", "same day", "emergent", "right now", "immediately"),
    "admit": ("admit", "telemetry", "monitored bed", "observation unit", "inpatient monitor"),
    "workup": ("repeat ecg", "repeat the ecg", "follow-up", "follow up", "outpatient", "echo", "holter", "electrolyte", "stress test"),
}


def parse_action_urgency(text: str) -> str:
    """Highest action-urgency level implied by an option's text (default 'routine').

    Word-boundary matched so a short cue ("icu") never matches inside a longer word
    ("medication"/"particular") — the substring bug that plagued the earlier cue lists."""
    lowered = (text or "").lower()
    for level in ("act_now", "urgent", "admit", "workup"):  # high → low
        for cue in ACTION_URGENCY_CUES[level]:
            if _re.search(r"\b" + _re.escape(cue) + r"\b", lowered):
                return level
    return "routine"


# Symptom synonyms so a stem's "blackouts"/"passed out" map to the causality vocabulary
# instead of being silently nulled (round-3 audit: symptom-null laundering).
SYMPTOM_SYNONYMS: dict[str, str] = {
    "blackout": "syncope", "blackouts": "syncope", "passed out": "syncope", "pass out": "syncope",
    "fainting": "syncope", "fainted": "syncope", "faint": "syncope", "loss of consciousness": "syncope",
    "collapse": "syncope", "collapsed": "syncope",
    "near-fainting": "presyncope", "nearly fainted": "presyncope", "almost passed out": "presyncope",
    "near syncope": "presyncope",
    "palpitation": "palpitations", "racing heart": "palpitations", "heart racing": "palpitations", "fluttering": "palpitations",
    "lightheaded": "lightheadedness", "light-headed": "lightheadedness", "light headed": "lightheadedness",
    "dizzy": "dizziness", "dizzy spells": "dizziness",
    "short of breath": "dyspnea", "shortness of breath": "dyspnea", "breathless": "dyspnea",
    "chest pressure": "chest_pain", "chest discomfort": "chest_pain", "chest tightness": "chest_pain", "chest pain": "chest_pain",
}


# --- round-3 audit: numeric/severity measurement-claim detection (anti-laundering) -
# A claim like "PR over 300 ms" or "markedly prolonged QT" in any free text must be backed
# by a validated measured threshold in ecg_supports; otherwise it is an unbound claim.
import re as _re

# feature word in prose → packet feature key
FEATURE_WORD_MAP: dict[str, str] = {
    "pr": "pr_ms", "qrs": "qrs_ms", "qtc": "qtc_ms", "qt": "qt_ms",
    "rate": "heart_rate", "heart rate": "heart_rate", "axis": "axis_deg",
}
# requires a comparator/abnormality word before the number, so plain descriptive values
# ("rate 118") are not flagged — only asserted abnormalities ("PR over 300", "QTc > 500").
# Captures (feature, comparator, number) so the claim can be EVALUATED against the packet's
# real features: a true "rate of 140" passes, a laundered "PR over 300" (actual 214) fails.
MEASUREMENT_CLAIM_RE = _re.compile(
    r"\b(pr|qrs|qtc|qt|rate|heart rate|axis)\b[^.\n]{0,18}?"
    r"(>=|<=|>|<|≥|≤|over|above|greater than|longer than|exceeds|under|below|less than|prolonged to|of|to)\s*(-?\d{1,4})",
    _re.I,
)
# prose comparator → operator; "~" = approximate equality (descriptive value, within tolerance).
PROSE_COMPARATORS: dict[str, str] = {
    ">": ">", ">=": ">=", "<": "<", "<=": "<=", "≥": ">=", "≤": "<=",
    "over": ">", "above": ">", "greater than": ">", "longer than": ">", "exceeds": ">",
    "under": "<", "below": "<", "less than": "<",
    "prolonged to": "~", "of": "~", "to": "~",
}
