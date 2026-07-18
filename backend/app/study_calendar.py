"""Learner-owned study calendar with evidence-safe retention projection.

Calendar items record a learner's intention to study.  They never mutate the
spaced-retention schedule: only verified independent learning events may move a
competency's ``next_due_at`` value.  Live review dates are therefore projected
from ``subskill_mastery`` on every read instead of copied into appointment rows.
"""

from __future__ import annotations

import sqlite3
import uuid
import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .objectives import objective_definition
from .rapid_rhythm_supplement import RUNTIME_OBJECTIVE_IDS
from .retention import due_snapshot, parse_instant


CALENDAR_VERSION = "study-calendar-v1"
MAX_CALENDAR_RANGE_DAYS = 42
_CALENDAR_PLAN_ACTION_VERSION = "calendar-plan-action-v1"
_CALENDAR_MODES = {"guided", "train", "rapid", "clinical"}


class CalendarItemNotFoundError(LookupError):
    """The requested item is absent or belongs to another learner."""


class CalendarItemConflictError(RuntimeError):
    """A retry conflicts with an existing mutation or a stale revision."""

    def __init__(self, code: str, message: str, current: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.current = current


class CalendarSourceChangedError(RuntimeError):
    """The exact competency due cycle changed before it was scheduled."""

    def __init__(self, current_due_at: str | None):
        super().__init__("The competency review timing changed before it was scheduled.")
        self.current_due_at = current_due_at


def validate_time_zone(value: str) -> str:
    cleaned = value.strip()
    if not cleaned or len(cleaned) > 64:
        raise ValueError("timeZone must be a valid IANA time zone")
    try:
        ZoneInfo(cleaned)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("timeZone must be a valid IANA time zone") from exc
    return cleaned


def validate_calendar_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Calendar dates must use YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise ValueError("Calendar dates must use YYYY-MM-DD")
    return value


def validate_calendar_range(start_date: str, end_date: str) -> tuple[date, date]:
    start = date.fromisoformat(validate_calendar_date(start_date))
    end = date.fromisoformat(validate_calendar_date(end_date))
    if end < start:
        raise ValueError("endDate must not be before startDate")
    if (end - start).days + 1 > MAX_CALENDAR_RANGE_DAYS:
        raise ValueError(
            f"Calendar ranges may include at most {MAX_CALENDAR_RANGE_DAYS} days"
        )
    return start, end


def _settings_dict(
    row: sqlite3.Row | None,
    *,
    requested_time_zone: str | None = None,
) -> dict[str, Any]:
    if row is not None:
        effective_zone = str(row["time_zone"])
    elif requested_time_zone is not None:
        effective_zone = validate_time_zone(requested_time_zone)
    else:
        effective_zone = "UTC"
    saved = row is not None
    return {
        "timeZone": effective_zone,
        "weekStartsOn": int(row["week_starts_on"]) if row is not None else 0,
        "saved": saved,
        "updatedAt": str(row["updated_at"]) if row is not None else None,
    }


def get_calendar_settings(
    conn: sqlite3.Connection,
    learner_id: str,
    *,
    requested_time_zone: str | None = None,
) -> dict[str, Any]:
    row = conn.execute(
        "SELECT time_zone, week_starts_on, updated_at "
        "FROM learner_calendar_settings WHERE learner_id = ?",
        (learner_id,),
    ).fetchone()
    return _settings_dict(row, requested_time_zone=requested_time_zone)


def save_calendar_settings(
    conn: sqlite3.Connection,
    learner_id: str,
    *,
    time_zone: str,
    week_starts_on: int,
    now: str,
) -> dict[str, Any]:
    zone = validate_time_zone(time_zone)
    if week_starts_on not in {0, 1}:
        raise ValueError("weekStartsOn must be 0 or 1")
    conn.execute(
        "INSERT INTO learner_calendar_settings ("
        "learner_id, time_zone, week_starts_on, created_at, updated_at"
        ") VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(learner_id) DO UPDATE SET "
        "time_zone = excluded.time_zone, "
        "week_starts_on = excluded.week_starts_on, "
        "updated_at = excluded.updated_at",
        (learner_id, zone, week_starts_on, now, now),
    )
    return get_calendar_settings(conn, learner_id)


def _target_key(objective_id: str, subskill: str) -> tuple[str, str]:
    return objective_id, subskill


def _objective_label(objective_id: str) -> str:
    definition = objective_definition(objective_id)
    return definition.label if definition is not None else objective_id.replace("_", " ")


def _launch_href(
    receipt: Mapping[str, Any] | None,
    *,
    scheduled_date: str,
) -> str | None:
    if not receipt:
        return None
    mode = str(receipt.get("mode") or "")
    case_concept = str(receipt.get("caseConcept") or "")
    receipt_concept = str(receipt.get("receiptConcept") or "")
    subskill = str(receipt.get("subskill") or "")
    if mode not in {"train", "rapid"} or not all(
        (case_concept, receipt_concept, subskill)
    ):
        return None
    return_to = f"/home?panel=calendar&date={scheduled_date}"
    params = {
        "receiptConcept": receipt_concept,
        "subskill": subskill,
        "returnTo": return_to,
    }
    if mode == "train":
        params["concept"] = case_concept
        return f"/train?{urlencode(params)}"
    params["focus"] = case_concept
    if case_concept in RUNTIME_OBJECTIVE_IDS:
        params["practiceMode"] = "emergency"
    return f"/rapid?{urlencode(params)}"


def _return_to_calendar(scheduled_date: str) -> str:
    return f"/home?panel=calendar&date={scheduled_date}"


def _generic_mode_launch_href(mode: str, *, scheduled_date: str) -> str | None:
    if mode not in _CALENDAR_MODES:
        return None
    if mode == "guided":
        return "/learn"
    path = {"train": "/train", "rapid": "/rapid", "clinical": "/practice"}[mode]
    return f"{path}?{urlencode({'returnTo': _return_to_calendar(scheduled_date)})}"


def calendarize_plan_launch_href(
    href: str,
    *,
    mode: str,
    scheduled_date: str,
) -> str:
    """Attach a calendar return only to a server-authored mode destination."""

    expected_path = {"train": "/train", "rapid": "/rapid"}.get(mode)
    parsed = urlsplit(href)
    if (
        expected_path is None
        or parsed.scheme
        or parsed.netloc
        or parsed.fragment
        or parsed.path != expected_path
    ):
        raise ValueError("The current study-plan action has no supported calendar route")
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key != "returnTo"]
    query.append(("returnTo", _return_to_calendar(scheduled_date)))
    return f"{parsed.path}?{urlencode(query)}"


