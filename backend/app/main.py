from __future__ import annotations

import hmac
import math
import re
from http.cookies import CookieError, SimpleCookie
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Literal

from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Path as ApiPath,
    Query,
    Request,
    Response,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from .account_boundary import (
    AccountGenerationRetiredError,
    OwnerParentMissingError,
)
from .adaptive import concept_availability, next_case
from .assessment_ledger import (
    IdempotencyConflictError,
    record_guided_packet_exposure,
)
from .assessment_presentation import (
    public_case_packet,
    public_case_summary,
    public_waveform,
)
from .adaptive_tutor_context import (
    CONTEXT_VERSION as ADAPTIVE_TUTOR_CONTEXT_VERSION,
    TUTOR_SCOPE as ADAPTIVE_TUTOR_SCOPE,
    AdaptiveTutorContextExpired,
    AdaptiveTutorContextNotFound,
    build_adaptive_tutor_context,
    enforce_adaptive_tutor_response,
    issue_adaptive_tutor_context,
    verify_adaptive_tutor_context,
)
from .auth import (
    ACCOUNT_REAUTH_BLOCK_MINUTES,
    EXPORT_AUTHORIZATION_SECONDS,
    EMAIL_RESEND_COOLDOWN_SECONDS,
    EXPORT_AUTH_COOKIE_NAME,
    LOGIN_BLOCK_MINUTES,
    REGISTRATION_BLOCK_MINUTES,
    RECOVERY_BLOCK_MINUTES,
    RECOVERY_CONFIRM_BLOCK_MINUTES,
    PRODUCTION_SESSION_COOKIE_NAME,
    SESSION_COOKIE_NAME as LEGACY_SESSION_COOKIE_NAME,
    SESSION_DAYS,
    AuthError,
    AuthService,
    bearer_token,
    session_cookie_name,
)
from .auth_mailer import BoundedAuthTaskDispatcher, build_auth_mailer
from .config import get_settings
from .coordinates import ViewerGeometry, point_to_ecg_coordinate
from .corpus_repository import build_repository
from .curriculum import curriculum_view
from .data_sources import case_summary
from .ecg_capability import (
    is_ecg_capability,
    issue_ecg_capability,
    matches_ecg_capability,
)
from .clinical.item_reference import public_item_reference
from .clinical.tutor_context import (
    ClinicalTutorContextInvalid,
    ClinicalTutorContextNotFound,
    ClinicalTutorContextNotReady,
    build_clinical_shift_tutor_context,
    build_clinical_tutor_context,
    is_uncommitted_clinical_case,
)
from .grading import grade_attempt, grade_click_answer, grade_region_answer
from .guest_identity import (
    GuestIdentityMiddleware,
    clear_guest_cookie,
    current_claimable_guest_learner,
    current_guest_learner,
)
from .guest_progress import (
    GuestProgressClaimConflict,
    GuestProgressClaimUnavailable,
    GuestProgressService,
)
from .http_errors import privacy_safe_validation_error
from .llm import TutorService, curated_general_teaching
from .learning_activity import ActivityCursorError, get_learning_activity
from .competency_trends import (
    MAX_COMPETENCY_TREND_POINTS,
    get_competency_trend,
)
from .learning_sessions import (
    MAX_SESSION_OFFSET,
    get_learning_session_review,
    get_learning_sessions,
    set_learning_session_attempt_flag,
)
from .learning_replay import (
    build_learning_replay,
    learning_replay_comparison_ecg_id,
    learning_replay_attempt_is_available,
    resolve_learning_replay_ecg_target,
    resolve_learning_replay_attempt,
)
from .study_calendar import (
    CalendarItemConflictError,
    CalendarItemNotFoundError,
    CalendarSourceChangedError,
    calendar_plan_action,
    calendarize_plan_launch_href,
    create_calendar_item,
    delete_calendar_item,
    get_calendar_item,
    get_calendar_snapshot,
    get_competency_due_source,
    get_competency_review_projection,
    replay_calendar_plan_request,
    save_calendar_settings,
    set_calendar_item_completion,
    update_calendar_item,
    validate_calendar_date,
    validate_calendar_range,
    validate_time_zone,
)
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
    validate_objective_subskill,
)
from .review import next_review_case, review_status, start_review
from .rapid_tutor_context import (
    CONTEXT_VERSION as RAPID_TUTOR_CONTEXT_VERSION,
    RapidTutorContextInvalid,
    RapidTutorContextNotFound,
    RapidTutorContextNotReady,
    build_rapid_round_tutor_context,
    deterministic_rapid_tutor_response,
)
from .training_tutor_context import (
    TrainingTutorContextInvalid,
    TrainingTutorContextNotFound,
    TrainingTutorContextNotReady,
    build_training_ecg_tutor_context,
    build_training_set_tutor_context,
    deterministic_training_tutor_response,
)
from .retention import competency_state
from .schemas import (
    LEADS,
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
# Route cookie aliases are fixed when FastAPI builds its dependency graph. In a
# production process this resolves to the RFC-required host-only name; local
# development and deterministic tests retain the familiar legacy name.
SESSION_COOKIE_NAME = session_cookie_name(settings.app_env)
ADAPTIVE_PLAN_CONTEXT_SECRET = settings.adaptive_plan_context_secret
repo = build_repository(settings)
store = LearningStore(
    settings.sqlite_path,
    public_reference_secret=settings.registration_rate_limit_secret,
)
store.set_case_packet_provider(repo.get_case)
tutor_service = TutorService(settings)
guest_progress_service = GuestProgressService(store)
auth_mailer = build_auth_mailer(
    app_env=settings.app_env,
    mode=settings.auth_email_delivery_mode,
    smtp_host=settings.auth_smtp_host,
    smtp_port=settings.auth_smtp_port,
    smtp_username=settings.auth_smtp_username,
    smtp_password=settings.auth_smtp_password,
    from_address=settings.auth_email_from_address,
    reply_to=settings.auth_email_reply_to,
    public_app_url=settings.auth_public_app_url,
    smtp_starttls=settings.auth_smtp_starttls,
    smtp_timeout_seconds=settings.auth_smtp_timeout_seconds,
)
auth_recovery_dispatcher = BoundedAuthTaskDispatcher(workers=2, capacity=100)
auth_service = AuthService(
    store,
    guest_progress_service,
    settings.registration_rate_limit_secret,
    mailer=auth_mailer,
    recovery_dispatcher=auth_recovery_dispatcher,
    # The former email-code second step is retained only in isolated legacy
    # tests while deployed students use verified email + password.
    email_two_factor_enabled=settings.app_env == "test",
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
    """Bind learner state to an authenticated account.

    ``requested`` remains in the signature for API compatibility, but it can
    never override an authenticated user's ownership. The exact test environment
    retains an internal deterministic fixture; deployed environments do not have
    an anonymous learner mode.
    """
    del requested
    user_id = session_user(authorization, session_cookie)
    if user_id:
        if settings.app_env != "test":
            user = auth_service.public_user(user_id)
            account_status = (
                str(user.get("accountStatus")) if user else "email_upgrade_required"
            )
            if account_status != "verified":
                messages = {
                    "email_upgrade_required": "Add and verify an email address before continuing learning.",
                    "email_verification_required": "Verify your email address before continuing learning.",
                }
                raise HTTPException(
                    status_code=403,
                    detail={
                        "code": account_status,
                        "message": messages.get(
                            account_status, "Complete account verification before continuing."
                        ),
                    },
                )
        return user_id
    if settings.app_env == "test":
        return current_guest_learner() or "demo"
    raise HTTPException(
        status_code=401,
        detail={
            "code": "authentication_required",
            "message": "Sign in to save and continue learning progress.",
        },
    )


def require_learning_account(
    response: Response,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> str:
    """Require the verified account boundary before releasing learner content.

    The existing deterministic ``demo`` principal remains available only in the
    exact test environment so corpus and pedagogy unit tests do not manufacture
    hundreds of accounts. Deployed runtimes always require a live, verified
    session through :func:`effective_learner`.
    """

    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["Vary"] = "Authorization, Cookie"
    return effective_learner(authorization, session_cookie=session_cookie)


def require_present_learning_account(
    authorization: str | None,
    session_cookie: str | None,
) -> str:
    """Require an actual browser session for server-served static learning data.

    Unlike ordinary test-mode learning dependencies, this check never accepts
    the anonymous ``demo`` fixture. Test accounts created by the browser harness
    predate email verification and are accepted only in ``APP_ENV=test``; every
    deployed environment still requires the account's verified status.
    """

    user_id = session_user(authorization, session_cookie)
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "authentication_required",
                "message": "Sign in to open learning content.",
            },
        )
    if settings.app_env != "test":
        user = auth_service.public_user(user_id)
        account_status = (
            str(user.get("accountStatus")) if user else "email_upgrade_required"
        )
        if account_status != "verified":
            raise HTTPException(
                status_code=403,
                detail={
                    "code": account_status,
                    "message": "Verify your account before opening learning content.",
                },
            )
    return user_id


_GUIDED_CONTEXT_VERSION = "guided-case-v1"
_GUIDED_CONTEXT_TTL_SECONDS = 2 * 60 * 60
_GUIDED_SESSION_PREFIX = "tutorial:"
_GUIDED_TOKEN_RE = re.compile(r"\A[A-Za-z0-9_:-]{1,120}\Z")


def _pending_assessment_case_ids() -> set[str]:
    """Return ECG ids whose answer boundary has not durably committed.

    The lookup is intentionally auth-agnostic. A learner cannot bypass secrecy
    by omitting their cookie or asking through a second account.
    """

    pending: set[str] = set()
    campaign_store = globals().get("training_campaign_store")
    if campaign_store is not None:
        with campaign_store.connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT pending_case_id FROM training_campaigns "
                "WHERE status = 'active' AND pending_case_id IS NOT NULL"
            ).fetchall()
        pending.update(str(row["pending_case_id"]) for row in rows)
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT pending_case_id FROM rapid_rounds "
            "WHERE status = 'active' AND pending_case_id IS NOT NULL"
        ).fetchall()
    pending.update(str(row["pending_case_id"]) for row in rows)
    item_store = globals().get("clinical_item_store")
    if item_store is not None:
        for item_id in store.pending_clinical_item_ids():
            item = item_store.get_item(item_id)
            if item is not None:
                pending.add(str(item.ecg_id))
                if item.prior_ecg_id:
                    pending.add(str(item.prior_ecg_id))
    return pending


def _assessment_case_pending(case_id: str | None) -> bool:
    if not case_id:
        return False
    normalized = str(case_id)
    campaign_store = globals().get("training_campaign_store")
    if campaign_store is not None and campaign_store.is_case_pending(normalized):
        return True
    if store.is_rapid_case_pending(normalized):
        return True
    item_store = globals().get("clinical_item_store")
    if item_store is not None:
        for item_id in store.pending_clinical_item_ids():
            item = item_store.get_item(item_id)
            if item is not None and normalized in {
                str(item.ecg_id),
                str(item.prior_ecg_id or ""),
            }:
                return True
    return False


def _assessment_case_pending_for_learner(case_id: str | None, learner_id: str) -> bool:
    """Return whether this owner currently has this ECG behind a commit gate."""

    if not case_id:
        return False
    normalized = str(case_id)
    campaign_store = globals().get("training_campaign_store")
    if (
        campaign_store is not None
        and campaign_store.is_case_pending_for_learner(normalized, learner_id)
    ):
        return True
    if store.is_rapid_case_pending_for_learner(normalized, learner_id):
        return True
    item_store = globals().get("clinical_item_store")
    if item_store is not None:
        for item_id in store.pending_clinical_item_ids(learner_id):
            item = item_store.get_item(item_id)
            if item is not None and normalized in {
                str(item.ecg_id),
                str(item.prior_ecg_id or ""),
            }:
                return True
    return False


def _guard_pending_assessment_case(
    case_id: str | None,
    *,
    learner_id: str | None = None,
) -> None:
    if not _assessment_case_pending(case_id):
        return
    if learner_id and _assessment_case_pending_for_learner(case_id, learner_id):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "assessment_case_not_committed",
                "message": "Commit the active assessment response before requesting answer-bearing case help.",
            },
        )
    # A learner who has already durably committed this ECG may use their own
    # post-commit debrief even while another learner happens to receive the
    # same corpus ECG. The other learner remains blocked. Without this
    # owner-aware exception, normal concurrent use can make AI feedback fail at
    # random whenever two campaigns overlap.
    if learner_id and case_id and store.has_committed_attempt(learner_id, str(case_id)):
        return
    raise HTTPException(
        status_code=409,
        detail={
            "code": "assessment_case_not_committed",
            "message": "Commit the active assessment response before requesting answer-bearing case help.",
        },
    )


def _guided_session_id(lesson_id: str) -> str:
    return f"{_GUIDED_SESSION_PREFIX}{lesson_id}"


def _guided_case_reference(learner_id: str, lesson_id: str, case_id: str) -> str:
    """Issue a payload-free, owner/lesson-bound reference for one teaching ECG."""

    return issue_ecg_capability(
        settings.registration_rate_limit_secret,
        learner_id,
        "guided",
        _guided_session_id(lesson_id),
        case_id,
    )


def _guided_context_token(learner_id: str, case_id: str, lesson_id: str) -> str:
    """Issue an opaque grading context; never serialize its corpus lookup key."""

    return issue_ecg_capability(
        settings.registration_rate_limit_secret,
        learner_id,
        _GUIDED_CONTEXT_VERSION,
        _guided_session_id(lesson_id),
        case_id,
    )


def _guided_exposure_rows(
    learner_id: str,
    *,
    lesson_id: str | None = None,
    recent_only: bool = False,
) -> list[Any]:
    clauses = [
        "owner_id = ?",
        "mode = 'guided'",
        "event_type = 'item_presented'",
    ]
    params: list[Any] = [learner_id]
    if lesson_id is not None:
        clauses.append("session_id = ?")
        params.append(_guided_session_id(lesson_id))
    if recent_only:
        clauses.append("occurred_at >= ?")
        params.append(
            (
                datetime.now(UTC)
                - timedelta(seconds=_GUIDED_CONTEXT_TTL_SECONDS)
            ).isoformat(timespec="microseconds")
        )
    with store.connect() as conn:
        return conn.execute(
            "SELECT session_id, ecg_id, MAX(occurred_at) AS last_seen "
            "FROM learner_events WHERE "
            + " AND ".join(clauses)
            + " GROUP BY session_id, ecg_id ORDER BY last_seen DESC",
            tuple(params),
        ).fetchall()


def _resolve_guided_case_reference(
    learner_id: str,
    lesson_id: str,
    reference: object,
) -> str | None:
    if not is_ecg_capability(reference):
        return None
    session_id = _guided_session_id(lesson_id)
    for row in _guided_exposure_rows(learner_id, lesson_id=lesson_id):
        canonical_id = str(row["ecg_id"])
        if matches_ecg_capability(
            reference,
            settings.registration_rate_limit_secret,
            learner_id,
            "guided",
            session_id,
            canonical_id,
        ):
            return canonical_id
    return None


def _guided_case_committed(learner_id: str, canonical_id: str) -> bool:
    """Return whether this learner has durably submitted any Guided action."""

    with store.connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM guided_learning_events "
            "WHERE learner_id = ? AND case_id = ? LIMIT 1",
            (learner_id, canonical_id),
        ).fetchone()
    return row is not None


def _validate_guided_context(
    token: str | None,
    *,
    learner_id: str,
    case_reference: str,
) -> dict[str, Any]:
    if not is_ecg_capability(token) or not is_ecg_capability(case_reference):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "guided_grading_context_required",
                "message": "Immediate trace grading is available only inside a server-selected Guided lesson.",
            },
        )
    for row in _guided_exposure_rows(learner_id, recent_only=True):
        session_id = str(row["session_id"])
        canonical_id = str(row["ecg_id"])
        if not session_id.startswith(_GUIDED_SESSION_PREFIX):
            continue
        case_matches = matches_ecg_capability(
            case_reference,
            settings.registration_rate_limit_secret,
            learner_id,
            "guided",
            session_id,
            canonical_id,
        )
        context_matches = matches_ecg_capability(
            token,
            settings.registration_rate_limit_secret,
            learner_id,
            _GUIDED_CONTEXT_VERSION,
            session_id,
            canonical_id,
        )
        if case_matches and context_matches:
            _guard_pending_assessment_case(canonical_id)
            return {
                "version": _GUIDED_CONTEXT_VERSION,
                "lessonId": session_id.removeprefix(_GUIDED_SESSION_PREFIX),
                "caseId": canonical_id,
            }
    raise HTTPException(status_code=403, detail="Invalid or expired Guided grading context")


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
    response.headers["Cache-Control"] = "no-store"
    production = settings.app_env.lower() in {"production", "prod"}
    active_name = session_cookie_name(settings.app_env)
    if production:
        # A host-only cookie and the legacy cookie may otherwise coexist with
        # different values. Always retire the legacy name before adopting the
        # production credential.
        response.delete_cookie(
            key=LEGACY_SESSION_COOKIE_NAME,
            httponly=True,
            secure=True,
            samesite="lax",
            path="/",
        )
    response.set_cookie(
        key=active_name,
        value=token,
        max_age=SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=production,
        samesite="lax",
        path="/",
    )


