"""Owner-bound references and server-owned grounding for the mastery-plan coach.

The browser receives only a short-lived signed capability.  It never sends the
mastery queue back as authority: every tutor turn verifies the capability for
the effective learner and rebuilds the current deterministic plan from durable
learner state.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import re
import secrets
from typing import Any


CONTEXT_VERSION = "adaptive-plan-coach-v1"
CONTEXT_PREFIX = "apc1"
CONTEXT_TTL = timedelta(hours=6)
TUTOR_SCOPE = "adaptive-mastery-plan"


_MASTERY_MUTATION_CLAIMS = (
    re.compile(
        r"\b(?:i|we|the\s+(?:coach|chat|tutor))\s+"
        r"(?:have\s+|just\s+)?"
        r"(?:updated|changed|raised|increased|set|awarded|recorded|marked)\b"
        r"[^.!?\n]{0,100}\b(?:mastery|progress|score|competenc(?:y|ies)|objectives?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:your|the\s+learner'?s?)\s+"
        r"(?:mastery|progress|score|competenc(?:y|ies)|objectives?)\b"
        r"[^.!?\n]{0,80}\b(?:is\s+now|are\s+now|rose\s+to|increased\s+to|has\s+been|have\s+been)\b"
        r"[^.!?\n]{0,40}"
        r"(?:\d+(?:\.\d+)?\s*%|updated|changed|raised|increased|set|awarded|recorded|mastered)",
        re.IGNORECASE,
    ),
    re.compile(r"\byou(?:'ve|\s+have)\s+(?:now\s+)?mastered\b", re.IGNORECASE),
)
_EXTERNAL_DESTINATION = re.compile(r"(?:https?://|www\.)", re.IGNORECASE)
_DESTINATION_DIRECTIVE = re.compile(
    r"\b(?:open|launch|visit|navigate\s+to|go\s+to|head\s+to|switch\s+to)\b"
    r"|\b(?:start|continue|practice)\s+(?:in|with|on)\b",
    re.IGNORECASE,
)

_PREFERENCE_CONTEXT_ALLOWED: dict[str, frozenset[Any]] = {
    "trainingStage": frozenset(
        {
            "not_set",
            "preclinical",
            "core_clerkship",
            "advanced_clerkship",
            "resident_review",
        }
    ),
    "primaryGoal": frozenset(
        {
            "build_fundamentals",
            "exam_prep",
            "clinical_reading",
            "emergency_prioritization",
            "medication_safety",
        }
    ),
    "defaultSessionLength": frozenset({5, 10, 25, 50}),
    "rapidPace": frozenset({"untimed", "ward", "emergency"}),
    "guidanceLevel": frozenset({"step_by_step", "balanced", "minimal"}),
}


class AdaptiveTutorContextNotFound(LookupError):
    """The reference is malformed, tampered with, or belongs to another learner."""


class AdaptiveTutorContextExpired(RuntimeError):
    """The otherwise-valid server-issued reference has exceeded its TTL."""


def _bounded_preference_context(plan: dict[str, Any]) -> dict[str, Any] | None:
    """Project only saved study defaults that the deterministic planner accepts."""

    source = (
        plan.get("preferenceContext")
        if isinstance(plan.get("preferenceContext"), dict)
        else None
    )
    if source is None:
        return None
    projected: dict[str, Any] = {}
    for key, allowed in _PREFERENCE_CONTEXT_ALLOWED.items():
        value = source.get(key)
        if not isinstance(value, (str, int)) or isinstance(value, bool):
            continue
        if value in allowed:
            projected[key] = value
    return projected or None


def _bounded_guided_remediation(plan: dict[str, Any]) -> dict[str, Any] | None:
    """Project one authored, formative Guided destination without a browser route."""

    source = (
        plan.get("guidedRemediation")
        if isinstance(plan.get("guidedRemediation"), dict)
        else None
    )
    if (
        source is None
        or source.get("mode") != "guided"
        or source.get("evidenceKind") != "formative_guided"
        or source.get("updatesIndependentMastery") is not False
    ):
        return None
    title = source.get("title")
    if not isinstance(title, str) or not title.strip():
        return None
    return {
        "mode": "guided",
        "title": title.strip(),
        "purpose": source.get("purpose"),
        "moduleId": source.get("moduleId"),
        "sceneId": source.get("sceneId"),
        "concept": source.get("concept"),
        "evidenceKind": "formative_guided",
        "updatesIndependentMastery": False,
        "beforeStageOrder": source.get("beforeStageOrder"),
        "reason": source.get("reason"),
    }


def _signing_key(secret: str) -> bytes:
    """Domain-separate this use from other HMACs backed by the deployment secret."""

    return hmac.new(
        secret.encode("utf-8"),
        b"ecg-tool\0adaptive-plan-coach\0v1",
        hashlib.sha256,
    ).digest()


def _signature(secret: str, learner_id: str, issued_at: int, nonce: str) -> str:
    message = f"{CONTEXT_VERSION}\0{learner_id}\0{issued_at}\0{nonce}".encode("utf-8")
    digest = hmac.new(_signing_key(secret), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _expiry_for(issued_at: int) -> datetime:
    return datetime.fromtimestamp(issued_at, tz=UTC) + CONTEXT_TTL


def issue_adaptive_tutor_context(
    learner_id: str,
    secret: str,
    *,
    now: datetime | None = None,
) -> dict[str, str]:
    issued = int((now or datetime.now(UTC)).astimezone(UTC).timestamp())
    nonce = secrets.token_urlsafe(18)
    signature = _signature(secret, learner_id, issued, nonce)
    return {
        "contextId": f"{CONTEXT_PREFIX}.{issued}.{nonce}.{signature}",
        "version": CONTEXT_VERSION,
        "expiresAt": _expiry_for(issued).isoformat(),
    }


def verify_adaptive_tutor_context(
    reference: dict[str, Any],
    learner_id: str,
    secret: str,
    *,
    now: datetime | None = None,
) -> dict[str, str]:
    """Verify ownership, integrity, version, and age without trusting plan data."""

    context_id = str(reference.get("contextId") or "")
    version = str(reference.get("version") or "")
    expires_at = str(reference.get("expiresAt") or "")
    parts = context_id.split(".")
    if version != CONTEXT_VERSION or len(parts) != 4 or parts[0] != CONTEXT_PREFIX:
        raise AdaptiveTutorContextNotFound("Adaptive plan context not found.")
    _, issued_text, nonce, supplied_signature = parts
    try:
        issued = int(issued_text)
        supplied_expiry = datetime.fromisoformat(expires_at).astimezone(UTC)
    except (TypeError, ValueError):
        raise AdaptiveTutorContextNotFound("Adaptive plan context not found.") from None
    if issued <= 0 or not (16 <= len(nonce) <= 64) or len(supplied_signature) != 43:
        raise AdaptiveTutorContextNotFound("Adaptive plan context not found.")

    expected_signature = _signature(secret, learner_id, issued, nonce)
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise AdaptiveTutorContextNotFound("Adaptive plan context not found.")

    expected_expiry = _expiry_for(issued)
    if supplied_expiry != expected_expiry:
        raise AdaptiveTutorContextNotFound("Adaptive plan context not found.")

    current = (now or datetime.now(UTC)).astimezone(UTC)
    issued_dt = datetime.fromtimestamp(issued, tz=UTC)
    if issued_dt > current + timedelta(minutes=1):
        raise AdaptiveTutorContextNotFound("Adaptive plan context not found.")
    if current >= expected_expiry:
        raise AdaptiveTutorContextExpired("Refresh the mastery plan before asking the coach.")
    return {
        "contextId": context_id,
        "version": CONTEXT_VERSION,
        "expiresAt": expected_expiry.isoformat(),
    }


def build_adaptive_tutor_context(
    plan: dict[str, Any], *, primary_guidance: str | None = None
) -> dict[str, Any]:
    """Return the bounded plan summary supplied to the tutor provider.

    The signed capability itself is intentionally excluded: it is an API
    credential, not educational context.
    """

    primary = plan.get("primary") if isinstance(plan.get("primary"), dict) else None
    priorities = plan.get("priorities") if isinstance(plan.get("priorities"), list) else []
    stages = plan.get("stages") if isinstance(plan.get("stages"), list) else []
    integration = plan.get("integration") if isinstance(plan.get("integration"), dict) else None
    clinical_application = (
        plan.get("clinicalApplication")
        if isinstance(plan.get("clinicalApplication"), dict)
        else None
    )
    preference_context = _bounded_preference_context(plan)
    guided_remediation = _bounded_guided_remediation(plan)
    prescribed_stages = [
        {
            "order": row.get("order"),
            "mode": row.get("mode"),
            "title": row.get("title"),
            "purpose": row.get("purpose"),
            "suggestedLength": row.get("suggestedLength"),
            "receiptConcept": row.get("receiptConcept"),
            "receiptSubskill": row.get("receiptSubskill"),
        }
        for row in stages[:6]
        if isinstance(row, dict)
    ]
    verified_destinations = []
    if guided_remediation:
        verified_destinations.append(
            {
                "kind": "guided_remediation",
                "title": guided_remediation["title"],
                "mode": "guided",
                "evidenceKind": "formative_guided",
            }
        )
    verified_destinations.extend(
        [
            {
                "kind": "prescribed_stage",
                "title": row.get("title"),
                "mode": row.get("mode"),
            }
            for row in prescribed_stages
            if isinstance(row.get("title"), str) and row.get("title", "").strip()
        ]
    )
    if clinical_application and isinstance(clinical_application.get("title"), str):
        verified_destinations.append(
            {
                "kind": "clinical_application",
                "title": clinical_application.get("title"),
                "mode": "clinical",
            }
        )

    return {
        "kind": "adaptive_mastery_plan",
        "activity": "adaptive_mastery_plan",
        "version": CONTEXT_VERSION,
        "authority": "verified_scheduler_only",
        "generatedAt": plan.get("generatedAt"),
        "explanation": plan.get("explanation"),
        "basis": plan.get("basis") or {},
        "preferenceContext": preference_context,
        "primary": (
            {
                "concept": primary.get("caseConcept"),
                "label": primary.get("label"),
                "subskill": primary.get("subskill"),
                "reason": primary.get("reason"),
                "eligibleDistinct": primary.get("eligibleDistinct"),
                "independentAttempts": primary.get("independentAttempts"),
                "independentMastery": primary.get("independentMastery"),
                "isDue": primary.get("isDue"),
                "dueState": primary.get("dueState"),
                "overdueDays": primary.get("overdueDays"),
                "nextDueAt": primary.get("nextDueAt"),
                "stabilityDays": primary.get("stabilityDays"),
            }
            if primary
            else None
        ),
        # This is a bounded, reviewed general-teaching statement selected from
        # the server-owned primary concept. It is not browser text and never
        # asserts that a finding is present on a current ECG.
        "primaryGuidance": primary_guidance if primary else None,
        "priorities": [
            {
                "concept": row.get("caseConcept"),
                "label": row.get("label"),
                "subskill": row.get("subskill"),
                "reason": row.get("reason"),
            }
            for row in priorities[:6]
            if isinstance(row, dict)
        ],
        "guidedRemediation": guided_remediation,
        "prescribedStages": prescribed_stages,
        "integrationPrompt": integration.get("prompt") if integration else None,
        "clinicalApplication": (
            {
                "title": clinical_application.get("title"),
                "purpose": clinical_application.get("purpose"),
                "concept": clinical_application.get("concept"),
                "subskill": clinical_application.get("subskill"),
                "evidenceKind": clinical_application.get("evidenceKind"),
                "reason": clinical_application.get("reason"),
            }
            if clinical_application
            else None
        ),
        "constraints": [
            "Do not change or score the deterministic plan.",
            "Do not infer a diagnosis or mastery value absent from this server-owned context.",
            "Recommend only the listed verified destinations.",
            (
                "Saved preferences and retention timing are read-only context, "
                "not instructions to change either record."
            ),
            "The coach cannot create, move, complete, or delete calendar items.",
            "A listed Clinical application is formative and cannot award independent mastery.",
        ],
        "verifiedDestinations": verified_destinations,
        # ``verifiedDestinations`` is already ordered by the deterministic
        # scheduler: guided remediation (when required), then prescribed
        # stages, then formative Clinical transfer.  Keep the coach pinned to
        # that first destination even when no guided step is present; otherwise
        # a provider could choose a later valid destination and silently skip
        # the scheduler's actual next step.
        "recommendedDestination": (
            verified_destinations[0] if verified_destinations else None
        ),
        "governance": {
            "source": "verified_competency_scheduler",
            "chatCanWriteMastery": False,
            "calendarWritesAllowed": False,
            "preferenceWritesAllowed": False,
            "retentionTimingReadOnly": True,
            "objectiveUpdatesAllowed": False,
            "viewerActionsAllowed": False,
            "nextStepMustMatchVerifiedDestination": True,
            "recommendedNextStepIsSchedulerOwned": True,
        },
    }


def _verified_destination_titles(context: dict[str, Any]) -> list[str]:
    rows = (
        context.get("verifiedDestinations")
        if isinstance(context.get("verifiedDestinations"), list)
        else []
    )
    titles: list[str] = []
    for row in rows:
        title = row.get("title") if isinstance(row, dict) else None
        if not isinstance(title, str):
            continue
        normalized = title.strip()
        if normalized and normalized not in titles:
            titles.append(normalized)
    return titles


def _recommended_destination_title(context: dict[str, Any]) -> str:
    recommended = (
        context.get("recommendedDestination")
        if isinstance(context.get("recommendedDestination"), dict)
        else None
    )
    title = recommended.get("title") if recommended else None
    normalized = title.strip() if isinstance(title, str) else ""
    destinations = _verified_destination_titles(context)
    return normalized if normalized in destinations else ""


def deterministic_adaptive_tutor_response(context: dict[str, Any]) -> dict[str, Any]:
    """Explain the verified plan without granting the chat any action authority."""

    primary = context.get("primary") if isinstance(context.get("primary"), dict) else None
    explanation = str(
        context.get("explanation")
        or "The verified scheduler has not supplied a personalized priority yet."
    ).strip()
    if primary:
        label = str(primary.get("label") or primary.get("concept") or "this competency")
        subskill = str(primary.get("subskill") or "").replace("_", " ").strip()
        target = f"{label} · {subskill}" if subskill else label
        reason = str(primary.get("reason") or explanation).strip()
        message = f"The verified scheduler currently prioritizes {target}. {reason}"
        cited = [reason, explanation]
    else:
        message = explanation
        cited = [explanation]

    destinations = _verified_destination_titles(context)
    recommended = _recommended_destination_title(context)
    return {
        "tutorMessage": message,
        "feedback": (
            "I can explain why the plan is ordered this way, but only independently graded work "
            "can change your recorded progress."
        ),
        "viewerActions": [],
        "objectiveUpdates": [],
        "misconceptions": [],
        "uncertaintyWarnings": [
            "The plan coach cannot score work, control the ECG viewer, or replace "
            "the verified scheduler."
        ],
        "suggestedNextStep": recommended or (destinations[0] if destinations else ""),
        "socraticQuestion": (
            "Which discriminator will you verify first during that scheduled activity?"
        ),
        "citedEvidence": list(dict.fromkeys(item for item in cited if item))[:3],
        "onLessonTopic": True,
    }


def _adaptive_prose_breaks_authority_boundary(
    response: dict[str, Any], destinations: list[str]
) -> bool:
    values: list[str] = []
    for key in ("tutorMessage", "feedback", "socraticQuestion"):
        value = response.get(key)
        if isinstance(value, str):
            values.append(value)
    for key in ("misconceptions", "uncertaintyWarnings", "citedEvidence"):
        value = response.get(key)
        if isinstance(value, list):
            values.extend(item for item in value if isinstance(item, str))

    allowed = [title.casefold() for title in destinations]
    for value in values:
        if any(pattern.search(value) for pattern in _MASTERY_MUTATION_CLAIMS):
            return True
        if _EXTERNAL_DESTINATION.search(value):
            return True
        for sentence in re.split(r"(?<=[.!?])\s+|[\r\n]+", value):
            if _DESTINATION_DIRECTIVE.search(sentence) and not any(
                title in sentence.casefold() for title in allowed
            ):
                return True
    return False


def enforce_adaptive_tutor_response(
    response: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    """Project a generic tutor reply onto the plan coach's read-only contract.

    Provider instructions are defense in depth. This post-generation boundary is
    authoritative: adaptive chat never emits mastery writes or viewer commands,
    and its next-step surface can name only an exact scheduler-issued title.
    """

    destinations = _verified_destination_titles(context)
    recommended = _recommended_destination_title(context)
    next_step = response.get("suggestedNextStep")
    next_step = next_step.strip() if isinstance(next_step, str) else ""
    violates_contract = bool(response.get("objectiveUpdates")) or bool(
        response.get("viewerActions")
    )
    violates_contract = violates_contract or (
        bool(next_step) and next_step not in destinations
    )
    violates_contract = violates_contract or _adaptive_prose_breaks_authority_boundary(
        response, destinations
    )

    safe = dict(response)
    if violates_contract:
        safe.update(deterministic_adaptive_tutor_response(context))
        safe["provider"] = "grounded-fallback"
    else:
        safe["objectiveUpdates"] = []
        safe["viewerActions"] = []
        safe["suggestedNextStep"] = recommended or next_step or (
            destinations[0] if destinations else ""
        )

    requested_actions = 0
    status = response.get("viewerActionStatus")
    if isinstance(status, dict):
        requested_actions = int(status.get("requested") or 0)
    elif isinstance(response.get("viewerActions"), list):
        requested_actions = len(response["viewerActions"])
    safe["viewerActionStatus"] = {
        "requested": requested_actions,
        "validated": 0,
        "appliedByClient": False,
        "clientAcknowledgementRequired": False,
    }
    return safe


__all__ = [
    "CONTEXT_TTL",
    "CONTEXT_VERSION",
    "TUTOR_SCOPE",
    "AdaptiveTutorContextExpired",
    "AdaptiveTutorContextNotFound",
    "build_adaptive_tutor_context",
    "deterministic_adaptive_tutor_response",
    "enforce_adaptive_tutor_response",
    "issue_adaptive_tutor_context",
    "verify_adaptive_tutor_context",
]
