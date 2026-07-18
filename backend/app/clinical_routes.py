"""FastAPI routes for the Clinical Decisions mode.

Built as a factory (``build_clinical_router``) that closes over the app's module-level
``store`` / item store / packet provider, so it composes with the existing decorator-style
``main.py`` without a circular import.
"""

from __future__ import annotations

from collections import Counter
import hmac
from typing import Any, Callable, Literal

from fastapi import APIRouter, Cookie, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field

from .auth import SESSION_COOKIE_NAME
from .clinical import shift
from .clinical import integrity as clinical_integrity
from .clinical.item_reference import public_item_reference, public_option_reference
from .clinical.real_items import (
    AUTHENTIC_LONGITUDINAL_PRIOR_BY_CURRENT,
    CLINICAL_FAMILY_BY_SCENARIO,
    REAL_ECGS_BY_SCENARIO,
    normalized_scenario_signature,
)
from .clinical.schemas import ClinicalAnswer
from .clinical.provenance import assert_learner_item_provenance
from .config import get_settings
from .ecg_capability import (
    is_ecg_capability,
    issue_ecg_capability,
    matches_ecg_capability,
)
from .learning_sessions import issue_learning_session_ref

PacketProvider = Callable[[str], dict[str, Any] | None]
WaveformProvider = Callable[..., dict[str, Any] | None]
LearnerResolver = Callable[[str | None, str, str | None], str]


class ShiftStartBody(BaseModel):
    learnerId: str = "demo"
    lane: Literal["clinic", "ward", "ed"] = "ed"
    tier: Literal["learn", "shift"] = "shift"
    focus: str | None = Field(default=None, max_length=80)
    subskill: str | None = Field(default=None, max_length=80)
    length: int = Field(default=5, ge=1, le=50)


class AnswerBody(BaseModel):
    itemId: str = Field(min_length=4, max_length=160)
    answer: ClinicalAnswer = Field(default_factory=ClinicalAnswer)


class FirstLookBody(BaseModel):
    itemId: str = Field(min_length=4, max_length=160)
    answer: ClinicalAnswer


class PhaseActivationBody(BaseModel):
    itemId: str = Field(min_length=4, max_length=160)
    phase: Literal["orient", "decide"]


class StepCommitBody(BaseModel):
    itemId: str = Field(min_length=4, max_length=160)
    stepIndex: int = Field(ge=0)
    answerIndex: int = Field(ge=0)


