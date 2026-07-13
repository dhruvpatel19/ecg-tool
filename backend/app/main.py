from __future__ import annotations

from typing import Any

from fastapi import Cookie, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from .adaptive import concept_availability, next_case
from .auth import (
    LOGIN_BLOCK_MINUTES,
    REGISTRATION_BLOCK_MINUTES,
    SESSION_COOKIE_NAME,
    SESSION_DAYS,
    AuthError,
    AuthService,
    bearer_token,
)
from .config import get_settings
from .coordinates import ViewerGeometry, point_to_ecg_coordinate
from .corpus_repository import build_repository
from .curriculum import curriculum_view
from .data_sources import case_summary
from .grading import grade_attempt, grade_click_answer, grade_region_answer
from .guest_identity import (
    GuestIdentityMiddleware,
    current_claimable_guest_learner,
    current_guest_learner,
    rotate_guest_cookie,
)
from .guest_progress import GuestProgressClaimConflict, GuestProgressService
from .llm import TutorService
from .mastery_planner import _best_case_concept, _receipt_mode, build_mastery_plan
from .origin_guard import OriginKeyMiddleware, trusted_registration_ip
from .ontology import CONCEPTS, CONCEPT_BY_ID, concept_label
from .objectives import (
    DYNAMIC_SOURCE_UNAVAILABLE,
    OBJECTIVES,
    REGISTRY_VERSION,
    SUBSKILLS,
    ObjectiveDefinition,
    ObjectiveRuntimeAvailability,
    audited_source_packet_supports_objective,
    objective_runtime_availability,
)
from .review import next_review_case, review_status, start_review
from .retention import competency_state
from .schemas import (
    TUTOR_MESSAGE_MAX_CHARS,
    AttemptRequest,
    GuidedLearningEventRequest,
    PathwayProgressUpsertRequest,
    TutorChatRequest,
    validate_tutor_viewer_state,
)
from .source_policy import (
    generic_learner_candidate_policy,
    learner_direct_packet_policy,
)
from .storage import LearningStore
from .tutorials import FRAMEWORKS, get_tutorial, list_tutorials


settings = get_settings()
repo = build_repository(settings)
store = LearningStore(settings.sqlite_path)
store.set_case_packet_provider(repo.get_case)
tutor_service = TutorService(settings)
guest_progress_service = GuestProgressService(store)
auth_service = AuthService(
    store,
    guest_progress_service,
    settings.registration_rate_limit_secret,
)


def session_user(authorization: str | None, session_cookie: str | None = None) -> str | None:
    """Resolve a presented credential strictly; never downgrade it to guest."""
    if authorization is not None:
        token = bearer_token(authorization)
        user_id = auth_service.resolve(token) if token else None
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid or expired session")
        return user_id
    if session_cookie is not None:
        user_id = auth_service.resolve(session_cookie)
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid or expired session")
        return user_id
    return None


def effective_learner(
    authorization: str | None,
    requested: str = "demo",
    session_cookie: str | None = None,
) -> str:
    """Bind state to the authenticated learner or this browser's guest namespace.

    ``requested`` remains in the signature for API compatibility, but it can
    never manufacture an anonymous learner namespace. This also means a body or
    URL cannot override an authenticated user's ownership.
    """
    del requested
    return session_user(authorization, session_cookie) or current_guest_learner()


def _remote_tutor_reservation(learner_id: str, request: Request):
    """Return a lazy reservation so curated/local answers consume no AI quota."""

    client_ip = trusted_registration_ip(request)

    def reserve() -> dict[str, Any]:
        return store.consume_remote_tutor_quota(
            learner_id=learner_id,
            client_ip=client_ip,
            hash_secret=settings.registration_rate_limit_secret,
            authenticated=learner_id.startswith("u_"),
            authenticated_daily_limit=settings.llm_authenticated_daily_limit,
            guest_daily_limit=settings.llm_guest_daily_limit,
            ip_hourly_limit=settings.llm_ip_hourly_limit,
            global_daily_limit=settings.llm_global_daily_limit,
        )

    return reserve


def _learner_case_or_404(case_id: str) -> dict[str, Any]:
    """Resolve a direct learner case while enforcing the global source denylist."""

    case = repo.get_case(case_id)
    if not learner_direct_packet_policy(case).allowed:
        # Use the same response for absent and disallowed packets so a research
        # source cannot be enumerated through learner endpoints.
        raise HTTPException(status_code=404, detail="Case not found")
    assert case is not None
    return case


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=settings.app_env.lower() in {"production", "prod"},
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        secure=settings.app_env.lower() in {"production", "prod"},
        samesite="lax",
        path="/",
    )

