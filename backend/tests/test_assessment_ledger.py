from __future__ import annotations

from datetime import UTC, datetime, timedelta
import sqlite3

import pytest

from app.assessment_ledger import (
    ActiveLeaseConflictError,
    IdempotencyConflictError,
    LedgerValidationError,
    LeaseExpiredError,
    LeaseNotFoundError,
    LeaseStateError,
    SubmissionKeyConflictError,
    append_event,
    claim_submission,
    create_lease,
    delete_owner_records,
    ensure_schema,
    expire_due_leases,
    mark_submitted,
    owner_exposure_ids,
    record_guided_packet_exposure,
    reassign_owner,
    release_submission,
    terminal_event_id,
    terminalize_lease,
)


BASE = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


@pytest.fixture()
def conn() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys=ON")
    ensure_schema(connection)
    connection.commit()
    try:
        yield connection
    finally:
        connection.close()


def _lease(
    conn: sqlite3.Connection,
    *,
    lease_id: str = "lease-1",
    owner_id: str = "owner-a",
    mode: str = "rapid",
    session_id: str = "session-1",
    ecg_ids: tuple[str, ...] = ("ecg-1",),
    created_at: datetime = BASE,
    expires_at: datetime = BASE + timedelta(minutes=1),
):
    return create_lease(
        conn,
        lease_id=lease_id,
        owner_id=owner_id,
        mode=mode,
        session_id=session_id,
        ecg_ids=ecg_ids,
        created_at=created_at,
        expires_at=expires_at,
    )


def test_schema_installation_respects_the_callers_transaction() -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute("BEGIN")
    ensure_schema(connection)
    assert connection.in_transaction is True
    connection.rollback()
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    assert "assessment_leases" not in tables
    assert "learner_events" not in tables
    connection.close()