def build_clinical_router(
    store,
    item_store,
    packet_provider: PacketProvider,
    resolve_learner: LearnerResolver,
    waveform_provider: WaveformProvider | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/clinical", tags=["clinical-decisions"])
    settings = get_settings()
    capability_secret = settings.adaptive_plan_context_secret
    review_session_secret = settings.registration_rate_limit_secret

    def reference_maps(
        session: dict[str, Any],
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Rebuild public references from durable owner-scoped canonical state.

        Nothing here is decoded from a browser reference.  This also keeps
        sessions written before capabilities existed resumable without a data
        migration: legacy canonical ids remain server-side and receive a fresh
        deterministic reference at the response boundary.
        """

        item_candidates = {
            str(value)
            for value in (
                *(session.get("served") or []),
                session.get("pendingItemId"),
                session.get("feedbackItemId"),
            )
            if value
        }
        canonical_ids = {
            str(value) for value in (session.get("servedEcgs") or []) if value
        }
        answers = store.get_shift_answers(str(session["sessionId"]))
        for answer in answers:
            if answer.get("itemId"):
                item_candidates.add(str(answer["itemId"]))
            if answer.get("ecgId"):
                canonical_ids.add(str(answer["ecgId"]))

        learner_id = str(session["learnerId"])
        session_id = str(session["sessionId"])
        item_references: dict[str, str] = {}
        for candidate in tuple(item_candidates):
            item = item_store.get_item(candidate)
            if item is None:
                continue
            canonical_item_id = str(item.item_id)
            reference = public_item_reference(
                canonical_item_id,
                learner_id=learner_id,
                session_id=session_id,
            )
            item_references[candidate] = reference
            item_references[canonical_item_id] = reference
            item_references[reference] = reference
            canonical_ids.add(str(item.ecg_id))
            if item.prior_ecg_id:
                canonical_ids.add(str(item.prior_ecg_id))

        references = {
            canonical_id: issue_ecg_capability(
                capability_secret,
                str(session["learnerId"]),
                "clinical",
                str(session["sessionId"]),
                canonical_id,
            )
            for canonical_id in canonical_ids
        }
        return references, item_references

    def public_payload(session: dict[str, Any], value: Any) -> Any:
        """Remove canonical ECG/item identifiers from a Clinical response."""

        ecg_references, item_references = reference_maps(session)
        learner_id = str(session["learnerId"])
        session_id = str(session["sessionId"])

        def item_reference(value: Any) -> str | None:
            if value is None:
                return None
            text = str(value)
            existing = item_references.get(text)
            if existing is not None:
                return existing
            item = item_store.get_item(text)
            if item is None:
                return None
            reference = public_item_reference(
                str(item.item_id),
                learner_id=learner_id,
                session_id=session_id,
            )
            item_references[text] = reference
            item_references[str(item.item_id)] = reference
            item_references[reference] = reference
            return reference
        review_session_ref = (
            issue_learning_session_ref(
                secret=review_session_secret,
                learner_id=str(session["learnerId"]),
                mode="clinical",
                session_id=str(session["sessionId"]),
            )
            if session.get("status") == "complete" and int(session.get("position") or 0) > 0
            else None
        )
        ecg_key_names = {
            "ecg_id": "ecg_ref",
            "ecgId": "ecgRef",
            "case_id": "ecg_ref",
            "prior_ecg_id": "prior_ecg_ref",
            "priorEcgId": "priorEcgRef",
        }
        display_keys = {"display_id", "displayId"}
        position = int(session.get("position") or 0)
        display_number = (
            max(1, position)
            if session.get("feedbackItemId") and not session.get("pendingItemId")
            else max(1, position + 1)
        )
        display_label = f"Clinical ECG {display_number:04d}"
        raw_path_keys = {
            "path",
            "sourcePath",
            "source_path",
            "recordPath",
            "record_path",
            "waveformPath",
            "waveform_path",
            "filePath",
            "file_path",
        }

        def visit(child: Any) -> Any:
            if isinstance(child, dict):
                result: dict[str, Any] = {}
                for raw_key, raw_value in child.items():
                    key = str(raw_key)
                    if key in raw_path_keys:
                        # Corpus object paths are server implementation details,
                        # never learner-facing locators.
                        continue
                    if key == "servedEcgs":
                        result["servedEcgRefs"] = [
                            ecg_references[str(candidate)]
                            for candidate in (raw_value or [])
                            if str(candidate) in ecg_references
                        ]
                        continue
                    if key in display_keys:
                        result[key] = display_label
                        continue
                    if key in ecg_key_names:
                        public_key = ecg_key_names[key]
                        if raw_value is None:
                            result[public_key] = None
                        else:
                            reference = ecg_references.get(str(raw_value))
                            if reference is not None:
                                result[public_key] = reference
                        continue
                    if key == "caseId":
                        text = str(raw_value or "")
                        if text in ecg_references:
                            result["ecgRef"] = ecg_references[text]
                        elif raw_value is not None:
                            reference = item_reference(text)
                            if reference is not None:
                                result[key] = reference
                        continue
                    if key in {
                        "item_id",
                        "itemId",
                        "pendingItemId",
                        "feedbackItemId",
                    }:
                        result[key] = item_reference(raw_value)
                        continue
                    result[key] = visit(raw_value)
                if (
                    review_session_ref is not None
                    and child.get("status") == "complete"
                    and child.get("sessionId") == session.get("sessionId")
                    and int(child.get("answered") or 0) > 0
                    and "performanceDomains" in child
                ):
                    result["reviewSessionRef"] = review_session_ref
                    result["reviewHref"] = f"/home/review/{review_session_ref}"
                attempt_index = child.get("attemptIndex")
                if (
                    review_session_ref is not None
                    and child.get("reviewAvailable") is True
                    and isinstance(attempt_index, int)
                    and attempt_index > 0
                ):
                    result["reviewHref"] = (
                        f"/home/review/{review_session_ref}/attempt/{attempt_index}"
                    )
                    result["replayHref"] = (
                        f"/learning/sessions/{review_session_ref}/attempts/"
                        f"{attempt_index}/replay"
                    )
                return result
            if isinstance(child, list):
                return [visit(entry) for entry in child]
            if isinstance(child, tuple):
                return [visit(entry) for entry in child]
            if isinstance(child, str):
                if child in ecg_references:
                    return ecg_references[child]
                if child in item_references:
                    return item_references[child]
            return child

        return visit(value)

    def public_session(session: dict[str, Any]) -> dict[str, Any]:
        return public_payload(session, session)

    def submitted_item_id(session: dict[str, Any], supplied: str) -> str:
        """Map only an owner session's opaque handle back to its durable key."""

        candidates = list(session.get("served") or [])
        candidates.extend(
            value
            for value in (session.get("pendingItemId"), session.get("feedbackItemId"))
            if value
        )
        learner_id = str(session["learnerId"])
        session_id = str(session["sessionId"])
        for candidate in dict.fromkeys(str(value) for value in candidates):
            item = item_store.get_item(candidate)
            if item is None:
                continue
            reference = public_item_reference(
                str(item.item_id),
                learner_id=learner_id,
                session_id=session_id,
            )
            if hmac.compare_digest(reference, supplied):
                return candidate
        # Preserve the ordinary not-pending response without ever accepting a
        # diagnosis-bearing internal id supplied by the browser.
        return "invalid-clinical-item-reference"

    def submitted_answer(
        session: dict[str, Any], item_id: str, answer: ClinicalAnswer
    ) -> ClinicalAnswer:
        """Resolve only this pending item's scoped option handle."""

        supplied = answer.selected_option_id
        if supplied is None:
            return answer
        item = item_store.get_item(item_id)
        if item is None:
            return answer.model_copy(
                update={"selected_option_id": "invalid-clinical-option-reference"}
            )
        learner_id = str(session["learnerId"])
        session_id = str(session["sessionId"])
        for option in item.options:
            reference = public_option_reference(
                str(item.item_id),
                str(option.id),
                learner_id=learner_id,
                session_id=session_id,
            )
            if hmac.compare_digest(reference, supplied):
                return answer.model_copy(update={"selected_option_id": option.id})
        return answer.model_copy(
            update={"selected_option_id": "invalid-clinical-option-reference"}
        )

    def public_pending(session: dict[str, Any], value: Any) -> str | None:
        if not value:
            return None
        _, item_references = reference_maps(session)
        return item_references.get(str(value))

    def owned_session(
        session_id: str, authorization: str | None, session_cookie: str | None
    ) -> dict[str, Any]:
        session = store.get_shift_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="shift session not found")
        # Ownership is enforced on every request. With no valid authentication the
        # effective learner is `demo`; an anonymous caller therefore cannot read or
        # mutate a `u_…` session even if its unguessable id leaks.
        learner = resolve_learner(authorization, "demo", session_cookie)
        if session.get("learnerId") != learner:
            raise HTTPException(status_code=404, detail="shift session not found")
        return session

    def reject_abandoned(session: dict[str, Any], action: str) -> None:
        if session.get("status") != "abandoned":
            return
        raise HTTPException(
            status_code=409,
            detail={
                "code": "clinical_shift_abandoned",
                "message": (
                    f"This Clinical shift was abandoned and cannot {action}. "
                    "Start a new shift from setup."
                ),
            },
        )

    def tracing_source_summary(items: list[Any]) -> tuple[list[str], dict[str, int]]:
        """Report the sources that the serving bank actually resolves to.

        The production bank is provenance-gated at startup, but this endpoint is
        also the learner/admin-visible audit surface.  Deriving the summary from
        the same packet provider prevents a legacy allow-list entry from being
        presented as though it were in the current bank.
        """

        counts: dict[str, int] = {}
        seen_ecgs: set[tuple[str, str]] = set()
        for item in items:
            # Status is an audit surface, so it must fail closed just like
            # serving and grading if a stale fixture row enters the pool.
            current_packet = assert_learner_item_provenance(item, packet_provider)
            packets = [current_packet]
            if item.prior_ecg_id:
                prior_packet = packet_provider(item.prior_ecg_id)
                if prior_packet is None:
                    raise RuntimeError("Clinical comparison ECG packet is missing.")
                packets.append(prior_packet)
            for packet in packets:
                source = str((packet or {}).get("source") or "").strip()
                case_id = str((packet or {}).get("case_id") or "").strip()
                identity = (source, case_id)
                if not source or not case_id or identity in seen_ecgs:
                    continue
                seen_ecgs.add(identity)
                counts[source] = counts.get(source, 0) + 1
        return sorted(counts), dict(sorted(counts.items()))

    @router.get("/bank/status")
    def bank_status(
        response: Response,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        resolve_learner(authorization, "demo", session_cookie)
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["Vary"] = "Authorization, Cookie"
        served = list(item_store.list_for_serving(status="harness_pass"))
        tracing_sources, tracing_source_counts = tracing_source_summary(served)
        family_by_ecg = {
            ecg_id: CLINICAL_FAMILY_BY_SCENARIO[scenario_id]
            for scenario_id, ecg_ids in REAL_ECGS_BY_SCENARIO.items()
            for ecg_id in ecg_ids
        }
        counts_by_situation = Counter(item.situation for item in served)
        counts_by_question_type = Counter(item.question_type for item in served)
        counts_by_setting = Counter(
            item.chips.setting or "unspecified" for item in served
        )
        waveform_ids = {
            str(ecg_id)
            for item in served
            for ecg_id in (item.ecg_id, item.prior_ecg_id)
            if ecg_id
        }
        longitudinal_episode_count = sum(
            1 for item in served if item.prior_ecg_id
        )
        counts_by_situation_and_question_type: dict[str, dict[str, int]] = {}
        for situation in sorted(counts_by_situation):
            row = Counter(
                item.question_type for item in served if item.situation == situation
            )
            counts_by_situation_and_question_type[situation] = dict(sorted(row.items()))
        return {
            "counts": item_store.count_by_status(),
            "servingItemCount": len(served),
            "distinctRealEcgs": len(waveform_ids),
            "longitudinalEpisodeCount": longitudinal_episode_count,
            "authenticatedComparisonEcgs": len({
                str(item.prior_ecg_id) for item in served if item.prior_ecg_id
            }),
            "longitudinalPairRegistrySize": len(AUTHENTIC_LONGITUDINAL_PRIOR_BY_CURRENT),
            "countsBySituation": dict(sorted(counts_by_situation.items())),
            "countsByQuestionType": dict(sorted(counts_by_question_type.items())),
            "countsBySituationAndQuestionType": counts_by_situation_and_question_type,
            "distinctAuthoredSettings": len(counts_by_setting),
            "countsByAuthoredSetting": dict(sorted(counts_by_setting.items())),
            "distinctScenarioSignatures": len({
                normalized_scenario_signature(item) for item in served
            }),
            "authoredClinicalFamilies": sorted({
                family_by_ecg[item.ecg_id]
                for item in served
                if item.ecg_id in family_by_ecg
            }),
            "servingStatus": "harness_pass",
            "learnerLabel": "automated-screened formative",
            "clinicianReviewed": False,
            "reviewStatus": "pending_named_clinician_signoff",
            "tracingSources": tracing_sources,
            "tracingSourceCounts": tracing_source_counts,
            "tracingLabel": "real de-identified ECG",
            "vignetteProvenance": "authored simulation",
            "learningEvidence": "formative_only",
            "provenanceGate": "passed",
        }

    @router.get("/bank/coverage")
    def bank_coverage(
        response: Response,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        """Per-concept pool depth (items + distinct ECGs) — surfaces which pathologies can
        sustain adaptive repetition and which are too thin to drill on yet."""
        resolve_learner(authorization, "demo", session_cookie)
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["Vary"] = "Authorization, Cookie"
        served = list(item_store.list_for_serving(status="harness_pass"))
        tracing_sources, tracing_source_counts = tracing_source_summary(served)
        return {
            "coverage": item_store.coverage(status="harness_pass"),
            "applicationCoverage": item_store.application_coverage(status="harness_pass"),
            "servingStatus": "harness_pass",
            "clinicianReviewed": False,
            "reviewStatus": "pending_named_clinician_signoff",
            "tracingSources": tracing_sources,
            "tracingSourceCounts": tracing_source_counts,
            "vignetteProvenance": "authored simulation",
        }

    @router.post("/shift/start")
    def shift_start(
        body: ShiftStartBody,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        # Client-supplied learner ids are never an ownership credential. Guests are
        # always demo; a valid bearer token resolves to its own `u_…` learner.
        learner = resolve_learner(authorization, "demo", session_cookie)
        session = shift.start_shift_with_capacity(
            store,
            item_store,
            packet_provider,
            learner,
            body.lane,
            body.tier,
            body.length,
            body.focus,
            body.subskill,
        )
        first = shift.next_shift_item(store, item_store, packet_provider, session["sessionId"])
        current = store.get_shift_session(session["sessionId"])
        payload = {"session": current, "next": first}
        return public_payload(current, payload) if current else payload

    @router.get("/shift/active")
    def shift_active(
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        learner = resolve_learner(authorization, "demo", session_cookie)
        session = store.get_resumable_shift_session(learner)
        result = shift.shift_lifecycle_payload(store, item_store, packet_provider, session)
        current = result.get("session") or session
        return public_payload(current, result) if current else result

    @router.get("/shift/{session_id}")
    def shift_get(
        session_id: str,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        return public_session(owned_session(session_id, authorization, session_cookie))

    @router.get("/shift/{session_id}/waveform/{ecg_ref}")
    def shift_waveform(
        session_id: str,
        ecg_ref: str,
        response: Response,
        leads: str | None = Query(default=None, max_length=120),
        start: float = Query(default=0, ge=0),
        end: float | None = Query(default=None, ge=0),
        maxPoints: int = Query(default=1200, ge=100, le=5000),
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        """Return only a waveform authorized by an owned Clinical capability."""

        not_found = HTTPException(status_code=404, detail="clinical waveform not found")
        try:
            session = owned_session(session_id, authorization, session_cookie)
        except HTTPException as error:
            if error.status_code == 404:
                raise not_found from None
            raise
        if waveform_provider is None or not is_ecg_capability(ecg_ref):
            raise not_found

        references, _ = reference_maps(session)
        canonical_id: str | None = None
        # Validate only against ECGs already authorized by durable state. The
        # capability is not decoded, and a canonical id from the URL is never
        # accepted as a fallback.
        for candidate in references:
            if matches_ecg_capability(
                ecg_ref,
                capability_secret,
                str(session["learnerId"]),
                "clinical",
                str(session["sessionId"]),
                candidate,
            ):
                canonical_id = candidate
        if canonical_id is None:
            raise not_found

        lead_list = [lead.strip() for lead in leads.split(",")] if leads else None
        if lead_list and (
            len(lead_list) > 12
            or any(not lead or len(lead) > 8 for lead in lead_list)
        ):
            raise HTTPException(
                status_code=422, detail="Invalid waveform lead selection"
            )
        waveform = waveform_provider(
            canonical_id,
            leads=lead_list,
            start=start,
            end=end,
            max_points=maxPoints,
        )
        if not waveform:
            raise not_found
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["Vary"] = "Authorization, Cookie"
        public_waveform = public_payload(session, waveform)
        public_waveform["caseId"] = ecg_ref
        public_waveform["ecgRef"] = ecg_ref
        return public_waveform

    @router.post("/shift/{session_id}/abandon")
    def shift_abandon(
        session_id: str,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        session = owned_session(session_id, authorization, session_cookie)
        if session.get("status") == "abandoned":
            # Safe retry. The first transition already cleared the pending
            # presentation; do not rewrite its durable transition timestamp.
            result = shift.shift_lifecycle_payload(
                store, item_store, packet_provider, session
            )
            current = result.get("session") or session
            return public_payload(current, result)
        if session.get("status") != "active":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "clinical_shift_not_active",
                    "message": "Only an active Clinical shift can be abandoned.",
                },
            )
        transition = clinical_integrity.abandon_session(
            store,
            session_id=session_id,
            owner_id=str(session["learnerId"]),
        )
        abandoned = store.get_shift_session(session_id)
        if (
            not transition
            or not transition.get("changed")
            or not abandoned
            or abandoned.get("status") != "abandoned"
        ):
            # A concurrent final answer can complete the shift after the owner
            # check. Never claim abandonment if the conditional write did not win.
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "clinical_shift_transition_lost",
                    "message": "The Clinical shift changed before it could be abandoned.",
                },
            )
        result = shift.shift_lifecycle_payload(
            store, item_store, packet_provider, abandoned
        )
        current = result.get("session") or abandoned
        return public_payload(current, result)

    @router.post("/shift/{session_id}/next")
    def shift_next(
        session_id: str,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        session = owned_session(session_id, authorization, session_cookie)
        reject_abandoned(session, "serve another case")
        result = shift.next_shift_item(store, item_store, packet_provider, session_id)
        if result is None:
            raise HTTPException(status_code=404, detail="shift session not found")
        current = store.get_shift_session(session_id) or session
        return public_payload(current, result)

    @router.post("/shift/{session_id}/answer")
    def shift_answer(
        session_id: str,
        body: AnswerBody,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        session = owned_session(session_id, authorization, session_cookie)
        reject_abandoned(session, "accept an answer")
        item_id = submitted_item_id(session, body.itemId)
        answer = submitted_answer(session, item_id, body.answer)
        result = shift.grade_and_record(
            store, item_store, packet_provider, session_id, item_id, answer
        )
        if result is None:
            raise HTTPException(status_code=404, detail="shift session or item not found")
        if result.get("error") == "not_pending":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "clinical_item_not_pending",
                    "message": "Only the current pending Clinical item can be answered.",
                    "pendingItemId": public_pending(session, result.get("pendingItemId")),
                },
            )
        if result.get("error") == "context_not_revealed":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "clinical_context_not_revealed",
                    "message": "Commit the ECG-only first look before submitting the clinical decision.",
                },
            )
        if result.get("error") == "phase_not_activated":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "clinical_decide_not_activated",
                    "message": "The decision clock starts only after the revealed case and ECG viewer are ready.",
                },
            )
        if result.get("error") == "stepwise_incomplete":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "clinical_stepwise_incomplete",
                    "message": "Commit each ECG interpretation step before the final clinical decision.",
                    "nextStepIndex": result.get("nextStepIndex"),
                },
            )
        if result.get("error") == "expired":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "clinical_item_expired",
                    "message": "This saved case expired after extended inactivity. Continue to receive a fresh case.",
                },
            )
        current = store.get_shift_session(session_id) or session
        return public_payload(current, result)

    @router.post("/shift/{session_id}/phase")
    def shift_phase(
        session_id: str,
        body: PhaseActivationBody,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        session = owned_session(session_id, authorization, session_cookie)
        reject_abandoned(session, "activate a timer")
        item_id = submitted_item_id(session, body.itemId)
        result = shift.activate_shift_phase(
            store, item_store, packet_provider, session_id, item_id, body.phase
        )
        if result is None or result.get("error") == "missing":
            raise HTTPException(status_code=404, detail="shift session or item not found")
        if result.get("error") == "not_pending":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "clinical_item_not_pending",
                    "message": "Only the current pending Clinical item can activate a phase.",
                    "pendingItemId": public_pending(session, result.get("pendingItemId")),
                },
            )
        if result.get("error") in {"phase_not_ready", "invalid_phase"}:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "clinical_phase_not_ready",
                    "message": "That Clinical phase is not ready to activate.",
                },
            )
        current = store.get_shift_session(session_id) or session
        return public_payload(current, result)

    @router.post("/shift/{session_id}/context")
    def shift_context(
        session_id: str,
        body: FirstLookBody,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        session = owned_session(session_id, authorization, session_cookie)
        reject_abandoned(session, "reveal clinical context")
        item_id = submitted_item_id(session, body.itemId)
        result = shift.reveal_shift_context(
            store, item_store, packet_provider, session_id, item_id, body.answer
        )
        if result is None or result.get("error") == "missing":
            raise HTTPException(status_code=404, detail="shift session or item not found")
        if result.get("error") == "not_pending":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "clinical_item_not_pending",
                    "message": "Only the current pending Clinical item can reveal context.",
                    "pendingItemId": public_pending(session, result.get("pendingItemId")),
                },
            )
        if result.get("error") == "first_look_required":
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "clinical_first_look_required",
                    "message": "Choose a first-look finding category before revealing the case question.",
                },
            )
        if result.get("error") == "phase_not_activated":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "clinical_orient_not_activated",
                    "message": "The timed first-look clock starts only after the ECG viewer is ready.",
                },
            )
        current = store.get_shift_session(session_id) or session
        return public_payload(current, result)

    @router.post("/shift/{session_id}/step")
    def shift_step(
        session_id: str,
        body: StepCommitBody,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        session = owned_session(session_id, authorization, session_cookie)
        reject_abandoned(session, "commit a stepwise decision")
        item_id = submitted_item_id(session, body.itemId)
        result = shift.commit_shift_step(
            store,
            item_store,
            packet_provider,
            session_id,
            item_id,
            body.stepIndex,
            body.answerIndex,
        )
        if result is None or result.get("error") == "missing":
            raise HTTPException(status_code=404, detail="shift session or item not found")
        error = result.get("error")
        if error == "not_pending":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "clinical_item_not_pending",
                    "message": "Only the current pending Clinical item can commit a step.",
                },
            )
        if error == "context_not_revealed":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "clinical_context_not_revealed",
                    "message": "Commit the ECG-only first look before the stepwise decision.",
                },
            )
        if error == "phase_not_activated":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "clinical_decide_not_activated",
                    "message": "The decision clock starts only after the revealed case and ECG viewer are ready.",
                },
            )
        if error in {"not_stepwise", "invalid_step", "step_locked", "step_out_of_order"}:
            messages = {
                "not_stepwise": "This Clinical item does not use staged decisions.",
                "invalid_step": "That step or answer is not available.",
                "step_locked": "A committed Clinical step cannot be changed.",
                "step_out_of_order": "Commit the currently revealed step before continuing.",
            }
            raise HTTPException(
                status_code=409,
                detail={
                    "code": f"clinical_{error}",
                    "message": messages[error],
                    "nextStepIndex": result.get("nextStepIndex"),
                },
            )
        current = store.get_shift_session(session_id) or session
        return public_payload(current, result)

    @router.get("/shift/{session_id}/report")
    def shift_report(
        session_id: str,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        session = owned_session(session_id, authorization, session_cookie)
        report = shift.shift_report(store, session_id, item_store, packet_provider)
        if report is None:
            raise HTTPException(status_code=404, detail="shift session not found")
        return public_payload(session, report)

    return router
