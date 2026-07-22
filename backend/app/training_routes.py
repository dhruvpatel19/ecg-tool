"""Server-owned lifecycle for large, unique-case Training campaigns."""

from __future__ import annotations

from collections import OrderedDict, deque
import math
import secrets
from threading import RLock
from typing import Any, Callable, Literal
from urllib.parse import parse_qs, parse_qsl, urlencode

from fastapi import APIRouter, Cookie, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field

from .auth import SESSION_COOKIE_NAME
from .assessment_presentation import (
    assessment_display_id,
    public_assessment_record,
    public_case_packet,
    public_case_summary,
    public_waveform,
)
from .assessment_ledger import AssessmentLedgerError
from .config import get_settings
from .data_sources import case_summary
from .ecg_capability import issue_ecg_capability, matches_ecg_capability
from .grading import grade_attempt, grade_click_answer
from .objectives import objective_definition
from .ontology import PRACTICE_GROUPS, concept_label
from .retention import DURABLE_DISTINCT_SUCCESSFUL_ECGS
from .schemas import AttemptRequest, StructuredInterpretation
from .source_policy import (
    LEGACY_AUDITED_SOURCES,
    packet_allows_learning_evidence,
    packet_mode_policy,
    retention_morphology_key,
)
from .subskill_tasks import (
    SYSTEMATIC_INTERPRETATION_KEYS,
    STRUCTURED_CHOICE_SUBSKILLS,
    build_subskill_task,
    calibration_grade,
    discrimination_task_available,
    mechanism_task_available,
    grade_subskill_task,
    training_independent_receipt_available,
)
from .training_store import TrainingExposureConflictError


LearnerResolver = Callable[[str | None, str, str | None], str]
PacketTransformer = Callable[[dict[str, Any]], dict[str, Any]]

CAMPAIGN_LENGTHS = (5, 10, 20, 25, 50, 100, 500, 1000, 5000)
TRAINING_POOL_CACHE_MAX_ENTRIES = 4
TRAINING_BALANCED_ROLES = ("target", "mimic", "negative")
TRAINING_SUBSKILL_ORDER = (
    "recognize", "localize", "measure", "discriminate", "explain_mechanism",
    "synthesize", "apply_in_context", "calibrate_confidence",
)
ALLOWED_SUBSKILLS = set(TRAINING_SUBSKILL_ORDER)
TRAINING_CLASSIFICATION_CONTRACT_VERSION = "focused-classification-v1"
TRAINING_QUESTION_SNAPSHOT_VERSION = "focused-question-v1"
MEASUREMENT_TARGETS = {
    "rate", "qrs_duration", "qtc_prolongation",
}


class TrainingCampaignStartBody(BaseModel):
    learnerId: str = "demo"
    conceptId: str = Field(min_length=1, max_length=160)
    subskill: str = Field(default="recognize", max_length=80)
    length: Literal[5, 10, 20, 25, 50, 100, 500, 1000, 5000] = 10
    contextKey: str = Field(default="", max_length=1000)
    replaceActive: bool = False


class TrainingStructuredInterpretation(BaseModel):
    rate: str = Field(default="", max_length=500)
    rhythm: str = Field(default="", max_length=500)
    axis: str = Field(default="", max_length=500)
    intervals: str = Field(default="", max_length=750)
    conduction: str = Field(default="", max_length=750)
    st_t: str = Field(default="", max_length=750)
    hypertrophy: str = Field(default="", max_length=750)
    synthesis: str = Field(default="", max_length=2_000)


class TrainingCampaignSubmitBody(BaseModel):
    caseId: str = Field(min_length=1, max_length=160)
    selectedAnswer: Literal["present", "absent"]
    # Confidence is authored only in the explicit calibration task. Other
    # Focused Practice skills must not manufacture a hidden 3/5 response.
    confidence: int | None = Field(default=None, ge=1, le=5)
    hintsUsed: int = Field(default=0, ge=0, le=10)
    evidenceNote: str = Field(default="", max_length=10_000)
    viewerTaskEvidence: dict[str, Any] | None = None
    subskillTaskAnswer: str = Field(default="", max_length=160)
    subskillTaskMatches: dict[str, str] = Field(default_factory=dict, max_length=3)
    subskillTaskValue: float | None = Field(default=None, ge=0, le=5000)
    structuredInterpretation: TrainingStructuredInterpretation | None = None
    receiptConcept: str | None = Field(default=None, max_length=160)


def build_training_classification_contract(
    concept: str, variant: int = 0
) -> dict[str, Any]:
    """Return the versioned, answer-free binary prompt frozen per ordinal."""

    prompt_variant = max(0, int(variant)) % 3
    if concept == "rate":
        prompts = (
            "Classify the ventricular rate band from the tracing.",
            "Estimate the ventricular rate, then place it relative to the adult 60–100 bpm band.",
            "Which rate category is supported by the R–R spacing?",
        )
        present_label = "Within 60–100 bpm"
        absent_label = "Outside 60–100 bpm"
    elif concept == "qrs_duration":
        prompts = (
            "Is the measured QRS wide at the adult 120 ms threshold?",
            "Measure ventricular depolarization, then classify it against 120 ms.",
            "Does QRS onset-to-offset cross the adult wide-complex threshold?",
        )
        present_label = "Wide (≥120 ms)"
        absent_label = "Not wide (<120 ms)"
    elif concept == "qtc_prolongation":
        prompts = (
            "Is the calculated QTc at least 480 ms?",
            "Measure QT, apply the provided correction method, then compare QTc with 480 ms.",
            "Which side of the 480 ms practice threshold does the calculated QTc fall on?",
        )
        present_label = "QTc ≥480 ms"
        absent_label = "QTc <480 ms"
    else:
        label = concept_label(concept)
        prompts = (
            f"Does this tracing support {label}?",
            f"Decide whether the waveform evidence meets the reviewed pattern for {label}.",
            f"After checking the defining leads, is {label} supported or not supported?",
        )
        present_label = "Target present"
        absent_label = "Target absent"
    present = {"id": "present", "label": present_label}
    absent = {"id": "absent", "label": absent_label}
    return {
        "version": TRAINING_CLASSIFICATION_CONTRACT_VERSION,
        "kind": "single_choice",
        "prompt": prompts[prompt_variant],
        "presentLabel": present_label,
        "absentLabel": absent_label,
        "options": [present, absent] if int(variant) % 2 == 0 else [absent, present],
        "required": True,
    }


def _features(case: dict[str, Any]) -> dict[str, Any]:
    plus = case.get("ptbxl_plus") or {}
    return {**(plus.get("features") or {}), **(plus.get("measurements") or {})}


def _rois(case: dict[str, Any]) -> list[dict[str, Any]]:
    return ((case.get("ptbxl_plus") or {}).get("fiducials") or {}).get("rois") or []


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    converted = float(value)
    return converted if math.isfinite(converted) else None


def _waveform_duration_seconds(case: dict[str, Any], lead: str) -> float | None:
    waveform = case.get("waveform") or {}
    duration = _finite_float(
        waveform.get("duration_sec", waveform.get("durationSec"))
    )
    if duration is not None and duration > 0:
        return duration
    sampling_frequency = _finite_float(
        waveform.get("sampling_frequency", waveform.get("samplingFrequency"))
    )
    samples = (case.get("waveform_data") or {}).get(lead)
    if (
        sampling_frequency is not None
        and sampling_frequency > 0
        and isinstance(samples, list)
        and samples
    ):
        return len(samples) / sampling_frequency
    return None


def _reviewed_segment_overlap(
    case: dict[str, Any], *, lead: str, segment: str, start: float, end: float
) -> bool:
    selected_span = end - start
    for roi in _rois(case):
        if roi.get("concept") != segment or roi.get("lead") != lead:
            continue
        roi_start = _finite_float(roi.get("timeStartSec"))
        roi_end = _finite_float(roi.get("timeEndSec"))
        if roi_start is None or roi_end is None or roi_end <= roi_start:
            continue
        overlap = min(end, roi_end) - max(start, roi_start)
        meaningful = max(0.020, 0.5 * min(selected_span, roi_end - roi_start))
        if overlap >= meaningful:
            return True
    return False


