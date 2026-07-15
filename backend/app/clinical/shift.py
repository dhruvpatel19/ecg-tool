"""Clinical Decisions "shift" sessions — start / serve-next / grade-and-record / report.

Mirrors the shape of ``app.review`` but for situation-framed item sets. Serving is
no-repeat within a lane; Learn tier is untimed; Shift tier returns the §16D clock spec
per item so the frontend drives the timer. The end-of-shift report surfaces a triage-style
calibration label (§16C/§16-4).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable

from ..adaptive import (
    _stale_bonus,
    formative_application_index,
    independent_subskill_index,
    priority_exact_row,
)
from . import grounding, integrity
from .clinical_grading import grade_clinical_answer
from .constants import clock_for
from .debrief import build_shift_debrief
from .item_reference import public_item_reference
from .provenance import assert_learner_item_provenance
from .schemas import ClinicalAnswer, ClinicalCaseItem
from .tutor_context import shift_tutor_context_reference, tutor_context_reference

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
    fill_in = data.get("fill_in_task")
    if fill_in:
        # The response shape is public; the packet feature and acceptance
        # tolerance are answer-key material and stay server-side until grade.
        fill_in.pop("objective_id", None)
        fill_in.pop("expected_feature", None)
        fill_in.pop("tolerance", None)
    else:
        data.pop("fill_in_task", None)
    matching = data.get("matching_task")
    if matching:
        # Clauses and target labels are public.  Their source classification,
        # packet/manifest references, and correct targets remain server-only
        # until the committed grade is returned.
        for row in matching.get("rows", []):
            for hidden in (
                "source_type", "correct_choice_id", "source_reference", "objective_id"
            ):
                row.pop(hidden, None)
    else:
        data.pop("matching_task", None)
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
        for field in (
            "stem", "chips", "prompt", "options", "steps", "machine_read", "fill_in_task",
            "matching_task",
        ):
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
    session_id = integrity.create_session(
        store,
        learner_id=learner_id,
        lane=lane,
        tier=tier,
        length=requested,
        focus_objective=focus_objective,
        focus_subskill=focus_subskill,
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
    """Start a lane bounded by ECGs that are safe for this learner now.

    The authored bank size is not the learner's usable capacity when a tracing
    is already protected by another live assessment or was recently shown in
    an answer-bearing mode.  Persisting that larger number would create a
    frozen shift that promises more distinct ECGs than selection is allowed to
    serve.  Capacity therefore uses the same owner exposure boundary as the
    per-item selector.
    """
    requested = int(length)
    lane_ecgs = {
        item.ecg_id
        for item in item_store.list_for_serving(situation=lane, status=SERVING_STATUS)
        if _lane_compatible(item, lane) and _runtime_provenance_ok(item, packet_provider)
    }
    owner_exposures = integrity.live_owner_exposures(store, learner_id)
    available = len(lane_ecgs - owner_exposures)
    held_out = len(lane_ecgs & owner_exposures)
    effective = min(requested, available)
    exposure_note = (
        f" {held_out} additional lane ECG(s) are temporarily held out because "
        "they are active or were recently shown."
        if held_out
        else ""
    )
    if available < requested:
        reason = (
            f"Requested {requested} case(s); {available} distinct {SERVING_LABEL} ECG(s) are available "
            f"for this learner in the {lane} lane.{exposure_note} "
            f"This session is capped at {effective}."
        )
    else:
        reason = (
            f"Requested {requested} case(s); {available} distinct {SERVING_LABEL} ECG(s) are available "
            f"for this learner in the {lane} lane.{exposure_note}"
        )
    session_id = integrity.create_session(
        store,
        learner_id=learner_id,
        lane=lane,
        tier=tier,
        length=effective,
        focus_objective=focus_objective,
        focus_subskill=focus_subskill,
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

    task = item.fill_in_task
    if (
        item.question_type == "fillin"
        and task is not None
        and task.objective_id in supported
    ):
        measurement_score = float(axes.get("measurement_accuracy", 0.0))
        events.append({
            "concept": task.objective_id,
            "subskill": "measure",
            "score": 0.0 if timed_out else measurement_score,
            "correct": bool(not timed_out and measurement_score >= 1.0),
            "confidence": answer.confidence,
            "caseId": item.ecg_id,
            "itemId": item.item_id,
            "evidenceSource": "clinical_measurement_server_grade",
        })
    return events


def _formative_application_priority(
    row: dict[str, Any] | None,
    *,
    unseen_case_count: int,
) -> float:
    """Return teaching priority for one exact application competency.

    This signal is intentionally separate from independent mastery.  It uses
    formative application performance to choose *what to teach next*, while
    leaving recognition mastery and retention state untouched.  A signal is
    actionable only when an unseen application case for the concept remains.
    """

    available = max(0, int(unseen_case_count))
    if available == 0:
        return 0.0

    # A small capacity tie-break favors concepts for which the bank can still
    # provide varied follow-up, without overpowering demonstrated learning need.
    capacity_bonus = min(0.08, max(0, available - 1) * 0.02)
    if row is None:
        # Sample an as-yet-unseen application competency, but keep this below a
        # clear prior miss or high-confidence error.
        return 0.24 + capacity_bonus

    formative_score = max(
        0.0, min(1.0, float(row.get("formativeScore") or 0.0))
    )
    attempts = max(0, int(row.get("attempts") or 0))
    high_confidence_wrong = max(
        0, int(row.get("highConfidenceWrong") or 0)
    )
    weakness = (1.0 - formative_score) * 1.15
    confidence_error = min(0.55, high_confidence_wrong * 0.14)
    recency = _stale_bonus(row.get("lastPracticedAt")) * 0.65
    early_evidence = 0.12 if attempts < 2 else 0.0
    return weakness + confidence_error + recency + early_evidence + capacity_bonus


def _score_item(
    item: ClinicalCaseItem,
    exact_mastery: dict[str, list[dict[str, Any]]],
    recent_ecgs: set[str],
    application_history: dict[str, dict[str, Any]] | None = None,
    unseen_application_counts: dict[str, int] | None = None,
) -> float:
    """Combine independent recognition need with separate application need.

    Recognition is personalized only from exact independent Training/Rapid
    evidence.  Formative Clinical decisions can alter which application case is
    taught next, but never enter that recognition signal or mastery state.
    """
    targets = _item_targets(item)
    # Key on the item's WEAKEST covered concept (max over targets), not the sum — otherwise a
    # multi-concept item always outranks the single-concept case on the pathology you're failing.
    best = 0.0
    for obj in targets:
        preferred = {"recognize"}
        if item.question_type == "stepwise":
            preferred.add("synthesize")
        if item.question_type == "fillin":
            preferred.add("measure")
        if item.roi_target and item.roi_target.concept == obj:
            preferred.add("localize")
        exact = priority_exact_row(
            exact_mastery.get(obj, []),
            as_of=datetime.now(UTC),
            preferred_subskills=preferred,
        )
        # Only exact independent Training/Rapid receipts may personalize
        # Clinical selection. Legacy objective mastery has no evidence-source
        # provenance and may contain historical formative Clinical scores, so a
        # missing exact cell is deliberately neutral rather than a fallback.
        row = exact or {}
        mastery_score = float(row.get("independentMastery", 0.25))
        attempts = int(row.get("independentAttempts", 0))
        signal = (1.0 - mastery_score) * 1.6 + _stale_bonus(row.get("lastPracticedAt"))
        signal += min(0.5, int(row.get("highConfidenceWrong", 0)) * 0.12)
        if exact and row.get("isDue"):
            signal += 1.0 + min(0.6, float(row.get("overdueDays", 0.0)) * 0.08)
        if exact:
            signal += min(0.35, int(row.get("lapses", 0)) * 0.1)
        if attempts < 2:
            signal += 0.25
        best = max(best, signal)
    recognition_value = best if targets else 0.1
    application_value = 0.0
    application_rows = application_history or {}
    for concept in item.application_objectives:
        # When called by the selector this map is the remaining, owner-safe
        # candidate pool.  The default of one keeps direct scoring intuitive:
        # the item being scored is itself one available application case.
        unseen_count = (
            1
            if unseen_application_counts is None
            else int(unseen_application_counts.get(concept, 0))
        )
        application_value = max(
            application_value,
            _formative_application_priority(
                application_rows.get(concept),
                unseen_case_count=unseen_count,
            ),
        )
    value = recognition_value + application_value
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
    live_exposures = integrity.live_owner_exposures(store, learner_id)
    candidates = [
        item for item in item_store.list_for_serving(situation=lane, status=SERVING_STATUS)
        if _lane_compatible(item, lane)
        and item.item_id not in served
        and item.ecg_id not in served_ecgs
        and item.ecg_id not in live_exposures
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
        elif focus_subskill == "measure":
            focused = [
                item for item in focused
                if item.question_type == "fillin"
                and item.fill_in_task is not None
                and item.fill_in_task.objective_id == focus_objective
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
    exact_mastery = independent_subskill_index(profile)
    application_history = formative_application_index(profile)
    unseen_application_ecgs: dict[str, set[str]] = {}
    for candidate in candidates:
        for concept in candidate.application_objectives:
            unseen_application_ecgs.setdefault(concept, set()).add(candidate.ecg_id)
    unseen_application_counts = {
        concept: len(ecg_ids)
        for concept, ecg_ids in unseen_application_ecgs.items()
    }
    recent_ecgs = set(store.recent_case_ids(learner_id))
    return max(
        candidates,
        key=lambda it: _score_item(
            it,
            exact_mastery,
            recent_ecgs,
            application_history,
            unseen_application_counts,
        ),
    )


def _serve_payload(
    item: ClinicalCaseItem,
    packet_provider: PacketProvider,
    session: dict[str, Any],
) -> dict[str, Any]:
    context_revealed = bool(session.get("contextRevealed"))
    blinded = blind_clinical_item(item, reveal_context=context_revealed)
    presented_item_id = public_item_reference(
        str(session.get("pendingItemId") or session.get("feedbackItemId") or item.item_id)
    )
    # Authoring ids intentionally describe scenario families and therefore can
    # contain the diagnosis.  Use only the keyed transport handle in every
    # pre/post-commit browser payload.
    blinded["item_id"] = presented_item_id
    if context_revealed and item.question_type == "stepwise":
        committed_answers = [int(value) for value in (session.get("stepAnswers") or [])]
        public_steps = blinded.pop("steps", [])
        committed_steps = [
            {
                "stepIndex": index,
                "prompt": public_steps[index]["prompt"],
                "answerIndex": answer_index,
                "answerText": public_steps[index]["options"][answer_index]["text"],
            }
            for index, answer_index in enumerate(committed_answers)
            if index < len(public_steps)
            and 0 <= answer_index < len(public_steps[index].get("options") or [])
        ]
        active_index = len(committed_steps)
        active_step = None
        if active_index < len(public_steps):
            active_step = {
                "stepIndex": active_index,
                **public_steps[active_index],
            }
            # The downstream clinical choices are part of the final stage. They
            # are not transported until every ECG interpretation step is locked.
            blinded.pop("options", None)
        blinded["stepwise_state"] = {
            "totalSteps": len(public_steps),
            "committed": committed_steps,
            "active": active_step,
            "finalChoicesRevealed": active_step is None,
        }
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
        "itemId": presented_item_id,
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


def commit_shift_step(
    store,
    item_store,
    packet_provider: PacketProvider,
    session_id: str,
    item_id: str,
    step_index: int,
    answer_index: int,
) -> dict[str, Any] | None:
    """Persist one stepwise interpretation before revealing the next choice."""

    session = store.get_shift_session(session_id)
    if not session:
        return None
    if session.get("pendingItemId") != item_id:
        return {"error": "not_pending", "pendingItemId": session.get("pendingItemId")}
    item = item_store.get_item(item_id)
    if item is None:
        return None
    if item.question_type != "stepwise":
        return {"error": "not_stepwise"}
    if step_index < 0 or step_index >= len(item.steps):
        return {"error": "invalid_step"}
    assert_learner_item_provenance(item, packet_provider)
    committed = store.commit_shift_step(
        session_id,
        item_id,
        step_index,
        answer_index,
        step_count=len(item.steps),
        option_count=len(item.steps[step_index].options),
    )
    status = committed.get("status")
    if status in {
        "missing",
        "not_pending",
        "context_not_revealed",
        "invalid_step",
        "step_locked",
        "step_out_of_order",
    }:
        return {"error": status, **committed}
    refreshed = store.get_shift_session(session_id)
    payload = _serve_payload(item, packet_provider, refreshed) if refreshed else None
    if payload is not None:
        payload["replay"] = status == "replay"
    return payload


def next_shift_item(store, item_store, packet_provider: PacketProvider, session_id: str) -> dict[str, Any] | None:
    integrity.expire_pending_item(store, session_id=session_id)
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
    claim = integrity.claim_pending_item(
        store,
        session_id=session_id,
        item_id=public_item_reference(item.item_id),
        ecg_id=item.ecg_id,
    )
    if claim.get("status") == "exposure_conflict":
        # Another mode claimed this tracing after selection but before the
        # serialized lease write. Re-select from the now-updated exposure set.
        return next_shift_item(store, item_store, packet_provider, session_id)
    if claim.get("status") == "missing":
        return None
    claimed = store.get_shift_session(session_id)
    if not claimed:
        return None
    # If two `next` requests raced, render whichever item won the persisted claim.
    pending_id = claimed.get("pendingItemId")
    persisted = (
        item
        if pending_id == public_item_reference(item.item_id)
        else item_store.get_item(pending_id)
    )
    return _serve_payload(persisted, packet_provider, claimed) if persisted else None


def grade_and_record(
    store, item_store, packet_provider: PacketProvider, session_id: str, item_id: str, answer: ClinicalAnswer
) -> dict[str, Any] | None:
    def committed_replay() -> dict[str, Any] | None:
        prior_answer = store.get_shift_answer(session_id, item_id)
        if not prior_answer:
            return None
        return {
            "grade": prior_answer["grade"],
            "replay": True,
            "answerId": prior_answer["answerId"],
            "tutorContext": tutor_context_reference(prior_answer),
        }

    session = store.get_shift_session(session_id)
    if not session:
        return None
    prior = committed_replay()
    if prior:
        return prior
    if session.get("pendingItemId") != item_id:
        prior = committed_replay()
        if prior:
            return prior
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
    if item.question_type == "stepwise":
        committed_steps = [int(value) for value in (session.get("stepAnswers") or [])]
        deadline = session.get("decideDeadlineAt")
        expired = bool(deadline and datetime.now(UTC) >= datetime.fromisoformat(str(deadline)))
        if len(committed_steps) != len(item.steps) and not expired:
            return {
                "error": "stepwise_incomplete",
                "nextStepIndex": len(committed_steps),
            }
        # Only the durable ordered commits participate in grading. A forged or
        # stale final payload cannot revise any prior step after later choices.
        answer = answer.model_copy(update={"step_answers": committed_steps})
    # A presentation created by an older process is backfilled before the
    # answer claim. New presentations already have an atomic_v2 lease.
    pending_contract = integrity.claim_pending_item(
        store,
        session_id=session_id,
        item_id=item_id,
        ecg_id=item.ecg_id,
    )
    if pending_contract.get("status") in {"missing", "not_active"}:
        prior = committed_replay()
        if prior:
            return prior
        return {
            "error": "not_pending",
            "pendingItemId": session.get("pendingItemId"),
        }
    reservation = integrity.claim_answer_submission(
        store,
        session_id=session_id,
        item_id=item_id,
        ecg_id=item.ecg_id,
    )
    if reservation.get("status") == "expired":
        return {"error": "expired", "pendingItemId": None}
    if reservation.get("status") in {"missing", "missing_lease", "not_pending"}:
        prior = committed_replay()
        if prior:
            return prior
        return {
            "error": "not_pending",
            "pendingItemId": reservation.get("pendingItemId"),
        }
    timing = store.claim_shift_submission_timing(session_id, item_id)
    if timing["status"] in {"missing", "not_pending", "context_not_revealed"}:
        integrity.release_answer_submission(
            store,
            session_id=session_id,
            owner_id=str(reservation["ownerId"]),
            lease_id=str(reservation["leaseId"]),
            submission_key=str(reservation["submissionKey"]),
        )
        prior = committed_replay()
        if prior:
            return prior
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
    try:
        grade = grade_clinical_answer(item, packet, answer)
        correct = (
            bool(grade.get("matchingCorrect"))
            if item.question_type == "matching"
            else not grade["missedObjectives"] and grade["score"] >= 0.6
        )
        calibration_event = {
            "itemId": item_id,
            "score": grade["score"],
            "correct": correct,
            "decideMs": timing["answerTimeMs"],
            **(grade.get("calibrationEvent") or {}),
        }
        recorded = integrity.finalize_answer(
            store,
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
            lease_id=str(reservation["leaseId"]),
            submission_key=str(reservation["submissionKey"]),
        )
    except Exception:
        integrity.release_answer_submission(
            store,
            session_id=session_id,
            owner_id=str(reservation["ownerId"]),
            lease_id=str(reservation["leaseId"]),
            submission_key=str(reservation["submissionKey"]),
        )
        raise
    if recorded["status"] == "not_pending":
        # A concurrent request may have committed this answer after the preflight.
        prior = committed_replay()
        if prior:
            return prior
        integrity.release_answer_submission(
            store,
            session_id=session_id,
            owner_id=str(reservation["ownerId"]),
            lease_id=str(reservation["leaseId"]),
            submission_key=str(reservation["submissionKey"]),
        )
        return {"error": "not_pending", "pendingItemId": recorded.get("pendingItemId")}
    if recorded["status"] == "context_not_revealed":
        integrity.release_answer_submission(
            store,
            session_id=session_id,
            owner_id=str(reservation["ownerId"]),
            lease_id=str(reservation["leaseId"]),
            submission_key=str(reservation["submissionKey"]),
        )
        return {"error": "context_not_revealed", "pendingItemId": recorded.get("pendingItemId")}
    if recorded["status"] == "missing":
        integrity.release_answer_submission(
            store,
            session_id=session_id,
            owner_id=str(reservation["ownerId"]),
            lease_id=str(reservation["leaseId"]),
            submission_key=str(reservation["submissionKey"]),
        )
        return None
    if recorded["status"] not in {"created", "replay"}:
        integrity.release_answer_submission(
            store,
            session_id=session_id,
            owner_id=str(reservation["ownerId"]),
            lease_id=str(reservation["leaseId"]),
            submission_key=str(reservation["submissionKey"]),
        )
        raise RuntimeError("Clinical answer finalization did not reach a durable state")
    stored = recorded["answer"]
    return {
        "grade": stored["grade"],
        "replay": recorded["status"] == "replay",
        "answerId": stored["answerId"],
        "tutorContext": tutor_context_reference(stored),
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
    expired = integrity.expire_pending_item(store, session_id=session["sessionId"])
    session = store.get_shift_session(session["sessionId"])
    if not session:
        return {"session": None, "state": "picker", "current": None, "grade": None, "report": None}
    if expired and session.get("status") == "active":
        next_shift_item(store, item_store, packet_provider, session["sessionId"])
        session = store.get_shift_session(session["sessionId"])
        if not session:
            return {"session": None, "state": "picker", "current": None, "grade": None, "report": None}
    pending_id = session.get("pendingItemId")
    if pending_id:
        item = item_store.get_item(pending_id)
        if item is not None:
            integrity.claim_pending_item(
                store,
                session_id=session["sessionId"],
                item_id=str(pending_id),
                ecg_id=item.ecg_id,
            )
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
                "tutorContext": tutor_context_reference(stored),
                "answer": {
                    "firstLookFinding": stored["response"].get("first_look_finding"),
                    "firstLookConfidence": stored["response"].get("first_look_confidence"),
                    "selectedOptionId": stored["response"].get("selected_option_id"),
                    "click": stored["response"].get("click"),
                    "machineLineId": stored["response"].get("machine_line_id"),
                    "fillInValue": stored["response"].get("fill_in_value"),
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
            "report": shift_report(
                store, session["sessionId"], item_store, packet_provider
            ),
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


_ECG_REPORT_AXES = {
    "concept_identification",
    "lead_selection",
    "region_accuracy",
    "measurement_accuracy",
    "machine_audit",
    "proof_on_trace",
    "ecg_sequence",
    "evidence_source_matching",
    "ecg_evidence",
    "authored_context_boundary",
    "unsupported_claim_boundary",
}


def _aggregate_axes(
    answers: list[dict[str, Any]], allowed: set[str]
) -> dict[str, dict[str, Any]]:
    values: dict[str, list[float]] = {}
    for row in answers:
        for axis, raw_score in (row.get("grade", {}).get("axisScores") or {}).items():
            if axis in allowed:
                values.setdefault(axis, []).append(float(raw_score))
    return {
        axis: {"assessed": len(scores), "score": round(sum(scores) / len(scores), 3)}
        for axis, scores in sorted(values.items())
        if scores
    }


def _performance_domains(
    answers: list[dict[str, Any]], calibration_summary: str
) -> dict[str, Any]:
    first_looks: list[dict[str, Any]] = []
    for row in answers:
        assessment = row.get("grade", {}).get("firstLookAssessment")
        if isinstance(assessment, dict) and assessment.get("agreement") in {True, False}:
            first_looks.append(assessment)
    matched = sum(1 for assessment in first_looks if assessment.get("agreement") is True)
    calibration_scores: list[float] = []
    high_confidence_mismatches = 0
    probability_by_confidence = {2: 0.4, 3: 0.65, 5: 0.9}
    for assessment in first_looks:
        confidence = int(assessment.get("confidence") or 0)
        probability = probability_by_confidence.get(confidence)
        if probability is None:
            continue
        outcome = 1.0 if assessment.get("agreement") is True else 0.0
        calibration_scores.append(1.0 - abs(probability - outcome))
        if confidence == 5 and outcome == 0.0:
            high_confidence_mismatches += 1

    trace_axes = _aggregate_axes(answers, _ECG_REPORT_AXES)
    clinical_axes = _aggregate_axes(answers, {"clinical_decision"})
    safety_axes = _aggregate_axes(answers, {"safety"})
    clinical_scores = [row["score"] for row in clinical_axes.values()]
    safety_scores = [
        float(row.get("grade", {}).get("axisScores", {}).get("safety"))
        for row in answers
        if "safety" in (row.get("grade", {}).get("axisScores") or {})
    ]
    flagged = sum(
        1
        for row in answers
        if row.get("grade", {}).get("safetyFlags")
        or float(row.get("grade", {}).get("axisScores", {}).get("safety", 1.0)) < 1.0
    )
    unsafe_choices = sum(
        1
        for row in answers
        if (row.get("grade", {}).get("calibrationEvent") or {}).get("unsafe")
    )
    calibration_score = (
        round(sum(calibration_scores) / len(calibration_scores), 3)
        if calibration_scores
        else None
    )
    if not calibration_scores:
        confidence_label = "No first-look confidence data"
    elif high_confidence_mismatches:
        confidence_label = (
            f"{high_confidence_mismatches} high-confidence broad-category mismatch"
            f"{'es' if high_confidence_mismatches != 1 else ''}"
        )
    elif calibration_score is not None and calibration_score >= 0.75:
        confidence_label = "Confidence broadly matched first-look performance"
    else:
        confidence_label = "Confidence needs recalibration"
    return {
        "ecgRecognitionFirstLook": {
            "broadCategory": {
                "assessed": len(first_looks),
                "matched": matched,
                "score": round(matched / len(first_looks), 3) if first_looks else None,
            },
            "traceAxes": trace_axes,
            "formativeOnly": True,
            "exactPathologyMastery": False,
        },
        "clinicalApplicationDecision": {
            "assessed": sum(row["assessed"] for row in clinical_axes.values()),
            "score": (
                round(sum(clinical_scores) / len(clinical_scores), 3)
                if clinical_scores
                else None
            ),
            "axes": clinical_axes,
            "formativeOnly": True,
        },
        "safety": {
            "assessed": len(safety_scores),
            "safe": sum(1 for score in safety_scores if score >= 1.0),
            "flagged": flagged,
            "unsafeChoices": unsafe_choices,
            "score": (
                round(sum(safety_scores) / len(safety_scores), 3)
                if safety_scores
                else None
            ),
        },
        "confidenceCalibration": {
            "assessed": len(calibration_scores),
            "broadCategoryMatches": matched,
            "highConfidenceMismatches": high_confidence_mismatches,
            "score": calibration_score,
            "label": confidence_label if calibration_scores else calibration_summary,
        },
    }


def shift_report(
    store, session_id: str, item_store=None, packet_provider: PacketProvider | None = None
) -> dict[str, Any] | None:
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
    summary_label = "calibration off (Learn)" if session["tier"] == "learn" else calibration_label(events)
    report = {
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
        "calibrationLabel": summary_label,
        "performanceDomains": _performance_domains(answers, summary_label),
        "status": session["status"],
    }
    if item_store is not None and answers:
        report["debrief"] = build_shift_debrief(
            session,
            answers,
            store.ensure_profile(session["learnerId"]),
            item_store,
            packet_provider,
        )
    if session.get("status") == "complete" and answers:
        report["tutorContext"] = shift_tutor_context_reference(session, answers)
    return report
