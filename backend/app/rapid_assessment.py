"""Atomic assessment integrity boundary for Rapid ECG rounds.

The original Rapid store predates the normalized assessment ledger.  This
adapter deliberately owns only Rapid-mode transactions: it freezes each
pending waveform in an owner-bound lease, reserves the exact item before
grading, and commits the answer, generic attempt, competency receipts,
answer-free learner event, round advance, and terminal lease together.

Raw responses and answer contracts remain in the protected Rapid tables.  The
normalized ledger receives only provenance, bounded scores, and competency
identifiers.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import sqlite3
import uuid
from typing import Any

from .assessment_ledger import (
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
from .objectives import REGISTRY_VERSION


RAPID_LEASE_TTL = timedelta(days=7)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _utc(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(candidate)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Rapid timestamps must include a UTC offset")
    return parsed.astimezone(UTC)


class RapidExposureConflictError(RuntimeError):
    """The selected waveform is already live elsewhere for this owner."""


class RapidAssessmentStore:
    """Rapid-specific transaction coordinator over ``LearningStore.connect``."""

    def __init__(self, learning_store: Any) -> None:
        self.store = learning_store

    @staticmethod
    def _submission_key(round_id: str, position: int, case_id: str) -> str:
        # Rapid preserves first-write-wins semantics for one frozen item. The
        # raw key never leaves the server and only its domain-separated hash is
        # persisted by the normalized lease helper.
        return f"rapid-submit:{round_id}:{position}:{case_id}"

    @staticmethod
    def _answer_event_id(round_id: str, position: int, case_id: str) -> str:
        return f"rapid-answer:{round_id}:{position}:{case_id}"

    @staticmethod
    def _current_lease(
        conn: sqlite3.Connection, *, learner_id: str, round_id: str
    ) -> sqlite3.Row | None:
        rows = conn.execute(
            "SELECT leases.*, cases.ecg_id FROM assessment_leases AS leases "
            "JOIN assessment_lease_cases AS cases "
            "ON cases.lease_id = leases.lease_id AND cases.ordinal = 0 "
            "WHERE leases.mode = 'rapid' AND leases.session_id = ? "
            "AND leases.state IN ('active', 'submitting') "
            "ORDER BY leases.lease_id",
            (round_id,),
        ).fetchall()
        if len(rows) > 1:
            raise RuntimeError("Rapid round has more than one live assessment lease")
        if rows and str(rows[0]["owner_id"]) != learner_id:
            raise RuntimeError("Rapid round and assessment lease have different owners")
        return rows[0] if rows else None

    @staticmethod
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
            mode="rapid",
            session_id=str(lease["session_id"]),
            lease_id=str(lease["lease_id"]),
            ecg_id=str(lease["ecg_id"]),
            event_type=event_type,
            evidence_level="independent_transfer",
            integrity_status=str(lease["integrity_status"]),
            occurred_at=occurred_at,
        )

    @classmethod
    def _create_lease(
        cls,
        conn: sqlite3.Connection,
        *,
        round_row: sqlite3.Row,
        case_id: str,
        now: str,
        integrity_status: str,
        renewing_expired: bool = False,
    ) -> sqlite3.Row:
        learner_id = str(round_row["learner_id"])
        round_id = str(round_row["round_id"])
        live = set(
            owner_exposure_ids(
                conn,
                owner_id=learner_id,
                ignore_presentation_scope=("rapid", round_id, case_id)
                if renewing_expired
                else None,
            )
        )
        if case_id in live:
            raise RapidExposureConflictError(
                "This ECG is already protected by another live assessment"
            )
        lease_id = f"rl_{uuid.uuid4().hex}"
        create_lease(
            conn,
            lease_id=lease_id,
            owner_id=learner_id,
            mode="rapid",
            session_id=round_id,
            ecg_ids=(case_id,),
            created_at=now,
            expires_at=_utc(now) + RAPID_LEASE_TTL,
            integrity_status=integrity_status,
        )
        append_event(
            conn,
            event_id=f"{lease_id}:presented",
            owner_id=learner_id,
            mode="rapid",
            session_id=round_id,
            lease_id=lease_id,
            ecg_id=case_id,
            event_type="item_presented",
            evidence_level="independent_transfer",
            integrity_status=integrity_status,
            occurred_at=now,
        )
        lease = cls._current_lease(
            conn,
            learner_id=learner_id,
            round_id=round_id,
        )
        if lease is None:
            raise RuntimeError("Rapid lease creation lost its active boundary")
        return lease

    @classmethod
    def _ensure_pending_lease(
        cls,
        conn: sqlite3.Connection,
        *,
        round_row: sqlite3.Row,
        now: str,
        backfilled: bool,
    ) -> sqlite3.Row | None:
        case_id = str(round_row["pending_case_id"] or "")
        if not case_id:
            return None
        learner_id = str(round_row["learner_id"])
        round_id = str(round_row["round_id"])
        lease = cls._current_lease(
            conn, learner_id=learner_id, round_id=round_id
        )
        if lease is not None and str(lease["ecg_id"]) != case_id:
            raise RuntimeError(
                "Rapid pending item and live assessment lease protect different ECGs"
            )
        if lease is not None and str(lease["state"]) == "submitting":
            return lease
        renewing_expired = False
        if lease is not None and _utc(str(lease["expires_at"])) <= _utc(now):
            terminalize_lease(
                conn,
                lease_id=str(lease["lease_id"]),
                owner_id=learner_id,
                terminal_state="expired",
                terminal_at=now,
            )
            cls._append_terminal_event(
                conn,
                lease=lease,
                event_type="item_expired",
                terminal_state="expired",
                occurred_at=now,
            )
            lease = None
            renewing_expired = True
        if lease is None:
            lease = cls._create_lease(
                conn,
                round_row=round_row,
                case_id=case_id,
                now=now,
                integrity_status="backfilled_v1" if backfilled else "atomic_v2",
                renewing_expired=renewing_expired,
            )
        return lease

    @classmethod
    def _abandon_pending_lease(
        cls, conn: sqlite3.Connection, *, round_row: sqlite3.Row, now: str
    ) -> None:
        case_id = str(round_row["pending_case_id"] or "")
        if not case_id:
            return
        learner_id = str(round_row["learner_id"])
        lease = cls._ensure_pending_lease(
            conn, round_row=round_row, now=now, backfilled=True
        )
        if lease is None:
            return
        mutation = terminalize_lease(
            conn,
            lease_id=str(lease["lease_id"]),
            owner_id=learner_id,
            terminal_state="abandoned",
            terminal_at=now,
        )
        if not mutation.replayed:
            cls._append_terminal_event(
                conn,
                lease=lease,
                event_type="item_abandoned",
                terminal_state="abandoned",
                occurred_at=now,
            )

    def live_exposure_ids(self, learner_id: str) -> set[str]:
        with self.store.connect() as conn:
            return set(owner_exposure_ids(conn, owner_id=learner_id))

    def create_round(
        self,
        *,
        learner_id: str,
        pace: str,
        length: int,
        assessment_scope: str,
        deadline_seconds: int | None,
        focus_concept: str | None,
        focus_subskill: str | None,
        context_key: str,
        exclusions: list[str],
    ) -> dict[str, Any]:
        self.store.ensure_profile(learner_id)
        now = _now()
        round_id = f"rr_{uuid.uuid4().hex[:16]}"
        with self.store.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            current = conn.execute(
                "SELECT * FROM rapid_rounds WHERE learner_id = ? "
                "AND (status = 'active' OR feedback_case_id IS NOT NULL) "
                "ORDER BY updated_at DESC, round_id DESC",
                (learner_id,),
            ).fetchall()
            for row in current:
                if str(row["status"]) == "active":
                    self._abandon_pending_lease(conn, round_row=row, now=now)
            conn.execute(
                "UPDATE rapid_rounds SET status = 'abandoned', "
                "pending_case_id = NULL, feedback_case_id = NULL, "
                "pending_started_at = NULL, pending_deadline_at = NULL, "
                "pending_manifest_json = '{}', updated_at = ? "
                "WHERE learner_id = ? "
                "AND (status = 'active' OR feedback_case_id IS NOT NULL)",
                (now, learner_id),
            )
            conn.execute(
                "INSERT INTO rapid_rounds ("
                "round_id, learner_id, pace, length, assessment_scope, "
                "focus_concept, focus_subskill, context_key, exclusions_json, "
                "served_json, deadline_seconds, position, status, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, 0, 'active', ?, ?)",
                (
                    round_id,
                    learner_id,
                    pace,
                    length,
                    assessment_scope,
                    focus_concept,
                    focus_subskill,
                    context_key,
                    json.dumps(exclusions),
                    deadline_seconds,
                    now,
                    now,
                ),
            )
        result = self.store.get_rapid_round(round_id)
        if result is None:
            raise RuntimeError("Rapid round creation did not persist")
        return result

    def ensure_pending_lease(self, *, round_id: str, learner_id: str) -> None:
        now = _now()
        with self.store.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM rapid_rounds WHERE round_id = ?", (round_id,)
            ).fetchone()
            if row is None or str(row["learner_id"]) != learner_id:
                return
            if str(row["status"]) == "active" and row["pending_case_id"]:
                self._ensure_pending_lease(
                    conn, round_row=row, now=now, backfilled=True
                )

    def freeze_pending(
        self,
        *,
        round_id: str,
        learner_id: str,
        case_id: str,
        tested_objective_manifest: dict[str, Any],
    ) -> dict[str, Any] | None:
        now = _now()
        with self.store.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM rapid_rounds WHERE round_id = ?", (round_id,)
            ).fetchone()
            if row is None or str(row["learner_id"]) != learner_id:
                return None
            if (
                str(row["status"]) != "active"
                or row["pending_case_id"] is not None
                or row["feedback_case_id"] is not None
                or int(row["position"]) >= int(row["length"])
            ):
                return self.store._rapid_round_dict(row)
            self._create_lease(
                conn,
                round_row=row,
                case_id=case_id,
                now=now,
                integrity_status="atomic_v2",
            )
            updated = conn.execute(
                "UPDATE rapid_rounds SET pending_case_id = ?, "
                "pending_started_at = NULL, pending_deadline_at = NULL, "
                "pending_manifest_json = ?, updated_at = ? "
                "WHERE round_id = ? AND learner_id = ? AND status = 'active' "
                "AND pending_case_id IS NULL AND feedback_case_id IS NULL "
                "AND position < length",
                (
                    case_id,
                    json.dumps(tested_objective_manifest),
                    now,
                    round_id,
                    learner_id,
                ),
            )
            if updated.rowcount != 1:
                raise RuntimeError("Rapid pending freeze lost its item boundary")
            persisted = conn.execute(
                "SELECT * FROM rapid_rounds WHERE round_id = ?", (round_id,)
            ).fetchone()
            return self.store._rapid_round_dict(persisted)

    def claim_answer_submission(
        self, *, round_id: str, case_id: str, learner_id: str
    ) -> dict[str, Any]:
        now = _now()
        with self.store.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM rapid_rounds WHERE round_id = ?", (round_id,)
            ).fetchone()
            if row is None or str(row["learner_id"]) != learner_id:
                return {"status": "missing"}
            existing = conn.execute(
                "SELECT * FROM rapid_round_answers WHERE round_id = ? AND case_id = ?",
                (round_id, case_id),
            ).fetchone()
            if existing is not None:
                return {"status": "replay", "answer": self.store._rapid_answer_dict(existing)}
            if str(row["status"]) != "active" or str(row["pending_case_id"] or "") != case_id:
                return {"status": "not_pending", "pendingCaseId": row["pending_case_id"]}
            lease = self._ensure_pending_lease(
                conn, round_row=row, now=now, backfilled=True
            )
            if lease is None:
                raise RuntimeError("Rapid pending item has no assessment lease")
            position = int(row["position"])
            submission_key = self._submission_key(round_id, position, case_id)
            mutation = claim_submission(
                conn,
                lease_id=str(lease["lease_id"]),
                owner_id=learner_id,
                submission_key=submission_key,
                claimed_at=now,
            )
            return {
                "status": "claimed",
                "leaseId": mutation.lease_id,
                "submissionKey": submission_key,
                "position": position,
                "replayed": mutation.replayed,
            }

    def release_answer_submission(
        self,
        *,
        round_id: str,
        learner_id: str,
        lease_id: str,
        submission_key: str,
    ) -> bool:
        now = _now()
        with self.store.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT learner_id FROM rapid_rounds WHERE round_id = ?", (round_id,)
            ).fetchone()
            if row is None or str(row["learner_id"]) != learner_id:
                return False
            try:
                release_submission(
                    conn,
                    lease_id=lease_id,
                    owner_id=learner_id,
                    submission_key=submission_key,
                    released_at=now,
                )
            except (LeaseNotFoundError, LeaseStateError):
                return False
            return True

    def abandon_round(self, *, round_id: str, learner_id: str) -> dict[str, Any] | None:
        now = _now()
        with self.store.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM rapid_rounds WHERE round_id = ?", (round_id,)
            ).fetchone()
            if row is None or str(row["learner_id"]) != learner_id:
                return None
            if str(row["status"]) == "active":
                self._abandon_pending_lease(conn, round_row=row, now=now)
                conn.execute(
                    "UPDATE rapid_rounds SET status = 'abandoned', "
                    "pending_case_id = NULL, feedback_case_id = NULL, "
                    "pending_started_at = NULL, pending_deadline_at = NULL, "
                    "pending_manifest_json = '{}', updated_at = ? "
                    "WHERE round_id = ? AND learner_id = ? AND status = 'active'",
                    (now, round_id, learner_id),
                )
            persisted = conn.execute(
                "SELECT * FROM rapid_rounds WHERE round_id = ?", (round_id,)
            ).fetchone()
            return self.store._rapid_round_dict(persisted) if persisted else None

    @staticmethod
    def _competency_evidence(
        receipt_events: dict[int, dict[str, Any]]
    ) -> dict[str, float]:
        competencies: dict[str, float] = {}
        for event in receipt_events.values():
            concept = str(event.get("concept") or "").strip()
            raw_score = event.get("score")
            if not concept or isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
                continue
            score = max(0.0, min(1.0, float(raw_score)))
            for raw_subskill in event.get("subskills") or []:
                subskill = str(raw_subskill or "").strip()
                if not subskill:
                    continue
                key = f"{concept}:{subskill}"
                prior = competencies.get(key)
                # If an integration ever produces multiple receipts for the
                # same competency, the most conservative evidence wins.
                competencies[key] = score if prior is None else min(prior, score)
        return competencies

    def finalize_answer(
        self,
        *,
        round_id: str,
        learner_id: str,
        lease_id: str,
        submission_key: str,
        position: int,
        case_id: str,
        response: dict[str, Any],
        grade: dict[str, Any],
        tutor: dict[str, Any] | None,
        trace_grade: dict[str, Any] | None,
        tested_objective_manifest: dict[str, Any],
        confidence: int,
        result: dict[str, Any],
        receipts: list[dict[str, Any]],
        receipt_events: dict[int, dict[str, Any]],
        submitted_at: datetime | str,
        planned_timed_out: bool,
    ) -> dict[str, Any]:
        """Commit the claimed Rapid item and normalized evidence exactly once."""

        submitted_dt = _utc(submitted_at)
        submitted_iso = submitted_dt.isoformat()
        try:
            with self.store.connect() as conn:
                if not conn.in_transaction:
                    conn.execute("BEGIN IMMEDIATE")
                existing = conn.execute(
                    "SELECT * FROM rapid_round_answers WHERE round_id = ? AND case_id = ?",
                    (round_id, case_id),
                ).fetchone()
                if existing:
                    answer = self.store._rapid_answer_dict(existing)
                    if (
                        answer["integrityStatus"] in {"legacy_incomplete", "finalizing"}
                        or not answer["receipts"]
                    ):
                        return {"status": "legacy_incomplete", "answer": answer}
                    return {"status": "replay", "answer": answer}
                session = conn.execute(
                    "SELECT * FROM rapid_rounds WHERE round_id = ?", (round_id,)
                ).fetchone()
                if session is None or str(session["learner_id"]) != learner_id:
                    return {"status": "missing"}
                if session["pending_case_id"] != case_id or session["status"] != "active":
                    return {"status": "not_pending", "pendingCaseId": session["pending_case_id"]}
                if int(session["position"]) != position:
                    release_submission(
                        conn,
                        lease_id=lease_id,
                        owner_id=learner_id,
                        submission_key=submission_key,
                        released_at=submitted_iso,
                    )
                    return {"status": "position_mismatch"}

                lease_contract = conn.execute(
                    "SELECT leases.*, cases.ecg_id FROM assessment_leases AS leases "
                    "JOIN assessment_lease_cases AS cases "
                    "ON cases.lease_id = leases.lease_id AND cases.ordinal = 0 "
                    "WHERE leases.lease_id = ? AND leases.owner_id = ? "
                    "AND leases.mode = 'rapid' AND leases.session_id = ? "
                    "AND cases.ecg_id = ?",
                    (lease_id, learner_id, round_id, case_id),
                ).fetchone()
                if lease_contract is None:
                    raise LeaseNotFoundError(
                        "Rapid answer reservation is not owned by this round"
                    )

                frozen_manifest = json.loads(session["pending_manifest_json"] or "{}")
                frozen_keys = (
                    "version",
                    "caseId",
                    "assessmentScope",
                    "taskKind",
                    "objectives",
                    "allowSelectedExtras",
                    "overcallPolicy",
                )
                if not frozen_manifest or any(
                    frozen_manifest.get(key) != tested_objective_manifest.get(key)
                    for key in frozen_keys
                ):
                    release_submission(
                        conn,
                        lease_id=lease_id,
                        owner_id=learner_id,
                        submission_key=submission_key,
                        released_at=submitted_iso,
                    )
                    return {"status": "manifest_mismatch"}

                started_at = session["pending_started_at"] or submitted_iso
                deadline_at = session["pending_deadline_at"]
                if not session["pending_started_at"] and session["deadline_seconds"] is not None:
                    deadline_at = (
                        submitted_dt + timedelta(seconds=int(session["deadline_seconds"]))
                    ).isoformat()
                started_dt = _utc(str(started_at))
                try:
                    deadline_dt = _utc(str(deadline_at)) if deadline_at else None
                except ValueError:
                    deadline_dt = submitted_dt
                response_ms = max(
                    0, int((submitted_dt - started_dt).total_seconds() * 1000)
                )
                timed_out = bool(deadline_dt and submitted_dt >= deadline_dt)
                if timed_out != bool(planned_timed_out):
                    release_submission(
                        conn,
                        lease_id=lease_id,
                        owner_id=learner_id,
                        submission_key=submission_key,
                        released_at=submitted_iso,
                    )
                    return {"status": "deadline_state_mismatch"}

                durable_result = {
                    **result,
                    "timedOut": timed_out,
                    "responseMs": response_ms,
                    "pace": session["pace"],
                    "assessmentScope": session["assessment_scope"],
                    "startedAt": started_at,
                    "deadlineAt": deadline_at,
                    "submittedAt": submitted_iso,
                }
                durable_response = {
                    **response,
                    "pace": session["pace"],
                    "assessmentScope": session["assessment_scope"],
                    "serverStartedAt": started_at,
                    "serverDeadlineAt": deadline_at,
                }
                attempt_id = self.store._save_attempt_in_transaction(
                    conn,
                    learner_id=learner_id,
                    case_id=case_id,
                    mode="rapid_practice",
                    structured_answer=response.get("structuredAnswer") or {},
                    confidence=confidence,
                    grade=grade,
                    now=submitted_iso,
                )
                self.store._rapid_finalization_checkpoint("after_attempt")
                cursor = conn.execute(
                    "INSERT INTO rapid_round_answers ("
                    "round_id, case_id, response_json, grade_json, tutor_json, "
                    "result_json, trace_grade_json, tested_manifest_json, "
                    "receipts_json, integrity_status, attempt_id, created_at"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, '[]', 'finalizing', ?, ?)",
                    (
                        round_id,
                        case_id,
                        json.dumps(durable_response),
                        json.dumps(grade),
                        json.dumps(tutor),
                        json.dumps(durable_result),
                        json.dumps(trace_grade) if trace_grade is not None else None,
                        json.dumps(tested_objective_manifest),
                        attempt_id,
                        submitted_iso,
                    ),
                )
                answer_id = int(cursor.lastrowid)
                self.store._rapid_finalization_checkpoint("after_answer")

                if not receipts:
                    raise ValueError(
                        "A verified Rapid answer requires an explicit receipt ledger"
                    )
                event_indexes = set(receipt_events)
                if any(
                    not isinstance(index, int)
                    or index < 0
                    or index >= len(receipts)
                    for index in event_indexes
                ):
                    raise ValueError("Rapid receipt event index is outside the receipt ledger")
                durable_receipts: list[dict[str, Any]] = []
                for index, source_receipt in enumerate(receipts):
                    receipt = dict(source_receipt)
                    event = receipt_events.get(index)
                    if event is not None:
                        event_result = self.store.save_guided_learning_event(
                            learner_id,
                            event,
                            occurred_at=submitted_dt,
                            _connection=conn,
                        )
                        if event_result.get("replay"):
                            raise RuntimeError(
                                "A Rapid receipt exists without its complete atomic answer"
                            )
                        receipt["evidenceLevel"] = event_result[
                            "effectiveEvidenceLevel"
                        ]
                    durable_receipts.append(receipt)
                    self.store._rapid_finalization_checkpoint(f"after_receipt:{index}")

                normalized_score = max(
                    0.0, min(1.0, float(result.get("score", 0.0)))
                )
                append_event(
                    conn,
                    event_id=self._answer_event_id(round_id, position, case_id),
                    owner_id=learner_id,
                    mode="rapid",
                    session_id=round_id,
                    lease_id=lease_id,
                    ecg_id=case_id,
                    event_type="answer_committed",
                    evidence_level="independent_transfer",
                    integrity_status=str(lease_contract["integrity_status"]),
                    score=normalized_score,
                    competencies=self._competency_evidence(receipt_events),
                    submission_key=submission_key,
                    occurred_at=submitted_iso,
                )
                self.store._rapid_finalization_checkpoint("after_learner_event")
                mark_submitted(
                    conn,
                    lease_id=lease_id,
                    owner_id=learner_id,
                    submission_key=submission_key,
                    submitted_at=submitted_iso,
                )
                self.store._rapid_finalization_checkpoint("after_lease_submitted")
                promoted = conn.execute(
                    "UPDATE rapid_round_answers SET receipts_json = ?, "
                    "integrity_status = 'atomic_v2' "
                    "WHERE id = ? AND integrity_status = 'finalizing'",
                    (json.dumps(durable_receipts), answer_id),
                )
                if promoted.rowcount != 1:
                    raise RuntimeError(
                        "Rapid answer receipt promotion lost its finalizing boundary"
                    )
                self.store._rapid_finalization_checkpoint("after_receipts_persisted")

                served = json.loads(session["served_json"] or "[]")
                if case_id not in served:
                    served.append(case_id)
                next_position = int(
                    conn.execute(
                        "SELECT COUNT(*) AS n FROM rapid_round_answers WHERE round_id = ?",
                        (round_id,),
                    ).fetchone()["n"]
                )
                status = (
                    "complete"
                    if next_position >= int(session["length"])
                    else "active"
                )
                advanced = conn.execute(
                    "UPDATE rapid_rounds SET served_json = ?, pending_case_id = NULL, "
                    "feedback_case_id = ?, pending_started_at = NULL, "
                    "pending_deadline_at = NULL, pending_manifest_json = '{}', "
                    "position = ?, status = ?, updated_at = ? "
                    "WHERE round_id = ? AND learner_id = ? AND position = ? "
                    "AND pending_case_id = ? AND status = 'active'",
                    (
                        json.dumps(served),
                        case_id,
                        next_position,
                        status,
                        submitted_iso,
                        round_id,
                        learner_id,
                        position,
                        case_id,
                    ),
                )
                if advanced.rowcount != 1:
                    raise RuntimeError("Rapid round advance lost its pending-item boundary")
                self.store._rapid_finalization_checkpoint("after_round_advance")
                answer_row = conn.execute(
                    "SELECT * FROM rapid_round_answers WHERE id = ?", (answer_id,)
                ).fetchone()
                return {
                    "status": "recorded",
                    "answer": self.store._rapid_answer_dict(answer_row),
                }
        except Exception:
            # The answer transaction has rolled back. Release only the exact
            # reservation generation; a concurrent submit/abandon is terminal
            # and will be left untouched by the best-effort helper.
            self.release_answer_submission(
                round_id=round_id,
                learner_id=learner_id,
                lease_id=lease_id,
                submission_key=submission_key,
            )
            raise
