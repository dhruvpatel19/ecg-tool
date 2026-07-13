"""Server-owned lifecycle for large, unique-case Training campaigns."""

from __future__ import annotations

from collections import deque
from typing import Any, Callable, Literal
from urllib.parse import parse_qs

from fastapi import APIRouter, Cookie, Header, HTTPException, Query
from pydantic import BaseModel, Field

from .auth import SESSION_COOKIE_NAME
from .data_sources import case_summary
from .grading import grade_attempt, grade_click_answer
from .objectives import objective_definition
from .ontology import PRACTICE_GROUPS
from .schemas import AttemptRequest, StructuredInterpretation
from .source_policy import (
    LEGACY_AUDITED_SOURCES,
    packet_allows_learning_evidence,
    packet_mode_policy,
    retention_morphology_key,
)
from .subskill_tasks import (
    build_subskill_task,
    calibration_grade,
    discrimination_task_available,
    mechanism_task_available,
)


LearnerResolver = Callable[[str | None, str, str | None], str]
PacketTransformer = Callable[[dict[str, Any]], dict[str, Any]]

CAMPAIGN_LENGTHS = (10, 25, 50, 100, 500, 1000, 5000)
TRAINING_PHASE_CYCLE = (
    "target", "target", "target", "mimic", "mimic",
    "negative", "negative", "transfer", "transfer", "transfer",
)
ALLOWED_SUBSKILLS = {
    "recognize", "localize", "measure", "discriminate", "explain_mechanism",
    "synthesize", "apply_in_context", "calibrate_confidence",
}
MEASUREMENT_TARGETS = {"rate", "qrs_duration", "qt_interval"}


class TrainingCampaignStartBody(BaseModel):
    learnerId: str = "demo"
    conceptId: str = Field(min_length=1, max_length=160)
    subskill: str = Field(default="recognize", max_length=80)
    length: Literal[10, 25, 50, 100, 500, 1000, 5000] = 10
    contextKey: str = Field(default="", max_length=1000)
    replaceActive: bool = False


class TrainingCampaignSubmitBody(BaseModel):
    caseId: str = Field(min_length=1, max_length=160)
    selectedAnswer: Literal["present", "absent"]
    confidence: int = Field(default=3, ge=1, le=5)
    hintsUsed: int = Field(default=0, ge=0, le=10)
    evidenceNote: str = Field(default="", max_length=10_000)
    viewerTaskEvidence: dict[str, Any] | None = None
    subskillTaskAnswer: str = Field(default="", max_length=160)
    receiptConcept: str | None = Field(default=None, max_length=160)


def _features(case: dict[str, Any]) -> dict[str, Any]:
    plus = case.get("ptbxl_plus") or {}
    return {**(plus.get("features") or {}), **(plus.get("measurements") or {})}


def _rois(case: dict[str, Any]) -> list[dict[str, Any]]:
    return ((case.get("ptbxl_plus") or {}).get("fiducials") or {}).get("rois") or []


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
        if not key:  # free-text measurement remains formative, as before
            return True
        if not isinstance(_features(case).get(key), (int, float)):
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