def _accept_new_session(
    response: Response,
    session: dict[str, Any],
    *,
    authorization: str | None,
    session_cookie: str | None,
) -> None:
    """Adopt one newly proved session and retire stale browser credentials."""

    token = str(session["token"])
    old_bearer = bearer_token(authorization)
    if old_bearer and old_bearer != token:
        auth_service.logout(old_bearer)
    if session_cookie and session_cookie != token:
        auth_service.logout(session_cookie)
    _set_session_cookie(response, token)
    if session.get("guestClaim"):
        clear_guest_cookie(response, app_env=settings.app_env)


def _clear_session_cookie(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    production = settings.app_env.lower() in {"production", "prod"}
    names = {session_cookie_name(settings.app_env), LEGACY_SESSION_COOKIE_NAME}
    for name in names:
        response.delete_cookie(
            key=name,
            httponly=True,
            secure=production,
            samesite="lax",
            path="/",
        )


def _migration_cookie_header(
    name: str, value: str, *, max_age: int
) -> bytes:
    cookie = SimpleCookie()
    cookie[name] = value
    morsel = cookie[name]
    morsel["path"] = "/"
    morsel["max-age"] = str(max_age)
    morsel["httponly"] = True
    morsel["secure"] = True
    morsel["samesite"] = "Lax"
    if max_age == 0:
        morsel["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
    return morsel.OutputString().encode("latin-1")


class SessionCookieMigrationMiddleware:
    """One-way production migration from ``ecg_session`` to ``__Host-``.

    The legacy token is accepted only when no host-prefixed cookie exists and
    the server-side session resolver still recognizes it. The current request
    receives that credential under the active name; the response installs the
    secure host-only cookie and expires the legacy name. When both names exist,
    the host cookie wins and the legacy cookie is only removed.
    """

    def __init__(self, app: Any, *, app_env: str, resolver: Any) -> None:
        self.app = app
        self.production = str(app_env or "").casefold() in {"production", "prod"}
        self.resolver = resolver

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if not self.production or scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = list(scope.get("headers") or [])
        raw_cookie = b"; ".join(
            value for name, value in headers if name.lower() == b"cookie"
        )
        parsed = SimpleCookie()
        try:
            parsed.load(raw_cookie.decode("latin-1"))
        except CookieError:
            parsed = SimpleCookie()
        host_morsel = parsed.get(PRODUCTION_SESSION_COOKIE_NAME)
        legacy_morsel = parsed.get(LEGACY_SESSION_COOKIE_NAME)
        host_token = host_morsel.value if host_morsel else None
        legacy_token = legacy_morsel.value if legacy_morsel else None
        migrate = bool(
            legacy_token
            and host_morsel is None
            and self.resolver(str(legacy_token)) is not None
        )
        # FastAPI dependencies intentionally keep one environment-neutral
        # internal alias. In production, translate the host-prefixed browser
        # credential to that alias only inside the ASGI scope. A conflicting
        # legacy browser cookie is removed first, so the host cookie always
        # wins and no route can accidentally authenticate the stale value.
        downstream_token = host_token or (legacy_token if migrate else None)
        if downstream_token:
            filtered = [
                (name, value) for name, value in headers if name.lower() != b"cookie"
            ]
            downstream_pairs = [
                f"{name}={morsel.coded_value}"
                for name, morsel in parsed.items()
                if name != LEGACY_SESSION_COOKIE_NAME
            ]
            if migrate and not host_token:
                downstream_pairs.append(
                    f"{PRODUCTION_SESSION_COOKIE_NAME}={SimpleCookie().value_encode(str(downstream_token))[1]}"
                )
            downstream_pairs.append(
                f"{LEGACY_SESSION_COOKIE_NAME}={SimpleCookie().value_encode(str(downstream_token))[1]}"
            )
            filtered.append(
                (b"cookie", "; ".join(downstream_pairs).encode("latin-1"))
            )
            scope = dict(scope)
            scope["headers"] = filtered

        async def send_with_migration(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.start" and legacy_token:
                response_headers = list(message.get("headers") or [])
                active_cookie_prefix = (
                    f"{PRODUCTION_SESSION_COOKIE_NAME}=".encode("latin-1")
                )
                active_cookie_already_set = any(
                    name.lower() == b"set-cookie"
                    and value.lstrip().startswith(active_cookie_prefix)
                    for name, value in response_headers
                )
                response_headers.append(
                    (
                        b"set-cookie",
                        _migration_cookie_header(
                            LEGACY_SESSION_COOKIE_NAME, "", max_age=0
                        ),
                    )
                )
                if migrate and not active_cookie_already_set:
                    response_headers.append(
                        (
                            b"set-cookie",
                            _migration_cookie_header(
                                PRODUCTION_SESSION_COOKIE_NAME,
                                str(legacy_token),
                                max_age=SESSION_DAYS * 24 * 60 * 60,
                            ),
                        )
                    )
                message = dict(message)
                message["headers"] = response_headers
            await send(message)

        await self.app(scope, receive, send_with_migration)


def _set_export_auth_cookie(response: Response, token: str) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        key=EXPORT_AUTH_COOKIE_NAME,
        value=token,
        max_age=EXPORT_AUTHORIZATION_SECONDS,
        httponly=True,
        secure=settings.app_env.lower() in {"production", "prod"},
        samesite="strict",
        path="/",
    )


def _clear_export_auth_cookie(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.delete_cookie(
        key=EXPORT_AUTH_COOKIE_NAME,
        httponly=True,
        secure=settings.app_env.lower() in {"production", "prod"},
        samesite="strict",
        path="/",
    )

app = FastAPI(
    title="ECG AI Learning Platform",
    version="1.0.0",
    description="Educational ECG learning platform with confidence-gated autonomous curation.",
    docs_url=None if settings.app_env.strip().lower() in {"production", "prod"} else "/docs",
    redoc_url=None if settings.app_env.strip().lower() in {"production", "prod"} else "/redoc",
    openapi_url=None if settings.app_env.strip().lower() in {"production", "prod"} else "/openapi.json",
)
app.add_exception_handler(RequestValidationError, privacy_safe_validation_error)


async def _account_unavailable_error(
    _request: Request,
    _error: AccountGenerationRetiredError | OwnerParentMissingError,
) -> JSONResponse:
    """Return one neutral result for a request that outlived its account."""

    return JSONResponse(
        status_code=409,
        content={
            "detail": {
                "code": "account_unavailable",
                "message": (
                    "This account is no longer available. Sign in again or "
                    "create a new account."
                ),
            }
        },
        headers={"Cache-Control": "no-store"},
    )


app.add_exception_handler(AccountGenerationRetiredError, _account_unavailable_error)
app.add_exception_handler(OwnerParentMissingError, _account_unavailable_error)

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
app.add_middleware(
    SessionCookieMigrationMiddleware,
    app_env=settings.app_env,
    resolver=auth_service.resolve,
)


class LearnerProfileUpdate(BaseModel):
    displayName: str = Field(min_length=1, max_length=80)

    @field_validator("displayName")
    @classmethod
    def meaningful_display_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Display name must contain a visible character")
        return cleaned


class LearningPreferencesUpdate(BaseModel):
    trainingStage: Literal[
        "not_set", "preclinical", "core_clerkship", "advanced_clerkship", "resident_review"
    ] | None = None
    primaryGoal: Literal[
        "build_fundamentals", "exam_prep", "clinical_reading",
        "emergency_prioritization", "medication_safety",
    ] | None = None
    defaultSessionLength: Literal[5, 10, 25, 50] | None = None
    rapidPace: Literal["untimed", "ward", "emergency"] | None = None
    guidanceLevel: Literal["step_by_step", "balanced", "minimal"] | None = None
    reduceMotion: bool | None = Field(default=None, strict=True)
    largeControls: bool | None = Field(default=None, strict=True)


class CalendarRequestModel(BaseModel):
    model_config = {"extra": "forbid"}


class CalendarSettingsUpdate(CalendarRequestModel):
    timeZone: str = Field(min_length=1, max_length=64)
    weekStartsOn: Literal[0, 1] = 0

    @field_validator("timeZone")
    @classmethod
    def valid_time_zone(cls, value: str) -> str:
        return validate_time_zone(value)


class CalendarItemCreate(CalendarRequestModel):
    title: str = Field(min_length=1, max_length=120)
    notes: str = Field(default="", max_length=1000)
    scheduledDate: str = Field(min_length=10, max_length=10)
    startMinute: int | None = Field(default=None, ge=0, le=1439)
    durationMinutes: int | None = Field(default=None, ge=5, le=240)
    mode: Literal["guided", "train", "rapid", "clinical"] | None = None
    clientRequestId: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )

    @field_validator("title")
    @classmethod
    def meaningful_title(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("title must contain a visible character")
        return cleaned

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, value: str) -> str:
        return value.strip()

    @field_validator("scheduledDate")
    @classmethod
    def valid_scheduled_date(cls, value: str) -> str:
        return validate_calendar_date(value)


class CalendarCompetencyItemCreate(CalendarRequestModel):
    objectiveId: str = Field(min_length=1, max_length=120)
    subskill: str = Field(min_length=1, max_length=80)
    expectedNextDueAt: str = Field(min_length=1, max_length=64)
    scheduledDate: str = Field(min_length=10, max_length=10)
    startMinute: int | None = Field(default=None, ge=0, le=1439)
    durationMinutes: int | None = Field(default=None, ge=5, le=240)
    notes: str = Field(default="", max_length=1000)
    clientRequestId: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )

    @field_validator("objectiveId", "subskill", "expectedNextDueAt", "clientRequestId")
    @classmethod
    def clean_required_value(cls, value: str) -> str:
        return value.strip()

    @field_validator("notes")
    @classmethod
    def clean_competency_notes(cls, value: str) -> str:
        return value.strip()

    @field_validator("scheduledDate")
    @classmethod
    def valid_competency_date(cls, value: str) -> str:
        return validate_calendar_date(value)

    @field_validator("expectedNextDueAt")
    @classmethod
    def valid_due_instant(cls, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("expectedNextDueAt must be an ISO-8601 instant") from exc
        if parsed.tzinfo is None:
            raise ValueError("expectedNextDueAt must include a time zone")
        return value


class CalendarPlanItemCreate(CalendarRequestModel):
    expectedActionKey: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    scheduledDate: str = Field(min_length=10, max_length=10)
    startMinute: int | None = Field(default=None, ge=0, le=1439)
    durationMinutes: int | None = Field(default=30, ge=5, le=240)
    notes: str = Field(default="", max_length=1000)
    clientRequestId: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )

    @field_validator("scheduledDate")
    @classmethod
    def valid_plan_date(cls, value: str) -> str:
        return validate_calendar_date(value)

    @field_validator("notes")
    @classmethod
    def clean_plan_notes(cls, value: str) -> str:
        return value.strip()


class CalendarItemUpdate(CalendarRequestModel):
    revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=1000)
    scheduledDate: str | None = Field(default=None, min_length=10, max_length=10)
    startMinute: int | None = Field(default=None, ge=0, le=1439)
    durationMinutes: int | None = Field(default=None, ge=5, le=240)

    @field_validator("title")
    @classmethod
    def meaningful_optional_title(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("title cannot be null")
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("title must contain a visible character")
        return cleaned

    @field_validator("notes")
    @classmethod
    def clean_optional_notes(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("notes cannot be null")
        return value.strip()

    @field_validator("scheduledDate")
    @classmethod
    def valid_optional_date(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("scheduledDate cannot be null")
        return validate_calendar_date(value)


class CalendarCompletionUpdate(CalendarRequestModel):
    revision: int = Field(ge=1)


class ClickGradeRequest(BaseModel):
    lead: str
    timeSec: float
    amplitudeMv: float
    concept: str | None = None
    guidedContext: str | None = Field(default=None, max_length=2048)


class RegionGradeRequest(BaseModel):
    lead: str
    timeStartSec: float
    timeEndSec: float
    ampMinMv: float
    ampMaxMv: float
    concept: str | None = None
    guidedContext: str | None = Field(default=None, max_length=2048)


class GuidedMeasurementGradeRequest(BaseModel):
    measurementKey: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9_:-]+$",
    )
    value: float = Field(ge=-10_000, le=10_000)
    tolerance: float = Field(gt=0, le=500)
    derive: Literal["rr_from_heart_rate"] | None = None
    guidedContext: str | None = Field(default=None, max_length=240)

    @field_validator("value", "tolerance")
    @classmethod
    def finite_measurement(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("measurement values must be finite")
        return value


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
def dataset_status(
    _learner: str = Depends(require_learning_account),
) -> dict[str, Any]:
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
    username: str | None = Field(default=None, max_length=64)
    identifier: str | None = Field(default=None, max_length=254)
    password: str = Field(max_length=256)
    email: str | None = Field(default=None, max_length=254)
    displayName: str | None = Field(default=None, max_length=80)
    claimGuestProgress: bool = False


class ChallengeProofRequest(BaseModel):
    challengeId: str = Field(min_length=12, max_length=128)
    token: str = Field(min_length=1, max_length=256)


class EmailVerificationConfirmRequest(ChallengeProofRequest):
    password: str = Field(max_length=256)


class ChallengeResendRequest(BaseModel):
    challengeId: str = Field(min_length=12, max_length=128)


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=1, max_length=254)


class PasswordResetConfirmRequest(ChallengeProofRequest):
    newPassword: str = Field(max_length=256)
    # Used only when the proof recovers a never-verified registration. Omitting
    # these remains safe: the backend replaces attacker-controlled identity
    # text with a neutral unique username and display name.
    recoveryUsername: str | None = Field(default=None, max_length=64)
    recoveryDisplayName: str | None = Field(default=None, max_length=80)


class EmailOtpRequest(BaseModel):
    challengeId: str = Field(min_length=12, max_length=128)
    code: str = Field(min_length=6, max_length=6, pattern=r"^[0-9]{6}$")


class EmailUpgradeRequest(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    currentPassword: str = Field(max_length=256)


class UnverifiedEmailReplaceRequest(BaseModel):
    currentPassword: str = Field(max_length=256)
    newEmail: str = Field(min_length=1, max_length=254)
    challengeId: str | None = Field(default=None, min_length=12, max_length=128)


class UnverifiedEmailCancelRequest(BaseModel):
    currentPassword: str = Field(max_length=256)
    challengeId: str | None = Field(default=None, min_length=12, max_length=128)


class DisableTwoFactorRequest(BaseModel):
    currentPassword: str = Field(max_length=256)


class ChangePasswordRequest(BaseModel):
    currentPassword: str = Field(max_length=256)
    newPassword: str = Field(max_length=256)


class ExportAuthorizationRequest(BaseModel):
    currentPassword: str = Field(max_length=256)


class DeleteAccountRequest(BaseModel):
    currentPassword: str = Field(max_length=256)
    confirmation: str = Field(max_length=64)


def _claimable_legacy_guest_or_400(requested: bool) -> str | None:
    """Preflight the one-time migration without consulting account credentials."""

    if not requested:
        return None
    guest_id = current_claimable_guest_learner()
    summary = guest_progress_service.summary(guest_id) if guest_id else None
    if not guest_id or not summary or not summary.get("claimable"):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "guest_claim_unavailable",
                "message": "No claimable legacy guest progress is available for this browser.",
            },
        )
    return guest_id


def _auth_feature_error(exc: AuthError) -> HTTPException:
    if exc.code == "email_delivery_unavailable":
        return HTTPException(
            status_code=503,
            detail={"code": exc.code, "message": str(exc)},
            headers={"Cache-Control": "no-store"},
        )
    if exc.code in {
        "resend_cooldown",
        "resend_limit",
        "recovery_throttled",
        "recovery_confirm_throttled",
        "reauth_throttled",
    }:
        retry = (
            EMAIL_RESEND_COOLDOWN_SECONDS
            if exc.code == "resend_cooldown"
            else ACCOUNT_REAUTH_BLOCK_MINUTES * 60
            if exc.code == "reauth_throttled"
            else RECOVERY_CONFIRM_BLOCK_MINUTES * 60
            if exc.code == "recovery_confirm_throttled"
            else RECOVERY_BLOCK_MINUTES * 60
        )
        return HTTPException(
            status_code=429,
            detail={"code": exc.code, "message": str(exc)},
            headers={"Retry-After": str(retry), "Cache-Control": "no-store"},
        )
    return HTTPException(
        status_code=400,
        detail={"field": exc.field, "code": exc.code, "message": str(exc)},
        headers={"Cache-Control": "no-store"},
    )


@app.get("/auth/capabilities")
def auth_capabilities(response: Response) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    delivery = auth_service.email_delivery_status()
    return {
        "verifiedEmailRequired": True,
        "emailTwoFactorAvailable": bool(delivery["ready"] and settings.app_env == "test"),
        "passwordRecoveryAvailable": bool(delivery["ready"]),
    }