def _rate_boundaries_are_anchored(
    case: dict[str, Any], *, lead: str, start: float, end: float
) -> bool:
    """Use reviewed QRS regions when at least two anchors are available."""

    anchors: list[tuple[float, float]] = []
    for roi in _rois(case):
        if roi.get("concept") != "qrs_complex" or roi.get("lead") != lead:
            continue
        roi_start = _finite_float(roi.get("timeStartSec"))
        roi_end = _finite_float(roi.get("timeEndSec"))
        if roi_start is not None and roi_end is not None and roi_end > roi_start:
            anchors.append((roi_start, roi_end))
    if len(anchors) < 2:
        # Some audited packets have a verified rate but only one/no beat ROI.
        # In that case duration bounds plus agreement with the server rate are
        # the strongest available geometry contract.
        return True

    def near(point: float, anchor: tuple[float, float]) -> bool:
        left, right = anchor
        return left - 0.120 <= point <= right + 0.120

    return any(
        first != second and near(start, first) and near(end, second)
        for first in anchors
        for second in anchors
    )


def _measurement_evidence_valid(
    case: dict[str, Any],
    concept: str,
    evidence: dict[str, Any],
) -> bool:
    key, leads, segment = _measurement_contract(concept)
    lead = str(evidence.get("lead") or "")
    if not key or evidence.get("mode") != "caliper" or lead not in leads:
        return False

    start = _finite_float(evidence.get("timeStartSec"))
    end = _finite_float(evidence.get("timeEndSec"))
    claimed_ms = _finite_float(evidence.get("valueMs"))
    duration = _waveform_duration_seconds(case, lead)
    if (
        start is None
        or end is None
        or claimed_ms is None
        or duration is None
        or start < 0
        or end <= start
        or end > duration + 1e-6
    ):
        return False

    measured_ms = (end - start) * 1000.0
    # Browser calipers display an integer number of milliseconds. The raw
    # boundaries are authoritative; allow only their one-millisecond rounding.
    if abs(claimed_ms - measured_ms) > 1.0:
        return False

    expected_value = _finite_float(_features(case).get(key))
    if expected_value is None or expected_value <= 0:
        return False
    expected_ms = (
        60_000.0 / expected_value if concept == "rate" else expected_value
    )
    tolerance = 90.0 if concept == "rate" else 35.0
    if abs(measured_ms - expected_ms) > tolerance:
        return False
    if segment is not None and not _reviewed_segment_overlap(
        case, lead=lead, segment=segment, start=start, end=end
    ):
        return False
    if concept == "rate" and not _rate_boundaries_are_anchored(
        case, lead=lead, start=start, end=end
    ):
        return False
    return True


def _is_training_case(case: dict[str, Any] | None, concept: str, subskill: str) -> bool:
    mode_decision = packet_mode_policy(case, "training")
    if not mode_decision.allowed:
        return False
    if mode_decision.source_kind == "legacy":
        return True
    return packet_allows_learning_evidence(case, "training", concept, subskill).allowed


def _hint_domain(concept: str) -> tuple[str, list[str]]:
    if "lead_territor" in concept or "frontal_lead_map" in concept:
        return "qrs_complex", ["II", "III", "aVF"]
    if "axis" in concept:
        return "qrs_complex", ["I", "aVF"]
    if "bundle" in concept or "qrs" in concept or "conduction" in concept:
        return "qrs_complex", ["V1", "V6"]
    if "av_block" in concept or concept.startswith("pr_"):
        return "pr_interval", ["II"]
    if "qt" in concept:
        return "qt_segment", ["II", "V5"]
    if any(token in concept for token in ("st_", "t_wave", "myocardial")) or concept.endswith("_mi"):
        leads = ["II", "III", "aVF"] if "inferior" in concept else (
            ["I", "aVL", "V5", "V6"] if "lateral" in concept else ["V2", "V3", "V4"]
        )
        return ("t_wave" if "t_wave" in concept else "st_segment"), leads
    if any(token in concept for token in ("atrial", "sinus", "flutter")):
        return "p_wave", ["II"]
    if any(token in concept for token in ("hypertrophy", "enlargement", "r_wave")):
        return "qrs_complex", ["V1", "V5", "V6"]
    return "qrs_complex", ["II"]


def _measurement_contract(concept: str) -> tuple[str, list[str], str | None]:
    segment, leads = _hint_domain(concept)
    if "qt" in concept:
        return "qt_ms", leads, "qt_segment"
    if "av_block" in concept or concept.startswith("pr_"):
        return "pr_ms", leads, "pr_interval"
    if concept == "rate":
        return "heart_rate", leads, None
    if any(token in concept for token in ("qrs", "bundle", "conduction")):
        return "qrs_ms", leads, "qrs_complex"
    return "", leads, segment


def _contract_subskills(case: dict[str, Any], concept: str) -> set[str]:
    eligibility = case.get("educational_eligibility") or {}
    rows = eligibility.get("eligibleSubskills") or {}
    allowed = rows.get(concept) if isinstance(rows, dict) else None
    return {str(item) for item in allowed} if isinstance(allowed, list) else set()


def _focus_is_grounded(case: dict[str, Any], concept: str, subskill: str) -> bool:
    if concept in set(case.get("supported_objectives") or []):
        return True
    # Neutral beat-location annotations are valid only for the exact source-
    # contracted localization objective; they never prove QRS morphology.
    return bool(
        subskill == "localize"
        and subskill in _contract_subskills(case, concept)
        and any(roi.get("concept") == concept for roi in _rois(case))
    )


def _expected_answer(case: dict[str, Any], concept: str, subskill: str = "") -> str | None:
    values = _features(case)
    if concept == "rate":
        rate = values.get("heart_rate")
        return None if not isinstance(rate, (int, float)) else ("present" if 60 <= rate <= 100 else "absent")
    if concept == "qrs_duration":
        qrs = values.get("qrs_ms")
        return None if not isinstance(qrs, (int, float)) else ("present" if qrs >= 120 else "absent")
    if concept == "qt_interval":
        return None
    if concept == "qtc_prolongation":
        qtc = values.get("qtc_ms")
        return None if not isinstance(qtc, (int, float)) else ("present" if qtc >= 480 else "absent")
    return "present" if _focus_is_grounded(case, concept, subskill) else "absent"


def _case_is_subskill_eligible(case: dict[str, Any], concept: str, subskill: str) -> bool:
    if not _is_training_case(case, concept, subskill) or _expected_answer(case, concept, subskill) is None:
        return False
    if not (case.get("supported_objectives") or []):
        return False
    if subskill == "localize":
        segment, leads = _hint_domain(concept)
        return any(roi.get("concept") == segment and roi.get("lead") in leads for roi in _rois(case))
    if subskill == "measure":
        key, leads, segment = _measurement_contract(concept)
        # A Focused set advertised as Measure must have a reviewed numeric
        # target and trace boundary. Free-text-only rehearsal cannot produce a
        # scored task and therefore is not a runnable topic/skill pair.
        if not key:
            return False
        if _finite_float(_features(case).get(key)) is None:
            return False
        # QTc practice separates the rate-corrected numeric answer from the
        # raw QT interval the learner can actually place calipers around.
        if concept == "qtc_prolongation" and _finite_float(
            _features(case).get("qtc_ms")
        ) is None:
            return False
        return segment is None or any(
            roi.get("concept") == segment and roi.get("lead") in leads for roi in _rois(case)
        )
    return True


def _contrast_family(concept: str) -> set[str]:
    if concept == "sinus_rhythm":
        return {"sinus_rhythm", "atrial_fibrillation", "atrial_flutter", "supraventricular_tachycardia", "paced_rhythm"}
    groups = [group for group in PRACTICE_GROUPS if concept in group.get("concepts", [])]
    selected = next((group for group in groups if group.get("id") != "normal_ecg"), groups[0] if groups else None)
    return set(selected.get("concepts", [])) if selected else {concept}


