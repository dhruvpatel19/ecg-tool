"""Deterministic spaced-retention policy for exact concept × subskill evidence.

This is intentionally smaller and more auditable than a black-box mastery model.
Only independently completed, server-verified real ECG events enter this state
machine. Formative work can improve the separate formative score, but it cannot
move a due date, increase stability, or erase a lapse.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


INITIAL_STABILITY_DAYS = 1.0
MINIMUM_STABILITY_DAYS = 0.5
DURABLE_STABILITY_DAYS = 7.0
DURABLE_SPACED_RETRIEVALS = 3
DURABLE_DISTINCT_SUCCESSFUL_ECGS = 3


def parse_instant(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def iso_instant(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


@dataclass(frozen=True)
class RetentionUpdate:
    stability_days: float
    next_due_at: str
    lapses: int
    spaced_retrievals: int
    last_independent_at: str
    last_independent_correct: bool
    interval_expanded: bool


def update_retention(
    current: dict[str, Any],
    *,
    correct: bool,
    occurred_at: datetime,
) -> RetentionUpdate:
    """Apply one eligible independent retrieval to the retention schedule.

    Repeating an item before it is due does not expand its interval. A correct
    retrieval at or after the due instant approximately doubles stability, with
    a small bounded reward for a delayed successful retrieval. A lapse contracts
    stability to 35% and schedules a near-term retry.
    """

    now = (parse_instant(occurred_at) or occurred_at).astimezone(UTC)
    stability = max(0.0, float(current.get("stabilityDays") or 0.0))
    lapses = max(0, int(current.get("lapses") or 0))
    spaced = max(0, int(current.get("spacedRetrievals") or 0))
    due = parse_instant(current.get("nextDueAt"))
    expanded = False

    if correct:
        if stability <= 0.0 or due is None:
            stability = INITIAL_STABILITY_DAYS
            due = now + timedelta(days=stability)
        elif now >= due:
            overdue_days = max(0.0, (now - due).total_seconds() / 86400.0)
            lateness_ratio = overdue_days / max(stability, MINIMUM_STABILITY_DAYS)
            growth = min(3.0, 2.0 + 0.15 * lateness_ratio)
            stability = max(stability + 1.0, stability * growth)
            due = now + timedelta(days=stability)
            spaced += 1
            expanded = True
        # Early repetition leaves both stability and the existing due date alone.
    else:
        lapses += 1
        stability = max(MINIMUM_STABILITY_DAYS, stability * 0.35)
        due = now + timedelta(days=stability)

    return RetentionUpdate(
        stability_days=round(stability, 3),
        next_due_at=iso_instant(due),
        lapses=lapses,
        spaced_retrievals=spaced,
        last_independent_at=iso_instant(now),
        last_independent_correct=correct,
        interval_expanded=expanded,
    )


def due_snapshot(row: dict[str, Any], *, as_of: datetime) -> dict[str, Any]:
    """Return learner-facing due state and a stable scheduler priority.

    Priority sorts due/overdue retrievals first, then unseen competencies, then
    competencies that are safely scheduled in the future. More overdue material
    sorts before newly-due material.
    """

    now = (parse_instant(as_of) or as_of).astimezone(UTC)
    due = parse_instant(row.get("nextDueAt"))
    independent_attempts = int(row.get("independentAttempts") or 0)
    if due is None or independent_attempts == 0:
        return {
            "dueState": "unseen",
            "isDue": False,
            "overdueDays": 0.0,
            "daysUntilDue": None,
            "duePriority": (1, 0.0),
        }

    delta_days = (due - now).total_seconds() / 86400.0
    if delta_days <= 0:
        overdue_days = abs(delta_days)
        state = "overdue" if overdue_days >= 1.0 else "due"
        return {
            "dueState": state,
            "isDue": True,
            "overdueDays": round(overdue_days, 3),
            "daysUntilDue": round(delta_days, 3),
            "duePriority": (0, -overdue_days),
        }
    return {
        "dueState": "scheduled",
        "isDue": False,
        "overdueDays": 0.0,
        "daysUntilDue": round(delta_days, 3),
        "duePriority": (2, delta_days),
    }


def durable_retention(row: dict[str, Any]) -> bool:
    return (
        float(row.get("stabilityDays") or 0.0) >= DURABLE_STABILITY_DAYS
        and int(row.get("spacedRetrievals") or 0) >= DURABLE_SPACED_RETRIEVALS
        and int(row.get("distinctSuccessfulEcgs") or 0) >= DURABLE_DISTINCT_SUCCESSFUL_ECGS
        and bool(row.get("lastIndependentCorrect"))
    )


def competency_state(row: dict[str, Any] | None) -> str:
    """Learner-facing state with a hard retention gate on ``durable``."""

    if not row or int(row.get("attempts", 0)) == 0:
        return "unseen"
    independent = float(row.get("independentMastery", 0.15))
    if independent < 0.35:
        return "acquiring"
    if independent < 0.6:
        return "developing"
    if independent < 0.8 or int(row.get("independentAttempts", 0)) < 3:
        return "consolidating"
    return "durable" if durable_retention(row) else "consolidating"


def retention_uncertainty(row: dict[str, Any], *, as_of: datetime) -> str | None:
    independent_attempts = int(row.get("independentAttempts") or 0)
    distinct = int(row.get("distinctSuccessfulEcgs") or 0)
    spaced = int(row.get("spacedRetrievals") or 0)
    if independent_attempts == 0:
        return "No independent evidence has been recorded."
    if int(row.get("distinctEligibleEcgs") or 0) == 0:
        return "No independent retrieval has been verified against a real eligible ECG."
    if not bool(row.get("lastIndependentCorrect")):
        return "The latest verified independent retrieval was a lapse; review is due."
    if distinct < DURABLE_DISTINCT_SUCCESSFUL_ECGS:
        remaining = DURABLE_DISTINCT_SUCCESSFUL_ECGS - distinct
        return f"Needs success on {remaining} more distinct real ECG{'s' if remaining != 1 else ''}."
    if spaced < DURABLE_SPACED_RETRIEVALS:
        remaining = DURABLE_SPACED_RETRIEVALS - spaced
        return f"Needs {remaining} more successful due-date retrieval{'s' if remaining != 1 else ''}."
    snapshot = due_snapshot(row, as_of=as_of)
    if snapshot["dueState"] == "overdue":
        return "Retention evidence is overdue for re-checking."
    if snapshot["dueState"] == "due":
        return "A retention check is due now."
    if float(row.get("stabilityDays") or 0.0) < DURABLE_STABILITY_DAYS:
        return "The current successful-retrieval interval is still consolidating."
    return None