@app.post("/auth/register")
def auth_register(
    request: AuthRequest,
    response: Response,
    http_request: Request,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    guest_id = _claimable_legacy_guest_or_400(request.claimGuestProgress)
    try:
        if request.email:
            session = auth_service.register_with_email(
                request.username,
                request.password,
                request.email,
                request.displayName,
                claim_guest_progress=request.claimGuestProgress,
                guest_id=guest_id,
                client_ip=trusted_registration_ip(http_request),
            )
        elif settings.app_env == "test":
            # Internal test fixtures created before verified email remain
            # deterministic. Deployed registrations never enter this branch.
            session = auth_service.register(
                request.username,
                request.password,
                request.displayName,
                claim_guest_progress=request.claimGuestProgress,
                guest_id=guest_id,
                client_ip=trusted_registration_ip(http_request),
            )
        else:
            raise AuthError(
                "Email is required to create an account.",
                field="email",
                code="email_required",
            )
        if session.get("verificationRequired"):
            response.headers["Cache-Control"] = "no-store"
            return session
        # Registration can be reached while another account is signed in. The
        # new cookie must replace—not merely hide—the prior browser session,
        # matching the account-switch behavior of login.
        old_bearer = bearer_token(authorization)
        if old_bearer and old_bearer != session["token"]:
            auth_service.logout(old_bearer)
        if session_cookie and session_cookie != session["token"]:
            auth_service.logout(session_cookie)
        _set_session_cookie(response, session["token"])
        if session.get("guestClaim"):
            clear_guest_cookie(response, app_env=settings.app_env)
        return {"user": session["user"], "guestClaim": session.get("guestClaim")}
    except GuestProgressClaimConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "guest_progress_already_claimed", "message": str(exc)},
        )
    except GuestProgressClaimUnavailable as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "guest_claim_unavailable", "message": str(exc)},
        )
    except AuthError as exc:
        if exc.code == "email_delivery_unavailable":
            raise HTTPException(
                status_code=503,
                detail={"code": exc.code, "message": str(exc)},
            )
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
    guest_id = _claimable_legacy_guest_or_400(request.claimGuestProgress)
    try:
        session = auth_service.login(
            request.identifier if request.identifier is not None else request.username or "",
            request.password,
            claim_guest_progress=request.claimGuestProgress,
            guest_id=guest_id,
            # Only the origin-key middleware may bless Vercel's private client
            # IP header; direct callers are bucketed by their socket peer.
            client_ip=trusted_registration_ip(http_request),
        )
        if session.get("verificationRequired") or (
            settings.app_env == "test" and session.get("twoFactorRequired")
        ):
            response.headers["Cache-Control"] = "no-store"
            return session
        old_bearer = bearer_token(authorization)
        if old_bearer and old_bearer != session["token"]:
            auth_service.logout(old_bearer)
        if session_cookie and session_cookie != session["token"]:
            auth_service.logout(session_cookie)
        _set_session_cookie(response, session["token"])
        if session.get("guestClaim"):
            clear_guest_cookie(response, app_env=settings.app_env)
        return {"user": session["user"], "guestClaim": session.get("guestClaim")}
    except GuestProgressClaimConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "guest_progress_already_claimed", "message": str(exc)},
        )
    except GuestProgressClaimUnavailable as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "guest_claim_unavailable", "message": str(exc)},
        )
    except AuthError as exc:
        if exc.code == "email_delivery_unavailable":
            raise HTTPException(
                status_code=503,
                detail={"code": exc.code, "message": str(exc)},
            )
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


@app.post("/auth/email/verify/confirm")
def auth_confirm_email(
    request: EmailVerificationConfirmRequest,
    response: Response,
    http_request: Request,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    try:
        session = auth_service.confirm_email_verification(
            request.challengeId,
            request.token,
            request.password,
            client_ip=trusted_registration_ip(http_request),
        )
        if session.get("accountResolutionRequired"):
            response.headers["Cache-Control"] = "no-store"
            return session
        _accept_new_session(
            response,
            session,
            authorization=authorization,
            session_cookie=session_cookie,
        )
        return {
            "user": auth_service.public_user(str(session["user"]["userId"])),
            "accountStatus": "verified",
            "guestClaim": session.get("guestClaim"),
        }
    except GuestProgressClaimConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "guest_progress_already_claimed", "message": str(exc)},
        )
    except GuestProgressClaimUnavailable as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "guest_claim_unavailable", "message": str(exc)},
        )
    except AuthError as exc:
        raise _auth_feature_error(exc)