def _receipt_concept(campaign: dict[str, Any]) -> str:
    values = parse_qs(str(campaign.get("contextKey") or ""), keep_blank_values=False)
    requested = str((values.get("receiptConcept") or [""])[0]).strip()
    return requested or str(campaign["conceptId"])


def is_qt_interval_measurement_proxy(
    case_concept: str, subskill: str, receipt_concept: str
) -> bool:
    """Return whether this is the one reviewed cross-concept Training task."""

    return (
        case_concept == "qtc_prolongation"
        and receipt_concept == "qt_interval"
        and subskill == "measure"
    )


def training_task_concept(
    case_concept: str, subskill: str, receipt_concept: str
) -> str:
    """Select the concept whose server-owned task is actually being graded."""

    if is_qt_interval_measurement_proxy(
        case_concept, subskill, receipt_concept
    ):
        return receipt_concept
    return case_concept


def _validate_receipt_contract(
    case_concept: str, subskill: str, receipt_concept: str
) -> str:
    """Bind a mastery receipt to an authored objective/case/skill triple."""

    definition = objective_definition(receipt_concept)
    reason = "unknown_objective"
    is_qt_proxy_pair = (
        case_concept == "qtc_prolongation"
        and receipt_concept == "qt_interval"
    )
    if definition is not None and subskill not in definition.allowed_subskills:
        reason = "subskill_not_authored"
    elif is_qt_proxy_pair and not is_qt_interval_measurement_proxy(
        case_concept, subskill, receipt_concept
    ):
        reason = "proxy_subskill_not_authored"
    elif is_qt_interval_measurement_proxy(
        case_concept, subskill, receipt_concept
    ):
        return receipt_concept
    elif (
        definition is not None
        and case_concept == receipt_concept == "qt_interval"
    ):
        # Preserve the registered direct-target API contract. The pool resolver
        # still fails this incoherent raw-interval campaign closed because no
        # binary positive/negative QT pool is authored.
        return receipt_concept
    elif definition is not None and case_concept not in definition.case_concepts:
        reason = "case_concept_not_authored"
    elif definition is not None:
        return receipt_concept
    raise HTTPException(
        status_code=422,
        detail={
            "code": "training_receipt_contract_invalid",
            "message": (
                "This Focused Practice receipt target is not authored for the "
                "selected ECG concept and skill."
            ),
            "reason": reason,
        },
    )


def _validated_campaign_receipt(campaign: dict[str, Any]) -> str:
    values = parse_qs(
        str(campaign.get("contextKey") or ""), keep_blank_values=False
    ).get("receiptConcept") or []
    if len(values) > 1:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "training_receipt_contract_invalid",
                "message": "A Focused Practice campaign must have one receipt target.",
                "reason": "duplicate_receipt_target",
            },
        )
    return _validate_receipt_contract(
        str(campaign["conceptId"]),
        str(campaign["subskill"]),
        _receipt_concept(campaign),
    )


def _canonical_campaign_context(
    case_concept: str, subskill: str, context_key: str
) -> tuple[str, str]:
    pairs = parse_qsl(context_key, keep_blank_values=False)
    requested = [value.strip() for key, value in pairs if key == "receiptConcept"]
    if len(requested) > 1:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "training_receipt_contract_invalid",
                "message": "A Focused Practice campaign must have one receipt target.",
                "reason": "duplicate_receipt_target",
            },
        )
    receipt_concept = _validate_receipt_contract(
        case_concept,
        subskill,
        requested[0] if requested and requested[0] else case_concept,
    )
    remaining = [(key, value) for key, value in pairs if key != "receiptConcept"]
    return receipt_concept, urlencode(
        [("receiptConcept", receipt_concept), *remaining], doseq=True
    )


def _public_pending_slot(slot: dict[str, Any]) -> dict[str, Any]:
    """Remove answer-bearing planning metadata from a pre-commit response.

    Phase, role, focus, truth, and selection rationale are useful after an
    answer is committed, but each can disclose whether the target is present.
    """
    answer_bearing_keys = {
        "caseFocus",
        "phase",
        "role",
        "selectionReason",
        "targetPresent",
    }
    return {
        key: value for key, value in slot.items()
        if key not in answer_bearing_keys
    }


def _pool_entry_from_truth(
    case_id: str, supported_objectives: list[str], concept: str, family: set[str], truth: bool
) -> dict[str, Any]:
    supported = list(dict.fromkeys(supported_objectives))
    focus = concept if truth else (
        next((item for item in supported if item in family and item != concept), None)
        or ("normal_ecg" if "normal_ecg" in supported else supported[0])
    )
    role = "target" if truth else ("mimic" if focus in family else "negative")
    return {
        "caseId": str(case_id),
        "caseFocus": focus,
        "targetPresent": truth,
        "role": role,
    }


def _pool_entry(case: dict[str, Any], concept: str, subskill: str, family: set[str]) -> dict[str, Any]:
    return _pool_entry_from_truth(
        str(case["case_id"]),
        list(case.get("supported_objectives") or []),
        concept,
        family,
        _expected_answer(case, concept, subskill) == "present",
    )


def _indexed_pool_entry(candidate: dict[str, Any], concept: str, family: set[str]) -> dict[str, Any]:
    value = candidate.get("training_truth_value")
    if concept == "rate":
        truth = isinstance(value, (int, float)) and 60 <= float(value) <= 100
    elif concept == "qrs_duration":
        truth = isinstance(value, (int, float)) and float(value) >= 120
    elif concept == "qtc_prolongation":
        truth = isinstance(value, (int, float)) and float(value) >= 480
    else:
        truth = concept in set(candidate.get("supported_objectives") or [])
    return _pool_entry_from_truth(
        str(candidate["case_id"]),
        list(candidate.get("supported_objectives") or []),
        concept,
        family,
        truth,
    )


