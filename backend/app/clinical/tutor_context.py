"""Owner-bound, post-commit grounding for the Clinical tutor.

The browser receives only :func:`tutor_context_reference`.  The actual context
is rebuilt from the durable Clinical answer and the startup-vetted item on every
tutor turn.  This keeps learner-controlled ``viewerState`` useful for UI state
without letting it impersonate a grade, rubric, or evidence manifest.
"""

from __future__ import annotations

import hashlib
from typing import Any, Callable

from ..config import get_settings
from ..ecg_capability import issue_ecg_capability
from .harness import run_harness
from .item_reference import public_item_reference
from .provenance import assert_learner_item_provenance
from .schemas import ClinicalCaseItem
from .debrief import build_shift_debrief

PacketProvider = Callable[[str], dict[str, Any] | None]

CONTEXT_VERSION = "clinical-post-feedback-v1"
SHIFT_CONTEXT_VERSION = "clinical-shift-debrief-v1"
SERVING_STATUS = "harness_pass"


class ClinicalTutorContextNotFound(LookupError):
    """The reference is missing, stale, tampered with, or belongs to another learner."""


class ClinicalTutorContextNotReady(RuntimeError):
    """The Clinical decision has not yet been durably graded."""


class ClinicalTutorContextInvalid(RuntimeError):
    """A previously reviewed item no longer satisfies its grounding contract."""


def tutor_context_reference(answer: dict[str, Any]) -> dict[str, Any]:
    """Return a stable, non-secret reference to one stored Clinical answer."""

    session_id = str(answer.get("sessionId") or "")
    item_id = str(answer.get("itemId") or "")
    answer_id = int(answer.get("answerId") or 0)
    if not session_id or not item_id or answer_id <= 0:
        raise ClinicalTutorContextInvalid("Stored Clinical answer cannot identify its tutor context.")
    digest = hashlib.sha256(
        f"{CONTEXT_VERSION}\0{session_id}\0{item_id}\0{answer_id}".encode("utf-8")
    ).hexdigest()[:24]
    return {
        "contextId": f"ct_{digest}",
        "sessionId": session_id,
        "itemId": item_id,
        "answerId": answer_id,
        "version": CONTEXT_VERSION,
    }


def shift_tutor_context_reference(
    session: dict[str, Any], answers: list[dict[str, Any]]
) -> dict[str, Any]:
    """Return an owner-checked reference to one completed Clinical shift."""

    session_id = str(session.get("sessionId") or "")
    answer_ids = [int(answer.get("answerId") or 0) for answer in answers]
    if (
        not session_id
        or session.get("status") != "complete"
        or not answer_ids
        or any(answer_id <= 0 for answer_id in answer_ids)
    ):
        raise ClinicalTutorContextNotReady(
            "Finish at least one Clinical case before opening the shift debrief."
        )
    digest = hashlib.sha256(
        (
            f"{SHIFT_CONTEXT_VERSION}\0{session_id}\0"
            + ",".join(str(answer_id) for answer_id in answer_ids)
        ).encode("utf-8")
    ).hexdigest()[:24]
    return {
        "contextId": f"cs_{digest}",
        "sessionId": session_id,
        "answerCount": len(answer_ids),
        "version": SHIFT_CONTEXT_VERSION,
    }


def _response_value(response: dict[str, Any], snake: str, camel: str) -> Any:
    return response.get(snake) if snake in response else response.get(camel)