app = FastAPI(
    title="ECG AI Learning Platform",
    version="1.0.0",
    description="Educational ECG learning platform with confidence-gated autonomous curation.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GuestIdentityMiddleware, app_env=settings.app_env)
app.add_middleware(OriginKeyMiddleware, shared_secret=settings.origin_guard_secret)


class LearnerProfileUpdate(BaseModel):
    displayName: str = Field(default="Demo Learner", min_length=1, max_length=80)


class ClickGradeRequest(BaseModel):
    lead: str
    timeSec: float
    amplitudeMv: float
    concept: str | None = None


class RegionGradeRequest(BaseModel):
    lead: str
    timeStartSec: float
    timeEndSec: float
    ampMinMv: float
    ampMaxMv: float
    concept: str | None = None


class ViewerPointRequest(BaseModel):
    x: float
    y: float
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    timeStartSec: float = 0
    timeEndSec: float = 10
    ampMinMv: float = -2
    ampMaxMv: float = 2


@app.get("/health")
def health() -> dict[str, bool]:
    # Public legacy liveness alias. Configuration, source/provider details, and
    # readiness failure reasons stay out of this endpoint.
    return {"ok": True}


@app.get("/dataset/status")
def dataset_status() -> dict[str, Any]:
    # Public readiness metadata must not disclose workstation paths or the
    # original mounted-drive locations embedded in a build manifest.
    status = dict(repo.status)
    status.pop("corpus_root", None)
    manifest = dict(status.get("manifest") or {})
    for private_key in ("ptbxlDataRoot", "ptbxlPlusDataRoot", "stagingRoot", "sourceRoot"):
        manifest.pop(private_key, None)
    status["manifest"] = manifest
    return status


class AuthRequest(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)
    displayName: str | None = Field(default=None, max_length=80)
    claimGuestProgress: bool = False


class ChangePasswordRequest(BaseModel):
    currentPassword: str = Field(max_length=256)
    newPassword: str = Field(max_length=256)


@app.post("/auth/register")
def auth_register(
    request: AuthRequest,
    response: Response,
    http_request: Request,
) -> dict[str, Any]:
    guest_id = current_claimable_guest_learner() if request.claimGuestProgress else None
    if request.claimGuestProgress and not guest_id:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "guest_claim_unavailable",
                "message": "No claimable guest progress is available for this browser.",
            },
        )
    try:
        session = auth_service.register(
            request.username,
            request.password,
            request.displayName,
            claim_guest_progress=request.claimGuestProgress,
            guest_id=guest_id,
            # The private client-IP header is accepted only after the Vercel
            # origin key was verified; otherwise the socket peer remains the
            # fail-closed fallback.
            client_ip=trusted_registration_ip(http_request),
        )
        _set_session_cookie(response, session["token"])
        if session.get("guestClaim"):
            rotate_guest_cookie(response, app_env=settings.app_env)
        return {"user": session["user"], "guestClaim": session.get("guestClaim")}
    except GuestProgressClaimConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "guest_progress_already_claimed", "message": str(exc)},
        )
    except AuthError as exc:
        if exc.code == "registration_throttled":
            raise HTTPException(
                status_code=429,
                detail={"message": str(exc)},
                headers={"Retry-After": str(REGISTRATION_BLOCK_MINUTES * 60)},
            )
        raise HTTPException(
            status_code=400,
            detail={"field": exc.field, "code": exc.code, "message": str(exc)},
        )


@app.post("/auth/login")
def auth_login(
    request: AuthRequest,
    response: Response,
    http_request: Request,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    guest_id = current_claimable_guest_learner() if request.claimGuestProgress else None
    if request.claimGuestProgress and not guest_id:
        # Reject independently of credential validity so this opt-in extension
        # cannot become an account-enumeration side channel.
        raise HTTPException(
            status_code=400,
            detail={
                "code": "guest_claim_unavailable",
                "message": "No claimable guest progress is available for this browser.",
            },
        )
    try:
        session = auth_service.login(
            request.username,
            request.password,
            claim_guest_progress=request.claimGuestProgress,
            guest_id=guest_id,
            # Only the origin-key middleware may bless Vercel's private client
            # IP header; direct callers are bucketed by their socket peer.
            client_ip=trusted_registration_ip(http_request),
        )
        old_bearer = bearer_token(authorization)
        if old_bearer and old_bearer != session["token"]:
            auth_service.logout(old_bearer)
        if session_cookie and session_cookie != session["token"]:
            auth_service.logout(session_cookie)
        _set_session_cookie(response, session["token"])
        if session.get("guestClaim"):
            rotate_guest_cookie(response, app_env=settings.app_env)
        return {"user": session["user"], "guestClaim": session.get("guestClaim")}
    except GuestProgressClaimConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "guest_progress_already_claimed", "message": str(exc)},
        )
    except AuthError as exc:
        headers = (
            {"Retry-After": str(LOGIN_BLOCK_MINUTES * 60)}
            if exc.code == "login_throttled"
            else None
        )
        raise HTTPException(
            status_code=429 if exc.code == "login_throttled" else 401,
            detail={"message": str(exc)},
            headers=headers,
        )


@app.get("/auth/guest-progress")
def auth_guest_progress() -> dict[str, Any]:
    """Describe only this browser's unclaimed guest work; never another namespace."""
    return guest_progress_service.summary(current_guest_learner())