def _build_plan(
    pool: list[dict[str, Any]],
    length: int,
    *,
    reserve_transfer_roles: set[str] | None = None,
    rng: Any | None = None,
) -> list[dict[str, Any]]:
    """Create one balanced, unpredictable recipe that is persisted as slots.

    A deterministic randomizer can be injected by tests. Production uses the
    operating system's random source so neither phase order nor case order is a
    reusable answer cue across five-item sets.
    """

    planned_length = min(length, len(pool))
    if planned_length <= 0:
        return []
    randomizer = rng or secrets.SystemRandom()
    transfer_count = max(1, planned_length // 5)
    instructional_count = planned_length - transfer_count
    phases = [
        TRAINING_BALANCED_ROLES[index % len(TRAINING_BALANCED_ROLES)]
        for index in range(instructional_count)
    ] + ["transfer"] * transfer_count
    randomizer.shuffle(phases)

    shuffled_pool = list(pool)
    randomizer.shuffle(shuffled_pool)
    reserved: deque[dict[str, Any]] = deque()
    reserved_ids: set[str] = set()
    if reserve_transfer_roles and transfer_count:
        eligible = [
            entry for entry in shuffled_pool
            if entry["role"] in reserve_transfer_roles
        ]
        randomizer.shuffle(eligible)
        for entry in eligible[:transfer_count]:
            reserved.append(entry)
            reserved_ids.add(entry["caseId"])

    remaining = {
        entry["caseId"]: entry for entry in shuffled_pool
        if entry["caseId"] not in reserved_ids
    }
    queues = {
        role: deque(
            entry["caseId"] for entry in shuffled_pool
            if entry["role"] == role and entry["caseId"] not in reserved_ids
        )
        for role in TRAINING_BALANCED_ROLES
    }
    all_cases = deque(
        entry["caseId"] for entry in shuffled_pool
        if entry["caseId"] not in reserved_ids
    )

    def take(role: str | None = None) -> dict[str, Any] | None:
        queue = queues.get(role) if role else all_cases
        if queue is None:
            return None
        while queue:
            case_id = queue.popleft()
            entry = remaining.pop(case_id, None)
            if entry:
                return entry
        return None

    plan: list[dict[str, Any]] = []
    for desired in phases:
        entry = reserved.popleft() if desired == "transfer" and reserved else (
            take(desired if desired != "transfer" else None)
        )
        if entry is None:
            entry = take(None)
        if entry is None:
            break
        phase = desired if desired == "transfer" or entry["role"] == desired else entry["role"]
        plan.append({**entry, "phase": phase})
    return plan


def _evidence_valid(
    case: dict[str, Any], concept: str, subskill: str, evidence: dict[str, Any] | None, note: str
) -> tuple[bool, bool]:
    evidence = evidence or {}
    if subskill in {"recognize", "calibrate_confidence"}:
        return True, False
    if subskill == "localize":
        point = evidence.get("point") if evidence.get("mode") == "point" else None
        if not isinstance(point, dict):
            return False, True
        segment, leads = _hint_domain(concept)
        if point.get("lead") not in leads:
            return False, True
        try:
            grade = grade_click_answer(
                case, str(point["lead"]), float(point["timeSec"]),
                float(point.get("amplitudeMv", 0)), segment,
            )
        except (KeyError, TypeError, ValueError):
            return False, True
        valid = bool(grade.get("correct")) and not bool(grade.get("noTarget"))
        if "lead_territor" in concept or "frontal_lead_map" in concept:
            lowered = note.lower()
            valid = valid and all(lead in lowered for lead in ("ii", "iii", "avf")) and (
                "inferior" in lowered or "contiguous" in lowered
            )
        return valid, True
    if subskill == "measure":
        key, _, _ = _measurement_contract(concept)
        if not key:
            # A note can document rehearsal, but without a server-owned numeric
            # target its value cannot be called correct or used as mastery
            # evidence. Submit-time logic records completeness separately.
            return False, False
        return _measurement_evidence_valid(case, concept, evidence), True
    # Structured synthesis/application/mechanism choices are graded below from
    # a server-owned answer key. Never let prose length stand in for semantic
    # evidence; an unsupported subskill fails closed.
    return False, False


def _adaptation_contract(
    *,
    expected: str | None,
    classification_correct: bool,
    evidence_valid: bool,
) -> tuple[str, str]:
    """Choose the next unseen roster role from the committed response.

    Classification errors receive another example of the missed class. When
    the ECG decision is right but the required skill task is not, the same
    class is rehearsed again. A fully correct answer switches class to prevent
    memorizing a target-present cadence.
    """

    if not classification_correct:
        if expected == "absent":
            return "contrast", "contrast_after_overcall"
        return "target", "target_recheck_after_miss"
    if not evidence_valid:
        if expected == "absent":
            return "contrast", "contrast_skill_recheck"
        return "target", "target_skill_recheck"
    if expected == "absent":
        return "target", "target_after_contrast_success"
    return "contrast", "contrast_after_target_success"


def _required_systematic_interpretation(
    body: TrainingCampaignSubmitBody, subskill: str
) -> dict[str, str] | None:
    if subskill != "synthesize":
        return None
    if body.structuredInterpretation is None:
        missing = list(SYSTEMATIC_INTERPRETATION_KEYS)
    else:
        values = {
            key: str(getattr(body.structuredInterpretation, key) or "").strip()
            for key in SYSTEMATIC_INTERPRETATION_KEYS
        }
        missing = [key for key, value in values.items() if not value]
        if not missing and len(values["synthesis"]) >= 12:
            return values
    if not missing:
        missing = ["synthesis"]
    raise HTTPException(
        status_code=422,
        detail={
            "code": "training_systematic_interpretation_required",
            "message": (
                "Complete all eight interpretation steps and provide a final "
                "synthesis of at least 12 characters before checking this task."
            ),
            "missingFields": missing,
        },
    )


def _grade_claimed_training_submission(
    *,
    campaign_store: Any,
    learning_store: Any,
    campaign: dict[str, Any],
    case: dict[str, Any],
    slot: dict[str, Any],
    body: TrainingCampaignSubmitBody,
    reservation: dict[str, Any],
) -> dict[str, Any]:
    """Grade and commit only after the pending lease is durably claimed.

    The route owns failure recovery around this function. Keeping every grading
    branch inside one callable guarantees that any exception before the atomic
    store commit releases the exact claim rather than leaving a learner stuck.
    """

    concept = str(campaign["conceptId"])
    subskill = str(campaign["subskill"])
    systematic_interpretation = _required_systematic_interpretation(body, subskill)
    if subskill == "calibrate_confidence" and body.confidence is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "training_confidence_required",
                "message": "Choose a confidence level before checking this calibration task.",
            },
        )
    authored_confidence = (
        body.confidence if subskill == "calibrate_confidence" else None
    )
    receipt_concept = _validated_campaign_receipt(campaign)
    task_concept = training_task_concept(
        concept, subskill, receipt_concept
    )
    expected = _expected_answer(case, concept, subskill)
    focus_grounded = _focus_is_grounded(case, str(slot["caseFocus"]), subskill)
    classification_correct = (
        expected is not None
        and body.selectedAnswer == expected
        and focus_grounded
    )
    evidence_valid, trace_native = _evidence_valid(
        case, receipt_concept, subskill, body.viewerTaskEvidence, body.evidenceNote
    )
    measurement_unverified = bool(
        subskill == "measure" and not _measurement_contract(receipt_concept)[0]
    )
    task_contract = build_subskill_task(
        case_id=body.caseId,
        case_concept=task_concept,
        subskill=subskill,
        case_focus=str(slot["caseFocus"]),
        contrast_family=_contrast_family(concept),
        variant=int(slot["position"]),
        case_packet=case,
    )
    task_complete = True
    task_score = 1.0 if evidence_valid else 0.0
    evidence_source = "trace_native" if trace_native else "response"
    task_result: dict[str, Any] | None = None
    if measurement_unverified:
        task_complete = (
            len(body.evidenceNote.strip()) >= 15
            and any(char.isdigit() for char in body.evidenceNote)
        )
        evidence_valid = False
        task_score = 0.0
        evidence_source = "unverified_measurement_rehearsal"
    elif subskill == "measure" and task_contract is not None:
        trace_evidence_valid = evidence_valid
        task_result = grade_subskill_task(
            task_contract,
            numeric_value=body.subskillTaskValue,
        )
        task_complete = bool(task_result["complete"])
        evidence_valid = bool(trace_evidence_valid and task_result["correct"])
        task_score = float(task_result["score"])
        evidence_source = f"trace_native+{task_contract.evidence_source}"
    elif subskill == "measure":
        task_complete = False
        evidence_valid = False
        task_score = 0.0
        evidence_source = "missing_packet_measurement_task"
    elif subskill in STRUCTURED_CHOICE_SUBSKILLS:
        task_result = (
            grade_subskill_task(
                task_contract,
                answer=body.subskillTaskAnswer,
                matches=body.subskillTaskMatches,
                systematic_interpretation=systematic_interpretation,
                case_packet=case,
            )
            if task_contract
            else None
        )
        systematic_complete = bool(
            task_result
            and task_result.get("systematicInterpretationComplete", True)
        )
        task_complete = bool(
            task_result and task_result["complete"] and systematic_complete
        )
        evidence_valid = bool(
            task_result and task_result["correct"] and systematic_complete
        )
        choice_score = float(task_result["score"]) if task_result else 0.0
        task_score = (
            round((choice_score + (1.0 if systematic_complete else 0.0)) / 2.0, 4)
            if subskill == "synthesize"
            else choice_score
        )
        evidence_source = (
            task_contract.evidence_source if task_contract else "response"
        )
    elif subskill == "calibrate_confidence":
        task_complete = task_contract is not None
        task_score, evidence_valid = calibration_grade(
            int(authored_confidence), classification_correct
        )
        evidence_source = "confidence_commit"

    # Recognition of the campaign target and performance of the selected skill
    # are separate constructs. A learner can measure a QRS correctly while
    # misnaming the pattern, or know a mechanism while overcalling its presence.
    # Preserve both outcomes instead of converting every classification miss
    # into a false measure/localize/mechanism miss.
    subskill_correct = (
        classification_correct if subskill == "recognize" else evidence_valid
    )
    misconceptions: list[str] = []
    if not classification_correct:
        misconceptions.append(f"target_status_error:{concept}")
    if measurement_unverified and not task_complete:
        misconceptions.append("subskill_task_incomplete:measure")
    elif subskill == "measure" and not task_complete:
        misconceptions.append("subskill_task_incomplete:measure")
    elif subskill in STRUCTURED_CHOICE_SUBSKILLS and not task_complete:
        misconceptions.append(f"subskill_task_incomplete:{subskill}")
    elif task_complete and not evidence_valid and not measurement_unverified:
        misconceptions.append(f"subskill_task_error:{subskill}")

    structured = StructuredInterpretation(
        framework="clerkship",
        **(systematic_interpretation or {}),
        selectedConcepts=[concept] if body.selectedAnswer == "present" else [],
    )
    attempt = AttemptRequest(
        learnerId=str(campaign["learnerId"]),
        caseId=body.caseId,
        mode="concept_practice",
        focusObjective=concept,
        structuredAnswer=structured,
        freeTextAnswer=(
            f"{concept}: {body.selectedAnswer}."
            + (
                f" Evidence: {body.evidenceNote.strip()}"
                if body.evidenceNote.strip()
                else ""
            )
        ),
        # The generic deterministic grader still accepts a 1–5 value, but its
        # legacy mastery delta is suppressed below. Only an explicitly authored
        # calibration response is persisted as learner confidence.
        confidence=authored_confidence or 3,
        hintsUsed=body.hintsUsed,
    )
    grade = {
        **grade_attempt(case, attempt),
        "masteryDelta": {},
        "legacyObjectiveMasterySuppressed": True,
        "trainingClassificationCorrect": classification_correct,
        "trainingSubskillEvidenceCorrect": evidence_valid,
        "trainingSubskillTaskComplete": task_complete,
        "trainingSubskillTaskScore": round(task_score, 4),
        "trainingEvidenceSource": evidence_source,
        "trainingEvidenceVerifiable": not measurement_unverified,
        "trainingOutcomeKind": (
            "unverified_rehearsal" if measurement_unverified else "scored_task"
        ),
        "trainingSubskillTaskResult": task_result,
    }
    reviewed_receipt_target = (
        receipt_concept == concept
        or is_qt_interval_measurement_proxy(
            concept, subskill, receipt_concept
        )
    )
    independently_assessable = bool(
        (subskill in {"localize", "measure"} and trace_native and evidence_valid)
        or (
            subskill in STRUCTURED_CHOICE_SUBSKILLS
            and task_complete
            and task_contract
            and task_contract.independently_assessable
        )
        or (subskill == "calibrate_confidence" and task_complete)
    )
    independently_assessed = (
        slot["phase"] == "transfer"
        and body.hintsUsed == 0
        and reviewed_receipt_target
        and independently_assessable
        and (
            subskill in STRUCTURED_CHOICE_SUBSKILLS
            or subskill == "calibrate_confidence"
            or expected == "present"
            or concept in MEASUREMENT_TARGETS
        )
        and focus_grounded
    )
    event_correct = (
        classification_correct and task_complete
        if measurement_unverified
        else subskill_correct
    )
    receipt_event = {
        "eventKey": (
            f"train:{campaign['campaignId']}:{slot['position']}:"
            f"{body.caseId}:{subskill}"
        ),
        "_serverVerifiedScoring": True,
        "moduleId": "train",
        "sceneId": f"{receipt_concept}:{slot['phase']}",
        "interactionId": f"{body.caseId}:{subskill}",
        "concept": receipt_concept,
        "subskills": [subskill],
        "score": (
            task_score if subskill == "calibrate_confidence" else (1.0 if event_correct else 0.0)
        ),
        "correct": event_correct,
        "attempts": 1,
        "assistance": "scaffolded" if body.hintsUsed else "independent",
        "hintsUsed": body.hintsUsed,
        "confidence": authored_confidence,
        "evidenceLevel": (
            "independent_transfer" if independently_assessed else "guided"
        ),
        "trainingPhase": slot["phase"],
        "evidenceSource": evidence_source,
        "caseId": body.caseId,
        "caseProvenance": "real_eligible",
        "unverifiedRehearsal": measurement_unverified,
        "caseEligible": (
            reviewed_receipt_target
            and focus_grounded
            and _is_training_case(case, concept, subskill)
        ),
        "misconceptions": misconceptions,
        "_retentionVerified": independently_assessed,
        "_retentionMorphologyKey": retention_morphology_key(case),
    }
    question_snapshot = {
        "version": TRAINING_QUESTION_SNAPSHOT_VERSION,
        "classification": build_training_classification_contract(
            concept, int(slot["position"])
        ),
        "task": task_contract.public if task_contract else None,
    }
    response_data = {
        "selectedAnswer": body.selectedAnswer,
        "confidence": authored_confidence,
        "hintsUsed": body.hintsUsed,
        "evidenceNote": body.evidenceNote,
        "viewerTaskEvidence": body.viewerTaskEvidence,
        "subskillTaskAnswer": body.subskillTaskAnswer,
        "subskillTaskMatches": body.subskillTaskMatches,
        "subskillTaskValue": body.subskillTaskValue,
        "structuredInterpretation": systematic_interpretation,
        "questionSnapshot": question_snapshot,
        "expectedAnswer": expected,
        "structuredAnswer": structured.model_dump(),
        "freeTextAnswer": attempt.freeTextAnswer,
    }
    summary = {
        "position": slot["position"],
        "caseId": body.caseId,
        "phase": slot["phase"],
        "correct": subskill_correct,
        "scored": not measurement_unverified,
        "outcomeKind": (
            "unverified_rehearsal" if measurement_unverified else "scored_task"
        ),
        "classificationCorrect": classification_correct,
        "focusGrounded": focus_grounded,
        "selectedResponse": body.selectedAnswer,
        "confidence": authored_confidence,
        "hintsUsed": body.hintsUsed,
        "misconceptions": misconceptions,
    }
    adaptation_preference, adaptation_reason = _adaptation_contract(
        expected=expected,
        classification_correct=classification_correct,
        evidence_valid=evidence_valid,
    )
    return campaign_store.finalize_answer(
        learning_store=learning_store,
        campaign_id=str(campaign["campaignId"]),
        case_id=body.caseId,
        learner_id=str(campaign["learnerId"]),
        lease_id=str(reservation["leaseId"]),
        submission_key=str(reservation["submissionKey"]),
        response=response_data,
        # Deterministic grading and evidence persistence never wait for an LLM.
        # Post-commit TutorChat remains available on explicit use.
        grade=grade,
        tutor=None,
        receipt_event=receipt_event,
        summary=summary,
        confidence=authored_confidence,
        hints_used=body.hintsUsed,
        adaptation_preference=adaptation_preference,
        adaptation_reason=adaptation_reason,
    )