def calendar_plan_action(plan: Mapping[str, Any]) -> dict[str, Any] | None:
    """Project one deterministic, launchable practice block from the current plan.

    Guided remediation remains the immediate recommendation when present. The
    calendar action is deliberately its independently checked follow-up, because
    Guided modules do not yet implement a calendar return contract.
    """

    stages = sorted(
        (
            stage
            for stage in plan.get("stages") or []
            if isinstance(stage, Mapping)
            and str(stage.get("mode") or "") in {"train", "rapid"}
            and str(stage.get("href") or "").strip()
        ),
        key=lambda stage: int(stage.get("order") or 0),
    )
    if not stages:
        return None
    stage = stages[0]
    primary = plan.get("primary") if isinstance(plan.get("primary"), Mapping) else {}
    basis = plan.get("basis") if isinstance(plan.get("basis"), Mapping) else {}
    guided = plan.get("guidedRemediation") if isinstance(plan.get("guidedRemediation"), Mapping) else None
    relationship = (
        "starting_check"
        if bool(basis.get("baselineNeeded"))
        else "follow_up"
        if guided is not None
        else "next_step"
    )
    stage_title = str(stage.get("title") or "Focused ECG practice").strip()[:120]
    title = (
        f"Starting check: {stage_title}"
        if relationship == "starting_check"
        else f"After guided review: {stage_title}"
        if relationship == "follow_up"
        else stage_title
    )[:120]
    objective_id = str(stage.get("receiptConcept") or "")
    subskill = str(stage.get("receiptSubskill") or "")
    case_concept = str(primary.get("caseConcept") or "")
    if not all((objective_id, subskill, case_concept)):
        return None
    action: dict[str, Any] = {
        "version": _CALENDAR_PLAN_ACTION_VERSION,
        "relationship": relationship,
        "title": title,
        "mode": str(stage["mode"]),
        "objectiveId": objective_id,
        "objectiveLabel": str(primary.get("label") or "") or None,
        "subskill": subskill,
        "caseConcept": case_concept,
        "launchHref": str(stage["href"]),
        "suggestedDurationMinutes": 30,
    }
    fingerprint = json.dumps(action, sort_keys=True, separators=(",", ":"))
    action["actionKey"] = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
    return action


