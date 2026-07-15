from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from types import SimpleNamespace

import pytest

from app.ops import RetentionCleanupCoordinator, build_ops_router
from app.storage import LearningStore
from app.training_store import TrainingCampaignStore


NOW = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


def _store(tmp_path) -> LearningStore:
    store = LearningStore(tmp_path / "retention.db")
    TrainingCampaignStore(tmp_path / "retention.db", store.connect)
    return store


def _guest(char: str) -> str:
    return f"g_{char * 24}"


def _profile_at(store: LearningStore, learner_id: str, instant: datetime) -> None:
    store.ensure_profile(learner_id)
    with store.connect() as conn:
        conn.execute(
            "UPDATE learner_profiles SET created_at = ?, updated_at = ? "
            "WHERE learner_id = ?",
            (instant.isoformat(), instant.isoformat(), learner_id),
        )


def _seed_guest_graph(
    store: LearningStore, learner_id: str, instant: datetime, prefix: str
) -> None:
    """Create parent and child records in every nested mode ledger."""

    _profile_at(store, learner_id, instant)
    stamp = instant.isoformat()
    with store.connect() as conn:
        attempt = conn.execute(
            "INSERT INTO attempts (learner_id, case_id, mode, structured_answer_json, "
            "free_text_answer, confidence, hints_used, score, correct_objectives_json, "
            "missed_objectives_json, misconception_tags_json, feedback, created_at) "
            "VALUES (?, ?, 'guided', '{}', '', 3, 0, .5, '[]', '[]', '[]', '', ?)",
            (learner_id, f"{prefix}-attempt", stamp),
        )
        attempt_id = int(attempt.lastrowid)
        conn.execute(
            "INSERT INTO tutor_threads "
            "(thread_id, learner_id, mode, title, created_at, updated_at) "
            "VALUES (?, ?, 'freeform', 'Help', ?, ?)",
            (f"{prefix}-thread", learner_id, stamp, stamp),
        )
        conn.execute(
            "INSERT INTO tutor_messages (thread_id, role, content, created_at) "
            "VALUES (?, 'user', 'Question', ?)",
            (f"{prefix}-thread", stamp),
        )
        conn.execute(
            "INSERT INTO rapid_rounds "
            "(round_id, learner_id, pace, length, assessment_scope, exclusions_json, "
            "served_json, position, status, created_at, updated_at) "
            "VALUES (?, ?, 'ward', 5, 'broad', '[]', '[]', 0, 'complete', ?, ?)",
            (f"{prefix}-rapid", learner_id, stamp, stamp),
        )
        conn.execute(
            "INSERT INTO rapid_round_answers "
            "(round_id, case_id, response_json, grade_json, tutor_json, result_json, "
            "receipts_json, integrity_status, attempt_id, created_at) "
            "VALUES (?, ?, '{}', '{}', '{}', '{}', '[]', 'legacy_incomplete', ?, ?)",
            (f"{prefix}-rapid", f"{prefix}-rapid-case", attempt_id, stamp),
        )
        conn.execute(
            "INSERT INTO clinical_shift_sessions "
            "(session_id, learner_id, lane, tier, length, requested_length, "
            "available_length, served_json, served_ecgs_json, calibration_json, "
            "position, status, created_at, updated_at) "
            "VALUES (?, ?, 'ward', 'student', 5, 5, 5, '[]', '[]', '[]', 0, "
            "'complete', ?, ?)",
            (f"{prefix}-clinical", learner_id, stamp, stamp),
        )
        conn.execute(
            "INSERT INTO clinical_shift_answers "
            "(session_id, item_id, ecg_id, response_json, grade_json, receipts_json, "
            "score, correct, attempt_id, created_at) "
            "VALUES (?, ?, ?, '{}', '{}', '[]', .5, 0, ?, ?)",
            (
                f"{prefix}-clinical",
                f"{prefix}-item",
                f"{prefix}-ecg",
                attempt_id,
                stamp,
            ),
        )
        conn.execute(
            "INSERT INTO training_campaigns "
            "(campaign_id, learner_id, concept_id, subskill, requested_length, "
            "length, pool_count, phases_json, phase_counts_json, position, status, "
            "context_key, created_at, updated_at) "
            "VALUES (?, ?, 'atrial_fibrillation', 'recognize', 5, 5, 10, "
            "'[\"recognize\"]', '{\"recognize\":5}', 1, 'complete', '', ?, ?)",
            (f"{prefix}-training", learner_id, stamp, stamp),
        )
        conn.execute(
            "INSERT INTO training_campaign_slots "
            "(campaign_id, ordinal, phase, case_id, case_focus, target_present, "
            "status, served_at, answered_at) "
            "VALUES (?, 0, 'recognize', ?, 'target', 1, 'answered', ?, ?)",
            (f"{prefix}-training", f"{prefix}-training-case", stamp, stamp),
        )
        conn.execute(
            "INSERT INTO training_campaign_answers "
            "(campaign_id, ordinal, case_id, response_json, grade_json, tutor_json, "
            "receipt_json, summary_json, attempt_id, created_at) "
            "VALUES (?, 0, ?, '{}', '{}', '{}', '[]', '{}', ?, ?)",
            (
                f"{prefix}-training",
                f"{prefix}-training-case",
                attempt_id,
                stamp,
            ),
        )


