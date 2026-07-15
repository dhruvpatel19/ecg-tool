"""Explicit, one-time guest progress claims into a student account.

Nothing in this module runs implicitly during authentication. A claim is bound
to the opaque guest namespace supplied by middleware, recorded exactly once,
and completed in one SQLite transaction across every learner-owned table.
"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from .assessment_ledger import append_event, terminal_event_id, terminalize_lease
from .storage import LearningStore, utc_now


_GUEST_NAMESPACE = re.compile(r"^g_[A-Za-z0-9_-]{24,64}$")


class GuestProgressClaimConflict(ValueError):
    """The presented guest namespace is already owned by another account."""


class GuestProgressClaimUnavailable(ValueError):
    """The presented legacy guest namespace contains no claimable work."""


def _json(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return fallback


def _latest(*values: str | None) -> str | None:
    present = [value for value in values if value]
    return max(present) if present else None


def _earliest(*values: str | None) -> str | None:
    present = [value for value in values if value]
    return min(present) if present else None


class GuestProgressService:
    def __init__(self, store: LearningStore):
        self.store = store
        with self.store.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS guest_progress_claims (
                    guest_learner_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    claimed_at TEXT NOT NULL,
                    summary_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_guest_claim_user
                    ON guest_progress_claims(user_id, claimed_at);
                """
            )
            self.store.ensure_account_write_guards(conn)

    @staticmethod
    def _validate_guest(guest_id: str) -> None:
        # The deterministic demo principal exists only in the isolated test app.
        if guest_id != "demo" and not _GUEST_NAMESPACE.fullmatch(guest_id or ""):
            raise ValueError("Invalid guest namespace")

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone() is not None

    @staticmethod
    def _count(conn: sqlite3.Connection, table: str, column: str, owner: str) -> int:
        if not GuestProgressService._table_exists(conn, table):
            return 0
        return int(
            conn.execute(
                f"SELECT COUNT(*) AS n FROM {table} WHERE {column} = ?", (owner,)
            ).fetchone()["n"]
        )

    def summary(self, guest_id: str) -> dict[str, Any]:
        self._validate_guest(guest_id)
        with self.store.connect() as conn:
            return self._summary(conn, guest_id)

    @staticmethod
    def empty_summary() -> dict[str, Any]:
        """Return the migration preview for a browser without a legacy identity."""

        return {
            "hasProgress": False,
            "claimable": False,
            "totalActivities": 0,
            "attempts": 0,
            "guidedInteractions": 0,
            "competencyReceipts": 0,
            "lessonScenes": 0,
            "tutorThreads": 0,
            "reviewSessions": 0,
            "rapidRounds": 0,
            "clinicalSessions": 0,
            "trainingCampaigns": 0,
            "learnerEvents": 0,
            "learningPreferences": 0,
            "competencies": 0,
            "lastActivityAt": None,
        }

    def delete(self, guest_id: str) -> int:
        """Erase the current guest namespace without touching any account."""

        self._validate_guest(guest_id)
        return self.store.delete_guest_learning_record(guest_id)

    def _summary(self, conn: sqlite3.Connection, guest_id: str) -> dict[str, Any]:
        counts = {
            "attempts": self._count(conn, "attempts", "learner_id", guest_id),
            "guidedInteractions": self._count(conn, "guided_learning_events", "learner_id", guest_id),
            "competencyReceipts": self._count(conn, "subskill_retention_events", "learner_id", guest_id),
            "lessonScenes": self._count(conn, "pathway_progress", "learner_id", guest_id),
            "tutorThreads": self._count(conn, "tutor_threads", "learner_id", guest_id),
            "reviewSessions": self._count(conn, "review_sessions", "learner_id", guest_id),
            "rapidRounds": self._count(conn, "rapid_rounds", "learner_id", guest_id),
            "clinicalSessions": self._count(conn, "clinical_shift_sessions", "learner_id", guest_id),
            "trainingCampaigns": self._count(conn, "training_campaigns", "learner_id", guest_id),
            "learnerEvents": self._count(conn, "learner_events", "owner_id", guest_id),
            "learningPreferences": self._count(conn, "learner_preferences", "learner_id", guest_id),
        }
        competency_rows = 0
        if self._table_exists(conn, "objective_mastery"):
            competency_rows += int(
                conn.execute(
                    "SELECT COUNT(*) AS n FROM objective_mastery WHERE learner_id = ? AND attempts > 0",
                    (guest_id,),
                ).fetchone()["n"]
            )
        if self._table_exists(conn, "subskill_mastery"):
            competency_rows += int(
                conn.execute(
                    "SELECT COUNT(*) AS n FROM subskill_mastery WHERE learner_id = ? AND attempts > 0",
                    (guest_id,),
                ).fetchone()["n"]
            )
        counts["competencies"] = competency_rows

        total = sum(counts.values())
        timestamps: list[str] = []
        timestamp_tables = (
            ("attempts", "learner_id", "created_at"),
            ("guided_learning_events", "learner_id", "created_at"),
            ("pathway_progress", "learner_id", "updated_at"),
            ("tutor_threads", "learner_id", "updated_at"),
            ("review_sessions", "learner_id", "updated_at"),
            ("rapid_rounds", "learner_id", "updated_at"),
            ("clinical_shift_sessions", "learner_id", "updated_at"),
            ("training_campaigns", "learner_id", "updated_at"),
            ("learner_events", "owner_id", "occurred_at"),
            ("learner_preferences", "learner_id", "updated_at"),
        )
        for table, owner_column, timestamp_column in timestamp_tables:
            if not self._table_exists(conn, table):
                continue
            row = conn.execute(
                f"SELECT MAX({timestamp_column}) AS value FROM {table} WHERE {owner_column} = ?",
                (guest_id,),
            ).fetchone()
            if row and row["value"]:
                timestamps.append(str(row["value"]))
        claimed = conn.execute(
            "SELECT 1 FROM guest_progress_claims WHERE guest_learner_id = ?", (guest_id,)
        ).fetchone()
        return {
            "hasProgress": total > 0,
            "claimable": total > 0 and claimed is None,
            "totalActivities": total,
            **counts,
            "lastActivityAt": max(timestamps) if timestamps else None,
        }

    def claim(self, guest_id: str, user_id: str) -> dict[str, Any]:
        self._validate_guest(guest_id)
        with self.store.connect() as conn:
            try:
                if not conn.in_transaction:
                    conn.execute("BEGIN IMMEDIATE")
                return self._claim(conn, guest_id, user_id)
            except Exception:
                conn.rollback()
                raise

    def create_user_and_claim(
        self,
        *,
        user_id: str,
        username: str,
        display_name: str,
        password_hash: str,
        email_normalized: str | None,
        guest_id: str,
        session_token: str | None,
        session_expires_at: str | None,
        _transaction_hook: Any | None = None,
        _failure_hook: Any | None = None,
    ) -> dict[str, Any]:
        """Create an account, claim, and issue its session in one transaction.

        A conflict or session failure rolls back the username, profile defaults,
        session, and all ownership changes together, so registration is safely
        retryable.
        """
        self._validate_guest(guest_id)
        now = utc_now()
        with self.store.connect() as conn:
            try:
                if not conn.in_transaction:
                    conn.execute("BEGIN IMMEDIATE")
                self.store._insert_new_user_graph(
                    conn,
                    user_id=user_id,
                    username=username,
                    display_name=display_name,
                    password_hash=password_hash,
                    email_normalized=email_normalized,
                    account_origin="established",
                    now=now,
                )
                claim = self._claim(conn, guest_id, user_id)
                if _transaction_hook is not None:
                    _transaction_hook(conn, now, claim)
                if session_token is not None and session_expires_at is not None:
                    self.store._insert_session(
                        conn,
                        token=session_token,
                        user_id=user_id,
                        expires_at=session_expires_at,
                        now=now,
                    )
                if _failure_hook is not None:
                    _failure_hook(conn)
                return claim
            except Exception:
                conn.rollback()
                raise

    def claim_and_create_session(
        self,
        *,
        guest_id: str,
        user_id: str,
        expected_password_hash: str,
        session_token: str,
        session_expires_at: str,
        replacement_password_hash: str | None = None,
        _failure_hook: Any | None = None,
    ) -> dict[str, Any] | None:
        """Claim and mint a login session under one credential-checked write lock."""

        self._validate_guest(guest_id)
        now = utc_now()
        with self.store.connect() as conn:
            try:
                if not conn.in_transaction:
                    conn.execute("BEGIN IMMEDIATE")
                current = conn.execute(
                    "SELECT password_hash FROM users WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
                if not current or str(current["password_hash"]) != expected_password_hash:
                    return None
                if replacement_password_hash is not None:
                    updated = conn.execute(
                        "UPDATE users SET password_hash = ? "
                        "WHERE user_id = ? AND password_hash = ?",
                        (replacement_password_hash, user_id, expected_password_hash),
                    )
                    if int(updated.rowcount) != 1:
                        return None
                    if self.store._table_exists(conn, "export_authorizations"):
                        conn.execute(
                            "DELETE FROM export_authorizations WHERE user_id = ?",
                            (user_id,),
                        )
                claim = self._claim(conn, guest_id, user_id)
                self.store._insert_session(
                    conn,
                    token=session_token,
                    user_id=user_id,
                    expires_at=session_expires_at,
                    now=now,
                )
                if _failure_hook is not None:
                    _failure_hook(conn)
                return claim
            except Exception:
                conn.rollback()
                raise

    def _claim(
        self, conn: sqlite3.Connection, guest_id: str, user_id: str
    ) -> dict[str, Any]:
        existing_claim = conn.execute(
            "SELECT user_id, claimed_at, summary_json FROM guest_progress_claims "
            "WHERE guest_learner_id = ?",
            (guest_id,),
        ).fetchone()
        if existing_claim:
            if existing_claim["user_id"] != user_id:
                raise GuestProgressClaimConflict(
                    "This browser's guest progress was already claimed by another account."
                )
            return {
                "claimed": True,
                "replay": True,
                "claimedAt": existing_claim["claimed_at"],
                "guestProgress": _json(existing_claim["summary_json"], {}),
            }
        if guest_id == user_id:
            raise ValueError("Guest and account owners must differ")
        if not conn.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone():
            raise ValueError("Target account does not exist")

        summary = self._summary(conn, guest_id)
        if not summary["claimable"]:
            raise GuestProgressClaimUnavailable(
                "No unclaimed legacy guest progress is available for this browser."
            )
        now = utc_now()
        self._normalize_active_sessions(conn, guest_id, user_id, now)
        self._merge_guided_events(conn, guest_id, user_id)
        self._merge_objective_mastery(conn, guest_id, user_id)
        affected_subskills = self._merge_subskill_mastery(conn, guest_id, user_id)
        if self._table_exists(conn, "subskill_retention_events"):
            affected_subskills.update(
                (str(row["concept"]), str(row["subskill"]))
                for row in conn.execute(
                    "SELECT DISTINCT concept, subskill FROM subskill_retention_events "
                    "WHERE learner_id = ?",
                    (guest_id,),
                ).fetchall()
            )
        self._merge_pathway_progress(conn, guest_id, user_id)

        # Lease-linked events use a composite foreign key that includes owner.
        # Defer the relationship until both sides are rekeyed so a guest claim
        # remains one atomic ownership transfer even on pre-cascade databases.
        if self._table_exists(conn, "assessment_leases") or self._table_exists(conn, "learner_events"):
            conn.execute("PRAGMA defer_foreign_keys = ON")
        if self._table_exists(conn, "assessment_leases"):
            conn.execute(
                "UPDATE assessment_leases SET owner_id = ? WHERE owner_id = ?",
                (user_id, guest_id),
            )
        if self._table_exists(conn, "learner_events"):
            conn.execute(
                "UPDATE learner_events SET owner_id = ? WHERE owner_id = ?",
                (user_id, guest_id),
            )
        if self._table_exists(conn, "learner_preferences"):
            account_preferences = conn.execute(
                "SELECT 1 FROM learner_preferences WHERE learner_id = ?",
                (user_id,),
            ).fetchone()
            if account_preferences:
                conn.execute(
                    "DELETE FROM learner_preferences WHERE learner_id = ?",
                    (guest_id,),
                )
            else:
                conn.execute(
                    "UPDATE learner_preferences SET learner_id = ? WHERE learner_id = ?",
                    (user_id, guest_id),
                )

        # Global integer/UUID primary keys remain unchanged; only their owner is
        # rekeyed. Dependent answer/message rows continue to reference those IDs.
        for table in (
            "attempts",
            "tutor_threads",
            "review_sessions",
            "rapid_rounds",
            "clinical_shift_sessions",
            "training_campaigns",
        ):
            if self._table_exists(conn, table):
                conn.execute(
                    f"UPDATE {table} SET learner_id = ? WHERE learner_id = ?",
                    (user_id, guest_id),
                )
        if self._table_exists(conn, "subskill_retention_events"):
            conn.execute(
                "UPDATE subskill_retention_events SET learner_id = ? WHERE learner_id = ?",
                (user_id, guest_id),
            )
        self._refresh_retention_counts(conn, user_id, affected_subskills)

        guest_profile = conn.execute(
            "SELECT updated_at FROM learner_profiles WHERE learner_id = ?", (guest_id,)
        ).fetchone()
        conn.execute(
            "UPDATE learner_profiles SET updated_at = ? WHERE learner_id = ?",
            (_latest(now, guest_profile["updated_at"] if guest_profile else None), user_id),
        )
        conn.execute("DELETE FROM learner_profiles WHERE learner_id = ?", (guest_id,))
        conn.execute(
            "INSERT INTO guest_progress_claims "
            "(guest_learner_id, user_id, claimed_at, summary_json) VALUES (?, ?, ?, ?)",
            (guest_id, user_id, now, json.dumps(summary, sort_keys=True)),
        )
        return {
            "claimed": True,
            "replay": False,
            "claimedAt": now,
            "guestProgress": summary,
        }

    def _merge_guided_events(
        self, conn: sqlite3.Connection, guest_id: str, user_id: str
    ) -> None:
        if not self._table_exists(conn, "guided_learning_events"):
            return
        guest_events = conn.execute(
            "SELECT * FROM guided_learning_events "
            "WHERE learner_id = ? AND event_key IS NOT NULL",
            (guest_id,),
        ).fetchall()
        for guest_event in guest_events:
            account_event = conn.execute(
                "SELECT * FROM guided_learning_events WHERE learner_id = ? AND event_key = ?",
                (user_id, guest_event["event_key"]),
            ).fetchone()
            if not account_event:
                continue
            # Fallback event keys are hashes of the educational payload and can
            # legitimately match when two owners complete the same interaction.
            # Preserve both ledgers; claim idempotency comes from the claim marker,
            # not from deleting cross-owner evidence that happens to look alike.
            claimed_key = f"guest-claim:{guest_id[-12:]}:{guest_event['id']}"
            suffix = 1
            while conn.execute(
                "SELECT 1 FROM guided_learning_events WHERE learner_id = ? AND event_key = ?",
                (user_id, claimed_key),
            ).fetchone():
                suffix += 1
                claimed_key = f"guest-claim:{guest_id[-12:]}:{guest_event['id']}:{suffix}"
            conn.execute(
                "UPDATE guided_learning_events SET event_key = ? WHERE id = ?",
                (claimed_key, guest_event["id"]),
            )
        conn.execute(
            "UPDATE guided_learning_events SET learner_id = ? WHERE learner_id = ?",
            (user_id, guest_id),
        )

    @staticmethod
    def _merge_objective_mastery(
        conn: sqlite3.Connection, guest_id: str, user_id: str
    ) -> None:
        guest_rows = conn.execute(
            "SELECT * FROM objective_mastery WHERE learner_id = ?", (guest_id,)
        ).fetchall()
        for guest in guest_rows:
            account = conn.execute(
                "SELECT * FROM objective_mastery WHERE learner_id = ? AND objective = ?",
                (user_id, guest["objective"]),
            ).fetchone()
            if not account:
                conn.execute(
                    "UPDATE objective_mastery SET learner_id = ? "
                    "WHERE learner_id = ? AND objective = ?",
                    (user_id, guest_id, guest["objective"]),
                )
                continue
            conn.execute(
                "UPDATE objective_mastery SET mastery = ?, attempts = ?, correct = ?, "
                "high_confidence_wrong = ?, last_practiced_at = ? "
                "WHERE learner_id = ? AND objective = ?",
                (
                    max(float(account["mastery"]), float(guest["mastery"])),
                    int(account["attempts"]) + int(guest["attempts"]),
                    int(account["correct"]) + int(guest["correct"]),
                    int(account["high_confidence_wrong"]) + int(guest["high_confidence_wrong"]),
                    _latest(account["last_practiced_at"], guest["last_practiced_at"]),
                    user_id,
                    guest["objective"],
                ),
            )
            conn.execute(
                "DELETE FROM objective_mastery WHERE learner_id = ? AND objective = ?",
                (guest_id, guest["objective"]),
            )

    @staticmethod
    def _merge_subskill_mastery(
        conn: sqlite3.Connection, guest_id: str, user_id: str
    ) -> set[tuple[str, str]]:
        affected: set[tuple[str, str]] = set()
        guest_rows = conn.execute(
            "SELECT * FROM subskill_mastery WHERE learner_id = ?", (guest_id,)
        ).fetchall()
        for guest in guest_rows:
            key = (str(guest["concept"]), str(guest["subskill"]))
            affected.add(key)
            account = conn.execute(
                "SELECT * FROM subskill_mastery WHERE learner_id = ? AND concept = ? AND subskill = ?",
                (user_id, *key),
            ).fetchone()
            if not account:
                conn.execute(
                    "UPDATE subskill_mastery SET learner_id = ? "
                    "WHERE learner_id = ? AND concept = ? AND subskill = ?",
                    (user_id, guest_id, *key),
                )
                continue
            latest_independent = _latest(
                account["last_independent_at"], guest["last_independent_at"]
            )
            latest_correct = account["last_independent_correct"]
            if (
                guest["last_independent_at"]
                and (
                    not account["last_independent_at"]
                    or guest["last_independent_at"] > account["last_independent_at"]
                )
            ):
                latest_correct = guest["last_independent_correct"]
            conn.execute(
                """UPDATE subskill_mastery SET
                    formative_score = ?, independent_mastery = ?, attempts = ?,
                    independent_attempts = ?, correct = ?, high_confidence_wrong = ?,
                    last_practiced_at = ?, next_due_at = ?, stability_days = ?,
                    lapses = ?, spaced_retrievals = ?, last_independent_at = ?,
                    last_independent_correct = ?, distinct_eligible_ecgs = ?,
                    distinct_successful_ecgs = ?, distinct_modes = ?,
                    distinct_morphologies = ?
                   WHERE learner_id = ? AND concept = ? AND subskill = ?""",
                (
                    max(float(account["formative_score"]), float(guest["formative_score"])),
                    max(float(account["independent_mastery"]), float(guest["independent_mastery"])),
                    int(account["attempts"]) + int(guest["attempts"]),
                    int(account["independent_attempts"]) + int(guest["independent_attempts"]),
                    int(account["correct"]) + int(guest["correct"]),
                    int(account["high_confidence_wrong"]) + int(guest["high_confidence_wrong"]),
                    _latest(account["last_practiced_at"], guest["last_practiced_at"]),
                    _earliest(account["next_due_at"], guest["next_due_at"]),
                    max(float(account["stability_days"]), float(guest["stability_days"])),
                    int(account["lapses"]) + int(guest["lapses"]),
                    int(account["spaced_retrievals"]) + int(guest["spaced_retrievals"]),
                    latest_independent,
                    latest_correct,
                    max(int(account["distinct_eligible_ecgs"]), int(guest["distinct_eligible_ecgs"])),
                    max(int(account["distinct_successful_ecgs"]), int(guest["distinct_successful_ecgs"])),
                    max(int(account["distinct_modes"]), int(guest["distinct_modes"])),
                    max(int(account["distinct_morphologies"]), int(guest["distinct_morphologies"])),
                    user_id,
                    *key,
                ),
            )
            conn.execute(
                "DELETE FROM subskill_mastery WHERE learner_id = ? AND concept = ? AND subskill = ?",
                (guest_id, *key),
            )
        return affected

    @staticmethod
    def _merge_pathway_progress(
        conn: sqlite3.Connection, guest_id: str, user_id: str
    ) -> None:
        guest_rows = conn.execute(
            "SELECT * FROM pathway_progress WHERE learner_id = ?", (guest_id,)
        ).fetchall()
        for guest in guest_rows:
            key = (guest["pathway_id"], guest["module_id"], guest["scene_id"])
            account = conn.execute(
                "SELECT * FROM pathway_progress WHERE learner_id = ? AND pathway_id = ? "
                "AND module_id = ? AND scene_id = ?",
                (user_id, *key),
            ).fetchone()
            if not account:
                conn.execute(
                    "UPDATE pathway_progress SET learner_id = ?, source = 'guest_import' "
                    "WHERE learner_id = ? AND pathway_id = ? AND module_id = ? AND scene_id = ?",
                    (user_id, guest_id, *key),
                )
                continue
            account_status = str(account["status"])
            guest_status = str(guest["status"])
            status = guest_status if _PATHWAY_STATUS_RANK_SAFE(guest_status) > _PATHWAY_STATUS_RANK_SAFE(account_status) else account_status
            actions = list(
                dict.fromkeys(
                    list(_json(account["completed_action_ids_json"], []))
                    + list(_json(guest["completed_action_ids_json"], []))
                )
            )
            # Account state wins on a key collision; guest-only keys are retained.
            state = {
                **dict(_json(guest["state_json"], {})),
                **dict(_json(account["state_json"], {})),
            }
            conn.execute(
                "UPDATE pathway_progress SET status = ?, active_interaction_index = ?, "
                "completed_action_ids_json = ?, state_json = ?, created_at = ?, updated_at = ? "
                "WHERE learner_id = ? AND pathway_id = ? AND module_id = ? AND scene_id = ?",
                (
                    status,
                    max(int(account["active_interaction_index"]), int(guest["active_interaction_index"])),
                    json.dumps(actions, sort_keys=True),
                    json.dumps(state, sort_keys=True),
                    _earliest(account["created_at"], guest["created_at"]),
                    _latest(account["updated_at"], guest["updated_at"]),
                    user_id,
                    *key,
                ),
            )
            conn.execute(
                "DELETE FROM pathway_progress WHERE learner_id = ? AND pathway_id = ? "
                "AND module_id = ? AND scene_id = ?",
                (guest_id, *key),
            )

    @staticmethod
    def _refresh_retention_counts(
        conn: sqlite3.Connection,
        user_id: str,
        affected: set[tuple[str, str]],
    ) -> None:
        for concept, subskill in affected:
            rows = conn.execute(
                "SELECT case_id, mode, morphology_key, correct, occurred_at "
                "FROM subskill_retention_events WHERE learner_id = ? AND concept = ? AND subskill = ?",
                (user_id, concept, subskill),
            ).fetchall()
            if not rows:
                continue
            last = max(rows, key=lambda row: row["occurred_at"])
            conn.execute(
                "UPDATE subskill_mastery SET distinct_eligible_ecgs = ?, "
                "distinct_successful_ecgs = ?, distinct_modes = ?, distinct_morphologies = ?, "
                "last_independent_at = ?, last_independent_correct = ? "
                "WHERE learner_id = ? AND concept = ? AND subskill = ?",
                (
                    len({row["case_id"] for row in rows}),
                    len({row["case_id"] for row in rows if row["correct"]}),
                    len({row["mode"] for row in rows}),
                    len({row["morphology_key"] for row in rows if row["morphology_key"]}),
                    last["occurred_at"],
                    int(last["correct"]),
                    user_id,
                    concept,
                    subskill,
                ),
            )

    def _normalize_active_sessions(
        self, conn: sqlite3.Connection, guest_id: str, user_id: str, now: str
    ) -> None:
        specs = (
            ("review_sessions", "session_id", "status = 'active'", []),
            (
                "rapid_rounds",
                "round_id",
                "(status = 'active' OR feedback_case_id IS NOT NULL)",
                [
                    "pending_case_id", "feedback_case_id", "pending_started_at",
                    "pending_deadline_at",
                ],
            ),
            (
                "clinical_shift_sessions",
                "session_id",
                "(status = 'active' OR feedback_item_id IS NOT NULL)",
                [
                    "pending_item_id", "feedback_item_id", "pending_first_look_json",
                    "pending_orient_started_at", "pending_orient_deadline_at",
                    "pending_decide_started_at", "pending_decide_deadline_at",
                    "pending_decide_submitted_at",
                ],
            ),
            (
                "training_campaigns",
                "campaign_id",
                "(status = 'active' OR feedback_case_id IS NOT NULL)",
                ["pending_case_id", "feedback_case_id"],
            ),
        )
        for table, id_column, resumable_where, clear_columns in specs:
            if not self._table_exists(conn, table):
                continue
            account_rows = conn.execute(
                f"SELECT {id_column}, learner_id, updated_at FROM {table} WHERE learner_id = ? "
                f"AND {resumable_where} ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
            guest_rows = conn.execute(
                f"SELECT {id_column}, learner_id, updated_at FROM {table} WHERE learner_id = ? "
                f"AND {resumable_where} ORDER BY updated_at DESC",
                (guest_id,),
            ).fetchall()
            keep = account_rows[0][id_column] if account_rows else (
                guest_rows[0][id_column] if guest_rows else None
            )
            for row in [*account_rows, *guest_rows]:
                if row[id_column] == keep:
                    continue
                if table in {"training_campaigns", "rapid_rounds", "clinical_shift_sessions"}:
                    mode = {
                        "training_campaigns": "training",
                        "rapid_rounds": "rapid",
                        "clinical_shift_sessions": "clinical",
                    }[table]
                    lease = conn.execute(
                        "SELECT al.lease_id, al.integrity_status, alc.ecg_id "
                        "FROM assessment_leases al LEFT JOIN assessment_lease_cases alc "
                        "ON alc.lease_id = al.lease_id AND alc.ordinal = 0 "
                        "WHERE al.owner_id = ? AND al.mode = ? AND al.session_id = ? "
                        "AND al.state IN ('active', 'submitting') LIMIT 1",
                        (str(row["learner_id"]), mode, str(row[id_column])),
                    ).fetchone()
                    if lease is not None:
                        lease_id = str(lease["lease_id"])
                        lease_owner = str(row["learner_id"])
                        terminalize_lease(
                            conn,
                            lease_id=lease_id,
                            owner_id=lease_owner,
                            terminal_state="abandoned",
                            terminal_at=now,
                        )
                        append_event(
                            conn,
                            event_id=terminal_event_id(lease_id, "abandoned"),
                            owner_id=lease_owner,
                            mode=mode,
                            session_id=str(row[id_column]),
                            lease_id=lease_id,
                            ecg_id=str(lease["ecg_id"]) if lease["ecg_id"] else None,
                            event_type="item_abandoned",
                            evidence_level="formative",
                            integrity_status=str(lease["integrity_status"]),
                            occurred_at=now,
                        )
                assignments = ["status = 'abandoned'", "updated_at = ?"]
                values: list[Any] = [now]
                for column in clear_columns:
                    assignments.append(f"{column} = NULL")
                if table == "training_campaigns":
                    assignments.append("abandoned_at = ?")
                    values.append(now)
                values.append(row[id_column])
                conn.execute(
                    f"UPDATE {table} SET {', '.join(assignments)} WHERE {id_column} = ?",
                    values,
                )


def _PATHWAY_STATUS_RANK_SAFE(status: str) -> int:
    return {
        "not-started": 0,
        "viewed": 1,
        "skipped": 1,
        "attempted": 2,
        "needs-review": 3,
        "complete": 4,
    }.get(status, 0)
