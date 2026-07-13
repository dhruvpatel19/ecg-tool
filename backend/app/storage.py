from __future__ import annotations

import json
import sqlite3
import threading
import hashlib
import hmac
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from .ontology import DEFAULT_MASTERY
from .objectives import (
    DYNAMIC_SOURCE_UNAVAILABLE,
    audited_source_packet_supports_objective,
    objective_definition,
)
from .retention import due_snapshot, parse_instant, retention_uncertainty, update_retention


_PATHWAY_STATUS_RANK = {
    "not-started": 0,
    "viewed": 1,
    "skipped": 1,
    "attempted": 2,
    "needs-review": 3,
    "complete": 4,
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class LearningStore:
    def __init__(self, db_path: Path | str):
        self.db_path = str(db_path)
        self._memory_conn: sqlite3.Connection | None = None
        self._case_packet_provider: Callable[[str], dict[str, Any] | None] | None = None
        # Serializes the shared in-memory connection across FastAPI's threadpool so
        # concurrent read-modify-write transactions can't interleave (V1 audit fix).
        self._lock = threading.Lock()
        if self.db_path == ":memory:":
            self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._memory_conn.row_factory = sqlite3.Row
        self.init_db()

    def set_case_packet_provider(
        self, provider: Callable[[str], dict[str, Any] | None]
    ) -> None:
        """Bind the read-only corpus lookup used by dynamic evidence ceilings.

        The store defaults to fail-closed when no provider is bound. Routers may
        call this repeatedly with the same repository method; no corpus state is
        mutated.
        """

        self._case_packet_provider = provider

    @contextmanager
    def connect(self):
        if self._memory_conn is not None:
            with self._lock:
                yield self._memory_conn
                self._memory_conn.commit()
            return
        # File-backed: WAL + a busy timeout so concurrent writers wait instead of
        # raising "database is locked" (V1 audit fix).
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
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
                CREATE TABLE IF NOT EXISTS learner_profiles (
                    learner_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS objective_mastery (
                    learner_id TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    mastery REAL NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    correct INTEGER NOT NULL DEFAULT 0,
                    high_confidence_wrong INTEGER NOT NULL DEFAULT 0,
                    last_practiced_at TEXT,
                    PRIMARY KEY (learner_id, objective)
                );

                CREATE TABLE IF NOT EXISTS attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    learner_id TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    structured_answer_json TEXT NOT NULL,
                    free_text_answer TEXT NOT NULL,
                    confidence INTEGER NOT NULL,
                    hints_used INTEGER NOT NULL,
                    score REAL NOT NULL,
                    correct_objectives_json TEXT NOT NULL,
                    missed_objectives_json TEXT NOT NULL,
                    misconception_tags_json TEXT NOT NULL,
                    feedback TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS subskill_mastery (
                    learner_id TEXT NOT NULL,
                    concept TEXT NOT NULL,
                    subskill TEXT NOT NULL,
                    formative_score REAL NOT NULL DEFAULT 0.0,
                    independent_mastery REAL NOT NULL DEFAULT 0.15,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    independent_attempts INTEGER NOT NULL DEFAULT 0,
                    correct INTEGER NOT NULL DEFAULT 0,
                    high_confidence_wrong INTEGER NOT NULL DEFAULT 0,
                    last_practiced_at TEXT,
                    next_due_at TEXT,
                    stability_days REAL NOT NULL DEFAULT 0.0,
                    lapses INTEGER NOT NULL DEFAULT 0,
                    spaced_retrievals INTEGER NOT NULL DEFAULT 0,
                    distinct_eligible_ecgs INTEGER NOT NULL DEFAULT 0,
                    distinct_successful_ecgs INTEGER NOT NULL DEFAULT 0,
                    distinct_modes INTEGER NOT NULL DEFAULT 0,
                    distinct_morphologies INTEGER NOT NULL DEFAULT 0,
                    last_independent_at TEXT,
                    last_independent_correct INTEGER,
                    PRIMARY KEY (learner_id, concept, subskill)
                );

                CREATE TABLE IF NOT EXISTS subskill_retention_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guided_event_id INTEGER NOT NULL,
                    learner_id TEXT NOT NULL,
                    concept TEXT NOT NULL,
                    subskill TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    morphology_key TEXT,
                    correct INTEGER NOT NULL,
                    occurred_at TEXT NOT NULL,
                    UNIQUE(guided_event_id, subskill)
                );
                CREATE INDEX IF NOT EXISTS idx_retention_competency
                    ON subskill_retention_events(learner_id, concept, subskill, occurred_at);

                CREATE TABLE IF NOT EXISTS guided_learning_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    learner_id TEXT NOT NULL,
                    module_id TEXT NOT NULL,
                    scene_id TEXT NOT NULL,
                    interaction_id TEXT NOT NULL,
                    concept TEXT NOT NULL,
                    subskills_json TEXT NOT NULL,
                    score REAL NOT NULL,
                    correct INTEGER NOT NULL,
                    attempts INTEGER NOT NULL,
                    assistance TEXT NOT NULL,
                    hints_used INTEGER NOT NULL DEFAULT 0,
                    confidence INTEGER,
                    requested_evidence_level TEXT NOT NULL,
                    effective_evidence_level TEXT NOT NULL,
                    case_id TEXT,
                    case_provenance TEXT NOT NULL,
                    case_eligible INTEGER NOT NULL,
                    misconception_tags_json TEXT NOT NULL DEFAULT '[]',
                    event_key TEXT,
                    receipt_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_guided_event_learner ON guided_learning_events(learner_id, created_at);

                CREATE TABLE IF NOT EXISTS pathway_progress (
                    learner_id TEXT NOT NULL,
                    pathway_id TEXT NOT NULL,
                    module_id TEXT NOT NULL,
                    scene_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    active_interaction_index INTEGER NOT NULL DEFAULT 0,
                    completed_action_ids_json TEXT NOT NULL DEFAULT '[]',
                    state_json TEXT NOT NULL DEFAULT '{}',
                    source TEXT NOT NULL DEFAULT 'server',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (learner_id, pathway_id, module_id, scene_id)
                );
                CREATE INDEX IF NOT EXISTS idx_pathway_progress_learner
                    ON pathway_progress(learner_id, pathway_id, updated_at);

                CREATE TABLE IF NOT EXISTS tutor_threads (
                    thread_id TEXT PRIMARY KEY,
                    learner_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    lesson_id TEXT,
                    case_id TEXT,
                    title TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_thread_learner ON tutor_threads(learner_id, updated_at);

                CREATE TABLE IF NOT EXISTS tutor_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    actions_json TEXT NOT NULL DEFAULT '[]',
                    meta_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_msg_thread ON tutor_messages(thread_id, id);

                CREATE TABLE IF NOT EXISTS remote_tutor_quota_buckets (
                    scope TEXT NOT NULL,
                    key_hash TEXT NOT NULL,
                    window_start TEXT NOT NULL,
                    request_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (scope, key_hash, window_start)
                );
                CREATE INDEX IF NOT EXISTS idx_remote_tutor_quota_updated
                    ON remote_tutor_quota_buckets(updated_at);

                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

                CREATE TABLE IF NOT EXISTS auth_registration_throttle (
                    scope TEXT NOT NULL,
                    key_hash TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    window_started_at TEXT NOT NULL,
                    blocked_until TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (scope, key_hash)
                );
                CREATE INDEX IF NOT EXISTS idx_registration_throttle_updated
                    ON auth_registration_throttle(updated_at);

                CREATE TABLE IF NOT EXISTS auth_login_throttle (
                    scope TEXT NOT NULL,
                    key_hash TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    window_started_at TEXT NOT NULL,
                    blocked_until TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (scope, key_hash)
                );
                CREATE INDEX IF NOT EXISTS idx_login_throttle_updated
                    ON auth_login_throttle(updated_at);

                CREATE TABLE IF NOT EXISTS review_sessions (
                    session_id TEXT PRIMARY KEY,
                    learner_id TEXT NOT NULL,
                    label TEXT,
                    objectives_json TEXT NOT NULL DEFAULT '[]',
                    target_mastery REAL NOT NULL DEFAULT 0.8,
                    max_cases INTEGER NOT NULL DEFAULT 30,
                    served_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_review_learner ON review_sessions(learner_id, status);

                CREATE TABLE IF NOT EXISTS rapid_rounds (
                    round_id TEXT PRIMARY KEY,
                    learner_id TEXT NOT NULL,
                    pace TEXT NOT NULL,
                    length INTEGER NOT NULL,
                    assessment_scope TEXT NOT NULL,
                    focus_concept TEXT,
                    focus_subskill TEXT,
                    context_key TEXT NOT NULL DEFAULT '',
                    exclusions_json TEXT NOT NULL DEFAULT '[]',
                    served_json TEXT NOT NULL DEFAULT '[]',
                    pending_case_id TEXT,
                    feedback_case_id TEXT,
                    pending_started_at TEXT,
                    pending_deadline_at TEXT,
                    deadline_seconds INTEGER,
                    position INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_rapid_round_learner
                    ON rapid_rounds(learner_id, status, updated_at);

                CREATE TABLE IF NOT EXISTS rapid_round_answers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    round_id TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    grade_json TEXT NOT NULL,
                    tutor_json TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT NOT NULL,
                    trace_grade_json TEXT,
                    receipts_json TEXT NOT NULL DEFAULT '[]',
                    attempt_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(round_id, case_id)
                );
                CREATE INDEX IF NOT EXISTS idx_rapid_answers_round
                    ON rapid_round_answers(round_id, id);

                CREATE TABLE IF NOT EXISTS clinical_shift_sessions (
                    session_id TEXT PRIMARY KEY,
                    learner_id TEXT NOT NULL,
                    lane TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    focus_objective TEXT,
                    focus_subskill TEXT,
                    length INTEGER NOT NULL DEFAULT 5,
                    requested_length INTEGER NOT NULL DEFAULT 5,
                    available_length INTEGER NOT NULL DEFAULT 0,
                    length_reason TEXT,
                    served_json TEXT NOT NULL DEFAULT '[]',
                    served_ecgs_json TEXT NOT NULL DEFAULT '[]',
                    calibration_json TEXT NOT NULL DEFAULT '[]',
                    pending_item_id TEXT,
                    feedback_item_id TEXT,
                    pending_context_revealed INTEGER NOT NULL DEFAULT 0,
                    pending_first_look_json TEXT,
                    pending_orient_started_at TEXT,
                    pending_orient_deadline_at TEXT,
                    pending_decide_started_at TEXT,
                    pending_decide_deadline_at TEXT,
                    pending_decide_submitted_at TEXT,
                    position INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_shift_learner ON clinical_shift_sessions(learner_id, status);

                CREATE TABLE IF NOT EXISTS clinical_shift_answers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    ecg_id TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    grade_json TEXT NOT NULL,
                    receipts_json TEXT NOT NULL DEFAULT '[]',
                    score REAL NOT NULL,
                    correct INTEGER NOT NULL,
                    answer_time_ms INTEGER,
                    calibration_event_json TEXT,
                    attempt_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(session_id, item_id)
                );
                CREATE INDEX IF NOT EXISTS idx_shift_answers_session
                    ON clinical_shift_answers(session_id, id);
                """
            )
            # Session credentials are stored only as SHA-256 lookup digests.
            # Invalidate pre-migration plaintext tokens instead of retaining a
            # raw reusable browser credential in the learner database.
            conn.execute(
                "DELETE FROM sessions WHERE length(token) != 64 "
                "OR token GLOB '*[^0-9a-f]*'"
            )
            # Additive migration for shift sessions created before guided→Clinical
            # handoffs carried a target objective.
            shift_columns = {row["name"] for row in conn.execute("PRAGMA table_info(clinical_shift_sessions)")}
            if "focus_objective" not in shift_columns:
                conn.execute("ALTER TABLE clinical_shift_sessions ADD COLUMN focus_objective TEXT")
            if "focus_subskill" not in shift_columns:
                conn.execute("ALTER TABLE clinical_shift_sessions ADD COLUMN focus_subskill TEXT")
            requested_length_was_missing = "requested_length" not in shift_columns
            additive_shift_columns = {
                "requested_length": "INTEGER NOT NULL DEFAULT 5",
                "available_length": "INTEGER NOT NULL DEFAULT 0",
                "length_reason": "TEXT",
                "served_ecgs_json": "TEXT NOT NULL DEFAULT '[]'",
                "pending_item_id": "TEXT",
                "feedback_item_id": "TEXT",
                "pending_context_revealed": "INTEGER NOT NULL DEFAULT 0",
                "pending_first_look_json": "TEXT",
                "pending_orient_started_at": "TEXT",
                "pending_orient_deadline_at": "TEXT",
                "pending_decide_started_at": "TEXT",
                "pending_decide_deadline_at": "TEXT",
                "pending_decide_submitted_at": "TEXT",
            }
            for name, declaration in additive_shift_columns.items():
                if name not in shift_columns:
                    conn.execute(f"ALTER TABLE clinical_shift_sessions ADD COLUMN {name} {declaration}")
            # Existing sessions predate explicit request/availability metadata. Preserve
            # their effective length as the requested length rather than reporting the
            # migration default of five.
            if requested_length_was_missing:
                conn.execute("UPDATE clinical_shift_sessions SET requested_length = length")

            shift_answer_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(clinical_shift_answers)")
            }
            if "receipts_json" not in shift_answer_columns:
                conn.execute(
                    "ALTER TABLE clinical_shift_answers "
                    "ADD COLUMN receipts_json TEXT NOT NULL DEFAULT '[]'"
                )

            guided_columns = {row["name"] for row in conn.execute("PRAGMA table_info(guided_learning_events)")}
            if "event_key" not in guided_columns:
                conn.execute("ALTER TABLE guided_learning_events ADD COLUMN event_key TEXT")
            if "receipt_json" not in guided_columns:
                conn.execute("ALTER TABLE guided_learning_events ADD COLUMN receipt_json TEXT NOT NULL DEFAULT '[]'")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_guided_event_idempotency "
                "ON guided_learning_events(learner_id, event_key) WHERE event_key IS NOT NULL"
            )

            subskill_columns = {row["name"] for row in conn.execute("PRAGMA table_info(subskill_mastery)")}
            additive_retention_columns = {
                "next_due_at": "TEXT",
                "stability_days": "REAL NOT NULL DEFAULT 0.0",
                "lapses": "INTEGER NOT NULL DEFAULT 0",
                "spaced_retrievals": "INTEGER NOT NULL DEFAULT 0",
                "distinct_eligible_ecgs": "INTEGER NOT NULL DEFAULT 0",
                "distinct_successful_ecgs": "INTEGER NOT NULL DEFAULT 0",
                "distinct_modes": "INTEGER NOT NULL DEFAULT 0",
                "distinct_morphologies": "INTEGER NOT NULL DEFAULT 0",
                "last_independent_at": "TEXT",
                "last_independent_correct": "INTEGER",
            }
            for name, declaration in additive_retention_columns.items():
                if name not in subskill_columns:
                    conn.execute(f"ALTER TABLE subskill_mastery ADD COLUMN {name} {declaration}")

    def ensure_profile(self, learner_id: str = "demo", display_name: str | None = None) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT learner_id, display_name, created_at, updated_at FROM learner_profiles WHERE learner_id = ?",
                (learner_id,),
            ).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO learner_profiles (learner_id, display_name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (learner_id, display_name or "Demo Learner", now, now),
                )
                for objective, mastery in DEFAULT_MASTERY.items():
                    conn.execute(
                        "INSERT OR IGNORE INTO objective_mastery (learner_id, objective, mastery) VALUES (?, ?, ?)",
                        (learner_id, objective, mastery),
                    )
            elif display_name and display_name != existing["display_name"]:
                conn.execute(
                    "UPDATE learner_profiles SET display_name = ?, updated_at = ? WHERE learner_id = ?",
                    (display_name, now, learner_id),
                )
        return self.get_profile(learner_id)

    def get_profile(self, learner_id: str = "demo") -> dict[str, Any]:
        result: dict[str, Any] | None = None
        with self.connect() as conn:
            profile = conn.execute(
                "SELECT learner_id, display_name, created_at, updated_at FROM learner_profiles WHERE learner_id = ?",
                (learner_id,),
            ).fetchone()
            if not profile:
                result = None
            else:
                mastery_rows = conn.execute(
                    """
                    SELECT objective, mastery, attempts, correct, high_confidence_wrong, last_practiced_at
                    FROM objective_mastery WHERE learner_id = ?
                    ORDER BY mastery ASC, attempts ASC
                    """,
                    (learner_id,),
                ).fetchall()
                attempts = conn.execute(
                    """
                    SELECT case_id, mode, score, confidence, misconception_tags_json, created_at
                    FROM attempts WHERE learner_id = ?
                    ORDER BY id DESC LIMIT 12
                    """,
                    (learner_id,),
                ).fetchall()
                attempt_count = int(
                    conn.execute(
                        "SELECT COUNT(*) AS n FROM attempts WHERE learner_id = ?",
                        (learner_id,),
                    ).fetchone()["n"]
                )
                misconceptions = self._misconception_counts(conn, learner_id)
                subskill_rows = conn.execute(
                    """
                    SELECT concept, subskill, formative_score, independent_mastery,
                           attempts, independent_attempts, correct, high_confidence_wrong,
                           last_practiced_at, next_due_at, stability_days, lapses,
                           spaced_retrievals, distinct_eligible_ecgs,
                           distinct_successful_ecgs, distinct_modes,
                           distinct_morphologies, last_independent_at,
                           last_independent_correct
                    FROM subskill_mastery WHERE learner_id = ?
                    ORDER BY independent_mastery ASC, formative_score ASC, attempts ASC
                    """,
                    (learner_id,),
                ).fetchall()
                as_of = parse_instant(utc_now()) or datetime.now(UTC)
                subskill_profile: list[dict[str, Any]] = []
                for row in subskill_rows:
                    retention_row = {
                        "independentAttempts": row["independent_attempts"],
                        "nextDueAt": row["next_due_at"],
                        "stabilityDays": row["stability_days"],
                        "lapses": row["lapses"],
                        "spacedRetrievals": row["spaced_retrievals"],
                        "distinctEligibleEcgs": row["distinct_eligible_ecgs"],
                        "distinctSuccessfulEcgs": row["distinct_successful_ecgs"],
                        "distinctModes": row["distinct_modes"],
                        "distinctMorphologies": row["distinct_morphologies"],
                        "lastIndependentAt": row["last_independent_at"],
                        "lastIndependentCorrect": (
                            bool(row["last_independent_correct"])
                            if row["last_independent_correct"] is not None
                            else None
                        ),
                    }
                    due = due_snapshot(retention_row, as_of=as_of)
                    subskill_profile.append({
                        "concept": row["concept"],
                        "subskill": row["subskill"],
                        "formativeScore": round(row["formative_score"], 3),
                        "independentMastery": round(row["independent_mastery"], 3),
                        "attempts": row["attempts"],
                        "independentAttempts": row["independent_attempts"],
                        "correct": row["correct"],
                        "highConfidenceWrong": row["high_confidence_wrong"],
                        "lastPracticedAt": row["last_practiced_at"],
                        **retention_row,
                        "dueState": due["dueState"],
                        "isDue": due["isDue"],
                        "overdueDays": due["overdueDays"],
                        "daysUntilDue": due["daysUntilDue"],
                        "retentionUncertainty": retention_uncertainty(retention_row, as_of=as_of),
                    })
                result = {
                    "learnerId": profile["learner_id"],
                    "displayName": profile["display_name"],
                    "createdAt": profile["created_at"],
                    "updatedAt": profile["updated_at"],
                    "attemptCount": attempt_count,
                    "mastery": [
                        {
                            "objective": row["objective"],
                            "mastery": round(row["mastery"], 3),
                            "attempts": row["attempts"],
                            "correct": row["correct"],
                            "highConfidenceWrong": row["high_confidence_wrong"],
                            "lastPracticedAt": row["last_practiced_at"],
                        }
                        for row in mastery_rows
                    ],
                    "subskillMastery": subskill_profile,
                    "recentAttempts": [
                        {
                            "caseId": row["case_id"],
                            "mode": row["mode"],
                            "score": round(row["score"], 3),
                            "confidence": row["confidence"],
                            "misconceptions": json.loads(row["misconception_tags_json"]),
                            "createdAt": row["created_at"],
                        }
                        for row in attempts
                    ],
                    "misconceptions": misconceptions,
                    "weakObjectives": [
                        row["objective"] for row in mastery_rows if row["mastery"] < 0.45
                    ][:8],
                }
        if result is None:
            return self.ensure_profile(learner_id)
        return result

    @staticmethod
    def _pathway_progress_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "pathwayId": row["pathway_id"],
            "moduleId": row["module_id"],
            "sceneId": row["scene_id"],
            "status": row["status"],
            "activeInteractionIndex": int(row["active_interaction_index"]),
            "completedActionIds": json.loads(row["completed_action_ids_json"]),
            "state": json.loads(row["state_json"]),
            "source": row["source"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def get_pathway_progress(
        self, learner_id: str, pathway_id: str | None = None
    ) -> list[dict[str, Any]]:
        self.ensure_profile(learner_id)
        sql = (
            "SELECT pathway_id, module_id, scene_id, status, active_interaction_index, "
            "completed_action_ids_json, state_json, source, created_at, updated_at "
            "FROM pathway_progress WHERE learner_id = ?"
        )
        params: list[Any] = [learner_id]
        if pathway_id:
            sql += " AND pathway_id = ?"
            params.append(pathway_id)
        sql += " ORDER BY pathway_id, module_id, scene_id"
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._pathway_progress_dict(row) for row in rows]

    def upsert_pathway_progress(
        self,
        learner_id: str,
        items: list[dict[str, Any]],
        *,
        source: str = "server",
        merge: bool = True,
    ) -> list[dict[str, Any]]:
        """Idempotently persist per-scene/action pathway state.

        Merge mode is intentionally monotonic for completion and action receipts,
        which makes a one-time guest import safe to retry without downgrading work
        already completed on another device.
        """
        self.ensure_profile(learner_id)
        now = utc_now()
        keys: list[tuple[str, str, str]] = []
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            for item in items:
                key = (item["pathwayId"], item["moduleId"], item["sceneId"])
                keys.append(key)
                existing = conn.execute(
                    "SELECT * FROM pathway_progress WHERE learner_id = ? AND pathway_id = ? "
                    "AND module_id = ? AND scene_id = ?",
                    (learner_id, *key),
                ).fetchone()
                incoming_status = str(item["status"])
                incoming_actions = list(dict.fromkeys(item.get("completedActionIds") or []))
                incoming_state = dict(item.get("state") or {})
                incoming_index = int(item.get("activeInteractionIndex", 0))

                if existing and merge:
                    existing_status = str(existing["status"])
                    status = (
                        incoming_status
                        if _PATHWAY_STATUS_RANK[incoming_status] >= _PATHWAY_STATUS_RANK[existing_status]
                        else existing_status
                    )
                    actions = list(dict.fromkeys(
                        json.loads(existing["completed_action_ids_json"]) + incoming_actions
                    ))
                    state = {**json.loads(existing["state_json"]), **incoming_state}
                    active_index = max(int(existing["active_interaction_index"]), incoming_index)
                else:
                    status = incoming_status
                    actions = incoming_actions
                    state = incoming_state
                    active_index = incoming_index

                encoded_actions = json.dumps(actions, sort_keys=True)
                encoded_state = json.dumps(state, sort_keys=True)
                if existing:
                    unchanged = (
                        existing["status"] == status
                        and int(existing["active_interaction_index"]) == active_index
                        and existing["completed_action_ids_json"] == encoded_actions
                        and existing["state_json"] == encoded_state
                        and existing["source"] == source
                    )
                    if not unchanged:
                        conn.execute(
                            "UPDATE pathway_progress SET status = ?, active_interaction_index = ?, "
                            "completed_action_ids_json = ?, state_json = ?, source = ?, updated_at = ? "
                            "WHERE learner_id = ? AND pathway_id = ? AND module_id = ? AND scene_id = ?",
                            (
                                status, active_index, encoded_actions, encoded_state, source, now,
                                learner_id, *key,
                            ),
                        )
                else:
                    conn.execute(
                        "INSERT INTO pathway_progress (learner_id, pathway_id, module_id, scene_id, status, "
                        "active_interaction_index, completed_action_ids_json, state_json, source, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            learner_id, *key, status, active_index, encoded_actions,
                            encoded_state, source, now, now,
                        ),
                    )
            conn.execute(
                "UPDATE learner_profiles SET updated_at = ? WHERE learner_id = ?", (now, learner_id)
            )

            results: list[dict[str, Any]] = []
            for pathway_id, module_id, scene_id in keys:
                row = conn.execute(
                    "SELECT * FROM pathway_progress WHERE learner_id = ? AND pathway_id = ? "
                    "AND module_id = ? AND scene_id = ?",
                    (learner_id, pathway_id, module_id, scene_id),
                ).fetchone()
                if row:
                    results.append(self._pathway_progress_dict(row))
        return results

    def save_guided_learning_event(
        self,
        learner_id: str,
        event: dict[str, Any],
        *,
        occurred_at: datetime | str | None = None,
    ) -> dict[str, Any]:
        self.ensure_profile(learner_id)
        event_time = parse_instant(occurred_at) or datetime.now(UTC)
        now = event_time.isoformat()
        event_key = str(event.get("eventKey") or "").strip()
        if not event_key:
            # A deterministic fallback protects older clients from network-retry
            # replay while still allowing a real subsequent attempt (whose attempt
            # count, response result, or assistance state will differ).
            idempotent_payload = {
                key: event.get(key)
                for key in (
                    "moduleId", "sceneId", "interactionId", "concept", "score", "correct",
                    "attempts", "assistance", "hintsUsed", "confidence", "evidenceLevel",
                    "trainingPhase", "evidenceSource", "caseId", "caseProvenance",
                    "caseEligible", "misconceptions",
                )
            }
            idempotent_payload["subskills"] = sorted(event.get("subskills") or [])
            event_key = hashlib.sha256(
                json.dumps(idempotent_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
        requested_level = str(event["evidenceLevel"])
        assistance = str(event["assistance"])
        provenance = str(event["caseProvenance"])
        case_eligible = bool(event["caseEligible"])
        server_verified_scoring = event.get("_serverVerifiedScoring") is True
        visual_subskills = {"recognize", "localize", "measure", "discriminate", "synthesize"}
        effective_level = requested_level
        if effective_level == "independent_transfer" and not server_verified_scoring:
            # Never turn a browser-asserted score/correct flag into independent
            # mastery. Only a mode-specific server grader may set the private
            # verification marker on its direct storage call.
            effective_level = "guided"
        definition = objective_definition(str(event["concept"]))
        if str(event["moduleId"]) == "train" and effective_level == "independent_transfer":
            # Training recognition and labeled build phases remain formative.
            # Independent transfer is limited to one exact, server-graded task
            # whose evidence source is appropriate for that subskill.
            training_subskills = list(event["subskills"])
            allowed_training_sources = {
                "localize": "trace_native",
                "measure": "trace_native",
                "discriminate": "labeled_contrast_task",
                "explain_mechanism": "curated_mechanism_task",
                "calibrate_confidence": "confidence_commit",
            }
            exact_server_task_transfer = (
                event.get("trainingPhase") == "transfer"
                and len(training_subskills) == 1
                and event.get("evidenceSource")
                == allowed_training_sources.get(training_subskills[0])
            )
            if not exact_server_task_transfer:
                effective_level = "guided"
        if effective_level == "independent_transfer" and definition:
            source_unlocked = True
            if definition.id in DYNAMIC_SOURCE_UNAVAILABLE:
                packet = None
                case_id = str(event.get("caseId") or "")
                if self._case_packet_provider is not None and case_id:
                    try:
                        packet = self._case_packet_provider(case_id)
                    except Exception:
                        packet = None
                source_unlocked = audited_source_packet_supports_objective(packet, definition.id)
            if definition.unavailable_reason or not source_unlocked:
                effective_level = "guided"
        if assistance != "independent" and effective_level == "independent_transfer":
            effective_level = "guided"
        if (visual_subskills & set(event["subskills"])) and (provenance not in {"real_eligible", "real_reviewed"} or not case_eligible):
            if effective_level == "independent_transfer":
                effective_level = "guided"
        if "apply_in_context" in set(event["subskills"]) and (provenance != "real_reviewed" or not case_eligible):
            if effective_level == "independent_transfer":
                effective_level = "guided"

        score = float(event["score"])
        correct = bool(event["correct"])
        confidence = event.get("confidence")
        receipts: list[dict[str, Any]] = []
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT id, requested_evidence_level, effective_evidence_level, receipt_json "
                "FROM guided_learning_events WHERE learner_id = ? AND event_key = ?",
                (learner_id, event_key),
            ).fetchone()
            if existing:
                return {
                    "eventId": int(existing["id"]),
                    "eventKey": event_key,
                    "replay": True,
                    "requestedEvidenceLevel": existing["requested_evidence_level"],
                    "effectiveEvidenceLevel": existing["effective_evidence_level"],
                    "receipts": json.loads(existing["receipt_json"] or "[]"),
                }
            cursor = conn.execute(
                """
                INSERT INTO guided_learning_events (
                    learner_id, module_id, scene_id, interaction_id, concept,
                    subskills_json, score, correct, attempts, assistance, hints_used,
                    confidence, requested_evidence_level, effective_evidence_level,
                    case_id, case_provenance, case_eligible, misconception_tags_json,
                    event_key, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    learner_id, event["moduleId"], event["sceneId"], event["interactionId"], event["concept"],
                    json.dumps(event["subskills"]), score, 1 if correct else 0, int(event["attempts"]), assistance,
                    int(event.get("hintsUsed", 0)), confidence, requested_level, effective_level, event.get("caseId"),
                    provenance, 1 if case_eligible else 0, json.dumps(event.get("misconceptions", [])), event_key, now,
                ),
            )
            for subskill in event["subskills"]:
                current = conn.execute(
                    """SELECT formative_score, independent_mastery, attempts, independent_attempts,
                              correct, high_confidence_wrong, next_due_at, stability_days,
                              lapses, spaced_retrievals, distinct_eligible_ecgs,
                              distinct_successful_ecgs, distinct_modes,
                              distinct_morphologies, last_independent_at,
                              last_independent_correct
                       FROM subskill_mastery
                       WHERE learner_id = ? AND concept = ? AND subskill = ?""",
                    (learner_id, event["concept"], subskill),
                ).fetchone()
                formative = float(current["formative_score"]) if current else 0.0
                independent = float(current["independent_mastery"]) if current else 0.15
                formative_delta = (0.04 + 0.04 * score) if correct else -0.04
                independent_delta = 0.0
                if effective_level == "independent_transfer":
                    independent_delta = (0.05 + 0.05 * score) if correct else -0.06
                next_formative = min(1.0, max(0.0, formative + formative_delta))
                next_independent = min(1.0, max(0.0, independent + independent_delta))
                high_conf_wrong = 1 if confidence is not None and int(confidence) >= 4 and not correct else 0
                retention_values = {
                    "independentAttempts": (
                        (int(current["independent_attempts"]) if current else 0)
                        + (1 if effective_level == "independent_transfer" else 0)
                    ),
                    "nextDueAt": current["next_due_at"] if current else None,
                    "stabilityDays": float(current["stability_days"]) if current else 0.0,
                    "lapses": int(current["lapses"]) if current else 0,
                    "spacedRetrievals": int(current["spaced_retrievals"]) if current else 0,
                    "distinctEligibleEcgs": int(current["distinct_eligible_ecgs"]) if current else 0,
                    "distinctSuccessfulEcgs": int(current["distinct_successful_ecgs"]) if current else 0,
                    "distinctModes": int(current["distinct_modes"]) if current else 0,
                    "distinctMorphologies": int(current["distinct_morphologies"]) if current else 0,
                    "lastIndependentAt": current["last_independent_at"] if current else None,
                    "lastIndependentCorrect": (
                        bool(current["last_independent_correct"])
                        if current and current["last_independent_correct"] is not None
                        else None
                    ),
                }
                retention_eligible = (
                    effective_level == "independent_transfer"
                    and bool(event.get("_retentionVerified"))
                    and bool(event.get("caseId"))
                )
                interval_expanded = False
                if retention_eligible:
                    update = update_retention(
                        retention_values,
                        correct=correct,
                        occurred_at=event_time,
                    )
                    retention_values.update({
                        "nextDueAt": update.next_due_at,
                        "stabilityDays": update.stability_days,
                        "lapses": update.lapses,
                        "spacedRetrievals": update.spaced_retrievals,
                        "lastIndependentAt": update.last_independent_at,
                        "lastIndependentCorrect": update.last_independent_correct,
                    })
                    interval_expanded = update.interval_expanded
                    conn.execute(
                        """
                        INSERT INTO subskill_retention_events (
                            guided_event_id, learner_id, concept, subskill, case_id,
                            mode, morphology_key, correct, occurred_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            int(cursor.lastrowid), learner_id, event["concept"], subskill,
                            str(event["caseId"]), str(event["moduleId"]),
                            event.get("_retentionMorphologyKey"), 1 if correct else 0, now,
                        ),
                    )
                    diversity = conn.execute(
                        """
                        SELECT COUNT(DISTINCT case_id) AS eligible_ecgs,
                               COUNT(DISTINCT CASE WHEN correct = 1 THEN case_id END) AS successful_ecgs,
                               COUNT(DISTINCT mode) AS modes,
                               COUNT(DISTINCT CASE
                                   WHEN morphology_key IS NOT NULL AND morphology_key != ''
                                   THEN morphology_key END) AS morphologies
                        FROM subskill_retention_events
                        WHERE learner_id = ? AND concept = ? AND subskill = ?
                        """,
                        (learner_id, event["concept"], subskill),
                    ).fetchone()
                    retention_values.update({
                        "distinctEligibleEcgs": int(diversity["eligible_ecgs"]),
                        "distinctSuccessfulEcgs": int(diversity["successful_ecgs"]),
                        "distinctModes": int(diversity["modes"]),
                        "distinctMorphologies": int(diversity["morphologies"]),
                    })
                if current:
                    conn.execute(
                        """
                        UPDATE subskill_mastery
                        SET formative_score = ?, independent_mastery = ?, attempts = attempts + 1,
                            independent_attempts = independent_attempts + ?, correct = correct + ?,
                            high_confidence_wrong = high_confidence_wrong + ?, last_practiced_at = ?,
                            next_due_at = ?, stability_days = ?, lapses = ?,
                            spaced_retrievals = ?, distinct_eligible_ecgs = ?,
                            distinct_successful_ecgs = ?, distinct_modes = ?,
                            distinct_morphologies = ?, last_independent_at = ?,
                            last_independent_correct = ?
                        WHERE learner_id = ? AND concept = ? AND subskill = ?
                        """,
                        (next_formative, next_independent, 1 if effective_level == "independent_transfer" else 0,
                         1 if correct else 0, high_conf_wrong, now,
                         retention_values["nextDueAt"], retention_values["stabilityDays"],
                         retention_values["lapses"], retention_values["spacedRetrievals"],
                         retention_values["distinctEligibleEcgs"], retention_values["distinctSuccessfulEcgs"],
                         retention_values["distinctModes"], retention_values["distinctMorphologies"],
                         retention_values["lastIndependentAt"],
                         (1 if retention_values["lastIndependentCorrect"] else 0)
                         if retention_values["lastIndependentCorrect"] is not None else None,
                         learner_id, event["concept"], subskill),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO subskill_mastery (
                            learner_id, concept, subskill, formative_score, independent_mastery,
                            attempts, independent_attempts, correct, high_confidence_wrong, last_practiced_at,
                            next_due_at, stability_days, lapses, spaced_retrievals,
                            distinct_eligible_ecgs, distinct_successful_ecgs, distinct_modes,
                            distinct_morphologies, last_independent_at, last_independent_correct
                        ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (learner_id, event["concept"], subskill, next_formative, next_independent,
                         1 if effective_level == "independent_transfer" else 0,
                         1 if correct else 0, high_conf_wrong, now,
                         retention_values["nextDueAt"], retention_values["stabilityDays"],
                         retention_values["lapses"], retention_values["spacedRetrievals"],
                         retention_values["distinctEligibleEcgs"], retention_values["distinctSuccessfulEcgs"],
                         retention_values["distinctModes"], retention_values["distinctMorphologies"],
                         retention_values["lastIndependentAt"],
                         (1 if retention_values["lastIndependentCorrect"] else 0)
                         if retention_values["lastIndependentCorrect"] is not None else None),
                    )
                due = due_snapshot(retention_values, as_of=event_time)
                receipts.append({
                    "concept": event["concept"],
                    "subskill": subskill,
                    "formativeScore": round(next_formative, 3),
                    "independentMastery": round(next_independent, 3),
                    "evidenceLevel": effective_level,
                    "retentionEligible": retention_eligible,
                    "nextDueAt": retention_values["nextDueAt"],
                    "stabilityDays": retention_values["stabilityDays"],
                    "lapses": retention_values["lapses"],
                    "spacedRetrievals": retention_values["spacedRetrievals"],
                    "distinctEligibleEcgs": retention_values["distinctEligibleEcgs"],
                    "distinctSuccessfulEcgs": retention_values["distinctSuccessfulEcgs"],
                    "distinctModes": retention_values["distinctModes"],
                    "distinctMorphologies": retention_values["distinctMorphologies"],
                    "dueState": due["dueState"],
                    "intervalExpanded": interval_expanded,
                })
            conn.execute(
                "UPDATE guided_learning_events SET receipt_json = ? WHERE id = ?",
                (json.dumps(receipts), cursor.lastrowid),
            )
            conn.execute("UPDATE learner_profiles SET updated_at = ? WHERE learner_id = ?", (now, learner_id))
            return {
                "eventId": int(cursor.lastrowid),
                "eventKey": event_key,
                "replay": False,
                "requestedEvidenceLevel": requested_level,
                "effectiveEvidenceLevel": effective_level,
                "receipts": receipts,
            }

    def save_attempt(
        self,
        learner_id: str,
        case_id: str,
        mode: str,
        structured_answer: dict[str, Any],
        free_text_answer: str,
        confidence: int,
        hints_used: int,
        grade: dict[str, Any],
    ) -> int:
        self.ensure_profile(learner_id)
        now = utc_now()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO attempts (
                    learner_id, case_id, mode, structured_answer_json, free_text_answer,
                    confidence, hints_used, score, correct_objectives_json,
                    missed_objectives_json, misconception_tags_json, feedback, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    learner_id,
                    case_id,
                    mode,
                    json.dumps(structured_answer),
                    free_text_answer,
                    confidence,
                    hints_used,
                    float(grade["score"]),
                    json.dumps(grade["correctObjectives"]),
                    json.dumps(grade["missedObjectives"]),
                    json.dumps(grade["misconceptions"]),
                    grade["feedback"],
                    now,
                ),
            )
            mastery_delta = {} if mode in {"concept_practice", "rapid_practice"} else grade["masteryDelta"]
            for objective, delta in mastery_delta.items():
                current = conn.execute(
                    """
                    SELECT mastery, attempts, correct, high_confidence_wrong
                    FROM objective_mastery WHERE learner_id = ? AND objective = ?
                    """,
                    (learner_id, objective),
                ).fetchone()
                if current:
                    new_mastery = min(1.0, max(0.0, current["mastery"] + delta))
                    correct_increment = 1 if objective in grade["correctObjectives"] else 0
                    high_conf_wrong_increment = (
                        1 if confidence >= 4 and objective in grade["missedObjectives"] else 0
                    )
                    conn.execute(
                        """
                        UPDATE objective_mastery
                        SET mastery = ?, attempts = attempts + 1, correct = correct + ?,
                            high_confidence_wrong = high_confidence_wrong + ?,
                            last_practiced_at = ?
                        WHERE learner_id = ? AND objective = ?
                        """,
                        (
                            new_mastery,
                            correct_increment,
                            high_conf_wrong_increment,
                            now,
                            learner_id,
                            objective,
                        ),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO objective_mastery (
                            learner_id, objective, mastery, attempts, correct,
                            high_confidence_wrong, last_practiced_at
                        )
                        VALUES (?, ?, ?, 1, ?, ?, ?)
                        """,
                        (
                            learner_id,
                            objective,
                            min(1.0, max(0.0, 0.25 + delta)),
                            1 if objective in grade["correctObjectives"] else 0,
                            1 if confidence >= 4 and objective in grade["missedObjectives"] else 0,
                            now,
                        ),
                    )
            conn.execute(
                "UPDATE learner_profiles SET updated_at = ? WHERE learner_id = ?",
                (now, learner_id),
            )
            return int(cursor.lastrowid)

    def _save_attempt_in_transaction(
        self,
        conn: sqlite3.Connection,
        *,
        learner_id: str,
        case_id: str,
        mode: str,
        structured_answer: dict[str, Any],
        confidence: int,
        grade: dict[str, Any],
        now: str,
    ) -> int:
        """Write one attempt and its mastery deltas on an existing transaction.

        Clinical answers use this helper so the answer ledger, generic attempt,
        mastery mutation, and session advance either all commit or all roll back.
        """
        cursor = conn.execute(
            """
            INSERT INTO attempts (
                learner_id, case_id, mode, structured_answer_json, free_text_answer,
                confidence, hints_used, score, correct_objectives_json,
                missed_objectives_json, misconception_tags_json, feedback, created_at
            ) VALUES (?, ?, ?, ?, '', ?, 0, ?, ?, ?, ?, ?, ?)
            """,
            (
                learner_id,
                case_id,
                mode,
                json.dumps(structured_answer),
                confidence,
                float(grade["score"]),
                json.dumps(grade["correctObjectives"]),
                json.dumps(grade["missedObjectives"]),
                json.dumps(grade["misconceptions"]),
                grade["feedback"],
                now,
            ),
        )
        mastery_delta = {} if mode in {"concept_practice", "rapid_practice"} else grade["masteryDelta"]
        for objective, delta in mastery_delta.items():
            current = conn.execute(
                """SELECT mastery, attempts, correct, high_confidence_wrong
                   FROM objective_mastery WHERE learner_id = ? AND objective = ?""",
                (learner_id, objective),
            ).fetchone()
            correct_increment = 1 if objective in grade["correctObjectives"] else 0
            high_conf_wrong_increment = (
                1 if confidence >= 4 and objective in grade["missedObjectives"] else 0
            )
            if current:
                conn.execute(
                    """
                    UPDATE objective_mastery
                    SET mastery = ?, attempts = attempts + 1, correct = correct + ?,
                        high_confidence_wrong = high_confidence_wrong + ?, last_practiced_at = ?
                    WHERE learner_id = ? AND objective = ?
                    """,
                    (
                        min(1.0, max(0.0, float(current["mastery"]) + float(delta))),
                        correct_increment,
                        high_conf_wrong_increment,
                        now,
                        learner_id,
                        objective,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO objective_mastery (
                        learner_id, objective, mastery, attempts, correct,
                        high_confidence_wrong, last_practiced_at
                    ) VALUES (?, ?, ?, 1, ?, ?, ?)
                    """,
                    (
                        learner_id,
                        objective,
                        min(1.0, max(0.0, 0.25 + float(delta))),
                        correct_increment,
                        high_conf_wrong_increment,
                        now,
                    ),
                )
        conn.execute(
            "UPDATE learner_profiles SET updated_at = ? WHERE learner_id = ?",
            (now, learner_id),
        )
        return int(cursor.lastrowid)

    def recent_case_ids(self, learner_id: str, limit: int = 12) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT case_id FROM attempts WHERE learner_id = ? ORDER BY id DESC LIMIT ?",
                (learner_id, limit),
            ).fetchall()
            return [row["case_id"] for row in rows]

    def retention_case_ids(self, learner_id: str, concept: str, subskill: str) -> list[str]:
        """Real ECGs already used as independent retention evidence for a competency."""

        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT case_id
                FROM subskill_retention_events
                WHERE learner_id = ? AND concept = ? AND subskill = ?
                ORDER BY case_id
                """,
                (learner_id, concept, subskill),
            ).fetchall()
        return [str(row["case_id"]) for row in rows]

    # --- users & sessions (Phase 4 auth) ---------------------------------------

    def create_user(self, user_id: str, username: str, display_name: str, password_hash: str) -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO users (user_id, username, display_name, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, username, display_name, password_hash, now),
            )

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT user_id, username, display_name, password_hash, created_at FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        return dict(row) if row else None

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT user_id, username, display_name, created_at FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_user_auth(self, user_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT user_id, username, display_name, password_hash, created_at "
                "FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return dict(row) if row else None

    def update_user_password(self, user_id: str, password_hash: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE user_id = ?",
                (password_hash, user_id),
            )

    @staticmethod
    def _session_key(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create_session(self, token: str, user_id: str, expires_at: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (self._session_key(token), user_id, utc_now(), expires_at),
            )

    def get_session_user(self, token: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT user_id, expires_at FROM sessions WHERE token = ?",
                (self._session_key(token),),
            ).fetchone()
        if not row:
            return None
        if row["expires_at"] < utc_now():
            self.delete_session(token)
            return None
        return row["user_id"]

    def delete_session(self, token: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (self._session_key(token),))

    def delete_user_sessions(self, user_id: str) -> int:
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        return int(cursor.rowcount)

    def _consume_auth_hash_reservation(
        self,
        *,
        table_name: str,
        buckets: tuple[tuple[str, str, int], ...],
        window_minutes: int,
        block_minutes: int,
    ) -> bool:
        """Atomically reserve one expensive auth hash across nested buckets.

        Buckets must be ordered from narrowest to broadest.  Only a request
        admitted by every bucket increments counters; when a bucket rejects,
        just that bucket records the block.  This keeps the counters equal to
        actual password-hash work and prevents a narrowly blocked caller from
        cheaply exhausting broader classroom-IP or deployment capacity.
        """

        if table_name not in {"auth_registration_throttle", "auth_login_throttle"}:
            raise ValueError("Unsupported authentication throttle table")
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        cutoff = now_dt - timedelta(hours=24)
        with self.connect() as conn:
            try:
                if not conn.in_transaction:
                    conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    f"DELETE FROM {table_name} WHERE updated_at < ?",
                    (cutoff.isoformat(),),
                )
                states: list[dict[str, Any]] = []
                for scope, key_hash, ceiling in buckets:
                    row = conn.execute(
                        "SELECT attempt_count, window_started_at, blocked_until "
                        f"FROM {table_name} WHERE scope = ? AND key_hash = ?",
                        (scope, key_hash),
                    ).fetchone()
                    count = 0
                    window_start = now_dt
                    active_block_until: str | None = None
                    if row:
                        try:
                            stored_window_start = datetime.fromisoformat(
                                row["window_started_at"]
                            )
                        except ValueError:
                            stored_window_start = now_dt
                        try:
                            stored_block = (
                                datetime.fromisoformat(row["blocked_until"])
                                if row["blocked_until"]
                                else None
                            )
                        except ValueError:
                            stored_block = None
                        if stored_block and stored_block > now_dt:
                            active_block_until = row["blocked_until"]
                        if stored_window_start >= now_dt - timedelta(
                            minutes=window_minutes
                        ):
                            window_start = stored_window_start
                            count = int(row["attempt_count"])
                    states.append(
                        {
                            "scope": scope,
                            "key_hash": key_hash,
                            "ceiling": max(0, int(ceiling)),
                            "count": count,
                            "window_start": window_start,
                            "active_block_until": active_block_until,
                        }
                    )

                blocked_state = next(
                    (
                        state
                        for state in states
                        if state["active_block_until"]
                        or state["count"] >= state["ceiling"]
                    ),
                    None,
                )
                for state in [blocked_state] if blocked_state else states:
                    assert state is not None
                    count = int(state["count"])
                    blocked_until = None
                    if blocked_state:
                        blocked_until = state["active_block_until"] or (
                            now_dt + timedelta(minutes=block_minutes)
                        ).isoformat()
                    else:
                        count += 1
                    conn.execute(
                        f"INSERT INTO {table_name} "
                        "(scope, key_hash, attempt_count, window_started_at, blocked_until, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?) "
                        "ON CONFLICT(scope, key_hash) DO UPDATE SET "
                        "attempt_count = excluded.attempt_count, "
                        "window_started_at = excluded.window_started_at, "
                        "blocked_until = excluded.blocked_until, updated_at = excluded.updated_at",
                        (
                            state["scope"],
                            state["key_hash"],
                            count,
                            state["window_start"].isoformat(),
                            blocked_until,
                            now,
                        ),
                    )
                # Pair keys are username-controlled.  Aggregate buckets remain
                # while the least-recently-updated high-cardinality rows prune.
                conn.execute(
                    f"DELETE FROM {table_name} WHERE rowid IN ("
                    f"SELECT rowid FROM {table_name} "
                    "ORDER BY updated_at DESC LIMIT -1 OFFSET 50000)"
                )
            except Exception:
                conn.rollback()
                raise
        return blocked_state is not None

    def consume_registration_attempt(
        self,
        *,
        pair_key_hash: str,
        ip_key_hash: str,
        global_key_hash: str,
        max_pair_attempts: int,
        max_ip_attempts: int,
        max_global_attempts: int,
        window_minutes: int,
        block_minutes: int,
    ) -> bool:
        """Reserve registration hashing without persisting raw identifiers."""

        return self._consume_auth_hash_reservation(
            table_name="auth_registration_throttle",
            buckets=(
                ("pair", pair_key_hash, max_pair_attempts),
                ("ip", ip_key_hash, max_ip_attempts),
                ("global", global_key_hash, max_global_attempts),
            ),
            window_minutes=window_minutes,
            block_minutes=block_minutes,
        )

    def consume_login_attempt(
        self,
        *,
        pair_key_hash: str,
        ip_key_hash: str,
        global_key_hash: str,
        max_pair_attempts: int,
        max_ip_attempts: int,
        max_global_attempts: int,
        window_minutes: int,
        block_minutes: int,
    ) -> bool:
        """Reserve a login hash attempt before any expensive password work.

        All identifiers arrive as domain-separated HMAC digests.  Pair limits
        prevent focused guessing without making a username globally lockable;
        IP and deployment-wide limits bound random-username and distributed
        CPU exhaustion.  Every admitted request consumes capacity, including a
        successful one, because the slow hash has been reserved; rejected work
        never drains a broader bucket.
        """

        return self._consume_auth_hash_reservation(
            table_name="auth_login_throttle",
            buckets=(
                ("pair", pair_key_hash, max_pair_attempts),
                ("ip", ip_key_hash, max_ip_attempts),
                ("global", global_key_hash, max_global_attempts),
            ),
            window_minutes=window_minutes,
            block_minutes=block_minutes,
        )

    def clear_login_pair_attempts(self, pair_key_hash: str) -> None:
        """Let a verified learner recover from typos without erasing CPU limits."""

        with self.connect() as conn:
            conn.execute(
                "DELETE FROM auth_login_throttle WHERE scope = 'pair' AND key_hash = ?",
                (pair_key_hash,),
            )

    # --- remote tutor quotas ---------------------------------------------------

    def consume_remote_tutor_quota(
        self,
        *,
        learner_id: str,
        client_ip: str,
        hash_secret: str,
        authenticated: bool,
        authenticated_daily_limit: int,
        guest_daily_limit: int,
        ip_hourly_limit: int,
        global_daily_limit: int,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Atomically reserve one remote-model call across durable limits.

        The database stores only domain-separated HMAC digests, never a learner
        id or IP address. A reservation is consumed before the network call and
        remains consumed if the provider fails; this prevents retry storms from
        bypassing the spend boundary. Deterministic tutor fallbacks do not call
        this method and therefore remain available after a limit is reached.
        """

        instant = now or datetime.now(UTC)
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=UTC)
        instant = instant.astimezone(UTC)
        day_start = instant.replace(hour=0, minute=0, second=0, microsecond=0)
        hour_start = instant.replace(minute=0, second=0, microsecond=0)
        learner_limit = (
            int(authenticated_daily_limit) if authenticated else int(guest_daily_limit)
        )
        limits = {
            "learnerDaily": learner_limit,
            "ipHourly": int(ip_hourly_limit),
            "globalDaily": int(global_daily_limit),
        }
        if not hash_secret or any(value <= 0 for value in limits.values()):
            raise ValueError("Remote tutor quota configuration must use a secret and positive limits")

        secret = hash_secret.encode("utf-8")

        def digest(scope: str, value: str) -> str:
            return hmac.new(
                secret,
                f"ecg-remote-tutor-quota-v1\0{scope}\0{value}".encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

        buckets = [
            {
                "scope": "learner_day",
                "key": digest("learner", learner_id),
                "window": day_start,
                "limit": learner_limit,
                "reason": "learner_daily",
                "remainingKey": "learnerDaily",
                "reset": day_start + timedelta(days=1),
            },
            {
                "scope": "ip_hour",
                "key": digest("ip", client_ip or "unknown"),
                "window": hour_start,
                "limit": int(ip_hourly_limit),
                "reason": "ip_hourly",
                "remainingKey": "ipHourly",
                "reset": hour_start + timedelta(hours=1),
            },
            {
                "scope": "global_day",
                "key": digest("global", "all"),
                "window": day_start,
                "limit": int(global_daily_limit),
                "reason": "global_daily",
                "remainingKey": "globalDaily",
                "reset": day_start + timedelta(days=1),
            },
        ]

        with self.connect() as conn:
            # A single writer reservation closes the select/increment race both
            # for the file-backed production DB and concurrent FastAPI workers.
            conn.execute("BEGIN IMMEDIATE")
            counts: dict[str, int] = {}
            for bucket in buckets:
                row = conn.execute(
                    "SELECT request_count FROM remote_tutor_quota_buckets "
                    "WHERE scope = ? AND key_hash = ? AND window_start = ?",
                    (
                        bucket["scope"],
                        bucket["key"],
                        bucket["window"].isoformat(),
                    ),
                ).fetchone()
                counts[bucket["remainingKey"]] = int(row["request_count"]) if row else 0

            blocked = next(
                (
                    bucket
                    for bucket in buckets
                    if counts[bucket["remainingKey"]] >= int(bucket["limit"])
                ),
                None,
            )
            if blocked is None:
                stamp = instant.isoformat()
                for bucket in buckets:
                    conn.execute(
                        "INSERT INTO remote_tutor_quota_buckets "
                        "(scope, key_hash, window_start, request_count, updated_at) "
                        "VALUES (?, ?, ?, 1, ?) "
                        "ON CONFLICT(scope, key_hash, window_start) DO UPDATE SET "
                        "request_count = request_count + 1, updated_at = excluded.updated_at",
                        (
                            bucket["scope"],
                            bucket["key"],
                            bucket["window"].isoformat(),
                            stamp,
                        ),
                    )
                    counts[bucket["remainingKey"]] += 1
                # Bound telemetry cardinality without touching current windows.
                conn.execute(
                    "DELETE FROM remote_tutor_quota_buckets WHERE updated_at < ?",
                    ((day_start - timedelta(days=8)).isoformat(),),
                )

        remaining = {
            key: max(0, limits[key] - count)
            for key, count in counts.items()
        }
        return {
            "allowed": blocked is None,
            "reason": blocked["reason"] if blocked else None,
            "resetAt": blocked["reset"].isoformat() if blocked else None,
            "remaining": remaining,
            "limits": limits,
        }

    # --- tutor conversation threads --------------------------------------------

    def ensure_thread(
        self,
        learner_id: str,
        thread_id: str | None = None,
        mode: str = "freeform",
        lesson_id: str | None = None,
        case_id: str | None = None,
        title: str | None = None,
    ) -> str:
        import uuid

        now = utc_now()
        with self.connect() as conn:
            if thread_id:
                existing = conn.execute(
                    "SELECT thread_id FROM tutor_threads WHERE thread_id = ?", (thread_id,)
                ).fetchone()
                if existing:
                    conn.execute(
                        "UPDATE tutor_threads SET updated_at = ?, mode = ?, "
                        "lesson_id = COALESCE(?, lesson_id), case_id = COALESCE(?, case_id) WHERE thread_id = ?",
                        (now, mode, lesson_id, case_id, thread_id),
                    )
                    return thread_id
            new_id = thread_id or f"th_{uuid.uuid4().hex[:16]}"
            conn.execute(
                "INSERT INTO tutor_threads (thread_id, learner_id, mode, lesson_id, case_id, title, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (new_id, learner_id, mode, lesson_id, case_id, title or "ECG tutor session", now, now),
            )
            return new_id

    def append_tutor_message(
        self,
        thread_id: str,
        role: str,
        content: str,
        actions: list[Any] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> int:
        now = utc_now()
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO tutor_messages (thread_id, role, content, actions_json, meta_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (thread_id, role, content, json.dumps(actions or []), json.dumps(meta or {}), now),
            )
            conn.execute("UPDATE tutor_threads SET updated_at = ? WHERE thread_id = ?", (now, thread_id))
            return int(cursor.lastrowid)

    def thread_history(self, thread_id: str, limit: int = 40) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT role, content, actions_json, meta_json, created_at FROM ("
                "SELECT id, role, content, actions_json, meta_json, created_at FROM tutor_messages "
                "WHERE thread_id = ? ORDER BY id DESC LIMIT ?) recent ORDER BY id ASC",
                (thread_id, limit),
            ).fetchall()
        return [
            {
                "role": row["role"],
                "content": row["content"],
                "viewerActions": json.loads(row["actions_json"]),
                "meta": json.loads(row["meta_json"]),
                "createdAt": row["created_at"],
            }
            for row in rows
        ]

    def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT thread_id, learner_id, mode, lesson_id, case_id, title, created_at, updated_at "
                "FROM tutor_threads WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "threadId": row["thread_id"],
            "learnerId": row["learner_id"],
            "mode": row["mode"],
            "lessonId": row["lesson_id"],
            "caseId": row["case_id"],
            "title": row["title"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "messages": self.thread_history(row["thread_id"]),
        }

    def list_threads(
        self,
        learner_id: str,
        *,
        mode: str | None = None,
        lesson_id: str | None = None,
        case_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        sql = (
            "SELECT thread_id, learner_id, mode, lesson_id, case_id, title, created_at, updated_at "
            "FROM tutor_threads WHERE learner_id = ?"
        )
        params: list[Any] = [learner_id]
        if mode is not None:
            sql += " AND mode = ?"
            params.append(mode)
        if lesson_id is not None:
            sql += " AND lesson_id = ?"
            params.append(lesson_id)
        if case_id is not None:
            sql += " AND case_id = ?"
            params.append(case_id)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, min(100, int(limit))))
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            {
                "threadId": row["thread_id"],
                "learnerId": row["learner_id"],
                "mode": row["mode"],
                "lessonId": row["lesson_id"],
                "caseId": row["case_id"],
                "title": row["title"],
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
            }
            for row in rows
        ]

    # --- server-owned Rapid rounds ---------------------------------------------

    @staticmethod
    def _rapid_round_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "roundId": row["round_id"],
            "learnerId": row["learner_id"],
            "pace": row["pace"],
            "length": int(row["length"]),
            "assessmentScope": row["assessment_scope"],
            "focusConcept": row["focus_concept"],
            "focusSubskill": row["focus_subskill"],
            "contextKey": row["context_key"],
            "exclusions": json.loads(row["exclusions_json"] or "[]"),
            "served": json.loads(row["served_json"] or "[]"),
            "pendingCaseId": row["pending_case_id"],
            "feedbackCaseId": row["feedback_case_id"],
            "pendingStartedAt": row["pending_started_at"],
            "pendingDeadlineAt": row["pending_deadline_at"],
            "deadlineSeconds": row["deadline_seconds"],
            "position": int(row["position"]),
            "status": row["status"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    @staticmethod
    def _rapid_answer_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "answerId": int(row["id"]),
            "roundId": row["round_id"],
            "caseId": row["case_id"],
            "response": json.loads(row["response_json"]),
            "grade": json.loads(row["grade_json"]),
            "tutor": json.loads(row["tutor_json"] or "null"),
            "result": json.loads(row["result_json"]),
            "traceGrade": json.loads(row["trace_grade_json"]) if row["trace_grade_json"] else None,
            "receipts": json.loads(row["receipts_json"] or "[]"),
            "attemptId": int(row["attempt_id"]),
            "createdAt": row["created_at"],
        }

    def create_rapid_round(
        self,
        learner_id: str,
        pace: str,
        length: int,
        assessment_scope: str,
        deadline_seconds: int | None,
        *,
        focus_concept: str | None = None,
        focus_subskill: str | None = None,
        context_key: str = "",
        exclusions: list[str] | None = None,
    ) -> dict[str, Any]:
        import uuid

        self.ensure_profile(learner_id)
        now = utc_now()
        round_id = f"rr_{uuid.uuid4().hex[:16]}"
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            # Starting a new round is an explicit replacement of any unfinished
            # round for the same learner; stale rounds cannot later win discovery.
            conn.execute(
                "UPDATE rapid_rounds SET status = 'abandoned', feedback_case_id = NULL, updated_at = ? "
                "WHERE learner_id = ? AND (status = 'active' OR feedback_case_id IS NOT NULL)",
                (now, learner_id),
            )
            conn.execute(
                """
                INSERT INTO rapid_rounds (
                    round_id, learner_id, pace, length, assessment_scope, focus_concept,
                    focus_subskill, context_key, exclusions_json, served_json,
                    deadline_seconds, position, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, 0, 'active', ?, ?)
                """,
                (
                    round_id, learner_id, pace, length, assessment_scope, focus_concept,
                    focus_subskill, context_key, json.dumps(exclusions or []),
                    deadline_seconds, now, now,
                ),
            )
        return self.get_rapid_round(round_id)  # type: ignore[return-value]

    def get_rapid_round(self, round_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM rapid_rounds WHERE round_id = ?", (round_id,)).fetchone()
        return self._rapid_round_dict(row) if row else None

    def get_resumable_rapid_round(self, learner_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM rapid_rounds WHERE learner_id = ? "
                "AND (status = 'active' OR feedback_case_id IS NOT NULL) "
                "ORDER BY updated_at DESC LIMIT 1",
                (learner_id,),
            ).fetchone()
        return self._rapid_round_dict(row) if row else None

    def get_rapid_answers(
        self, round_id: str, *, limit: int | None = None, offset: int = 0
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM rapid_round_answers WHERE round_id = ? ORDER BY id"
        params: list[Any] = [round_id]
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([int(limit), int(offset)])
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._rapid_answer_dict(row) for row in rows]

    def get_recent_rapid_answers(self, round_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM (SELECT * FROM rapid_round_answers WHERE round_id = ? "
                "ORDER BY id DESC LIMIT ?) ORDER BY id",
                (round_id, int(limit)),
            ).fetchall()
        return [self._rapid_answer_dict(row) for row in rows]

    def rapid_answer_count(self, round_id: str) -> int:
        with self.connect() as conn:
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM rapid_round_answers WHERE round_id = ?", (round_id,)
                ).fetchone()[0]
            )

    def get_rapid_answer(self, round_id: str, case_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM rapid_round_answers WHERE round_id = ? AND case_id = ?",
                (round_id, case_id),
            ).fetchone()
        return self._rapid_answer_dict(row) if row else None

    def acknowledge_rapid_feedback(self, round_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE rapid_rounds SET feedback_case_id = NULL, updated_at = ? WHERE round_id = ?",
                (utc_now(), round_id),
            )
        return self.get_rapid_round(round_id)

    def set_rapid_pending(self, round_id: str, case_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE rapid_rounds SET pending_case_id = ?, pending_started_at = NULL, "
                "pending_deadline_at = NULL, updated_at = ? WHERE round_id = ? "
                "AND status = 'active' AND pending_case_id IS NULL AND feedback_case_id IS NULL "
                "AND position < length",
                (case_id, utc_now(), round_id),
            )
        return self.get_rapid_round(round_id)

    def activate_rapid_pending(self, round_id: str) -> dict[str, Any] | None:
        session = self.get_rapid_round(round_id)
        if not session or not session.get("pendingCaseId"):
            return session
        if session.get("pendingStartedAt"):
            return session
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        duration = session.get("deadlineSeconds")
        deadline = (now_dt + timedelta(seconds=int(duration))).isoformat() if duration is not None else None
        with self.connect() as conn:
            conn.execute(
                "UPDATE rapid_rounds SET pending_started_at = ?, pending_deadline_at = ?, updated_at = ? "
                "WHERE round_id = ? AND pending_case_id IS NOT NULL AND pending_started_at IS NULL",
                (now, deadline, now, round_id),
            )
        return self.get_rapid_round(round_id)

    def record_rapid_answer(
        self,
        *,
        round_id: str,
        case_id: str,
        response: dict[str, Any],
        grade: dict[str, Any],
        tutor: dict[str, Any] | None,
        trace_grade: dict[str, Any] | None,
        confidence: int,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """Exactly-once Rapid submission and generic attempt audit."""
        submitted_dt = datetime.now(UTC)
        submitted_at = submitted_dt.isoformat()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM rapid_round_answers WHERE round_id = ? AND case_id = ?",
                (round_id, case_id),
            ).fetchone()
            if existing:
                return {"status": "replay", "answer": self._rapid_answer_dict(existing)}
            session = conn.execute(
                "SELECT * FROM rapid_rounds WHERE round_id = ?", (round_id,)
            ).fetchone()
            if not session:
                return {"status": "missing"}
            if session["pending_case_id"] != case_id or session["status"] != "active":
                return {"status": "not_pending", "pendingCaseId": session["pending_case_id"]}

            started_at = session["pending_started_at"]
            deadline_at = session["pending_deadline_at"]
            if not started_at:
                started_at = submitted_at
                duration = session["deadline_seconds"]
                deadline_at = (
                    (submitted_dt + timedelta(seconds=int(duration))).isoformat()
                    if duration is not None else None
                )
            started_dt = datetime.fromisoformat(str(started_at))
            deadline_dt = datetime.fromisoformat(str(deadline_at)) if deadline_at else None
            response_ms = max(0, int((submitted_dt - started_dt).total_seconds() * 1000))
            timed_out = bool(deadline_dt and submitted_dt >= deadline_dt)
            durable_result = {
                **result,
                "timedOut": timed_out,
                "responseMs": response_ms,
                "pace": session["pace"],
                "assessmentScope": session["assessment_scope"],
                "startedAt": started_at,
                "deadlineAt": deadline_at,
                "submittedAt": submitted_at,
            }
            durable_response = {
                **response,
                "pace": session["pace"],
                "assessmentScope": session["assessment_scope"],
                "serverStartedAt": started_at,
                "serverDeadlineAt": deadline_at,
            }
            attempt_id = self._save_attempt_in_transaction(
                conn,
                learner_id=session["learner_id"],
                case_id=case_id,
                mode="rapid_practice",
                structured_answer=response.get("structuredAnswer") or {},
                confidence=confidence,
                grade=grade,
                now=submitted_at,
            )
            cursor = conn.execute(
                """
                INSERT INTO rapid_round_answers (
                    round_id, case_id, response_json, grade_json, tutor_json,
                    result_json, trace_grade_json, receipts_json, attempt_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, '[]', ?, ?)
                """,
                (
                    round_id, case_id, json.dumps(durable_response), json.dumps(grade),
                    json.dumps(tutor), json.dumps(durable_result),
                    json.dumps(trace_grade) if trace_grade is not None else None,
                    attempt_id, submitted_at,
                ),
            )
            served = json.loads(session["served_json"] or "[]")
            if case_id not in served:
                served.append(case_id)
            position = int(
                conn.execute(
                    "SELECT COUNT(*) AS n FROM rapid_round_answers WHERE round_id = ?", (round_id,)
                ).fetchone()["n"]
            )
            status = "complete" if position >= int(session["length"]) else "active"
            conn.execute(
                "UPDATE rapid_rounds SET served_json = ?, pending_case_id = NULL, "
                "feedback_case_id = ?, pending_started_at = NULL, pending_deadline_at = NULL, "
                "position = ?, status = ?, updated_at = ? WHERE round_id = ?",
                (json.dumps(served), case_id, position, status, submitted_at, round_id),
            )
            answer_row = conn.execute(
                "SELECT * FROM rapid_round_answers WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        return {"status": "recorded", "answer": self._rapid_answer_dict(answer_row)}

    def set_rapid_answer_receipts(
        self, round_id: str, case_id: str, receipts: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE rapid_round_answers SET receipts_json = ? WHERE round_id = ? AND case_id = ?",
                (json.dumps(receipts), round_id, case_id),
            )
        return self.get_rapid_answer(round_id, case_id)

    # --- adaptive rapid-review sessions ----------------------------------------

    def create_review_session(
        self,
        learner_id: str,
        objectives: list[str],
        label: str,
        target_mastery: float = 0.8,
        max_cases: int = 30,
    ) -> str:
        import uuid

        now = utc_now()
        session_id = f"rs_{uuid.uuid4().hex[:16]}"
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO review_sessions (session_id, learner_id, label, objectives_json, target_mastery, "
                "max_cases, served_json, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, '[]', 'active', ?, ?)",
                (session_id, learner_id, label, json.dumps(objectives), target_mastery, max_cases, now, now),
            )
        return session_id

    def get_review_session(self, session_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT session_id, learner_id, label, objectives_json, target_mastery, max_cases, served_json, "
                "status, created_at, updated_at FROM review_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "sessionId": row["session_id"],
            "learnerId": row["learner_id"],
            "label": row["label"],
            "objectives": json.loads(row["objectives_json"]),
            "targetMastery": row["target_mastery"],
            "maxCases": row["max_cases"],
            "served": json.loads(row["served_json"]),
            "status": row["status"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def record_review_served(self, session_id: str, case_id: str, status: str | None = None) -> None:
        session = self.get_review_session(session_id)
        if not session:
            return
        served = session["served"]
        if case_id not in served:
            served.append(case_id)
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                "UPDATE review_sessions SET served_json = ?, status = COALESCE(?, status), updated_at = ? "
                "WHERE session_id = ?",
                (json.dumps(served), status, now, session_id),
            )

    def set_review_status(self, session_id: str, status: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE review_sessions SET status = ?, updated_at = ? WHERE session_id = ?",
                (status, utc_now(), session_id),
            )

    # --- clinical shift sessions (Clinical Decisions mode) ---------------------

    def create_shift_session(
        self,
        learner_id: str,
        lane: str,
        tier: str,
        length: int = 5,
        focus_objective: str | None = None,
        focus_subskill: str | None = None,
        requested_length: int | None = None,
        available_length: int | None = None,
        length_reason: str | None = None,
    ) -> str:
        import uuid

        self.ensure_profile(learner_id)
        now = utc_now()
        session_id = f"cs_{uuid.uuid4().hex[:16]}"
        requested = int(length if requested_length is None else requested_length)
        available = int(length if available_length is None else available_length)
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            # A deliberate new shift replaces any unfinished presentation for this
            # learner, making active-session discovery deterministic.
            conn.execute(
                "UPDATE clinical_shift_sessions SET status = 'abandoned', feedback_item_id = NULL, "
                "updated_at = ? WHERE learner_id = ? AND (status = 'active' OR feedback_item_id IS NOT NULL)",
                (now, learner_id),
            )
            conn.execute(
                "INSERT INTO clinical_shift_sessions (session_id, learner_id, lane, tier, focus_objective, focus_subskill, "
                "length, requested_length, available_length, length_reason, served_json, served_ecgs_json, "
                "calibration_json, pending_item_id, feedback_item_id, position, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', '[]', '[]', NULL, NULL, 0, ?, ?, ?)",
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
        return session_id

    def get_shift_session(self, session_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT session_id, learner_id, lane, tier, focus_objective, focus_subskill, length, requested_length, "
                "available_length, length_reason, served_json, served_ecgs_json, calibration_json, "
                "pending_item_id, feedback_item_id, pending_context_revealed, pending_first_look_json, "
                "pending_orient_started_at, pending_orient_deadline_at, pending_decide_started_at, "
                "pending_decide_deadline_at, pending_decide_submitted_at, position, status, "
                "created_at, updated_at "
                "FROM clinical_shift_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "sessionId": row["session_id"],
            "learnerId": row["learner_id"],
            "lane": row["lane"],
            "tier": row["tier"],
            "focusObjective": row["focus_objective"],
            "focusSubskill": row["focus_subskill"],
            "length": row["length"],
            "requestedLength": row["requested_length"],
            "availableDistinctEcgs": row["available_length"],
            "lengthReason": row["length_reason"],
            "served": json.loads(row["served_json"]),
            "servedEcgs": json.loads(row["served_ecgs_json"]),
            "calibration": json.loads(row["calibration_json"]),
            "pendingItemId": row["pending_item_id"],
            "feedbackItemId": row["feedback_item_id"],
            "contextRevealed": bool(row["pending_context_revealed"]),
            "firstLook": (
                json.loads(row["pending_first_look_json"])
                if row["pending_first_look_json"] is not None
                else None
            ),
            "orientStartedAt": row["pending_orient_started_at"],
            "orientDeadlineAt": row["pending_orient_deadline_at"],
            "decideStartedAt": row["pending_decide_started_at"],
            "decideDeadlineAt": row["pending_decide_deadline_at"],
            "decideSubmittedAt": row["pending_decide_submitted_at"],
            "position": row["position"],
            "status": row["status"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def set_shift_pending(self, session_id: str, item_id: str) -> dict[str, Any] | None:
        """Persist the current item once; concurrent/repeated `next` calls keep it stable."""
        with self.connect() as conn:
            conn.execute(
                "UPDATE clinical_shift_sessions SET pending_item_id = ?, pending_context_revealed = 0, "
                "pending_first_look_json = NULL, pending_orient_started_at = NULL, "
                "pending_orient_deadline_at = NULL, pending_decide_started_at = NULL, "
                "pending_decide_deadline_at = NULL, pending_decide_submitted_at = NULL, updated_at = ? "
                "WHERE session_id = ? AND pending_item_id IS NULL AND feedback_item_id IS NULL "
                "AND status = 'active'",
                (item_id, utc_now(), session_id),
            )
        return self.get_shift_session(session_id)

    def get_resumable_shift_session(self, learner_id: str) -> dict[str, Any] | None:
        """Return the learner's one durable Clinical presentation.

        Active work and unacknowledged feedback win.  If neither exists, the most
        recent completed report remains discoverable across refresh/devices.
        """
        with self.connect() as conn:
            row = conn.execute(
                "SELECT session_id FROM clinical_shift_sessions WHERE learner_id = ? "
                "AND (status = 'active' OR feedback_item_id IS NOT NULL) "
                "ORDER BY updated_at DESC LIMIT 1",
                (learner_id,),
            ).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT session_id FROM clinical_shift_sessions WHERE learner_id = ? "
                    "AND status = 'complete' ORDER BY updated_at DESC LIMIT 1",
                    (learner_id,),
                ).fetchone()
        return self.get_shift_session(row["session_id"]) if row else None

    def acknowledge_shift_feedback(self, session_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE clinical_shift_sessions SET feedback_item_id = NULL, updated_at = ? "
                "WHERE session_id = ?",
                (utc_now(), session_id),
            )
        return self.get_shift_session(session_id)

    def activate_shift_phase(
        self,
        session_id: str,
        item_id: str,
        phase: str,
        duration_seconds: int | None,
    ) -> dict[str, Any]:
        """Activate one server-owned phase clock exactly once.

        The route derives ``duration_seconds`` from the persisted item/tier; no
        client duration participates in this write boundary.
        """
        if phase not in {"orient", "decide"}:
            return {"status": "invalid_phase"}
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        deadline = (
            (now_dt + timedelta(seconds=int(duration_seconds))).isoformat()
            if duration_seconds is not None
            else None
        )
        started_column = f"pending_{phase}_started_at"
        deadline_column = f"pending_{phase}_deadline_at"
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT pending_item_id, pending_context_revealed, status, "
                f"{started_column} AS started_at FROM clinical_shift_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if not row:
                return {"status": "missing"}
            if row["pending_item_id"] != item_id or row["status"] != "active":
                return {"status": "not_pending", "pendingItemId": row["pending_item_id"]}
            phase_ready = (phase == "orient" and not row["pending_context_revealed"]) or (
                phase == "decide" and bool(row["pending_context_revealed"])
            )
            if not phase_ready:
                return {"status": "phase_not_ready"}
            if row["started_at"]:
                return {"status": "replay"}
            conn.execute(
                f"UPDATE clinical_shift_sessions SET {started_column} = ?, {deadline_column} = ?, "
                "updated_at = ? WHERE session_id = ? AND pending_item_id = ? "
                f"AND {started_column} IS NULL",
                (now, deadline, now, session_id, item_id),
            )
        return {"status": "activated"}

    def reveal_shift_context(
        self,
        session_id: str,
        item_id: str,
        first_look: dict[str, Any],
        decide_duration_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Persist the ECG-only commitment before authored context is served.

        The first commitment wins. A repeated reveal request replays that value,
        which makes refresh/resume safe without letting the pre-context answer be
        silently revised.
        """
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        decide_deadline = (
            (now_dt + timedelta(seconds=int(decide_duration_seconds))).isoformat()
            if decide_duration_seconds is not None
            else None
        )
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT pending_item_id, pending_context_revealed, pending_first_look_json, tier, "
                "pending_orient_started_at, pending_orient_deadline_at, pending_decide_started_at "
                "FROM clinical_shift_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if not row:
                return {"status": "missing"}
            if row["pending_item_id"] != item_id:
                return {"status": "not_pending", "pendingItemId": row["pending_item_id"]}
            if row["pending_context_revealed"]:
                return {
                    "status": "replay",
                    "firstLook": json.loads(row["pending_first_look_json"] or "{}"),
                }
            if row["tier"] == "shift" and not row["pending_orient_started_at"]:
                # A timed first look cannot begin at page/request time. The viewer
                # readiness activation endpoint is the only clock start boundary.
                return {"status": "phase_not_activated"}
            orient_started = (
                datetime.fromisoformat(str(row["pending_orient_started_at"]))
                if row["pending_orient_started_at"]
                else now_dt
            )
            orient_deadline = (
                datetime.fromisoformat(str(row["pending_orient_deadline_at"]))
                if row["pending_orient_deadline_at"]
                else None
            )
            durable_first_look = {
                **first_look,
                "orientAnswerTimeMs": max(0, int((now_dt - orient_started).total_seconds() * 1000)),
                "orientTimedOut": bool(orient_deadline and now_dt >= orient_deadline),
                "orientStartedAt": row["pending_orient_started_at"] or now,
                "orientDeadlineAt": row["pending_orient_deadline_at"],
            }
            conn.execute(
                "UPDATE clinical_shift_sessions SET pending_context_revealed = 1, "
                "pending_first_look_json = ?, pending_decide_started_at = ?, "
                "pending_decide_deadline_at = ?, updated_at = ? WHERE session_id = ? "
                "AND pending_context_revealed = 0",
                (json.dumps(durable_first_look), now, decide_deadline, now, session_id),
            )
            return {"status": "recorded", "firstLook": durable_first_look}

    def claim_shift_submission_timing(self, session_id: str, item_id: str) -> dict[str, Any]:
        """Freeze one authoritative decision submission timestamp.

        Freezing before grading keeps the timeout decision and response time stable
        across retries and concurrent submissions. Client timing fields are never
        read at this boundary.
        """
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT pending_item_id, pending_context_revealed, pending_decide_started_at, "
                "pending_decide_deadline_at, pending_decide_submitted_at, status "
                "FROM clinical_shift_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if not row:
                return {"status": "missing"}
            if row["pending_item_id"] != item_id or row["status"] != "active":
                return {"status": "not_pending", "pendingItemId": row["pending_item_id"]}
            if not row["pending_context_revealed"]:
                return {"status": "context_not_revealed", "pendingItemId": item_id}
            started_at = row["pending_decide_started_at"] or now
            submitted_at = row["pending_decide_submitted_at"] or now
            if not row["pending_decide_started_at"] or not row["pending_decide_submitted_at"]:
                conn.execute(
                    "UPDATE clinical_shift_sessions SET pending_decide_started_at = COALESCE(pending_decide_started_at, ?), "
                    "pending_decide_submitted_at = COALESCE(pending_decide_submitted_at, ?), updated_at = ? "
                    "WHERE session_id = ? AND pending_item_id = ?",
                    (started_at, submitted_at, now, session_id, item_id),
                )
            started_dt = datetime.fromisoformat(str(started_at))
            submitted_dt = datetime.fromisoformat(str(submitted_at))
            deadline_at = row["pending_decide_deadline_at"]
            deadline_dt = datetime.fromisoformat(str(deadline_at)) if deadline_at else None
            return {
                "status": "claimed" if not row["pending_decide_submitted_at"] else "replay",
                "startedAt": started_at,
                "deadlineAt": deadline_at,
                "submittedAt": submitted_at,
                "answerTimeMs": max(0, int((submitted_dt - started_dt).total_seconds() * 1000)),
                "timedOut": bool(deadline_dt and submitted_dt >= deadline_dt),
            }

    def _record_formative_subskill_receipts_in_transaction(
        self,
        conn: sqlite3.Connection,
        *,
        learner_id: str,
        events: list[dict[str, Any]],
        now: str,
    ) -> list[dict[str, Any]]:
        """Apply server-authored Clinical evidence on the answer transaction.

        Clinical content is automated-screened and pending named clinician
        sign-off, so this path can update formative evidence only.  It never
        increments independent attempts, creates retention events, or schedules
        a due date.  The enclosing unique Clinical answer row is the exactly-once
        idempotency boundary.
        """

        receipts: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for event in events:
            concept = str(event.get("concept") or "").strip()
            subskill = str(event.get("subskill") or "").strip()
            key = (concept, subskill)
            if not concept or not subskill or key in seen:
                continue
            seen.add(key)
            definition = objective_definition(concept)
            if definition is None or subskill not in definition.allowed_subskills:
                raise ValueError(
                    f"Clinical competency event targets unavailable cell {concept} x {subskill}."
                )
            score = max(0.0, min(1.0, float(event.get("score", 0.0))))
            correct = bool(event.get("correct"))
            confidence = event.get("confidence")
            high_conf_wrong = 1 if confidence is not None and int(confidence) >= 4 and not correct else 0
            current = conn.execute(
                """
                SELECT formative_score, independent_mastery, attempts,
                       independent_attempts, correct, high_confidence_wrong,
                       next_due_at, stability_days, lapses, spaced_retrievals,
                       distinct_eligible_ecgs, distinct_successful_ecgs,
                       distinct_modes, distinct_morphologies,
                       last_independent_at, last_independent_correct
                FROM subskill_mastery
                WHERE learner_id = ? AND concept = ? AND subskill = ?
                """,
                (learner_id, concept, subskill),
            ).fetchone()
            formative = float(current["formative_score"]) if current else 0.0
            formative_delta = (0.04 + 0.04 * score) if correct else -0.04
            next_formative = min(1.0, max(0.0, formative + formative_delta))
            if current:
                conn.execute(
                    """
                    UPDATE subskill_mastery
                    SET formative_score = ?, attempts = attempts + 1,
                        correct = correct + ?,
                        high_confidence_wrong = high_confidence_wrong + ?,
                        last_practiced_at = ?
                    WHERE learner_id = ? AND concept = ? AND subskill = ?
                    """,
                    (
                        next_formative,
                        1 if correct else 0,
                        high_conf_wrong,
                        now,
                        learner_id,
                        concept,
                        subskill,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO subskill_mastery (
                        learner_id, concept, subskill, formative_score,
                        independent_mastery, attempts, independent_attempts,
                        correct, high_confidence_wrong, last_practiced_at
                    ) VALUES (?, ?, ?, ?, 0.15, 1, 0, ?, ?, ?)
                    """,
                    (
                        learner_id,
                        concept,
                        subskill,
                        next_formative,
                        1 if correct else 0,
                        high_conf_wrong,
                        now,
                    ),
                )
            retention_values = {
                "nextDueAt": current["next_due_at"] if current else None,
                "stabilityDays": float(current["stability_days"]) if current else 0.0,
                "lapses": int(current["lapses"]) if current else 0,
                "spacedRetrievals": int(current["spaced_retrievals"]) if current else 0,
                "distinctEligibleEcgs": int(current["distinct_eligible_ecgs"]) if current else 0,
                "distinctSuccessfulEcgs": int(current["distinct_successful_ecgs"]) if current else 0,
                "distinctModes": int(current["distinct_modes"]) if current else 0,
                "distinctMorphologies": int(current["distinct_morphologies"]) if current else 0,
                "lastIndependentAt": current["last_independent_at"] if current else None,
                "lastIndependentCorrect": (
                    bool(current["last_independent_correct"])
                    if current and current["last_independent_correct"] is not None
                    else None
                ),
            }
            due = due_snapshot(retention_values, as_of=datetime.fromisoformat(now))
            receipts.append({
                "concept": concept,
                "subskill": subskill,
                "score": round(score, 3),
                "correct": correct,
                "formativeScore": round(next_formative, 3),
                "independentMastery": round(
                    float(current["independent_mastery"]) if current else 0.15,
                    3,
                ),
                "evidenceLevel": "guided",
                "formativeOnly": True,
                "retentionEligible": False,
                "nextDueAt": retention_values["nextDueAt"],
                "stabilityDays": retention_values["stabilityDays"],
                "lapses": retention_values["lapses"],
                "spacedRetrievals": retention_values["spacedRetrievals"],
                "distinctEligibleEcgs": retention_values["distinctEligibleEcgs"],
                "distinctSuccessfulEcgs": retention_values["distinctSuccessfulEcgs"],
                "distinctModes": retention_values["distinctModes"],
                "distinctMorphologies": retention_values["distinctMorphologies"],
                "dueState": due["dueState"],
                "intervalExpanded": False,
                "evidenceSource": str(event.get("evidenceSource") or "clinical_server_grade"),
                "mode": "clinical",
                "caseId": str(event.get("caseId") or ""),
                "itemId": str(event.get("itemId") or ""),
            })
        return receipts

    @staticmethod
    def _shift_answer_dict(row: sqlite3.Row) -> dict[str, Any]:
        receipts = json.loads(row["receipts_json"] or "[]") if "receipts_json" in row.keys() else []
        return {
            "answerId": int(row["id"]),
            "sessionId": row["session_id"],
            "itemId": row["item_id"],
            "ecgId": row["ecg_id"],
            "response": json.loads(row["response_json"]),
            "grade": json.loads(row["grade_json"]),
            "receipts": receipts,
            "score": float(row["score"]),
            "correct": bool(row["correct"]),
            "answerTimeMs": row["answer_time_ms"],
            "calibrationEvent": (
                json.loads(row["calibration_event_json"])
                if row["calibration_event_json"] is not None
                else None
            ),
            "attemptId": int(row["attempt_id"]),
            "createdAt": row["created_at"],
        }

    def get_shift_answer(self, session_id: str, item_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM clinical_shift_answers WHERE session_id = ? AND item_id = ?",
                (session_id, item_id),
            ).fetchone()
        return self._shift_answer_dict(row) if row else None

    def get_shift_answers(self, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM clinical_shift_answers WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
        return [self._shift_answer_dict(row) for row in rows]

    def record_shift_answer(
        self,
        *,
        session_id: str,
        item_id: str,
        ecg_id: str,
        response: dict[str, Any],
        grade: dict[str, Any],
        correct: bool,
        confidence: int,
        calibration_event: dict[str, Any] | None,
        competency_events: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Exactly-once Clinical write boundary.

        A replay returns the first stored grade. A first submission is accepted only
        for the persisted pending item, and advances attempts/mastery/position once.
        """
        now = utc_now()
        with self.connect() as conn:
            # Serialize file-backed writers before checking the uniqueness/pending gates.
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM clinical_shift_answers WHERE session_id = ? AND item_id = ?",
                (session_id, item_id),
            ).fetchone()
            if existing:
                return {"status": "replay", "answer": self._shift_answer_dict(existing)}

            session = conn.execute(
                "SELECT learner_id, tier, length, served_json, served_ecgs_json, calibration_json, "
                "pending_item_id, pending_context_revealed, pending_first_look_json, "
                "pending_decide_submitted_at "
                "FROM clinical_shift_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if not session:
                return {"status": "missing"}
            if session["pending_item_id"] != item_id:
                return {"status": "not_pending", "pendingItemId": session["pending_item_id"]}
            if not session["pending_context_revealed"]:
                return {"status": "context_not_revealed", "pendingItemId": session["pending_item_id"]}
            if not session["pending_decide_submitted_at"]:
                return {"status": "timing_not_claimed", "pendingItemId": session["pending_item_id"]}

            receipts = self._record_formative_subskill_receipts_in_transaction(
                conn,
                learner_id=session["learner_id"],
                events=competency_events or [],
                now=now,
            )
            stored_grade = {**grade, "competencyReceipts": receipts}
            attempt_id = self._save_attempt_in_transaction(
                conn,
                learner_id=session["learner_id"],
                case_id=ecg_id,
                mode="clinical_decision",
                structured_answer=response,
                confidence=confidence,
                grade=stored_grade,
                now=now,
            )
            cursor = conn.execute(
                """
                INSERT INTO clinical_shift_answers (
                    session_id, item_id, ecg_id, response_json, grade_json,
                    receipts_json, score, correct, answer_time_ms,
                    calibration_event_json, attempt_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
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
                "pending_first_look_json = NULL, pending_orient_started_at = NULL, "
                "pending_orient_deadline_at = NULL, pending_decide_started_at = NULL, "
                "pending_decide_deadline_at = NULL, pending_decide_submitted_at = NULL, "
                "feedback_item_id = ?, position = ?, status = ?, updated_at = ? "
                "WHERE session_id = ?",
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
            answer_row = conn.execute(
                "SELECT * FROM clinical_shift_answers WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            return {"status": "created", "answer": self._shift_answer_dict(answer_row)}

    def record_shift_served(
        self, session_id: str, item_id: str, calibration_event: dict[str, Any] | None = None
    ) -> None:
        session = self.get_shift_session(session_id)
        if not session:
            return
        served = session["served"]
        if item_id not in served:
            served.append(item_id)
        calibration = session["calibration"]
        if calibration_event is not None:
            calibration.append(calibration_event)
        position = session["position"] + 1
        status = "complete" if position >= session["length"] else "active"
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                "UPDATE clinical_shift_sessions SET served_json = ?, calibration_json = ?, position = ?, "
                "status = ?, updated_at = ? WHERE session_id = ?",
                (json.dumps(served), json.dumps(calibration), position, status, now, session_id),
            )

    def set_shift_status(self, session_id: str, status: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE clinical_shift_sessions SET status = ?, updated_at = ? WHERE session_id = ?",
                (status, utc_now(), session_id),
            )

    def _misconception_counts(self, conn: sqlite3.Connection, learner_id: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            "SELECT misconception_tags_json FROM attempts WHERE learner_id = ? ORDER BY id DESC LIMIT 50",
            (learner_id,),
        ).fetchall()
        counts: dict[str, int] = {}
        for row in rows:
            for tag in json.loads(row["misconception_tags_json"]):
                counts[tag] = counts.get(tag, 0) + 1
        return [
            {"tag": tag, "count": count}
            for tag, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)
        ]