def _table_count(store: LearningStore, table: str, predicate: str = "1=1", params=()) -> int:
    with store.connect() as conn:
        return int(
            conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {predicate}", params
            ).fetchone()[0]
        )


def test_expiry_cleanup_is_inclusive_bounded_and_idempotent(tmp_path) -> None:
    store = _store(tmp_path)
    before = (NOW - timedelta(seconds=1)).isoformat()
    exact = NOW.isoformat()
    future = (NOW + timedelta(seconds=1)).isoformat()
    with store.connect() as conn:
        for suffix, expiry in (("before", before), ("exact", exact), ("future", future)):
            conn.execute(
                "INSERT INTO sessions (token, user_id, created_at, expires_at) "
                "VALUES (?, 'u_owner', ?, ?)",
                (f"session-{suffix}", before, expiry),
            )
            conn.execute(
                "INSERT INTO export_authorizations "
                "(token_hash, user_id, session_hash, password_fingerprint, "
                "created_at, expires_at) VALUES (?, 'u_owner', 'session', 'password', ?, ?)",
                (f"export-{suffix}", before, expiry),
            )
            conn.execute(
                "INSERT INTO maintenance_leases "
                "(lease_name, token_hash, acquired_at, expires_at) VALUES (?, ?, ?, ?)",
                (f"lease-{suffix}", f"hash-{suffix}", before, expiry),
            )

    first = store.cleanup_retention(
        now=NOW, guest_inactivity_days=30, batch_size=1
    )
    assert first == {
        "expiredSessions": 1,
        "expiredExportAuthorizations": 1,
        "expiredAuthChallenges": 0,
        "expiredAuthVerificationBudgets": 0,
        "expiredMaintenanceLeases": 1,
        "inactiveGuestOwners": 0,
        "inactiveGuestRecords": 0,
        "expiredUnverifiedAccounts": 0,
    }
    # The exact-cutoff rows are expired but remain only because this pass was
    # bounded to one row per transient ledger.
    assert _table_count(store, "sessions", "token = 'session-exact'") == 1

    second = store.cleanup_retention(
        now=NOW, guest_inactivity_days=30, batch_size=10
    )
    assert second["expiredSessions"] == 1
    assert second["expiredExportAuthorizations"] == 1
    assert second["expiredMaintenanceLeases"] == 1
    assert _table_count(store, "sessions", "token = 'session-future'") == 1
    assert _table_count(store, "export_authorizations", "token_hash = 'export-future'") == 1
    assert _table_count(store, "maintenance_leases", "lease_name = 'lease-future'") == 1

    repeated = store.cleanup_retention(
        now=NOW, guest_inactivity_days=30, batch_size=10
    )
    assert repeated == {
        "expiredSessions": 0,
        "expiredExportAuthorizations": 0,
        "expiredAuthChallenges": 0,
        "expiredAuthVerificationBudgets": 0,
        "expiredMaintenanceLeases": 0,
        "inactiveGuestOwners": 0,
        "inactiveGuestRecords": 0,
        "expiredUnverifiedAccounts": 0,
    }


