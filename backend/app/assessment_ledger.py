"""Normalized assessment leases and answer-free learner event primitives.

This module deliberately owns no connection lifecycle.  Every helper operates
inside the transaction selected by its caller and never begins, commits, or
rolls back a transaction.  That makes lease transitions, grading writes, and
event appends composable as one SQLite commit when the mode stores adopt these
primitives.

The learner event ledger is intentionally narrow.  It stores provenance,
scores, and normalized competency evidence, but has no generic JSON or
answer-bearing field.  Answer contracts, submitted responses, rationales, and
feedback belong in the mode-specific protected stores.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import math
import sqlite3
from typing import Final, Literal


Mode = Literal["guided", "training", "rapid", "clinical"]
LeaseMode = Literal["training", "rapid", "clinical"]
LeaseState = Literal[
    "active",
    "submitting",
    "submitted",
    "expired",
    "abandoned",
    "superseded",
    "quarantined",
]
EventType = Literal[
    "session_started",
    "item_presented",
    "interaction_committed",
    "answer_committed",
    "item_expired",
    "item_abandoned",
    "session_abandoned",
    "session_completed",
    "pathway_progressed",
    "answer_quarantined",
]
EvidenceLevel = Literal[
    "guided", "formative", "independent_transfer", "legacy_unverified"
]
IntegrityStatus = Literal["atomic_v2", "backfilled_v1", "quarantined"]


ALLOWED_MODES: Final[frozenset[str]] = frozenset(
    {"guided", "training", "rapid", "clinical"}
)
LEASE_MODES: Final[frozenset[str]] = frozenset({"training", "rapid", "clinical"})
LEASE_STATES: Final[frozenset[str]] = frozenset(
    {
        "active",
        "submitting",
        "submitted",
        "expired",
        "abandoned",
        "superseded",
        "quarantined",
    }
)
TERMINAL_LEASE_STATES: Final[frozenset[str]] = frozenset(
    {"submitted", "expired", "abandoned", "superseded", "quarantined"}
)
EXPOSURE_LEASE_STATES: Final[frozenset[str]] = frozenset(
    {"active", "submitting"}
)
EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "session_started",
        "item_presented",
        "interaction_committed",
        "answer_committed",
        "item_expired",
        "item_abandoned",
        "session_abandoned",
        "session_completed",
        "pathway_progressed",
        "answer_quarantined",
    }
)
EVIDENCE_LEVELS: Final[frozenset[str]] = frozenset(
    {"guided", "formative", "independent_transfer", "legacy_unverified"}
)
INTEGRITY_STATUSES: Final[frozenset[str]] = frozenset(
    {"atomic_v2", "backfilled_v1", "quarantined"}
)

_SCORABLE_EVENTS: Final[frozenset[str]] = frozenset(
    {"interaction_committed", "answer_committed"}
)
_TERMINAL_EVENT_STATE: Final[dict[str, str]] = {
    "item_expired": "expired",
    "item_abandoned": "abandoned",
    "session_abandoned": "abandoned",
    "answer_quarantined": "quarantined",
}
_SUBMISSION_KEY_DOMAIN: Final[bytes] = b"ecg-assessment-submission-key-v1\x00"
_TERMINAL_EVENT_DOMAIN: Final[bytes] = b"ecg-assessment-terminal-event-v1\x00"
_GUIDED_EXPOSURE_EVENT_DOMAIN: Final[bytes] = (
    b"ecg-guided-answer-bearing-exposure-v1\x00"
)
_GUIDED_INTERACTION_EVENT_DOMAIN: Final[bytes] = (
    b"ecg-guided-interaction-event-v2\x00"
)

# Answer-bearing ECGs remain unavailable to independent modes for one reviewed
# spacing interval.  This is deliberately finite: a tracing may become a valid
# reassessment after the learner has had time to forget the answer, but it must
# not be presented as unseen immediately after Guided feedback or a generic
# post-commit packet reveal.
ANSWER_BEARING_REASSESSMENT_INTERVAL: Final[timedelta] = timedelta(days=30)

# GETs can be replayed by React development behavior, browser retries, or a
# refresh. Collapse those deliveries without making an exposure permanently
# immutable: a later visit receives a new event and refreshes the rolling
# reassessment boundary.
GUIDED_EXPOSURE_IDEMPOTENCY_WINDOW: Final[timedelta] = timedelta(minutes=5)


class AssessmentLedgerError(RuntimeError):
    """Base error for a rejected ledger or lease operation."""


class LedgerValidationError(AssessmentLedgerError, ValueError):
    """Raised when a caller supplies data outside the reviewed contract."""


class LeaseNotFoundError(AssessmentLedgerError):
    """Raised for a missing lease or an owner mismatch, without disclosing which."""


class LeaseStateError(AssessmentLedgerError):
    """Raised when a transition is invalid for the current lease state."""


class LeaseExpiredError(LeaseStateError):
    """Raised when a submission claim loses the inclusive expiry boundary."""


class SubmissionKeyConflictError(LeaseStateError):
    """Raised when another submission reservation already owns the lease."""


class ActiveLeaseConflictError(LeaseStateError):
    """Raised when a session already has another active lease generation."""


class IdempotencyConflictError(AssessmentLedgerError):
    """Raised when an idempotency identifier is reused for different content."""


@dataclass(frozen=True, slots=True)
class LeaseMutation:
    lease_id: str
    state: str
    replayed: bool


@dataclass(frozen=True, slots=True)
class EventMutation:
    event_id: str
    replayed: bool


@dataclass(frozen=True, slots=True)
class ExpiredLease:
    """Safe projection returned so integration can append its terminal event."""

    lease_id: str
    owner_id: str
    mode: str
    session_id: str
    expired_at: str


@dataclass(frozen=True, slots=True)
class OwnerLedgerMutation:
    leases: int
    events: int
    competencies: int


@dataclass(frozen=True, slots=True)
class _LeaseSnapshot:
    lease_id: str
    owner_id: str
    mode: str
    session_id: str
    state: str
    integrity_status: str
    expires_at: str
    submission_key_hash: str | None
    created_at: str
    updated_at: str
    claimed_at: str | None
    terminal_at: str | None


_LEASE_SELECT: Final[str] = (
    "lease_id, owner_id, mode, session_id, state, integrity_status, expires_at, "
    "submission_key_hash, created_at, updated_at, claimed_at, terminal_at"
)


_SCHEMA_STATEMENTS: Final[tuple[str, ...]] = (
    """
    CREATE TABLE IF NOT EXISTS assessment_leases (
        lease_id TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL,
        mode TEXT NOT NULL CHECK (mode IN ('training', 'rapid', 'clinical')),
        session_id TEXT NOT NULL,
        state TEXT NOT NULL CHECK (
            state IN (
                'active', 'submitting', 'submitted', 'expired', 'abandoned',
                'superseded', 'quarantined'
            )
        ),
        integrity_status TEXT NOT NULL CHECK (
            integrity_status IN ('atomic_v2', 'backfilled_v1', 'quarantined')
        ),
        expires_at TEXT NOT NULL,
        submission_key_hash TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        claimed_at TEXT,
        terminal_at TEXT,
        UNIQUE (lease_id, owner_id, mode, session_id),
        CHECK (
            (state = 'active' AND submission_key_hash IS NULL
                AND claimed_at IS NULL AND terminal_at IS NULL)
            OR
            (state = 'submitting' AND submission_key_hash IS NOT NULL
                AND claimed_at IS NOT NULL AND terminal_at IS NULL)
            OR
            (state = 'submitted' AND submission_key_hash IS NOT NULL
                AND claimed_at IS NOT NULL AND terminal_at IS NOT NULL)
            OR
            (state IN ('expired', 'abandoned', 'superseded', 'quarantined')
                AND terminal_at IS NOT NULL)
        )
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_assessment_lease_active_session
    ON assessment_leases(owner_id, mode, session_id)
    WHERE state IN ('active', 'submitting')
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_assessment_lease_due
    ON assessment_leases(state, expires_at, lease_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_assessment_lease_owner_state
    ON assessment_leases(owner_id, state, mode, lease_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS assessment_lease_cases (
        lease_id TEXT NOT NULL,
        ecg_id TEXT NOT NULL,
        ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
        PRIMARY KEY (lease_id, ecg_id),
        UNIQUE (lease_id, ordinal),
        FOREIGN KEY (lease_id) REFERENCES assessment_leases(lease_id)
            ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_assessment_lease_case_exposure
    ON assessment_lease_cases(ecg_id, lease_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS learner_events (
        event_id TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL,
        mode TEXT NOT NULL CHECK (
            mode IN ('guided', 'training', 'rapid', 'clinical')
        ),
        session_id TEXT NOT NULL,
        lease_id TEXT,
        ecg_id TEXT,
        event_type TEXT NOT NULL CHECK (
            event_type IN (
                'session_started', 'item_presented', 'interaction_committed',
                'answer_committed', 'item_expired', 'session_abandoned',
                'item_abandoned', 'session_completed', 'pathway_progressed',
                'answer_quarantined'
            )
        ),
        evidence_level TEXT NOT NULL CHECK (
            evidence_level IN (
                'guided', 'formative', 'independent_transfer',
                'legacy_unverified'
            )
        ),
        integrity_status TEXT NOT NULL CHECK (
            integrity_status IN ('atomic_v2', 'backfilled_v1', 'quarantined')
        ),
        score REAL,
        occurred_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (lease_id, owner_id, mode, session_id)
            REFERENCES assessment_leases(lease_id, owner_id, mode, session_id)
            ON UPDATE CASCADE,
        CHECK (score IS NULL OR (score >= 0.0 AND score <= 1.0)),
        CHECK (
            event_type IN ('interaction_committed', 'answer_committed')
            OR score IS NULL
        ),
        CHECK (event_type <> 'answer_committed' OR score IS NOT NULL)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_learner_event_owner_time
    ON learner_events(owner_id, occurred_at, event_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_learner_event_session
    ON learner_events(owner_id, mode, session_id, occurred_at, event_id)
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_learner_event_lease_type
    ON learner_events(lease_id, event_type)
    WHERE lease_id IS NOT NULL
      AND event_type IN (
          'item_expired', 'item_abandoned', 'answer_quarantined'
      )
    """,
    """
    CREATE TABLE IF NOT EXISTS learner_event_competencies (
        event_id TEXT NOT NULL,
        competency_id TEXT NOT NULL,
        competency_score REAL NOT NULL CHECK (
            competency_score >= 0.0 AND competency_score <= 1.0
        ),
        PRIMARY KEY (event_id, competency_id),
        FOREIGN KEY (event_id) REFERENCES learner_events(event_id)
            ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_learner_event_competency
    ON learner_event_competencies(competency_id, event_id)
    """,
    "DROP TRIGGER IF EXISTS assessment_lease_terminal_state_immutable",
    """
    CREATE TRIGGER assessment_lease_terminal_state_immutable
    BEFORE UPDATE ON assessment_leases
    WHEN OLD.state IN (
        'submitted', 'expired', 'abandoned', 'superseded', 'quarantined'
    ) AND (
        NEW.lease_id IS NOT OLD.lease_id
        OR NEW.mode IS NOT OLD.mode
        OR NEW.session_id IS NOT OLD.session_id
        OR NEW.state IS NOT OLD.state
        OR NEW.integrity_status IS NOT OLD.integrity_status
        OR NEW.expires_at IS NOT OLD.expires_at
        OR NEW.submission_key_hash IS NOT OLD.submission_key_hash
        OR NEW.created_at IS NOT OLD.created_at
        OR NEW.updated_at IS NOT OLD.updated_at
        OR NEW.claimed_at IS NOT OLD.claimed_at
        OR NEW.terminal_at IS NOT OLD.terminal_at
    )
    BEGIN
        SELECT RAISE(ABORT, 'assessment lease terminal state is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS learner_event_competency_requires_scored_event
    BEFORE INSERT ON learner_event_competencies
    WHEN NOT EXISTS (
        SELECT 1 FROM learner_events
        WHERE event_id = NEW.event_id
          AND event_type IN ('interaction_committed', 'answer_committed')
          AND score IS NOT NULL
    )
    BEGIN
        SELECT RAISE(ABORT, 'competency evidence requires a scored event');
    END
    """,
)


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the four additive tables without taking over the transaction.

    ``sqlite3.Connection.executescript`` is intentionally avoided because it
    may commit a caller's pending transaction.  If schema installation must be
    atomic, the caller should begin a transaction before invoking this helper.
    """

    for statement in _SCHEMA_STATEMENTS:
        conn.execute(statement)


def create_lease(
    conn: sqlite3.Connection,
    *,
    lease_id: str,
    owner_id: str,
    mode: str,
    session_id: str,
    ecg_ids: Sequence[str],
    expires_at: str | datetime,
    created_at: str | datetime,
    integrity_status: str = "atomic_v2",
) -> LeaseMutation:
    """Create one immutable exposure generation, or replay the same creation."""

    lease_id = _identifier(lease_id, "lease_id")
    owner_id = _identifier(owner_id, "owner_id")
    session_id = _identifier(session_id, "session_id")
    mode = _allow(mode, LEASE_MODES, "lease mode")
    integrity_status = _allow(
        integrity_status, INTEGRITY_STATUSES, "integrity status"
    )
    created = _utc_iso(created_at, "created_at")
    expires = _utc_iso(expires_at, "expires_at")
    if expires <= created:
        raise LedgerValidationError("expires_at must be later than created_at")
    protected = _ecg_sequence(ecg_ids)

    existing = _load_lease(conn, lease_id)
    if existing is not None:
        existing_cases = _lease_ecgs(conn, lease_id)
        identity = (
            existing.owner_id,
            existing.mode,
            existing.session_id,
            existing.integrity_status,
            existing.expires_at,
            existing.created_at,
            existing_cases,
        )
        requested = (
            owner_id,
            mode,
            session_id,
            integrity_status,
            expires,
            created,
            protected,
        )
        if identity != requested:
            raise IdempotencyConflictError(
                "lease_id was already used for a different lease generation"
            )
        return LeaseMutation(lease_id, existing.state, True)

    active = conn.execute(
        "SELECT lease_id FROM assessment_leases "
        "WHERE owner_id = ? AND mode = ? AND session_id = ? "
        "AND state IN ('active', 'submitting') LIMIT 1",
        (owner_id, mode, session_id),
    ).fetchone()
    if active is not None:
        raise ActiveLeaseConflictError(
            "session already has an active assessment lease generation"
        )

    conn.execute(
        "INSERT INTO assessment_leases "
        "(lease_id, owner_id, mode, session_id, state, integrity_status, "
        "expires_at, submission_key_hash, created_at, updated_at, claimed_at, "
        "terminal_at) VALUES (?, ?, ?, ?, 'active', ?, ?, NULL, ?, ?, NULL, NULL)",
        (
            lease_id,
            owner_id,
            mode,
            session_id,
            integrity_status,
            expires,
            created,
            created,
        ),
    )
    conn.executemany(
        "INSERT INTO assessment_lease_cases (lease_id, ecg_id, ordinal) "
        "VALUES (?, ?, ?)",
        ((lease_id, ecg_id, ordinal) for ordinal, ecg_id in enumerate(protected)),
    )
    return LeaseMutation(lease_id, "active", False)


def claim_submission(
    conn: sqlite3.Connection,
    *,
    lease_id: str,
    owner_id: str,
    submission_key: str,
    claimed_at: str | datetime,
) -> LeaseMutation:
    """Reserve an active lease for one exact submission generation.

    Expiry is inclusive: a claim at exactly ``expires_at`` loses.  A claim that
    wins before the boundary moves to ``submitting`` and is no longer eligible
    for the expiry sweep, so grading can finish without a timeout race.
    """

    lease = _owned_lease(conn, lease_id, owner_id)
    at = _utc_iso(claimed_at, "claimed_at")
    key_hash = _submission_hash(submission_key)

    if lease.state in {"submitting", "submitted"}:
        if lease.submission_key_hash != key_hash:
            raise SubmissionKeyConflictError(
                "assessment lease is reserved by another submission key"
            )
        return LeaseMutation(lease.lease_id, lease.state, True)
    if lease.state != "active":
        raise LeaseStateError(f"cannot claim a lease in {lease.state!r} state")
    if lease.expires_at <= at:
        raise LeaseExpiredError("assessment lease is due for inclusive expiry")

    updated = conn.execute(
        "UPDATE assessment_leases SET state = 'submitting', "
        "submission_key_hash = ?, claimed_at = ?, updated_at = ? "
        "WHERE lease_id = ? AND owner_id = ? AND state = 'active' "
        "AND expires_at > ?",
        (key_hash, at, at, lease.lease_id, lease.owner_id, at),
    )
    if updated.rowcount != 1:
        raise LeaseStateError("assessment lease changed before it could be claimed")
    return LeaseMutation(lease.lease_id, "submitting", False)


def release_submission(
    conn: sqlite3.Connection,
    *,
    lease_id: str,
    owner_id: str,
    submission_key: str,
    released_at: str | datetime,
) -> LeaseMutation:
    """Release the exact in-flight reservation after a grading failure."""

    lease = _owned_lease(conn, lease_id, owner_id)
    at = _utc_iso(released_at, "released_at")
    key_hash = _submission_hash(submission_key)
    if lease.state != "submitting":
        raise LeaseStateError(f"cannot release a lease in {lease.state!r} state")
    if lease.submission_key_hash != key_hash:
        raise SubmissionKeyConflictError(
            "submission key does not own this assessment reservation"
        )
    updated = conn.execute(
        "UPDATE assessment_leases SET state = 'active', "
        "submission_key_hash = NULL, claimed_at = NULL, updated_at = ? "
        "WHERE lease_id = ? AND owner_id = ? AND state = 'submitting' "
        "AND submission_key_hash = ?",
        (at, lease.lease_id, lease.owner_id, key_hash),
    )
    if updated.rowcount != 1:
        raise LeaseStateError("assessment reservation changed before release")
    return LeaseMutation(lease.lease_id, "active", False)


def mark_submitted(
    conn: sqlite3.Connection,
    *,
    lease_id: str,
    owner_id: str,
    submission_key: str,
    submitted_at: str | datetime,
) -> LeaseMutation:
    """Make a claimed submission terminal, with same-key replay semantics."""

    lease = _owned_lease(conn, lease_id, owner_id)
    at = _utc_iso(submitted_at, "submitted_at")
    key_hash = _submission_hash(submission_key)
    if lease.state == "submitted":
        if lease.submission_key_hash != key_hash:
            raise SubmissionKeyConflictError(
                "submitted assessment belongs to another submission key"
            )
        return LeaseMutation(lease.lease_id, "submitted", True)
    if lease.state != "submitting":
        raise LeaseStateError(f"cannot submit a lease in {lease.state!r} state")
    if lease.submission_key_hash != key_hash:
        raise SubmissionKeyConflictError(
            "submission key does not own this assessment reservation"
        )
    updated = conn.execute(
        "UPDATE assessment_leases SET state = 'submitted', terminal_at = ?, "
        "updated_at = ? WHERE lease_id = ? AND owner_id = ? "
        "AND state = 'submitting' AND submission_key_hash = ?",
        (at, at, lease.lease_id, lease.owner_id, key_hash),
    )
    if updated.rowcount != 1:
        raise LeaseStateError("assessment reservation changed before submission")
    return LeaseMutation(lease.lease_id, "submitted", False)


def terminalize_lease(
    conn: sqlite3.Connection,
    *,
    lease_id: str,
    owner_id: str,
    terminal_state: str,
    terminal_at: str | datetime,
) -> LeaseMutation:
    """End a nonterminal lease without creating score or mastery evidence."""

    terminal_state = _allow(
        terminal_state,
        frozenset({"expired", "abandoned", "superseded", "quarantined"}),
        "terminal state",
    )
    lease = _owned_lease(conn, lease_id, owner_id)
    at = _utc_iso(terminal_at, "terminal_at")
    if lease.state in TERMINAL_LEASE_STATES:
        if lease.state == terminal_state:
            return LeaseMutation(lease.lease_id, lease.state, True)
        raise LeaseStateError(
            f"terminal lease state {lease.state!r} is immutable"
        )
    if terminal_state == "expired":
        if lease.state != "active":
            raise LeaseStateError("a claimed submission cannot lose to expiry")
        if lease.expires_at > at:
            raise LeaseStateError("assessment lease is not due for expiry")

    updated = conn.execute(
        "UPDATE assessment_leases SET state = ?, terminal_at = ?, updated_at = ? "
        "WHERE lease_id = ? AND owner_id = ? AND state IN ('active', 'submitting')",
        (terminal_state, at, at, lease.lease_id, lease.owner_id),
    )
    if updated.rowcount != 1:
        raise LeaseStateError("assessment lease changed before terminalization")
    return LeaseMutation(lease.lease_id, terminal_state, False)


def expire_due_leases(
    conn: sqlite3.Connection,
    *,
    expired_at: str | datetime,
) -> tuple[ExpiredLease, ...]:
    """Expire every unclaimed lease with ``expires_at <= expired_at``.

    The safe projections let the caller append exactly one ``item_expired``
    event per returned lease before committing the same transaction.  Claimed
    ``submitting`` rows are excluded because their reservation won the race.
    """

    at = _utc_iso(expired_at, "expired_at")
    rows = conn.execute(
        "SELECT lease_id, owner_id, mode, session_id FROM assessment_leases "
        "WHERE state = 'active' AND expires_at <= ? ORDER BY lease_id",
        (at,),
    ).fetchall()
    if not rows:
        return ()
    conn.execute(
        "UPDATE assessment_leases SET state = 'expired', terminal_at = ?, "
        "updated_at = ? WHERE state = 'active' AND expires_at <= ?",
        (at, at, at),
    )
    return tuple(
        ExpiredLease(str(row[0]), str(row[1]), str(row[2]), str(row[3]), at)
        for row in rows
    )


def append_event(
    conn: sqlite3.Connection,
    *,
    event_id: str,
    owner_id: str,
    mode: str,
    session_id: str,
    event_type: str,
    evidence_level: str,
    integrity_status: str,
    occurred_at: str | datetime,
    lease_id: str | None = None,
    ecg_id: str | None = None,
    score: float | None = None,
    competencies: Mapping[str, float] | Iterable[tuple[str, float]] = (),
    submission_key: str | None = None,
) -> EventMutation:
    """Append an answer-free event and normalized competency rows once.

    ``event_id`` is the idempotency identity.  Reusing it with byte-for-byte
    equivalent semantic fields replays safely; any different field or
    competency set is rejected.  This helper never updates a mastery table.
    """

    event_id = _identifier(event_id, "event_id")
    owner_id = _identifier(owner_id, "owner_id")
    session_id = _identifier(session_id, "session_id")
    mode = _allow(mode, ALLOWED_MODES, "mode")
    event_type = _allow(event_type, EVENT_TYPES, "event type")
    evidence_level = _allow(evidence_level, EVIDENCE_LEVELS, "evidence level")
    integrity_status = _allow(
        integrity_status, INTEGRITY_STATUSES, "integrity status"
    )
    occurred = _utc_iso(occurred_at, "occurred_at")
    lease_id = _optional_identifier(lease_id, "lease_id")
    ecg_id = _optional_identifier(ecg_id, "ecg_id")
    normalized_score = _score(score, "score")
    competency_rows = _competencies(competencies)
    _validate_event_evidence(event_type, normalized_score, competency_rows)

    requested = (
        owner_id,
        mode,
        session_id,
        lease_id,
        ecg_id,
        event_type,
        evidence_level,
        integrity_status,
        normalized_score,
        occurred,
    )
    existing = conn.execute(
        "SELECT owner_id, mode, session_id, lease_id, ecg_id, event_type, "
        "evidence_level, integrity_status, score, occurred_at "
        "FROM learner_events WHERE event_id = ?",
        (event_id,),
    ).fetchone()
    if existing is not None:
        existing_values = tuple(existing)
        existing_competencies = tuple(
            (str(row[0]), float(row[1]))
            for row in conn.execute(
                "SELECT competency_id, competency_score "
                "FROM learner_event_competencies WHERE event_id = ? "
                "ORDER BY competency_id",
                (event_id,),
            ).fetchall()
        )
        if existing_values != requested or existing_competencies != competency_rows:
            raise IdempotencyConflictError(
                "event_id was already used for different learner evidence"
            )
        # The ledger does not persist raw submission keys, but a replay of a
        # committed answer must still prove ownership of the same reservation.
        if event_type == "answer_committed" and lease_id is not None:
            replay_lease = _owned_lease(conn, lease_id, owner_id)
            _validate_event_lease_state(
                replay_lease,
                event_type=event_type,
                submission_key=submission_key,
            )
        elif submission_key is not None:
            raise LedgerValidationError(
                "submission_key is only accepted for answer_committed events"
            )
        return EventMutation(event_id, True)

    lease: _LeaseSnapshot | None = None
    if lease_id is not None:
        lease = _owned_lease(conn, lease_id, owner_id)
        if (lease.mode, lease.session_id) != (mode, session_id):
            raise LeaseNotFoundError("assessment lease was not found for this owner")
        if ecg_id is not None and ecg_id not in _lease_ecgs(conn, lease_id):
            raise LedgerValidationError(
                "event ECG is not protected by the assessment lease"
            )
        _validate_event_lease_state(
            lease, event_type=event_type, submission_key=submission_key
        )
    elif submission_key is not None:
        raise LedgerValidationError("submission_key requires an assessment lease")
    elif event_type in {
        "item_presented",
        "answer_committed",
        "item_expired",
        "item_abandoned",
        "answer_quarantined",
    } and mode in LEASE_MODES:
        raise LedgerValidationError(
            f"{event_type} requires a lease in assessment mode {mode}"
        )

    conn.execute(
        "INSERT INTO learner_events "
        "(event_id, owner_id, mode, session_id, lease_id, ecg_id, event_type, "
        "evidence_level, integrity_status, score, occurred_at, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            event_id,
            owner_id,
            mode,
            session_id,
            lease_id,
            ecg_id,
            event_type,
            evidence_level,
            integrity_status,
            normalized_score,
            occurred,
            occurred,
        ),
    )
    if competency_rows:
        conn.executemany(
            "INSERT INTO learner_event_competencies "
            "(event_id, competency_id, competency_score) VALUES (?, ?, ?)",
            (
                (event_id, competency_id, competency_score)
                for competency_id, competency_score in competency_rows
            ),
        )
    return EventMutation(event_id, False)


def record_guided_packet_exposure(
    conn: sqlite3.Connection,
    *,
    owner_id: str,
    lesson_id: str,
    ecg_id: str,
    occurred_at: str | datetime,
) -> EventMutation:
    """Record delivery of one answer-bearing Guided packet without its answer.

    A deterministic five-minute generation makes ordinary GET retries
    idempotent. Unlike ``append_event`` replay, the retry intentionally keeps
    the first server timestamp: every later generation records a new actual
    presentation and therefore refreshes the rolling reassessment boundary.
    The caller should serialize this check-and-insert in its write transaction.
    """

    owner = _identifier(owner_id, "owner_id")
    lesson = _identifier(lesson_id, "lesson_id")
    ecg = _identifier(ecg_id, "ecg_id")
    occurred = _utc_iso(occurred_at, "occurred_at")
    parsed = datetime.fromisoformat(occurred)
    window_seconds = int(GUIDED_EXPOSURE_IDEMPOTENCY_WINDOW.total_seconds())
    generation = int(parsed.timestamp()) // window_seconds
    session_id = f"tutorial:{lesson}"
    identity = "\x00".join((owner, session_id, ecg, str(generation)))
    digest = hashlib.sha256(
        _GUIDED_EXPOSURE_EVENT_DOMAIN + identity.encode("utf-8")
    ).hexdigest()
    event_id = f"guided-exposure:{digest}"

    existing = conn.execute(
        "SELECT owner_id, mode, session_id, ecg_id, event_type, "
        "evidence_level, integrity_status, score "
        "FROM learner_events WHERE event_id = ?",
        (event_id,),
    ).fetchone()
    expected = (
        owner,
        "guided",
        session_id,
        ecg,
        "item_presented",
        "guided",
        "atomic_v2",
        None,
    )
    if existing is not None:
        if tuple(existing) != expected:
            raise IdempotencyConflictError(
                "guided exposure generation was already used for different content"
            )
        return EventMutation(event_id, True)

    return append_event(
        conn,
        event_id=event_id,
        owner_id=owner,
        mode="guided",
        session_id=session_id,
        ecg_id=ecg,
        event_type="item_presented",
        evidence_level="guided",
        integrity_status="atomic_v2",
        occurred_at=occurred,
    )


def guided_interaction_event_id(owner_id: str, event_key: str) -> str:
    """Return a globally unique, owner-scoped Guided audit identity.

    Browser event keys are intentionally deterministic so one owner's network
    retry replays. They are not globally unique: every learner can complete the
    same authored action. Binding the normalized ledger id to both values keeps
    that per-owner idempotency contract without exposing the owner in the id.
    """

    owner = _identifier(owner_id, "owner_id")
    # The public contract caps explicit keys at 160 characters; the legacy
    # deterministic fallback is a 64-character digest. Keeping that bound lets
    # the raw action key remain visible in the audit id without exceeding the
    # ledger's 255-character identifier contract.
    key = _identifier(event_key, "event_key", maximum=160)
    digest = hashlib.sha256(
        _GUIDED_INTERACTION_EVENT_DOMAIN
        + owner.encode("utf-8")
        + b"\x00"
        + key.encode("utf-8")
    ).hexdigest()
    return f"guided:v2:{digest}:{key}"


def owner_exposure_ids(
    conn: sqlite3.Connection,
    *,
    owner_id: str,
    states: Iterable[str] = EXPOSURE_LEASE_STATES,
    as_of: str | datetime | None = None,
    reassessment_interval: timedelta = ANSWER_BEARING_REASSESSMENT_INTERVAL,
    ignore_presentation_scope: tuple[str, str, str] | None = None,
) -> tuple[str, ...]:
    """Return ECG ids protected from independent reuse for one owner.

    An active lease stops excluding its ECG at the inclusive expiry boundary,
    even if that mode has not revisited the session to write its terminal event
    yet. A claimed/submitting lease remains protected because grading is
    genuinely in flight and must retain its frozen exposure through commit or
    rollback. Recent answer-bearing presentations remain protected for the
    finite reassessment interval, including pre-ledger Guided and generic
    attempt history. Only ECG identifiers cross this boundary; answer contracts
    and learner responses are never projected. ``ignore_presentation_scope`` is a
    narrow renewal seam for an already-frozen item whose expired lease is being
    rotated in the same mode/session. It ignores only that session and ECG's
    normalized ``item_presented`` events; scored interactions, live leases, and
    legacy answer-bearing histories remain protected.
    """

    owner_id = _identifier(owner_id, "owner_id")
    selected_states = tuple(
        sorted({_allow(state, LEASE_STATES, "lease state") for state in states})
    )
    if not isinstance(reassessment_interval, timedelta):
        raise LedgerValidationError("reassessment_interval must be a timedelta")
    interval_seconds = reassessment_interval.total_seconds()
    if not math.isfinite(interval_seconds) or interval_seconds <= 0:
        raise LedgerValidationError("reassessment_interval must be positive")
    if not selected_states:
        return ()
    at = _utc_iso(as_of or datetime.now(UTC), "as_of")
    cutoff = (
        datetime.fromisoformat(at) - reassessment_interval
    ).isoformat(timespec="microseconds")
    placeholders = ", ".join("?" for _ in selected_states)
    rows = conn.execute(
        "SELECT DISTINCT cases.ecg_id FROM assessment_lease_cases AS cases "
        "JOIN assessment_leases AS leases ON leases.lease_id = cases.lease_id "
        f"WHERE leases.owner_id = ? AND leases.state IN ({placeholders}) "
        "AND (leases.state <> 'active' OR leases.expires_at > ?) "
        "ORDER BY cases.ecg_id",
        (owner_id, *selected_states, at),
    ).fetchall()
    protected = {str(row[0]) for row in rows}

    # The normalized timeline covers every current mode, including Guided
    # packet delivery. Terminal assessment presentations still count: seeing a
    # waveform is enough to contaminate an immediate "unseen" assessment even
    # when the learner never submitted an answer.
    event_scope_sql = ""
    event_scope_params: tuple[str, ...] = ()
    if ignore_presentation_scope is not None:
        ignored_mode = _allow(
            ignore_presentation_scope[0], ALLOWED_MODES, "ignored presentation mode"
        )
        ignored_session = _identifier(
            ignore_presentation_scope[1], "ignored presentation session_id"
        )
        ignored_ecg = _identifier(
            ignore_presentation_scope[2], "ignored presentation ecg_id"
        )
        event_scope_sql = (
            "AND NOT (mode = ? AND session_id = ? AND ecg_id = ? "
            "AND event_type = 'item_presented') "
        )
        event_scope_params = (ignored_mode, ignored_session, ignored_ecg)
    event_rows = conn.execute(
        "SELECT DISTINCT ecg_id FROM learner_events "
        "WHERE owner_id = ? AND ecg_id IS NOT NULL "
        "AND event_type IN ('item_presented', 'interaction_committed', "
        f"'answer_committed') {event_scope_sql}"
        "AND occurred_at > ? AND occurred_at <= ?",
        (owner_id, *event_scope_params, cutoff, at),
    ).fetchall()
    protected.update(str(row[0]) for row in event_rows)

    # Older installations already have durable answer-bearing history in these
    # two stores. Query them when present so deployment of this policy does not
    # misclassify a previously revealed ECG as unseen. Fixed table names and
    # indexed owner/time predicates keep this migration-safe and bounded.
    tables = {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name IN ('guided_learning_events', 'attempts')"
        ).fetchall()
    }
    if "guided_learning_events" in tables:
        guided_rows = conn.execute(
            "SELECT DISTINCT case_id FROM guided_learning_events "
            "WHERE learner_id = ? AND case_id IS NOT NULL AND case_id <> '' "
            "AND created_at > ? AND created_at <= ?",
            (owner_id, cutoff, at),
        ).fetchall()
        protected.update(str(row[0]) for row in guided_rows)
    if "attempts" in tables:
        attempt_rows = conn.execute(
            "SELECT DISTINCT case_id FROM attempts "
            "WHERE learner_id = ? AND case_id IS NOT NULL AND case_id <> '' "
            "AND created_at > ? AND created_at <= ?",
            (owner_id, cutoff, at),
        ).fetchall()
        protected.update(str(row[0]) for row in attempt_rows)
    return tuple(sorted(protected))


def reassign_owner(
    conn: sqlite3.Connection,
    *,
    source_owner_id: str,
    destination_owner_id: str,
) -> OwnerLedgerMutation:
    """Atomically re-key all normalized assessment rows during account claim.

    The composite learner-event foreign key makes a parent/child owner change
    impossible as two independently checked statements. SQLite's transaction-
    scoped deferred-FK switch keeps both updates in the caller's one commit.
    This helper still owns no transaction lifecycle.
    """

    source = _identifier(source_owner_id, "source_owner_id")
    destination = _identifier(destination_owner_id, "destination_owner_id")
    if source == destination:
        return OwnerLedgerMutation(0, 0, 0)
    conflict = conn.execute(
        "SELECT 1 FROM assessment_leases AS source "
        "JOIN assessment_leases AS destination "
        "ON destination.owner_id = ? AND destination.mode = source.mode "
        "AND destination.session_id = source.session_id "
        "AND destination.state IN ('active', 'submitting') "
        "WHERE source.owner_id = ? "
        "AND source.state IN ('active', 'submitting') LIMIT 1",
        (destination, source),
    ).fetchone()
    if conflict is not None:
        raise ActiveLeaseConflictError(
            "destination owner already has a live generation for this session"
        )
    competency_count = int(
        conn.execute(
            "SELECT COUNT(*) FROM learner_event_competencies AS competencies "
            "JOIN learner_events AS events ON events.event_id = competencies.event_id "
            "WHERE events.owner_id = ?",
            (source,),
        ).fetchone()[0]
    )
    event_count = int(
        conn.execute(
            "SELECT COUNT(*) FROM learner_events WHERE owner_id = ?", (source,)
        ).fetchone()[0]
    )
    # This pragma lasts only for the surrounding transaction and is reset by
    # SQLite at commit/rollback. It does not weaken the eventual FK check.
    conn.execute("PRAGMA defer_foreign_keys = ON")
    leases = conn.execute(
        "UPDATE assessment_leases SET owner_id = ? WHERE owner_id = ?",
        (destination, source),
    ).rowcount
    # Lease-linked events follow through ON UPDATE CASCADE. This second update
    # covers unleased Guided/pathway events in the same normalized table.
    conn.execute(
        "UPDATE learner_events SET owner_id = ? WHERE owner_id = ?",
        (destination, source),
    )
    return OwnerLedgerMutation(int(leases), event_count, competency_count)


def delete_owner_records(
    conn: sqlite3.Connection,
    *,
    owner_id: str,
) -> OwnerLedgerMutation:
    """Delete one owner's normalized ledger rows in foreign-key-safe order."""

    owner = _identifier(owner_id, "owner_id")
    lease_count = int(
        conn.execute(
            "SELECT COUNT(*) FROM assessment_leases WHERE owner_id = ?", (owner,)
        ).fetchone()[0]
    )
    event_count = int(
        conn.execute(
            "SELECT COUNT(*) FROM learner_events WHERE owner_id = ?", (owner,)
        ).fetchone()[0]
    )
    competency_count = int(
        conn.execute(
            "SELECT COUNT(*) FROM learner_event_competencies AS competencies "
            "JOIN learner_events AS events ON events.event_id = competencies.event_id "
            "WHERE events.owner_id = ?",
            (owner,),
        ).fetchone()[0]
    )
    conn.execute(
        "DELETE FROM learner_event_competencies WHERE event_id IN "
        "(SELECT event_id FROM learner_events WHERE owner_id = ?)",
        (owner,),
    )
    conn.execute("DELETE FROM learner_events WHERE owner_id = ?", (owner,))
    conn.execute(
        "DELETE FROM assessment_lease_cases WHERE lease_id IN "
        "(SELECT lease_id FROM assessment_leases WHERE owner_id = ?)",
        (owner,),
    )
    conn.execute("DELETE FROM assessment_leases WHERE owner_id = ?", (owner,))
    return OwnerLedgerMutation(lease_count, event_count, competency_count)


def terminal_event_id(lease_id: str, terminal_state: str) -> str:
    """Return a stable id for an integration-layer lease terminal event."""

    lease_id = _identifier(lease_id, "lease_id")
    terminal_state = _allow(
        terminal_state,
        frozenset({"expired", "abandoned", "quarantined"}),
        "terminal event state",
    )
    digest = hashlib.sha256(
        _TERMINAL_EVENT_DOMAIN
        + lease_id.encode("utf-8")
        + b"\x00"
        + terminal_state.encode("ascii")
    ).hexdigest()
    return f"lease-terminal-{digest}"


def _load_lease(conn: sqlite3.Connection, lease_id: str) -> _LeaseSnapshot | None:
    row = conn.execute(
        f"SELECT {_LEASE_SELECT} FROM assessment_leases WHERE lease_id = ?",
        (lease_id,),
    ).fetchone()
    return _LeaseSnapshot(*tuple(row)) if row is not None else None


def _owned_lease(
    conn: sqlite3.Connection, lease_id: str, owner_id: str
) -> _LeaseSnapshot:
    lease_id = _identifier(lease_id, "lease_id")
    owner_id = _identifier(owner_id, "owner_id")
    lease = _load_lease(conn, lease_id)
    if lease is None or lease.owner_id != owner_id:
        raise LeaseNotFoundError("assessment lease was not found for this owner")
    return lease


def _lease_ecgs(conn: sqlite3.Connection, lease_id: str) -> tuple[str, ...]:
    return tuple(
        str(row[0])
        for row in conn.execute(
            "SELECT ecg_id FROM assessment_lease_cases "
            "WHERE lease_id = ? ORDER BY ordinal",
            (lease_id,),
        ).fetchall()
    )


def _validate_event_lease_state(
    lease: _LeaseSnapshot,
    *,
    event_type: str,
    submission_key: str | None,
) -> None:
    expected_terminal = _TERMINAL_EVENT_STATE.get(event_type)
    if expected_terminal is not None and lease.state != expected_terminal:
        raise LeaseStateError(
            f"{event_type} requires lease state {expected_terminal!r}"
        )
    if event_type == "item_presented" and lease.state != "active":
        raise LeaseStateError("item presentation requires an active lease")
    if event_type == "answer_committed":
        if lease.state not in {"submitting", "submitted"}:
            raise LeaseStateError("answer commit requires a claimed lease")
        if submission_key is None:
            raise LedgerValidationError(
                "answer commit requires the owning submission_key"
            )
        if lease.submission_key_hash != _submission_hash(submission_key):
            raise SubmissionKeyConflictError(
                "submission key does not own this assessment reservation"
            )
    elif submission_key is not None:
        raise LedgerValidationError(
            "submission_key is only accepted for answer_committed events"
        )


def _validate_event_evidence(
    event_type: str,
    score: float | None,
    competencies: tuple[tuple[str, float], ...],
) -> None:
    if event_type not in _SCORABLE_EVENTS and score is not None:
        raise LedgerValidationError(
            f"{event_type} is unscored and cannot carry a score"
        )
    if event_type == "answer_committed" and score is None:
        raise LedgerValidationError("answer_committed requires a score")
    if competencies and (event_type not in _SCORABLE_EVENTS or score is None):
        raise LedgerValidationError(
            "competency evidence requires a scored committed interaction"
        )


def _competencies(
    values: Mapping[str, float] | Iterable[tuple[str, float]],
) -> tuple[tuple[str, float], ...]:
    entries = values.items() if isinstance(values, Mapping) else values
    normalized: dict[str, float] = {}
    for raw_id, raw_score in entries:
        competency_id = _identifier(raw_id, "competency_id")
        competency_score = _score(raw_score, "competency score")
        if competency_score is None:
            raise LedgerValidationError("competency score cannot be null")
        prior = normalized.get(competency_id)
        if prior is not None and prior != competency_score:
            raise LedgerValidationError(
                f"competency {competency_id!r} has conflicting scores"
            )
        normalized[competency_id] = competency_score
    return tuple(sorted(normalized.items()))


def _ecg_sequence(values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise LedgerValidationError("ecg_ids must be a sequence of identifiers")
    normalized = tuple(_identifier(value, "ecg_id") for value in values)
    if not normalized:
        raise LedgerValidationError("an assessment lease must protect at least one ECG")
    if len(set(normalized)) != len(normalized):
        raise LedgerValidationError("an assessment lease cannot repeat an ECG")
    return normalized


def _submission_hash(value: str) -> str:
    key = _identifier(value, "submission_key", maximum=512)
    return hashlib.sha256(_SUBMISSION_KEY_DOMAIN + key.encode("utf-8")).hexdigest()


def _score(value: float | None, label: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LedgerValidationError(f"{label} must be a number between 0 and 1")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0.0 <= normalized <= 1.0:
        raise LedgerValidationError(f"{label} must be a number between 0 and 1")
    return normalized


def _utc_iso(value: str | datetime, label: str) -> str:
    if isinstance(value, str):
        candidate = value.strip()
        if candidate.endswith("Z"):
            candidate = f"{candidate[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError as exc:
            raise LedgerValidationError(f"{label} must be an ISO timestamp") from exc
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise LedgerValidationError(f"{label} must be an ISO timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LedgerValidationError(f"{label} must include a UTC offset")
    return parsed.astimezone(UTC).isoformat(timespec="microseconds")


def _allow(value: str, allowed: frozenset[str], label: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        choices = ", ".join(sorted(allowed))
        raise LedgerValidationError(f"{label} must be one of: {choices}")
    return value


def _identifier(value: str, label: str, maximum: int = 255) -> str:
    if not isinstance(value, str):
        raise LedgerValidationError(f"{label} must be a string")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise LedgerValidationError(
            f"{label} must contain between 1 and {maximum} characters"
        )
    if any(ord(char) < 32 for char in normalized):
        raise LedgerValidationError(f"{label} cannot contain control characters")
    return normalized


def _optional_identifier(value: str | None, label: str) -> str | None:
    return None if value is None else _identifier(value, label)
