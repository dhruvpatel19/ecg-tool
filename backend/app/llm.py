"""Grounded, multi-turn, tool-using ECG tutor.

Providers return schema-validated structured JSON (message + viewer actions +
objective updates). The tutor never invents diagnoses/measurements/ROIs: it is
given a grounded case packet (allowed/forbidden claims, real measurements, parsed
ROIs) and conversation history, and may only explain, quiz, and recommend viewer
actions. The enhanced MockProvider supports the full demo flow without an API key;
the OpenAI-compatible provider serves real (cheap) models via env config.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any, Protocol

from .config import Settings
from .coordinates import clamp_action_to_case
from .ontology import concept_label
from .schemas import (
    TUTOR_MESSAGE_MAX_CHARS,
    TutorChatRequest,
    TutorResponse,
    validate_tutor_response,
)


logger = logging.getLogger(__name__)

# Concept cues for the deterministic mock to detect what the learner is asking about.
_CONCEPT_CUES: dict[str, list[str]] = {
    "st_elevation": ["st elevation", "stemi", "elevated st"],
    "st_depression": ["st depression"],
    "t_wave_inversion": ["t wave inversion", "inverted t"],
    "myocardial_infarction": ["mi", "infarct", "infarction"],
    "anterior_mi": ["anterior"],
    "inferior_mi": ["inferior"],
    "qt_interval": ["qt", "qtc"],
    "qtc_prolongation": ["long qt", "prolonged qt"],
    "pr_ms": ["pr interval", "pr segment"],
    "av_block_first_degree": ["av block", "first degree", "heart block"],
    "axis_normal": ["axis"],
    "left_axis_deviation": ["left axis"],
    "right_axis_deviation": ["right axis"],
    "right_bundle_branch_block": ["rbbb", "right bundle"],
    "left_bundle_branch_block": ["lbbb", "left bundle"],
    "wide_complex_tachycardia": ["wide complex tachycardia", "wide-complex tachycardia", "ventricular tachycardia", " wct", " vt"],
    "qrs_duration": ["qrs", "wide complex", "bundle"],
    "left_ventricular_hypertrophy": ["lvh", "hypertrophy", "voltage"],
    "atrial_fibrillation": ["afib", "atrial fibrillation", "irregular"],
    "sinus_rhythm": ["sinus", "rhythm", "p wave", "p activity", "atrial activity"],
    "rate": ["rate", "bradycardia", "tachycardia", "heart rate"],
    "normal_ecg": ["normal"],
}

_MEASUREMENT_LABELS = {
    "heart_rate": ("heart rate", "bpm"),
    "pr_ms": ("PR interval", "ms"),
    "qrs_ms": ("QRS duration", "ms"),
    "qt_ms": ("QT interval", "ms"),
    "qtc_ms": ("QTc", "ms"),
    "axis_deg": ("frontal axis", "°"),
}


class LLMProvider(Protocol):
    def generate(self, messages: list[dict[str, Any]], context: dict[str, Any]) -> str: ...


class ProviderOutput(str):
    """String-compatible provider output with concurrency-safe call telemetry."""

    provider_status: str

    def __new__(cls, value: str, provider_status: str):
        instance = super().__new__(cls, value)
        instance.provider_status = provider_status
        return instance


# --- shared grounding helpers ---------------------------------------------------


def _measurements_summary(case: dict[str, Any]) -> list[str]:
    features = ((case.get("ptbxl_plus") or {}).get("features") or {})
    out: list[str] = []
    for key, (label, unit) in _MEASUREMENT_LABELS.items():
        value = features.get(key)
        if isinstance(value, (int, float)):
            out.append(f"{label} {value:g} {unit}".strip())
    return out


def _rois(case: dict[str, Any]) -> list[dict[str, Any]]:
    return ((case.get("ptbxl_plus") or {}).get("fiducials") or {}).get("rois") or []


def _supported(case: dict[str, Any]) -> list[str]:
    return case.get("supported_objectives", []) or []


def _detect_concepts(text: str) -> list[str]:
    lowered = (text or "").lower()
    hits: list[str] = []
    for concept, cues in _CONCEPT_CUES.items():
        if any(re.search(r"(?<![a-z])" + re.escape(cue.strip()) + r"(?![a-z])", lowered) for cue in cues):
            hits.append(concept)
    return hits


_GENERAL_QUESTION_CUES = (
    "how do i", "how can i", "how does", "what is", "what does", "why does", "why is",
    "difference between", "distinguish", "in general", "does it always", "can it",
    "explain", "teach me", "when do", "if the",
)
_CASE_SPECIFIC_PATTERN = re.compile(
    r"\b(?:this|current|displayed)\s+(?:ecg|ekg|tracing|trace|case)\b"
    r"|\bon\s+this\b|\bdoes\s+this\b|\bthis\s+looks\b|\bselected\s+point\b"
    r"|\bthis\s+(?:is|has|shows|demonstrates)\b"
    r"|\bshow\s+me\s+on\s+(?:this|the\s+current|the\s+displayed)\b|\bhere\b"
)


def _is_general_concept_question(text: str) -> bool:
    lowered = (text or "").lower()
    # Match actual deictic phrases, not raw substrings: "here" must not match
    # "where", and merely naming "lead V1" does not make an explicitly general
    # teaching question a claim about the ECG on screen.
    if _CASE_SPECIFIC_PATTERN.search(lowered):
        return False
    return any(cue in lowered for cue in _GENERAL_QUESTION_CUES)


def _curated_process_teaching(text: str) -> tuple[str, list[str]] | None:
    """Deterministic novice explanations for sequence/physiology questions."""
    lowered = (text or "").lower()
    if (
        "rate" in lowered
        and "rhythm" in lowered
        and any(cue in lowered for cue in ("before", "sequence", "systematic", "order", "fit"))
    ):
        return (
            "In a systematic ECG read, estimate rate before naming the rhythm. Rate narrows the rhythm possibilities "
            "and changes how you interpret regularity and intervals; next assess regularity, identify atrial activity, "
            "and determine how each P wave relates to each QRS complex.",
            ["rate", "sinus_rhythm"],
        )
    if (
        any(cue in lowered for cue in ("p wave", "p activity", "atrial activity", "atrial depolarization"))
        and "qrs" in lowered
        and any(cue in lowered for cue in ("why", "before", "preced", "physiolog"))
    ):
        return (
            "Atrial depolarization produces the P wave first. The impulse then pauses through the AV node, represented "
            "within the PR interval, before ventricular depolarization produces the QRS complex; that P-to-QRS sequence "
            "is the physiology you test, while a P wave by itself does not prove sinus rhythm.",
            ["sinus_rhythm", "qrs_duration"],
        )
    return None


_GENERAL_TEACHING: dict[str, str] = {
    "rate": (
        "Estimate rate early in the systematic sequence because it narrows rhythm possibilities and affects interval "
        "interpretation; then assess regularity and the atrial-to-ventricular relationship."
    ),
    "sinus_rhythm": (
        "Atrial depolarization normally creates a P wave before AV-nodal delay and ventricular depolarization creates "
        "the QRS; verify a consistent P-before-QRS relationship rather than treating any P wave as proof of sinus rhythm."
    ),
    "t_wave_inversion": (
        "T-wave inversion is a descriptive repolarization finding, not a diagnosis by itself. "
        "Its significance depends on which leads are involved, the shape and depth, whether it is new or dynamic, "
        "the QRS pattern, and the clinical context; ischemia is one possibility among several."
    ),
    "wide_complex_tachycardia": (
        "Wide-complex tachycardia describes what you see—a fast rhythm with broad QRS complexes—and ventricular "
        "tachycardia (VT) is one major cause, not an opposing category. Assess clinical stability first, then regularity "
        "and QRS morphology; compare with a baseline and look for AV dissociation (atria and ventricles acting independently) "
        "or capture/fusion beats (occasional differently shaped beats). Other mechanisms include a supraventricular rhythm "
        "with bundle delay or pre-excitation, and unresolved uncertainty should keep VT prominent."
    ),
    "right_bundle_branch_block": (
        "RBBB reasoning combines QRS duration with terminal rightward forces: inspect V1 for a compatible terminal positive pattern "
        "and lateral leads for a broad terminal S wave. Width alone or an rSr′ in V1 alone is not enough."
    ),
    "left_bundle_branch_block": (
        "LBBB reflects delayed left-ventricular activation: look for a broad predominantly negative QRS in V1 and a broad/notched "
        "lateral R pattern, with secondary ST–T discordance. Duration and morphology must agree."
    ),
    "qt_interval": (
        "Measure QT from QRS onset to T-wave end in a clear lead and across more than one beat. QT varies with rate, so state the "
        "correction method; Bazett and Fridericia can diverge at rate extremes, and a wide QRS can lengthen QT through depolarization."
    ),
    "qtc_prolongation": (
        "A prolonged QTc is a measured risk clue, not a stand-alone prediction of torsades. Verify the T-wave end, rate correction, "
        "QRS width, medications, interactions, electrolytes, and clinical context."
    ),
    "atrial_fibrillation": (
        "AF is supported by absent consistent organized P waves plus an irregularly irregular ventricular response. Frequent ectopy, "
        "flutter with variable block, and artifact are important mimics, so use both atrial and R–R evidence."
    ),
    "myocardial_infarction": (
        "An ECG pattern can raise concern for infarction, but acuity and patient diagnosis require symptoms, comparison/serial change, "
        "biomarkers, and context. Start by describing contiguous and reciprocal lead findings rather than jumping from one feature to a label."
    ),
}


# Contiguous-lead territories (ordered by preference among the leads we parse: II, V2, V5).
_TERRITORY_LEADS = {
    "anterior_mi": ["V2", "V3", "V4", "V1"],
    "septal_mi": ["V2", "V1"],
    "lateral_mi": ["V5", "V6", "I", "aVL"],
    "inferior_mi": ["II", "III", "aVF"],
    "st_elevation": ["V2", "V5", "II"],
    "st_depression": ["V2", "V5", "II"],
    # Frontal QRS axis is reasoned from limb-lead QRS polarity. Lead II is a
    # useful refinement near the left-axis boundary; precordial P-wave ROIs are
    # never axis evidence.
    "axis_normal": ["I", "aVF", "II"],
    "left_axis_deviation": ["I", "aVF", "II"],
    "right_axis_deviation": ["I", "aVF", "II"],
}


# Map a clinical concept to the neutral segment-location ROI that anchors it.
_CONCEPT_TO_ROI = {
    "qrs_duration": "qrs_complex", "right_bundle_branch_block": "qrs_complex",
    "left_bundle_branch_block": "qrs_complex", "nonspecific_intraventricular_conduction_delay": "qrs_complex",
    "left_ventricular_hypertrophy": "qrs_complex", "right_ventricular_hypertrophy": "qrs_complex",
    "st_elevation": "st_segment", "st_depression": "st_segment", "nonspecific_st_t_change": "st_segment",
    "myocardial_infarction": "st_segment", "anterior_mi": "st_segment", "inferior_mi": "st_segment",
    "lateral_mi": "st_segment", "septal_mi": "st_segment", "posterior_mi": "st_segment",
    "t_wave_inversion": "t_wave",
    "qt_interval": "qt_segment", "qtc_prolongation": "qt_segment",
    "av_block_first_degree": "pr_interval",
    "atrial_enlargement": "p_wave", "sinus_rhythm": "p_wave", "atrial_fibrillation": "p_wave",
    "atrial_flutter": "p_wave",
    "axis_normal": "qrs_complex", "left_axis_deviation": "qrs_complex",
    "right_axis_deviation": "qrs_complex",
}

_AXIS_CONCEPTS = {"axis_normal", "left_axis_deviation", "right_axis_deviation"}


def _roi_for_concept(
    case: dict[str, Any], concept: str | None, viewer_state: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    rois = _rois(case)
    if not rois:
        return None
    roi_concept = _CONCEPT_TO_ROI.get(concept) if concept else None
    if roi_concept:
        matching = [roi for roi in rois if roi.get("concept") == roi_concept]
        if matching:
            selected = (viewer_state or {}).get("selectedPoint") or {}
            selected_lead = selected.get("lead") if isinstance(selected, dict) else None
            selected_time = selected.get("timeSec") if isinstance(selected, dict) else None
            same_lead = [roi for roi in matching if roi.get("lead") == selected_lead]
            if same_lead:
                if isinstance(selected_time, (int, float)):
                    return min(
                        same_lead,
                        key=lambda roi: abs(
                            (float(roi.get("timeStartSec", 0)) + float(roi.get("timeEndSec", 0))) / 2
                            - float(selected_time)
                        ),
                    )
                return same_lead[0]
            # Territory preference (anterior->V2, lateral->V5, inferior->II) for ST/MI.
            for preferred_lead in _TERRITORY_LEADS.get(concept, []):
                for roi in matching:
                    if roi.get("lead") == preferred_lead:
                        return roi
            return matching[0]
    return rois[0]


def _action_from_roi(roi: dict[str, Any], duration: float) -> list[dict[str, Any]]:
    return [
        {
            "type": "highlightROI",
            "lead": roi["lead"],
            "timeStart": roi["timeStartSec"],
            "timeEnd": roi["timeEndSec"],
            "ampMin": roi["ampMinMv"],
            "ampMax": roi["ampMaxMv"],
            "label": roi["label"],
        },
        {
            "type": "zoom",
            "leads": [roi["lead"]],
            "timeStart": max(0.0, roi["timeStartSec"] - 0.6),
            "timeEnd": min(duration, roi["timeEndSec"] + 0.7),
        },
    ]


# A neutral "show me the <component>" request is about ECG ANATOMY, not a diagnostic
# claim — it must point at that component's segment ROI (present on every tracing) and
# must NOT raise an unsupported-finding warning. V1 audit: "Show me the QRS complex"
# wrongly warned about unsupported QRS duration and highlighted the P wave. Cues match
# component NOUNS ("ST segment"), not pathology ("ST elevation"). Keyed to the neutral
# fiducial ROI concepts from ingest/fiducials.py.
_NEUTRAL_ANATOMY: dict[str, list[str]] = {
    "p_wave": ["p wave", "p-wave"],
    "pr_interval": ["pr interval", "pr segment"],
    "qrs_complex": ["qrs complex", "qrs-complex", "qrs morphology", "the qrs", "qrs"],
    "st_segment": ["st segment", "st-segment", "j point", "j-point"],
    "t_wave": ["t wave", "t-wave"],
    "qt_segment": ["qt interval", "qt-interval", "qt segment"],
}
_COMPONENT_LABEL = {
    "p_wave": "P wave", "pr_interval": "PR interval", "qrs_complex": "QRS complex",
    "st_segment": "ST segment", "t_wave": "T wave", "qt_segment": "QT interval",
}
_LOCATE_VERBS = ("show", "point", "where", "find", "highlight", "indicate", "locate", "look at", "see the")


def _detect_neutral_anatomy(text: str) -> str | None:
    """Return the neutral ROI concept the learner asked to be *shown* (anatomy), or None.

    Requires a locate verb so it does not fire on diagnostic discussion, and matches
    component nouns ("ST segment"), never pathology phrases ("ST elevation").
    """
    lowered = (text or "").lower()
    if not any(verb in lowered for verb in _LOCATE_VERBS):
        return None
    for roi_concept, cues in _NEUTRAL_ANATOMY.items():
        if any(cue in lowered for cue in cues):
            return roi_concept
    return None


def _neutral_roi(case: dict[str, Any], roi_concept: str) -> dict[str, Any] | None:
    matching = [roi for roi in _rois(case) if roi.get("concept") == roi_concept]
    if not matching:
        return None
    for preferred_lead in ("II", "V2", "V5"):
        for roi in matching:
            if roi.get("lead") == preferred_lead:
                return roi
    return matching[0]


# --- providers ------------------------------------------------------------------


class MockProvider:
    """Deterministic, grounded tutor for keyless local use and CI.

    Responds to the learner's actual question, cites real packet evidence, refuses
    findings absent from the packet, and asks a Socratic follow-up in tutorials.
    """

    def generate(self, messages: list[dict[str, Any]], context: dict[str, Any]) -> str:
        case = context.get("casePacket") or {}
        mode = context.get("mode", "freeform")
        lesson = context.get("lesson") or {}
        learner_message = ""
        for message in reversed(messages):
            if message.get("role") == "user":
                learner_message = message.get("content", "")
                break

        supported = _supported(case)
        measurements = _measurements_summary(case)
        asked = _detect_concepts(learner_message)
        duration = float((case.get("waveform") or {}).get("duration_sec", 10))
        viewer_state = context.get("viewerState") or {}

        if viewer_state.get("activity") == "adaptive_mastery_plan":
            primary = viewer_state.get("primary") if isinstance(viewer_state.get("primary"), dict) else None
            stages = viewer_state.get("prescribedStages") if isinstance(viewer_state.get("prescribedStages"), list) else []
            explanation = str(viewer_state.get("explanation") or "The verified scheduler has not supplied an explanation.")
            if primary:
                target = f"{primary.get('label') or primary.get('concept')} · {str(primary.get('subskill') or '').replace('_', ' ')}"
                reason = str(primary.get("reason") or explanation)
                first_stage = stages[0] if stages and isinstance(stages[0], dict) else {}
                if any(cue in learner_message.lower() for cue in ("why", "first", "priority", "priorit")):
                    message = f"{target} comes first because {reason[:1].lower() + reason[1:] if reason else explanation}"
                elif any(cue in learner_message.lower() for cue in ("durable", "improve", "move", "mastery", "evidence")):
                    message = (
                        f"For {target}, the next useful evidence is an independent answer on a new eligible ECG, followed by spaced retrieval and morphology diversity. "
                        "Hints and coached explanations remain formative; the verified scheduler, not this chat, decides when evidence is durable."
                    )
                else:
                    message = (
                        f"The verified queue currently anchors on {target}. {reason} "
                        f"Start with {first_stage.get('title') or 'the first prescribed stage'}, then keep the same discriminator in the later transfer stage."
                    )
                cited = [reason, explanation]
            else:
                message = (
                    "No independent baseline is recorded yet, so the verified plan starts with an untimed mixed read. "
                    "That establishes evidence before focused remediation; this coach will not guess a weakness from an empty record."
                )
                first_stage = stages[0] if stages and isinstance(stages[0], dict) else {}
                cited = [explanation]
            return json.dumps({
                "tutorMessage": message,
                "feedback": "This explanation uses the server-issued plan summary; the deterministic scheduler remains authoritative.",
                "viewerActions": [],
                "objectiveUpdates": [],
                "misconceptions": [],
                "uncertaintyWarnings": ["The plan coach cannot score work, alter the queue, or create ECG ground truth."],
                "suggestedNextStep": str(first_stage.get("title") or "Open the first prescribed stage."),
                "socraticQuestion": "What discriminator will you carry from focused practice into the mixed transfer read?",
                "citedEvidence": [item for item in cited if item][:3],
                "onLessonTopic": True,
            })

        # Axis is a ventricular-depolarization measurement. Handle it before
        # neutral anatomy so a challenge such as "why is the P wave evidence
        # for axis; show the correct evidence" cannot be misread as a request
        # to highlight a P wave.
        axis_asks = [concept for concept in asked if concept in _AXIS_CONCEPTS]
        if axis_asks:
            supported_axis = next((concept for concept in axis_asks if concept in supported), None)
            packet_axis = next((concept for concept in supported if concept in _AXIS_CONCEPTS), None)
            return self._axis_response(case, supported_axis or packet_axis or axis_asks[0], mode, duration)

        # A general educational tangent is not an assertion about the current case.
        # Answer it, label the epistemic boundary, and preserve a return waypoint;
        # do not reject it merely because this packet lacks that diagnosis.
        process_teaching = _curated_process_teaching(learner_message)
        if process_teaching and _is_general_concept_question(learner_message):
            teaching, process_concepts = process_teaching
            lesson_objectives = set(lesson.get("objectives") or [])
            return json.dumps(
                {
                    "tutorMessage": teaching,
                    "feedback": "That is general ECG process/physiology teaching, not a claim about the current tracing.",
                    "viewerActions": [],
                    "objectiveUpdates": [],
                    "misconceptions": [],
                    "uncertaintyWarnings": ["General concept explanation; current-case evidence was not asserted."],
                    "suggestedNextStep": (viewer_state.get("pausedWaypoint") or "Return to the paused lesson checkpoint."),
                    "socraticQuestion": "How would you apply that sequence at the paused checkpoint?",
                    "citedEvidence": ["Versioned ECG concept graph; not current-case evidence"],
                    "onLessonTopic": any(concept in lesson_objectives for concept in process_concepts),
                }
            )
        if asked and _is_general_concept_question(learner_message):
            teaching = [_GENERAL_TEACHING[concept] for concept in asked if concept in _GENERAL_TEACHING]
            if teaching:
                lesson_objectives = set(lesson.get("objectives") or [])
                on_topic = any(concept in lesson_objectives for concept in asked)
                return json.dumps(
                    {
                        "tutorMessage": " ".join(teaching[:2]),
                        "feedback": "That is general ECG teaching, not a claim that the current tracing has the finding.",
                        "viewerActions": [],
                        "objectiveUpdates": [],
                        "misconceptions": [],
                        "uncertaintyWarnings": ["General concept explanation; current-case evidence was not asserted."],
                        "suggestedNextStep": (viewer_state.get("pausedWaypoint") or "Return to the paused lesson checkpoint."),
                        "socraticQuestion": "Which discriminator would you look for first on an actual tracing?",
                        "citedEvidence": ["Versioned ECG concept graph; not current-case evidence"],
                        "onLessonTopic": on_topic,
                    }
                )

        # Neutral "show me the <component>" request: point at the waveform component
        # itself (anatomy), never raise an unsupported-finding warning.
        neutral_concept = _detect_neutral_anatomy(learner_message)
        if neutral_concept:
            return self._anatomy_response(case, neutral_concept, mode, duration)

        on_topic = True
        warnings: list[str] = []
        cited: list[str] = []
        actions: list[dict[str, Any]] = []

        # Concept the response should anchor on.
        focus_concept = None
        for concept in asked:
            if concept in supported:
                focus_concept = concept
                break
        unsupported_ask = [c for c in asked if c not in supported and c in _CONCEPT_CUES]
        if focus_concept is None and supported:
            focus_concept = lesson.get("caseConcept") if lesson.get("caseConcept") in supported else supported[0]

        if focus_concept in _AXIS_CONCEPTS:
            return self._axis_response(case, focus_concept, mode, duration)

        roi = _roi_for_concept(case, focus_concept, viewer_state)
        if roi:
            actions = _action_from_roi(roi, duration)
            cited.append(f"{roi['label']} ROI in lead {roi['lead']}")

        parts: list[str] = []
        # ALWAYS surface findings the learner asked about that aren't grounded in the
        # packet — even when the case has some other supported concept (V1 audit:
        # previously this only fired when nothing was supported, so probes for an
        # unsupported finding got a silent topic-switch).
        if unsupported_ask:
            names = ", ".join(concept_label(c) for c in unsupported_ask[:2])
            parts.append(
                f"I don't have grounded evidence for {names} in this case packet, so I won't claim it — "
                "curation keeps unsupported findings out rather than guessing."
            )
            warnings.append(f"No grounded evidence for: {names}.")
            if mode == "tutorial":
                on_topic = False

        if focus_concept:
            lead_in = "Here, " if unsupported_ask else "Let's "
            parts.append(f"{lead_in}reason about {concept_label(focus_concept)} using what the case packet supports.")
            if roi:
                parts.append(
                    f"I've highlighted the {roi['label']} in lead {roi['lead']} "
                    f"({roi['timeStartSec']:.2f}–{roi['timeEndSec']:.2f}s) as the visual anchor."
                )
        elif not unsupported_ask:
            parts.append("Start with a systematic read: rate, rhythm, axis, intervals, QRS, ST-T, then synthesis.")

        if measurements:
            shown = "; ".join(measurements[:4])
            parts.append(f"Grounded measurements you may cite: {shown}.")
            cited.extend(measurements[:4])

        socratic = ""
        if mode == "tutorial" and lesson:
            objective = (lesson.get("objectives") or [focus_concept or "the read"])[0]
            socratic = f"Looking at the highlighted evidence, what feature confirms or excludes {concept_label(objective)}?"

        response = {
            "tutorMessage": " ".join(parts),
            "feedback": "Tie each claim to a specific lead, interval, or measurement; name what stays uncertain.",
            "viewerActions": actions,
            "objectiveUpdates": [],
            "misconceptions": [],
            "uncertaintyWarnings": warnings,
            "suggestedNextStep": socratic or "Name the finding and cite the lead or measurement that supports it.",
            "socraticQuestion": socratic,
            "citedEvidence": cited[:6],
            "onLessonTopic": on_topic,
        }
        return json.dumps(response)

    def _axis_response(
        self, case: dict[str, Any], focus_concept: str, mode: str, duration: float
    ) -> str:
        """Explain QRS axis only from frontal-axis measurement/QRS evidence.

        Fiducial ROIs identify where a complex is, not its net polarity. They
        are therefore useful visual anchors but never substitutes for the
        packet's measured frontal QRS axis.
        """
        features = ((case.get("ptbxl_plus") or {}).get("features") or {})
        axis_deg = features.get("axis_deg")
        has_axis_measurement = isinstance(axis_deg, (int, float))
        qrs_rois = [roi for roi in _rois(case) if roi.get("concept") == "qrs_complex"]
        ordered: list[dict[str, Any]] = []
        for lead in ("I", "aVF", "II"):
            roi = next((candidate for candidate in qrs_rois if candidate.get("lead") == lead), None)
            if roi is not None:
                ordered.append(roi)
        if not ordered and qrs_rois:
            ordered.append(qrs_rois[0])

        actions: list[dict[str, Any]] = []
        cited: list[str] = []
        for roi in ordered[:2]:
            actions.append(
                {
                    "type": "highlightROI",
                    "lead": roi["lead"],
                    "timeStart": roi["timeStartSec"],
                    "timeEnd": roi["timeEndSec"],
                    "ampMin": roi["ampMinMv"],
                    "ampMax": roi["ampMaxMv"],
                    "label": f"QRS axis evidence · lead {roi['lead']}",
                }
            )
            cited.append(f"QRS complex ROI in limb lead {roi['lead']}")

        if has_axis_measurement:
            cited.insert(0, f"frontal QRS axis {float(axis_deg):g} °")
            message = (
                f"The packet's measured frontal QRS axis is {float(axis_deg):g}°. "
                "QRS axis comes from ventricular depolarization: compare net QRS polarity in limb leads I and aVF, "
                "using lead II to refine a borderline leftward axis. P-wave morphology is atrial evidence and does "
                "not support a QRS-axis claim."
            )
            if ordered:
                message += (
                    " The highlighted QRS complexes show where to inspect; the segment ROIs locate the complexes "
                    "but do not by themselves encode net polarity."
                )
            warnings: list[str] = []
        else:
            message = (
                "P-wave morphology does not support a QRS-axis claim. This packet has no numeric frontal QRS-axis "
                "measurement, so I cannot substantiate the axis label from a segment-location ROI alone. On a "
                "12-lead, compare net QRS polarity in leads I and aVF and use lead II for a borderline leftward axis."
            )
            warnings = ["No numeric frontal QRS-axis measurement is present in this case packet."]

        socratic = (
            "What are the net QRS polarities in leads I and aVF, and does the measured axis agree?"
            if mode == "tutorial"
            else ""
        )
        return json.dumps(
            {
                "tutorMessage": message,
                "feedback": "Use ventricular QRS evidence for QRS axis; keep atrial P-wave evidence separate.",
                "viewerActions": actions,
                "objectiveUpdates": [],
                "misconceptions": ["P-wave morphology was treated as evidence for frontal QRS axis."],
                "uncertaintyWarnings": warnings,
                "suggestedNextStep": socratic or "Compare net QRS polarity in leads I and aVF.",
                "socraticQuestion": socratic,
                "citedEvidence": cited,
                "onLessonTopic": True,
            }
        )

    def _anatomy_response(self, case: dict[str, Any], roi_concept: str, mode: str, duration: float) -> str:
        """Grounded response to a neutral 'show me the <component>' request: highlight
        the component's segment ROI, no diagnostic claim, no unsupported-finding warning."""
        roi = _neutral_roi(case, roi_concept)
        label = _COMPONENT_LABEL.get(roi_concept, roi_concept.replace("_", " "))
        actions = _action_from_roi(roi, duration) if roi else []
        cited = [f"{roi['label']} ROI in lead {roi['lead']}"] if roi else []
        if roi:
            message = (
                f"Here's the {label} in lead {roi['lead']} "
                f"({roi['timeStartSec']:.2f}–{roi['timeEndSec']:.2f}s) — I've highlighted and zoomed to it. "
                "That's the segment location on this tracing; describe what you see there."
            )
        else:
            message = (
                f"This case's parsed landmarks don't separately mark the {label}, but on a 12-lead it sits in "
                "its usual place in the cardiac cycle — walk the complex left to right to locate it."
            )
        socratic = (
            f"Looking at the {label}, what stands out about its shape, duration, or position?"
            if mode == "tutorial"
            else ""
        )
        response = {
            "tutorMessage": message,
            "feedback": "Anchor each observation to the lead and the segment you are looking at.",
            "viewerActions": actions,
            "objectiveUpdates": [],
            "misconceptions": [],
            "uncertaintyWarnings": [],
            "suggestedNextStep": socratic or f"Describe the {label} you see, then ask about the next component.",
            "socraticQuestion": socratic,
            "citedEvidence": cited,
            "onLessonTopic": True,
        }
        return json.dumps(response)


class OpenAICompatibleProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    def generate(self, messages: list[dict[str, Any]], context: dict[str, Any], system_prompt: str | None = None) -> str:
        if not self.settings.llm_api_key:
            return ProviderOutput(json.dumps(
                {
                    "tutorMessage": "OpenAI-compatible provider is configured, but no LLM_API_KEY is set.",
                    "feedback": "Set LLM_API_KEY server-side or use LLM_PROVIDER=mock.",
                    "viewerActions": [],
                    "uncertaintyWarnings": ["Missing API key; no remote call was made."],
                    "suggestedNextStep": "Use mock mode for local verification.",
                }
            ), "not_configured")
        base_url = (self.settings.llm_base_url or "https://api.openai.com/v1").rstrip("/")
        prompt_context = dict(context)
        safety_identifier = prompt_context.pop("_safetyIdentifier", None)
        if context.get("casePacket"):
            prompt_context["casePacket"] = _packet_for_llm(context["casePacket"])
        chat_messages = [{"role": "system", "content": system_prompt or SYSTEM_PROMPT}]
        chat_messages.append({"role": "system", "content": "GROUNDED CONTEXT:\n" + json.dumps(prompt_context, default=str)})
        chat_messages.extend({"role": m["role"], "content": m["content"]} for m in messages)
        request_payload = {
            # Keep the model configurable so deployment access can be changed
            # without code edits. GPT-5.6 Luna is the requested high-volume tutor
            # model; provider failures remain grounded and non-destructive.
            "model": self.settings.llm_model or "gpt-5.6-luna",
            "response_format": {"type": "json_object"},
            "max_completion_tokens": int(
                getattr(self.settings, "llm_max_completion_tokens", 1_200)
            ),
            "messages": chat_messages,
        }
        # OpenAI accepts a stable, privacy-preserving safety identifier. Avoid
        # sending an OpenAI-specific field to arbitrary compatible endpoints.
        if safety_identifier and base_url == "https://api.openai.com/v1":
            request_payload["safety_identifier"] = safety_identifier
        data = json.dumps(request_payload, separators=(",", ":")).encode("utf-8")
        max_request_bytes = int(getattr(self.settings, "llm_max_request_bytes", 128 * 1024))
        if len(data) > max_request_bytes:
            return ProviderOutput(
                json.dumps(
                    {
                        "tutorMessage": "The live tutor context exceeded its configured request boundary; using grounded fallback guidance.",
                        "feedback": "The platform did not send an oversized prompt to the remote provider.",
                        "viewerActions": [],
                        "uncertaintyWarnings": ["Remote tutor request was not sent."],
                        "suggestedNextStep": "Continue with the grounded task evidence or ask a narrower question.",
                    }
                ),
                "request_rejected",
            )
        request = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=data,
            headers={
                "Authorization": f"Bearer {self.settings.llm_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            max_response_bytes = int(getattr(self.settings, "llm_max_response_bytes", 128 * 1024))
            timeout_seconds = int(getattr(self.settings, "llm_request_timeout_seconds", 30))
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read(max_response_bytes + 1)
            if len(raw) > max_response_bytes:
                raise ValueError("Remote tutor response exceeded the configured byte limit")
            parsed = json.loads(raw.decode("utf-8"))
            return ProviderOutput(parsed["choices"][0]["message"]["content"], "success")
        except urllib.error.HTTPError as exc:
            try:
                # Drain only a bounded prefix. Provider error bodies are never
                # learner content and may contain internal diagnostics.
                exc.read(max_response_bytes + 1)
            except Exception:
                pass
            request_id = (exc.headers or {}).get("x-request-id", "")
            safe_request_id = request_id if re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", request_id) else "unavailable"
            logger.warning(
                "Remote tutor HTTP failure status=%s request_id=%s",
                exc.code,
                safe_request_id,
            )
            return ProviderOutput(json.dumps(
                {
                    "tutorMessage": "The remote tutor provider failed; returning grounded fallback guidance.",
                    "feedback": "The platform did not use the LLM as source of truth.",
                    "viewerActions": [],
                    "uncertaintyWarnings": ["The live tutor is temporarily unavailable."],
                    "suggestedNextStep": "Continue with the grounded task evidence and retry the live tutor later.",
                }
            ), "failed")
        except Exception as exc:
            logger.warning("Remote tutor failure type=%s", type(exc).__name__)
            return ProviderOutput(json.dumps(
                {
                    "tutorMessage": "The remote tutor provider failed; returning grounded fallback guidance.",
                    "feedback": "The platform did not use the LLM as source of truth.",
                    "viewerActions": [],
                    "uncertaintyWarnings": ["The live tutor is temporarily unavailable."],
                    "suggestedNextStep": "Continue with the grounded task evidence and retry the live tutor later.",
                }
            ), "failed")


SYSTEM_PROMPT = """
You are an ECG tutor for medical students entering clerkship. Reply with ONE JSON object only — no prose,
no markdown fences. Every field is required:
{
  "tutorMessage": string,        "feedback": string,
  "viewerActions": [ ...objects... ],     "objectiveUpdates": [ ...objects... ],
  "misconceptions": [string],    "uncertaintyWarnings": [string],
  "suggestedNextStep": string,   "socraticQuestion": string,
  "citedEvidence": [string],     "onLessonTopic": boolean
}

viewerActions items are OBJECTS (never bare strings), each a "type" plus its fields, using ONLY supplied leads/ROIs:
  {"type":"highlightLead","lead":"II"}
  {"type":"zoom","leads":["V2"],"timeStart":2.0,"timeEnd":4.0}
  {"type":"highlightROI","lead":"V2","timeStart":3.1,"timeEnd":3.5,"ampMin":-0.1,"ampMax":0.3,"label":"ST segment"}
  {"type":"circleROI","lead":"II","timeStart":1.0,"timeEnd":1.2}
  {"type":"drawCaliper","lead":"II","timeStart":1.0,"timeEnd":1.16,"label":"PR"}
  {"type":"showFiducial","lead":"II","timeSec":1.0,"label":"J point"}
  {"type":"resetView"}
WRONG: "viewerActions":["highlightLead","highlightROI"].  Use [] if none.

objectiveUpdates items are OBJECTS (never bare strings): {"objective":"anterior_mi","delta":0.1,"reason":"learner localized it"}.
WRONG: "objectiveUpdates":["anterior_mi"].  Use [] if none.

You are NOT the source of truth. Use ONLY the supplied GROUNDED CONTEXT (case packet: allowed/forbidden
claims, measurements, PTB-XL labels, PTB-XL+ statements, parsed ROIs) and conversation history. NEVER invent
diagnoses, measurements, intervals, fiducials, or ROIs. If asked about a finding not in the packet, say so
plainly and add an uncertaintyWarning. In tutorial mode, ask one socraticQuestion and keep the learner moving.
For frontal QRS axis, use ONLY the packet's numeric frontal-axis measurement and ventricular QRS evidence in
limb leads I/aVF (lead II may refine a borderline leftward axis). P-wave morphology is atrial evidence and must
NEVER be cited or highlighted as support for QRS axis. A segment-location ROI does not itself prove net polarity.
If they tangent, answer the safe educational core directly, explain how it connects, and set onLessonTopic=false.
Distinguish a GENERAL concept question ("How do I distinguish WCT from VT?") from a CURRENT-CASE claim
("Does this tracing show VT?"). General teaching may discuss a concept absent from the current packet, but it
must say that it is not asserting the concept on this case. Use viewerState's module, scene, step, attempt,
selected point, and pausedWaypoint. Return to the exact paused task, not lesson step one. Only say something
is highlighted or measured when a validated viewerAction accompanies the claim. Teach reasoning, not labels.
Educational use only; no individualized clinical advice.
When viewerState.activity is "adaptive_mastery_plan", use only its verified plan summary. Explain its
priority or study sequence, but never change the queue, invent a mastery value, choose an unlisted case,
or emit objectiveUpdates/viewerActions. The deterministic scheduler is authoritative for destinations.
"""


# Concept tutor for the "Foundations" learning module: answers beginner questions about
# reading an ECG with NO image/case needed, strictly describe-not-diagnose.
FOUNDATIONS_SYSTEM_PROMPT = """
You are a warm, plain-spoken tutor for someone learning to READ AN ECG for the very first time
(the "Foundations" module). You teach the fundamentals only: the waves (P, QRS, T), the graph-paper grid
and boxes, heart rate, rhythm/sinus, the PR/QRS/QT intervals, the ST segment, axis (basics), and R-wave
progression — plus the cardiac physiology behind them.

HARD RULES:
- You do NOT have or need an ECG image. Answer the learner's concept question directly from general
  ECG knowledge. NEVER ask the learner to upload, attach, or provide an ECG / image / tracing.
- Scope is DESCRIBE, not diagnose. If they ask a GENERAL educational question about what a finding can mean,
  answer the safe core in one or two sentences: say that several causes are possible, name only a few broad
  categories when helpful, state which trace/context discriminators matter, and connect it to the later module.
  Do not claim the current teaching tracing has a diagnosis and do not give management. Real-patient symptoms,
  urgency, individualized diagnosis, or treatment still require a clear safety boundary.
- Beginner level: 1-3 short sentences, plain words, define any jargon. Tie to physiology when it builds
  intuition (e.g., the QRS is tall because the ventricles are thick-walled).
- Educational use only; not medical advice.

Reply with ONE JSON object only, no markdown fences: {"tutorMessage": string}
"""


class TutorService:
    def __init__(self, settings: Settings):
        self.settings = settings
        provider_name = settings.llm_provider.lower()
        self.provider: LLMProvider = (
            OpenAICompatibleProvider(settings) if provider_name == "openai-compatible" else MockProvider()
        )

    @property
    def remote_configured(self) -> bool:
        return bool(
            self.settings.llm_provider.lower() == "openai-compatible"
            and self.settings.llm_api_key
        )

    def _safety_identifier(self, learner_id: str | None) -> str | None:
        if not learner_id:
            return None
        secret = self.settings.registration_rate_limit_secret.encode("utf-8")
        digest = hmac.new(
            secret,
            f"ecg-openai-safety-v1\0{learner_id}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"ecg_{digest[:40]}"

    # Dedicated Foundations concept tutor — no case/image, describe-not-diagnose.
    def foundations(
        self,
        message: str,
        scope: str | None = None,
        *,
        learner_id: str | None = None,
        allow_remote: bool = True,
        remote_reservation: Callable[[], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        # Without a real remote model, return a sentinel so the frontend uses its grounded local KB.
        if not allow_remote or not self.remote_configured:
            return {"tutorMessage": "", "provider": "none"}
        quota = remote_reservation() if remote_reservation else None
        if quota is not None and not quota.get("allowed", False):
            return {
                "tutorMessage": "",
                "provider": "grounded-fallback",
                "remoteProviderConfigured": True,
                "remoteUsage": {**quota, "status": "quota_fallback"},
            }
        context = {
            "module": "foundations",
            "scope": scope or "",
            "policy": "describe-not-diagnose; no image needed",
            "_safetyIdentifier": self._safety_identifier(learner_id),
        }
        messages = [{"role": "user", "content": message or "Ask me anything about reading an ECG."}]
        raw = self.provider.generate(messages, context, system_prompt=FOUNDATIONS_SYSTEM_PROMPT)
        provider_status = getattr(raw, "provider_status", "unknown")
        if provider_status != "success":
            return {
                "tutorMessage": "",
                "provider": "grounded-fallback",
                "remoteProviderConfigured": True,
                "remoteUsage": {**(quota or {}), "status": "reserved"},
                "remoteCall": {"attempted": True, "status": provider_status},
            }
        try:
            obj = json.loads(raw)
            msg = (obj.get("tutorMessage") or obj.get("feedback") or "").strip()
        except Exception:
            msg = raw.strip() if isinstance(raw, str) else ""
        return {
            "tutorMessage": msg,
            "provider": self.settings.llm_provider,
            "remoteProviderConfigured": True,
            "remoteUsage": {**(quota or {}), "status": "reserved"},
            "remoteCall": {"attempted": True, "status": "success"},
        }

    # Legacy single-shot path (used by practice grading feedback).
    def chat(
        self,
        request: TutorChatRequest,
        case_packet: dict[str, Any] | None,
        learner_profile: dict[str, Any],
        *,
        allow_remote: bool = True,
        remote_reservation: Callable[[], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        context = self._context(request.mode, case_packet, learner_profile, None, request.viewerState)
        messages = [{"role": "user", "content": request.learnerMessage or "Give a concise grounded read of this ECG."}]
        return self._run(
            messages,
            context,
            case_packet,
            allow_remote=allow_remote,
            remote_reservation=remote_reservation,
        )

    # Multi-turn conversational path (tutor chat, tutorials with tangents).
    def converse(
        self,
        learner_message: str,
        case_packet: dict[str, Any] | None,
        learner_profile: dict[str, Any],
        history: list[dict[str, Any]],
        mode: str = "freeform",
        lesson: dict[str, Any] | None = None,
        viewer_state: dict[str, Any] | None = None,
        *,
        allow_remote: bool = True,
        remote_reservation: Callable[[], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        context = self._context(mode, case_packet, learner_profile, lesson, viewer_state or {})
        messages = [
            {
                "role": "assistant" if turn["role"] == "tutor" else "user",
                "content": str(turn["content"] or "")[:TUTOR_MESSAGE_MAX_CHARS],
            }
            for turn in history[-10:]
        ]
        messages.append({"role": "user", "content": learner_message})
        return self._run(
            messages,
            context,
            case_packet,
            allow_remote=allow_remote,
            remote_reservation=remote_reservation,
        )

    def _context(
        self,
        mode: str,
        case_packet: dict[str, Any] | None,
        profile: dict[str, Any],
        lesson: dict[str, Any] | None,
        viewer_state: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            "mode": mode,
            "lesson": lesson,
            # Full packet so the deterministic mock can ground on real ROIs/measurements;
            # the OpenAI provider trims it for the prompt.
            "casePacket": case_packet,
            "learnerProfileSummary": _profile_summary(profile),
            "viewerState": viewer_state or {},
            "_safetyIdentifier": self._safety_identifier(profile.get("learnerId")),
            "allowedViewerActions": [
                "zoom", "highlightLead", "highlightROI", "circleROI", "drawCaliper", "showFiducial", "resetView",
            ],
            "groundingRules": [
                "LLM cannot override curation.",
                "Do not invent measurements, ROIs, or diagnoses absent from the packet.",
                "Educational use only.",
            ],
        }

    def _run(
        self,
        messages: list[dict[str, Any]],
        context: dict[str, Any],
        case_packet: dict[str, Any] | None,
        *,
        allow_remote: bool = True,
        remote_reservation: Callable[[], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        # General educational tangents use the versioned concept graph before a
        # remote model is called. This prevents a case-grounding guard from
        # incorrectly refusing a legitimate teaching question just because the
        # current tracing lacks that diagnosis, and gives the learner a fast,
        # deterministic return to the exact paused waypoint.
        learner_message = next(
            (str(message.get("content") or "") for message in reversed(messages) if message.get("role") == "user"),
            "",
        )
        asked = _detect_concepts(learner_message)
        has_curated_general_answer = any(concept in _GENERAL_TEACHING for concept in asked)
        is_curated_general_tangent = bool(
            asked and has_curated_general_answer and _is_general_concept_question(learner_message)
        )
        # Keep this evidence boundary deterministic even with a remote model:
        # an earlier production audit saw a model defend QRS axis with P waves.
        # The curated path can only emit numeric frontal-axis and QRS evidence.
        is_axis_evidence_question = any(concept in _AXIS_CONCEPTS for concept in asked)
        remote_candidate = bool(
            allow_remote
            and self.remote_configured
            and not is_curated_general_tangent
            and not is_axis_evidence_question
        )
        quota = remote_reservation() if remote_candidate and remote_reservation else None
        used_remote = bool(remote_candidate and (quota is None or quota.get("allowed", False)))
        if not used_remote:
            raw = MockProvider().generate(messages, context)
        else:
            raw = self.provider.generate(messages, context)
        provider_status = getattr(raw, "provider_status", "success" if used_remote else "not_attempted")
        response, error = validate_tutor_response(raw)
        meas_flags: list[str] = []
        dx_flags: list[str] = []
        requested_action_count = len(response.viewerActions)
        applied_action_count = requested_action_count
        if case_packet:
            response.viewerActions = _safe_actions(response, case_packet)
            applied_action_count = len(response.viewerActions)
            if requested_action_count and applied_action_count == 0:
                # Never retain prose claiming an overlay exists when grounding or
                # geometry validation removed every requested action.
                cleaned = re.sub(
                    r"[^.?!]*(?:highlight(?:ed)?|zoom(?:ed)?|circle(?:d)?|caliper)[^.?!]*[.?!]?",
                    " ",
                    response.tutorMessage or "",
                    flags=re.IGNORECASE,
                ).strip()
                response.tutorMessage = (
                    "I could not place a validated overlay in the visible tracing, so I will not claim one is shown. "
                    + (cleaned or "Use the named lead and waveform boundaries as the visual anchor.")
                )
                response.uncertaintyWarnings = list(response.uncertaintyWarnings) + [
                    "Requested viewer action was not applied after grounding/geometry validation."
                ]
            # Curated general teaching is explicitly not a claim about this
            # packet, so a case-diagnosis checker must not reinterpret the names
            # in that explanation as asserted findings on the displayed ECG.
            if not is_curated_general_tangent:
                meas_flags = _flag_unsupported_measurements(response, case_packet)
                dx_flags = _flag_unsupported_diagnoses(response, case_packet)
            flags = meas_flags + dx_flags
            if flags:
                # Do not display a hallucinated claim with a warning underneath.
                # Replace it with a grounded refusal; deterministic case evidence
                # remains available in the packet and viewer.
                response.tutorMessage = (
                    "I can’t support that statement from this ECG’s curated evidence, so I’m not going to present it as a finding."
                )
                response.feedback = "Use the verified measurements, labels, and highlighted regions for this case."
                response.viewerActions = []
                response.objectiveUpdates = []
                response.socraticQuestion = "Which visible feature can you describe without going beyond the supplied evidence?"
                response.suggestedNextStep = "Anchor the next observation to a lead and a verified waveform region."
                response.uncertaintyWarnings = list(response.uncertaintyWarnings) + flags
        result = response.model_dump()
        result["schemaError"] = error
        displayed_remote = bool(used_remote and provider_status == "success" and error is None)
        result["provider"] = self.settings.llm_provider if displayed_remote else "grounded-fallback"
        result["remoteProviderConfigured"] = self.remote_configured
        result["remoteCall"] = {
            "attempted": used_remote,
            "status": provider_status,
        }
        if quota is not None:
            result["remoteUsage"] = {
                **quota,
                "status": "reserved" if used_remote else "quota_fallback",
            }
        result["claimCheck"] = {
            "unsupportedMeasurementMentions": meas_flags,
            "unsupportedDiagnosisClaims": dx_flags,
        }
        result["viewerActionStatus"] = {
            "requested": requested_action_count,
            "validated": applied_action_count,
            # Backend validation means "safe to request", not "rendered". A
            # future client acknowledgement must close this loop before the
            # platform can truthfully claim an overlay was applied.
            "appliedByClient": False,
            "clientAcknowledgementRequired": applied_action_count > 0,
        }
        return result


def _packet_for_llm(case: dict[str, Any]) -> dict[str, Any]:
    """A trimmed packet for the prompt: grounding-relevant fields only."""
    plus = case.get("ptbxl_plus") or {}
    return {
        "case_id": case.get("case_id"),
        "teaching_tier": case.get("teaching_tier"),
        "clinical_stem": case.get("clinical_stem"),
        "ptbxl": {
            "diagnostic_superclass": (case.get("ptbxl") or {}).get("diagnostic_superclass"),
            "report": (case.get("ptbxl") or {}).get("report"),
        },
        "measurements": _measurements_summary(case),
        "supported_objectives": _supported(case),
        "unsupported_objectives": case.get("unsupported_objectives", [])[:8],
        "rois": [
            {"lead": r["lead"], "label": r["label"], "concept": r.get("concept"),
             "timeStartSec": r["timeStartSec"], "timeEndSec": r["timeEndSec"],
             "ampMinMv": r.get("ampMinMv"), "ampMaxMv": r.get("ampMaxMv")}
            for r in _rois(case)[:12]
        ],
        "statements": plus.get("statements", [])[:6],
        "llm_allowed_claims": case.get("llm_allowed_claims", []),
        "llm_forbidden_claims": case.get("llm_forbidden_claims", []),
        "teaching_points": case.get("teaching_points", [])[:6],
    }


def _profile_summary(profile: dict[str, Any]) -> dict[str, Any]:
    exact_rows = [
        row for row in profile.get("subskillMastery", [])
        if int(row.get("attempts", 0)) > 0
    ]

    def priority(row: dict[str, Any]) -> tuple[Any, ...]:
        due_lane = {"overdue": 0, "due": 1, "unseen": 2, "scheduled": 3}.get(
            str(row.get("dueState") or "unseen"), 2
        )
        return (
            due_lane,
            -float(row.get("overdueDays", 0.0)),
            -int(row.get("highConfidenceWrong", 0)),
            float(row.get("independentMastery", 0.15)),
            int(row.get("independentAttempts", 0)),
            str(row.get("concept") or ""),
            str(row.get("subskill") or ""),
        )

    ranked = sorted(exact_rows, key=priority)
    compact = [
        {
            "objectiveId": row.get("concept"),
            "subskillId": row.get("subskill"),
            "independentMastery": row.get("independentMastery"),
            "independentAttempts": int(row.get("independentAttempts", 0)),
            "formativeScore": row.get("formativeScore"),
            "dueState": row.get("dueState"),
            "overdueDays": float(row.get("overdueDays", 0.0)),
            "nextDueAt": row.get("nextDueAt"),
            "stabilityDays": float(row.get("stabilityDays", 0.0)),
            "lapses": int(row.get("lapses", 0)),
            "spacedRetrievals": int(row.get("spacedRetrievals", 0)),
            "distinctSuccessfulEcgs": int(row.get("distinctSuccessfulEcgs", 0)),
            "distinctMorphologies": int(row.get("distinctMorphologies", 0)),
            "highConfidenceWrong": int(row.get("highConfidenceWrong", 0)),
            "lastIndependentCorrect": row.get("lastIndependentCorrect"),
            "retentionUncertainty": row.get("retentionUncertainty"),
        }
        for row in ranked[:8]
    ]
    exact_weak: list[str] = []
    for row in ranked:
        concept = str(row.get("concept") or "")
        needs_work = (
            int(row.get("independentAttempts", 0)) == 0
            or float(row.get("independentMastery", 0.15)) < 0.6
            or bool(row.get("isDue"))
            or int(row.get("highConfidenceWrong", 0)) > 0
        )
        if concept and needs_work and concept not in exact_weak:
            exact_weak.append(concept)
        if len(exact_weak) == 6:
            break
    exact_objectives = {str(row.get("concept") or "") for row in exact_rows}
    legacy_weak = [
        objective for objective in profile.get("weakObjectives", [])
        if objective not in exact_objectives
    ][:6]
    weak_objectives = list(dict.fromkeys(exact_weak + legacy_weak))[:6]
    return {
        "learnerId": profile.get("learnerId"),
        "competencySource": "exact_subskill_receipts" if exact_rows else "legacy_objective_fallback",
        "weakObjectives": weak_objectives,
        "priorityCompetencies": compact,
        "dueCompetencyCount": sum(1 for row in exact_rows if row.get("isDue")),
        "legacyWeakObjectives": legacy_weak,
        "recentMisconceptions": [m.get("tag") if isinstance(m, dict) else m for m in profile.get("misconceptions", [])][:5],
    }


_MEASUREMENT_MENTIONS = {
    "qtc_ms": ["qtc"],
    "qt_ms": ["qt interval", "qt of", "qt is", "qt ="],
    "pr_ms": ["pr interval", "pr segment", "pr of", "pr is"],
    "axis_deg": ["axis of", "axis is", "° axis", "degree axis", "qrs axis"],
}


def _flag_unsupported_measurements(response: TutorResponse, case: dict[str, Any]) -> list[str]:
    """Guard for the real-LLM path: flag tutor prose that cites a measurement which
    is NOT present in the case packet (the deterministic mock never trips this)."""
    text = (response.tutorMessage or "").lower() + " " + (response.feedback or "").lower()
    available = set((case.get("ptbxl_plus") or {}).get("features") or {})
    flags: list[str] = []
    for key, cues in _MEASUREMENT_MENTIONS.items():
        if key in available:
            continue
        if any(cue in text for cue in cues):
            flags.append(f"Tutor referenced {key.replace('_ms', '').replace('_deg', '').upper()} but it is not in this case packet.")
    return flags


# Diagnostic findings a tutor must not ASSERT unless curation supports them for the case.
# Cues are pathology phrases; the check skips occurrences inside a refusal/negation window
# so legitimate "I don't have evidence for X" prose is not flagged.
_DIAGNOSIS_CLAIM_CUES: dict[str, list[str]] = {
    "st_elevation": ["st elevation", "st-elevation", "stemi"],
    "st_depression": ["st depression", "st-depression"],
    "t_wave_inversion": ["t wave inversion", "t-wave inversion", "inverted t wave"],
    "myocardial_infarction": ["myocardial infarction", "infarction", "infarct"],
    "anterior_mi": ["anterior mi", "anterior infarct", "anteroseptal infarct"],
    "inferior_mi": ["inferior mi", "inferior infarct"],
    "lateral_mi": ["lateral mi", "lateral infarct"],
    "septal_mi": ["septal mi", "septal infarct"],
    "posterior_mi": ["posterior mi", "posterior infarct"],
    "left_bundle_branch_block": ["lbbb", "left bundle branch block"],
    "right_bundle_branch_block": ["rbbb", "right bundle branch block"],
    "atrial_fibrillation": ["atrial fibrillation", "afib", "a-fib"],
    "atrial_flutter": ["atrial flutter"],
    "left_ventricular_hypertrophy": ["lvh", "left ventricular hypertrophy"],
    "right_ventricular_hypertrophy": ["rvh", "right ventricular hypertrophy"],
    "av_block_third_degree": ["complete heart block", "third degree av block", "third-degree av block"],
    "av_block_second_degree_mobitz_ii": ["mobitz ii", "mobitz 2"],
    "qtc_prolongation": ["prolonged qt", "long qt", "qtc prolongation", "prolonged qtc"],
    "wide_complex_tachycardia": ["ventricular tachycardia", "wide complex tachycardia", " vt "],
}

_REFUSAL_CUES = (
    "no ", "not ", "n't", "without", "rule out", "ruled out", "evidence for",
    "don't have", "do not have", "won't", "cannot", "can't", "absent", "rather than",
    "no grounded", "unsupported", "isn't", "is not", "versus", "vs ", "instead of",
)


def _asserts_finding(text: str, cue: str) -> bool:
    """True if ``cue`` appears affirmatively (not inside a refusal/negation window)."""
    start = 0
    while True:
        idx = text.find(cue, start)
        if idx == -1:
            return False
        window = text[max(0, idx - 45): idx + len(cue) + 12]
        if not any(refusal in window for refusal in _REFUSAL_CUES):
            return True
        start = idx + len(cue)


def _flag_unsupported_diagnoses(response: TutorResponse, case: dict[str, Any]) -> list[str]:
    """Guard for the real-LLM path: flag tutor prose that ASSERTS a diagnostic finding
    curation did not support for this case. The deterministic mock refuses unsupported
    findings, so it does not trip this; a real model can overclaim in prose."""
    text = (response.tutorMessage or "").lower() + " " + (response.feedback or "").lower()
    supported = set(case.get("supported_objectives") or [])
    flags: list[str] = []
    for concept, cues in _DIAGNOSIS_CLAIM_CUES.items():
        if concept in supported:
            continue
        if any(_asserts_finding(text, cue) for cue in cues):
            flags.append(
                f"Tutor asserted '{concept_label(concept)}' but it is not a curation-supported finding for this case."
            )
    return flags


def _safe_actions(response: TutorResponse, case: dict[str, Any]) -> list[Any]:
    safe = []
    duration = (case.get("waveform") or {}).get("duration_sec", 10)
    leads = (case.get("waveform") or {}).get("leads", [])
    grounded_rois = _rois(case)
    for action in response.viewerActions:
        clamped = clamp_action_to_case(action.model_dump(exclude_none=True), duration, leads)
        if clamped is None:
            continue
        action_type = clamped.get("type")
        if action_type in {"highlightROI", "circleROI", "drawCaliper", "showFiducial"}:
            lead = clamped.get("lead")
            candidates = [roi for roi in grounded_rois if roi.get("lead") == lead]
            if action_type == "showFiducial":
                time_sec = float(clamped.get("timeSec", -1))
                grounded = any(
                    float(roi.get("timeStartSec", 0)) - 0.08
                    <= time_sec
                    <= float(roi.get("timeEndSec", 0)) + 0.08
                    for roi in candidates
                )
            else:
                start = float(clamped.get("timeStart", -1))
                end = float(clamped.get("timeEnd", -1))
                grounded = any(
                    min(end, float(roi.get("timeEndSec", 0)))
                    - max(start, float(roi.get("timeStartSec", 0)))
                    >= -0.04
                    for roi in candidates
                )
            if not grounded:
                continue
        safe.append(type(action).model_validate(clamped))
    return safe
