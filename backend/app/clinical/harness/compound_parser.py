"""§16A1 — compound-option parsing.

Splits each option into a get-more-data component and a safety-action component, so a
bundle ("insufficient data — get vitals/12-lead WHILE readying pads") is graded as a
bundle and never auto-tagged ``insufficient_data`` (the corrected Case W rule). Mutates
``option.parsed`` in place so the required-safety check can read the detected tokens.
"""

from __future__ import annotations

from typing import Any

from ..schemas import ClinicalCaseItem, ParsedComponents
from .result import CheckResult

# Text cues → canonical safety tokens (§16B5 vocabulary).
SAFETY_TOKEN_CUES: dict[str, list[str]] = {
    "pacing_pads": ["pacing pad", "pacer pad", "place pads", "pads on", "apply pads", "pads + "],
    "tcp_ready": [
        "transcutaneous pacing", "tcp", "pacing readiness", "ready pacing", "readying pads",
        "ready the pads", "prepare to pace", "prepare pacing", "pacing ready",
    ],
    "transvenous_pacing": ["transvenous pac"],
    "defib_pads": ["defib pad", "defibrillator pad"],
    "synchronized_cardioversion": ["synchronized cardioversion", "cardiovert", "cardioversion"],
    "call_help": [
        "call cardiology", "call cards", "call for help", "rapid response", "call the senior",
        "call senior", "consult cardiology", "activate", "call a code",
    ],
    "bedside_now": [
        "bedside assessment", "assess at the bedside", "check pulse", "check bp", "at the bedside",
        "see the patient", "go to the bedside", "check a pulse",
    ],
    "iv_access": ["iv access", "establish iv", "place an iv"],
    "continuous_monitoring": ["continuous monitor", "telemetry", "on the monitor", "keep on the monitor"],
    "twelve_lead": ["12-lead", "12 lead", "twelve-lead", "repeat ecg", "repeat the ecg"],
    "atropine": ["atropine"],
    "magnesium": ["magnesium", "iv mag"],
    "hold_qt_drugs": ["hold qt", "hold the offending", "stop the offending", "discontinue the offending"],
    "check_electrolytes": ["check electrolytes", "check potassium", "potassium", "electrolyte"],
    "vagal_maneuver": ["vagal", "valsalva", "carotid sinus massage"],
    "adenosine": ["adenosine"],
    "rate_control": ["rate control", "diltiazem", "iv metoprolol", "beta blocker", "beta-blocker"],
    "anticoagulation_assessment": ["anticoagulation", "anticoagulate", "chads"],
}

# Tokens that count as an active high-acuity *safety* action (for the bundle rule).
_SAFETY_ACTION_TOKENS = {
    "pacing_pads", "tcp_ready", "transvenous_pacing", "defib_pads",
    "synchronized_cardioversion", "call_help", "bedside_now", "magnesium", "adenosine",
}

GET_MORE_DATA_CUES = [
    "insufficient data", "insufficient information", "get vitals", "obtain vitals", "get more",
    "more information", "cannot determine", "need more", "check labs", "get labs", "troponin",
    "prior ecg", "old ecg", "compare with prior", "compare to prior", "get the prior",
]

DELAY_CUES = [
    "before deciding", "before escalat", "then decide", "reassess in", "wait for", "and reassess",
    "watch and wait", "observe overnight", "in the morning", "routine a.m", "routine am",
    "before further", "first, then",
]


def _detect_tokens(text: str) -> list[str]:
    lowered = (text or "").lower()
    found: list[str] = []
    for token, cues in SAFETY_TOKEN_CUES.items():
        if any(cue in lowered for cue in cues):
            found.append(token)
    return found


def parse_option_text(text: str) -> ParsedComponents:
    lowered = (text or "").lower()
    tokens = _detect_tokens(text)
    safety_action = any(t in _SAFETY_ACTION_TOKENS for t in tokens)
    get_more = any(cue in lowered for cue in GET_MORE_DATA_CUES)
    delayed = any(cue in lowered for cue in DELAY_CUES) and not safety_action
    return ParsedComponents(
        get_more_data=get_more,
        safety_action_present=safety_action,
        safety_tokens=tokens,
        action_delayed=delayed,
    )


def check(item: ClinicalCaseItem, packet: dict[str, Any], prior_packet: dict[str, Any] | None) -> CheckResult:
    messages: list[str] = []
    for option in item.options:
        # Author may precompute parsed; otherwise derive it (and persist for later checks).
        if option.parsed is None:
            option.parsed = parse_option_text(option.text)
        parsed = option.parsed
        # §16A1: a bundle (get-more-data + a parallel, non-delayed safety action) must NOT
        # be tagged insufficient_data — that is the high-credit Case W answer, not low-credit.
        if (
            option.answer_class == "insufficient_data"
            and parsed.safety_action_present
            and not parsed.action_delayed
        ):
            messages.append(
                f"Option '{option.id}' is tagged insufficient_data but bundles a parallel safety "
                f"action ({', '.join(parsed.safety_tokens)}); per §16A1 it should be ideal/acceptable."
            )
    return CheckResult("compound_option_parsing", passed=not messages, hard_stop=True, messages=messages)
