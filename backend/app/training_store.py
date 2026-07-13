"""Durable, server-owned Training campaign ledger.

Campaign plans are immutable: every slot receives a unique real PTB case, phase,
and contrast focus at creation. Runtime state only advances slot status and the
campaign cursor. This keeps 5,000-case campaigns resumable without shipping a
5,000-id exclusion list through the browser.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, ContextManager


def _now() -> str:
    return datetime.now(UTC).isoformat()


class TrainingCampaignStore:
    def __init__(
        self,
        db_path: Path | str,
        connection_provider: Callable[[], ContextManager[sqlite3.Connection]] | None = None,
    ):
        self.db_path = str(db_path)
        self._connection_provider = connection_provider
        self._lock = threading.Lock()
        self._memory_conn = (
            sqlite3.connect(":memory:", check_same_thread=False)
            if self.db_path == ":memory:" and connection_provider is None
            else None
        )
        if self._memory_conn is not None:
            self._memory_conn.row_factory = sqlite3.Row
        self.init_db()

    @contextmanager
    def connect(self):
        if self._connection_provider is not None:
            with self._connection_provider() as conn:
                yield conn
            return
        if self._memory_conn is not None:
            with self._lock:
                yield self._memory_conn
                self._memory_conn.commit()
            return
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=10000")
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.OperationalError:
            pass
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS training_campaigns (
                    campaign_id TEXT PRIMARY KEY,
                    learner_id TEXT NOT NULL,
                    concept_id TEXT NOT NULL,
                    subskill TEXT NOT NULL,
                    requested_length INTEGER NOT NULL,
                    length INTEGER NOT NULL,
                    pool_count INTEGER NOT NULL,
                    phases_json TEXT NOT NULL,
                    phase_counts_json TEXT NOT NULL,
                    position INTEGER NOT NULL DEFAULT 0,
                    pending_case_id TEXT,
                    feedback_case_id TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    context_key TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    abandoned_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_training_campaign_active
                    ON training_campaigns(learner_id, status, updated_at);

                CREATE TABLE IF NOT EXISTS training_campaign_slots (
                    campaign_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    phase TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    case_focus TEXT NOT NULL,
                    target_present INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    served_at TEXT,
                    answered_at TEXT,
                    PRIMARY KEY (campaign_id, ordinal),
                    UNIQUE (campaign_id, case_id),
                    FOREIGN KEY (campaign_id) REFERENCES training_campaigns(campaign_id)
                );
                CREATE INDEX IF NOT EXISTS idx_training_slot_case
                    ON training_campaign_slots(campaign_id, case_id);

                CREATE TABLE IF NOT EXISTS training_campaign_answers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    case_id TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    grade_json TEXT NOT NULL,
                    tutor_json TEXT NOT NULL,
                    receipt_json TEXT NOT NULL,
                    summary_json TEXT NOT NULL,
                    attempt_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (campaign_id, ordinal),
                    UNIQUE (campaign_id, case_id),
                    FOREIGN KEY (campaign_id) REFERENCES training_campaigns(campaign_id)
                );
                CREATE INDEX IF NOT EXISTS idx_training_answer_campaign
                    ON training_campaign_answers(campaign_id, ordinal);
                """
            )

    @staticmethod
    def _campaign(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "campaignId": row["campaign_id"],
            "learnerId": row["learner_id"],
            "conceptId": row["concept_id"],
            "subskill": row["subskill"],
            "requestedLength": int(row["requested_length"]),
            "length": int(row["length"]),
            "poolCount": int(row["pool_count"]),
            "phases": json.loads(row["phases_json"]),
            "phaseCounts": json.loads(row["phase_counts_json"]),
            "position": int(row["position"]),
            "pendingCaseId": row["pending_case_id"],
            "feedbackCaseId": row["feedback_case_id"],
            "status": row["status"],
            "contextKey": row["context_key"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "abandonedAt": row["abandoned_at"],
        }

    @staticmethod
    def _slot(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "position": int(row["ordinal"]),
            "phase": row["phase"],
            "caseId": row["case_id"],
            "caseFocus": row["case_focus"],
            "targetPresent": bool(row["target_present"]),
            "status": row["status"],
            "servedAt": row["served_at"],
            "answeredAt": row["answered_at"],
        }

    @staticmethod
    def _answer(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "answerId": int(row["id"]),
            "campaignId": row["campaign_id"],
            "position": int(row["ordinal"]),
            "caseId": row["case_id"],
            "response": json.loads(row["response_json"]),
            "grade": json.loads(row["grade_json"]),
            "tutor": json.loads(row["tutor_json"]),
            "receipt": json.loads(row["receipt_json"]),
            "summary": json.loads(row["summary_json"]),
            "attemptId": int(row["attempt_id"]),
            "createdAt": row["created_at"],
        }

    def create_campaign(
        self,
        learner_id: str,
        concept_id: str,
        subskill: str,
        requested_length: int,
        pool_count: int,
        plan: list[dict[str, Any]],
        *,
        context_key: str = "",
    ) -> dict[str, Any]:
        if not plan:
            raise ValueError("Training campaign plan cannot be empty")
        case_ids = [str(slot["caseId"]) for slot in plan]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("Training campaign cases must be unique")
        phases = [str(slot["phase"]) for slot in plan]
        phase_counts = {phase: phases.count(phase) for phase in ("target", "mimic", "negative", "transfer")}
        campaign_id = f"tc_{uuid.uuid4().hex[:20]}"
        now = _now()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO training_campaigns (
                    campaign_id, learner_id, concept_id, subskill, requested_length,
                    length, pool_count, phases_json, phase_counts_json, position,
                    status, context_key, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'active', ?, ?, ?)
                """,
                (
                    campaign_id, learner_id, concept_id, subskill, requested_length,
                    len(plan), pool_count, json.dumps(phases), json.dumps(phase_counts),
                    context_key, now, now,
                ),
            )
            conn.executemany(
                """
                INSERT INTO training_campaign_slots (
                    campaign_id, ordinal, phase, case_id, case_focus, target_present, status
                ) VALUES (?, ?, ?, ?, ?, ?, 'queued')
                """,
                [
                    (
                        campaign_id, index, slot["phase"], str(slot["caseId"]),
                        str(slot["caseFocus"]), 1 if slot["targetPresent"] else 0,
                    )
                    for index, slot in enumerate(plan)
                ],
            )
        return self.get_campaign(campaign_id)  # type: ignore[return-value]

    def get_campaign(self, campaign_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM training_campaigns WHERE campaign_id = ?", (campaign_id,)
            ).fetchone()
        return self._campaign(row) if row else None

    def get_active(self, learner_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM training_campaigns WHERE learner_id = ? "
                "AND (status = 'active' OR feedback_case_id IS NOT NULL) "
                "ORDER BY updated_at DESC LIMIT 1",
                (learner_id,),
            ).fetchone()
        return self._campaign(row) if row else None

    def get_slot(self, campaign_id: str, position: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM training_campaign_slots WHERE campaign_id = ? AND ordinal = ?",
                (campaign_id, position),
            ).fetchone()
        return self._slot(row) if row else None

    def get_slot_for_case(self, campaign_id: str, case_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM training_campaign_slots WHERE campaign_id = ? AND case_id = ?",
                (campaign_id, case_id),
            ).fetchone()
        return self._slot(row) if row else None

    def claim_next(self, campaign_id: str) -> dict[str, Any] | None:
        now = _now()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            campaign = conn.execute(
                "SELECT * FROM training_campaigns WHERE campaign_id = ?", (campaign_id,)
            ).fetchone()
            if not campaign:
                return None
            if campaign["pending_case_id"] or campaign["feedback_case_id"]:
                return self._campaign(campaign)
            position = int(campaign["position"])
            if campaign["status"] != "active" or position >= int(campaign["length"]):
                return self._campaign(campaign)
            slot = conn.execute(
                "SELECT case_id FROM training_campaign_slots WHERE campaign_id = ? AND ordinal = ?",
                (campaign_id, position),
            ).fetchone()
            if not slot:
                return self._campaign(campaign)
            conn.execute(
                "UPDATE training_campaign_slots SET status = 'pending', served_at = COALESCE(served_at, ?) "
                "WHERE campaign_id = ? AND ordinal = ? AND status = 'queued'",
                (now, campaign_id, position),
            )
            conn.execute(
                "UPDATE training_campaigns SET pending_case_id = ?, updated_at = ? "
                "WHERE campaign_id = ? AND pending_case_id IS NULL AND feedback_case_id IS NULL",
                (slot["case_id"], now, campaign_id),
            )
        return self.get_campaign(campaign_id)

    def acknowledge_feedback(self, campaign_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE training_campaigns SET feedback_case_id = NULL, updated_at = ? "
                "WHERE campaign_id = ?",
                (_now(), campaign_id),
            )
        return self.get_campaign(campaign_id)

    def get_answer(self, campaign_id: str, case_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM training_campaign_answers WHERE campaign_id = ? AND case_id = ?",
                (campaign_id, case_id),
            ).fetchone()
        return self._answer(row) if row else None

    def record_answer(
        self,
        *,
        campaign_id: str,
        case_id: str,
        response: dict[str, Any],
        grade: dict[str, Any],
        tutor: dict[str, Any] | None,
        receipt: dict[str, Any],
        summary: dict[str, Any],
        confidence: int,
        hints_used: int,
    ) -> dict[str, Any]:
        now = _now()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM training_campaign_answers WHERE campaign_id = ? AND case_id = ?",
                (campaign_id, case_id),
            ).fetchone()
            if existing:
                return {"status": "replay", "answer": self._answer(existing)}
            campaign = conn.execute(
                "SELECT * FROM training_campaigns WHERE campaign_id = ?", (campaign_id,)
            ).fetchone()
            if not campaign:
                return {"status": "missing"}
            position = int(campaign["position"])
            if campaign["status"] != "active" or campaign["pending_case_id"] != case_id:
                return {
                    "status": "not_pending",
                    "pendingCaseId": campaign["pending_case_id"],
                }
            slot = conn.execute(
                "SELECT * FROM training_campaign_slots WHERE campaign_id = ? AND ordinal = ?",
                (campaign_id, position),
            ).fetchone()
            if not slot or slot["case_id"] != case_id:
                return {"status": "not_pending", "pendingCaseId": campaign["pending_case_id"]}

            # Generic attempt audit is inserted in the same transaction as the
            # campaign answer. Training mastery remains exclusively controlled
            # by the idempotent guided-event receipt and its evidence ceiling.
            attempt_cursor = conn.execute(
                """
                INSERT INTO attempts (
                    learner_id, case_id, mode, structured_answer_json, free_text_answer,
                    confidence, hints_used, score, correct_objectives_json,
                    missed_objectives_json, misconception_tags_json, feedback, created_at
                ) VALUES (?, ?, 'concept_practice', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    campaign["learner_id"], case_id,
                    json.dumps(response.get("structuredAnswer") or {}),
                    str(response.get("freeTextAnswer") or ""), confidence, hints_used,
                    float(grade.get("score", 0.0)),
                    json.dumps(grade.get("correctObjectives") or []),
                    json.dumps(grade.get("missedObjectives") or []),
                    json.dumps(grade.get("misconceptions") or []),
                    str(grade.get("feedback") or ""), now,
                ),
            )
            answer_cursor = conn.execute(
                """
                INSERT INTO training_campaign_answers (
                    campaign_id, ordinal, case_id, response_json, grade_json,
                    tutor_json, receipt_json, summary_json, attempt_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    campaign_id, position, case_id, json.dumps(response), json.dumps(grade),
                    json.dumps(tutor), json.dumps(receipt), json.dumps(summary),
                    int(attempt_cursor.lastrowid), now,
                ),
            )
            conn.execute(
                "UPDATE training_campaign_slots SET status = 'answered', answered_at = ? "
                "WHERE campaign_id = ? AND ordinal = ?",
                (now, campaign_id, position),
            )
            next_position = position + 1
            status = "complete" if next_position >= int(campaign["length"]) else "active"
            conn.execute(
                "UPDATE training_campaigns SET position = ?, pending_case_id = NULL, "
                "feedback_case_id = ?, status = ?, updated_at = ? WHERE campaign_id = ?",
                (next_position, case_id, status, now, campaign_id),
            )
            row = conn.execute(
                "SELECT * FROM training_campaign_answers WHERE id = ?", (answer_cursor.lastrowid,)
            ).fetchone()
        return {"status": "recorded", "answer": self._answer(row)}

    def summary(self, campaign_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT summary_json FROM training_campaign_answers WHERE campaign_id = ? ORDER BY ordinal",
                (campaign_id,),
            ).fetchall()
        attempts = [json.loads(row["summary_json"]) for row in rows]
        by_phase: dict[str, dict[str, int]] = {
            phase: {"attempted": 0, "correct": 0}
            for phase in ("target", "mimic", "negative", "transfer")
        }
        for attempt in attempts:
            phase = str(attempt.get("phase") or "transfer")
            bucket = by_phase.setdefault(phase, {"attempted": 0, "correct": 0})
            bucket["attempted"] += 1
            bucket["correct"] += 1 if attempt.get("correct") else 0
        return {
            "attempted": len(attempts),
            "correct": sum(1 for attempt in attempts if attempt.get("correct")),
            "independentReceipts": sum(
                1 for attempt in attempts if attempt.get("evidenceLevel") == "independent_transfer"
            ),
            "byPhase": by_phase,
            "recent": attempts[-25:],
        }

    def abandon(self, campaign_id: str) -> dict[str, Any] | None:
        now = _now()
        with self.connect() as conn:
            conn.execute(
                "UPDATE training_campaigns SET status = 'abandoned', pending_case_id = NULL, "
                "feedback_case_id = NULL, abandoned_at = ?, updated_at = ? "
                "WHERE campaign_id = ? AND status != 'abandoned'",
                (now, now, campaign_id),
            )
        return self.get_campaign(campaign_id)

    def all_slots(self, campaign_id: str) -> list[dict[str, Any]]:
        """Test/diagnostic read of the immutable campaign ledger."""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM training_campaign_slots WHERE campaign_id = ? ORDER BY ordinal",
                (campaign_id,),
            ).fetchall()
        return [self._slot(row) for row in rows]
