"""Clinical Decisions "shift" sessions — start / serve-next / grade-and-record / report.

Mirrors the shape of ``app.review`` but for situation-framed item sets. Serving is
no-repeat within a lane; Learn tier is untimed; Shift tier returns the §16D clock spec
per item so the frontend drives the timer. The end-of-shift report surfaces a triage-style
calibration label (§16C/§16-4).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable

from ..adaptive import _stale_bonus, independent_subskill_index, priority_exact_row
from . import grounding
from .clinical_grading import grade_clinical_answer
from .constants import clock_for
from .provenance import assert_learner_item_provenance
from .schemas import ClinicalAnswer, ClinicalCaseItem

PacketProvider = Callable[[str], dict[str, Any] | None]
SERVING_STATUS = "harness_pass"
SERVING_LABEL = "automated-screened formative"

# A metadata label cannot turn a scheduled outpatient encounter into an ED
# case. These phrases describe workflows that are categorically incompatible
# with an emergency-department shift, even if generated content was mistakenly
# tagged ``situation=ed``. Acute/stable ED presentations (for example stable
# SVT) remain valid; this guard only rejects explicit setting contradictions.
_ED_OUTPATIENT_CONTEXT_CUES = (
    "pre-operative",
    "preoperative",
    "pre-op",
    "routine clearance",
    "medication-review visit",
    "medication review visit",
    "routine follow-up",
    "routine follow up",
    "clinic visit",
    "outpatient",
)


def _lane_compatible(item: ClinicalCaseItem, lane: str) -> bool:
    """Return whether authored context is semantically compatible with a lane."""
    if item.situation != lane:
        return False
    if lane != "ed":
        return True
    context = " ".join(filter(None, (item.stem, item.prompt))).lower()
    return not any(cue in context for cue in _ED_OUTPATIENT_CONTEXT_CUES)


def _runtime_provenance_ok(
    item: ClinicalCaseItem, packet_provider: PacketProvider
) -> bool:
    """Fail closed if a stale or injected row reaches the runtime pool."""

    assert_learner_item_provenance(item, packet_provider)
    return True


# --- blinding ---------------------------------------------------------------------
def blind_clinical_item(
    item: ClinicalCaseItem, *, reveal_context: bool = True
) -> dict[str, Any]:
    """Strip answer keys and, until first-look commit, all authored context."""
    data = item.model_dump()
    data.pop("evidence_manifest", None)
    data.pop("application_objectives", None)
    data.pop("disclosed_objectives", None)
    data.pop("acuity_tier", None)
    # roi target location is server-side; expose only which leads are clickable.
    roi = data.pop("roi_target", None)
    if roi:
        data["clickable_leads"] = roi.get("leads", [])
        data["click_target_type"] = roi.get("target_type")
    for opt in data.get("options", []):
        for hidden in ("answer_class", "axis_scores", "required_safety_tokens", "parsed"):
            opt.pop(hidden, None)
    for step in data.get("steps", []):
        for so in step.get("options", []):
            so.pop("correct", None)
    for line in data.get("machine_read", []):
        line.pop("bad", None)
    data.pop("difficulty_vector", None)
    data.pop("provenance", None)
    data.pop("validation_status", None)
    if not reveal_context:
        # This is a transport boundary, not merely a hidden React panel: authored
        # symptoms, vitals, prompts, choices, and machine text do not reach the
        # browser until the learner persists an ECG-only first look.
        for field in ("stem", "chips", "prompt", "options", "steps", "machine_read"):
            data.pop(field, None)
        data.pop("clickable_leads", None)
        data.pop("click_target_type", None)
    return data


def clock_spec(item: ClinicalCaseItem, tier: str) -> dict[str, Any]:
    if tier == "learn":
        return {"untimed": True}
    orient, decide = clock_for(item.situation, item.question_type)
    return {"untimed": False, "orientSec": orient, "decideSec": decide}


def _phase_duration(item: ClinicalCaseItem, tier: str, phase: str) -> int | None:
    if tier == "learn":
        return None
    orient, decide = clock_for(item.situation, item.question_type)
    return orient if phase == "orient" else decide


# --- session flow -----------------------------------------------------------------
def start_shift(
    store,
    learner_id: str,
    lane: str,
    tier: str = "shift",
    length: int = 5,
    focus_objective: str | None = None,
    focus_subskill: str | None = None,
) -> dict[str, Any]:
    requested = int(length)
    session_id = store.create_shift_session(
        learner_id, lane, tier, requested, focus_objective, focus_subskill
    )
    return store.get_shift_session(session_id)


def start_shift_with_capacity(
    store,
    item_store,
    packet_provider: PacketProvider,
    learner_id: str,
    lane: str,
    tier: str = "shift",
    length: int = 5,
    focus_objective: str | None = None,
    focus_subskill: str | None = None,
) -> dict[str, Any]:
    """Start a lane bounded by its automated-screened formative ECGs."""
    requested = int(length)
    available = len({
        item.ecg_id
        for item in item_store.list_for_serving(situation=lane, status=SERVING_STATUS)
        if _lane_compatible(item, lane) and _runtime_provenance_ok(item, packet_provider)
    })
    effective = min(requested, available)
    if available < requested:
        reason = (
            f"Requested {requested} case(s); {available} distinct {SERVING_LABEL} ECG(s) are available "
            f"in the {lane} lane. This session is capped at {effective}."
        )
    else:
        reason = (
            f"Requested {requested} case(s); {available} distinct {SERVING_LABEL} ECG(s) are available "
            f"in the {lane} lane."
        )
    session_id = store.create_shift_session(
        learner_id,
        lane,
        tier,
        effective,
        focus_objective,
        focus_subskill,
        requested_length=requested,
        available_length=available,
        length_reason=reason,
    )
    return store.get_shift_session(session_id)


def _item_targets(item: ClinicalCaseItem) -> list[str]:
    return [c.objective_id for c in item.evidence_manifest.ecg_supports]


def _clinical_competency_events(
    item: ClinicalCaseItem,
    packet: dict[str, Any],
    grade: dict[str, Any],
    answer: ClinicalAnswer,
) -> list[dict[str, Any]]:
    """Translate only exact server grades into formative competency cells."""

    supported = grounding.supported_objectives(packet)
    events: list[dict[str, Any]] = []
    timed_out = bool(grade.get("timedOut"))
    axes = grade.get("axisScores") or {}
    action_correct = bool(
        not timed_out
        and grade.get("answerClass") in {"ideal", "acceptable"}
        and not grade.get("safetyFlags")
    )
    action_score = float(axes.get("clinical_decision", grade.get("score", 0.0)))
    if item.question_type == "stepwise":
        # A correct disposition guessed after an incorrect ECG sequence is not
        # successful application of that ECG concept.  Preserve the attempt, but
        # require both the interpretation chain and decision for positive credit.
        sequence_score = float(axes.get("ecg_sequence", 0.0))
        action_correct = bool(action_correct and sequence_score >= 1.0)
        action_score = min(action_score, sequence_score)
    for concept in item.application_objectives:
        if concept not in supported:
            continue
        events.append({
            "concept": concept,
            "subskill": "apply_in_context",
            "score": 0.0 if timed_out else action_score,
            "correct": action_correct,
            "confidence": answer.confidence,
            "caseId": item.ecg_id,
            "itemId": item.item_id,
            "evidenceSource": "clinical_action_server_grade",
        })

    # A point is localization evidence only when the server matched it against
    # the packet ROI.  Merely viewing a highlighted ROI or answering an MCQ never
    # reaches this path.
    if item.roi_target and item.roi_target.concept in supported:
        exact_score: float | None = None
        if item.question_type == "click":
            exact_score = float(axes.get("region_accuracy", 0.0))
        elif item.question_type == "spoterror":
            exact_score = float(axes.get("proof_on_trace", 0.0))
        if exact_score is not None:
            events.append({
                "concept": item.roi_target.concept,
                "subskill": "localize",
                "score": 0.0 if timed_out else exact_score,
                "correct": bool(not timed_out and exact_score >= 1.0),
                "confidence": answer.confidence,
                "caseId": item.ecg_id,
                "itemId": item.item_id,
                "evidenceSource": "clinical_trace_roi_server_grade",
            })
    return events


def _score_item(
    item: ClinicalCaseItem,
    mastery: dict[str, Any],
    exact_mastery: dict[str, list[dict[str, Any]]],
    recent_ecgs: set[str],
) -> float:
    """Mastery-driven priority (mirrors adaptive.next_case): weak / stale / high-confidence-wrong
    target concepts score higher, so a struggling student keeps getting that pathology until
    mastery rises; the same tracing is de-prioritized to keep variety."""
    targets = _item_targets(item)
    # Key on the item's WEAKEST covered concept (max over targets), not the sum — otherwise a
    # multi-concept item always outranks the single-concept case on the pathology you're failing.
    best = 0.0
    for obj in targets:
        preferred = {"recognize"}
        if item.question_type == "stepwise":
            preferred.add("synthesize")
        if item.roi_target and item.roi_target.concept == obj:
            preferred.add("localize")
        exact = priority_exact_row(
            exact_mastery.get(obj, []),
            as_of=datetime.now(UTC),
            preferred_subskills=preferred,
        )
        # Training/Rapid exact receipts are authoritative. Legacy objective
        # mastery remains only for profiles that have no independent exact cell
        # for this objective yet.
        row = exact or mastery.get(obj, {})
        mastery_score = float(
            row.get("independentMastery", 0.15)
            if exact
            else row.get("mastery", 0.25)
        )
        attempts = int(
            row.get("independentAttempts", 0) if exact else row.get("attempts", 0)
        )
        signal = (1.0 - mastery_score) * 1.6 + _stale_bonus(row.get("lastPracticedAt"))
        signal += min(0.5, int(row.get("highConfidenceWrong", 0)) * 0.12)
        if exact and row.get("isDue"):
            signal += 1.0 + min(0.6, float(row.get("overdueDays", 0.0)) * 0.08)
        if exact:
            signal += min(0.35, int(row.get("lapses", 0)) * 0.1)
        if attempts < 2:
            signal += 0.25
        best = max(best, signal)
    value = best if targets else 0.1
    if item.ecg_id in recent_ecgs:
        value -= 0.9  # avoid repeating the exact tracing
    return value


def _select_next(
    store,
    item_store,
    packet_provider: PacketProvider,
    lane: str,
    served: list[str],
    served_ecgs: set[str],
    learner_id: str,
    focus_objective: str | None = None,
    focus_subskill: str | None = None,
) -> ClinicalCaseItem | None:
    candidates = [
        item for item in item_store.list_for_serving(situation=lane, status=SERVING_STATUS)
        if _lane_compatible(item, lane)
        and item.item_id not in served
        and item.ecg_id not in served_ecgs
        and _runtime_provenance_ok(item, packet_provider)
    ]
    if not candidates:
        return None
    # A guided handoff must actually begin on a compatible clinical item. After
    # that first transfer item, normal adaptive/interleaved selection resumes.
    if focus_objective and not served:
        focused = [item for item in candidates if focus_objective in _item_targets(item)]
        if focus_subskill == "apply_in_context":
            focused = [
                item for item in focused
                if focus_objective in item.application_objectives
            ]
        elif focus_subskill == "localize":
            focused = [
                item for item in focused
                if item.question_type in {"click", "spoterror"}
                and item.roi_target is not None
                and item.roi_target.concept == focus_objective
            ]
        elif focus_subskill:
            # Clinical currently issues exact server receipts only for its
            # authored action cells and packet-ROI localization cells.
            focused = []
        if not focused:
            # Target fidelity is a mastery-integrity boundary. An unrelated item
            # must never be served under the requested handoff label.
            return None
        candidates = focused
    profile = store.ensure_profile(learner_id)
    mastery = {row["objective"]: row for row in profile["mastery"]}
    exact_mastery = independent_subskill_index(profile)
    recent_ecgs = set(store.recent_case_ids(learner_id))
    return max(
        candidates,
        key=lambda it: _score_item(it, mastery, exact_mastery, recent_ecgs),
    )


def _serve_payload(
    item: ClinicalCaseItem,
    packet_provider: PacketProvider,
    session: dict[str, Any],
) -> dict[str, Any]:
    context_revealed = bool(session.get("contextRevealed"))
    blinded = blind_clinical_item(item, reveal_context=context_revealed)
    assert_learner_item_provenance(item, packet_provider)
    packet = packet_provider(item.ecg_id) or {}
    if context_revealed and item.roi_target:
        # The response surface needs a neutral waveform concept to validate
        # pointer and keyboard placement. Expose the parsed ROI (for example,
        # qrs_complex), never the pathology answer key in roi_target.concept.
        requested = item.roi_target.concept
        acceptable = [grounding.CONCEPT_TO_ROI.get(requested), requested]
        allowed_leads = set(item.roi_target.leads)
        roi_concept = next(
            (
                roi.get("concept")
                for concept in acceptable
                if concept
                for roi in grounding.rois(packet)
                if roi.get("concept") == concept
                and (not allowed_leads or roi.get("lead") in allowed_leads)
            ),
            None,
        )
        if roi_concept:
            blinded["click_roi_concept"] = roi_concept
    blinded["tracing_provenance"] = "real_deidentified_ecg"
    blinded["context_provenance"] = "authored_simulation"
    blinded["learning_evidence"] = "formative_only"
    blinded["content_label"] = (
        "Automated-screened authored vignette · real de-identified ECG · formative only · pending named clinician sign-off"
    )
    clock = {
        **clock_spec(item, session["tier"]),
        "orientStartedAt": session.get("orientStartedAt"),
        "orientDeadlineAt": session.get("orientDeadlineAt"),
        "decideStartedAt": session.get("decideStartedAt"),
        "decideDeadlineAt": session.get("decideDeadlineAt"),
    }
    active_phase = "decide" if context_revealed else "orient"
    clock["activePhase"] = active_phase
    clock["phaseStartedAt"] = clock.get(f"{active_phase}StartedAt")
    clock["phaseDeadlineAt"] = clock.get(f"{active_phase}DeadlineAt")
    return {
        "item": blinded,
        "itemId": item.item_id,
        "index": session["position"],
        "total": session["length"],
        "requested": session.get("requestedLength", session["length"]),
        "available": session.get("availableDistinctEcgs", session["length"]),
        "lengthReason": session.get("lengthReason"),
        "done": False,
        "contextRevealed": context_revealed,
        "firstLook": session.get("firstLook") if context_revealed else None,
        "clock": clock,
    }


def activate_shift_phase(
    store,
    item_store,
    packet_provider: PacketProvider,
    session_id: str,
    item_id: str,
    phase: str,
) -> dict[str, Any] | None:
    """Activate a phase only after the browser reports that phase ready."""
    session = store.get_shift_session(session_id)
    if not session:
        return None
    if session.get("pendingItemId") != item_id:
        return {"error": "not_pending", "pendingItemId": session.get("pendingItemId")}
    item = item_store.get_item(item_id)
    if item is None:
        return None
    assert_learner_item_provenance(item, packet_provider)
    result = store.activate_shift_phase(
        session_id,
        item_id,
        phase,
        _phase_duration(item, session["tier"], phase),
    )
    if result["status"] in {"missing", "not_pending", "phase_not_ready", "invalid_phase"}:
        return {"error": result["status"], "pendingItemId": result.get("pendingItemId")}
    refreshed = store.get_shift_session(session_id)
    return _serve_payload(item, packet_provider, refreshed) if refreshed else None


def reveal_shift_context(
    store,
    item_store,
    packet_provider: PacketProvider,
    session_id: str,
    item_id: str,
    answer: ClinicalAnswer,
) -> dict[str, Any] | None:
    """Commit first look exactly once, then return the context-bearing item."""
    session = store.get_shift_session(session_id)
    if not session:
        return None
    if session.get("pendingItemId") != item_id:
        return {"error": "not_pending", "pendingItemId": session.get("pendingItemId")}
    if answer.first_look_finding is None or answer.first_look_confidence is None:
        return {"error": "first_look_required"}
    item = item_store.get_item(item_id)
    if item is None:
        return None
    assert_learner_item_provenance(item, packet_provider)
    result = store.reveal_shift_context(
        session_id,
        item_id,
        {
            "firstLookFinding": answer.first_look_finding,
            "firstLookConfidence": answer.first_look_confidence,
        },
        _phase_duration(item, session["tier"], "decide"),
    )
    if result["status"] in {"missing", "not_pending", "phase_not_activated"}:
        return {
            "error": (
                "not_pending" if result["status"] == "not_pending" else result["status"]
            ),
            "pendingItemId": result.get("pendingItemId"),
        }
    revealed_session = store.get_shift_session(session_id)
    payload = _serve_payload(item, packet_provider, revealed_session)
    payload["replay"] = result["status"] == "replay"
    return payload


def next_shift_item(store, item_store, packet_provider: PacketProvider, session_id: str) -> dict[str, Any] | None:
    session = store.get_shift_session(session_id)
    if not session:
        return None
    if session.get("feedbackItemId"):
        # Advancing is the explicit acknowledgement boundary. Until this call,
        # refresh and active discovery reconstruct the exact feedback screen.
        session = store.acknowledge_shift_feedback(session_id)
        if not session:
            return None
    # Refresh/resume is stable: an unsubmitted item remains the one and only
    # current item until it has an answer-ledger row.
    if session.get("pendingItemId"):
        pending = item_store.get_item(session["pendingItemId"])
        if pending is not None:
            return _serve_payload(pending, packet_provider, session)
    if session["position"] >= session["length"] or session["status"] == "complete":
        return {
            "item": None,
            "index": session["position"],
            "total": session["length"],
            "requested": session.get("requestedLength", session["length"]),
            "available": session.get("availableDistinctEcgs", session["length"]),
            "lengthReason": session.get("lengthReason"),
            "done": True,
        }
    item = _select_next(
        store,
        item_store,
        packet_provider,
        session["lane"],
        session["served"],
        set(session.get("servedEcgs", [])),
        session["learnerId"],
        session.get("focusObjective"),
        session.get("focusSubskill"),
    )
    if item is None:
        store.set_shift_status(session_id, "complete")
        focus = session.get("focusObjective")
        focus_subskill = session.get("focusSubskill")
        focus_subskill_label = (
            f" x {focus_subskill.replace('_', ' ')}" if focus_subskill else ""
        )
        reason = (
            f"No {SERVING_LABEL} {focus.replace('_', ' ')}"
            f"{focus_subskill_label} "
            f"clinical item is available in the {session['lane']} lane. "
            "No substitute case or competency receipt was created."
            if focus and not session["served"]
            else f"No additional {SERVING_LABEL} clinical item is available in this lane."
        )
        return {
            "item": None,
            "index": session["position"],
            "total": session["length"],
            "requested": session.get("requestedLength", session["length"]),
            "available": session.get("availableDistinctEcgs", session["length"]),
            "lengthReason": session.get("lengthReason"),
            "done": True,
            "reason": reason,
        }
    claimed = store.set_shift_pending(session_id, item.item_id)
    if not claimed:
        return None
    # If two `next` requests raced, render whichever item won the persisted claim.
    pending_id = claimed.get("pendingItemId")
    persisted = item if pending_id == item.item_id else item_store.get_item(pending_id)
    return _serve_payload(persisted, packet_provider, claimed) if persisted else None


def grade_and_record(
    store, item_store, packet_provider: PacketProvider, session_id: str, item_id: str, answer: ClinicalAnswer
) -> dict[str, Any] | None:
    session = store.get_shift_session(session_id)
    if not session:
        return None
    prior = store.get_shift_answer(session_id, item_id)
    if prior:
        return {"grade": prior["grade"], "replay": True, "answerId": prior["answerId"]}
    if session.get("pendingItemId") != item_id:
        return {
            "error": "not_pending",
            "pendingItemId": session.get("pendingItemId"),
        }
    if not session.get("contextRevealed") or not session.get("firstLook"):
        return {"error": "context_not_revealed", "pendingItemId": item_id}
    item = item_store.get_item(item_id)
    if item is None:
        return None
    packet = assert_learner_item_provenance(item, packet_provider)
    timing = store.claim_shift_submission_timing(session_id, item_id)
    if timing["status"] in {"missing", "not_pending", "context_not_revealed"}:
        return {
            "error": timing["status"],
            "pendingItemId": timing.get("pendingItemId"),
        }
    # The persisted pre-context commitment is authoritative. A caller cannot
    # revise it inside the final answer payload after seeing the vignette. The
    # same applies to all timing: the server-owned phase timestamps replace any
    # forged answerTimeMs/timedOut values in the request.
    committed = session["firstLook"]
    answer = answer.model_copy(
        update={
            "first_look_finding": committed.get("firstLookFinding"),
            "first_look_confidence": committed.get("firstLookConfidence"),
            "answer_time_ms": timing["answerTimeMs"],
            # There is no independent server event for a confidence-only click;
            # retaining a client duration would falsely imply verified timing.
            "confidence_time_ms": None,
            "timed_out": timing["timedOut"],
        }
    )
    grade = grade_clinical_answer(item, packet, answer)
    correct = not grade["missedObjectives"] and grade["score"] >= 0.6
    calibration_event = {
        "itemId": item_id,
        "score": grade["score"],
        "correct": correct,
        "decideMs": timing["answerTimeMs"],
        **(grade.get("calibrationEvent") or {}),
    }
    recorded = store.record_shift_answer(
        session_id=session_id,
        item_id=item_id,
        ecg_id=item.ecg_id,
        response={
            **answer.model_dump(mode="json"),
            "serverStartedAt": timing["startedAt"],
            "serverDeadlineAt": timing["deadlineAt"],
            "serverSubmittedAt": timing["submittedAt"],
        },
        grade=grade,
        correct=correct,
        confidence=answer.confidence or 3,
        calibration_event=None if session["tier"] == "learn" else calibration_event,
        competency_events=_clinical_competency_events(item, packet, grade, answer),
    )
    if recorded["status"] == "not_pending":
        # A concurrent request may have committed this answer after the preflight.
        prior = store.get_shift_answer(session_id, item_id)
        if prior:
            return {"grade": prior["grade"], "replay": True, "answerId": prior["answerId"]}
        return {"error": "not_pending", "pendingItemId": recorded.get("pendingItemId")}
    if recorded["status"] == "context_not_revealed":
        return {"error": "context_not_revealed", "pendingItemId": recorded.get("pendingItemId")}
    if recorded["status"] == "missing":
        return None
    stored = recorded["answer"]
    return {
        "grade": stored["grade"],
        "replay": recorded["status"] == "replay",
        "answerId": stored["answerId"],
    }


def shift_lifecycle_payload(
    store,
    item_store,
    packet_provider: PacketProvider,
    session: dict[str, Any] | None,
) -> dict[str, Any]:
    """Reconstruct the exact owned Clinical presentation after a refresh/login."""
    if not session:
        return {"session": None, "state": "picker", "current": None, "grade": None, "report": None}
    pending_id = session.get("pendingItemId")
    if pending_id:
        item = item_store.get_item(pending_id)
        current = _serve_payload(item, packet_provider, session) if item else None
        return {
            "session": session,
            "state": "decide" if session.get("contextRevealed") else "orient",
            "current": current,
            "grade": None,
            "answer": None,
            "report": None,
        }
    feedback_id = session.get("feedbackItemId")
    if feedback_id:
        stored = store.get_shift_answer(session["sessionId"], feedback_id)
        item = item_store.get_item(feedback_id)
        if stored and item:
            feedback_session = {
                **session,
                "position": max(0, int(session["position"]) - 1),
                "contextRevealed": True,
                "firstLook": {
                    "firstLookFinding": stored["response"].get("first_look_finding"),
                    "firstLookConfidence": stored["response"].get("first_look_confidence"),
                },
            }
            return {
                "session": session,
                "state": "feedback",
                "current": _serve_payload(item, packet_provider, feedback_session),
                "grade": stored["grade"],
                "answer": {
                    "firstLookFinding": stored["response"].get("first_look_finding"),
                    "firstLookConfidence": stored["response"].get("first_look_confidence"),
                    "selectedOptionId": stored["response"].get("selected_option_id"),
                    "click": stored["response"].get("click"),
                    "machineLineId": stored["response"].get("machine_line_id"),
                    "confidence": stored["response"].get("confidence"),
                    "answerTimeMs": stored["response"].get("answer_time_ms"),
                    "confidenceTimeMs": stored["response"].get("confidence_time_ms"),
                    "timedOut": stored["response"].get("timed_out", False),
                    "stepAnswers": stored["response"].get("step_answers") or [],
                },
                "report": None,
            }
    if session.get("status") == "complete":
        return {
            "session": session,
            "state": "report",
            "current": None,
            "grade": None,
            "answer": None,
            "report": shift_report(store, session["sessionId"]),
        }
    return {"session": session, "state": "picker", "current": None, "grade": None, "answer": None, "report": None}


# --- end-of-shift report ----------------------------------------------------------
_MIN_CASES_FOR_LABEL = 8  # round-3 audit: a 5-case label flips on one item; show counts until enough data


def calibration_label(events: list[dict[str, Any]]) -> str:
    n = len(events)
    if n == 0:
        return "no calibration data"
    over = sum(1 for e in events if e.get("overTriage"))
    under = sum(1 for e in events if e.get("underTriage") or e.get("unsafe"))
    hcw = sum(1 for e in events if e.get("highConfidenceWrong"))
    if n < _MIN_CASES_FOR_LABEL:
        return f"early signal — {over} over-call(s), {under} under-call(s) (need {_MIN_CASES_FOR_LABEL}+ cases to label)"
    if hcw >= max(1, round(n * 0.3)):
        return "confident-but-brittle"
    if under > over and under >= max(1, round(n * 0.3)):
        return "risky under-caller"
    if over > under and over >= max(1, round(n * 0.3)):
        return "cautious over-caller"
    return "well-calibrated"


def shift_report(store, session_id: str) -> dict[str, Any] | None:
    session = store.get_shift_session(session_id)
    if not session:
        return None
    answers = store.get_shift_answers(session_id)
    events = [row["calibrationEvent"] for row in answers if row["calibrationEvent"] is not None]
    answered = len(answers)
    correct = sum(1 for row in answers if row["correct"])
    decide_times = [row["answerTimeMs"] for row in answers if row["answerTimeMs"] is not None]
    best_streak = streak = 0
    for row in answers:
        streak = streak + 1 if row["correct"] else 0
        best_streak = max(best_streak, streak)
    return {
        "sessionId": session_id,
        "lane": session["lane"],
        "tier": session["tier"],
        "answered": answered,
        "length": session["length"],
        "requested": session.get("requestedLength", session["length"]),
        "available": session.get("availableDistinctEcgs", session["length"]),
        "lengthReason": session.get("lengthReason"),
        "accuracy": round(correct / answered, 3) if answered else 0.0,
        "bestStreak": best_streak,
        "avgDecideMs": round(sum(decide_times) / len(decide_times)) if decide_times else None,
        "calibrationLabel": "calibration off (Learn)" if session["tier"] == "learn" else calibration_label(events),
        "status": session["status"],
    }