@app.post("/auth/email/verify/resend")
def auth_resend_email_verification(
    request: ChallengeResendRequest, response: Response
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    try:
        return auth_service.resend_registration_email(request.challengeId)
    except AuthError as exc:
        raise _auth_feature_error(exc)


@app.post("/auth/password-reset/request")
def auth_request_password_reset(
    request: PasswordResetRequest,
    response: Response,
    http_request: Request,
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    try:
        return auth_service.request_password_reset(
            request.email, client_ip=trusted_registration_ip(http_request)
        )
    except AuthError as exc:
        raise _auth_feature_error(exc)


@app.post("/auth/password-reset/confirm")
def auth_confirm_password_reset(
    request: PasswordResetConfirmRequest,
    response: Response,
    http_request: Request,
) -> dict[str, Any]:
    try:
        result = auth_service.confirm_password_reset(
            request.challengeId,
            request.token,
            request.newPassword,
            recovery_username=request.recoveryUsername,
            recovery_display_name=request.recoveryDisplayName,
            client_ip=trusted_registration_ip(http_request),
        )
        _clear_session_cookie(response)
        _clear_export_auth_cookie(response)
        return result
    except AuthError as exc:
        raise _auth_feature_error(exc)


def auth_verify_email_two_factor(
    request: EmailOtpRequest,
    response: Response,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    try:
        session = auth_service.verify_email_two_factor(
            request.challengeId, request.code
        )
        _accept_new_session(
            response,
            session,
            authorization=authorization,
            session_cookie=session_cookie,
        )
        return {
            "user": auth_service.public_user(str(session["user"]["userId"])),
            "twoFactorRequired": False,
            "guestClaim": session.get("guestClaim"),
        }
    except (GuestProgressClaimConflict, GuestProgressClaimUnavailable) as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "guest_claim_unavailable", "message": str(exc)},
        )
    except AuthError as exc:
        raise _auth_feature_error(exc)


def auth_resend_email_two_factor(
    request: ChallengeResendRequest, response: Response
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    try:
        return auth_service.resend_email_challenge(
            request.challengeId, purpose="two_factor_login"
        )
    except AuthError as exc:
        raise _auth_feature_error(exc)


def auth_request_email_two_factor_enable(
    request: DisableTwoFactorRequest,
    response: Response,
    http_request: Request,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    user_id = session_user(authorization, session_cookie)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    response.headers["Cache-Control"] = "no-store"
    try:
        return auth_service.request_email_two_factor_enable(
            user_id,
            request.currentPassword,
            client_ip=trusted_registration_ip(http_request),
        )
    except AuthError as exc:
        raise _auth_feature_error(exc)


def auth_confirm_email_two_factor_enable(
    request: EmailOtpRequest,
    response: Response,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    user_id = session_user(authorization, session_cookie)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    current_token = (
        bearer_token(authorization) if authorization is not None else session_cookie
    )
    if not current_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    response.headers["Cache-Control"] = "no-store"
    try:
        result = auth_service.confirm_email_two_factor_enable(
            user_id, request.challengeId, request.code, current_token
        )
        replacement_token = str(result.pop("_sessionToken"))
        _set_session_cookie(response, replacement_token)
        _clear_export_auth_cookie(response)
        return result
    except AuthError as exc:
        raise _auth_feature_error(exc)


def auth_resend_email_two_factor_enable(
    request: ChallengeResendRequest,
    response: Response,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    user_id = session_user(authorization, session_cookie)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    response.headers["Cache-Control"] = "no-store"
    try:
        return auth_service.resend_email_challenge(
            request.challengeId, purpose="two_factor_enable", user_id=user_id
        )
    except AuthError as exc:
        raise _auth_feature_error(exc)


def auth_request_email_two_factor_disable(
    request: DisableTwoFactorRequest,
    response: Response,
    http_request: Request,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    user_id = session_user(authorization, session_cookie)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    response.headers["Cache-Control"] = "no-store"
    try:
        return auth_service.request_email_two_factor_disable(
            user_id,
            request.currentPassword,
            client_ip=trusted_registration_ip(http_request),
        )
    except AuthError as exc:
        raise _auth_feature_error(exc)


def auth_confirm_email_two_factor_disable(
    request: EmailOtpRequest,
    response: Response,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    user_id = session_user(authorization, session_cookie)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    current_token = (
        bearer_token(authorization) if authorization is not None else session_cookie
    )
    if not current_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    response.headers["Cache-Control"] = "no-store"
    try:
        result = auth_service.confirm_email_two_factor_disable(
            user_id, request.challengeId, request.code, current_token
        )
        replacement_token = str(result.pop("_sessionToken"))
        _set_session_cookie(response, replacement_token)
        _clear_export_auth_cookie(response)
        return result
    except AuthError as exc:
        raise _auth_feature_error(exc)


def auth_resend_email_two_factor_disable(
    request: ChallengeResendRequest,
    response: Response,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    user_id = session_user(authorization, session_cookie)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    response.headers["Cache-Control"] = "no-store"
    try:
        return auth_service.resend_email_challenge(
            request.challengeId, purpose="two_factor_disable", user_id=user_id
        )
    except AuthError as exc:
        raise _auth_feature_error(exc)


# Keep the retired API contract available only to deterministic legacy tests.
# No non-test deployment publishes these routes in OpenAPI or accepts them.
if settings.app_env == "test":
    app.add_api_route(
        "/auth/2fa/email/verify",
        auth_verify_email_two_factor,
        methods=["POST"],
    )
    app.add_api_route(
        "/auth/2fa/email/resend",
        auth_resend_email_two_factor,
        methods=["POST"],
    )
    app.add_api_route(
        "/auth/2fa/email/enable/request",
        auth_request_email_two_factor_enable,
        methods=["POST"],
    )
    app.add_api_route(
        "/auth/2fa/email/enable/confirm",
        auth_confirm_email_two_factor_enable,
        methods=["POST"],
    )
    app.add_api_route(
        "/auth/2fa/email/enable/resend",
        auth_resend_email_two_factor_enable,
        methods=["POST"],
    )
    app.add_api_route(
        "/auth/2fa/email/disable/request",
        auth_request_email_two_factor_disable,
        methods=["POST"],
    )
    app.add_api_route(
        "/auth/2fa/email/disable/confirm",
        auth_confirm_email_two_factor_disable,
        methods=["POST"],
    )
    app.add_api_route(
        "/auth/2fa/email/disable/resend",
        auth_resend_email_two_factor_disable,
        methods=["POST"],
    )


@app.post("/auth/email/upgrade/request")
def auth_request_legacy_email_upgrade(
    request: EmailUpgradeRequest,
    response: Response,
    http_request: Request,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    user_id = session_user(authorization, session_cookie)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    response.headers["Cache-Control"] = "no-store"
    try:
        return auth_service.request_legacy_email_upgrade(
            user_id,
            request.email,
            request.currentPassword,
            client_ip=trusted_registration_ip(http_request),
        )
    except AuthError as exc:
        raise _auth_feature_error(exc)


@app.post("/auth/email/change/request")
def auth_request_email_change(
    request: EmailUpgradeRequest,
    response: Response,
    http_request: Request,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    user_id = session_user(authorization, session_cookie)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    response.headers["Cache-Control"] = "no-store"
    try:
        return auth_service.request_email_change(
            user_id,
            request.email,
            request.currentPassword,
            client_ip=trusted_registration_ip(http_request),
        )
    except AuthError as exc:
        raise _auth_feature_error(exc)


@app.post("/auth/email/change/current-factor/confirm")
def auth_confirm_email_change_current_factor(
    request: EmailOtpRequest,
    response: Response,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    user_id = session_user(authorization, session_cookie)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    current_token = (
        bearer_token(authorization) if authorization is not None else session_cookie
    )
    if not current_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    response.headers["Cache-Control"] = "no-store"
    try:
        return auth_service.confirm_email_change_current_factor(
            user_id, request.challengeId, request.code, current_token
        )
    except AuthError as exc:
        raise _auth_feature_error(exc)


@app.post("/auth/email/change/current-factor/resend")
def auth_resend_email_change_current_factor(
    request: ChallengeResendRequest,
    response: Response,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    user_id = session_user(authorization, session_cookie)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    response.headers["Cache-Control"] = "no-store"
    try:
        return auth_service.resend_email_challenge(
            request.challengeId,
            purpose="email_change_current_factor",
            user_id=user_id,
        )
    except AuthError as exc:
        raise _auth_feature_error(exc)


@app.post("/auth/email/unverified/replace")
def auth_replace_unverified_email(
    request: UnverifiedEmailReplaceRequest,
    response: Response,
    http_request: Request,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    """Correct setup email with either a session or pending challenge + password."""

    user_id = session_user(authorization, session_cookie)
    response.headers["Cache-Control"] = "no-store"
    try:
        return auth_service.replace_unverified_email(
            user_id=user_id,
            challenge_id=request.challengeId,
            current_password=request.currentPassword,
            new_email=request.newEmail,
            client_ip=trusted_registration_ip(http_request),
        )
    except AuthError as exc:
        raise _auth_feature_error(exc)


@app.post("/auth/email/unverified/cancel")
def auth_cancel_unverified_email(
    request: UnverifiedEmailCancelRequest,
    response: Response,
    http_request: Request,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    """Release a pending registration or detach a legacy setup typo."""

    user_id = session_user(authorization, session_cookie)
    response.headers["Cache-Control"] = "no-store"
    try:
        result = auth_service.cancel_unverified_email(
            user_id=user_id,
            challenge_id=request.challengeId,
            current_password=request.currentPassword,
            client_ip=trusted_registration_ip(http_request),
        )
        if result.get("accountCancelled"):
            _clear_session_cookie(response)
            _clear_export_auth_cookie(response)
        return result
    except AuthError as exc:
        raise _auth_feature_error(exc)


@app.post("/auth/email/change/confirm")
def auth_confirm_email_change(
    request: ChallengeProofRequest,
    response: Response,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    user_id = session_user(authorization, session_cookie)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    current_token = bearer_token(authorization) if authorization is not None else session_cookie
    if not current_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    response.headers["Cache-Control"] = "no-store"
    try:
        result = auth_service.confirm_email_change(
            user_id, request.challengeId, request.token, current_token
        )
        replacement_token = str(result.pop("_sessionToken"))
        _set_session_cookie(response, replacement_token)
        _clear_export_auth_cookie(response)
        return result
    except AuthError as exc:
        raise _auth_feature_error(exc)


@app.post("/auth/email/change/resend")
def auth_resend_email_change(
    request: ChallengeResendRequest,
    response: Response,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    user_id = session_user(authorization, session_cookie)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    response.headers["Cache-Control"] = "no-store"
    try:
        return auth_service.resend_email_challenge(
            request.challengeId, purpose="email_change", user_id=user_id
        )
    except AuthError as exc:
        raise _auth_feature_error(exc)


@app.post("/auth/email/change/cancel")
def auth_cancel_email_change(
    request: ChallengeResendRequest,
    response: Response,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, bool]:
    user_id = session_user(authorization, session_cookie)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    response.headers["Cache-Control"] = "no-store"
    return auth_service.cancel_email_change(user_id, request.challengeId)


@app.get("/auth/guest-progress")
def auth_guest_progress(response: Response) -> dict[str, Any]:
    """Preview only pre-existing migration work; never create guest state."""
    response.headers["Cache-Control"] = "no-store"
    guest_id = current_claimable_guest_learner()
    return (
        guest_progress_service.summary(guest_id)
        if guest_id
        else guest_progress_service.empty_summary()
    )


@app.post("/auth/guest-progress/claim")
def auth_claim_legacy_guest_progress(
    response: Response,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    """Attach only the positive legacy record presented by this browser."""

    user_id = session_user(authorization, session_cookie)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    user = auth_service.public_user(user_id)
    if not user or user.get("accountStatus") != "verified":
        raise HTTPException(
            status_code=403,
            detail={
                "code": user.get("accountStatus") if user else "account_unavailable",
                "message": "Verify the account before attaching legacy progress.",
            },
        )
    guest_id = _claimable_legacy_guest_or_400(True)
    assert guest_id is not None
    try:
        claim = guest_progress_service.claim(guest_id, user_id)
    except GuestProgressClaimConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "guest_progress_already_claimed", "message": str(exc)},
        )
    except GuestProgressClaimUnavailable as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "guest_claim_unavailable", "message": str(exc)},
        )
    clear_guest_cookie(response, app_env=settings.app_env)
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True, "guestClaim": claim}


@app.delete("/auth/guest-progress")
def auth_delete_guest_progress(
    response: Response,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    """Erase only the guest namespace presented by this browser.

    The deployed Next.js proxy rejects cross-site mutations before forwarding
    this request, and the backend origin-key middleware rejects direct calls.
    """

    # A signed-in learner may explicitly discard this browser's separate legacy
    # record. The presented account is never part of the deletion graph.
    session_user(authorization, session_cookie)
    guest_id = current_claimable_guest_learner()
    if not guest_id:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "guest_identity_required",
                "message": "Refresh once before deleting this browser's guest record.",
            },
        )
    deleted_records = guest_progress_service.delete(guest_id)
    clear_guest_cookie(response, app_env=settings.app_env)
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True, "deletedRecords": deleted_records}


@app.post("/auth/logout")
def auth_logout(
    response: Response,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    auth_service.logout(bearer_token(authorization))
    auth_service.logout(session_cookie)
    _clear_session_cookie(response)
    _clear_export_auth_cookie(response)
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
    _clear_export_auth_cookie(response)
    return {"ok": True, "revokedSessions": revoked}


@app.post("/auth/logout-others")
def auth_logout_others(
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    user_id = session_user(authorization, session_cookie)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    current_token = bearer_token(authorization) if authorization is not None else session_cookie
    if not current_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    revoked = auth_service.logout_others(user_id, current_token)
    return {"ok": True, "revokedOtherSessions": revoked}


@app.get("/auth/sessions")
def auth_sessions(
    response: Response,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    user_id = session_user(authorization, session_cookie)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    current_token = bearer_token(authorization) if authorization is not None else session_cookie
    if not current_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    response.headers["Cache-Control"] = "no-store"
    return {"sessions": auth_service.sessions(user_id, current_token)}


@app.delete("/auth/sessions/{session_id}")
def auth_revoke_session(
    session_id: str = ApiPath(
        min_length=68,
        max_length=68,
        pattern=r"^ses_[0-9a-f]{64}$",
    ),
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    user_id = session_user(authorization, session_cookie)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    current_token = bearer_token(authorization) if authorization is not None else session_cookie
    if not current_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        auth_service.revoke_session(user_id, current_token, session_id)
    except AuthError as exc:
        raise HTTPException(
            status_code=409 if exc.code == "current_session" else 404,
            detail={"code": exc.code, "message": str(exc)},
        )
    return {"ok": True, "revokedSessionId": session_id}


@app.post("/auth/change-password")
def auth_change_password(
    request: ChangePasswordRequest,
    response: Response,
    http_request: Request,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    user_id = session_user(authorization, session_cookie)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        session = auth_service.change_password(
            user_id,
            request.currentPassword,
            request.newPassword,
            client_ip=trusted_registration_ip(http_request),
        )
    except AuthError as exc:
        raise HTTPException(
            status_code=429 if exc.code == "reauth_throttled" else 400,
            detail={"field": exc.field, "code": exc.code, "message": str(exc)},
            headers=(
                {"Retry-After": str(ACCOUNT_REAUTH_BLOCK_MINUTES * 60)}
                if exc.code == "reauth_throttled"
                else None
            ),
        )
    _set_session_cookie(response, session["token"])
    _clear_export_auth_cookie(response)
    return {"user": session["user"], "revokedOtherSessions": True}


@app.post("/auth/export/authorize")
def auth_authorize_export(
    request: ExportAuthorizationRequest,
    response: Response,
    http_request: Request,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    user_id = session_user(authorization, session_cookie)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    current_token = bearer_token(authorization) if authorization is not None else session_cookie
    if not current_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        grant = auth_service.authorize_export(
            user_id,
            current_token,
            request.currentPassword,
            client_ip=trusted_registration_ip(http_request),
        )
    except AuthError as exc:
        raise HTTPException(
            status_code=429 if exc.code == "reauth_throttled" else 400,
            detail={"field": exc.field, "code": exc.code, "message": str(exc)},
            headers=(
                {"Retry-After": str(ACCOUNT_REAUTH_BLOCK_MINUTES * 60)}
                if exc.code == "reauth_throttled"
                else None
            ),
        )
    _set_export_auth_cookie(response, grant["token"])
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True, "expiresAt": grant["expiresAt"]}


@app.post("/auth/export")
def auth_export_progress(
    response: Response,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    export_authorization: str | None = Cookie(
        default=None, alias=EXPORT_AUTH_COOKIE_NAME
    ),
) -> dict[str, Any]:
    user_id = session_user(authorization, session_cookie)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    current_token = bearer_token(authorization) if authorization is not None else session_cookie
    if not current_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        exported = auth_service.export_progress(
            user_id, current_token, export_authorization
        )
    except AuthError as exc:
        raise HTTPException(
            status_code=404 if exc.code == "account_unavailable" else 403,
            detail={"code": exc.code, "message": str(exc)},
        )
    _clear_export_auth_cookie(response)
    username = str(exported["account"]["username"])
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Disposition"] = (
        f'attachment; filename="ecg-progress-{username}.json"'
    )
    return exported


@app.delete("/auth/account")
def auth_delete_account(
    request: DeleteAccountRequest,
    response: Response,
    http_request: Request,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    user_id = session_user(authorization, session_cookie)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        auth_service.delete_account(
            user_id,
            request.currentPassword,
            request.confirmation,
            client_ip=trusted_registration_ip(http_request),
        )
    except AuthError as exc:
        raise HTTPException(
            status_code=429 if exc.code == "reauth_throttled" else 400,
            detail={"field": exc.field, "code": exc.code, "message": str(exc)},
            headers=(
                {"Retry-After": str(ACCOUNT_REAUTH_BLOCK_MINUTES * 60)}
                if exc.code == "reauth_throttled"
                else None
            ),
        )
    _clear_session_cookie(response)
    _clear_export_auth_cookie(response)
    return {"ok": True}


@app.get("/auth/me")
def auth_me(
    response: Response,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
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


@app.get("/auth/learning-access", status_code=204)
def auth_learning_access(
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> Response:
    """Authorize same-origin static learning assets without exposing identity.

    The Next.js server calls this endpoint before it releases any Foundations
    HTML, script, stylesheet, or PTB teaching data. The response is deliberately
    body-free so it cannot become a second account-hydration API.
    """

    require_present_learning_account(authorization, session_cookie)
    return Response(
        status_code=204,
        headers={
            "Cache-Control": "private, no-store",
            "Pragma": "no-cache",
            "Vary": "Authorization, Cookie",
        },
    )


def _runtime_index_build_enabled(app_env: str) -> bool:
    """Keep offline corpus mutation/refresh routes out of hosted runtimes."""

    return app_env.strip().lower() not in {"production", "prod"}


if _runtime_index_build_enabled(settings.app_env):

    @app.post("/ingest/build-index")
    def build_index(limit: int = Query(default=80, ge=1, le=1000)) -> dict[str, Any]:
        return repo.build_index(limit)


@app.get("/concepts")
def concepts(
    _learner: str = Depends(require_learning_account),
) -> dict[str, Any]:
    return {
        "concepts": [
            {"id": concept.id, "label": concept.label, "group": concept.group, "highYield": concept.high_yield}
            for concept in CONCEPTS
        ],
        "practiceGroups": concept_availability(repo),
    }


_training_pool_receipt_available: Callable[[str, str], bool] | None = None


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
    mode = _receipt_mode(
        definition,
        case_concept,
        subskill,
        training_receipt_available=_training_pool_receipt_available,
    )
    if mode is None:
        return None
    return {
        "mode": mode,
        "caseConcept": case_concept,
        "receiptConcept": definition.id,
        "subskill": subskill,
    }


@app.get("/objectives")
def objective_registry(
    _learner: str = Depends(require_learning_account),
) -> dict[str, Any]:
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
    _learner: str = Depends(require_learning_account),
) -> list[dict[str, Any]]:
    # A blinded row is not sufficient if diagnostic filters remain available:
    # an API-aware learner who knows a pending case id can probe membership in
    # `/cases?concept=...` or `/cases?query=...` and recover the answer one bit
    # at a time. Omitting pending rows alone is not enough because a caller can
    # cache diagnostic counts before starting a round and diff them afterward.
    # Authored mode selectors own diagnostic discovery; this learner catalogue
    # is intentionally unfiltered and answer-blind.
    if concept is not None or query is not None or includeUncertain:
        raise HTTPException(
            status_code=403,
            detail="diagnostic_case_filters_unavailable",
        )
    rows = repo.list_cases(
        concept=None,
        include_uncertain=False,
        query=None,
        limit=limit,
        offset=offset,
    )
    return [
        blind_summary(row)
        for row in rows
        if generic_learner_candidate_policy(row).allowed
    ]


@app.get("/cases/{case_id}")
def get_case(
    case_id: str,
    _learner: str = Depends(require_learning_account),
) -> dict[str, Any]:
    case = _learner_case_or_404(case_id)
    return blind_summary(case_summary(case))


@app.get("/cases/{case_id}/packet")
def get_case_packet(
    case_id: str,
    blinded: bool = True,
    _learner: str = Depends(require_learning_account),
) -> dict[str, Any]:
    # Compatibility-only query flag. Public packets are always blinded; a
    # caller cannot opt into the answer key with `?blinded=false`.
    del blinded
    case = _learner_case_or_404(case_id)
    return blind_packet(packet_for_case(case))


@app.get("/cases/{case_id}/waveform")
def get_waveform(
    case_id: str,
    leads: str | None = None,
    start: float = Query(default=0, ge=0),
    end: float | None = Query(default=None, ge=0),
    maxPoints: int = Query(default=1200, ge=100, le=5000),
    _learner: str = Depends(require_learning_account),
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
def get_ptbxl_plus(
    case_id: str,
    _learner: str = Depends(require_learning_account),
) -> dict[str, Any]:
    case = _learner_case_or_404(case_id)
    return blind_packet(packet_for_case(case))["ptbxl_plus"]


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
    learner = effective_learner(authorization, learner_id, session_cookie)
    account = auth_service.public_user(learner)
    # The account record is the canonical identity source. In particular, a
    # requested URL id can never supply or inherit a prototype profile name.
    canonical_name = None
    if account:
        canonical_name = str(account.get("displayName") or account["username"])
    return store.ensure_profile(learner, canonical_name)


@app.put("/learners/{learner_id}")
def update_profile(
    learner_id: str,
    update: LearnerProfileUpdate,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    return store.ensure_profile(effective_learner(authorization, learner_id, session_cookie), update.displayName)


@app.get("/learning/preferences")
def learning_preferences(
    response: Response,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    learner = effective_learner(authorization, session_cookie=session_cookie)
    return store.get_learning_preferences(learner)


@app.put("/learning/preferences")
def update_learning_preferences(
    update: LearningPreferencesUpdate,
    response: Response,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    learner = effective_learner(authorization, session_cookie=session_cookie)
    return store.update_learning_preferences(
        learner,
        update.model_dump(exclude_none=True),
    )


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
    time_zone: str | None = Header(default=None, alias="X-ECG-Time-Zone"),
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    learner = effective_learner(authorization, learner_id, session_cookie)
    profile = store.ensure_profile(learner)
    observed = {
        (row["concept"], row["subskill"]): row
        for row in profile.get("subskillMastery", [])
    }
    try:
        if time_zone is not None:
            validate_time_zone(time_zone)
        with store.connect() as conn:
            calendar_projection = get_competency_review_projection(
                conn,
                learner,
                observed,
                requested_time_zone=time_zone,
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_time_zone", "message": str(exc)},
        ) from exc
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
        "calendarProjection": calendar_projection,
        "objectives": objectives,
    }


def _calendar_receipt_contracts() -> dict[tuple[str, str], dict[str, str] | None]:
    concept_counts = repo.concept_ab_counts()
    contracts: dict[tuple[str, str], dict[str, str] | None] = {}
    for definition in OBJECTIVES.values():
        runtime = objective_runtime_availability(definition, repo)
        for subskill in definition.allowed_subskills:
            contracts[(definition.id, subskill)] = _independent_receipt_contract(
                definition,
                runtime,
                concept_counts,
                subskill,
            )
    return contracts


def _calendar_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"


def _calendar_mutation_error(exc: Exception) -> HTTPException:
    headers = {"Cache-Control": "no-store, private", "Pragma": "no-cache"}
    if isinstance(exc, CalendarItemNotFoundError):
        return HTTPException(
            status_code=404,
            detail={"code": "calendar_item_not_found", "message": "Calendar item not found"},
            headers=headers,
        )
    if isinstance(exc, CalendarSourceChangedError):
        return HTTPException(
            status_code=409,
            detail={
                "code": "calendar_source_changed",
                "message": str(exc),
                "currentNextDueAt": exc.current_due_at,
            },
            headers=headers,
        )
    if isinstance(exc, CalendarItemConflictError):
        detail: dict[str, Any] = {"code": exc.code, "message": str(exc)}
        if exc.current is not None:
            detail["current"] = exc.current
        return HTTPException(status_code=409, detail=detail, headers=headers)
    return HTTPException(
        status_code=400,
        detail={"code": "calendar_request_invalid", "message": str(exc)},
        headers=headers,
    )


@app.get("/learning/calendar")
def learning_calendar(
    response: Response,
    start_date: str = Query(
        alias="startDate",
        min_length=10,
        max_length=10,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    ),
    end_date: str = Query(
        alias="endDate",
        min_length=10,
        max_length=10,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    ),
    time_zone: str | None = Query(default=None, alias="timeZone", max_length=64),
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    """Return one bounded planner window plus live competency review dates."""

    _calendar_headers(response)
    learner = effective_learner(authorization, session_cookie=session_cookie)
    store.ensure_profile(learner)
    try:
        validate_calendar_range(start_date, end_date)
        if time_zone is not None:
            validate_time_zone(time_zone)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_calendar_range", "message": str(exc)},
        ) from exc
    current_plan = _adaptive_plan_for_learner(learner)
    current_action = current_plan.get("calendarAction")
    current_action_key = (
        str(current_action.get("actionKey"))
        if isinstance(current_action, dict) and current_action.get("actionKey")
        else None
    )
    current_plan_priorities: dict[tuple[str, str], int] = {}
    for index, priority in enumerate(current_plan.get("priorities") or [], start=1):
        if not isinstance(priority, dict):
            continue
        objective_id = priority.get("objectiveId")
        subskill = priority.get("subskill")
        if isinstance(objective_id, str) and isinstance(subskill, str):
            current_plan_priorities.setdefault((objective_id, subskill), index)
    with store.connect() as conn:
        return get_calendar_snapshot(
            conn,
            learner,
            start_date=start_date,
            end_date=end_date,
            requested_time_zone=time_zone,
            receipts=_calendar_receipt_contracts(),
            current_plan_action_key=current_action_key,
            current_plan_priorities=current_plan_priorities,
        )


@app.put("/learning/calendar/settings")
def update_learning_calendar_settings(
    update: CalendarSettingsUpdate,
    response: Response,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    _calendar_headers(response)
    learner = effective_learner(authorization, session_cookie=session_cookie)
    store.ensure_profile(learner)
    with store.connect() as conn:
        return save_calendar_settings(
            conn,
            learner,
            time_zone=update.timeZone,
            week_starts_on=update.weekStartsOn,
            now=datetime.now(UTC).isoformat(),
        )


@app.post("/learning/calendar/items", status_code=201)
def create_learning_calendar_item(
    request: CalendarItemCreate,
    response: Response,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    _calendar_headers(response)
    learner = effective_learner(authorization, session_cookie=session_cookie)
    store.ensure_profile(learner)
    try:
        with store.connect() as conn:
            return create_calendar_item(
                conn,
                learner,
                source="manual",
                title=request.title,
                notes=request.notes,
                scheduled_date=request.scheduledDate,
                start_minute=request.startMinute,
                duration_minutes=request.durationMinutes,
                client_request_id=request.clientRequestId,
                now=datetime.now(UTC).isoformat(),
                target={"mode": request.mode} if request.mode else None,
            )
    except (CalendarItemConflictError, ValueError) as exc:
        raise _calendar_mutation_error(exc) from exc


@app.post("/learning/calendar/items/from-plan", status_code=201)
def create_learning_calendar_plan_item(
    request: CalendarPlanItemCreate,
    response: Response,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    """Schedule the server-owned runnable action the learner explicitly confirmed."""

    _calendar_headers(response)
    learner = effective_learner(authorization, session_cookie=session_cookie)
    store.ensure_profile(learner)
    try:
        plan = _adaptive_plan_for_learner(learner)
        action = plan.get("calendarAction")
        current_action_key = (
            str(action.get("actionKey"))
            if isinstance(action, dict) and action.get("actionKey")
            else None
        )
        with store.connect() as conn:
            replay = replay_calendar_plan_request(
                conn,
                learner,
                client_request_id=request.clientRequestId,
                source_plan_key=request.expectedActionKey,
                scheduled_date=request.scheduledDate,
                start_minute=request.startMinute,
                duration_minutes=request.durationMinutes,
                notes=request.notes,
                current_plan_action_key=current_action_key,
            )
            if replay is not None:
                return replay

        if not isinstance(action, dict):
            raise CalendarItemConflictError(
                "calendar_plan_unavailable",
                "The current study plan has no launchable activity to schedule.",
            )
        if action.get("actionKey") != request.expectedActionKey:
            raise CalendarItemConflictError(
                "calendar_plan_changed",
                "The recommended activity changed before it was scheduled. Review the current plan and confirm again.",
            )
        objective_id = str(action.get("objectiveId") or "")
        subskill = str(action.get("subskill") or "")
        case_concept = str(action.get("caseConcept") or "")
        mode = str(action.get("mode") or "")
        if not all((objective_id, subskill, case_concept)) or mode not in {"train", "rapid"}:
            raise ValueError("The current study-plan action is not an exact runnable ECG skill")
        launch_href = calendarize_plan_launch_href(
            str(action.get("launchHref") or ""),
            mode=mode,
            scheduled_date=request.scheduledDate,
        )
        with store.connect() as conn:
            created = create_calendar_item(
                conn,
                learner,
                source="study_plan",
                title=str(action.get("title") or "Planned ECG practice")[:120],
                notes=request.notes,
                scheduled_date=request.scheduledDate,
                start_minute=request.startMinute,
                duration_minutes=request.durationMinutes,
                client_request_id=request.clientRequestId,
                now=datetime.now(UTC).isoformat(),
                target={
                    "objectiveId": objective_id,
                    "subskill": subskill,
                    "mode": mode,
                    "caseConcept": case_concept,
                },
                target_launch_href=launch_href,
                source_plan_key=request.expectedActionKey,
            )
            return get_calendar_item(
                conn,
                learner,
                created["itemId"],
                receipts=_calendar_receipt_contracts(),
                current_plan_action_key=request.expectedActionKey,
            )
    except (CalendarItemConflictError, ValueError) as exc:
        raise _calendar_mutation_error(exc) from exc


@app.post("/learning/calendar/items/from-competency", status_code=201)
def create_learning_calendar_competency_item(
    request: CalendarCompetencyItemCreate,
    response: Response,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    """Schedule one exact review without changing its retention due instant."""

    _calendar_headers(response)
    learner = effective_learner(authorization, session_cookie=session_cookie)
    store.ensure_profile(learner)
    definition = OBJECTIVES.get(request.objectiveId)
    if definition is None or request.subskill not in definition.allowed_subskills:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "calendar_competency_not_found",
                "message": "Competency not found",
            },
        )
    receipt = _independent_receipt_contract(
        definition,
        objective_runtime_availability(definition, repo),
        repo.concept_ab_counts(),
        request.subskill,
    )
    if receipt is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "calendar_competency_unavailable",
                "message": "No independent real-ECG review route is currently available.",
            },
        )
    try:
        with store.connect() as conn:
            source = get_competency_due_source(
                conn,
                learner,
                request.objectiveId,
                request.subskill,
            )
            current_due_at = source["nextDueAt"] if source is not None else None
            if current_due_at != request.expectedNextDueAt:
                raise CalendarSourceChangedError(current_due_at)
            created = create_calendar_item(
                conn,
                learner,
                source="retention_review",
                title=(
                    f"Review {definition.label}: "
                    f"{request.subskill.replace('_', ' ')}"
                )[:120],
                notes=request.notes,
                scheduled_date=request.scheduledDate,
                start_minute=request.startMinute,
                duration_minutes=request.durationMinutes,
                client_request_id=request.clientRequestId,
                now=datetime.now(UTC).isoformat(),
                target={
                    "objectiveId": request.objectiveId,
                    "subskill": request.subskill,
                    "mode": receipt["mode"],
                    "caseConcept": receipt["caseConcept"],
                },
                source_due_at=request.expectedNextDueAt,
            )
            return get_calendar_item(
                conn,
                learner,
                created["itemId"],
                receipts={(request.objectiveId, request.subskill): receipt},
            )
    except (
        CalendarItemConflictError,
        CalendarSourceChangedError,
        ValueError,
    ) as exc:
        raise _calendar_mutation_error(exc) from exc


@app.patch("/learning/calendar/items/{item_id}")
def edit_learning_calendar_item(
    request: CalendarItemUpdate,
    response: Response,
    item_id: str = ApiPath(min_length=36, max_length=36),
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    _calendar_headers(response)
    learner = effective_learner(authorization, session_cookie=session_cookie)
    changes = request.model_dump(exclude_unset=True, exclude={"revision"})
    try:
        with store.connect() as conn:
            updated = update_calendar_item(
                conn,
                learner,
                item_id,
                revision=request.revision,
                changes=changes,
                now=datetime.now(UTC).isoformat(),
            )
            return get_calendar_item(
                conn,
                learner,
                updated["itemId"],
                receipts=_calendar_receipt_contracts(),
            )
    except (CalendarItemNotFoundError, CalendarItemConflictError, ValueError) as exc:
        raise _calendar_mutation_error(exc) from exc


@app.put("/learning/calendar/items/{item_id}/completion")
def complete_learning_calendar_item(
    request: CalendarCompletionUpdate,
    response: Response,
    item_id: str = ApiPath(min_length=36, max_length=36),
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    return _set_learning_calendar_item_completion(
        completed=True,
        revision=request.revision,
        response=response,
        item_id=item_id,
        authorization=authorization,
        session_cookie=session_cookie,
    )


def _set_learning_calendar_item_completion(
    *,
    completed: bool,
    revision: int,
    response: Response,
    item_id: str,
    authorization: str | None,
    session_cookie: str | None,
) -> dict[str, Any]:
    _calendar_headers(response)
    learner = effective_learner(authorization, session_cookie=session_cookie)
    try:
        with store.connect() as conn:
            updated = set_calendar_item_completion(
                conn,
                learner,
                item_id,
                revision=revision,
                completed=completed,
                now=datetime.now(UTC).isoformat(),
            )
            return get_calendar_item(
                conn,
                learner,
                updated["itemId"],
                receipts=_calendar_receipt_contracts(),
            )
    except (CalendarItemNotFoundError, CalendarItemConflictError) as exc:
        raise _calendar_mutation_error(exc) from exc


@app.delete("/learning/calendar/items/{item_id}/completion")
def reopen_learning_calendar_item(
    response: Response,
    item_id: str = ApiPath(min_length=36, max_length=36),
    revision: int = Query(ge=1),
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    return _set_learning_calendar_item_completion(
        completed=False,
        revision=revision,
        response=response,
        item_id=item_id,
        authorization=authorization,
        session_cookie=session_cookie,
    )


@app.delete("/learning/calendar/items/{item_id}")
def remove_learning_calendar_item(
    response: Response,
    item_id: str = ApiPath(min_length=36, max_length=36),
    revision: int = Query(ge=1),
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    _calendar_headers(response)
    learner = effective_learner(authorization, session_cookie=session_cookie)
    try:
        with store.connect() as conn:
            delete_calendar_item(
                conn,
                learner,
                item_id,
                revision=revision,
            )
    except (CalendarItemNotFoundError, CalendarItemConflictError) as exc:
        raise _calendar_mutation_error(exc) from exc
    return {"deleted": True, "itemId": item_id}


@app.get(
    "/learners/{learner_id}/competencies/{objective_id}/{subskill}/trend"
)
def competency_evidence_trend(
    learner_id: str,
    response: Response,
    objective_id: str = ApiPath(min_length=1, max_length=120),
    subskill: str = ApiPath(min_length=1, max_length=80),
    limit: int = Query(default=20, ge=1, le=MAX_COMPETENCY_TREND_POINTS),
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    """Return scored observations, not reconstructed historical mastery."""

    learner = effective_learner(authorization, learner_id, session_cookie)
    if not validate_objective_subskill(objective_id, subskill):
        raise HTTPException(status_code=404, detail="Competency not found")
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Vary"] = "Authorization, Cookie"
    with store.connect() as conn:
        return get_competency_trend(
            conn,
            learner_id=learner,
            objective_id=objective_id,
            subskill=subskill,
            limit=limit,
        )


def _adaptive_plan_for_learner(learner: str) -> dict[str, Any]:
    """Rebuild the current deterministic plan from durable owner state."""

    profile = store.ensure_profile(learner)
    clinical_concepts = {
        concept
        for item in clinical_item_store.list_for_serving(status="harness_pass")
        for concept in item.application_objectives
    }
    runtime = {
        definition.id: objective_runtime_availability(definition, repo)
        for definition in OBJECTIVES.values()
    }
    plan = build_mastery_plan(
        profile,
        repo.concept_ab_counts(),
        preferences=store.get_learning_preferences(learner),
        runtime_evidence={
            objective_id: availability.evidence_ceiling
            for objective_id, availability in runtime.items()
        },
        runtime_subskills={
            objective_id: set(availability.eligible_subskills)
            for objective_id, availability in runtime.items()
        },
        clinical_concepts=clinical_concepts,
        training_receipt_available=_training_pool_receipt_available,
    )
    return {
        "learnerId": learner,
        **plan,
        "calendarAction": calendar_plan_action(plan),
    }


@app.get("/adaptive/plan")
def adaptive_mastery_plan(
    learnerId: str = "demo",
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    """Return a transparent cross-mode plan plus an owner-bound coach reference.

    The caller-supplied learner id is advisory only; cookie/bearer ownership is
    resolved exactly as it is for the competency registry. The reference proves
    only that this learner opened a server-issued plan; the plan itself is rebuilt
    from durable state on every tutor turn.
    """

    learner = effective_learner(authorization, learnerId, session_cookie)
    return {
        **_adaptive_plan_for_learner(learner),
        "coachContext": issue_adaptive_tutor_context(
            learner,
            ADAPTIVE_PLAN_CONTEXT_SECRET,
        ),
    }


@app.get("/learning/resume")
def learning_resume(
    response: Response,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    """Return the owner's read-only cross-mode continuation snapshot."""

    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    learner = effective_learner(authorization, session_cookie=session_cookie)
    return store.get_learning_resume_snapshot(learner)


@app.get("/learning/activity")
def learning_activity(
    response: Response,
    mode: str = Query(
        default="all",
        pattern=r"^(all|guided|training|rapid|clinical)$",
    ),
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=2048),
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    """Return one safe page of committed learning history for this owner."""

    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    learner = effective_learner(authorization, session_cookie=session_cookie)
    try:
        with store.connect() as conn:
            return get_learning_activity(
                conn,
                learner,
                secret=settings.registration_rate_limit_secret,
                mode=mode,
                limit=limit,
                cursor=cursor,
            )
    except (ActivityCursorError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_activity_request",
                "message": "The requested activity page is unavailable. Start again from the first page.",
            },
        ) from exc


@app.get("/learning/sessions")
def learning_sessions(
    response: Response,
    limit: int = Query(default=10, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=MAX_SESSION_OFFSET),
    saved_only: bool = Query(default=False, alias="savedOnly"),
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    """Return recent completed session aggregates without assessment payloads."""

    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    learner = effective_learner(authorization, session_cookie=session_cookie)
    with store.connect() as conn:
        return get_learning_sessions(
            conn,
            learner,
            secret=settings.registration_rate_limit_secret,
            limit=limit,
            offset=offset,
            saved_only=saved_only,
        )


@app.get("/learning/sessions/{session_ref}")
def learning_session_review(
    response: Response,
    session_ref: str = ApiPath(min_length=1, max_length=128),
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    """Resolve an opaque owner-bound reference to an answer-free review."""

    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    learner = effective_learner(authorization, session_cookie=session_cookie)
    with store.connect() as conn:
        review = get_learning_session_review(
            conn,
            learner,
            secret=settings.registration_rate_limit_secret,
            session_ref=session_ref,
        )
    if review is None:
        raise _learning_session_not_found()
    return review


def _learning_session_not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": "learning_session_not_found",
            "message": "Learning session not found",
        },
        headers={
            "Cache-Control": "no-store, private",
            "Pragma": "no-cache",
            "Vary": "Authorization, Cookie",
        },
    )


def _set_learning_replay_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Vary"] = "Authorization, Cookie"


def _guard_learning_replay_case(case_id: str, learner_id: str) -> None:
    """Preserve assessment secrecy and cache policy on guarded replay reads."""

    try:
        _guard_pending_assessment_case(case_id, learner_id=learner_id)
    except HTTPException as exc:
        headers = dict(exc.headers or {})
        headers.update(
            {
                "Cache-Control": "no-store, private",
                "Pragma": "no-cache",
                "Vary": "Authorization, Cookie",
            }
        )
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
            headers=headers,
        ) from exc


def _owned_learning_replay_attempt(
    *, learner_id: str, session_ref: str, attempt_index: int
) -> Any:
    with store.connect() as conn:
        attempt = resolve_learning_replay_attempt(
            conn,
            learner_id,
            session_secret=settings.registration_rate_limit_secret,
            session_ref=session_ref,
            attempt_index=attempt_index,
        )
    if attempt is None:
        raise _learning_session_not_found()
    return attempt


@app.get("/learning/sessions/{session_ref}/attempts/{attempt_index}/replay")
def learning_session_attempt_replay(
    response: Response,
    session_ref: str = ApiPath(min_length=1, max_length=128),
    attempt_index: int = ApiPath(ge=1, le=5000),
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    """Reconstruct one committed item through a strict post-completion DTO."""

    _set_learning_replay_headers(response)
    learner = effective_learner(authorization, session_cookie=session_cookie)
    attempt = _owned_learning_replay_attempt(
        learner_id=learner,
        session_ref=session_ref,
        attempt_index=attempt_index,
    )
    if not learning_replay_attempt_is_available(
        attempt,
        repo=repo,
        clinical_item_store=clinical_item_store,
    ):
        raise _learning_session_not_found()
    _guard_learning_replay_case(attempt.canonical_ecg_id, learner)
    comparison_ecg_id = learning_replay_comparison_ecg_id(
        attempt, clinical_item_store=clinical_item_store
    )
    if comparison_ecg_id:
        _guard_learning_replay_case(comparison_ecg_id, learner)
    try:
        replay = build_learning_replay(
            attempt,
            learner_id=learner,
            session_ref=session_ref,
            capability_secret=ADAPTIVE_PLAN_CONTEXT_SECRET,
            repo=repo,
            packet_provider=packet_for_case,
            clinical_item_store=clinical_item_store,
        )
    except (KeyError, TypeError, ValueError, OSError):
        replay = None
    if replay is None:
        raise _learning_session_not_found()
    return replay


@app.get(
    "/learning/sessions/{session_ref}/attempts/{attempt_index}/waveform/{ecg_ref}"
)
def learning_session_attempt_waveform(
    response: Response,
    session_ref: str = ApiPath(min_length=1, max_length=128),
    attempt_index: int = ApiPath(ge=1, le=5000),
    ecg_ref: str = ApiPath(min_length=1, max_length=128),
    leads: str | None = Query(default=None, max_length=120),
    start: float = Query(default=0, ge=0),
    end: float | None = Query(default=None, ge=0),
    maxPoints: int = Query(default=1200, ge=100, le=5000),
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    """Return only a bounded waveform window for the opened replay attempt."""

    _set_learning_replay_headers(response)
    learner = effective_learner(authorization, session_cookie=session_cookie)
    attempt = _owned_learning_replay_attempt(
        learner_id=learner,
        session_ref=session_ref,
        attempt_index=attempt_index,
    )
    target_ecg_id = (
        resolve_learning_replay_ecg_target(
            attempt,
            ecg_ref,
            learner_id=learner,
            capability_secret=ADAPTIVE_PLAN_CONTEXT_SECRET,
            clinical_item_store=clinical_item_store,
        )
        if is_ecg_capability(ecg_ref)
        else None
    )
    if target_ecg_id is None:
        raise _learning_session_not_found()
    if not learning_replay_attempt_is_available(
        attempt,
        repo=repo,
        clinical_item_store=clinical_item_store,
    ):
        raise _learning_session_not_found()
    _guard_learning_replay_case(target_ecg_id, learner)
    replay_case = repo.get_case(target_ecg_id)
    replay_waveform = (
        replay_case.get("waveform")
        if isinstance(replay_case, dict)
        else {}
    )
    replay_leads = {
        str(value)
        for value in (
            replay_waveform.get("leads")
            if isinstance(replay_waveform, dict)
            else []
        )
        or []
        if str(value)
    }
    lead_list = [lead.strip() for lead in leads.split(",")] if leads else None
    if lead_list and (
        len(lead_list) > 12
        or any(lead not in replay_leads for lead in lead_list)
    ):
        raise HTTPException(
            status_code=422,
            detail="Invalid waveform lead selection",
            headers={
                "Cache-Control": "no-store, private",
                "Pragma": "no-cache",
                "Vary": "Authorization, Cookie",
            },
        )
    try:
        waveform = repo.get_waveform_window(
            target_ecg_id,
            leads=lead_list,
            start=start,
            end=end,
            max_points=maxPoints,
        )
    except (KeyError, TypeError, ValueError, OSError):
        waveform = None
    if not waveform:
        raise _learning_session_not_found()
    return public_waveform(waveform, case_reference=ecg_ref)


def _update_learning_session_attempt_flag(
    *,
    flagged: bool,
    session_ref: str,
    attempt_index: int,
    response: Response,
    authorization: str | None,
    session_cookie: str | None,
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    if session_user(authorization, session_cookie) is None:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "authentication_required",
                "message": "Sign in to save items for review.",
            },
            headers={
                "Cache-Control": "no-store, private",
                "Pragma": "no-cache",
            },
        )
    learner = effective_learner(
        authorization,
        session_cookie=session_cookie,
    )
    with store.connect() as conn:
        result = set_learning_session_attempt_flag(
            conn,
            learner,
            secret=settings.registration_rate_limit_secret,
            session_ref=session_ref,
            attempt_index=attempt_index,
            flagged=flagged,
        )
    if result is None:
        raise _learning_session_not_found()
    return result


@app.put("/learning/sessions/{session_ref}/attempts/{attempt_index}/flag")
def save_learning_session_attempt_flag(
    response: Response,
    session_ref: str = ApiPath(min_length=1, max_length=128),
    attempt_index: int = ApiPath(ge=1, le=5000),
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    """Idempotently save one submitted session item for later review."""

    return _update_learning_session_attempt_flag(
        flagged=True,
        session_ref=session_ref,
        attempt_index=attempt_index,
        response=response,
        authorization=authorization,
        session_cookie=session_cookie,
    )


@app.delete("/learning/sessions/{session_ref}/attempts/{attempt_index}/flag")
def remove_learning_session_attempt_flag(
    response: Response,
    session_ref: str = ApiPath(min_length=1, max_length=128),
    attempt_index: int = ApiPath(ge=1, le=5000),
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    """Idempotently remove one submitted item from the review queue."""

    return _update_learning_session_attempt_flag(
        flagged=False,
        session_ref=session_ref,
        attempt_index=attempt_index,
        response=response,
        authorization=authorization,
        session_cookie=session_cookie,
    )


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
    _guard_pending_assessment_case(attempt.caseId)
    case = _learner_case_or_404(attempt.caseId)
    grade = grade_attempt(case, attempt)
    if attempt.mode in {"concept_practice", "rapid_practice", "tutorial"}:
        # Training and Rapid have exact concept+subskill receipt ledgers, while
        # Guided records its separately labelled formative interaction receipt.
        # The generic grader remains an attempt audit, but it must not also
        # mutate (or advertise a delta for) the legacy objective ledger.
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
    return {
        "attemptId": attempt_id,
        "grade": grade,
        "tutor": tutor,
        "profile": store.get_profile(learner),
        # This response is itself the durable commitment boundary for the
        # generic interpreter. Public packet endpoints remain blinded.
        "packet": packet_for_case(case),
    }


@app.post("/learning-events/guided")
def save_guided_learning_event(
    event: GuidedLearningEventRequest,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    learner = effective_learner(authorization, event.learnerId, session_cookie)
    payload = event.model_dump()
    payload.pop("guidedContext", None)
    canonical_case_id = event.caseId
    if event.caseId and is_ecg_capability(event.caseId):
        guided = _validate_guided_context(
            event.guidedContext,
            learner_id=learner,
            case_reference=event.caseId,
        )
        canonical_case_id = str(guided["caseId"])
        payload["caseId"] = canonical_case_id
    packet = repo.get_case(canonical_case_id) if canonical_case_id else None
    supported = set((packet or {}).get("supported_objectives") or [])
    definition = OBJECTIVES.get(event.concept)
    if definition is None:
        raise HTTPException(status_code=422, detail="Unknown educational objective")
    invalid_subskills = sorted(
        set(event.subskills) - set(definition.allowed_subskills)
    )
    if invalid_subskills:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "objective_subskill_not_registered",
                "objective": event.concept,
                "subskills": invalid_subskills,
            },
        )
    grounded_concepts = set(definition.case_concepts)
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
    try:
        return store.save_guided_learning_event(learner, payload)
    except IdempotencyConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "guided_event_idempotency_conflict",
                "message": (
                    "This Guided action was already saved with different evidence. "
                    "Reload the lesson before trying again."
                ),
            },
        ) from exc


@app.post("/grade/structured")
def grade_structured(attempt: AttemptRequest) -> dict[str, Any]:
    del attempt
    raise HTTPException(
        status_code=403,
        detail={
            "code": "server_submit_grading_required",
            "message": "Assessment interpretations are graded only by their durable submit endpoint.",
        },
    )


@app.post("/grade/text")
def grade_text(attempt: AttemptRequest) -> dict[str, Any]:
    del attempt
    raise HTTPException(
        status_code=403,
        detail={
            "code": "server_submit_grading_required",
            "message": "Assessment interpretations are graded only by their durable submit endpoint.",
        },
    )


@app.post("/grade/click/{case_id}")
def grade_click(
    case_id: str,
    request: ClickGradeRequest,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    learner = effective_learner(authorization, session_cookie=session_cookie)
    guided = _validate_guided_context(
        request.guidedContext,
        learner_id=learner,
        case_reference=case_id,
    )
    case = _learner_case_or_404(str(guided["caseId"]))
    return grade_click_answer(case, request.lead, request.timeSec, request.amplitudeMv, request.concept)


@app.post("/grade/region/{case_id}")
def grade_region(
    case_id: str,
    request: RegionGradeRequest,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    learner = effective_learner(authorization, session_cookie=session_cookie)
    guided = _validate_guided_context(
        request.guidedContext,
        learner_id=learner,
        case_reference=case_id,
    )
    case = _learner_case_or_404(str(guided["caseId"]))
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


def _packet_measurement_value(
    case: dict[str, Any], measurement_key: str, derive: str | None
) -> float | None:
    raw = ((case.get("ptbxl_plus") or {}).get("measurements") or {}).get(
        measurement_key
    )
    value: object = raw
    if isinstance(raw, dict):
        value = raw.get("value", raw.get("value_ms"))
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    result = float(value)
    if not math.isfinite(result):
        return None
    if derive == "rr_from_heart_rate":
        if result <= 0:
            return None
        result = 60_000 / result
    return result if math.isfinite(result) else None


@app.post("/grade/measurement/{case_id}")
def grade_guided_measurement(
    case_id: str,
    request: GuidedMeasurementGradeRequest,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    """Grade one committed Guided measurement without returning its answer value."""

    learner = effective_learner(authorization, session_cookie=session_cookie)
    guided = _validate_guided_context(
        request.guidedContext,
        learner_id=learner,
        case_reference=case_id,
    )
    case = _learner_case_or_404(str(guided["caseId"]))
    expected = _packet_measurement_value(
        case, request.measurementKey, request.derive
    )
    if expected is None:
        return {
            "correct": False,
            "noTarget": True,
            "feedback": "This ECG has no reviewed measurement for this task.",
        }
    correct = abs(request.value - expected) <= request.tolerance
    return {
        "correct": correct,
        "noTarget": False,
        "feedback": (
            "Your committed measurement is within the reviewed tolerance."
            if correct
            else "Your committed measurement is outside the reviewed tolerance. Recheck the boundaries and units."
        ),
    }


@app.get("/practice/next")
def get_next_practice_case(
    learnerId: str = "demo",
    conceptId: str | None = Query(
        default=None,
        min_length=1,
        max_length=160,
        pattern=r"^[A-Za-z0-9_:-]+$",
    ),
    subskill: str | None = Query(
        default=None,
        min_length=1,
        max_length=40,
        pattern=r"^[a-z_]+$",
    ),
    excludeCaseIds: str | None = Query(default=None, max_length=4000),
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    allowed_subskills = {"recognize", "localize", "measure", "discriminate", "explain_mechanism", "synthesize", "apply_in_context", "calibrate_confidence"}
    # Reject unknown selector keys before calling the repository. Previously an
    # unknown concept produced an empty indexed query and then fell through to
    # an unscoped full-corpus candidate load. Invalid subskills were silently
    # discarded, which made a malformed targeted request look successful.
    if conceptId is not None and conceptId not in CONCEPT_BY_ID:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "unknown_practice_concept",
                "message": "Choose a concept from the current ECG concept registry.",
            },
        )
    if subskill is not None and subskill not in allowed_subskills:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "unknown_practice_subskill",
                "message": "Choose a subskill from the current competency registry.",
            },
        )
    excluded = [item.strip() for item in (excludeCaseIds or "").split(",") if item.strip()]
    if len(excluded) > 100 or any(len(item) > 128 for item in excluded):
        raise HTTPException(status_code=422, detail="excludeCaseIds accepts at most 100 bounded case ids")
    result = next_case(
        repo,
        store,
        learner_id=effective_learner(authorization, learnerId, session_cookie),
        concept_id=conceptId,
        subskill_id=subskill,
        exclude_case_ids=set(excluded),
    )
    # Practice is assessment: don't leak the report/top-concepts in the pre-answer payload.
    if result.get("case"):
        result["case"] = blind_summary(result["case"])
    # The selector's target list is an answer key. The committed grade carries
    # the reviewed objectives later.
    result["targetObjectives"] = []
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
    if result.get("deprecated"):
        raise HTTPException(status_code=410, detail=result["error"])
    if result is None or result.get("error"):
        raise HTTPException(status_code=400, detail=(result or {}).get("error", "Could not start review session."))
    if result.get("case"):
        result["case"] = blind_summary(result["case"])
    if "targetObjectives" in result:
        result["targetObjectives"] = []
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
    if "targetObjectives" in result:
        result["targetObjectives"] = []
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
    if result.get("deprecated"):
        raise HTTPException(
            status_code=410,
            detail={
                "code": "legacy_review_deprecated",
                "message": result["reason"],
                "replacement": result["replacement"],
            },
        )
    if result.get("case"):
        result["case"] = blind_summary(result["case"])
    if "targetObjectives" in result:
        result["targetObjectives"] = []
    return result


@app.post("/tutor/chat")
def tutor_chat(
    request: TutorChatRequest,
    http_request: Request,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    learner = effective_learner(authorization, request.learnerId, session_cookie)
    if request.viewerState.get("activity") == "adaptive_mastery_plan":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "adaptive_plan_context_required",
                "message": "Open the server-issued mastery plan before asking its coach.",
            },
        )
    _guard_uncommitted_clinical_tutor(learner, request.caseId)
    _guard_pending_assessment_case(request.caseId)
    case_packet = None
    if request.caseId:
        guided_case_id: str | None = None
        if request.mode == "tutorial":
            if not request.lessonId or not is_ecg_capability(request.caseId):
                raise HTTPException(status_code=404, detail="Case not found")
            guided_case_id = _resolve_guided_case_reference(
                learner, request.lessonId, request.caseId
            )
            if guided_case_id is None:
                raise HTTPException(status_code=404, detail="Case not found")
        case = repo.get_case(guided_case_id or request.caseId)
        if case:
            if not learner_direct_packet_policy(case).allowed:
                raise HTTPException(status_code=404, detail="Case not found")
            if guided_case_id:
                case_packet = (
                    public_case_packet(
                        packet_for_case(case),
                        case_reference=request.caseId,
                        display_id="Guided teaching ECG",
                    )
                    if _guided_case_committed(learner, guided_case_id)
                    else _guided_public_packet(
                        case,
                        case_reference=request.caseId,
                        display_id="Guided teaching ECG",
                    )
                )
            else:
                case_packet = packet_for_case(case)
        else:
            # Clinical items are authored scenarios, but their tracings must
            # resolve through the same real PTB-backed packet provider.
            case_packet = clinical_packet(request.caseId)
        if case_packet is None:
            raise HTTPException(status_code=404, detail="Case not found")
    profile = store.ensure_profile(learner)
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
    scopeKey: str | None = Field(default=None, max_length=240)
    message: str = Field(min_length=1, max_length=TUTOR_MESSAGE_MAX_CHARS)
    viewerState: dict[str, Any] = Field(default_factory=dict)
    clinicalContext: "ClinicalTutorContextRef | None" = None
    clinicalShiftContext: "ClinicalShiftTutorContextRef | None" = None
    adaptiveContext: "AdaptiveTutorContextRef | None" = None
    rapidRoundContext: "RapidRoundTutorContextRef | None" = None
    trainingSetContext: "TrainingSetTutorContextRef | None" = None

    _bounded_viewer_state = field_validator("viewerState")(validate_tutor_viewer_state)


class ClinicalTutorContextRef(BaseModel):
    contextId: str = Field(min_length=4, max_length=160)
    sessionId: str = Field(min_length=1, max_length=160)
    itemId: str = Field(min_length=1, max_length=240)
    answerId: int = Field(ge=1)
    version: str = Field(min_length=1, max_length=80)


class ClinicalShiftTutorContextRef(BaseModel):
    contextId: str = Field(min_length=4, max_length=160)
    sessionId: str = Field(min_length=1, max_length=160)
    answerCount: int = Field(ge=1, le=100)
    version: str = Field(min_length=1, max_length=80)


class AdaptiveTutorContextRef(BaseModel):
    contextId: str = Field(min_length=32, max_length=180)
    version: str = Field(min_length=1, max_length=80)
    expiresAt: str = Field(min_length=20, max_length=80)


class RapidRoundTutorContextRef(BaseModel):
    roundId: str = Field(min_length=4, max_length=160)
    answerCount: int = Field(ge=1, le=5000)
    version: str = Field(min_length=1, max_length=80)


class TrainingSetTutorContextRef(BaseModel):
    campaignId: str = Field(min_length=4, max_length=160)
    answerCount: int = Field(ge=1, le=5000)
    version: str = Field(min_length=1, max_length=80)


TutorMessageRequest.model_rebuild()


def _is_foundations_tutor_turn(request: TutorMessageRequest) -> bool:
    """Fail closed on chat-authored progress for every native Foundations scene.

    The native module currently uses the shared Guided tutor without a
    server-graded assessment context. These identifiers only make the tutor
    more restrictive: spoofing them cannot unlock data or evidence.
    """

    if request.mode != "tutorial":
        return False
    if request.lessonId == "foundations":
        return True
    scope_key = str(request.scopeKey or "")
    if scope_key == "foundations" or scope_key.startswith("foundations:"):
        return True
    return request.viewerState.get("moduleId") == "foundations"


def _safe_tutor_runtime_meta(result: dict[str, Any]) -> dict[str, Any]:
    """Persist bounded delivery telemetry without provider payloads or secrets."""

    provider = result.get("provider")
    safe_provider = (
        provider[:80]
        if isinstance(provider, str) and provider and len(provider) <= 160
        else "unknown"
    )
    remote = (
        result.get("remoteCall")
        if isinstance(result.get("remoteCall"), dict)
        else {}
    )
    allowed_statuses = {
        "not_attempted",
        "not_configured",
        "request_rejected",
        "failed",
        "success",
        "unknown",
    }
    remote_status = str(remote.get("status") or "unknown")
    if remote_status not in allowed_statuses:
        remote_status = "unknown"
    claim_check = (
        result.get("claimCheck")
        if isinstance(result.get("claimCheck"), dict)
        else {}
    )

    def safe_count(key: str) -> int:
        value = claim_check.get(key)
        return min(len(value), 100) if isinstance(value, list) else 0

    return {
        "provider": safe_provider,
        "remoteProviderConfigured": bool(result.get("remoteProviderConfigured")),
        "remoteCall": {
            "attempted": bool(remote.get("attempted")),
            "status": remote_status,
        },
        # Raw validation errors can contain provider-output fragments. Store
        # only whether the schema fallback was required.
        "schemaStatus": (
            "fallback" if result.get("schemaError") is not None else "validated"
        ),
        "claimCheck": {
            "unsupportedMeasurementMentions": safe_count(
                "unsupportedMeasurementMentions"
            ),
            "unsupportedDiagnosisClaims": safe_count(
                "unsupportedDiagnosisClaims"
            ),
        },
    }


def _clinical_tutor_bundle(
    request: TutorMessageRequest,
    learner: str,
) -> dict[str, Any] | None:
    reference = request.clinicalContext
    if reference is None:
        return None
    if request.mode != "practice":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "clinical_tutor_context_mode_mismatch",
                "message": "Clinical feedback context is available only to the post-commit practice tutor.",
            },
        )
    # New Clinical rows already use opaque item handles, while older completed
    # shifts can retain an authored item id. Resolve the browser's public handle
    # only through this owner's durable answer ledger so legacy debriefs remain
    # usable without accepting a raw authoring key.
    durable_item_id = reference.itemId
    owned_session = store.get_shift_session(reference.sessionId)
    if owned_session and str(owned_session.get("learnerId") or "") == learner:
        for answer in store.get_shift_answers(reference.sessionId):
            candidate = str(answer.get("itemId") or "")
            item = clinical_item_store.get_item(candidate) if candidate else None
            if item is not None and hmac.compare_digest(
                public_item_reference(
                    str(item.item_id),
                    learner_id=learner,
                    session_id=reference.sessionId,
                ),
                reference.itemId,
            ):
                durable_item_id = candidate
                break
    try:
        bundle = build_clinical_tutor_context(
            store,
            clinical_item_store,
            clinical_packet,
            learner_id=learner,
            session_id=reference.sessionId,
            item_id=durable_item_id,
            answer_id=reference.answerId,
            context_id=reference.contextId,
            version=reference.version,
        )
    except ClinicalTutorContextNotReady as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "clinical_tutor_context_not_ready", "message": str(exc)},
        ) from exc
    except ClinicalTutorContextNotFound as exc:
        raise HTTPException(status_code=404, detail="Clinical tutor context not found") from exc
    except ClinicalTutorContextInvalid as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "clinical_tutor_context_invalid",
                "message": "The stored Clinical feedback no longer satisfies its grounding contract.",
            },
        ) from exc

    # The canonical lookup key remains only in the server-owned packet. The
    # provider context itself contains the owner/session capability.
    authoritative_case = str(bundle["casePacket"]["case_id"])
    authoritative_scope = str(bundle["reference"]["contextId"])
    authoritative_case_ref = issue_ecg_capability(
        settings.registration_rate_limit_secret,
        learner,
        "clinical",
        reference.sessionId,
        authoritative_case,
    )
    authoritative_scope_key = f"clinical:{reference.sessionId}"
    case_matches = request.caseId is None or matches_ecg_capability(
        request.caseId,
        settings.registration_rate_limit_secret,
        learner,
        "clinical",
        reference.sessionId,
        authoritative_case,
    )
    if (
        not case_matches
        or request.lessonId not in {None, authoritative_scope}
        or request.scopeKey not in {None, authoritative_scope_key}
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "clinical_tutor_context_mismatch",
                "message": "The tutor request does not match the stored Clinical feedback.",
            },
        )
    # These values are derived from the durable answer, not trusted from the
    # browser. They also scope thread restoration to this exact attempt.
    request.caseId = authoritative_case_ref
    request.lessonId = authoritative_scope
    request.scopeKey = authoritative_scope_key
    return bundle


def _clinical_shift_tutor_bundle(
    request: TutorMessageRequest,
    learner: str,
) -> dict[str, Any] | None:
    reference = request.clinicalShiftContext
    if reference is None:
        return None
    if request.mode != "practice":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "clinical_shift_tutor_context_mode_mismatch",
                "message": "The completed-shift coach is available only in Clinical practice mode.",
            },
        )
    if request.caseId is not None or request.lessonId not in {
        None,
        reference.contextId,
    }:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "clinical_shift_tutor_context_mismatch",
                "message": "The tutor request does not match the completed Clinical shift.",
            },
        )
    try:
        bundle = build_clinical_shift_tutor_context(
            store,
            clinical_item_store,
            clinical_packet,
            learner_id=learner,
            session_id=reference.sessionId,
            answer_count=reference.answerCount,
            context_id=reference.contextId,
            version=reference.version,
        )
    except ClinicalTutorContextNotReady as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "clinical_shift_tutor_context_not_ready",
                "message": str(exc),
            },
        ) from exc
    except ClinicalTutorContextNotFound as exc:
        raise HTTPException(status_code=404, detail="Clinical shift debrief not found") from exc
    except ClinicalTutorContextInvalid as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "clinical_shift_tutor_context_invalid",
                "message": "The completed Clinical shift no longer satisfies its grounding contract.",
            },
        ) from exc
    request.caseId = None
    request.lessonId = str(bundle["reference"]["contextId"])
    return bundle


def _rapid_round_tutor_bundle(
    request: TutorMessageRequest,
    learner: str,
) -> dict[str, Any] | None:
    reference = request.rapidRoundContext
    if reference is None:
        return None
    if request.mode != "practice":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "rapid_round_context_mode_mismatch",
                "message": "The completed-round coach is available only in Rapid practice mode.",
            },
        )
    if request.caseId is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "rapid_round_context_mismatch",
                "message": "A completed-round debrief cannot be rebound to one browser-selected ECG.",
            },
        )
    try:
        bundle = build_rapid_round_tutor_context(
            store,
            learner_id=learner,
            round_id=reference.roundId,
            answer_count=reference.answerCount,
            version=reference.version,
        )
    except RapidTutorContextNotReady as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "rapid_round_context_not_ready", "message": str(exc)},
        ) from exc
    except RapidTutorContextNotFound as exc:
        raise HTTPException(status_code=404, detail="Rapid round debrief not found") from exc
    except RapidTutorContextInvalid as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "rapid_round_context_invalid",
                "message": "The completed Rapid round no longer satisfies its grounding contract.",
            },
        ) from exc
    context_id = str(bundle["reference"]["contextId"])
    if request.lessonId not in {None, context_id} or request.scopeKey not in {
        None,
        context_id,
    }:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "rapid_round_context_mismatch",
                "message": "The tutor request does not match the completed Rapid round.",
            },
        )
    # The automatic debrief turn has one reviewed instruction. Browser text,
    # aggregates, and receipt samples are deliberately discarded before chat
    # history or a model sees them.
    request.message = (
        "Debrief this completed Rapid ECG round using only the server-owned aggregate and "
        "receipt context. Identify one recurring reasoning pattern, connect two concepts "
        "only when the stored evidence supports it, and ask one concise next-step question."
    )
    request.caseId = None
    request.lessonId = context_id
    request.scopeKey = context_id
    return bundle