def test_schema_is_normalized_and_has_no_answer_bearing_or_generic_payload_columns(
    conn: sqlite3.Connection,
) -> None:
    expected = {
        "assessment_leases",
        "assessment_lease_cases",
        "learner_events",
        "learner_event_competencies",
    }
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    assert expected <= tables

    forbidden_fragments = {
        "answer",
        "response",
        "payload",
        "json",
        "manifest",
        "rationale",
        "feedback",
        "grade",
        "correct",
    }
    for table in expected:
        columns = {
            str(row[1]).lower()
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        assert not {
            column
            for column in columns
            if any(fragment in column for fragment in forbidden_fragments)
        }


def test_duplicate_lease_is_deterministic_and_clinical_protects_multiple_ecgs(
    conn: sqlite3.Connection,
) -> None:
    created = _lease(
        conn,
        lease_id="clinical-generation",
        mode="clinical",
        session_id="clinical-shift",
        ecg_ids=("ptb-a", "ptb-b", "ptb-c"),
    )
    assert created.state == "active"
    assert created.replayed is False

    replay = _lease(
        conn,
        lease_id="clinical-generation",
        mode="clinical",
        session_id="clinical-shift",
        ecg_ids=("ptb-a", "ptb-b", "ptb-c"),
    )
    assert replay.state == "active"
    assert replay.replayed is True
    assert owner_exposure_ids(conn, owner_id="owner-a", as_of=BASE) == (
        "ptb-a",
        "ptb-b",
        "ptb-c",
    )
    assert conn.execute("SELECT COUNT(*) FROM assessment_leases").fetchone()[0] == 1
    assert (
        conn.execute("SELECT COUNT(*) FROM assessment_lease_cases").fetchone()[0]
        == 3
    )

    with pytest.raises(IdempotencyConflictError):
        _lease(
            conn,
            lease_id="clinical-generation",
            mode="clinical",
            session_id="clinical-shift",
            ecg_ids=("ptb-a", "ptb-c", "ptb-b"),
        )
    with pytest.raises(ActiveLeaseConflictError):
        _lease(
            conn,
            lease_id="another-generation",
            mode="clinical",
            session_id="clinical-shift",
            ecg_ids=("ptb-d",),
        )


def test_expiry_is_inclusive_but_a_prior_claim_wins_the_race(
    conn: sqlite3.Connection,
) -> None:
    _lease(conn, lease_id="loses-at-boundary", expires_at=BASE + timedelta(minutes=1))
    boundary = BASE + timedelta(minutes=1)
    with pytest.raises(LeaseExpiredError):
        claim_submission(
            conn,
            lease_id="loses-at-boundary",
            owner_id="owner-a",
            submission_key="submit-late",
            claimed_at=boundary,
        )

    expired = expire_due_leases(conn, expired_at=boundary)
    assert [row.lease_id for row in expired] == ["loses-at-boundary"]
    assert expire_due_leases(conn, expired_at=boundary) == ()
    expired_event = append_event(
        conn,
        event_id=terminal_event_id("loses-at-boundary", "expired"),
        owner_id="owner-a",
        mode="rapid",
        session_id="session-1",
        lease_id="loses-at-boundary",
        event_type="item_expired",
        evidence_level="formative",
        integrity_status="atomic_v2",
        occurred_at=boundary,
    )
    assert expired_event.replayed is False
    assert append_event(
        conn,
        event_id=terminal_event_id("loses-at-boundary", "expired"),
        owner_id="owner-a",
        mode="rapid",
        session_id="session-1",
        lease_id="loses-at-boundary",
        event_type="item_expired",
        evidence_level="formative",
        integrity_status="atomic_v2",
        occurred_at=boundary,
    ).replayed is True

    _lease(
        conn,
        lease_id="claim-wins",
        session_id="session-2",
        expires_at=boundary,
    )
    claimed = claim_submission(
        conn,
        lease_id="claim-wins",
        owner_id="owner-a",
        submission_key="submit-before",
        claimed_at=boundary - timedelta(microseconds=1),
    )
    assert claimed.state == "submitting"
    assert expire_due_leases(conn, expired_at=boundary + timedelta(hours=1)) == ()
    assert mark_submitted(
        conn,
        lease_id="claim-wins",
        owner_id="owner-a",
        submission_key="submit-before",
        submitted_at=boundary + timedelta(hours=1),
    ).state == "submitted"


def test_claim_release_and_same_submission_key_replay(conn: sqlite3.Connection) -> None:
    _lease(conn)
    first = claim_submission(
        conn,
        lease_id="lease-1",
        owner_id="owner-a",
        submission_key="request-1",
        claimed_at=BASE + timedelta(seconds=2),
    )
    assert first.replayed is False
    replay = claim_submission(
        conn,
        lease_id="lease-1",
        owner_id="owner-a",
        submission_key="request-1",
        claimed_at=BASE + timedelta(seconds=3),
    )
    assert (replay.state, replay.replayed) == ("submitting", True)
    with pytest.raises(SubmissionKeyConflictError):
        claim_submission(
            conn,
            lease_id="lease-1",
            owner_id="owner-a",
            submission_key="request-2",
            claimed_at=BASE + timedelta(seconds=3),
        )

    assert release_submission(
        conn,
        lease_id="lease-1",
        owner_id="owner-a",
        submission_key="request-1",
        released_at=BASE + timedelta(seconds=4),
    ).state == "active"
    claim_submission(
        conn,
        lease_id="lease-1",
        owner_id="owner-a",
        submission_key="request-2",
        claimed_at=BASE + timedelta(seconds=5),
    )
    assert mark_submitted(
        conn,
        lease_id="lease-1",
        owner_id="owner-a",
        submission_key="request-2",
        submitted_at=BASE + timedelta(seconds=6),
    ).replayed is False
    assert mark_submitted(
        conn,
        lease_id="lease-1",
        owner_id="owner-a",
        submission_key="request-2",
        submitted_at=BASE + timedelta(seconds=7),
    ).replayed is True
    with pytest.raises(SubmissionKeyConflictError):
        mark_submitted(
            conn,
            lease_id="lease-1",
            owner_id="owner-a",
            submission_key="request-3",
            submitted_at=BASE + timedelta(seconds=7),
        )


def test_terminal_states_are_immutable_and_lease_ids_prevent_aba(
    conn: sqlite3.Connection,
) -> None:
    _lease(conn, lease_id="generation-a", session_id="reused-session")
    claim_submission(
        conn,
        lease_id="generation-a",
        owner_id="owner-a",
        submission_key="same-request-key",
        claimed_at=BASE + timedelta(seconds=1),
    )
    terminalize_lease(
        conn,
        lease_id="generation-a",
        owner_id="owner-a",
        terminal_state="superseded",
        terminal_at=BASE + timedelta(seconds=2),
    )
    assert terminalize_lease(
        conn,
        lease_id="generation-a",
        owner_id="owner-a",
        terminal_state="superseded",
        terminal_at=BASE + timedelta(seconds=3),
    ).replayed is True
    with pytest.raises(LeaseStateError):
        terminalize_lease(
            conn,
            lease_id="generation-a",
            owner_id="owner-a",
            terminal_state="abandoned",
            terminal_at=BASE + timedelta(seconds=3),
        )

    _lease(
        conn,
        lease_id="generation-b",
        session_id="reused-session",
        ecg_ids=("ecg-2",),
        created_at=BASE + timedelta(seconds=3),
        expires_at=BASE + timedelta(minutes=2),
    )
    with pytest.raises(LeaseStateError):
        mark_submitted(
            conn,
            lease_id="generation-a",
            owner_id="owner-a",
            submission_key="same-request-key",
            submitted_at=BASE + timedelta(seconds=4),
        )
    assert claim_submission(
        conn,
        lease_id="generation-b",
        owner_id="owner-a",
        submission_key="same-request-key",
        claimed_at=BASE + timedelta(seconds=4),
    ).replayed is False

    with pytest.raises(sqlite3.IntegrityError, match="terminal state is immutable"):
        conn.execute(
            "UPDATE assessment_leases SET terminal_at = ? "
            "WHERE lease_id = 'generation-a'",
            (BASE.isoformat(),),
        )


def test_event_append_is_idempotent_answer_free_and_competencies_are_normalized(
    conn: sqlite3.Connection,
) -> None:
    _lease(conn, ecg_ids=("ecg-a", "ecg-b"), mode="clinical")
    claim_submission(
        conn,
        lease_id="lease-1",
        owner_id="owner-a",
        submission_key="answer-request",
        claimed_at=BASE + timedelta(seconds=1),
    )
    first = append_event(
        conn,
        event_id="answer-event",
        owner_id="owner-a",
        mode="clinical",
        session_id="session-1",
        lease_id="lease-1",
        ecg_id="ecg-b",
        event_type="answer_committed",
        evidence_level="independent_transfer",
        integrity_status="atomic_v2",
        score=0.75,
        competencies={"rhythm.af": 1.0, "safety.stability": 0.5},
        submission_key="answer-request",
        occurred_at=BASE + timedelta(seconds=2),
    )
    assert first.replayed is False
    replay = append_event(
        conn,
        event_id="answer-event",
        owner_id="owner-a",
        mode="clinical",
        session_id="session-1",
        lease_id="lease-1",
        ecg_id="ecg-b",
        event_type="answer_committed",
        evidence_level="independent_transfer",
        integrity_status="atomic_v2",
        score=0.75,
        competencies=(("safety.stability", 0.5), ("rhythm.af", 1.0)),
        submission_key="answer-request",
        occurred_at=BASE + timedelta(seconds=2),
    )
    assert replay.replayed is True
    with pytest.raises(SubmissionKeyConflictError):
        append_event(
            conn,
            event_id="answer-event",
            owner_id="owner-a",
            mode="clinical",
            session_id="session-1",
            lease_id="lease-1",
            ecg_id="ecg-b",
            event_type="answer_committed",
            evidence_level="independent_transfer",
            integrity_status="atomic_v2",
            score=0.75,
            competencies={"rhythm.af": 1.0, "safety.stability": 0.5},
            submission_key="another-request",
            occurred_at=BASE + timedelta(seconds=2),
        )
    assert conn.execute(
        "SELECT competency_id, competency_score "
        "FROM learner_event_competencies ORDER BY competency_id"
    ).fetchall() == [("rhythm.af", 1.0), ("safety.stability", 0.5)]

    with pytest.raises(IdempotencyConflictError):
        append_event(
            conn,
            event_id="answer-event",
            owner_id="owner-a",
            mode="clinical",
            session_id="session-1",
            lease_id="lease-1",
            ecg_id="ecg-b",
            event_type="answer_committed",
            evidence_level="independent_transfer",
            integrity_status="atomic_v2",
            score=1.0,
            competencies={"rhythm.af": 1.0},
            submission_key="answer-request",
            occurred_at=BASE + timedelta(seconds=2),
        )
    with pytest.raises(LedgerValidationError, match="not protected"):
        append_event(
            conn,
            event_id="wrong-ecg",
            owner_id="owner-a",
            mode="clinical",
            session_id="session-1",
            lease_id="lease-1",
            ecg_id="ecg-outside-lease",
            event_type="answer_committed",
            evidence_level="independent_transfer",
            integrity_status="atomic_v2",
            score=1.0,
            submission_key="answer-request",
            occurred_at=BASE + timedelta(seconds=2),
        )


@pytest.mark.parametrize(
    ("event_type", "terminal_state"),
    [
        ("item_presented", None),
        ("item_expired", "expired"),
        ("item_abandoned", "abandoned"),
        ("session_abandoned", "abandoned"),
        ("session_completed", None),
        ("answer_quarantined", "quarantined"),
    ],
)
def test_precommit_and_unscored_terminal_events_reject_score_and_competencies(
    conn: sqlite3.Connection,
    event_type: str,
    terminal_state: str | None,
) -> None:
    lease_id = f"lease-{event_type}"
    session_id = f"session-{event_type}"
    _lease(conn, lease_id=lease_id, session_id=session_id)
    if terminal_state is not None:
        terminalize_lease(
            conn,
            lease_id=lease_id,
            owner_id="owner-a",
            terminal_state=terminal_state,
            terminal_at=(
                BASE + timedelta(minutes=1)
                if terminal_state == "expired"
                else BASE + timedelta(seconds=1)
            ),
        )
    kwargs = {
        "event_id": f"event-{event_type}",
        "owner_id": "owner-a",
        "mode": "rapid",
        "session_id": session_id,
        "event_type": event_type,
        "evidence_level": "formative",
        "integrity_status": "atomic_v2",
        "occurred_at": BASE + timedelta(minutes=1),
    }
    if event_type in {
        "item_presented",
        "item_expired",
        "item_abandoned",
        "answer_quarantined",
    }:
        kwargs["lease_id"] = lease_id

    with pytest.raises(LedgerValidationError, match="unscored"):
        append_event(conn, score=0.5, **kwargs)
    with pytest.raises(LedgerValidationError, match="competency evidence"):
        append_event(conn, competencies={"objective.secret": 1.0}, **kwargs)
    assert conn.execute(
        "SELECT COUNT(*) FROM learner_event_competencies"
    ).fetchone()[0] == 0


def test_owner_exposure_query_and_mutations_are_owner_isolated(
    conn: sqlite3.Connection,
) -> None:
    _lease(conn, lease_id="owner-a-lease", owner_id="owner-a", ecg_ids=("a-ecg",))
    _lease(
        conn,
        lease_id="owner-b-lease",
        owner_id="owner-b",
        session_id="session-b",
        ecg_ids=("b-ecg",),
    )
    assert owner_exposure_ids(conn, owner_id="owner-a", as_of=BASE) == ("a-ecg",)
    assert owner_exposure_ids(conn, owner_id="owner-b", as_of=BASE) == ("b-ecg",)
    assert owner_exposure_ids(conn, owner_id="owner-c", as_of=BASE) == ()


def test_event_scope_ignore_allows_only_same_session_frozen_item_renewal(
    conn: sqlite3.Connection,
) -> None:
    expiry = BASE + timedelta(minutes=1)
    _lease(
        conn,
        lease_id="renewal-lease",
        owner_id="renewal-owner",
        session_id="renewal-session",
        ecg_ids=("renewal-ecg",),
        expires_at=expiry,
    )
    append_event(
        conn,
        event_id="renewal-presented",
        owner_id="renewal-owner",
        mode="rapid",
        session_id="renewal-session",
        lease_id="renewal-lease",
        ecg_id="renewal-ecg",
        event_type="item_presented",
        evidence_level="independent_transfer",
        integrity_status="atomic_v2",
        occurred_at=BASE,
    )
    terminalize_lease(
        conn,
        lease_id="renewal-lease",
        owner_id="renewal-owner",
        terminal_state="expired",
        terminal_at=expiry,
    )

    assert owner_exposure_ids(
        conn, owner_id="renewal-owner", as_of=expiry
    ) == ("renewal-ecg",)
    assert owner_exposure_ids(
        conn,
        owner_id="renewal-owner",
        as_of=expiry,
        ignore_presentation_scope=(
            "rapid",
            "renewal-session",
            "renewal-ecg",
        ),
    ) == ()

    # A committed interaction in that same session is not a presentation-only
    # renewal artifact and must keep protecting the ECG.
    append_event(
        conn,
        event_id="renewal-interaction",
        owner_id="renewal-owner",
        mode="rapid",
        session_id="renewal-session",
        ecg_id="renewal-ecg",
        event_type="interaction_committed",
        evidence_level="independent_transfer",
        integrity_status="atomic_v2",
        occurred_at=expiry,
        score=0.5,
    )
    assert owner_exposure_ids(
        conn,
        owner_id="renewal-owner",
        as_of=expiry,
        ignore_presentation_scope=(
            "rapid",
            "renewal-session",
            "renewal-ecg",
        ),
    ) == ("renewal-ecg",)

    conn.execute(
        "DELETE FROM learner_events WHERE event_id = 'renewal-interaction'"
    )

    # Another scope's recent reveal continues to protect the ECG even when the
    # renewing Rapid session ignores only its own prior presentation event.
    record_guided_packet_exposure(
        conn,
        owner_id="renewal-owner",
        lesson_id="axis",
        ecg_id="renewal-ecg",
        occurred_at=expiry,
    )
    assert owner_exposure_ids(
        conn,
        owner_id="renewal-owner",
        as_of=expiry,
        ignore_presentation_scope=(
            "rapid",
            "renewal-session",
            "renewal-ecg",
        ),
    ) == ("renewal-ecg",)


def test_guided_packet_exposure_is_owner_bound_answer_free_and_refresh_idempotent(
    conn: sqlite3.Connection,
) -> None:
    first = record_guided_packet_exposure(
        conn,
        owner_id="owner-a",
        lesson_id="axis",
        ecg_id="ptb-guided-axis",
        occurred_at=BASE,
    )
    replay = record_guided_packet_exposure(
        conn,
        owner_id="owner-a",
        lesson_id="axis",
        ecg_id="ptb-guided-axis",
        occurred_at=BASE + timedelta(minutes=2),
    )
    assert first.replayed is False
    assert replay == type(first)(first.event_id, True)
    assert "owner-a" not in first.event_id
    assert "ptb-guided-axis" not in first.event_id
    assert owner_exposure_ids(conn, owner_id="owner-a", as_of=BASE) == (
        "ptb-guided-axis",
    )
    assert owner_exposure_ids(conn, owner_id="owner-b", as_of=BASE) == ()

    event = conn.execute(
        "SELECT mode, session_id, ecg_id, event_type, score, lease_id, occurred_at "
        "FROM learner_events WHERE event_id = ?",
        (first.event_id,),
    ).fetchone()
    assert tuple(event[:6]) == (
        "guided",
        "tutorial:axis",
        "ptb-guided-axis",
        "item_presented",
        None,
        None,
    )
    assert event[6] == BASE.isoformat(timespec="microseconds")
    assert conn.execute(
        "SELECT COUNT(*) FROM learner_event_competencies WHERE event_id = ?",
        (first.event_id,),
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM learner_events WHERE owner_id = 'owner-a'"
    ).fetchone()[0] == 1

    # The ECG becomes a valid spaced reassessment at the exact 30-day boundary.
    reassessment_at = BASE + timedelta(days=30)
    assert owner_exposure_ids(
        conn, owner_id="owner-a", as_of=reassessment_at
    ) == ()
    later = record_guided_packet_exposure(
        conn,
        owner_id="owner-a",
        lesson_id="axis",
        ecg_id="ptb-guided-axis",
        occurred_at=reassessment_at,
    )
    assert later.event_id != first.event_id
    assert owner_exposure_ids(
        conn, owner_id="owner-a", as_of=reassessment_at
    ) == ("ptb-guided-axis",)


def test_owner_exposure_includes_legacy_guided_and_generic_attempt_history(
    conn: sqlite3.Connection,
) -> None:
    conn.execute(
        "CREATE TABLE guided_learning_events "
        "(learner_id TEXT, case_id TEXT, created_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE attempts (learner_id TEXT, case_id TEXT, created_at TEXT)"
    )
    recent = (BASE - timedelta(hours=12)).isoformat(timespec="microseconds")
    boundary = (BASE - timedelta(days=1)).isoformat(timespec="microseconds")
    future = (BASE + timedelta(seconds=1)).isoformat(timespec="microseconds")
    conn.executemany(
        "INSERT INTO guided_learning_events VALUES (?, ?, ?)",
        (
            ("owner-a", "guided-recent", recent),
            ("owner-a", "guided-at-boundary", boundary),
            ("owner-b", "guided-other-owner", recent),
        ),
    )
    conn.executemany(
        "INSERT INTO attempts VALUES (?, ?, ?)",
        (
            ("owner-a", "generic-recent", recent),
            ("owner-a", "generic-future", future),
            ("owner-b", "generic-other-owner", recent),
        ),
    )
    assert owner_exposure_ids(
        conn,
        owner_id="owner-a",
        as_of=BASE,
        reassessment_interval=timedelta(days=1),
    ) == ("generic-recent", "guided-recent")


def test_due_active_exposure_stops_blocking_other_modes_but_inflight_submit_stays_protected(
    conn: sqlite3.Connection,
) -> None:
    expiry = BASE + timedelta(minutes=1)
    _lease(
        conn,
        lease_id="due-active",
        owner_id="active-owner",
        ecg_ids=("expired-ecg",),
        expires_at=expiry,
    )
    assert owner_exposure_ids(
        conn, owner_id="active-owner", as_of=expiry - timedelta(microseconds=1)
    ) == ("expired-ecg",)
    assert owner_exposure_ids(
        conn, owner_id="active-owner", as_of=expiry
    ) == ()
    assert conn.execute(
        "SELECT state FROM assessment_leases WHERE lease_id='due-active'"
    ).fetchone()[0] == "active"

    _lease(
        conn,
        lease_id="inflight",
        owner_id="submitting-owner",
        session_id="submitting-session",
        ecg_ids=("inflight-ecg",),
        expires_at=expiry,
    )
    claim_submission(
        conn,
        lease_id="inflight",
        owner_id="submitting-owner",
        submission_key="inflight-key",
        claimed_at=BASE + timedelta(seconds=10),
    )
    assert owner_exposure_ids(
        conn,
        owner_id="submitting-owner",
        as_of=expiry + timedelta(hours=1),
    ) == ("inflight-ecg",)


def test_owner_reassignment_preserves_composite_foreign_keys_and_evidence(
    conn: sqlite3.Connection,
) -> None:
    _lease(
        conn,
        lease_id="guest-lease",
        owner_id="guest-owner",
        session_id="guest-session",
        ecg_ids=("guest-ecg",),
    )
    claim_submission(
        conn,
        lease_id="guest-lease",
        owner_id="guest-owner",
        submission_key="guest-submit",
        claimed_at=BASE + timedelta(seconds=1),
    )
    append_event(
        conn,
        event_id="guest-answer-event",
        owner_id="guest-owner",
        mode="rapid",
        session_id="guest-session",
        lease_id="guest-lease",
        ecg_id="guest-ecg",
        event_type="answer_committed",
        evidence_level="independent_transfer",
        integrity_status="atomic_v2",
        score=0.75,
        competencies={"rhythm.af::recognize": 0.75},
        submission_key="guest-submit",
        occurred_at=BASE + timedelta(seconds=2),
    )

    moved = reassign_owner(
        conn,
        source_owner_id="guest-owner",
        destination_owner_id="account-owner",
    )
    conn.commit()

    assert (moved.leases, moved.events, moved.competencies) == (1, 1, 1)
    assert owner_exposure_ids(conn, owner_id="guest-owner", as_of=BASE) == ()
    assert owner_exposure_ids(conn, owner_id="account-owner", as_of=BASE) == ("guest-ecg",)
    assert conn.execute(
        "SELECT owner_id FROM learner_events WHERE event_id = 'guest-answer-event'"
    ).fetchone()[0] == "account-owner"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert reassign_owner(
        conn,
        source_owner_id="guest-owner",
        destination_owner_id="account-owner",
    ).leases == 0


def test_owner_reassignment_rejects_destination_live_session_collision(
    conn: sqlite3.Connection,
) -> None:
    _lease(
        conn,
        lease_id="source-live",
        owner_id="guest-owner",
        session_id="shared-session",
        ecg_ids=("source-ecg",),
    )
    _lease(
        conn,
        lease_id="destination-live",
        owner_id="account-owner",
        session_id="shared-session",
        ecg_ids=("destination-ecg",),
    )
    with pytest.raises(ActiveLeaseConflictError, match="destination owner"):
        reassign_owner(
            conn,
            source_owner_id="guest-owner",
            destination_owner_id="account-owner",
        )
    assert owner_exposure_ids(conn, owner_id="guest-owner", as_of=BASE) == ("source-ecg",)
    assert owner_exposure_ids(conn, owner_id="account-owner", as_of=BASE) == (
        "destination-ecg",
    )


def test_owner_record_deletion_removes_children_without_touching_other_owner(
    conn: sqlite3.Connection,
) -> None:
    _lease(
        conn,
        lease_id="delete-lease",
        owner_id="delete-owner",
        session_id="delete-session",
        ecg_ids=("delete-ecg",),
    )
    claim_submission(
        conn,
        lease_id="delete-lease",
        owner_id="delete-owner",
        submission_key="delete-submit",
        claimed_at=BASE + timedelta(seconds=1),
    )
    append_event(
        conn,
        event_id="delete-event",
        owner_id="delete-owner",
        mode="rapid",
        session_id="delete-session",
        lease_id="delete-lease",
        ecg_id="delete-ecg",
        event_type="answer_committed",
        evidence_level="formative",
        integrity_status="atomic_v2",
        score=0.25,
        competencies={"rhythm.af::recognize": 0.25},
        submission_key="delete-submit",
        occurred_at=BASE + timedelta(seconds=2),
    )
    _lease(
        conn,
        lease_id="keep-lease",
        owner_id="keep-owner",
        session_id="keep-session",
        ecg_ids=("keep-ecg",),
    )

    deleted = delete_owner_records(conn, owner_id="delete-owner")
    conn.commit()

    assert (deleted.leases, deleted.events, deleted.competencies) == (1, 1, 1)
    assert conn.execute(
        "SELECT COUNT(*) FROM assessment_leases WHERE owner_id = 'delete-owner'"
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM learner_events WHERE owner_id = 'delete-owner'"
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM learner_event_competencies"
    ).fetchone()[0] == 0
    assert owner_exposure_ids(conn, owner_id="keep-owner", as_of=BASE) == ("keep-ecg",)
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    with pytest.raises(LeaseNotFoundError):
        claim_submission(
            conn,
            lease_id="owner-a-lease",
            owner_id="owner-b",
            submission_key="not-yours",
            claimed_at=BASE + timedelta(seconds=1),
        )


def test_allowlists_fail_closed(conn: sqlite3.Connection) -> None:
    with pytest.raises(LedgerValidationError, match="lease mode"):
        _lease(conn, mode="guided")
    _lease(conn)
    with pytest.raises(LedgerValidationError, match="terminal state"):
        terminalize_lease(
            conn,
            lease_id="lease-1",
            owner_id="owner-a",
            terminal_state="finished",
            terminal_at=BASE + timedelta(seconds=1),
        )
    with pytest.raises(LedgerValidationError, match="event type"):
        append_event(
            conn,
            event_id="unknown-event",
            owner_id="owner-a",
            mode="guided",
            session_id="guided-1",
            event_type="clicked_around",
            evidence_level="guided",
            integrity_status="atomic_v2",
            occurred_at=BASE,
        )
    with pytest.raises(LedgerValidationError, match="evidence level"):
        append_event(
            conn,
            event_id="unknown-evidence",
            owner_id="owner-a",
            mode="guided",
            session_id="guided-1",
            event_type="session_started",
            evidence_level="mastered",
            integrity_status="atomic_v2",
            occurred_at=BASE,
        )
    with pytest.raises(LedgerValidationError, match="integrity status"):
        append_event(
            conn,
            event_id="unknown-integrity",
            owner_id="owner-a",
            mode="guided",
            session_id="guided-1",
            event_type="session_started",
            evidence_level="guided",
            integrity_status="best_effort",
            occurred_at=BASE,
        )
    with pytest.raises(LedgerValidationError, match="lease state"):
        owner_exposure_ids(conn, owner_id="owner-a", states=("pending",), as_of=BASE)


def test_ledger_helpers_do_not_mutate_mastery_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE objective_mastery "
        "(owner_id TEXT, objective TEXT, mastery REAL, attempts INTEGER)"
    )
    conn.execute(
        "INSERT INTO objective_mastery VALUES ('owner-a', 'rhythm.af', 0.42, 7)"
    )
    before = conn.execute("SELECT * FROM objective_mastery").fetchall()

    _lease(conn)
    claim_submission(
        conn,
        lease_id="lease-1",
        owner_id="owner-a",
        submission_key="submission-1",
        claimed_at=BASE + timedelta(seconds=1),
    )
    append_event(
        conn,
        event_id="scored-event",
        owner_id="owner-a",
        mode="rapid",
        session_id="session-1",
        lease_id="lease-1",
        ecg_id="ecg-1",
        event_type="answer_committed",
        evidence_level="independent_transfer",
        integrity_status="atomic_v2",
        score=1.0,
        competencies={"rhythm.af": 1.0},
        submission_key="submission-1",
        occurred_at=BASE + timedelta(seconds=2),
    )
    mark_submitted(
        conn,
        lease_id="lease-1",
        owner_id="owner-a",
        submission_key="submission-1",
        submitted_at=BASE + timedelta(seconds=2),
    )

    assert conn.execute("SELECT * FROM objective_mastery").fetchall() == before