def _current_due_rows(conn: sqlite3.Connection, learner_id: str) -> dict[tuple[str, str], sqlite3.Row]:
    rows = conn.execute(
        "SELECT concept, subskill, independent_attempts, next_due_at, "
        "stability_days, lapses, spaced_retrievals, last_independent_at, "
        "last_independent_correct FROM subskill_mastery "
        "WHERE learner_id = ? AND independent_attempts > 0 "
        "AND next_due_at IS NOT NULL",
        (learner_id,),
    ).fetchall()
    return {
        _target_key(str(row["concept"]), str(row["subskill"])): row
        for row in rows
    }


def get_competency_due_source(
    conn: sqlite3.Connection,
    learner_id: str,
    objective_id: str,
    subskill: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT independent_attempts, next_due_at FROM subskill_mastery "
        "WHERE learner_id = ? AND concept = ? AND subskill = ?",
        (learner_id, objective_id, subskill),
    ).fetchone()
    if row is None or int(row["independent_attempts"]) <= 0 or not row["next_due_at"]:
        return None
    return {
        "objectiveId": objective_id,
        "objectiveLabel": _objective_label(objective_id),
        "subskill": subskill,
        "nextDueAt": str(row["next_due_at"]),
    }


def get_competency_review_projection(
    conn: sqlite3.Connection,
    learner_id: str,
    rows: Mapping[tuple[str, str], Mapping[str, Any]],
    *,
    requested_time_zone: str | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return the same timezone-aware review buckets used by the calendar."""

    settings = get_calendar_settings(
        conn,
        learner_id,
        requested_time_zone=requested_time_zone,
    )
    zone = ZoneInfo(str(settings["timeZone"]))
    generated = (now or datetime.now(UTC)).astimezone(UTC)
    today = generated.astimezone(zone).date()
    counts: dict[str, int] = {}
    for row in rows.values():
        if int(row.get("independentAttempts", 0)) <= 0 or not row.get("nextDueAt"):
            continue
        due_at = parse_instant(str(row["nextDueAt"]))
        if due_at is None:
            continue
        state = due_snapshot(row, as_of=generated)
        projection_date = today if state["isDue"] else due_at.astimezone(zone).date()
        key = projection_date.isoformat()
        counts[key] = counts.get(key, 0) + 1
    return {
        "timeZone": str(settings["timeZone"]),
        "today": today.isoformat(),
        "reviewDays": [
            {"date": key, "total": total}
            for key, total in sorted(counts.items())
        ],
    }


def _item_dict(
    row: sqlite3.Row,
    *,
    due_rows: Mapping[tuple[str, str], sqlite3.Row] | None = None,
    receipts: Mapping[tuple[str, str], Mapping[str, Any] | None] | None = None,
    current_plan_action_key: str | None = None,
) -> dict[str, Any]:
    source = str(row["source"])
    objective_id = str(row["target_objective"] or "")
    subskill = str(row["target_subskill"] or "")
    competency = None
    if source == "retention_review" and objective_id and subskill:
        key = _target_key(objective_id, subskill)
        current = due_rows.get(key) if due_rows is not None else None
        current_due_at = str(current["next_due_at"]) if current is not None else None
        receipt = receipts.get(key) if receipts is not None else None
        competency = {
            "objectiveId": objective_id,
            "objectiveLabel": _objective_label(objective_id),
            "subskill": subskill,
            "caseConcept": str(row["target_case_concept"]),
            "mode": str(row["target_mode"]),
            "sourceDueAt": str(row["source_due_at"]),
            "currentDueAt": current_due_at,
            "sourceCurrent": current_due_at == str(row["source_due_at"]),
            "launchHref": _launch_href(
                receipt,
                scheduled_date=str(row["scheduled_date"]),
            ),
        }
    target_mode = str(row["target_mode"] or "")
    activity = None
    if source == "retention_review" and competency is not None:
        activity = {
            "kind": "retention_review",
            "mode": target_mode,
            "objectiveId": objective_id,
            "objectiveLabel": competency["objectiveLabel"],
            "subskill": subskill,
            "caseConcept": str(row["target_case_concept"] or "") or None,
            "sourceCurrent": competency["sourceCurrent"],
            "launchHref": competency["launchHref"],
        }
    elif source == "study_plan" and target_mode:
        activity = {
            "kind": "study_plan",
            "mode": target_mode,
            "objectiveId": objective_id or None,
            "objectiveLabel": _objective_label(objective_id) if objective_id else None,
            "subskill": subskill or None,
            "caseConcept": str(row["target_case_concept"] or "") or None,
            "sourceCurrent": (
                str(row["source_plan_key"] or "") == current_plan_action_key
                if current_plan_action_key is not None
                else None
            ),
            "launchHref": str(row["target_launch_href"] or "") or None,
        }
    elif source == "manual" and target_mode:
        activity = {
            "kind": "manual_mode",
            "mode": target_mode,
            "objectiveId": None,
            "objectiveLabel": None,
            "subskill": None,
            "caseConcept": None,
            "sourceCurrent": None,
            "launchHref": _generic_mode_launch_href(
                target_mode,
                scheduled_date=str(row["scheduled_date"]),
            ),
        }
    return {
        "itemId": str(row["item_id"]),
        "source": source,
        "title": str(row["title"]),
        "notes": str(row["notes"]),
        "scheduledDate": str(row["scheduled_date"]),
        "startMinute": (
            int(row["start_minute"]) if row["start_minute"] is not None else None
        ),
        "durationMinutes": (
            int(row["duration_minutes"])
            if row["duration_minutes"] is not None
            else None
        ),
        "status": str(row["status"]),
        "completionSource": (
            str(row["completion_source"]) if row["completion_source"] else None
        ),
        "completedAt": str(row["completed_at"]) if row["completed_at"] else None,
        "competency": competency,
        "activity": activity,
        "revision": int(row["revision"]),
        "createdAt": str(row["created_at"]),
        "updatedAt": str(row["updated_at"]),
    }


def _owned_item(
    conn: sqlite3.Connection,
    learner_id: str,
    item_id: str,
) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM study_calendar_items WHERE learner_id = ? AND item_id = ?",
        (learner_id, item_id),
    ).fetchone()
    if row is None:
        raise CalendarItemNotFoundError("Calendar item not found")
    return row


def get_calendar_item(
    conn: sqlite3.Connection,
    learner_id: str,
    item_id: str,
    *,
    receipts: Mapping[tuple[str, str], Mapping[str, Any] | None] | None = None,
    current_plan_action_key: str | None = None,
) -> dict[str, Any]:
    return _item_dict(
        _owned_item(conn, learner_id, item_id),
        due_rows=_current_due_rows(conn, learner_id),
        receipts=receipts or {},
        current_plan_action_key=current_plan_action_key,
    )


def _existing_request(
    conn: sqlite3.Connection,
    learner_id: str,
    client_request_id: str,
) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM study_calendar_items "
        "WHERE learner_id = ? AND client_request_id = ?",
        (learner_id, client_request_id),
    ).fetchone()


def replay_calendar_plan_request(
    conn: sqlite3.Connection,
    learner_id: str,
    *,
    client_request_id: str,
    source_plan_key: str,
    scheduled_date: str,
    start_minute: int | None,
    duration_minutes: int | None,
    notes: str,
    current_plan_action_key: str | None,
) -> dict[str, Any] | None:
    """Replay the same confirmed plan block even if the live plan later changes."""

    existing = _existing_request(conn, learner_id, client_request_id)
    if existing is None:
        return None
    expected = {
        "source": "study_plan",
        "source_plan_key": source_plan_key,
        "scheduled_date": scheduled_date,
        "start_minute": start_minute,
        "duration_minutes": duration_minutes,
        "notes": notes,
    }
    if all(existing[key] == value for key, value in expected.items()):
        return _item_dict(
            existing,
            due_rows=_current_due_rows(conn, learner_id),
            current_plan_action_key=current_plan_action_key,
        )
    raise CalendarItemConflictError(
        "calendar_request_conflict",
        "This request id was already used for a different calendar item.",
        _item_dict(existing),
    )


def create_calendar_item(
    conn: sqlite3.Connection,
    learner_id: str,
    *,
    source: str,
    title: str,
    notes: str,
    scheduled_date: str,
    start_minute: int | None,
    duration_minutes: int | None,
    client_request_id: str,
    now: str,
    target: Mapping[str, Any] | None = None,
    source_due_at: str | None = None,
    target_launch_href: str | None = None,
    source_plan_key: str | None = None,
) -> dict[str, Any]:
    if source not in {"manual", "retention_review", "study_plan"}:
        raise ValueError("Unsupported calendar item source")
    validate_calendar_date(scheduled_date)
    existing = _existing_request(conn, learner_id, client_request_id)
    target = target or {}
    semantic = {
        "source": source,
        "title": title,
        "notes": notes,
        "scheduled_date": scheduled_date,
        "start_minute": start_minute,
        "duration_minutes": duration_minutes,
        "target_objective": target.get("objectiveId"),
        "target_subskill": target.get("subskill"),
        "target_mode": target.get("mode"),
        "target_case_concept": target.get("caseConcept"),
        "source_due_at": source_due_at,
        "target_launch_href": target_launch_href,
        "source_plan_key": source_plan_key,
    }
    if existing is not None:
        if all(existing[key] == value for key, value in semantic.items()):
            return _item_dict(existing)
        raise CalendarItemConflictError(
            "calendar_request_conflict",
            "This request id was already used for a different calendar item.",
            _item_dict(existing),
        )
    item_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO study_calendar_items ("
        "item_id, learner_id, source, title, notes, scheduled_date, start_minute, "
        "duration_minutes, status, target_objective, target_subskill, target_mode, "
        "target_case_concept, source_due_at, target_launch_href, source_plan_key, "
        "client_request_id, revision, "
        "created_at, updated_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'scheduled', ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
        (
            item_id,
            learner_id,
            source,
            title,
            notes,
            scheduled_date,
            start_minute,
            duration_minutes,
            semantic["target_objective"],
            semantic["target_subskill"],
            semantic["target_mode"],
            semantic["target_case_concept"],
            source_due_at,
            target_launch_href,
            source_plan_key,
            client_request_id,
            now,
            now,
        ),
    )
    return _item_dict(_owned_item(conn, learner_id, item_id))


def update_calendar_item(
    conn: sqlite3.Connection,
    learner_id: str,
    item_id: str,
    *,
    revision: int,
    changes: Mapping[str, Any],
    now: str,
) -> dict[str, Any]:
    current = _owned_item(conn, learner_id, item_id)
    if int(current["revision"]) != revision:
        raise CalendarItemConflictError(
            "calendar_item_conflict",
            "This calendar item changed in another view.",
            _item_dict(current),
        )
    columns = {
        "title": "title",
        "notes": "notes",
        "scheduledDate": "scheduled_date",
        "startMinute": "start_minute",
        "durationMinutes": "duration_minutes",
    }
    assignments: list[str] = []
    values: list[Any] = []
    for key, value in changes.items():
        if key not in columns:
            raise ValueError(f"Unsupported calendar item update: {key}")
        if key == "scheduledDate":
            validate_calendar_date(str(value))
        assignments.append(f"{columns[key]} = ?")
        values.append(value)
    if not assignments:
        return _item_dict(current)
    cursor = conn.execute(
        "UPDATE study_calendar_items SET "
        + ", ".join(assignments)
        + ", revision = revision + 1, updated_at = ? "
        "WHERE learner_id = ? AND item_id = ? AND revision = ?",
        (*values, now, learner_id, item_id, revision),
    )
    if cursor.rowcount != 1:
        latest = _owned_item(conn, learner_id, item_id)
        raise CalendarItemConflictError(
            "calendar_item_conflict",
            "This calendar item changed in another view.",
            _item_dict(latest),
        )
    return _item_dict(_owned_item(conn, learner_id, item_id))


def set_calendar_item_completion(
    conn: sqlite3.Connection,
    learner_id: str,
    item_id: str,
    *,
    revision: int,
    completed: bool,
    now: str,
) -> dict[str, Any]:
    current = _owned_item(conn, learner_id, item_id)
    desired = "completed" if completed else "scheduled"
    if str(current["status"]) == desired:
        return _item_dict(current)
    if int(current["revision"]) != revision:
        raise CalendarItemConflictError(
            "calendar_item_conflict",
            "This calendar item changed in another view.",
            _item_dict(current),
        )
    cursor = conn.execute(
        "UPDATE study_calendar_items SET status = ?, completion_source = ?, "
        "completed_at = ?, revision = revision + 1, updated_at = ? "
        "WHERE learner_id = ? AND item_id = ? AND revision = ?",
        (
            desired,
            "manual" if completed else None,
            now if completed else None,
            now,
            learner_id,
            item_id,
            revision,
        ),
    )
    if cursor.rowcount != 1:
        latest = _owned_item(conn, learner_id, item_id)
        raise CalendarItemConflictError(
            "calendar_item_conflict",
            "This calendar item changed in another view.",
            _item_dict(latest),
        )
    return _item_dict(_owned_item(conn, learner_id, item_id))


def delete_calendar_item(
    conn: sqlite3.Connection,
    learner_id: str,
    item_id: str,
    *,
    revision: int,
) -> None:
    current = _owned_item(conn, learner_id, item_id)
    if int(current["revision"]) != revision:
        raise CalendarItemConflictError(
            "calendar_item_conflict",
            "This calendar item changed in another view.",
            _item_dict(current),
        )
    cursor = conn.execute(
        "DELETE FROM study_calendar_items "
        "WHERE learner_id = ? AND item_id = ? AND revision = ?",
        (learner_id, item_id, revision),
    )
    if cursor.rowcount != 1:
        latest = _owned_item(conn, learner_id, item_id)
        raise CalendarItemConflictError(
            "calendar_item_conflict",
            "This calendar item changed in another view.",
            _item_dict(latest),
        )


def get_calendar_snapshot(
    conn: sqlite3.Connection,
    learner_id: str,
    *,
    start_date: str,
    end_date: str,
    requested_time_zone: str | None,
    receipts: Mapping[tuple[str, str], Mapping[str, Any] | None],
    current_plan_action_key: str | None = None,
    current_plan_priorities: Mapping[tuple[str, str], int] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    start, end = validate_calendar_range(start_date, end_date)
    settings = get_calendar_settings(
        conn,
        learner_id,
        requested_time_zone=requested_time_zone,
    )
    zone = ZoneInfo(str(settings["timeZone"]))
    generated = (now or datetime.now(UTC)).astimezone(UTC)
    today = generated.astimezone(zone).date()
    due_rows = _current_due_rows(conn, learner_id)
    item_rows = conn.execute(
        "SELECT * FROM study_calendar_items WHERE learner_id = ? "
        "AND scheduled_date >= ? AND scheduled_date <= ? "
        "ORDER BY scheduled_date, start_minute IS NULL, start_minute, created_at, item_id",
        (learner_id, start.isoformat(), end.isoformat()),
    ).fetchall()
    scheduled_targets = conn.execute(
        "SELECT item_id, target_objective, target_subskill, source_due_at, "
        "scheduled_date FROM study_calendar_items WHERE learner_id = ? "
        "AND source = 'retention_review' AND status = 'scheduled' "
        "ORDER BY scheduled_date, created_at, item_id",
        (learner_id,),
    ).fetchall()
    planned: dict[tuple[str, str, str], sqlite3.Row] = {}
    for row in scheduled_targets:
        planned.setdefault(
            (
                str(row["target_objective"]),
                str(row["target_subskill"]),
                str(row["source_due_at"]),
            ),
            row,
        )

    review_by_date: dict[str, list[dict[str, Any]]] = {}
    for key, row in due_rows.items():
        due_at = parse_instant(str(row["next_due_at"]))
        if due_at is None:
            continue
        state = due_snapshot(
            {
                "independentAttempts": row["independent_attempts"],
                "nextDueAt": row["next_due_at"],
            },
            as_of=generated,
        )
        projection_date = today if state["isDue"] else due_at.astimezone(zone).date()
        if projection_date < start or projection_date > end:
            continue
        objective_id, subskill = key
        source_due_at = str(row["next_due_at"])
        planned_row = planned.get((objective_id, subskill, source_due_at))
        item = {
            "key": f"{objective_id}:{subskill}:{source_due_at}",
            "objectiveId": objective_id,
            "objectiveLabel": _objective_label(objective_id),
            "subskill": subskill,
            "nextDueAt": source_due_at,
            "dueState": str(state["dueState"]),
            "overdueDays": float(state["overdueDays"]),
            "plannedFor": (
                str(planned_row["scheduled_date"]) if planned_row is not None else None
            ),
            "scheduledItemId": (
                str(planned_row["item_id"]) if planned_row is not None else None
            ),
            "launchHref": _launch_href(
                receipts.get(key),
                scheduled_date=projection_date.isoformat(),
            ),
            # This is presentation ordering only. The deterministic mastery
            # planner remains the source of priority and every due review stays
            # in the response so the calendar never hides retention evidence.
            "planPriority": (current_plan_priorities or {}).get(key),
        }
        review_by_date.setdefault(projection_date.isoformat(), []).append(item)

    review_days = []
    for day, items in sorted(review_by_date.items()):
        items.sort(
            key=lambda item: (
                0 if item["dueState"] == "overdue" else 1,
                -float(item["overdueDays"]),
                int(item["planPriority"])
                if item["planPriority"] is not None
                else 1_000_000,
                str(item["objectiveLabel"]),
                str(item["subskill"]),
            )
        )
        review_days.append(
            {
                "date": day,
                "total": len(items),
                "overdue": sum(item["dueState"] == "overdue" for item in items),
                "items": items,
            }
        )

    return {
        "version": CALENDAR_VERSION,
        "generatedAt": generated.isoformat(),
        "range": {"startDate": start.isoformat(), "endDate": end.isoformat()},
        "settings": settings,
        "today": today.isoformat(),
        "items": [
            _item_dict(
                row,
                due_rows=due_rows,
                receipts=receipts,
                current_plan_action_key=current_plan_action_key,
            )
            for row in item_rows
        ],
        "reviewDays": review_days,
    }