def _learner_answer_summary(item: ClinicalCaseItem, response: dict[str, Any]) -> dict[str, Any]:
    """Translate the stored response to learner-visible text without key material."""

    selected_option_id = _response_value(response, "selected_option_id", "selectedOptionId")
    selected_option = next(
        (option.text for option in item.options if option.id == selected_option_id),
        None,
    )
    selected_machine_id = _response_value(response, "machine_line_id", "machineLineId")
    selected_machine_line = next(
        (line.text for line in item.machine_read if line.id == selected_machine_id),
        None,
    )
    raw_steps = _response_value(response, "step_answers", "stepAnswers") or []
    step_selections: list[dict[str, str]] = []
    for index, selected in enumerate(raw_steps):
        if index >= len(item.steps) or not isinstance(selected, int):
            continue
        step = item.steps[index]
        if 0 <= selected < len(step.options):
            step_selections.append(
                {
                    "prompt": step.prompt,
                    "selectedResponse": step.options[selected].text,
                }
            )

    click = _response_value(response, "click", "click")
    click_summary = None
    if isinstance(click, dict):
        click_summary = {
            "lead": click.get("lead"),
            "timeSec": _response_value(click, "time_sec", "timeSec"),
            "amplitudeMv": _response_value(click, "amplitude_mv", "amplitudeMv"),
        }

    return {
        "firstLook": {
            "finding": _response_value(response, "first_look_finding", "firstLookFinding"),
            "confidence": _response_value(
                response, "first_look_confidence", "firstLookConfidence"
            ),
        },
        "selectedResponse": selected_option,
        "selectedMachineStatement": selected_machine_line,
        "enteredMeasurement": _response_value(
            response, "fill_in_value", "fillInValue"
        ),
        "stepSelections": step_selections,
        "click": click_summary,
        "confidence": response.get("confidence"),
        "timedOut": bool(_response_value(response, "timed_out", "timedOut")),
    }


def _feedback_summary(grade: dict[str, Any]) -> dict[str, Any]:
    first_look = grade.get("firstLookAssessment") or {}
    return {
        "score": float(grade.get("score") or 0.0),
        "answerClass": grade.get("answerClass"),
        "axisScores": grade.get("axisScores") or {},
        "feedback": str(grade.get("feedback") or ""),
        "teachingPoints": list(grade.get("teachingPoints") or []),
        "correctObjectives": list(grade.get("correctObjectives") or []),
        "missedObjectives": list(grade.get("missedObjectives") or []),
        "safetyFlags": list(grade.get("safetyFlags") or []),
        "timedOut": bool(grade.get("timedOut")),
        "firstLook": {
            "submittedCategory": first_look.get("submittedCategory"),
            "confidence": first_look.get("confidence"),
            "agreement": first_look.get("agreement"),
            "formativeOnly": True,
        },
        "clinicalApplicationEvidence": grade.get("clinicalApplicationEvidence"),
    }


_RAW_KEY_FIELDS = frozenset(
    {
        "options",
        "steps",
        "machineRead",
        "machine_read",
        "correct",
        "bad",
        "answer_class",
        "selectedOptionId",
        "selected_option_id",
        "machineLineId",
        "machine_line_id",
        "stepAnswers",
        "step_answers",
        "expectedCategories",
        "masteryDelta",
        "calibrationEvent",
        "viewerActions",
        "fillInTask",
        "fill_in_task",
        "expectedFeature",
        "expected_feature",
        "tolerance",
        "requiredSafetyTokens",
        "parsed",
    }
)