def _training_set_tutor_bundle(
    request: TutorMessageRequest,
    learner: str,
) -> dict[str, Any] | None:
    reference = request.trainingSetContext
    if reference is None:
        return None
    if request.mode != "practice":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "training_set_context_mode_mismatch",
                "message": "The completed-set coach is available only in Focused Practice mode.",
            },
        )
    if request.caseId is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "training_set_context_mismatch",
                "message": "A completed-set debrief cannot be rebound to one browser-selected ECG.",
            },
        )
    try:
        bundle = build_training_set_tutor_context(
            training_campaign_store,
            learner_id=learner,
            campaign_id=reference.campaignId,
            answer_count=reference.answerCount,
            version=reference.version,
        )
    except TrainingTutorContextNotReady as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "training_set_context_not_ready", "message": str(exc)},
        ) from exc
    except TrainingTutorContextNotFound as exc:
        raise HTTPException(
            status_code=404, detail="Focused Practice set debrief not found"
        ) from exc
    except TrainingTutorContextInvalid as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "training_set_context_invalid",
                "message": "The completed Focused Practice set no longer satisfies its grounding contract.",
            },
        ) from exc
    context_id = str(bundle["reference"]["contextId"])
    if request.lessonId not in {None, context_id} or request.scopeKey not in {
        None,
        context_id,
    }:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "training_set_context_mismatch",
                "message": "The tutor request does not match the completed Focused Practice set.",
            },
        )
    # Keep the learner's actual question intact. The model receives it as the
    # question, while every performance fact comes from serverOwnedContext.
    request.caseId = None
    request.lessonId = context_id
    request.scopeKey = context_id
    return bundle


