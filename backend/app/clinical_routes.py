"""FastAPI routes for the Clinical Decisions mode.

Built as a factory (``build_clinical_router``) that closes over the app's module-level
``store`` / item store / packet provider, so it composes with the existing decorator-style
``main.py`` without a circular import.
"""

from __future__ import annotations

from typing import Any, Callable, Literal

from fastapi import APIRouter, Cookie, Header, HTTPException
from pydantic import BaseModel, Field

from .auth import SESSION_COOKIE_NAME
from .clinical import shift
from .clinical.real_items import (
    CLINICAL_FAMILY_BY_SCENARIO,
    REAL_ECGS_BY_SCENARIO,
    normalized_scenario_signature,
)
from .clinical.schemas import ClinicalAnswer

PacketProvider = Callable[[str], dict[str, Any] | None]
LearnerResolver = Callable[[str | None, str, str | None], str]


class ShiftStartBody(BaseModel):
    learnerId: str = "demo"
    lane: str = "ed"
    tier: str = "shift"  # learn | shift
    focus: str | None = Field(default=None, max_length=80)
    subskill: str | None = Field(default=None, max_length=80)
    length: int = Field(default=5, ge=1, le=50)


class AnswerBody(BaseModel):
    itemId: str
    answer: ClinicalAnswer = Field(default_factory=ClinicalAnswer)


class FirstLookBody(BaseModel):
    itemId: str
    answer: ClinicalAnswer


class PhaseActivationBody(BaseModel):
    itemId: str
    phase: Literal["orient", "decide"]


def build_clinical_router(
    store,
    item_store,
    packet_provider: PacketProvider,
    resolve_learner: LearnerResolver,
) -> APIRouter:
    router = APIRouter(prefix="/clinical", tags=["clinical-decisions"])

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

    def tracing_source_summary(items: list[Any]) -> tuple[list[str], dict[str, int]]:
        """Report the sources that the serving bank actually resolves to.

        The production bank is provenance-gated at startup, but this endpoint is
        also the learner/admin-visible audit surface.  Deriving the summary from
        the same packet provider prevents a legacy allow-list entry from being
        presented as though it were in the current bank.
        """

        counts: dict[str, int] = {}
        for item in items:
            packet = packet_provider(item.ecg_id)
            source = str((packet or {}).get("source") or "").strip()
            if source:
                counts[source] = counts.get(source, 0) + 1
        return sorted(counts), dict(sorted(counts.items()))

    @router.get("/bank/status")
    def bank_status() -> dict[str, Any]:
        served = list(item_store.list_for_serving(status="harness_pass"))
        tracing_sources, tracing_source_counts = tracing_source_summary(served)
        family_by_ecg = {
            ecg_id: CLINICAL_FAMILY_BY_SCENARIO[scenario_id]
            for scenario_id, ecg_ids in REAL_ECGS_BY_SCENARIO.items()
            for ecg_id in ecg_ids
        }
        return {
            "counts": item_store.count_by_status(),
            "distinctRealEcgs": len({item.ecg_id for item in served}),
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
        }

    @router.get("/bank/coverage")
    def bank_coverage() -> dict[str, Any]:
        """Per-concept pool depth (items + distinct ECGs) — surfaces which pathologies can
        sustain adaptive repetition and which are too thin to drill on yet."""
        served = list(item_store.list_for_serving(status="harness_pass"))
        tracing_sources, tracing_source_counts = tracing_source_summary(served)
        return {
            "coverage": item_store.coverage(status="harness_pass"),
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
        return {"session": store.get_shift_session(session["sessionId"]), "next": first}

    @router.get("/shift/active")
    def shift_active(
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        learner = resolve_learner(authorization, "demo", session_cookie)
        session = store.get_resumable_shift_session(learner)
        return shift.shift_lifecycle_payload(store, item_store, packet_provider, session)

    @router.get("/shift/{session_id}")
    def shift_get(
        session_id: str,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        return owned_session(session_id, authorization, session_cookie)

    @router.post("/shift/{session_id}/next")
    def shift_next(
        session_id: str,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        owned_session(session_id, authorization, session_cookie)
        result = shift.next_shift_item(store, item_store, packet_provider, session_id)
        if result is None:
            raise HTTPException(status_code=404, detail="shift session not found")
        return result

    @router.post("/shift/{session_id}/answer")
    def shift_answer(
        session_id: str,
        body: AnswerBody,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        owned_session(session_id, authorization, session_cookie)
        result = shift.grade_and_record(
            store, item_store, packet_provider, session_id, body.itemId, body.answer
        )
        if result is None:
            raise HTTPException(status_code=404, detail="shift session or item not found")
        if result.get("error") == "not_pending":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "clinical_item_not_pending",
                    "message": "Only the current pending Clinical item can be answered.",
                    "pendingItemId": result.get("pendingItemId"),
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
        return result

    @router.post("/shift/{session_id}/phase")
    def shift_phase(
        session_id: str,
        body: PhaseActivationBody,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        owned_session(session_id, authorization, session_cookie)
        result = shift.activate_shift_phase(
            store, item_store, packet_provider, session_id, body.itemId, body.phase
        )
        if result is None or result.get("error") == "missing":
            raise HTTPException(status_code=404, detail="shift session or item not found")
        if result.get("error") == "not_pending":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "clinical_item_not_pending",
                    "message": "Only the current pending Clinical item can activate a phase.",
                    "pendingItemId": result.get("pendingItemId"),
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
        return result

    @router.post("/shift/{session_id}/context")
    def shift_context(
        session_id: str,
        body: FirstLookBody,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        owned_session(session_id, authorization, session_cookie)
        result = shift.reveal_shift_context(
            store, item_store, packet_provider, session_id, body.itemId, body.answer
        )
        if result is None or result.get("error") == "missing":
            raise HTTPException(status_code=404, detail="shift session or item not found")
        if result.get("error") == "not_pending":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "clinical_item_not_pending",
                    "message": "Only the current pending Clinical item can reveal context.",
                    "pendingItemId": result.get("pendingItemId"),
                },
            )
        if result.get("error") == "first_look_required":
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "clinical_first_look_required",
                    "message": "A finding category and confidence are required before context reveal.",
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
        return result

    @router.get("/shift/{session_id}/report")
    def shift_report(
        session_id: str,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        owned_session(session_id, authorization, session_cookie)
        report = shift.shift_report(store, session_id)
        if report is None:
            raise HTTPException(status_code=404, detail="shift session not found")
        return report

    return router
