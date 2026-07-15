"""Clinical-specific assessment lease and atomic answer integration.

The generic learner store predates the normalized assessment ledger.  This
module keeps the Clinical migration local to the mode while composing the
existing Clinical answer, attempt, formative mastery, session, lease, and
answer-free learner-event writes in one SQLite transaction.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import sqlite3
import uuid
from typing import Any

from ..assessment_ledger import (
    LeaseExpiredError,
    LeaseNotFoundError,
    LeaseStateError,
    append_event,
    claim_submission,
    create_lease,
    mark_submitted,
    owner_exposure_ids,
    release_submission,
    terminal_event_id,
    terminalize_lease,
)


CLINICAL_LEASE_TTL = timedelta(days=30)
EVIDENCE_LEVEL = "formative"
INTEGRITY_STATUS = "atomic_v2"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _submission_key(session_id: str, item_id: str) -> str:
    # First-write-wins is the Clinical contract. A retry carrying altered UI
    # fields must replay the first durable decision, never create a second grade.
    return f"clinical-submit:{session_id}:{item_id}"


def _answer_event_id(session_id: str, item_id: str) -> str:
    return f"clinical-answer:{session_id}:{item_id}"


def _session_event_id(session_id: str, event_type: str) -> str:
    return f"clinical-session:{session_id}:{event_type}"


def _live_lease(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    owner_id: str | None = None,
) -> sqlite3.Row | None:
    rows = conn.execute(
        "SELECT leases.*, cases.ecg_id FROM assessment_leases AS leases "
        "JOIN assessment_lease_cases AS cases "
        "ON cases.lease_id = leases.lease_id AND cases.ordinal = 0 "
        "WHERE leases.mode = 'clinical' AND leases.session_id = ? "
        "AND leases.state IN ('active', 'submitting') ORDER BY leases.lease_id",
        (session_id,),
    ).fetchall()
    if len(rows) > 1:
        raise RuntimeError("Clinical session has more than one live assessment lease")
    if rows and owner_id is not None and str(rows[0]["owner_id"]) != owner_id:
        raise RuntimeError("Clinical session and assessment lease have different owners")
    return rows[0] if rows else None


def _append_terminal_event(
    conn: sqlite3.Connection,
    *,
    lease: sqlite3.Row,
    event_type: str,
    terminal_state: str,
    occurred_at: str,
) -> None:
    append_event(
        conn,
        event_id=terminal_event_id(str(lease["lease_id"]), terminal_state),
        owner_id=str(lease["owner_id"]),
        mode="clinical",
        session_id=str(lease["session_id"]),
        lease_id=str(lease["lease_id"]),
        ecg_id=str(lease["ecg_id"]),
        event_type=event_type,
        evidence_level=EVIDENCE_LEVEL,
        integrity_status=str(lease["integrity_status"]),
        occurred_at=occurred_at,
    )


def create_session(
    store,
    *,
    learner_id: str,
    lane: str,
    tier: str,
    length: int,
    focus_objective: str | None,
    focus_subskill: str | None,
    requested_length: int | None = None,
    available_length: int | None = None,
    length_reason: str | None = None,
) -> str:
    """Create one Clinical session and retire prior live exposure atomically."""

    store.ensure_profile(learner_id)
    now = _now()
    session_id = f"cs_{uuid.uuid4().hex[:16]}"
    requested = int(length if requested_length is None else requested_length)
    available = int(length if available_length is None else available_length)
    with store.connect() as conn:
        if not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE")
        prior_sessions = conn.execute(
            "SELECT session_id FROM clinical_shift_sessions "
            "WHERE learner_id = ? AND status = 'active' ORDER BY created_at, session_id",
            (learner_id,),
        ).fetchall()
        for prior in prior_sessions:
            prior_id = str(prior["session_id"])
            lease = _live_lease(conn, session_id=prior_id, owner_id=learner_id)
            if lease is not None:
                terminalize_lease(
                    conn,
                    lease_id=str(lease["lease_id"]),
                    owner_id=learner_id,
                    terminal_state="abandoned",
                    terminal_at=now,
                )
                _append_terminal_event(
                    conn,
                    lease=lease,
                    event_type="item_abandoned",
                    terminal_state="abandoned",
                    occurred_at=now,
                )
        conn.execute(
            "UPDATE clinical_shift_sessions SET status = 'abandoned', pending_item_id = NULL, "
            "feedback_item_id = NULL, pending_context_revealed = 0, "
            "pending_first_look_json = NULL, pending_step_answers_json = '[]', "
            "pending_orient_started_at = NULL, pending_orient_deadline_at = NULL, "
            "pending_decide_started_at = NULL, pending_decide_deadline_at = NULL, "
            "pending_decide_submitted_at = NULL, updated_at = ? "
            "WHERE learner_id = ? AND status = 'active'",
            (now, learner_id),
        )
        conn.execute(
            "UPDATE clinical_shift_sessions SET feedback_item_id = NULL, updated_at = ? "
            "WHERE learner_id = ? AND status = 'complete' AND feedback_item_id IS NOT NULL",
            (now, learner_id),
        )
        conn.execute(
            "INSERT INTO clinical_shift_sessions ("
            "session_id, learner_id, lane, tier, focus_objective, focus_subskill, "
            "length, requested_length, available_length, length_reason, served_json, "
            "served_ecgs_json, calibration_json, pending_item_id, feedback_item_id, "
            "position, status, created_at, updated_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', '[]', '[]', NULL, NULL, 0, ?, ?, ?)",
            (
                session_id,
                learner_id,
                lane,
                tier,
                focus_objective,
                focus_subskill,
                int(length),
                requested,
                available,
                length_reason,
                "complete" if int(length) == 0 else "active",
                now,
                now,
            ),
        )
        append_event(
            conn,
            event_id=_session_event_id(session_id, "started"),
            owner_id=learner_id,
            mode="clinical",
            session_id=session_id,
            event_type="session_started",
            evidence_level=EVIDENCE_LEVEL,
            integrity_status=INTEGRITY_STATUS,
            occurred_at=now,
        )
    return session_id


def live_owner_exposures(store, learner_id: str) -> set[str]:
    with store.connect() as conn:
        return set(owner_exposure_ids(conn, owner_id=learner_id))


def claim_pending_item(
    store,
    *,
    session_id: str,
    item_id: str,
    ecg_id: str,
) -> dict[str, Any]:
    """Persist the frozen pending item and its real-ECG lease together."""

    now = _now()
    with store.connect() as conn:
        if not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE")
        session = conn.execute(
            "SELECT learner_id, pending_item_id, status, served_json, served_ecgs_json "
            "FROM clinical_shift_sessions "
            "WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if session is None:
            return {"status": "missing"}
        owner_id = str(session["learner_id"])
        existing_pending = session["pending_item_id"]
        if existing_pending is not None and str(existing_pending) != item_id:
            return {"status": "existing", "pendingItemId": str(existing_pending)}
        if session["status"] != "active":
            return {"status": "not_active", "pendingItemId": existing_pending}

        lease = _live_lease(conn, session_id=session_id, owner_id=owner_id)
        if existing_pending is not None:
            if lease is None:
                # Safe migration for a presentation created by the prior binary.
                lease_id = f"cl_{uuid.uuid4().hex}"
                create_lease(
                    conn,
                    lease_id=lease_id,
                    owner_id=owner_id,
                    mode="clinical",
                    session_id=session_id,
                    ecg_ids=(ecg_id,),
                    created_at=now,
                    expires_at=_utc(now) + CLINICAL_LEASE_TTL,
                    integrity_status="backfilled_v1",
                )
                append_event(
                    conn,
                    event_id=f"{lease_id}:presented",
                    owner_id=owner_id,
                    mode="clinical",
                    session_id=session_id,
                    lease_id=lease_id,
                    ecg_id=ecg_id,
                    event_type="item_presented",
                    evidence_level=EVIDENCE_LEVEL,
                    integrity_status="backfilled_v1",
                    occurred_at=now,
                )
                return {"status": "backfilled", "pendingItemId": item_id}
            if str(lease["ecg_id"]) != ecg_id:
                raise RuntimeError("Clinical pending item and assessment ECG diverged")
            return {"status": "existing", "pendingItemId": item_id}

        if lease is not None:
            raise RuntimeError("Clinical session has a live lease without a pending item")
        if ecg_id in set(owner_exposure_ids(conn, owner_id=owner_id)):
            return {"status": "exposure_conflict", "pendingItemId": None}
        updated = conn.execute(
            "UPDATE clinical_shift_sessions SET pending_item_id = ?, "
            "pending_context_revealed = 0, pending_first_look_json = NULL, "
            "pending_step_answers_json = '[]', pending_orient_started_at = NULL, "
            "pending_orient_deadline_at = NULL, pending_decide_started_at = NULL, "
            "pending_decide_deadline_at = NULL, pending_decide_submitted_at = NULL, "
            "updated_at = ? WHERE session_id = ? AND pending_item_id IS NULL "
            "AND feedback_item_id IS NULL AND status = 'active'",
            (item_id, now, session_id),
        )
        if updated.rowcount != 1:
            current = conn.execute(
                "SELECT pending_item_id FROM clinical_shift_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return {
                "status": "existing",
                "pendingItemId": str(current["pending_item_id"]) if current and current["pending_item_id"] else None,
            }
        lease_id = f"cl_{uuid.uuid4().hex}"
        create_lease(
            conn,
            lease_id=lease_id,
            owner_id=owner_id,
            mode="clinical",
            session_id=session_id,
            ecg_ids=(ecg_id,),
            created_at=now,
            expires_at=_utc(now) + CLINICAL_LEASE_TTL,
            integrity_status=INTEGRITY_STATUS,
        )
        append_event(
            conn,
            event_id=f"{lease_id}:presented",
            owner_id=owner_id,
            mode="clinical",
            session_id=session_id,
            lease_id=lease_id,
            ecg_id=ecg_id,
            event_type="item_presented",
            evidence_level=EVIDENCE_LEVEL,
            integrity_status=INTEGRITY_STATUS,
            occurred_at=now,
        )
        return {"status": "claimed", "pendingItemId": item_id, "leaseId": lease_id}


def expire_pending_item(store, *, session_id: str) -> bool:
    """Expire a stale unclaimed Clinical presentation exactly once."""

    now = _now()
    with store.connect() as conn:
        if not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE")
        session = conn.execute(
            "SELECT learner_id, pending_item_id, status, served_json, served_ecgs_json "
            "FROM clinical_shift_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if session is None or session["pending_item_id"] is None:
            return False
        lease = _live_lease(
            conn,
            session_id=session_id,
            owner_id=str(session["learner_id"]),
        )
        if (
            lease is None
            or str(lease["state"]) != "active"
            or _utc(str(lease["expires_at"])) > _utc(now)
        ):
            return False
        terminalize_lease(
            conn,
            lease_id=str(lease["lease_id"]),
            owner_id=str(session["learner_id"]),
            terminal_state="expired",
            terminal_at=now,
        )
        _append_terminal_event(
            conn,
            lease=lease,
            event_type="item_expired",
            terminal_state="expired",
            occurred_at=now,
        )
        served = json.loads(session["served_json"])
        if str(session["pending_item_id"]) not in served:
            served.append(str(session["pending_item_id"]))
        served_ecgs = json.loads(session["served_ecgs_json"])
        if str(lease["ecg_id"]) not in served_ecgs:
            served_ecgs.append(str(lease["ecg_id"]))
        conn.execute(
            "UPDATE clinical_shift_sessions SET served_json = ?, served_ecgs_json = ?, "
            "pending_item_id = NULL, "
            "pending_context_revealed = 0, pending_first_look_json = NULL, "
            "pending_step_answers_json = '[]', pending_orient_started_at = NULL, "
            "pending_orient_deadline_at = NULL, pending_decide_started_at = NULL, "
            "pending_decide_deadline_at = NULL, pending_decide_submitted_at = NULL, "
            "updated_at = ? WHERE session_id = ? AND pending_item_id = ?",
            (
                json.dumps(served),
                json.dumps(served_ecgs),
                now,
                session_id,
                session["pending_item_id"],
            ),
        )
        return True


def claim_answer_submission(
    store,
    *,
    session_id: str,
    item_id: str,
    ecg_id: str,
) -> dict[str, Any]:
    """Reserve the current Clinical lease before any grading work occurs."""

    now = _now()
    with store.connect() as conn:
        if not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE")
        session = conn.execute(
            "SELECT learner_id, pending_item_id, status, served_json, served_ecgs_json "
            "FROM clinical_shift_sessions "
            "WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if session is None:
            return {"status": "missing"}
        if session["status"] != "active" or str(session["pending_item_id"] or "") != item_id:
            return {"status": "not_pending", "pendingItemId": session["pending_item_id"]}
        owner_id = str(session["learner_id"])
        lease = _live_lease(conn, session_id=session_id, owner_id=owner_id)
        if lease is None:
            return {"status": "missing_lease"}
        if str(lease["ecg_id"]) != ecg_id:
            raise RuntimeError("Clinical answer ECG is outside the frozen lease")
        submission_key = _submission_key(session_id, item_id)
        try:
            mutation = claim_submission(
                conn,
                lease_id=str(lease["lease_id"]),
                owner_id=owner_id,
                submission_key=submission_key,
                claimed_at=now,
            )
        except LeaseExpiredError:
            terminalize_lease(
                conn,
                lease_id=str(lease["lease_id"]),
                owner_id=owner_id,
                terminal_state="expired",
                terminal_at=now,
            )
            _append_terminal_event(
                conn,
                lease=lease,
                event_type="item_expired",
                terminal_state="expired",
                occurred_at=now,
            )
            served = json.loads(session["served_json"])
            if item_id not in served:
                served.append(item_id)
            served_ecgs = json.loads(session["served_ecgs_json"])
            if ecg_id not in served_ecgs:
                served_ecgs.append(ecg_id)
            conn.execute(
                "UPDATE clinical_shift_sessions SET served_json = ?, served_ecgs_json = ?, "
                "pending_item_id = NULL, "
                "pending_context_revealed = 0, pending_first_look_json = NULL, "
                "pending_step_answers_json = '[]', pending_orient_started_at = NULL, "
                "pending_orient_deadline_at = NULL, pending_decide_started_at = NULL, "
                "pending_decide_deadline_at = NULL, pending_decide_submitted_at = NULL, "
                "updated_at = ? WHERE session_id = ? AND pending_item_id = ?",
                (
                    json.dumps(served),
                    json.dumps(served_ecgs),
                    now,
                    session_id,
                    item_id,
                ),
            )
            return {"status": "expired"}
        return {
            "status": "claimed",
            "leaseId": mutation.lease_id,
            "submissionKey": submission_key,
            "ownerId": owner_id,
            "replayed": mutation.replayed,
        }


def release_answer_submission(
    store,
    *,
    session_id: str,
    owner_id: str,
    lease_id: str,
    submission_key: str,
) -> bool:
    """Best-effort exact-key release after a recoverable grading failure."""

    now = _now()
    with store.connect() as conn:
        if not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE")
        session = conn.execute(
            "SELECT learner_id FROM clinical_shift_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if session is None or str(session["learner_id"]) != owner_id:
            return False
        try:
            release_submission(
                conn,
                lease_id=lease_id,
                owner_id=owner_id,
                submission_key=submission_key,
                released_at=now,
            )
        except (LeaseNotFoundError, LeaseStateError):
            return False
        return True


def finalize_answer(
    store,
    *,
    session_id: str,
    item_id: str,
    ecg_id: str,
    response: dict[str, Any],
    grade: dict[str, Any],
    correct: bool,
    confidence: int,
    calibration_event: dict[str, Any] | None,
    competency_events: list[dict[str, Any]],
    lease_id: str,
    submission_key: str,
) -> dict[str, Any]:
    """Commit the answer, progress, evidence, and lease terminal state together."""

    now = _now()
    with store.connect() as conn:
        if not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT * FROM clinical_shift_answers WHERE session_id = ? AND item_id = ?",
            (session_id, item_id),
        ).fetchone()
        if existing is not None:
            return {"status": "replay", "answer": store._shift_answer_dict(existing)}
        session = conn.execute(
            "SELECT learner_id, tier, length, served_json, served_ecgs_json, "
            "calibration_json, pending_item_id, pending_context_revealed, "
            "pending_decide_submitted_at FROM clinical_shift_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if session is None:
            return {"status": "missing"}
        if str(session["pending_item_id"] or "") != item_id:
            return {"status": "not_pending", "pendingItemId": session["pending_item_id"]}
        if not session["pending_context_revealed"]:
            return {"status": "context_not_revealed", "pendingItemId": item_id}
        if not session["pending_decide_submitted_at"]:
            return {"status": "timing_not_claimed", "pendingItemId": item_id}
        owner_id = str(session["learner_id"])
        lease = conn.execute(
            "SELECT leases.integrity_status, leases.state, cases.ecg_id "
            "FROM assessment_leases AS leases JOIN assessment_lease_cases AS cases "
            "ON cases.lease_id = leases.lease_id AND cases.ordinal = 0 "
            "WHERE leases.lease_id = ? AND leases.owner_id = ? "
            "AND leases.mode = 'clinical' AND leases.session_id = ?",
            (lease_id, owner_id, session_id),
        ).fetchone()
        if lease is None or str(lease["ecg_id"]) != ecg_id:
            raise LeaseNotFoundError("Clinical answer reservation is not owned by this case")
        if str(lease["state"]) != "submitting":
            raise LeaseStateError("Clinical answer requires a claimed assessment lease")

        receipts = store._record_formative_subskill_receipts_in_transaction(
            conn,
            learner_id=owner_id,
            events=competency_events,
            now=now,
        )
        stored_grade = {**grade, "competencyReceipts": receipts}
        attempt_id = store._save_attempt_in_transaction(
            conn,
            learner_id=owner_id,
            case_id=ecg_id,
            mode="clinical_decision",
            structured_answer=response,
            confidence=confidence,
            grade=stored_grade,
            now=now,
        )
        cursor = conn.execute(
            "INSERT INTO clinical_shift_answers ("
            "session_id, item_id, ecg_id, response_json, grade_json, receipts_json, "
            "score, correct, answer_time_ms, calibration_event_json, attempt_id, created_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                item_id,
                ecg_id,
                json.dumps(response),
                json.dumps(stored_grade),
                json.dumps(receipts),
                float(stored_grade["score"]),
                1 if correct else 0,
                response.get("answer_time_ms", response.get("answerTimeMs")),
                json.dumps(calibration_event) if calibration_event is not None else None,
                attempt_id,
                now,
            ),
        )
        served = json.loads(session["served_json"])
        if item_id not in served:
            served.append(item_id)
        served_ecgs = json.loads(session["served_ecgs_json"])
        if ecg_id not in served_ecgs:
            served_ecgs.append(ecg_id)
        calibration = json.loads(session["calibration_json"])
        if calibration_event is not None:
            calibration.append(calibration_event)
        position = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM clinical_shift_answers WHERE session_id = ?",
                (session_id,),
            ).fetchone()["n"]
        )
        status = "complete" if position >= int(session["length"]) else "active"
        conn.execute(
            "UPDATE clinical_shift_sessions SET served_json = ?, served_ecgs_json = ?, "
            "calibration_json = ?, pending_item_id = NULL, pending_context_revealed = 0, "
            "pending_first_look_json = NULL, pending_step_answers_json = '[]', "
            "pending_orient_started_at = NULL, pending_orient_deadline_at = NULL, "
            "pending_decide_started_at = NULL, pending_decide_deadline_at = NULL, "
            "pending_decide_submitted_at = NULL, feedback_item_id = ?, position = ?, "
            "status = ?, updated_at = ? WHERE session_id = ?",
            (
                json.dumps(served),
                json.dumps(served_ecgs),
                json.dumps(calibration),
                item_id,
                position,
                status,
                now,
                session_id,
            ),
        )
        competency_scores: dict[str, float] = {}
        for event in competency_events:
            concept = str(event.get("concept") or "").strip()
            subskill = str(event.get("subskill") or "").strip()
            if concept and subskill:
                competency_scores[f"{concept}:{subskill}"] = max(
                    competency_scores.get(f"{concept}:{subskill}", 0.0),
                    max(0.0, min(1.0, float(event.get("score", 0.0)))),
                )
        append_event(
            conn,
            event_id=_answer_event_id(session_id, item_id),
            owner_id=owner_id,
            mode="clinical",
            session_id=session_id,
            lease_id=lease_id,
            ecg_id=ecg_id,
            event_type="answer_committed",
            evidence_level=EVIDENCE_LEVEL,
            integrity_status=str(lease["integrity_status"]),
            score=max(0.0, min(1.0, float(stored_grade["score"]))),
            competencies=competency_scores,
            submission_key=submission_key,
            occurred_at=now,
        )
        mark_submitted(
            conn,
            lease_id=lease_id,
            owner_id=owner_id,
            submission_key=submission_key,
            submitted_at=now,
        )
        if status == "complete":
            append_event(
                conn,
                event_id=_session_event_id(session_id, "completed"),
                owner_id=owner_id,
                mode="clinical",
                session_id=session_id,
                event_type="session_completed",
                evidence_level=EVIDENCE_LEVEL,
                integrity_status=str(lease["integrity_status"]),
                occurred_at=now,
            )
        answer_row = conn.execute(
            "SELECT * FROM clinical_shift_answers WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        return {"status": "created", "answer": store._shift_answer_dict(answer_row)}


def abandon_session(store, *, session_id: str, owner_id: str) -> dict[str, Any] | None:
    """Retire one active Clinical session and its pending lease atomically."""

    now = _now()
    with store.connect() as conn:
        if not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE")
        session = conn.execute(
            "SELECT learner_id, status FROM clinical_shift_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if session is None or str(session["learner_id"]) != owner_id:
            return None
        if str(session["status"]) != "active":
            return {"status": str(session["status"]), "changed": False}
        lease = _live_lease(conn, session_id=session_id, owner_id=owner_id)
        if lease is not None:
            terminalize_lease(
                conn,
                lease_id=str(lease["lease_id"]),
                owner_id=owner_id,
                terminal_state="abandoned",
                terminal_at=now,
            )
            _append_terminal_event(
                conn,
                lease=lease,
                event_type="item_abandoned",
                terminal_state="abandoned",
                occurred_at=now,
            )
        else:
            append_event(
                conn,
                event_id=_session_event_id(session_id, "abandoned"),
                owner_id=owner_id,
                mode="clinical",
                session_id=session_id,
                event_type="session_abandoned",
                evidence_level=EVIDENCE_LEVEL,
                integrity_status=INTEGRITY_STATUS,
                occurred_at=now,
            )
        updated = conn.execute(
            "UPDATE clinical_shift_sessions SET status = 'abandoned', "
            "pending_item_id = NULL, feedback_item_id = NULL, "
            "pending_context_revealed = 0, pending_first_look_json = NULL, "
            "pending_step_answers_json = '[]', pending_orient_started_at = NULL, "
            "pending_orient_deadline_at = NULL, pending_decide_started_at = NULL, "
            "pending_decide_deadline_at = NULL, pending_decide_submitted_at = NULL, "
            "updated_at = ? WHERE session_id = ? AND status = 'active'",
            (now, session_id),
        )
        return {"status": "abandoned", "changed": updated.rowcount == 1}