def _adaptive_tutor_bundle(
    request: TutorMessageRequest,
    learner: str,
) -> dict[str, Any] | None:
    reference = request.adaptiveContext
    if reference is None:
        return None
    if request.mode != "freeform":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "adaptive_plan_context_mode_mismatch",
                "message": "The mastery-plan coach is available only in its freeform review workspace.",
            },
        )
    if request.caseId is not None or request.lessonId not in {None, ADAPTIVE_TUTOR_SCOPE}:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "adaptive_plan_context_mismatch",
                "message": "The tutor request does not match the server-issued mastery-plan workspace.",
            },
        )
    try:
        verified_reference = verify_adaptive_tutor_context(
            reference.model_dump(),
            learner,
            ADAPTIVE_PLAN_CONTEXT_SECRET,
        )
    except AdaptiveTutorContextExpired as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "adaptive_plan_context_expired",
                "message": str(exc),
            },
        ) from exc
    except AdaptiveTutorContextNotFound as exc:
        raise HTTPException(status_code=404, detail="Adaptive plan context not found") from exc

    # Rebuild from current durable competency state. No plan field supplied by
    # the browser is copied into the provider context.
    current_plan = _adaptive_plan_for_learner(learner)
    request.caseId = None
    request.lessonId = ADAPTIVE_TUTOR_SCOPE
    primary = (
        current_plan.get("primary")
        if isinstance(current_plan.get("primary"), dict)
        else None
    )
    return {
        "context": build_adaptive_tutor_context(
            current_plan,
            primary_guidance=curated_general_teaching(
                str(primary.get("caseConcept") or "") if primary else None
            ),
        ),
        "reference": verified_reference,
    }