def _assert_key_safe(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = _RAW_KEY_FIELDS.intersection(value)
        if forbidden:
            raise ClinicalTutorContextInvalid(
                f"Clinical tutor context contains raw answer-key field(s): {sorted(forbidden)}"
            )
        for child in value.values():
            _assert_key_safe(child)
    elif isinstance(value, list):
        for child in value:
            _assert_key_safe(child)


def is_uncommitted_clinical_case(
    store,
    item_store,
    *,
    learner_id: str,
    case_id: str,
) -> bool:
    """Return whether this learner currently sees ``case_id`` before final commit."""

    session = store.get_resumable_shift_session(learner_id)
    if not session or not session.get("pendingItemId"):
        return False
    item = item_store.get_item(str(session["pendingItemId"]))
    if item is None or str(item.ecg_id) != str(case_id):
        return False
    return store.get_shift_answer(session["sessionId"], item.item_id) is None


def build_clinical_tutor_context(
    store,
    item_store,
    packet_provider: PacketProvider,
    *,
    learner_id: str,
    session_id: str,
    item_id: str,
    answer_id: int,
    context_id: str,
    version: str,
) -> dict[str, Any]:
    """Rebuild one trusted tutor context from durable, owner-bound state.

    No part of the returned object is supplied by the browser.  A stored answer
    is the release gate, so this context cannot exist during ECG-only orientation
    or after context reveal but before the learner submits the clinical decision.
    """

    session = store.get_shift_session(session_id)
    if not session or str(session.get("learnerId")) != str(learner_id):
        raise ClinicalTutorContextNotFound("Clinical tutor context not found.")

    answer = store.get_shift_answer(session_id, item_id)
    if answer is None:
        raise ClinicalTutorContextNotReady(
            "Submit the Clinical decision before opening its grounded tutor context."
        )

    expected_reference = tutor_context_reference(answer)
    supplied_reference = {
        "contextId": context_id,
        "sessionId": session_id,
        "itemId": item_id,
        "answerId": int(answer_id),
        "version": version,
    }
    if supplied_reference != expected_reference:
        raise ClinicalTutorContextNotFound("Clinical tutor context not found.")

    item = item_store.get_item(item_id)
    if item is None or item.validation_status != SERVING_STATUS:
        raise ClinicalTutorContextNotFound("Clinical tutor context not found.")
    if str(answer.get("ecgId")) != str(item.ecg_id):
        raise ClinicalTutorContextInvalid("Stored Clinical answer no longer matches its item.")

    packet = assert_learner_item_provenance(item, packet_provider)
    # Re-run the honesty harness on a deep copy. Startup already gates the bank;
    # this second fail-closed check prevents stale/tampered item state from being
    # promoted into a remote tutor prompt later.
    report = run_harness(item.model_copy(deep=True), packet, None)
    if not report.passed:
        raise ClinicalTutorContextInvalid("Clinical item no longer passes its review harness.")

    manifest = item.evidence_manifest
    public_reference = {
        **expected_reference,
        "itemId": public_item_reference(str(expected_reference["itemId"])),
    }
    ecg_reference = issue_ecg_capability(
        get_settings().registration_rate_limit_secret,
        learner_id,
        "clinical",
        session_id,
        str(item.ecg_id),
    )
    context = {
        "version": CONTEXT_VERSION,
        "reference": public_reference,
        "phase": "post_feedback",
        "case": {
            "caseNumber": next(
                (
                    index
                    for index, candidate in enumerate(
                        store.get_shift_answers(session_id), start=1
                    )
                    if int(candidate.get("answerId") or 0) == int(answer_id)
                ),
                1,
            ),
            "itemRef": public_item_reference(str(item.item_id)),
            "ecgRef": ecg_reference,
            "situation": item.situation,
            "questionType": item.question_type,
            "stem": item.stem,
            "chips": item.chips.model_dump(exclude_none=True),
            "prompt": item.prompt,
            "testedScope": item.tested_scope,
        },
        "learnerAnswer": _learner_answer_summary(item, answer.get("response") or {}),
        "storedFeedback": _feedback_summary(answer.get("grade") or {}),
        "evidenceManifest": {
            "ecgSupports": [
                {
                    "objectiveId": claim.objective_id,
                    "threshold": claim.threshold,
                    "leads": list(claim.leads),
                    "roiConcept": claim.roi_concept,
                    "sourceType": claim.source_type,
                }
                for claim in manifest.ecg_supports
            ],
            "stemAdds": list(manifest.stem_adds),
        },
        "reviewedRubric": {
            "actionRationale": manifest.action_rationale,
            "acceptableRange": list(manifest.acceptable_range),
            "forbiddenClaims": list(manifest.forbidden_claims),
            "epistemicStatus": manifest.epistemic_status,
            "applicationObjectives": list(item.application_objectives),
        },
        "governance": {
            "validationStatus": item.validation_status,
            "harnessPassed": True,
            "clinicianReviewed": False,
            "learningEvidence": "formative_only",
            "answerKeyPolicy": (
                "The context includes only the learner's own selected response and "
                "post-commit feedback; raw alternative keys, step correctness flags, "
                "and machine-line truth labels are excluded."
            ),
        },
    }
    _assert_key_safe(context)
    return {"context": context, "casePacket": packet, "reference": public_reference}


def build_clinical_shift_tutor_context(
    store,
    item_store,
    packet_provider: PacketProvider,
    *,
    learner_id: str,
    session_id: str,
    answer_count: int,
    context_id: str,
    version: str,
) -> dict[str, Any]:
    """Rebuild a completed-shift context from durable, owner-bound grades.

    Every included item is rechecked against its real packet and honesty harness.
    Only post-commit feedback fields are retained; raw alternatives, correctness
    keys, and grading internals never enter the provider context.
    """

    session = store.get_shift_session(session_id)
    if not session or str(session.get("learnerId")) != str(learner_id):
        raise ClinicalTutorContextNotFound("Clinical shift debrief not found.")
    if session.get("status") != "complete":
        raise ClinicalTutorContextNotReady(
            "Finish the Clinical shift before opening its grounded debrief."
        )
    answers = store.get_shift_answers(session_id)
    expected_reference = shift_tutor_context_reference(session, answers)
    supplied_reference = {
        "contextId": context_id,
        "sessionId": session_id,
        "answerCount": int(answer_count),
        "version": version,
    }
    if supplied_reference != expected_reference:
        raise ClinicalTutorContextNotFound("Clinical shift debrief not found.")

    safe_cases: list[dict[str, Any]] = []
    for case_number, answer in enumerate(answers, start=1):
        item = item_store.get_item(str(answer.get("itemId") or ""))
        if item is None or item.validation_status != SERVING_STATUS:
            raise ClinicalTutorContextNotFound("Clinical shift debrief not found.")
        if str(answer.get("ecgId")) != str(item.ecg_id):
            raise ClinicalTutorContextInvalid(
                "Stored Clinical shift evidence no longer matches its item."
            )
        packet = assert_learner_item_provenance(item, packet_provider)
        harness = run_harness(item.model_copy(deep=True), packet, None)
        if not harness.passed:
            raise ClinicalTutorContextInvalid(
                "A Clinical shift item no longer passes its review harness."
            )
        grade = answer.get("grade") if isinstance(answer.get("grade"), dict) else {}
        safe_cases.append(
            {
                "caseNumber": case_number,
                "itemRef": public_item_reference(str(item.item_id)),
                "ecgRef": issue_ecg_capability(
                    get_settings().registration_rate_limit_secret,
                    learner_id,
                    "clinical",
                    session_id,
                    str(item.ecg_id),
                ),
                "situation": item.situation,
                "questionType": item.question_type,
                "score": float(grade.get("score") or 0.0),
                "correctObjectives": list(grade.get("correctObjectives") or []),
                "missedObjectives": list(grade.get("missedObjectives") or []),
                "feedback": str(grade.get("feedback") or ""),
                "teachingPoints": list(grade.get("teachingPoints") or []),
                "timedOut": bool(grade.get("timedOut")),
                "ecgSupports": [
                    {
                        "objectiveId": claim.objective_id,
                        "threshold": claim.threshold,
                        "leads": list(claim.leads),
                        "roiConcept": claim.roi_concept,
                        "sourceType": claim.source_type,
                    }
                    for claim in item.evidence_manifest.ecg_supports
                ],
                "applicationObjectives": list(item.application_objectives),
            }
        )

    profile = store.ensure_profile(learner_id)
    debrief = build_shift_debrief(
        session, answers, profile, item_store, packet_provider
    )
    correct = sum(1 for answer in answers if answer.get("correct"))
    context = {
        "kind": "clinical_shift_debrief",
        "phase": "post_shift",
        "version": SHIFT_CONTEXT_VERSION,
        "reference": expected_reference,
        "session": {
            "sessionId": session_id,
            "lane": session.get("lane"),
            "tier": session.get("tier"),
            "answered": len(answers),
            "accuracy": round(correct / len(answers), 3) if answers else 0.0,
        },
        "completedCases": safe_cases,
        "debrief": debrief,
        "governance": {
            "validationStatus": SERVING_STATUS,
            "harnessRechecked": True,
            "clinicianReviewed": False,
            "learningEvidence": "formative_only",
            "selectionAuthority": (
                "The next-case proposal is deterministic and uses completed server grades, "
                "current independent competency state, and a different serving real ECG."
            ),
            "answerKeyPolicy": (
                "Only completed feedback and manifested ECG evidence are included; raw alternatives, "
                "correctness flags, grading tolerances, and unserved item keys are excluded."
            ),
        },
    }
    _assert_key_safe(context)
    return {"context": context, "reference": expected_reference}


__all__ = [
    "CONTEXT_VERSION",
    "SHIFT_CONTEXT_VERSION",
    "ClinicalTutorContextInvalid",
    "ClinicalTutorContextNotFound",
    "ClinicalTutorContextNotReady",
    "build_clinical_tutor_context",
    "build_clinical_shift_tutor_context",
    "is_uncommitted_clinical_case",
    "tutor_context_reference",
    "shift_tutor_context_reference",
]