def test_guest_cutoff_preserves_recent_activity_and_authenticated_owner(tmp_path) -> None:
    store = _store(tmp_path)
    cutoff = NOW - timedelta(days=30)
    old = cutoff - timedelta(seconds=1)
    stale_guest = _guest("s")
    boundary_guest = _guest("b")
    active_guest = _guest("a")
    resumable_guest = _guest("m")
    account_with_guest_shape = _guest("u")

    _seed_guest_graph(store, stale_guest, old, "stale")
    _profile_at(store, boundary_guest, cutoff)
    _profile_at(store, active_guest, old)
    _profile_at(store, resumable_guest, old)
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO tutor_threads "
            "(thread_id, learner_id, mode, title, created_at, updated_at) "
            "VALUES ('active-thread', ?, 'freeform', 'Help', ?, ?)",
            (active_guest, old.isoformat(), old.isoformat()),
        )
        # Child-only activity exactly on the cutoff is enough to preserve the
        # entire anonymous owner graph.
        conn.execute(
            "INSERT INTO tutor_messages (thread_id, role, content, created_at) "
            "VALUES ('active-thread', 'user', 'Still active', ?)",
            (cutoff.isoformat(),),
        )
        conn.execute(
            "INSERT INTO rapid_rounds "
            "(round_id, learner_id, pace, length, assessment_scope, exclusions_json, "
            "served_json, pending_case_id, pending_manifest_json, position, status, "
            "created_at, updated_at) VALUES "
            "('recent-resumable', ?, 'ward', 5, 'broad', '[]', '[]', "
            "'pending-case', '{}', 0, 'active', ?, ?)",
            (resumable_guest, old.isoformat(), cutoff.isoformat()),
        )
    store.create_user(
        account_with_guest_shape,
        "guest-shaped-account",
        "Authenticated learner",
        "password-hash",
    )
    _profile_at(store, account_with_guest_shape, old)

    counts = store.cleanup_retention(
        now=NOW, guest_inactivity_days=30, batch_size=10
    )

    assert counts["inactiveGuestOwners"] == 1
    assert counts["inactiveGuestRecords"] > 4
    assert _table_count(store, "learner_profiles", "learner_id = ?", (stale_guest,)) == 0
    assert _table_count(store, "tutor_messages", "thread_id = 'stale-thread'") == 0
    assert _table_count(store, "rapid_round_answers", "round_id = 'stale-rapid'") == 0
    assert _table_count(store, "clinical_shift_answers", "session_id = 'stale-clinical'") == 0
    assert _table_count(store, "training_campaign_slots", "campaign_id = 'stale-training'") == 0
    assert _table_count(store, "training_campaign_answers", "campaign_id = 'stale-training'") == 0
    for learner_id in (
        boundary_guest,
        active_guest,
        resumable_guest,
        account_with_guest_shape,
    ):
        assert _table_count(
            store, "learner_profiles", "learner_id = ?", (learner_id,)
        ) == 1
    assert _table_count(store, "users", "user_id = ?", (account_with_guest_shape,)) == 1


def test_inactive_guest_owner_batch_is_bounded_across_repeated_runs(tmp_path) -> None:
    store = _store(tmp_path)
    old = NOW - timedelta(days=31)
    first_guest = _guest("c")
    second_guest = _guest("d")
    _profile_at(store, first_guest, old)
    _profile_at(store, second_guest, old)

    first = store.cleanup_retention(
        now=NOW, guest_inactivity_days=30, batch_size=1
    )
    assert first["inactiveGuestOwners"] == 1
    assert _table_count(
        store,
        "learner_profiles",
        "learner_id IN (?, ?)",
        (first_guest, second_guest),
    ) == 1

    second = store.cleanup_retention(
        now=NOW, guest_inactivity_days=30, batch_size=1
    )
    assert second["inactiveGuestOwners"] == 1
    assert _table_count(
        store,
        "learner_profiles",
        "learner_id IN (?, ?)",
        (first_guest, second_guest),
    ) == 0

    assert store.cleanup_retention(
        now=NOW, guest_inactivity_days=30, batch_size=1
    )["inactiveGuestOwners"] == 0