def _guard_uncommitted_clinical_tutor(learner: str, case_id: str | None) -> None:
    pending = bool(
        case_id
        and is_uncommitted_clinical_case(
            store,
            clinical_item_store,
            learner_id=learner,
            case_id=case_id,
        )
    )
    if case_id and is_ecg_capability(case_id):
        session = store.get_resumable_shift_session(learner)
        pending_item = (
            clinical_item_store.get_item(str(session.get("pendingItemId") or ""))
            if session
            else None
        )
        pending = bool(
            session
            and pending_item
            and any(
                canonical_id
                and matches_ecg_capability(
                    case_id,
                    settings.registration_rate_limit_secret,
                    learner,
                    "clinical",
                    str(session["sessionId"]),
                    str(canonical_id),
                )
                for canonical_id in (
                    pending_item.ecg_id,
                    pending_item.prior_ecg_id,
                )
            )
        )
    if pending:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "clinical_tutor_context_not_ready",
                "message": "Submit the Clinical decision before asking the case-grounded tutor.",
            },
        )


def _committed_assessment_tutor_case(
    learner: str,
    reference: str,
    scope_key: str | None,
) -> str | None:
    """Resolve a post-commit mode capability without broad corpus lookup.

    The browser supplies only an opaque reference and a session scope. The
    canonical ECG is accepted solely when durable owner state identifies it as
    that session's current feedback case.
    """

    if not is_ecg_capability(reference) or not scope_key:
        return None
    mode, separator, session_id = scope_key.partition(":")
    if not separator or mode not in {"training", "rapid"} or not session_id:
        return None

    if mode == "training":
        session = training_campaign_store.get_campaign(session_id)
    else:
        session = store.get_rapid_round(session_id)
    if not session or str(session.get("learnerId") or "") != learner:
        return None
    canonical_id = str(session.get("feedbackCaseId") or "")
    if not canonical_id or not matches_ecg_capability(
        reference,
        settings.registration_rate_limit_secret,
        learner,
        mode,
        session_id,
        canonical_id,
    ):
        return None
    return canonical_id


@app.post("/tutor/message")
def tutor_message(
    request: TutorMessageRequest,
    http_request: Request,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    learner = effective_learner(authorization, request.learnerId, session_cookie)
    supplied_contexts = sum(
        context is not None
        for context in (
            request.clinicalContext,
            request.clinicalShiftContext,
            request.adaptiveContext,
            request.rapidRoundContext,
            request.trainingSetContext,
        )
    )
    if supplied_contexts > 1:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "tutor_context_conflict",
                "message": "A tutor turn can use one server-owned learning context at a time.",
            },
        )
    clinical_bundle = _clinical_tutor_bundle(request, learner)
    clinical_shift_bundle = _clinical_shift_tutor_bundle(request, learner)
    rapid_round_bundle = _rapid_round_tutor_bundle(request, learner)
    training_set_bundle = _training_set_tutor_bundle(request, learner)
    adaptive_bundle = _adaptive_tutor_bundle(request, learner)
    if (
        clinical_bundle is None
        and clinical_shift_bundle is None
        and rapid_round_bundle is None
        and training_set_bundle is None
        and adaptive_bundle is None
    ):
        if request.viewerState.get("activity") == "adaptive_mastery_plan":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "adaptive_plan_context_required",
                    "message": "Open the server-issued mastery plan before asking its coach.",
                },
            )
        if request.viewerState.get("activity") == "training_set_debrief":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "training_set_context_required",
                    "message": "Open the completed Focused Practice set before asking its coach.",
                },
            )
        _guard_uncommitted_clinical_tutor(learner, request.caseId)
        _guard_pending_assessment_case(request.caseId, learner_id=learner)
    authoritative_bundle = (
        clinical_bundle
        or clinical_shift_bundle
        or rapid_round_bundle
        or training_set_bundle
        or adaptive_bundle
    )
    assessment_scope_mode = (
        str(request.scopeKey).partition(":")[0]
        if request.scopeKey is not None
        else ""
    )
    if (
        authoritative_bundle is None
        and assessment_scope_mode in {"training", "rapid"}
        and (not request.caseId or not is_ecg_capability(request.caseId))
    ):
        # A mode-scoped post-commit tutor turn must resolve through the exact
        # owner/session capability. Never let a guessed canonical id fall back
        # to the generic corpus tutor merely because the assessment committed.
        raise HTTPException(status_code=404, detail="Case not found")
    assessment_tutor_case: str | None = None
    training_ecg_context: dict[str, Any] | None = None
    guided_tutor_case: str | None = None
    if (
        authoritative_bundle is None
        and request.caseId
        and is_ecg_capability(request.caseId)
    ):
        if request.mode == "tutorial" and request.lessonId:
            guided_tutor_case = _resolve_guided_case_reference(
                learner,
                request.lessonId,
                request.caseId,
            )
        assessment_tutor_case = guided_tutor_case or _committed_assessment_tutor_case(
            learner, request.caseId, request.scopeKey
        )
        if assessment_tutor_case is None:
            # A capability is useful only with the exact owner/session feedback
            # record that issued it. Never fall back to a corpus-wide search.
            raise HTTPException(status_code=404, detail="Case not found")
        if assessment_scope_mode == "training":
            try:
                training_ecg_context = build_training_ecg_tutor_context(
                    training_campaign_store,
                    learner_id=learner,
                    campaign_id=str(request.scopeKey).partition(":")[2],
                    case_id=assessment_tutor_case,
                )
            except TrainingTutorContextNotFound as exc:
                raise HTTPException(status_code=404, detail="Case not found") from exc
            except (
                TrainingTutorContextInvalid,
                TrainingTutorContextNotReady,
            ) as exc:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "training_ecg_context_invalid",
                        "message": "The committed Focused Practice ECG no longer satisfies its tutor grounding contract.",
                    },
                ) from exc
    if request.threadId:
        existing_thread = store.get_thread(request.threadId)
        if existing_thread and existing_thread.get("learnerId") != learner:
            raise HTTPException(status_code=404, detail="Thread not found")
        if existing_thread:
            # A pending case cannot be recovered from an older tutor thread.
            # Also require ordinary threads to retain their original case
            # binding so omitting `caseId` cannot smuggle answer-bearing history
            # into an apparently ungrounded turn.
            _guard_pending_assessment_case(existing_thread.get("caseId"), learner_id=learner)
            if authoritative_bundle is None and existing_thread.get("caseId") != request.caseId:
                raise HTTPException(status_code=404, detail="Thread not found")
            # A tutor thread is also bound to its exact learning waypoint. This
            # prevents a conversation (and its answer-bearing annotations) from
            # one Guided scene being replayed in another scene that happens to
            # use the same ECG and lesson.
            if existing_thread.get("scopeKey") != request.scopeKey:
                raise HTTPException(status_code=404, detail="Thread not found")
        if authoritative_bundle and existing_thread and (
            existing_thread.get("caseId") != request.caseId
            or existing_thread.get("lessonId") != request.lessonId
            or existing_thread.get("mode") != request.mode
            or existing_thread.get("scopeKey") != request.scopeKey
        ):
            raise HTTPException(status_code=404, detail="Thread not found")
    case_packet = clinical_bundle["casePacket"] if clinical_bundle else None
    if request.caseId and authoritative_bundle is None:
        canonical_case_id = assessment_tutor_case or request.caseId
        case = repo.get_case(canonical_case_id)
        if case:
            if not learner_direct_packet_policy(case).allowed:
                raise HTTPException(status_code=404, detail="Case not found")
            case_packet = packet_for_case(case)
        else:
            # Clinical items may use a scenario id distinct from the underlying
            # real ECG id. The provider remains provenance-gated and arbitrary
            # ids fail closed.
            case_packet = clinical_packet(canonical_case_id)
        if case_packet is None:
            raise HTTPException(status_code=404, detail="Case not found")
    if case_packet and request.caseId and is_ecg_capability(request.caseId):
        # Tutor grounding keeps its evidence, but the provider never receives
        # a source-dataset lookup key that could be echoed in prose.
        if guided_tutor_case and not _guided_case_committed(
            learner, guided_tutor_case
        ):
            case_packet = _guided_public_packet(
                repo.get_case(guided_tutor_case) or {},
                case_reference=request.caseId,
                display_id="Guided teaching ECG",
            )
        else:
            case_packet = public_case_packet(
                case_packet,
                case_reference=request.caseId,
                display_id=(
                    "Guided teaching ECG"
                    if guided_tutor_case
                    else f"Assessment ECG {request.caseId[-8:]}"
                ),
            )
    lesson = (
        None
        if authoritative_bundle
        else get_tutorial(request.lessonId) if request.lessonId else None
    )
    profile = store.ensure_profile(learner)
    thread_id = store.ensure_thread(
        learner_id=learner,
        thread_id=request.threadId,
        mode=request.mode,
        lesson_id=request.lessonId,
        case_id=request.caseId,
        scope_key=request.scopeKey,
    )
    history = store.thread_history(thread_id)
    store.append_tutor_message(thread_id, "user", request.message)
    if clinical_bundle:
        viewer_state = {"activity": "clinical_case_debrief", "committed": True}
        server_context = clinical_bundle["context"]
    elif clinical_shift_bundle:
        viewer_state = {
            "activity": "clinical_shift_debrief",
            "committed": True,
            "completedCaseCount": clinical_shift_bundle["reference"]["answerCount"],
            "authoritativeShiftContext": True,
        }
        server_context = clinical_shift_bundle["context"]
    elif rapid_round_bundle:
        viewer_state = {
            "activity": "rapid_round_debrief",
            "committed": True,
            "completedCaseCount": rapid_round_bundle["reference"]["answerCount"],
            "authoritativeRoundContext": True,
        }
        server_context = rapid_round_bundle["context"]
    elif training_set_bundle:
        # Browser aggregates are intentionally discarded. This fixed marker
        # tells the provider which review surface is open without accepting any
        # learner-score, receipt, or ECG claims from viewerState.
        viewer_state = {
            "activity": "training_set_debrief",
            "surface": "review",
            "committed": True,
            "completedCaseCount": training_set_bundle["reference"]["answerCount"],
            "authoritativeTrainingSetContext": True,
        }
        server_context = training_set_bundle["context"]
    elif adaptive_bundle:
        # This is a fixed UI marker, not the caller's viewerState. The complete
        # authoritative plan lives in serverOwnedContext below.
        viewer_state = {
            "activity": "adaptive_mastery_plan",
            "surface": "review",
            "authoritativePlanContext": True,
        }
        server_context = adaptive_bundle["context"]
    elif training_ecg_context:
        viewer_state = {
            key: value
            for key, value in request.viewerState.items()
            if key != "structuredInterpretation"
        }
        viewer_state.update(
            {
                "activity": "training_ecg_debrief",
                "committed": True,
                "authoritativeTrainingEcgContext": True,
            }
        )
        server_context = training_ecg_context
    else:
        viewer_state = request.viewerState
        server_context = None
    result = tutor_service.converse(
        request.message,
        case_packet,
        profile,
        history,
        request.mode,
        lesson,
        viewer_state,
        server_context=server_context,
        remote_reservation=_remote_tutor_reservation(learner, http_request),
    )
    if rapid_round_bundle:
        # Chat is explanatory only. Even a schema-valid remote response cannot
        # turn a debrief into assessment evidence or annotate a non-current ECG.
        remote = result.get("remoteCall") if isinstance(result.get("remoteCall"), dict) else {}
        if result.get("schemaError") is not None or remote.get("status") in {
            "failed",
            "request_rejected",
            "not_configured",
            "unknown",
        }:
            telemetry = {
                key: result.get(key)
                for key in (
                    "schemaError",
                    "provider",
                    "remoteProviderConfigured",
                    "remoteCall",
                    "remoteUsage",
                    "claimCheck",
                    "viewerActionStatus",
                )
                if key in result
            }
            result = {
                **deterministic_rapid_tutor_response(rapid_round_bundle["context"]),
                **telemetry,
            }
        result["objectiveUpdates"] = []
        result["viewerActions"] = []
    if training_set_bundle:
        # Set review is explanatory only. Even a schema-valid provider reply
        # cannot create competency evidence or drive an ECG that is no longer
        # the active assessment item.
        remote = result.get("remoteCall") if isinstance(result.get("remoteCall"), dict) else {}
        if result.get("schemaError") is not None or remote.get("status") in {
            "failed",
            "request_rejected",
            "not_configured",
            "unknown",
        }:
            telemetry = {
                key: result.get(key)
                for key in (
                    "schemaError",
                    "provider",
                    "remoteProviderConfigured",
                    "remoteCall",
                    "remoteUsage",
                    "claimCheck",
                    "viewerActionStatus",
                )
                if key in result
            }
            result = {
                **deterministic_training_tutor_response(
                    training_set_bundle["context"]
                ),
                **telemetry,
            }
        result["objectiveUpdates"] = []
        result["viewerActions"] = []
    if adaptive_bundle:
        # The generic tutor schema includes capabilities used elsewhere. The
        # plan coach is read-only: enforce that contract after generation so a
        # valid-but-errant provider response still cannot mutate, annotate, or
        # redirect beyond the current scheduler-issued plan.
        result = enforce_adaptive_tutor_response(result, adaptive_bundle["context"])
    if _is_foundations_tutor_turn(request):
        # Foundations interactions are formative until their reviewed manifest
        # and server-owned grader exist. Tutor output may explain or annotate,
        # but it can never create a progress/mastery mutation.
        result["objectiveUpdates"] = []
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
            **_safe_tutor_runtime_meta(result),
            "clinicalContextId": (
                clinical_bundle["reference"]["contextId"] if clinical_bundle else None
            ),
            "clinicalShiftContextId": (
                clinical_shift_bundle["reference"]["contextId"]
                if clinical_shift_bundle
                else None
            ),
            "rapidRoundContextId": (
                rapid_round_bundle["reference"]["contextId"]
                if rapid_round_bundle
                else None
            ),
            "trainingSetContextId": (
                training_set_bundle["reference"]["contextId"]
                if training_set_bundle
                else None
            ),
            "adaptiveContextVersion": (
                ADAPTIVE_TUTOR_CONTEXT_VERSION if adaptive_bundle else None
            ),
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
    learner = effective_learner(authorization, session_cookie=session_cookie)
    if thread.get("learnerId") != learner:
        raise HTTPException(status_code=404, detail="Thread not found")
    _guard_pending_assessment_case(thread.get("caseId"), learner_id=learner)
    return thread


