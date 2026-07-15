"""Fail-closed compatibility surface for deprecated rapid-review sessions.

The original Review API selected and counted a case as soon as ``/next`` was
called, while the actual answer was submitted separately through ``/attempts``.
There was no server-owned lease connecting those operations. A caller could
therefore skip cases, and the session could describe mastery progress that its
own workflow had not established.

The canonical learner flow is now the due-first plan at ``GET /adaptive/plan``;
its recommended Training, Rapid, and Clinical activities own their assessment
lifecycles and evidence. Historical Review sessions remain readable for account
compatibility, but this module never creates, serves, advances, or scores them.
"""

from __future__ import annotations

from typing import Any

from .storage import LearningStore


LEGACY_REVIEW_REPLACEMENT = {"method": "GET", "path": "/adaptive/plan"}


def legacy_review_deprecation() -> dict[str, Any]:
    """Return a fresh API-safe deprecation payload."""

    return {
        "code": "legacy_review_deprecated",
        "message": (
            "Legacy Review cannot safely associate its separately submitted answers "
            "with the case it served. Open the adaptive plan for evidence-tracked "
            "Training, Rapid, and Clinical recommendations."
        ),
        "replacement": dict(LEGACY_REVIEW_REPLACEMENT),
    }


def start_review(
    repo: Any,
    store: LearningStore,
    learner_id: str,
    concept_id: str | None = None,
    group_id: str | None = None,
    objectives: list[str] | None = None,
    target_mastery: float = 0.8,
    max_cases: int = 30,
) -> dict[str, Any]:
    """Reject new legacy sessions without writing learner or session state."""

    # Retain the historical call signature for internal compatibility while
    # deliberately refusing to infer progress from unbound /attempts records.
    del repo, store, learner_id, concept_id, group_id, objectives, target_mastery, max_cases
    return {"error": legacy_review_deprecation(), "deprecated": True}


def review_status(
    repo: Any, store: LearningStore, session_id: str
) -> dict[str, Any] | None:
    """Expose a non-mutating historical snapshot without a mastery claim."""

    del repo
    session = store.get_review_session(session_id)
    if not session:
        return None
    historical_status = str(session.get("status") or "unknown")
    return {
        "session": {
            **session,
            "legacyStatus": historical_status,
            "status": "deprecated",
        },
        "casesDone": len(session.get("served") or []),
        "case": None,
        "done": True,
        "deprecated": True,
        "readOnly": True,
        "reason": legacy_review_deprecation()["message"],
        "replacement": dict(LEGACY_REVIEW_REPLACEMENT),
    }


def next_review_case(
    repo: Any, store: LearningStore, session_id: str
) -> dict[str, Any] | None:
    """Never serve or advance a legacy session; return its read-only snapshot."""

    return review_status(repo, store, session_id)