def _public_campaign(campaign: dict[str, Any]) -> dict[str, Any]:
    """Keep the server-owned roster recipe and composition server-side.

    Queued slot contracts may be reordered after a response. Neither phase
    counts nor reuse-by-role policy is needed to render learner progress, and
    both can become answer-order cues in short sets.
    """
    return {
        key: value for key, value in campaign.items()
        if key not in {"phases", "phaseCounts", "rosterPolicy"}
    }


class TrainingPoolResolver:
    """Resolve the exact runnable Focused-practice pool behind every route.

    The lightweight target check is shared with dashboard, planner, and
    calendar receipt contracts. The full pool remains lazily materialized only
    when a learner opens setup or launches a campaign, so projecting the full
    competency matrix does not retain corpus-sized lists for every cell.
    """

    def __init__(self, repo) -> None:
        self.repo = repo
        self._pool_cache: OrderedDict[tuple[str, str], list[dict[str, Any]]] = OrderedDict()
        self._target_depth_cache: dict[tuple[str, str], int] = {}
        self._cache_lock = RLock()
        self._pool_cache_max_entries = TRAINING_POOL_CACHE_MAX_ENTRIES

    @staticmethod
    def _pair_is_supported(concept: str, subskill: str) -> bool:
        if subskill not in ALLOWED_SUBSKILLS:
            return False
        # A binary present/absent question is not coherent for a raw interval.
        # qtc_prolongation owns the paired raw-QT caliper + typed-QTc task.
        if concept == "qt_interval":
            return False
        definition = objective_definition(concept)
        if definition is None or subskill not in definition.allowed_subskills:
            return False
        if subskill == "discriminate" and not discrimination_task_available(concept):
            return False
        if subskill == "explain_mechanism" and not mechanism_task_available(concept):
            return False
        return True

    def _candidate_rows(self, concept: str, subskill: str) -> list[dict[str, Any]]:
        segment: str | None = None
        leads: list[str] = []
        measurement_key: str | None = None
        if subskill == "localize":
            segment, leads = _hint_domain(concept)
        elif subskill == "measure":
            raw_key, leads, segment = _measurement_contract(concept)
            measurement_key = raw_key or None
        truth_key = {
            "rate": "heart_rate",
            "qrs_duration": "qrs_ms",
            "qtc_prolongation": "qtc_ms",
        }.get(concept)
        indexed_candidates = getattr(self.repo, "training_candidates", None)
        return indexed_candidates(
            segment=segment,
            leads=leads,
            measurement_key=measurement_key,
            truth_key=truth_key,
        ) if callable(indexed_candidates) else self.repo.candidates(None)

    def _entry_from_candidate(
        self,
        candidate: dict[str, Any],
        concept: str,
        subskill: str,
        family: set[str],
    ) -> dict[str, Any] | None:
        case_id = str(candidate.get("case_id") or "")
        if not case_id:
            return None
        if (
            candidate.get("training_indexed")
            and candidate.get("source") in LEGACY_AUDITED_SOURCES
        ):
            if not (candidate.get("supported_objectives") or []):
                return None
            return _indexed_pool_entry(candidate, concept, family)
        case = self.repo.get_case(case_id)
        if not _case_is_subskill_eligible(case or {}, concept, subskill):
            return None
        return _pool_entry(case, concept, subskill, family)

    def _iter_entries(self, concept: str, subskill: str):
        family = _contrast_family(concept)
        seen: set[str] = set()
        for candidate in self._candidate_rows(concept, subskill):
            case_id = str(candidate.get("case_id") or "")
            if not case_id or case_id in seen:
                continue
            entry = self._entry_from_candidate(candidate, concept, subskill, family)
            if entry is None:
                continue
            seen.add(case_id)
            yield entry

    def _iter_target_entries(self, concept: str, subskill: str):
        """Use the concept index for a cheap exact target-only availability check."""

        family = _contrast_family(concept)
        for candidate in self.repo.candidates(concept):
            entry = self._entry_from_candidate(candidate, concept, subskill, family)
            if entry is not None and entry["targetPresent"]:
                yield entry

    def exact_target_depth(self, concept: str, subskill: str) -> int:
        """Count exact eligible positives only up to the durable threshold."""

        key = (concept, subskill)
        if not self._pair_is_supported(concept, subskill):
            return 0
        with self._cache_lock:
            cached_pool = self._pool_cache.get(key)
            if cached_pool is not None:
                self._pool_cache.move_to_end(key)
                return min(
                    DURABLE_DISTINCT_SUCCESSFUL_ECGS,
                    sum(1 for entry in cached_pool if entry["targetPresent"]),
                )
            cached_depth = self._target_depth_cache.get(key)
            if cached_depth is not None:
                return cached_depth
        depth = 0
        for _entry in self._iter_target_entries(concept, subskill):
            depth += 1
            if depth >= DURABLE_DISTINCT_SUCCESSFUL_ECGS:
                break
        with self._cache_lock:
            self._target_depth_cache[key] = depth
        return depth

    def has_exact_target(self, concept: str, subskill: str) -> bool:
        """Return whether this exact pair can launch formative Focused work."""

        return self.exact_target_depth(concept, subskill) > 0

    def has_durable_exact_target(self, concept: str, subskill: str) -> bool:
        """Gate planner/dashboard receipts on enough distinct positive ECGs."""

        return self.exact_target_depth(
            concept, subskill
        ) >= DURABLE_DISTINCT_SUCCESSFUL_ECGS

    def eligible_pool(self, concept: str, subskill: str) -> list[dict[str, Any]]:
        key = (concept, subskill)
        if not self._pair_is_supported(concept, subskill):
            return []
        with self._cache_lock:
            cached = self._pool_cache.get(key)
            if cached is not None:
                self._pool_cache.move_to_end(key)
                return cached
        entries = list(self._iter_entries(concept, subskill))
        # A target campaign without at least one grounded positive case would
        # be a generic normality quiz mislabeled as competency training.
        target_available = any(entry["targetPresent"] for entry in entries)
        if not target_available:
            entries = []
        entries.sort(
            key=lambda entry: (
                not entry["targetPresent"],
                (0, int(entry["caseId"]))
                if entry["caseId"].isdigit()
                else (1, entry["caseId"]),
            )
        )
        with self._cache_lock:
            # Another request may have populated the same pool while this one
            # was built. Reuse that working set and preserve LRU order.
            cached = self._pool_cache.get(key)
            if cached is not None:
                self._pool_cache.move_to_end(key)
                return cached
            self._target_depth_cache[key] = min(
                DURABLE_DISTINCT_SUCCESSFUL_ECGS,
                sum(1 for entry in entries if entry["targetPresent"]),
            )
            self._pool_cache[key] = entries
            self._pool_cache.move_to_end(key)
            while len(self._pool_cache) > self._pool_cache_max_entries:
                self._pool_cache.popitem(last=False)
            return entries