@app.get("/tutor/threads")
def tutor_threads(
    mode: str | None = None,
    lessonId: str | None = None,
    caseId: str | None = None,
    scopeKey: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    learner = effective_learner(authorization, session_cookie=session_cookie)
    _guard_pending_assessment_case(caseId, learner_id=learner)
    pending_case_ids = _pending_assessment_case_ids()
    threads = store.list_threads(
        learner,
        mode=mode,
        lesson_id=lessonId,
        case_id=caseId,
        scope_key=scopeKey,
        limit=limit,
    )
    return {
        "threads": [
            thread for thread in threads
            if str(thread.get("caseId") or "") not in pending_case_ids
            or store.has_committed_attempt(learner, str(thread.get("caseId") or ""))
        ]
    }


@app.get("/curriculum")
def curriculum(
    learnerId: str = "demo",
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    profile = store.ensure_profile(effective_learner(authorization, learnerId, session_cookie))
    # Guided curriculum completion and independently demonstrated competence
    # are different records. Use only exact, independently assessed cells for
    # the latter; legacy objective priors and formative Guided work must never
    # appear as earned mastery.
    observed: dict[str, list[float]] = {}
    for row in profile.get("subskillMastery", []):
        if int(row.get("independentAttempts") or 0) <= 0:
            continue
        observed.setdefault(str(row["concept"]), []).append(float(row["independentMastery"]))
    mastery = {
        objective: sum(values) / len(values)
        for objective, values in observed.items()
        if values
    }
    return curriculum_view(repo, mastery)


@app.get("/tutorials")
def tutorials(
    _learner: str = Depends(require_learning_account),
) -> dict[str, Any]:
    return {"frameworks": FRAMEWORKS, "tutorials": list_tutorials()}


def _guided_requirement_tokens(value: str | None, field_name: str) -> tuple[str, ...]:
    if not value:
        return ()
    tokens = tuple(dict.fromkeys(item.strip() for item in value.split(",") if item.strip()))
    if len(tokens) > 32 or any(not _GUIDED_TOKEN_RE.fullmatch(item) for item in tokens):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_guided_case_contract",
                "message": f"{field_name} contains an invalid requirement.",
            },
        )
    return tokens


def _guided_case_eligibility(
    case: dict[str, Any],
    *,
    requested_concept: str | None,
    requested_unavailable: bool,
    minimum_tier: str,
    required_leads: tuple[str, ...],
    required_measurements: tuple[str, ...],
    required_rois: tuple[str, ...],
    requires_per_beat_landmarks: bool,
) -> dict[str, Any]:
    supported = {str(item) for item in case.get("supported_objectives") or []}
    definition = OBJECTIVES.get(requested_concept or "")
    grounded = set(definition.case_concepts) if definition else set()
    target_supported = (
        requested_concept is None
        or requested_concept in supported
        or bool(grounded & supported)
    )
    tier = str(case.get("teaching_tier") or "D")
    tier_rank = {"A": 2, "B": 1, "C": 0, "D": -1}
    tier_supported = tier_rank.get(tier, -1) >= tier_rank.get(minimum_tier, 1)
    waveform_leads = {str(item) for item in (case.get("waveform") or {}).get("leads") or []}
    measurements = (case.get("ptbxl_plus") or {}).get("measurements") or {}
    fiducials = (case.get("ptbxl_plus") or {}).get("fiducials") or {}
    rois = fiducials.get("rois") or []
    roi_concepts = {
        str(roi.get("concept"))
        for roi in rois
        if isinstance(roi, dict) and roi.get("concept")
    }
    irregular_objectives = {
        "atrial_fibrillation",
        "atrial_flutter",
        "premature_atrial_complex",
        "premature_ventricular_complex",
        "av_block_second_degree_mobitz_i",
        "av_block_second_degree_mobitz_ii",
        "av_block_third_degree",
    }
    per_beat_supported = (
        not requires_per_beat_landmarks
        or not bool(supported & irregular_objectives)
        or isinstance(fiducials.get("per_beat_landmarks"), list)
    )
    checks = (
        not requested_unavailable,
        target_supported,
        tier_supported,
        set(required_leads).issubset(waveform_leads),
        all(key in measurements for key in required_measurements),
        set(required_rois).issubset(roi_concepts),
        per_beat_supported,
    )
    missing_count = sum(not check for check in checks)
    return {
        "eligible": missing_count == 0,
        "missingRequirementCount": missing_count,
        "message": (
            "This real ECG satisfies the reviewed evidence contract for the scene."
            if missing_count == 0
            else "This ECG does not satisfy every reviewed evidence requirement for this scene."
        ),
    }


def _guided_public_packet(
    case: dict[str, Any], *, case_reference: str, display_id: str
) -> dict[str, Any]:
    """Return waveform-only teaching data with no diagnosis or source lookup key."""

    packet = blind_packet(packet_for_case(case))
    packet.pop("ptbxl", None)
    packet["source"] = "audited_waveform"
    packet["waveform"] = {
        **dict(packet.get("waveform") or {}),
        "source": "audited_waveform",
    }
    quality = dict(packet.get("signal_quality") or {})
    packet["signal_quality"] = {
        "status": quality.get("status", "unknown"),
        "reasons": [],
    }
    return public_case_packet(
        packet,
        case_reference=case_reference,
        display_id=display_id,
    )


@app.get("/tutorials/{lesson_id}")
def tutorial(
    lesson_id: str,
    response: Response,
    concept: str | None = None,
    excludeCaseId: str | None = None,
    minimumTier: Literal["A", "B"] = "B",
    requiredLeads: str | None = Query(default=None, max_length=240),
    requiredMeasurements: str | None = Query(default=None, max_length=800),
    requiredRois: str | None = Query(default=None, max_length=800),
    requiresPerBeatLandmarks: bool = False,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    lesson = get_tutorial(lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Tutorial not found")
    learner = effective_learner(authorization, session_cookie=session_cookie)
    requested_concept = concept if concept in CONCEPT_BY_ID else lesson.get("caseConcept")
    excluded_case_id: str | None = None
    if excludeCaseId:
        if is_ecg_capability(excludeCaseId):
            excluded_case_id = _resolve_guided_case_reference(
                learner, lesson_id, excludeCaseId
            )
            if excluded_case_id is None:
                raise HTTPException(status_code=404, detail="Guided ECG not found")
        else:
            # Backward compatibility for non-learner internal callers. Learner
            # responses never disclose this value after the capability rollout.
            excluded_case_id = excludeCaseId
    excluded = ({excluded_case_id} if excluded_case_id else set()) | _pending_assessment_case_ids()
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
    selected_case = repo.get_case(str(selected["caseId"])) if selected else None
    if selected_case is None:
        raise HTTPException(status_code=409, detail="No non-pending Guided case is available")
    # The response below contains the Guided answer packet. Commit its
    # owner-bound, answer-free exposure before releasing that packet so an
    # immediate Training/Rapid/Clinical selector cannot call the tracing
    # "unseen". BEGIN IMMEDIATE serializes duplicate GET deliveries around the
    # ledger helper's bounded idempotency generation.
    with store.connect() as conn:
        if not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE")
        record_guided_packet_exposure(
            conn,
            owner_id=learner,
            lesson_id=lesson_id,
            ecg_id=str(selected["caseId"]),
            occurred_at=datetime.now(UTC),
        )
    guided_context = _guided_context_token(
        learner,
        str(selected["caseId"]),
        lesson_id,
    )
    case_reference = _guided_case_reference(
        learner,
        lesson_id,
        str(selected["caseId"]),
    )
    display_id = "Guided teaching ECG"
    public_summary = blind_summary(selected)
    public_summary["source"] = "audited_waveform"
    public_summary = public_case_summary(
        public_summary,
        case_reference=case_reference,
        display_id=display_id,
    )
    requested_unavailable = bool(selection.get("requestedConceptUnavailable"))
    guided_eligibility = _guided_case_eligibility(
        selected_case,
        requested_concept=requested_concept,
        requested_unavailable=requested_unavailable,
        minimum_tier=minimumTier,
        required_leads=_guided_requirement_tokens(requiredLeads, "requiredLeads"),
        required_measurements=_guided_requirement_tokens(
            requiredMeasurements, "requiredMeasurements"
        ),
        required_rois=_guided_requirement_tokens(requiredRois, "requiredRois"),
        requires_per_beat_landmarks=requiresPerBeatLandmarks,
    )
    public_selection = {
        "requestedConceptUnavailable": requested_unavailable,
        "excludedBorderlineCount": len(selection.get("exemplarRejections") or []),
        "reason": (
            "A contrast ECG was selected because no eligible target exemplar is available."
            if requested_unavailable
            else "An eligible teaching ECG was selected without disclosing its answer labels."
        ),
    }
    return {
        "lesson": lesson,
        "frameworks": FRAMEWORKS,
        "recommendedCase": public_summary,
        # Guided receives only waveform-safe presentation fields. Exact
        # geometry and measurement correctness cross the boundary one learner
        # commitment at a time through the owner-bound grading context.
        "recommendedPacket": _guided_public_packet(
            selected_case,
            case_reference=case_reference,
            display_id=display_id,
        ),
        "guidedContext": guided_context,
        "guidedEligibility": guided_eligibility,
        "selection": public_selection,
        "assessmentPrivacy": {
            "opaqueEcgReference": True,
            "answerFieldsWithheldUntilCommit": True,
            "sourceRecordIdentityWithheld": True,
        },
        "openingPrompt": f"Inspect the tracing and justify {', '.join(concept_label(item) for item in lesson['objectives'][:3])} using visible ECG evidence.",
    }


@app.get("/tutorials/{lesson_id}/waveform/{case_ref}")
def guided_waveform(
    lesson_id: str,
    case_ref: str,
    response: Response,
    leads: str | None = Query(default=None, max_length=120),
    start: float = Query(default=0, ge=0),
    end: float | None = Query(default=None, ge=0),
    maxPoints: int = Query(default=1200, ge=100, le=5000),
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    learner = effective_learner(authorization, session_cookie=session_cookie)
    canonical_id = _resolve_guided_case_reference(learner, lesson_id, case_ref)
    if canonical_id is None:
        raise HTTPException(status_code=404, detail="Guided ECG not found")
    case = _learner_case_or_404(canonical_id)
    lead_list = [lead.strip() for lead in leads.split(",")] if leads else None
    if lead_list and (
        len(lead_list) > 12
        or any(not lead or len(lead) > 8 for lead in lead_list)
    ):
        raise HTTPException(status_code=422, detail="Invalid waveform lead selection")
    waveform = repo.get_waveform_window(
        str(case["case_id"]),
        leads=lead_list,
        start=start,
        end=end,
        max_points=maxPoints,
    )
    if not waveform:
        raise HTTPException(status_code=404, detail="Guided ECG not found")
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["Vary"] = "Authorization, Cookie"
    return public_waveform(waveform, case_reference=case_ref)


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
    Keeps waveform data/metadata, a raw median beat, demographics, and signal
    quality. Measurements, derived features, fiducial targets, statements, and
    per-lead computed values are answer-bearing and remain server-side until a
    durable submission or a signed Guided context."""
    plus = dict(packet.get("ptbxl_plus") or {})
    ptbxl = packet.get("ptbxl") or {}
    return {
        "case_id": packet["case_id"],
        "display_id": packet.get("display_id"),
        "clinical_stem": "",
        "source": packet.get("source", "unknown"),
        "waveform": packet["waveform"],
        "ptbxl": {"fold": ptbxl.get("fold"), "metadata": {"age": (ptbxl.get("metadata") or {}).get("age"),
                                                            "sex": (ptbxl.get("metadata") or {}).get("sex")}},
        "ptbxl_plus": {
            "features": {},
            "measurements": {},
            "fiducials": {"rois": []},
            "median_beats": plus.get("median_beats", {}),
            "per_lead_st_mv": {},
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
    redacted["clinicalStem"] = ""
    redacted["blinded"] = True
    return redacted


# --- Clinical Decisions mode wiring -----------------------------------------------
from .clinical.provenance import assert_serving_bank_provenance  # noqa: E402
from .clinical.real_items import vetted_real_items  # noqa: E402
from .clinical_routes import build_clinical_router  # noqa: E402
from .rapid_routes import build_rapid_router  # noqa: E402
from .training_routes import TrainingPoolResolver, build_training_router  # noqa: E402
from .training_store import TrainingCampaignStore  # noqa: E402
from .store.clinical_item_store import ClinicalItemStore  # noqa: E402

clinical_item_store = ClinicalItemStore(settings.sqlite_path)
training_campaign_store = TrainingCampaignStore(settings.sqlite_path, store.connect)
training_pool_resolver = TrainingPoolResolver(repo)
_training_pool_receipt_available = training_pool_resolver.has_durable_exact_target


def clinical_packet(ecg_id: str) -> dict[str, Any] | None:
    """Resolve Clinical ECGs with server-only identity for pair authentication."""
    case = repo.get_case(ecg_id)
    if not case:
        return None
    packet = packet_for_case(case)
    # These fields never enter the learner packet projection. They exist here
    # solely so the Clinical provenance gate can prove that comparison ECGs are
    # distinct, same-patient, same-release, and chronologically ordered.
    packet["record_identity"] = case.get("record_identity", {})
    packet["source_provenance"] = case.get("source_provenance", {})
    return packet


# The learner bank is code-defined, real-ECG-backed, and automatically screened.
# It is formative content, not clinician-reviewed. Publish the full replacement
# in one transaction so multiple workers never expose a clear/partial bank.
clinical_item_store.replace_items_atomically(vetted_real_items(clinical_packet))
assert_serving_bank_provenance(clinical_item_store.iter_items(), clinical_packet)


app.include_router(
    build_clinical_router(
        store,
        clinical_item_store,
        clinical_packet,
        effective_learner,
        repo.get_waveform_window,
    )
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
        training_pool_resolver,
    )
)

# Registered after learner routers so readiness describes the fully initialized
# repository and learner store.
from .ops import build_ops_router  # noqa: E402

app.include_router(build_ops_router(settings, repo, store, clinical_item_store))