@app.post("/auth/logout")
def auth_logout(
    response: Response,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    auth_service.logout(bearer_token(authorization))
    auth_service.logout(session_cookie)
    _clear_session_cookie(response)
    return {"ok": True}


@app.post("/auth/logout-all")
def auth_logout_all(
    response: Response,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    user_id = session_user(authorization, session_cookie)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    revoked = auth_service.logout_all(user_id)
    _clear_session_cookie(response)
    return {"ok": True, "revokedSessions": revoked}


@app.post("/auth/change-password")
def auth_change_password(
    request: ChangePasswordRequest,
    response: Response,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    user_id = session_user(authorization, session_cookie)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        session = auth_service.change_password(
            user_id, request.currentPassword, request.newPassword
        )
    except AuthError as exc:
        raise HTTPException(
            status_code=400,
            detail={"field": exc.field, "code": exc.code, "message": str(exc)},
        )
    _set_session_cookie(response, session["token"])
    return {"user": session["user"], "revokedOtherSessions": True}


@app.get("/auth/me")
def auth_me(
    response: Response,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    if authorization is not None:
        user_id = session_user(authorization, None)
    else:
        user_id = auth_service.resolve(session_cookie)
        if session_cookie and not user_id:
            # Hydration is the one endpoint allowed to turn an expired browser
            # cookie into a confirmed guest state, and it clears that cookie.
            _clear_session_cookie(response)
    user = auth_service.public_user(user_id) if user_id else None
    return {"authenticated": bool(user), "user": user}


@app.post("/ingest/build-index")
def build_index(limit: int = Query(default=80, ge=1, le=1000)) -> dict[str, Any]:
    return repo.build_index(limit)


@app.get("/concepts")
def concepts() -> dict[str, Any]:
    return {
        "concepts": [
            {"id": concept.id, "label": concept.label, "group": concept.group, "highYield": concept.high_yield}
            for concept in CONCEPTS
        ],
        "practiceGroups": concept_availability(repo),
    }


def _independent_receipt_contract(
    definition: ObjectiveDefinition,
    runtime: ObjectiveRuntimeAvailability,
    concept_counts: dict[str, int],
    subskill: str,
) -> dict[str, str] | None:
    """Resolve the same independently scored route used by the mastery planner."""
    if runtime.evidence_ceiling != "eligible_real_case":
        return None
    if subskill not in runtime.eligible_subskills:
        return None
    case_concept = _best_case_concept(definition, concept_counts)
    if not case_concept:
        return None
    mode = _receipt_mode(definition, case_concept, subskill)
    if mode is None:
        return None
    return {
        "mode": mode,
        "caseConcept": case_concept,
        "receiptConcept": definition.id,
        "subskill": subskill,
    }


@app.get("/objectives")
def objective_registry() -> dict[str, Any]:
    """Versioned educational objectives plus honest corpus/task availability."""
    mapped_concepts = {
        case_concept
        for definition in OBJECTIVES.values()
        for case_concept in definition.case_concepts
    }
    candidate_ids = {
        concept_id: {row["case_id"] for row in repo.candidates(concept_id)}
        for concept_id in mapped_concepts
    }
    concept_counts = repo.concept_ab_counts()
    rows: list[dict[str, Any]] = []
    for definition in OBJECTIVES.values():
        runtime_availability = objective_runtime_availability(definition, repo)
        reliable_ids: set[str] = set()
        mapped_counts = []
        for concept_id in definition.case_concepts:
            ids = candidate_ids.get(concept_id, set())
            if definition.id in DYNAMIC_SOURCE_UNAVAILABLE and concept_id == definition.id:
                ids = set(runtime_availability.eligible_case_ids)
            reliable_ids.update(ids)
            mapped_counts.append({"caseConceptId": concept_id, "reliableCaseCount": len(ids)})
        receipt_contracts = [
            contract
            for subskill in definition.allowed_subskills
            if (
                contract := _independent_receipt_contract(
                    definition, runtime_availability, concept_counts, subskill
                )
            ) is not None
        ]
        row = definition.as_api()
        row["evidenceCeiling"] = runtime_availability.evidence_ceiling
        row["unavailableReason"] = runtime_availability.unavailable_reason
        row["coverage"] = {
            "reliableDistinctCases": len(reliable_ids),
            "mappedConcepts": mapped_counts,
            "independentEvidenceAvailable": bool(receipt_contracts),
            "eligibleSubskills": [contract["subskill"] for contract in receipt_contracts],
            "receiptContracts": receipt_contracts,
            "reason": runtime_availability.unavailable_reason or (
                None
                if receipt_contracts
                else "No implemented independent receipt route is available for this objective."
                if reliable_ids
                else "No reliable Tier A/B case is connected to this objective."
            ),
        }
        rows.append(row)
    return {"registryVersion": REGISTRY_VERSION, "subskills": list(SUBSKILLS), "objectives": rows}


@app.get("/cases")
def list_cases(
    concept: str | None = None,
    includeUncertain: bool = False,
    query: str | None = None,
    limit: int = Query(default=200, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    rows = repo.list_cases(
        concept=concept,
        include_uncertain=includeUncertain,
        query=query,
        limit=limit,
        offset=offset,
    )
    return [row for row in rows if generic_learner_candidate_policy(row).allowed]


@app.get("/cases/{case_id}")
def get_case(case_id: str) -> dict[str, Any]:
    case = _learner_case_or_404(case_id)
    return case_summary(case)


@app.get("/cases/{case_id}/packet")
def get_case_packet(case_id: str, blinded: bool = False) -> dict[str, Any]:
    case = _learner_case_or_404(case_id)
    packet = packet_for_case(case)
    return blind_packet(packet) if blinded else packet


@app.get("/cases/{case_id}/waveform")
def get_waveform(
    case_id: str,
    leads: str | None = None,
    start: float = Query(default=0, ge=0),
    end: float | None = Query(default=None, ge=0),
    maxPoints: int = Query(default=1200, ge=100, le=5000),
) -> dict[str, Any]:
    lead_list = [lead.strip() for lead in leads.split(",")] if leads else None
    # Confirm repository membership before touching the numeric shard store.
    # Non-corpus fixture/seed ids are intentionally not exposed by this route.
    repository_case = _learner_case_or_404(case_id)
    waveform = (
        repo.get_waveform_window(case_id, leads=lead_list, start=start, end=end, max_points=maxPoints)
        if repository_case is not None
        else None
    )
    if not waveform:
        raise HTTPException(status_code=404, detail="Case not found")
    return waveform


@app.get("/cases/{case_id}/ptbxl-plus")
def get_ptbxl_plus(case_id: str) -> dict[str, Any]:
    case = _learner_case_or_404(case_id)
    return case.get("ptbxl_plus", {})


@app.post("/viewer/map-point")
def map_viewer_point(request: ViewerPointRequest) -> dict[str, Any]:
    return point_to_ecg_coordinate(
        request.x,
        request.y,
        ViewerGeometry(
            width=request.width,
            height=request.height,
            time_start_sec=request.timeStartSec,
            time_end_sec=request.timeEndSec,
            amp_min_mv=request.ampMinMv,
            amp_max_mv=request.ampMaxMv,
        ),
    )


@app.get("/learners/{learner_id}")
def get_profile(
    learner_id: str,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    return store.ensure_profile(effective_learner(authorization, learner_id, session_cookie))


@app.put("/learners/{learner_id}")
def update_profile(
    learner_id: str,
    update: LearnerProfileUpdate,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    return store.ensure_profile(effective_learner(authorization, learner_id, session_cookie), update.displayName)


@app.get("/learners/{learner_id}/mastery")
def mastery_summary(
    learner_id: str,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    learner = effective_learner(authorization, learner_id, session_cookie)
    profile = store.ensure_profile(learner)
    return {
        "learnerId": learner,
        "mastery": profile["mastery"],
        "subskillMastery": profile["subskillMastery"],
        "weakObjectives": profile["weakObjectives"],
        "misconceptions": profile["misconceptions"],
        "recentAttempts": profile["recentAttempts"],
    }


def _competency_state(row: dict[str, Any] | None) -> str:
    return competency_state(row)


@app.get("/learners/{learner_id}/competencies")
def competency_registry_state(
    learner_id: str,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    learner = effective_learner(authorization, learner_id, session_cookie)
    profile = store.ensure_profile(learner)
    observed = {
        (row["concept"], row["subskill"]): row
        for row in profile.get("subskillMastery", [])
    }
    concept_counts = repo.concept_ab_counts()
    objectives: list[dict[str, Any]] = []
    for definition in OBJECTIVES.values():
        runtime_availability = objective_runtime_availability(definition, repo)
        cells = []
        for subskill in definition.allowed_subskills:
            actual = observed.get((definition.id, subskill))
            receipt_contract = _independent_receipt_contract(
                definition, runtime_availability, concept_counts, subskill
            )
            independently_eligible = receipt_contract is not None
            cells.append({
                "subskill": subskill,
                "state": _competency_state(actual),
                "formativeScore": float(actual.get("formativeScore", 0.0)) if actual else 0.0,
                # The scheduler may use a Bayesian-style prior internally, but an
                # unseen learner-facing cell must never look like earned mastery.
                "independentMastery": float(actual.get("independentMastery", 0.0)) if actual else 0.0,
                "attempts": int(actual.get("attempts", 0)) if actual else 0,
                "independentAttempts": int(actual.get("independentAttempts", 0)) if actual else 0,
                "highConfidenceWrong": int(actual.get("highConfidenceWrong", 0)) if actual else 0,
                "lastPracticedAt": actual.get("lastPracticedAt") if actual else None,
                "lastIndependentAt": actual.get("lastIndependentAt") if actual else None,
                "lastIndependentCorrect": actual.get("lastIndependentCorrect") if actual else None,
                "nextDueAt": actual.get("nextDueAt") if actual else None,
                "dueState": actual.get("dueState", "unseen") if actual else "unseen",
                "isDue": bool(actual.get("isDue", False)) if actual else False,
                "overdueDays": float(actual.get("overdueDays", 0.0)) if actual else 0.0,
                "daysUntilDue": actual.get("daysUntilDue") if actual else None,
                "stabilityDays": float(actual.get("stabilityDays", 0.0)) if actual else 0.0,
                "lapses": int(actual.get("lapses", 0)) if actual else 0,
                "spacedRetrievals": int(actual.get("spacedRetrievals", 0)) if actual else 0,
                "distinctEligibleEcgs": int(actual.get("distinctEligibleEcgs", 0)) if actual else 0,
                "distinctSuccessfulEcgs": int(actual.get("distinctSuccessfulEcgs", 0)) if actual else 0,
                "distinctModes": int(actual.get("distinctModes", 0)) if actual else 0,
                "distinctMorphologies": int(actual.get("distinctMorphologies", 0)) if actual else 0,
                "independentEvidenceAvailable": independently_eligible,
                "independentReceipt": receipt_contract,
                "evidenceUncertainty": runtime_availability.unavailable_reason or (
                    f"No implemented independent {subskill.replace('_', ' ')} receipt route is available for this objective."
                    if not independently_eligible
                    else
                    "No observation recorded yet."
                    if actual is None
                    else actual.get("retentionUncertainty")
                ),
            })
        objectives.append({
            "objectiveId": definition.id,
            "label": definition.label,
            "domain": definition.domain,
            "caseConcepts": list(definition.case_concepts),
            "evidenceCeiling": runtime_availability.evidence_ceiling,
            "subskills": cells,
        })
    return {
        "learnerId": learner,
        "registryVersion": REGISTRY_VERSION,
        "objectives": objectives,
    }


@app.get("/adaptive/plan")
def adaptive_mastery_plan(
    learnerId: str = "demo",
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    """Return a transparent cross-mode plan for the effective learner.

    The caller-supplied learner id is advisory only; cookie/bearer ownership is
    resolved exactly as it is for the competency registry.
    """
    learner = effective_learner(authorization, learnerId, session_cookie)
    profile = store.ensure_profile(learner)
    clinical_concepts = set(clinical_item_store.coverage(status="harness_pass"))
    runtime = {
        definition.id: objective_runtime_availability(definition, repo)
        for definition in OBJECTIVES.values()
    }
    return {
        "learnerId": learner,
        **build_mastery_plan(
            profile,
            repo.concept_ab_counts(),
            runtime_evidence={
                objective_id: availability.evidence_ceiling
                for objective_id, availability in runtime.items()
            },
            runtime_subskills={
                objective_id: set(availability.eligible_subskills)
                for objective_id, availability in runtime.items()
            },
            clinical_concepts=clinical_concepts,
        ),
    }


@app.get("/learners/{learner_id}/pathway-progress")
def pathway_progress(
    learner_id: str,
    pathwayId: str | None = Query(default=None, min_length=1, max_length=120),
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    learner = effective_learner(authorization, learner_id, session_cookie)
    return {
        "learnerId": learner,
        "items": store.get_pathway_progress(learner, pathwayId),
    }


@app.post("/learners/{learner_id}/pathway-progress")
def upsert_pathway_progress(
    learner_id: str,
    request: PathwayProgressUpsertRequest,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    learner = effective_learner(authorization, learner_id, session_cookie)
    return {
        "learnerId": learner,
        "items": store.upsert_pathway_progress(
            learner,
            [item.model_dump() for item in request.items],
            source=request.source,
            merge=request.merge,
        ),
    }


@app.post("/attempts")
def save_interpretation_attempt(
    attempt: AttemptRequest,
    http_request: Request,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    learner = effective_learner(authorization, attempt.learnerId, session_cookie)
    case = _learner_case_or_404(attempt.caseId)
    grade = grade_attempt(case, attempt)
    if attempt.mode in {"concept_practice", "rapid_practice"}:
        # Training and Rapid have exact concept+subskill receipt ledgers. The
        # generic grader remains an attempt audit, but it must not also mutate
        # (or advertise a delta for) the legacy objective ledger.
        grade = {
            **grade,
            "masteryDelta": {},
            "legacyObjectiveMasterySuppressed": True,
        }
    attempt_id = store.save_attempt(
        learner_id=learner,
        case_id=attempt.caseId,
        mode=attempt.mode,
        structured_answer=attempt.structuredAnswer.model_dump(),
        free_text_answer=attempt.freeTextAnswer,
        confidence=attempt.confidence,
        hints_used=attempt.hintsUsed,
        grade=grade,
    )
    tutor = tutor_service.chat(
        TutorChatRequest(
            learnerId=learner,
            mode=attempt.mode,
            caseId=attempt.caseId,
            learnerMessage=f"Grade this interpretation: {attempt.freeTextAnswer}",
            structuredAnswer=attempt.structuredAnswer,
        ),
        packet_for_case(case),
        store.get_profile(learner),
        remote_reservation=_remote_tutor_reservation(learner, http_request),
    )
    return {"attemptId": attempt_id, "grade": grade, "tutor": tutor, "profile": store.get_profile(learner)}


@app.post("/learning-events/guided")
def save_guided_learning_event(
    event: GuidedLearningEventRequest,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    learner = effective_learner(authorization, event.learnerId, session_cookie)
    payload = event.model_dump()
    packet = repo.get_case(event.caseId) if event.caseId else None
    supported = set((packet or {}).get("supported_objectives") or [])
    definition = OBJECTIVES.get(event.concept)
    grounded_concepts = set(definition.case_concepts) if definition else {event.concept}
    source = str((packet or {}).get("source") or "").casefold()
    audited_dynamic_source = audited_source_packet_supports_objective(packet, event.concept)
    verified_real_case = bool(
        packet
        and event.caseProvenance in {"real_eligible", "real_reviewed"}
        and event.caseEligible
        and (source in {"ptbxl", "prepared_bundle"} or audited_dynamic_source)
        and (packet or {}).get("teaching_tier") in {"A", "B"}
        and bool(grounded_concepts & supported)
    )
    diagnostic_subclasses = ((packet or {}).get("ptbxl") or {}).get("diagnostic_subclass") or []
    if isinstance(diagnostic_subclasses, str):
        diagnostic_subclasses = [diagnostic_subclasses]
    payload["_retentionVerified"] = verified_real_case
    # This public endpoint receives a client-evaluated tutorial result. The
    # authored interaction remains useful formative evidence, but it is not a
    # server grade and therefore can never issue independent mastery. Training,
    # Rapid, and Clinical use their own server-owned graders and internal write
    # paths for independent receipts.
    payload["_serverVerifiedScoring"] = False
    payload["_retentionMorphologyKey"] = (
        "|".join(sorted(str(value) for value in diagnostic_subclasses if value))
        if verified_real_case else None
    )
    return store.save_guided_learning_event(learner, payload)


@app.post("/grade/structured")
def grade_structured(attempt: AttemptRequest) -> dict[str, Any]:
    case = _learner_case_or_404(attempt.caseId)
    return grade_attempt(case, attempt)


@app.post("/grade/text")
def grade_text(attempt: AttemptRequest) -> dict[str, Any]:
    case = _learner_case_or_404(attempt.caseId)
    return grade_attempt(case, attempt)


@app.post("/grade/click/{case_id}")
def grade_click(case_id: str, request: ClickGradeRequest) -> dict[str, Any]:
    case = _learner_case_or_404(case_id)
    return grade_click_answer(case, request.lead, request.timeSec, request.amplitudeMv, request.concept)


@app.post("/grade/region/{case_id}")
def grade_region(case_id: str, request: RegionGradeRequest) -> dict[str, Any]:
    case = _learner_case_or_404(case_id)
    if request.timeEndSec <= request.timeStartSec or request.ampMaxMv <= request.ampMinMv:
        raise HTTPException(status_code=422, detail="Region must have positive time and amplitude spans")
    return grade_region_answer(
        case,
        request.lead,
        request.timeStartSec,
        request.timeEndSec,
        request.ampMinMv,
        request.ampMaxMv,
        request.concept,
    )


@app.get("/practice/next")
def get_next_practice_case(
    learnerId: str = "demo", conceptId: str | None = None, subskill: str | None = None,
    excludeCaseIds: str | None = Query(default=None, max_length=4000),
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    allowed_subskills = {"recognize", "localize", "measure", "discriminate", "explain_mechanism", "synthesize", "apply_in_context", "calibrate_confidence"}
    excluded = [item.strip() for item in (excludeCaseIds or "").split(",") if item.strip()]
    if len(excluded) > 100 or any(len(item) > 128 for item in excluded):
        raise HTTPException(status_code=422, detail="excludeCaseIds accepts at most 100 bounded case ids")
    result = next_case(
        repo,
        store,
        learner_id=effective_learner(authorization, learnerId, session_cookie),
        concept_id=conceptId,
        subskill_id=subskill if subskill in allowed_subskills else None,
        exclude_case_ids=set(excluded),
    )
    # Practice is assessment: don't leak the report/top-concepts in the pre-answer payload.
    if result.get("case"):
        result["case"] = blind_summary(result["case"])
    return result


class ReviewStartRequest(BaseModel):
    learnerId: str = "demo"
    conceptId: str | None = None
    groupId: str | None = None
    objectives: list[str] | None = None
    targetMastery: float = Field(default=0.8, ge=0.1, le=1.0)
    maxCases: int = Field(default=30, ge=1, le=200)


@app.post("/review/start")
def review_start(
    request: ReviewStartRequest,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    result = start_review(
        repo,
        store,
        effective_learner(authorization, request.learnerId, session_cookie),
        concept_id=request.conceptId,
        group_id=request.groupId,
        objectives=request.objectives,
        target_mastery=request.targetMastery,
        max_cases=request.maxCases,
    )
    if result is None or result.get("error"):
        raise HTTPException(status_code=400, detail=(result or {}).get("error", "Could not start review session."))
    if result.get("case"):
        result["case"] = blind_summary(result["case"])
    return result


@app.get("/review/{session_id}")
def review_get(
    session_id: str,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    owner = effective_learner(authorization, session_cookie=session_cookie)
    session = store.get_review_session(session_id)
    if not session or session.get("learnerId") != owner:
        raise HTTPException(status_code=404, detail="Review session not found")
    result = review_status(repo, store, session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Review session not found")
    if result.get("case"):
        result["case"] = blind_summary(result["case"])
    return result


@app.post("/review/{session_id}/next")
def review_next(
    session_id: str,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    owner = effective_learner(authorization, session_cookie=session_cookie)
    session = store.get_review_session(session_id)
    if not session or session.get("learnerId") != owner:
        raise HTTPException(status_code=404, detail="Review session not found")
    result = next_review_case(repo, store, session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Review session not found")
    if result.get("case"):
        result["case"] = blind_summary(result["case"])
    return result


@app.post("/tutor/chat")
def tutor_chat(
    request: TutorChatRequest,
    http_request: Request,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    case_packet = None
    if request.caseId:
        case = repo.get_case(request.caseId)
        if case:
            if not learner_direct_packet_policy(case).allowed:
                raise HTTPException(status_code=404, detail="Case not found")
            case_packet = packet_for_case(case)
        else:
            # Clinical items are authored scenarios, but their tracings must
            # resolve through the same real PTB-backed packet provider.
            case_packet = clinical_packet(request.caseId)
        if case_packet is None:
            raise HTTPException(status_code=404, detail="Case not found")
    profile = store.ensure_profile(effective_learner(authorization, request.learnerId, session_cookie))
    return tutor_service.chat(
        request,
        case_packet,
        profile,
        remote_reservation=_remote_tutor_reservation(profile["learnerId"], http_request),
    )


@app.post("/tutor/viewer-actions")
def tutor_viewer_actions(
    request: TutorChatRequest,
    http_request: Request,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    request.learnerMessage = request.learnerMessage or "Suggest grounded viewer actions for this ECG."
    return tutor_chat(request, http_request, authorization, session_cookie)


class FoundationsTutorRequest(BaseModel):
    learnerMessage: str = Field(default="", max_length=TUTOR_MESSAGE_MAX_CHARS)
    scope: str | None = Field(default=None, max_length=160)


@app.post("/tutor/foundations")
def tutor_foundations(
    request: FoundationsTutorRequest,
    http_request: Request,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    """Concept tutor for the Foundations learning module: answers beginner ECG-reading
    questions without needing an ECG image, strictly describe-not-diagnose."""
    learner = effective_learner(authorization, session_cookie=session_cookie)
    return tutor_service.foundations(
        request.learnerMessage,
        request.scope,
        learner_id=learner,
        remote_reservation=_remote_tutor_reservation(learner, http_request),
    )


class TutorMessageRequest(BaseModel):
    learnerId: str = Field(default="demo", max_length=160)
    threadId: str | None = Field(default=None, max_length=160)
    mode: str = Field(default="freeform", max_length=80)
    lessonId: str | None = Field(default=None, max_length=160)
    caseId: str | None = Field(default=None, max_length=240)
    message: str = Field(min_length=1, max_length=TUTOR_MESSAGE_MAX_CHARS)
    viewerState: dict[str, Any] = Field(default_factory=dict)

    _bounded_viewer_state = field_validator("viewerState")(validate_tutor_viewer_state)


@app.post("/tutor/message")
def tutor_message(
    request: TutorMessageRequest,
    http_request: Request,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    learner = effective_learner(authorization, request.learnerId, session_cookie)
    if request.threadId:
        existing_thread = store.get_thread(request.threadId)
        if existing_thread and existing_thread.get("learnerId") != learner:
            raise HTTPException(status_code=404, detail="Thread not found")
    case_packet = None
    if request.caseId:
        case = repo.get_case(request.caseId)
        if case:
            if not learner_direct_packet_policy(case).allowed:
                raise HTTPException(status_code=404, detail="Case not found")
            case_packet = packet_for_case(case)
        else:
            # Clinical items may use a scenario id distinct from the underlying
            # real ECG id. The provider remains provenance-gated and arbitrary
            # ids fail closed.
            case_packet = clinical_packet(request.caseId)
        if case_packet is None:
            raise HTTPException(status_code=404, detail="Case not found")
    lesson = get_tutorial(request.lessonId) if request.lessonId else None
    profile = store.ensure_profile(learner)
    thread_id = store.ensure_thread(
        learner, request.threadId, request.mode, request.lessonId, request.caseId
    )
    history = store.thread_history(thread_id)
    store.append_tutor_message(thread_id, "user", request.message)
    result = tutor_service.converse(
        request.message,
        case_packet,
        profile,
        history,
        request.mode,
        lesson,
        request.viewerState,
        remote_reservation=_remote_tutor_reservation(learner, http_request),
    )
    store.append_tutor_message(
        thread_id,
        "tutor",
        result.get("tutorMessage", ""),
        result.get("viewerActions"),
        {
            "socraticQuestion": result.get("socraticQuestion"),
            "onLessonTopic": result.get("onLessonTopic", True),
            "citedEvidence": result.get("citedEvidence", []),
            "uncertaintyWarnings": result.get("uncertaintyWarnings", []),
            "suggestedNextStep": result.get("suggestedNextStep"),
            "remoteUsage": result.get("remoteUsage"),
        },
    )
    result["threadId"] = thread_id
    return result


@app.get("/tutor/thread/{thread_id}")
def tutor_thread(
    thread_id: str,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    thread = store.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if thread.get("learnerId") != effective_learner(authorization, session_cookie=session_cookie):
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread


@app.get("/tutor/threads")
def tutor_threads(
    mode: str | None = None,
    lessonId: str | None = None,
    caseId: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    learner = effective_learner(authorization, session_cookie=session_cookie)
    return {
        "threads": store.list_threads(
            learner,
            mode=mode,
            lesson_id=lessonId,
            case_id=caseId,
            limit=limit,
        )
    }


@app.get("/curriculum")
def curriculum(
    learnerId: str = "demo",
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    profile = store.ensure_profile(effective_learner(authorization, learnerId, session_cookie))
    mastery = {row["objective"]: row["mastery"] for row in profile["mastery"]}
    return curriculum_view(repo, mastery)


@app.get("/tutorials")
def tutorials() -> dict[str, Any]:
    return {"frameworks": FRAMEWORKS, "tutorials": list_tutorials()}


@app.get("/tutorials/{lesson_id}")
def tutorial(
    lesson_id: str,
    concept: str | None = None,
    excludeCaseId: str | None = None,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    lesson = get_tutorial(lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Tutorial not found")
    learner = effective_learner(authorization, session_cookie=session_cookie)
    requested_concept = concept if concept in CONCEPT_BY_ID else lesson.get("caseConcept")
    excluded = {excludeCaseId} if excludeCaseId else set()
    selection = next_case(repo, store, learner, requested_concept, teaching_exemplar=True, exclude_case_ids=excluded)
    selected = selection["case"]
    if selected is None:
        # Keep the route usable while making the data boundary explicit. This
        # fallback is a contrast/mechanism tracing, never evidence that the
        # unavailable requested finding is present.
        # Never re-serve the rejected pathology as if it were a canonical
        # example. Use an eligible normal/contrast tracing and label it clearly.
        fallback = next_case(repo, store, learner, "normal_ecg", teaching_exemplar=True, exclude_case_ids=excluded)
        if fallback.get("case") is None:
            fallback = next_case(repo, store, learner, "normal_ecg", exclude_case_ids=excluded)
        selected = fallback["case"]
        selection = {
            **selection,
            "requestedConceptUnavailable": True,
            "fallbackReason": fallback.get("reason"),
        }
    return {
        "lesson": lesson,
        "frameworks": FRAMEWORKS,
        "recommendedCase": selected,
        "selection": selection,
        "openingPrompt": f"Inspect the tracing and justify {', '.join(concept_label(item) for item in lesson['objectives'][:3])} using visible ECG evidence.",
    }


def packet_for_case(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": case["case_id"],
        "display_id": case.get("display_id", case["case_id"]),
        "clinical_stem": case.get("clinical_stem", ""),
        "source": case.get("source", "unknown"),
        "waveform": case["waveform"],
        "ptbxl": case["ptbxl"],
        "ptbxl_plus": case["ptbxl_plus"],
        "signal_quality": case["signal_quality"],
        "concept_confidence": case["concept_confidence"],
        "supported_objectives": case["supported_objectives"],
        "unsupported_objectives": case["unsupported_objectives"],
        "teaching_tier": case["teaching_tier"],
        "inclusion_reasons": case["inclusion_reasons"],
        "exclusion_reasons": case["exclusion_reasons"],
        "llm_allowed_claims": case["llm_allowed_claims"],
        "llm_forbidden_claims": case["llm_forbidden_claims"],
        "teaching_points": case.get("teaching_points", []),
    }


def blind_packet(packet: dict[str, Any]) -> dict[str, Any]:
    """Strip diagnosis-revealing fields so a pre-submission practice payload can't
    leak the answer key (V1 audit): no labels/report/statements/concepts/objectives.
    Keeps the waveform, raw measurements (to interpret), neutral segment ROIs, and
    signal quality — what a learner reads off the tracing themselves."""
    plus = dict(packet.get("ptbxl_plus") or {})
    ptbxl = packet.get("ptbxl") or {}
    return {
        "case_id": packet["case_id"],
        "display_id": packet.get("display_id"),
        "clinical_stem": packet.get("clinical_stem", ""),
        "source": packet.get("source", "unknown"),
        "waveform": packet["waveform"],
        "ptbxl": {"fold": ptbxl.get("fold"), "metadata": {"age": (ptbxl.get("metadata") or {}).get("age"),
                                                            "sex": (ptbxl.get("metadata") or {}).get("sex")}},
        "ptbxl_plus": {
            "features": plus.get("features", {}),
            "measurements": plus.get("measurements", {}),
            "fiducials": plus.get("fiducials", {"rois": []}),  # neutral segment locations only
            "median_beats": plus.get("median_beats", {}),
            "per_lead_st_mv": plus.get("per_lead_st_mv", {}),
        },
        "signal_quality": packet.get("signal_quality", {}),
        "teaching_tier": packet.get("teaching_tier"),
        "blinded": True,
    }


def blind_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """Practice case summary without the report/top-concepts that reveal the read."""
    redacted = dict(summary)
    redacted["report"] = ""
    redacted["topConcepts"] = []
    return redacted


# --- Clinical Decisions mode wiring -----------------------------------------------
from .clinical.provenance import assert_serving_bank_provenance  # noqa: E402
from .clinical.real_items import vetted_real_items  # noqa: E402
from .clinical_routes import build_clinical_router  # noqa: E402
from .rapid_routes import build_rapid_router  # noqa: E402
from .training_routes import build_training_router  # noqa: E402
from .training_store import TrainingCampaignStore  # noqa: E402
from .store.clinical_item_store import ClinicalItemStore  # noqa: E402

clinical_item_store = ClinicalItemStore(settings.sqlite_path)
training_campaign_store = TrainingCampaignStore(settings.sqlite_path, store.connect)


def clinical_packet(ecg_id: str) -> dict[str, Any] | None:
    """Resolve learner Clinical ECGs only through the active checked repository."""
    case = repo.get_case(ecg_id)
    return packet_for_case(case) if case else None


# The learner bank is code-defined, real-ECG-backed, and automatically screened.
# It is formative content, not clinician-reviewed. Publish the full replacement
# in one transaction so multiple workers never expose a clear/partial bank.
clinical_item_store.replace_items_atomically(vetted_real_items(clinical_packet))
assert_serving_bank_provenance(clinical_item_store.iter_items(), clinical_packet)


app.include_router(
    build_clinical_router(store, clinical_item_store, clinical_packet, effective_learner)
)
app.include_router(
    build_rapid_router(
        repo,
        store,
        packet_for_case,
        blind_packet,
        blind_summary,
        effective_learner,
    )
)
app.include_router(
    build_training_router(
        repo,
        store,
        training_campaign_store,
        packet_for_case,
        blind_packet,
        blind_summary,
        effective_learner,
    )
)

# Registered after learner routers so readiness describes the fully initialized
# repository and learner store.
from .ops import build_ops_router  # noqa: E402

app.include_router(build_ops_router(settings, repo, store, clinical_item_store))
