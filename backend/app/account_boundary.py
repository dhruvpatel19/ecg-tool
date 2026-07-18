"""Durable database boundary for retired account generations.

Account deletion removes every directly or transitively owned row.  A request
that authenticated before deletion can still resume afterwards, however, and
historically an idempotent profile write could recreate that owner's graph.
This module gives SQLite the final say: deleting an account retires its opaque
user-id generation, and triggers reject every later owner-scoped mutation.

Only a domain-separated digest of the high-entropy internal user id is kept.
No username, email address, display name, or raw user id survives deletion.
Legacy guest ids are never retired and retain their existing lifecycle.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from collections.abc import Mapping


ACCOUNT_GENERATION_RETIRED = "account_generation_retired"
OWNER_PARENT_MISSING = "owner_parent_missing"
_OWNER_GENERATION_DOMAIN = b"ecg-account-generation-v1\x00"
_SAFE_IDENTIFIER = re.compile(r"\A[A-Za-z_][A-Za-z0-9_]*\Z")


class AccountGenerationRetiredError(RuntimeError):
    """A stale write targeted an account generation that was deleted."""


class OwnerParentMissingError(RuntimeError):
    """A child-ledger write lost its owner-scoped parent transaction."""


# Every table that stores an authenticated owner directly.  Guest rows share
# these tables, but remain writable because guest deletion never creates an
# account-generation tombstone.
DIRECT_OWNER_TABLES: Mapping[str, str] = {
    "users": "user_id",
    "sessions": "user_id",
    "export_authorizations": "user_id",
    "auth_challenges": "user_id",
    "learner_profiles": "learner_id",
    "learner_preferences": "learner_id",
    "learner_calendar_settings": "learner_id",
    "study_calendar_items": "learner_id",
    "objective_mastery": "learner_id",
    "subskill_mastery": "learner_id",
    "subskill_retention_events": "learner_id",
    "guided_learning_events": "learner_id",
    "attempts": "learner_id",
    "pathway_progress": "learner_id",
    "tutor_threads": "learner_id",
    "review_sessions": "learner_id",
    "rapid_rounds": "learner_id",
    "clinical_shift_sessions": "learner_id",
    "training_campaigns": "learner_id",
    "assessment_leases": "owner_id",
    "learner_events": "owner_id",
    "learning_session_flags": "owner_id",
    "guest_progress_claims": "user_id",
}


# Child ledgers inherit ownership through a parent.  Requiring the parent in
# the trigger prevents a post-deletion request from leaving an ownerless row
# after the parent has already been purged.
CHILD_OWNER_TABLES: Mapping[str, tuple[str, str, str]] = {
    "tutor_messages": ("thread_id", "tutor_threads", "thread_id"),
    "rapid_round_answers": ("round_id", "rapid_rounds", "round_id"),
    "clinical_shift_answers": (
        "session_id",
        "clinical_shift_sessions",
        "session_id",
    ),
    "training_campaign_slots": (
        "campaign_id",
        "training_campaigns",
        "campaign_id",
    ),
    "training_campaign_answers": (
        "campaign_id",
        "training_campaigns",
        "campaign_id",
    ),
    "assessment_lease_cases": (
        "lease_id",
        "assessment_leases",
        "lease_id",
    ),
    "learner_event_competencies": (
        "event_id",
        "learner_events",
        "event_id",
    ),
}


_PARENT_OWNER_COLUMNS: Mapping[str, str] = {
    "tutor_threads": "learner_id",
    "rapid_rounds": "learner_id",
    "clinical_shift_sessions": "learner_id",
    "training_campaigns": "learner_id",
    "assessment_leases": "owner_id",
    "learner_events": "owner_id",
}


def account_generation_key(owner_id: object) -> str:
    """Return a stable, non-reversible key for one opaque account generation."""

    if not isinstance(owner_id, str) or not owner_id:
        return ""
    return hashlib.sha256(
        _OWNER_GENERATION_DOMAIN + owner_id.encode("utf-8")
    ).hexdigest()


def configure_account_boundary(conn: sqlite3.Connection) -> None:
    """Register the deterministic function used by durable SQLite triggers."""

    conn.create_function(
        "account_generation_key",
        1,
        account_generation_key,
        deterministic=True,
    )


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone() is not None


def _identifier(value: str) -> str:
    if not _SAFE_IDENTIFIER.fullmatch(value):
        raise ValueError("Unsafe owner-boundary schema identifier")
    return value


def ensure_account_boundary_schema(conn: sqlite3.Connection) -> None:
    """Create the tombstone ledger and guards for all currently present tables."""

    configure_account_boundary(conn)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS account_tombstones ("
        "owner_key TEXT PRIMARY KEY CHECK (length(owner_key) = 64), "
        "retired_at TEXT NOT NULL, "
        "reason TEXT NOT NULL CHECK (reason IN ("
        "'owner_deleted', 'pending_registration_cancelled', "
        "'unverified_registration_expired')), "
        "boundary_version INTEGER NOT NULL DEFAULT 1 "
        "CHECK (boundary_version = 1))"
    )

    for table, owner_column in DIRECT_OWNER_TABLES.items():
        if not _table_exists(conn, table):
            continue
        table = _identifier(table)
        owner_column = _identifier(owner_column)
        for operation in ("INSERT", "UPDATE"):
            trigger = _identifier(
                f"account_generation_guard_{table}_{operation.lower()}"
            )
            conn.execute(
                f"CREATE TRIGGER IF NOT EXISTS {trigger} "
                f"BEFORE {operation} ON {table} "
                "WHEN EXISTS (SELECT 1 FROM account_tombstones "
                f"WHERE owner_key = account_generation_key(NEW.{owner_column})) "
                f"BEGIN SELECT RAISE(ABORT, '{ACCOUNT_GENERATION_RETIRED}'); END"
            )

    for child, (child_key, parent, parent_key) in CHILD_OWNER_TABLES.items():
        if not (_table_exists(conn, child) and _table_exists(conn, parent)):
            continue
        child = _identifier(child)
        child_key = _identifier(child_key)
        parent = _identifier(parent)
        parent_key = _identifier(parent_key)
        parent_owner = _identifier(_PARENT_OWNER_COLUMNS[parent])
        for operation in ("INSERT", "UPDATE"):
            suffix = operation.lower()
            parent_trigger = _identifier(
                f"account_owner_parent_guard_{child}_{suffix}"
            )
            retired_trigger = _identifier(
                f"account_generation_guard_{child}_{suffix}"
            )
            conn.execute(
                f"CREATE TRIGGER IF NOT EXISTS {parent_trigger} "
                f"BEFORE {operation} ON {child} "
                f"WHEN NOT EXISTS (SELECT 1 FROM {parent} "
                f"WHERE {parent_key} = NEW.{child_key}) "
                f"BEGIN SELECT RAISE(ABORT, '{OWNER_PARENT_MISSING}'); END"
            )
            conn.execute(
                f"CREATE TRIGGER IF NOT EXISTS {retired_trigger} "
                f"BEFORE {operation} ON {child} "
                "WHEN EXISTS (SELECT 1 FROM account_tombstones tombstone "
                f"JOIN {parent} parent ON "
                f"parent.{parent_key} = NEW.{child_key} "
                "WHERE tombstone.owner_key = "
                f"account_generation_key(parent.{parent_owner})) "
                f"BEGIN SELECT RAISE(ABORT, '{ACCOUNT_GENERATION_RETIRED}'); END"
            )


def retire_account_generation(
    conn: sqlite3.Connection,
    owner_id: str,
    *,
    retired_at: str,
    reason: str,
) -> None:
    """Retire one internal account id in the caller's deletion transaction."""

    if not owner_id:
        raise ValueError("An account owner id is required")
    conn.execute(
        "INSERT INTO account_tombstones "
        "(owner_key, retired_at, reason, boundary_version) VALUES (?, ?, ?, 1) "
        "ON CONFLICT(owner_key) DO NOTHING",
        (account_generation_key(owner_id), retired_at, reason),
    )


def translate_account_boundary_error(error: sqlite3.IntegrityError) -> Exception:
    """Translate private trigger codes into stable storage-layer failures."""

    message = str(error)
    if ACCOUNT_GENERATION_RETIRED in message:
        return AccountGenerationRetiredError(
            "The account was deleted before this write could complete."
        )
    if OWNER_PARENT_MISSING in message:
        return OwnerParentMissingError(
            "The owner-scoped parent no longer exists for this write."
        )
    return error


def expected_guard_triggers(conn: sqlite3.Connection) -> set[str]:
    """Return the complete expected trigger inventory for present owner tables."""

    names: set[str] = set()
    for table in DIRECT_OWNER_TABLES:
        if _table_exists(conn, table):
            names.update(
                {
                    f"account_generation_guard_{table}_insert",
                    f"account_generation_guard_{table}_update",
                }
            )
    for child, (_, parent, _) in CHILD_OWNER_TABLES.items():
        if _table_exists(conn, child) and _table_exists(conn, parent):
            names.update(
                {
                    f"account_owner_parent_guard_{child}_insert",
                    f"account_owner_parent_guard_{child}_update",
                    f"account_generation_guard_{child}_insert",
                    f"account_generation_guard_{child}_update",
                }
            )
    return names