def test_cleanup_preserves_authenticated_assessment_deadlines(tmp_path) -> None:
    store = _store(tmp_path)
    learner_id = "u_authenticated"
    store.create_user(learner_id, "authenticated", "Learner", "password-hash")
    _profile_at(store, learner_id, NOW - timedelta(days=365))
    old = (NOW - timedelta(days=60)).isoformat()
    deadline = (NOW - timedelta(days=59)).isoformat()
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO rapid_rounds "
            "(round_id, learner_id, pace, length, assessment_scope, exclusions_json, "
            "served_json, pending_case_id, pending_manifest_json, pending_started_at, "
            "pending_deadline_at, position, status, created_at, updated_at) "
            "VALUES ('expired-rapid', ?, 'emergency', 5, 'broad', '[]', '[]', "
            "'pending-ecg', '{\"caseId\":\"pending-ecg\"}', ?, ?, 0, 'active', ?, ?)",
            (learner_id, old, deadline, old, old),
        )
        conn.execute(
            "INSERT INTO clinical_shift_sessions "
            "(session_id, learner_id, lane, tier, length, requested_length, "
            "available_length, served_json, served_ecgs_json, calibration_json, "
            "pending_item_id, pending_orient_started_at, pending_orient_deadline_at, "
            "position, status, created_at, updated_at) "
            "VALUES ('expired-clinical', ?, 'emergency', 'shift', 5, 5, 5, "
            "'[]', '[]', '[]', 'pending-item', ?, ?, 0, 'active', ?, ?)",
            (learner_id, old, deadline, old, old),
        )

    store.cleanup_retention(now=NOW, guest_inactivity_days=30, batch_size=10)

    with store.connect() as conn:
        rapid = conn.execute(
            "SELECT pending_case_id, pending_deadline_at, status "
            "FROM rapid_rounds WHERE round_id = 'expired-rapid'"
        ).fetchone()
        clinical = conn.execute(
            "SELECT pending_item_id, pending_orient_deadline_at, status "
            "FROM clinical_shift_sessions WHERE session_id = 'expired-clinical'"
        ).fetchone()
    assert tuple(rapid) == ("pending-ecg", deadline, "active")
    assert tuple(clinical) == ("pending-item", deadline, "active")


def test_cleanup_rolls_back_all_ledgers_after_failure(tmp_path) -> None:
    store = _store(tmp_path)
    guest_id = _guest("r")
    old = NOW - timedelta(days=31)
    _seed_guest_graph(store, guest_id, old, "rollback")
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) "
            "VALUES ('expired-session', 'u_owner', ?, ?)",
            (old.isoformat(), old.isoformat()),
        )
        conn.execute(
            "INSERT INTO export_authorizations "
            "(token_hash, user_id, session_hash, password_fingerprint, "
            "created_at, expires_at) VALUES "
            "('expired-export', 'u_owner', 'session', 'password', ?, ?)",
            (old.isoformat(), old.isoformat()),
        )
        conn.execute(
            "INSERT INTO maintenance_leases "
            "(lease_name, token_hash, acquired_at, expires_at) "
            "VALUES ('expired-lease', 'hash', ?, ?)",
            (old.isoformat(), old.isoformat()),
        )

    def fail(_conn) -> None:
        raise RuntimeError("injected retention cleanup failure")

    with pytest.raises(RuntimeError, match="injected retention cleanup failure"):
        store.cleanup_retention(
            now=NOW,
            guest_inactivity_days=30,
            batch_size=10,
            _failure_hook=fail,
        )

    assert _table_count(store, "sessions", "token = 'expired-session'") == 1
    assert _table_count(store, "export_authorizations", "token_hash = 'expired-export'") == 1
    assert _table_count(store, "maintenance_leases", "lease_name = 'expired-lease'") == 1
    assert _table_count(store, "learner_profiles", "learner_id = ?", (guest_id,)) == 1
    assert _table_count(store, "training_campaign_answers", "campaign_id = 'rollback-training'") == 1


def test_coordinator_runs_once_when_due_and_logs_counts_only(tmp_path, caplog) -> None:
    store = _store(tmp_path)
    guest_id = _guest("l")
    second_guest_id = _guest("q")
    _profile_at(store, guest_id, NOW - timedelta(days=31))
    _profile_at(store, second_guest_id, NOW - timedelta(days=31))
    settings = SimpleNamespace(
        retention_cleanup_enabled=True,
        guest_inactivity_days=30,
        retention_cleanup_batch_size=1,
        retention_cleanup_interval_seconds=3600,
        retention_cleanup_lease_seconds=300,
    )
    first_worker = RetentionCleanupCoordinator(settings, store)
    second_worker = RetentionCleanupCoordinator(settings, store)

    with caplog.at_level(logging.INFO, logger="app.ops"):
        first = first_worker.maybe_run(now=NOW)
        duplicate = second_worker.maybe_run(now=NOW)

    assert first is not None and first["inactiveGuestOwners"] == 1
    assert duplicate is None
    assert first_worker.healthy is True
    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "inactiveGuestOwners" in messages
    assert guest_id not in messages
    assert second_guest_id not in messages

    assert second_worker.maybe_run(now=NOW + timedelta(seconds=59)) is None
    due_again = second_worker.maybe_run(now=NOW + timedelta(seconds=60))
    assert due_again is not None
    assert due_again["inactiveGuestOwners"] == 1