def build_training_router(
    repo,
    learning_store,
    campaign_store,
    packet_provider: PacketTransformer,
    blind_packet: PacketTransformer,
    blind_summary: PacketTransformer,
    resolve_learner: LearnerResolver,
    training_pool_resolver: TrainingPoolResolver | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/training/campaigns", tags=["training-campaigns"])
    capability_secret = get_settings().adaptive_plan_context_secret
    bind_case_packets = getattr(learning_store, "set_case_packet_provider", None)
    if callable(bind_case_packets):
        bind_case_packets(repo.get_case)
    # Each full pool can describe most of the 22k-record release corpus. The
    # shared resolver keeps only a small LRU while retaining lightweight exact
    # availability checks for dashboard, planner, and calendar projections.
    pool_resolver = training_pool_resolver or TrainingPoolResolver(repo)
    eligible_pool = pool_resolver.eligible_pool

    def require_known_objective(concept: str) -> None:
        if objective_definition(concept) is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "unknown_training_objective",
                    "message": "Choose a competency from the current objective registry.",
                },
            )

    def owned(
        campaign_id: str, authorization: str | None, session_cookie: str | None
    ) -> dict[str, Any]:
        campaign = campaign_store.get_campaign(campaign_id)
        learner = resolve_learner(authorization, "demo", session_cookie)
        if not campaign or campaign.get("learnerId") != learner:
            raise HTTPException(status_code=404, detail="Training campaign not found")
        return campaign

    def case_reference(campaign: dict[str, Any], canonical_id: str) -> str:
        return issue_ecg_capability(
            capability_secret,
            str(campaign["learnerId"]),
            "training",
            str(campaign["campaignId"]),
            str(canonical_id),
        )

    def reference_matches(
        campaign: dict[str, Any], reference: object, canonical_id: str
    ) -> bool:
        return matches_ecg_capability(
            reference,
            capability_secret,
            str(campaign["learnerId"]),
            "training",
            str(campaign["campaignId"]),
            str(canonical_id),
        )

    def public_answer(
        campaign: dict[str, Any], answer: dict[str, Any]
    ) -> dict[str, Any]:
        canonical_id = str(answer.get("caseId") or "")
        ordinal = int(answer.get("position") or 0) + 1
        return public_assessment_record(
            answer,
            case_reference=case_reference(campaign, canonical_id),
            display_id=assessment_display_id("training", ordinal),
        )

    def public_summary(
        campaign: dict[str, Any], summary: dict[str, Any]
    ) -> dict[str, Any]:
        public = dict(summary)
        public["recent"] = [
            public_assessment_record(
                attempt,
                case_reference=case_reference(
                    campaign, str(attempt.get("caseId") or "")
                ),
                display_id=assessment_display_id(
                    "training", int(attempt.get("position") or 0) + 1
                ),
            )
            for attempt in (summary.get("recent") or [])
        ]
        return public

    def public_campaign(campaign: dict[str, Any]) -> dict[str, Any]:
        public = _public_campaign(campaign)
        for key in ("pendingCaseId", "feedbackCaseId"):
            canonical_id = public.get(key)
            public[key] = (
                case_reference(campaign, str(canonical_id))
                if canonical_id
                else None
            )
        return public

    def payload(campaign: dict[str, Any] | None) -> dict[str, Any]:
        if not campaign:
            return {"campaign": None, "current": None, "summary": None}
        current: dict[str, Any] | None = None
        pending = campaign.get("pendingCaseId")
        feedback = campaign.get("feedbackCaseId")
        if pending:
            case = repo.get_case(pending)
            slot = campaign_store.get_slot_for_case(campaign["campaignId"], pending)
            if not _is_training_case(case, campaign["conceptId"], campaign["subskill"]):
                raise HTTPException(status_code=409, detail="Training campaign case failed its audited source contract")
            receipt_concept = _validated_campaign_receipt(campaign)
            task_concept = training_task_concept(
                str(campaign["conceptId"]),
                str(campaign["subskill"]),
                receipt_concept,
            )
            task = build_subskill_task(
                case_id=str(pending),
                case_concept=task_concept,
                subskill=str(campaign["subskill"]),
                case_focus=str(slot["caseFocus"]),
                contrast_family=_contrast_family(str(campaign["conceptId"])),
                variant=int(slot["position"]),
                case_packet=case,
            ) if slot else None
            classification = build_training_classification_contract(
                str(campaign["conceptId"]),
                int(slot["position"] if slot else campaign["position"]),
            )
            question_snapshot = {
                "version": TRAINING_QUESTION_SNAPSHOT_VERSION,
                "classification": classification,
                "task": task.public if task else None,
            }
            reference = case_reference(campaign, str(pending))
            display_id = assessment_display_id(
                "training", int(slot["position"] if slot else campaign["position"]) + 1
            )
            public_slot = _public_pending_slot(slot) if slot else None
            if public_slot is not None:
                public_slot["caseId"] = reference
            current = {
                "kind": "pending",
                "slot": public_slot,
                "case": public_case_summary(
                    blind_summary(case_summary(case)),
                    case_reference=reference,
                    display_id=display_id,
                ),
                "packet": public_case_packet(
                    blind_packet(packet_provider(case)),
                    case_reference=reference,
                    display_id=display_id,
                ),
                "task": task.public if task else None,
                "classification": classification,
                "questionSnapshot": question_snapshot,
            }
        elif feedback:
            case = repo.get_case(feedback)
            slot = campaign_store.get_slot_for_case(campaign["campaignId"], feedback)
            answer = campaign_store.get_answer(campaign["campaignId"], feedback)
            if not _is_training_case(case, campaign["conceptId"], campaign["subskill"]):
                raise HTTPException(status_code=409, detail="Training feedback case failed its audited source contract")
            if case and answer:
                receipt_concept = _validated_campaign_receipt(campaign)
                task_concept = training_task_concept(
                    str(campaign["conceptId"]),
                    str(campaign["subskill"]),
                    receipt_concept,
                )
                task = build_subskill_task(
                    case_id=str(feedback),
                    case_concept=task_concept,
                    subskill=str(campaign["subskill"]),
                    case_focus=str(slot["caseFocus"]),
                    contrast_family=_contrast_family(str(campaign["conceptId"])),
                    variant=int(slot["position"]),
                    case_packet=case,
                ) if slot else None
                stored_snapshot = (
                    (answer.get("response") or {}).get("questionSnapshot")
                    if isinstance(answer.get("response"), dict)
                    else None
                )
                if not isinstance(stored_snapshot, dict):
                    stored_snapshot = {
                        "version": TRAINING_QUESTION_SNAPSHOT_VERSION,
                        "classification": build_training_classification_contract(
                            str(campaign["conceptId"]),
                            int(slot["position"] if slot else campaign["position"] - 1),
                        ),
                        "task": task.public if task else None,
                    }
                classification = stored_snapshot.get("classification")
                frozen_task = stored_snapshot.get("task")
                reference = case_reference(campaign, str(feedback))
                display_id = assessment_display_id(
                    "training", int(slot["position"] if slot else campaign["position"] - 1) + 1
                )
                current = {
                    "kind": "feedback",
                    "slot": public_assessment_record(
                        slot,
                        case_reference=reference,
                        display_id=display_id,
                    ) if slot else None,
                    "case": public_case_summary(
                        blind_summary(case_summary(case)),
                        case_reference=reference,
                        display_id=display_id,
                    ),
                    "packet": public_case_packet(
                        packet_provider(case),
                        case_reference=reference,
                        display_id=display_id,
                    ),
                    "answer": public_answer(campaign, answer),
                    "task": frozen_task,
                    "classification": classification,
                    "questionSnapshot": stored_snapshot,
                }
        return {
            "campaign": public_campaign(campaign),
            "current": current,
            "summary": public_summary(
                campaign, campaign_store.summary(campaign["campaignId"])
            ),
        }

    @router.get("/availability")
    def availability(
        response: Response,
        conceptId: str = Query(min_length=1, max_length=160),
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        """Return cheap exact-pair launchability without materializing 8 pools."""

        resolve_learner(authorization, "demo", session_cookie)
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["Vary"] = "Authorization, Cookie"
        require_known_objective(conceptId)
        subskills: dict[str, dict[str, bool]] = {}
        for subskill in TRAINING_SUBSKILL_ORDER:
            exact_depth = pool_resolver.exact_target_depth(conceptId, subskill)
            available = exact_depth > 0
            subskills[subskill] = {
                "available": available,
                "independentReceiptsAvailable": bool(
                    exact_depth >= DURABLE_DISTINCT_SUCCESSFUL_ECGS
                    and training_independent_receipt_available(conceptId, subskill)
                ),
            }
        return {
            "conceptId": conceptId,
            "subskills": subskills,
            "source": "exact_target_index",
        }

    @router.get("/pool")
    def pool(
        response: Response,
        conceptId: str = Query(min_length=1, max_length=160),
        subskill: str = Query(default="recognize", max_length=80),
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        resolve_learner(authorization, "demo", session_cookie)
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["Vary"] = "Authorization, Cookie"
        require_known_objective(conceptId)
        entries = eligible_pool(conceptId, subskill)
        role_counts = {
            role: sum(1 for entry in entries if entry["role"] == role)
            for role in ("target", "mimic", "negative")
        }
        return {
            "conceptId": conceptId,
            "subskill": subskill,
            "eligibleDistinct": len(entries),
            "roleCounts": role_counts,
            "allowedLengths": list(CAMPAIGN_LENGTHS),
            "source": "audited_waveform_only",
            "independentReceiptsAvailable": training_independent_receipt_available(
                conceptId, subskill
            ),
        }

    @router.post("")
    def start(
        body: TrainingCampaignStartBody,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        if body.subskill not in ALLOWED_SUBSKILLS:
            raise HTTPException(status_code=422, detail="Unknown Training subskill")
        require_known_objective(body.conceptId)
        _, canonical_context_key = _canonical_campaign_context(
            body.conceptId,
            body.subskill,
            body.contextKey,
        )
        learner = resolve_learner(authorization, body.learnerId, session_cookie)
        entries = eligible_pool(body.conceptId, body.subskill)
        if not entries:
            raise HTTPException(status_code=409, detail="No eligible distinct audited waveform ECGs support this competency")
        canonical_plan = _build_plan(
            entries,
            min(body.length, len(entries)),
            reserve_transfer_roles=(
                {"target"}
                if body.subskill in {"localize", "measure"}
                else {"target", "mimic"}
                if body.subskill == "discriminate"
                else None
            ),
        )
        learning_store.ensure_profile(learner)
        try:
            started = campaign_store.start_or_return_campaign(
                learner,
                body.conceptId,
                body.subskill,
                body.length,
                len(entries),
                canonical_plan,
                entries,
                context_key=canonical_context_key,
                replace_active=body.replaceActive,
            )
        except TrainingExposureConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "training_live_exposure_conflict",
                    "message": "Another active assessment is using ECGs required by this exact set. Finish that assessment, then start Training again.",
                },
            ) from exc
        campaign = started["campaign"]
        if started["status"] == "existing":
            raise HTTPException(
                status_code=409,
                detail={"code": "active_training_campaign", "campaignId": campaign["campaignId"]},
            )
        return payload(campaign)

    @router.get("/active")
    def active(
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        learner = resolve_learner(authorization, "demo", session_cookie)
        return payload(campaign_store.get_active(learner))

    @router.get("/{campaign_id}")
    def get_campaign(
        campaign_id: str,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        return payload(owned(campaign_id, authorization, session_cookie))

    @router.get("/{campaign_id}/waveform/{case_ref}")
    def get_campaign_waveform(
        campaign_id: str,
        case_ref: str,
        response: Response,
        leads: str | None = Query(default=None, max_length=120),
        start: float = Query(default=0, ge=0),
        end: float | None = Query(default=None, ge=0),
        maxPoints: int = Query(default=1200, ge=100, le=5000),
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        campaign = owned(campaign_id, authorization, session_cookie)
        canonical_id = next(
            (
                str(candidate)
                for candidate in (
                    campaign.get("pendingCaseId"),
                    campaign.get("feedbackCaseId"),
                )
                if candidate and reference_matches(campaign, case_ref, str(candidate))
            ),
            None,
        )
        if canonical_id is None:
            raise HTTPException(status_code=404, detail="Training ECG not found")
        lead_list = [lead.strip() for lead in leads.split(",")] if leads else None
        if lead_list and (len(lead_list) > 12 or any(not lead or len(lead) > 8 for lead in lead_list)):
            raise HTTPException(status_code=422, detail="Invalid waveform lead selection")
        waveform = repo.get_waveform_window(
            canonical_id,
            leads=lead_list,
            start=start,
            end=end,
            max_points=maxPoints,
        )
        if not waveform:
            raise HTTPException(status_code=404, detail="Training ECG not found")
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["Vary"] = "Authorization, Cookie"
        return public_waveform(waveform, case_reference=case_ref)

    @router.post("/{campaign_id}/next")
    def next_case(
        campaign_id: str,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        campaign = owned(campaign_id, authorization, session_cookie)
        if campaign.get("feedbackCaseId"):
            campaign = campaign_store.acknowledge_feedback(campaign_id) or campaign
        if campaign.get("status") == "active" and not campaign.get("pendingCaseId"):
            campaign = campaign_store.claim_next(campaign_id) or campaign
        return payload(campaign)

    @router.post("/{campaign_id}/submit")
    def submit(
        campaign_id: str,
        body: TrainingCampaignSubmitBody,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        campaign = owned(campaign_id, authorization, session_cookie)
        pending_id = str(campaign.get("pendingCaseId") or "")
        feedback_id = str(campaign.get("feedbackCaseId") or "")
        canonical_id = next(
            (
                candidate
                for candidate in (pending_id, feedback_id)
                if candidate and reference_matches(campaign, body.caseId, candidate)
            ),
            None,
        )
        if canonical_id is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "training_case_not_pending",
                    "pendingCaseId": (
                        case_reference(campaign, pending_id) if pending_id else None
                    ),
                },
            )
        body = body.model_copy(update={"caseId": canonical_id})
        prior = campaign_store.get_answer(campaign_id, canonical_id)
        if prior:
            if (
                prior.get("integrityStatus") == "finalizing"
                or not prior.get("receipt")
                or not prior["receipt"].get("eventId")
            ):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "training_legacy_answer_quarantined",
                        "message": "This historical Training answer has no complete receipt ledger.",
                    },
                )
            response = payload(campaign_store.get_campaign(campaign_id))
            response.update({"answer": public_answer(campaign, prior), "replay": True})
            return response
        if pending_id != canonical_id:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "training_case_not_pending",
                    "pendingCaseId": (
                        case_reference(campaign, pending_id) if pending_id else None
                    ),
                },
            )
        case = repo.get_case(canonical_id)
        if not _is_training_case(case, campaign["conceptId"], campaign["subskill"]):
            raise HTTPException(status_code=409, detail="Training submissions require a source-contracted Tier A/B waveform ECG")
        slot = campaign_store.get_slot_for_case(campaign_id, body.caseId)
        if not slot:
            raise HTTPException(status_code=409, detail="Training slot not found")

        concept = campaign["conceptId"]
        subskill = campaign["subskill"]
        receipt_concept = _validated_campaign_receipt(campaign)
        if body.receiptConcept and body.receiptConcept != receipt_concept:
            raise HTTPException(
                status_code=422,
                detail="The submitted receipt target does not match the server-owned campaign contract",
            )
        try:
            reservation = campaign_store.claim_answer_submission(
                campaign_id=campaign_id,
                case_id=body.caseId,
                learner_id=str(campaign["learnerId"]),
            )
        except AssessmentLedgerError as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "training_assessment_unavailable",
                    "message": "This Training item changed before it could be reserved. Resume the campaign and try again.",
                },
            ) from exc
        if reservation["status"] == "replay":
            recorded = reservation
        elif reservation["status"] != "claimed":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "training_case_not_pending",
                    "pendingCaseId": (
                        case_reference(
                            campaign, str(reservation.get("pendingCaseId"))
                        )
                        if reservation.get("pendingCaseId")
                        else None
                    ),
                },
            )
        else:
            try:
                recorded = _grade_claimed_training_submission(
                    campaign_store=campaign_store,
                    learning_store=learning_store,
                    campaign=campaign,
                    case=case,
                    slot=slot,
                    body=body,
                    reservation=reservation,
                )
            except AssessmentLedgerError as exc:
                campaign_store.release_answer_submission(
                    campaign_id=campaign_id,
                    learner_id=str(campaign["learnerId"]),
                    lease_id=str(reservation["leaseId"]),
                    submission_key=str(reservation["submissionKey"]),
                )
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "training_assessment_changed",
                        "message": "This Training item changed before the answer could be committed. Resume the campaign to continue safely.",
                    },
                ) from exc
            except Exception:
                campaign_store.release_answer_submission(
                    campaign_id=campaign_id,
                    learner_id=str(campaign["learnerId"]),
                    lease_id=str(reservation["leaseId"]),
                    submission_key=str(reservation["submissionKey"]),
                )
                raise
            if recorded["status"] not in {"recorded", "replay"}:
                campaign_store.release_answer_submission(
                    campaign_id=campaign_id,
                    learner_id=str(campaign["learnerId"]),
                    lease_id=str(reservation["leaseId"]),
                    submission_key=str(reservation["submissionKey"]),
                )
        if recorded["status"] == "replay":
            response = payload(campaign_store.get_campaign(campaign_id))
            response.update({
                "answer": public_answer(campaign, recorded["answer"]),
                "replay": True,
            })
            return response
        if recorded["status"] == "legacy_incomplete":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "training_legacy_answer_quarantined",
                    "message": "This historical Training answer has no complete receipt ledger.",
                },
            )
        if recorded["status"] != "recorded":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "training_assessment_changed",
                    "message": "This Training item changed before the answer could be committed. Resume the campaign to continue safely.",
                },
            )
        response = payload(campaign_store.get_campaign(campaign_id))
        response.update({
            "answer": public_answer(campaign, recorded["answer"]),
            "replay": False,
        })
        return response

    @router.post("/{campaign_id}/abandon")
    def abandon(
        campaign_id: str,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        campaign = owned(campaign_id, authorization, session_cookie)
        return payload(
            campaign_store.abandon(
                campaign_id,
                learner_id=str(campaign["learnerId"]),
            )
        )

    return router