def _public_pending_slot(slot: dict[str, Any]) -> dict[str, Any]:
    """Remove the durable answer key from the pre-commit response.

    Phase is pedagogical (and transfer remains unannounced), but caseFocus and
    targetPresent directly reveal the server-owned target/mimic truth.
    """
    return {
        key: value for key, value in slot.items()
        if key not in {"caseFocus", "targetPresent"}
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
    elif concept == "qt_interval":
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
) -> list[dict[str, Any]]:
    planned_length = min(length, len(pool))
    transfer_count = sum(
        1 for index in range(planned_length)
        if TRAINING_PHASE_CYCLE[index % len(TRAINING_PHASE_CYCLE)] == "transfer"
    )
    reserved: deque[dict[str, Any]] = deque()
    reserved_ids: set[str] = set()
    if reserve_transfer_roles and transfer_count:
        eligible = [entry for entry in pool if entry["role"] in reserve_transfer_roles]
        for entry in eligible[-transfer_count:]:
            reserved.append(entry)
            reserved_ids.add(entry["caseId"])

    remaining = {
        entry["caseId"]: entry for entry in pool
        if entry["caseId"] not in reserved_ids
    }
    queues = {
        role: deque(
            entry["caseId"] for entry in pool
            if entry["role"] == role and entry["caseId"] not in reserved_ids
        )
        for role in ("target", "mimic", "negative")
    }
    all_cases = deque(
        entry["caseId"] for entry in pool if entry["caseId"] not in reserved_ids
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
    for index in range(planned_length):
        desired = TRAINING_PHASE_CYCLE[index % len(TRAINING_PHASE_CYCLE)]
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
        key, leads, _ = _measurement_contract(concept)
        if not key:
            return len(note.strip()) >= 15 and any(char.isdigit() for char in note), False
        if evidence.get("mode") != "caliper" or evidence.get("lead") not in leads:
            return False, True
        measured = evidence.get("valueMs")
        expected_value = _features(case).get(key)
        if not isinstance(measured, (int, float)) or not isinstance(expected_value, (int, float)):
            return False, True
        expected_ms = 60_000 / expected_value if concept == "rate" and expected_value > 0 else expected_value
        tolerance = 90 if concept == "rate" else 35
        return abs(float(measured) - float(expected_ms)) <= tolerance, True
    return len(note.strip()) >= 20, False


def _public_campaign(campaign: dict[str, Any]) -> dict[str, Any]:
    """Keep the immutable 5,000-slot phase sequence server-side.

    The current slot and aggregate phase counts are sufficient for rendering;
    serializing the full sequence after every answer would create quadratic
    response bandwidth over a long campaign.
    """
    public = dict(campaign)
    public.pop("phases", None)
    return public


def build_training_router(
    repo,
    learning_store,
    campaign_store,
    packet_provider: PacketTransformer,
    blind_packet: PacketTransformer,
    blind_summary: PacketTransformer,
    resolve_learner: LearnerResolver,
) -> APIRouter:
    router = APIRouter(prefix="/training/campaigns", tags=["training-campaigns"])
    bind_case_packets = getattr(learning_store, "set_case_packet_provider", None)
    if callable(bind_case_packets):
        bind_case_packets(repo.get_case)
    pool_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}

    def eligible_pool(concept: str, subskill: str) -> list[dict[str, Any]]:
        key = (concept, subskill)
        if key in pool_cache:
            return pool_cache[key]
        if subskill not in ALLOWED_SUBSKILLS:
            return []
        definition = objective_definition(concept)
        if definition and subskill not in definition.allowed_subskills:
            return []
        family = _contrast_family(concept)
        if subskill == "discriminate" and not discrimination_task_available(concept):
            return []
        if subskill == "explain_mechanism" and not mechanism_task_available(concept):
            return []
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
            "qt_interval": "qtc_ms",
        }.get(concept)
        indexed_candidates = getattr(repo, "training_candidates", None)
        candidates = indexed_candidates(
            segment=segment,
            leads=leads,
            measurement_key=measurement_key,
            truth_key=truth_key,
        ) if callable(indexed_candidates) else repo.candidates(None)
        entries: list[dict[str, Any]] = []
        seen: set[str] = set()
        for candidate in candidates:
            case_id = str(candidate.get("case_id") or "")
            if not case_id or case_id in seen:
                continue
            if candidate.get("training_indexed") and candidate.get("source") in LEGACY_AUDITED_SOURCES:
                if not (candidate.get("supported_objectives") or []):
                    continue
                seen.add(case_id)
                entries.append(_indexed_pool_entry(candidate, concept, family))
                continue
            case = repo.get_case(case_id)
            if not _case_is_subskill_eligible(case or {}, concept, subskill):
                continue
            seen.add(case_id)
            entries.append(_pool_entry(case, concept, subskill, family))
        # A target campaign without at least one grounded positive case would be
        # a generic normality quiz mislabeled as competency training.
        if not any(entry["targetPresent"] for entry in entries):
            entries = []
        entries.sort(
            key=lambda entry: (
                not entry["targetPresent"],
                (0, int(entry["caseId"]))
                if entry["caseId"].isdigit()
                else (1, entry["caseId"]),
            )
        )
        pool_cache[key] = entries
        return entries

    def owned(
        campaign_id: str, authorization: str | None, session_cookie: str | None
    ) -> dict[str, Any]:
        campaign = campaign_store.get_campaign(campaign_id)
        learner = resolve_learner(authorization, "demo", session_cookie)
        if not campaign or campaign.get("learnerId") != learner:
            raise HTTPException(status_code=404, detail="Training campaign not found")
        return campaign

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
            task = build_subskill_task(
                case_id=str(pending),
                case_concept=str(campaign["conceptId"]),
                subskill=str(campaign["subskill"]),
                case_focus=str(slot["caseFocus"]),
                contrast_family=_contrast_family(str(campaign["conceptId"])),
            ) if slot else None
            current = {
                "kind": "pending",
                "slot": _public_pending_slot(slot) if slot else None,
                "case": blind_summary(case_summary(case)),
                "packet": blind_packet(packet_provider(case)),
                "task": task.public if task else None,
            }
        elif feedback:
            case = repo.get_case(feedback)
            slot = campaign_store.get_slot_for_case(campaign["campaignId"], feedback)
            answer = campaign_store.get_answer(campaign["campaignId"], feedback)
            if not _is_training_case(case, campaign["conceptId"], campaign["subskill"]):
                raise HTTPException(status_code=409, detail="Training feedback case failed its audited source contract")
            if case and answer:
                task = build_subskill_task(
                    case_id=str(feedback),
                    case_concept=str(campaign["conceptId"]),
                    subskill=str(campaign["subskill"]),
                    case_focus=str(slot["caseFocus"]),
                    contrast_family=_contrast_family(str(campaign["conceptId"])),
                ) if slot else None
                current = {
                    "kind": "feedback",
                    "slot": slot,
                    "case": blind_summary(case_summary(case)),
                    "packet": packet_provider(case),
                    "answer": answer,
                    "task": task.public if task else None,
                }
        return {
            "campaign": _public_campaign(campaign),
            "current": current,
            "summary": campaign_store.summary(campaign["campaignId"]),
        }

    @router.get("/pool")
    def pool(conceptId: str = Query(min_length=1), subskill: str = Query(default="recognize")) -> dict[str, Any]:
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
        }

    @router.post("")
    def start(
        body: TrainingCampaignStartBody,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        if body.subskill not in ALLOWED_SUBSKILLS:
            raise HTTPException(status_code=422, detail="Unknown Training subskill")
        learner = resolve_learner(authorization, body.learnerId, session_cookie)
        active = campaign_store.get_active(learner)
        if active and not body.replaceActive:
            raise HTTPException(
                status_code=409,
                detail={"code": "active_training_campaign", "campaignId": active["campaignId"]},
            )
        if active:
            campaign_store.abandon(active["campaignId"])
        entries = eligible_pool(body.conceptId, body.subskill)
        if not entries:
            raise HTTPException(status_code=409, detail="No eligible distinct audited waveform ECGs support this competency")
        plan = _build_plan(
            entries,
            min(body.length, len(entries)),
            reserve_transfer_roles={"target", "mimic"}
            if body.subskill == "discriminate" else None,
        )
        learning_store.ensure_profile(learner)
        campaign = campaign_store.create_campaign(
            learner, body.conceptId, body.subskill, body.length, len(entries), plan,
            context_key=body.contextKey,
        )
        campaign = campaign_store.claim_next(campaign["campaignId"]) or campaign
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
        prior = campaign_store.get_answer(campaign_id, body.caseId)
        if prior:
            response = payload(campaign_store.get_campaign(campaign_id))
            response.update({"answer": prior, "replay": True})
            return response
        if campaign.get("pendingCaseId") != body.caseId:
            raise HTTPException(
                status_code=409,
                detail={"code": "training_case_not_pending", "pendingCaseId": campaign.get("pendingCaseId")},
            )
        case = repo.get_case(body.caseId)
        if not _is_training_case(case, campaign["conceptId"], campaign["subskill"]):
            raise HTTPException(status_code=409, detail="Training submissions require a source-contracted Tier A/B waveform ECG")
        slot = campaign_store.get_slot_for_case(campaign_id, body.caseId)
        if not slot:
            raise HTTPException(status_code=409, detail="Training slot not found")

        concept = campaign["conceptId"]
        subskill = campaign["subskill"]
        receipt_concept = _receipt_concept(campaign)
        if body.receiptConcept and body.receiptConcept != receipt_concept:
            raise HTTPException(
                status_code=422,
                detail="The submitted receipt target does not match the server-owned campaign contract",
            )
        expected = _expected_answer(case, concept, subskill)
        focus_grounded = _focus_is_grounded(case, slot["caseFocus"], subskill)
        classification_correct = expected is not None and body.selectedAnswer == expected and focus_grounded
        evidence_valid, trace_native = _evidence_valid(
            case, receipt_concept, subskill, body.viewerTaskEvidence, body.evidenceNote
        )
        task_contract = build_subskill_task(
            case_id=body.caseId,
            case_concept=concept,
            subskill=subskill,
            case_focus=str(slot["caseFocus"]),
            contrast_family=_contrast_family(concept),
        )
        task_complete = True
        task_score = 1.0 if evidence_valid else 0.0
        evidence_source = "trace_native" if trace_native else "response"
        if subskill in {"discriminate", "explain_mechanism"}:
            task_complete = bool(task_contract and body.subskillTaskAnswer)
            evidence_valid = bool(
                task_complete
                and task_contract
                and body.subskillTaskAnswer == task_contract.correct_answer
            )
            task_score = 1.0 if evidence_valid else 0.0
            evidence_source = task_contract.evidence_source if task_contract else "response"
        elif subskill == "calibrate_confidence":
            task_complete = task_contract is not None
            task_score, evidence_valid = calibration_grade(
                body.confidence, classification_correct
            )
            evidence_source = "confidence_commit"

        subskill_correct = (
            evidence_valid
            if subskill == "calibrate_confidence"
            else classification_correct and evidence_valid
        )
        misconceptions: list[str] = []
        if not classification_correct:
            misconceptions.append(f"target_status_error:{concept}")
        if task_complete and not evidence_valid:
            misconceptions.append(f"subskill_task_error:{subskill}")

        structured = StructuredInterpretation(
            framework="clerkship",
            selectedConcepts=[concept] if body.selectedAnswer == "present" else [],
        )
        attempt = AttemptRequest(
            learnerId=campaign["learnerId"],
            caseId=body.caseId,
            mode="concept_practice",
            focusObjective=concept,
            structuredAnswer=structured,
            freeTextAnswer=(
                f"{concept}: {body.selectedAnswer}."
                + (f" Evidence: {body.evidenceNote.strip()}" if body.evidenceNote.strip() else "")
            ),
            confidence=body.confidence,
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
        }
        exact_receipt_target = receipt_concept == concept
        independently_assessable = bool(
            (subskill in {"localize", "measure"} and trace_native and evidence_valid)
            or (
                subskill == "discriminate"
                and task_complete
                and task_contract
                and task_contract.independently_assessable
            )
            or (
                subskill == "explain_mechanism"
                and task_complete
                and task_contract
                and task_contract.independently_assessable
            )
            or (subskill == "calibrate_confidence" and task_complete)
        )
        independently_assessed = (
            slot["phase"] == "transfer"
            and body.hintsUsed == 0
            and exact_receipt_target
            and independently_assessable
            and (
                subskill in {"discriminate", "explain_mechanism", "calibrate_confidence"}
                or expected == "present"
                or concept in MEASUREMENT_TARGETS
            )
            and focus_grounded
        )
        event = learning_store.save_guided_learning_event(
            campaign["learnerId"],
            {
                "eventKey": f"train:{campaign_id}:{slot['position']}:{body.caseId}:{subskill}",
                "_serverVerifiedScoring": True,
                "moduleId": "train",
                "sceneId": f"{receipt_concept}:{slot['phase']}",
                "interactionId": f"{body.caseId}:{subskill}",
                "concept": receipt_concept,
                "subskills": [subskill],
                "score": task_score if subskill == "calibrate_confidence" else (1.0 if subskill_correct else 0.0),
                "correct": subskill_correct,
                "attempts": 1,
                "assistance": "scaffolded" if body.hintsUsed else "independent",
                "hintsUsed": body.hintsUsed,
                "confidence": body.confidence,
                "evidenceLevel": "independent_transfer" if independently_assessed else "guided",
                "trainingPhase": slot["phase"],
                "evidenceSource": evidence_source,
                "caseId": body.caseId,
                "caseProvenance": "real_eligible",
                "caseEligible": exact_receipt_target
                and focus_grounded
                and _is_training_case(case, concept, subskill),
                "misconceptions": misconceptions,
                "_retentionVerified": independently_assessed,
                "_retentionMorphologyKey": retention_morphology_key(case),
            },
        )
        response_data = {
            "selectedAnswer": body.selectedAnswer,
            "confidence": body.confidence,
            "hintsUsed": body.hintsUsed,
            "evidenceNote": body.evidenceNote,
            "viewerTaskEvidence": body.viewerTaskEvidence,
            "subskillTaskAnswer": body.subskillTaskAnswer,
            "expectedAnswer": expected,
            "structuredAnswer": structured.model_dump(),
            "freeTextAnswer": attempt.freeTextAnswer,
        }
        summary = {
            "position": slot["position"],
            "caseId": body.caseId,
            "phase": slot["phase"],
            "correct": subskill_correct,
            "classificationCorrect": classification_correct,
            "focusGrounded": focus_grounded,
            "selectedResponse": body.selectedAnswer,
            "confidence": body.confidence,
            "hintsUsed": body.hintsUsed,
            "evidenceLevel": event["effectiveEvidenceLevel"],
            "misconceptions": misconceptions,
        }
        recorded = campaign_store.record_answer(
            campaign_id=campaign_id, case_id=body.caseId, response=response_data,
            # Deterministic grading and evidence persistence never wait for an
            # LLM. Post-commit TutorChat remains available on explicit use.
            grade=grade, tutor=None, receipt=event, summary=summary,
            confidence=body.confidence, hints_used=body.hintsUsed,
        )
        if recorded["status"] == "replay":
            response = payload(campaign_store.get_campaign(campaign_id))
            response.update({"answer": recorded["answer"], "replay": True})
            return response
        if recorded["status"] != "recorded":
            raise HTTPException(status_code=409, detail="Training case is no longer pending")
        response = payload(campaign_store.get_campaign(campaign_id))
        response.update({"answer": recorded["answer"], "replay": False})
        return response

    @router.post("/{campaign_id}/abandon")
    def abandon(
        campaign_id: str,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        owned(campaign_id, authorization, session_cookie)
        return payload(campaign_store.abandon(campaign_id))

    return router