def test_ops_router_construction_runs_due_startup_cleanup(tmp_path) -> None:
    store = _store(tmp_path)
    guest_id = _guest("o")
    _profile_at(store, guest_id, NOW - timedelta(days=3650))
    settings = SimpleNamespace(
        retention_cleanup_enabled=True,
        guest_inactivity_days=30,
        retention_cleanup_batch_size=10,
        retention_cleanup_interval_seconds=3600,
        retention_cleanup_lease_seconds=300,
    )

    build_ops_router(settings, object(), store, object())

    assert _table_count(
        store, "learner_profiles", "learner_id = ?", (guest_id,)
    ) == 0


def test_live_maintenance_lease_is_owner_safe_and_expired_lease_is_reclaimable(
    tmp_path,
) -> None:
    store = _store(tmp_path)
    assert store.claim_maintenance_lease(
        job_name="job", token="first", now=NOW, lease_seconds=60
    )
    assert not store.claim_maintenance_lease(
        job_name="job",
        token="second",
        now=NOW + timedelta(seconds=59),
        lease_seconds=60,
    )
    assert not store.release_maintenance_lease(job_name="job", token="second")
    assert store.claim_maintenance_lease(
        job_name="job",
        token="second",
        now=NOW + timedelta(seconds=60),
        lease_seconds=60,
    )
    assert not store.complete_maintenance_lease(
        job_name="job", token="first", completed_at=NOW, interval_seconds=3600
    )
    assert store.complete_maintenance_lease(
        job_name="job",
        token="second",
        completed_at=NOW + timedelta(seconds=60),
        interval_seconds=3600,
    )


def test_never_verified_empty_account_shells_expire_without_touching_real_learners(
    tmp_path,
) -> None:
    store = _store(tmp_path)
    users = {
        "u_stale": NOW - timedelta(days=8),
        "u_boundary": NOW - timedelta(days=7),
        "u_verified": NOW - timedelta(days=30),
        "u_with_learning": NOW - timedelta(days=30),
    }
    for user_id, created in users.items():
        store.create_registered_user(
            user_id=user_id,
            username=user_id.removeprefix("u_"),
            display_name=user_id,
            password_hash="test-password-hash",
            email_normalized=f"{user_id}@example.edu",
            session_token=None,
            session_expires_at=None,
            account_origin="pending_registration",
        )
        with store.connect() as conn:
            conn.execute(
                "UPDATE users SET created_at = ? WHERE user_id = ?",
                (created.isoformat(), user_id),
            )
    with store.connect() as conn:
        conn.execute(
            "UPDATE users SET email_verified_at = ? WHERE user_id = 'u_verified'",
            ((NOW - timedelta(days=29)).isoformat(),),
        )
        conn.execute(
            "INSERT INTO attempts (learner_id, case_id, mode, structured_answer_json, "
            "free_text_answer, confidence, hints_used, score, correct_objectives_json, "
            "missed_objectives_json, misconception_tags_json, feedback, created_at) "
            "VALUES ('u_with_learning', 'case', 'rapid', '{}', '', 3, 0, 1, "
            "'[]', '[]', '[]', '', ?)",
            ((NOW - timedelta(days=20)).isoformat(),),
        )
    store.create_auth_challenge(
        challenge_id="ach_stale",
        user_id="u_stale",
        purpose="email_verification",
        secret_hash="hash-only",
        expires_at=(NOW + timedelta(days=1)).isoformat(),
        max_attempts=8,
    )

    counts = store.cleanup_retention(
        now=NOW,
        guest_inactivity_days=30,
        unverified_account_expiry_days=7,
        batch_size=20,
    )

    assert counts["expiredUnverifiedAccounts"] == 1
    assert store.get_user("u_stale") is None
    assert store.get_auth_challenge("ach_stale") is None
    assert store.get_user("u_boundary") is not None
    assert store.get_user("u_verified") is not None
    assert store.get_user("u_with_learning") is not None
