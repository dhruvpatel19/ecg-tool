"""Explicit guest-to-account progress claims and collision safety."""

from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.assessment_ledger import append_event, create_lease
from app.auth import AuthService
from app.guest_progress import (
    GuestProgressClaimConflict,
    GuestProgressClaimUnavailable,
    GuestProgressService,
)
from app.main import app
from app.storage import LearningStore
from app.training_store import TrainingCampaignStore


_PASSWORD = "Guest-Claim-Test-Password!"
_NOW = "2026-07-13T12:00:00+00:00"
_LATER = "2026-07-13T13:00:00+00:00"


def _services(tmp_path):
    db_path = tmp_path / f"claim-{uuid.uuid4().hex}.db"
    store = LearningStore(db_path)
    TrainingCampaignStore(db_path, store.connect)
    claims = GuestProgressService(store)
    return store, claims, AuthService(store, claims)


def _create_account(store: LearningStore, suffix: str) -> str:
    user_id = f"u_{suffix}_{uuid.uuid4().hex[:8]}"
    username = f"claim_{suffix}_{uuid.uuid4().hex[:8]}"
    store.create_user(user_id, username, suffix.title(), "not-used-by-service-tests")
    store.ensure_profile(user_id, suffix.title())
    store.update_learning_preferences(user_id, {"guidanceLevel": "minimal"})
    return user_id


def _insert_attempt(conn, learner_id: str, case_id: str, *, score: float = 0.8) -> int:
    cursor = conn.execute(
        """INSERT INTO attempts (
            learner_id, case_id, mode, structured_answer_json, free_text_answer,
            confidence, hints_used, score, correct_objectives_json,
            missed_objectives_json, misconception_tags_json, feedback, created_at
        ) VALUES (?, ?, 'rapid', '{}', '', 3, 0, ?, '[\"rate\"]', '[]', '[]', 'ok', ?)""",
        (learner_id, case_id, score, _NOW),
    )
    return int(cursor.lastrowid)


def test_empty_legacy_namespace_is_not_claimable_and_registration_rolls_back(tmp_path) -> None:
    store, claims, auth = _services(tmp_path)
    guest_id = f"g_{'e' * 24}"
    owner = _create_account(store, "empty-target")

    summary = claims.summary(guest_id)
    assert summary["hasProgress"] is False
    assert summary["claimable"] is False
    with pytest.raises(GuestProgressClaimUnavailable):
        claims.claim(guest_id, owner)

    username = f"empty_claim_{uuid.uuid4().hex[:8]}"
    with pytest.raises(GuestProgressClaimUnavailable):
        auth.register(
            username,
            _PASSWORD,
            claim_guest_progress=True,
            guest_id=guest_id,
        )
    assert store.get_user_by_username(username) is None


def _insert_guided(
    conn,
    learner_id: str,
    event_key: str,
    *,
    score: float,
    case_id: str,
) -> int:
    cursor = conn.execute(
        """INSERT INTO guided_learning_events (
            learner_id, module_id, scene_id, interaction_id, concept,
            subskills_json, score, correct, attempts, assistance, hints_used,
            confidence, requested_evidence_level, effective_evidence_level,
            case_id, case_provenance, case_eligible, misconception_tags_json,
            event_key, receipt_json, created_at
        ) VALUES (?, 'guided-module', 'scene-1', 'interaction-1',
                  'atrial_fibrillation', '[\"identify\"]', ?, ?, 1,
                  'independent', 0, 3, 'independent_transfer',
                  'independent_transfer', ?, 'audited_real', 1, '[]', ?, '[]', ?)""",
        (learner_id, score, 1 if score >= 0.7 else 0, case_id, event_key, _NOW),
    )
    return int(cursor.lastrowid)


def _seed_every_mode(store: LearningStore, guest_id: str, user_id: str) -> dict[str, int]:
    store.ensure_profile(guest_id, "Guest learner")
    store.update_learning_preferences(guest_id, {"guidanceLevel": "minimal"})
    with store.connect() as conn:
        for owner, suffix in ((user_id, "account"), (guest_id, "guest")):
            conn.execute(
                "INSERT INTO learner_calendar_settings ("
                "learner_id, time_zone, week_starts_on, created_at, updated_at"
                ") VALUES (?, 'UTC', 0, ?, ?)",
                (owner, _NOW, _NOW),
            )
            conn.execute(
                "INSERT INTO study_calendar_items ("
                "item_id, learner_id, source, title, notes, scheduled_date, "
                "status, client_request_id, revision, created_at, updated_at"
                ") VALUES (?, ?, 'manual', ?, '', '2026-07-20', 'scheduled', ?, 1, ?, ?)",
                (
                    str(uuid.uuid5(uuid.NAMESPACE_URL, f"calendar-{owner}")),
                    owner,
                    f"{suffix.title()} study block",
                    f"calendar-{suffix}",
                    _NOW,
                    _NOW,
                ),
            )
        conn.execute(
            "UPDATE objective_mastery SET mastery=.70, attempts=2, correct=1, "
            "high_confidence_wrong=0, last_practiced_at=? "
            "WHERE learner_id=? AND objective='rate'",
            (_NOW, user_id),
        )
        conn.execute(
            "UPDATE objective_mastery SET mastery=.50, attempts=3, correct=2, "
            "high_confidence_wrong=1, last_practiced_at=? "
            "WHERE learner_id=? AND objective='rate'",
            (_LATER, guest_id),
        )
        account_attempt = _insert_attempt(conn, user_id, "account-case")
        guest_attempt = _insert_attempt(conn, guest_id, "guest-case")

        conn.execute(
            """INSERT INTO subskill_mastery (
                learner_id, concept, subskill, formative_score,
                independent_mastery, attempts, independent_attempts, correct,
                high_confidence_wrong, last_practiced_at, next_due_at,
                stability_days, lapses, spaced_retrievals
            ) VALUES (?, 'atrial_fibrillation', 'identify', .8, .7, 2, 1, 1, 0,
                      ?, '2026-07-20T00:00:00+00:00', 4, 0, 1)""",
            (user_id, _NOW),
        )
        conn.execute(
            """INSERT INTO subskill_mastery (
                learner_id, concept, subskill, formative_score,
                independent_mastery, attempts, independent_attempts, correct,
                high_confidence_wrong, last_practiced_at, next_due_at,
                stability_days, lapses, spaced_retrievals
            ) VALUES (?, 'atrial_fibrillation', 'identify', .4, .9, 3, 2, 2, 1,
                      ?, '2026-07-18T00:00:00+00:00', 6, 1, 2)""",
            (guest_id, _LATER),
        )

        account_identical = _insert_guided(
            conn, user_id, "same-event", score=1.0, case_id="same-case"
        )
        guest_identical = _insert_guided(
            conn, guest_id, "same-event", score=1.0, case_id="same-case"
        )
        _insert_guided(
            conn, user_id, "colliding-event", score=1.0, case_id="account-guided"
        )
        guest_distinct = _insert_guided(
            conn, guest_id, "colliding-event", score=0.2, case_id="guest-guided"
        )
        for event_id, owner, case_id in (
            (account_identical, user_id, "same-case"),
            (guest_identical, guest_id, "same-case"),
            (guest_distinct, guest_id, "guest-guided"),
        ):
            conn.execute(
                """INSERT INTO subskill_retention_events (
                    guided_event_id, learner_id, concept, subskill, case_id,
                    mode, morphology_key, correct, occurred_at
                ) VALUES (?, ?, 'atrial_fibrillation', 'identify', ?,
                          'guided-module', ?, 1, ?)""",
                (event_id, owner, case_id, f"morph-{case_id}", _NOW),
            )

        conn.execute(
            """INSERT INTO pathway_progress (
                learner_id, pathway_id, module_id, scene_id, status,
                active_interaction_index, completed_action_ids_json, state_json,
                source, created_at, updated_at
            ) VALUES (?, 'guided', 'module-1', 'scene-1', 'attempted', 1,
                      '[\"account-action\"]',
                      '{\"shared\":\"account\",\"accountOnly\":true}',
                      'server', ?, ?)""",
            (user_id, _NOW, _NOW),
        )
        conn.execute(
            """INSERT INTO pathway_progress (
                learner_id, pathway_id, module_id, scene_id, status,
                active_interaction_index, completed_action_ids_json, state_json,
                source, created_at, updated_at
            ) VALUES (?, 'guided', 'module-1', 'scene-1', 'complete', 3,
                      '[\"guest-action\",\"account-action\"]',
                      '{\"shared\":\"guest\",\"guestOnly\":true}',
                      'server', ?, ?)""",
            (guest_id, _NOW, _LATER),
        )

        conn.execute(
            "INSERT INTO tutor_threads "
            "(thread_id, learner_id, mode, lesson_id, case_id, scope_key, title, created_at, updated_at) "
            "VALUES ('guest-thread', ?, 'freeform', NULL, NULL, NULL, 'Guest help', ?, ?)",
            (guest_id, _NOW, _NOW),
        )
        conn.execute(
            "INSERT INTO tutor_messages (thread_id, role, content, created_at) "
            "VALUES ('guest-thread', 'user', 'Explain this rhythm', ?)",
            (_NOW,),
        )

        for session_id, owner in (("review-account", user_id), ("review-guest", guest_id)):
            conn.execute(
                """INSERT INTO review_sessions (
                    session_id, learner_id, label, objectives_json, target_mastery,
                    max_cases, served_json, status, created_at, updated_at
                ) VALUES (?, ?, 'Review', '[\"rate\"]', .8, 10, '[]', 'active', ?, ?)""",
                (session_id, owner, _NOW, _LATER if owner == guest_id else _NOW),
            )

        for round_id, owner, pending in (
            ("rapid-account", user_id, "account-pending"),
            ("rapid-guest", guest_id, "guest-pending"),
        ):
            conn.execute(
                """INSERT INTO rapid_rounds (
                    round_id, learner_id, pace, length, assessment_scope,
                    context_key, exclusions_json, served_json, pending_case_id,
                    pending_started_at, pending_deadline_at, position, status,
                    created_at, updated_at
                ) VALUES (?, ?, 'ward', 5, 'broad', '', '[]', '[]', ?, ?, ?, 0,
                          'active', ?, ?)""",
                (round_id, owner, pending, _NOW, _LATER, _NOW, _LATER if owner == guest_id else _NOW),
            )
        conn.execute(
            """INSERT INTO rapid_round_answers (
                round_id, case_id, response_json, grade_json, tutor_json,
                result_json, receipts_json, integrity_status, attempt_id, created_at
            ) VALUES ('rapid-guest', 'answered-rapid', '{}', '{}', '{}', '{}',
                      '[]', 'legacy_incomplete', ?, ?)""",
            (guest_attempt, _NOW),
        )

        for session_id, owner, pending in (
            ("clinical-account", user_id, "account-item"),
            ("clinical-guest", guest_id, "guest-item"),
        ):
            conn.execute(
                """INSERT INTO clinical_shift_sessions (
                    session_id, learner_id, lane, tier, length, requested_length,
                    available_length, served_json, served_ecgs_json,
                    calibration_json, pending_item_id, pending_orient_started_at,
                    pending_orient_deadline_at, position, status, created_at,
                    updated_at
                ) VALUES (?, ?, 'ward', 'student', 5, 5, 5, '[]', '[]', '[]',
                          ?, ?, ?, 0, 'active', ?, ?)""",
                (session_id, owner, pending, _NOW, _LATER, _NOW, _LATER if owner == guest_id else _NOW),
            )
        conn.execute(
            """INSERT INTO clinical_shift_answers (
                session_id, item_id, ecg_id, response_json, grade_json,
                receipts_json, score, correct, attempt_id, created_at
            ) VALUES ('clinical-guest', 'old-item', 'ecg-old', '{}', '{}', '[]',
                      .9, 1, ?, ?)""",
            (guest_attempt, _NOW),
        )

        for campaign_id, owner, pending in (
            ("training-account", user_id, "account-training"),
            ("training-guest", guest_id, "guest-training"),
        ):
            conn.execute(
                """INSERT INTO training_campaigns (
                    campaign_id, learner_id, concept_id, subskill,
                    requested_length, length, pool_count, phases_json,
                    phase_counts_json, position, pending_case_id, status,
                    context_key, created_at, updated_at
                ) VALUES (?, ?, 'atrial_fibrillation', 'identify', 5, 5, 12,
                          '[\"recognize\"]', '{\"recognize\":5}', 0, ?, 'active',
                          '', ?, ?)""",
                (campaign_id, owner, pending, _NOW, _LATER if owner == guest_id else _NOW),
            )
        conn.execute(
            """INSERT INTO training_campaign_slots (
                campaign_id, ordinal, phase, case_id, case_focus,
                target_present, status
            ) VALUES ('training-guest', 0, 'recognize', 'training-old', 'target', 1,
                      'answered')"""
        )
        conn.execute(
            """INSERT INTO training_campaign_answers (
                campaign_id, ordinal, case_id, response_json, grade_json,
                tutor_json, receipt_json, summary_json, attempt_id, created_at
            ) VALUES ('training-guest', 0, 'training-old', '{}', '{}', '{}', '[]',
                      '{}', ?, ?)""",
            (guest_attempt, _NOW),
        )
    return {"accountAttempt": account_attempt, "guestAttempt": guest_attempt}


_GUEST_DIRECT_TABLES = (
    "learner_preferences",
    "learner_calendar_settings",
    "study_calendar_items",
    "subskill_retention_events",
    "guided_learning_events",
    "objective_mastery",
    "subskill_mastery",
    "attempts",
    "pathway_progress",
    "tutor_threads",
    "review_sessions",
    "rapid_rounds",
    "clinical_shift_sessions",
    "training_campaigns",
    "learner_profiles",
)


def _seed_account_child_ledgers(store: LearningStore, user_id: str, attempt_id: int) -> None:
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO tutor_threads "
            "(thread_id, learner_id, mode, lesson_id, case_id, scope_key, title, created_at, updated_at) "
            "VALUES ('account-thread', ?, 'freeform', NULL, NULL, NULL, 'Account help', ?, ?)",
            (user_id, _NOW, _NOW),
        )
        conn.execute(
            "INSERT INTO tutor_messages (thread_id, role, content, created_at) "
            "VALUES ('account-thread', 'user', 'Keep this message', ?)",
            (_NOW,),
        )
        conn.execute(
            """INSERT INTO rapid_round_answers (
                round_id, case_id, response_json, grade_json, tutor_json,
                result_json, receipts_json, integrity_status, attempt_id, created_at
            ) VALUES ('rapid-account', 'account-answer', '{}', '{}', '{}', '{}',
                      '[]', 'legacy_incomplete', ?, ?)""",
            (attempt_id, _NOW),
        )
        conn.execute(
            """INSERT INTO clinical_shift_answers (
                session_id, item_id, ecg_id, response_json, grade_json,
                receipts_json, score, correct, attempt_id, created_at
            ) VALUES ('clinical-account', 'account-item-old', 'account-ecg', '{}', '{}',
                      '[]', .8, 1, ?, ?)""",
            (attempt_id, _NOW),
        )
        conn.execute(
            """INSERT INTO training_campaign_slots (
                campaign_id, ordinal, phase, case_id, case_focus,
                target_present, status
            ) VALUES ('training-account', 0, 'recognize', 'account-training-old',
                      'target', 1, 'answered')"""
        )
        conn.execute(
            """INSERT INTO training_campaign_answers (
                campaign_id, ordinal, case_id, response_json, grade_json,
                tutor_json, receipt_json, summary_json, attempt_id, created_at
            ) VALUES ('training-account', 0, 'account-training-old', '{}', '{}', '{}',
                      '[]', '{}', ?, ?)""",
            (attempt_id, _NOW),
        )


def _guest_record_counts(store: LearningStore, guest_id: str) -> dict[str, int]:
    with store.connect() as conn:
        counts = {
            table: int(
                conn.execute(
                    f"SELECT COUNT(*) AS n FROM {table} WHERE learner_id = ?",
                    (guest_id,),
                ).fetchone()["n"]
            )
            for table in _GUEST_DIRECT_TABLES
        }
        counts.update(
            {
                "tutor_messages": int(conn.execute(
                    "SELECT COUNT(*) AS n FROM tutor_messages WHERE thread_id='guest-thread'"
                ).fetchone()["n"]),
                "rapid_round_answers": int(conn.execute(
                    "SELECT COUNT(*) AS n FROM rapid_round_answers WHERE round_id='rapid-guest'"
                ).fetchone()["n"]),
                "clinical_shift_answers": int(conn.execute(
                    "SELECT COUNT(*) AS n FROM clinical_shift_answers WHERE session_id='clinical-guest'"
                ).fetchone()["n"]),
                "training_campaign_slots": int(conn.execute(
                    "SELECT COUNT(*) AS n FROM training_campaign_slots WHERE campaign_id='training-guest'"
                ).fetchone()["n"]),
                "training_campaign_answers": int(conn.execute(
                    "SELECT COUNT(*) AS n FROM training_campaign_answers WHERE campaign_id='training-guest'"
                ).fetchone()["n"]),
            }
        )
    return counts


def test_guest_record_delete_covers_every_owner_table_without_cross_owner_loss(tmp_path) -> None:
    store, claims, _ = _services(tmp_path)
    guest_id = f"g_{'d' * 24}"
    user_id = _create_account(store, "delete-owner")
    ids = _seed_every_mode(store, guest_id, user_id)
    _seed_account_child_ledgers(store, user_id, ids["accountAttempt"])

    with store.connect() as conn:
        # Any future learner-owned table must be added to the atomic deletion
        # contract and this explicit test ledger in the same change.
        learner_owned_tables = {
            str(row["name"])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            if any(
                str(column["name"]) == "learner_id"
                for column in conn.execute(f"PRAGMA table_info({row['name']})").fetchall()
            )
        }
    assert learner_owned_tables == set(_GUEST_DIRECT_TABLES)
    assert all(count > 0 for count in _guest_record_counts(store, guest_id).values())

    deleted = claims.delete(guest_id)
    assert deleted > 0
    assert set(_guest_record_counts(store, guest_id).values()) == {0}

    with store.connect() as conn:
        for table in _GUEST_DIRECT_TABLES:
            assert conn.execute(
                f"SELECT COUNT(*) AS n FROM {table} WHERE learner_id = ?", (user_id,)
            ).fetchone()["n"] > 0
        for table, predicate in (
            ("tutor_messages", "thread_id='account-thread'"),
            ("rapid_round_answers", "round_id='rapid-account'"),
            ("clinical_shift_answers", "session_id='clinical-account'"),
            ("training_campaign_slots", "campaign_id='training-account'"),
            ("training_campaign_answers", "campaign_id='training-account'"),
        ):
            assert conn.execute(
                f"SELECT COUNT(*) AS n FROM {table} WHERE {predicate}"
            ).fetchone()["n"] > 0


def test_guest_record_delete_rolls_back_every_table_after_injected_failure(tmp_path) -> None:
    store, _, _ = _services(tmp_path)
    guest_id = f"g_{'r' * 24}"
    user_id = _create_account(store, "delete-rollback")
    _seed_every_mode(store, guest_id, user_id)
    before = _guest_record_counts(store, guest_id)

    def fail_after_deletes(_conn) -> None:
        raise RuntimeError("injected guest deletion failure")

    with pytest.raises(RuntimeError, match="injected guest deletion failure"):
        store.delete_guest_learning_record(guest_id, _failure_hook=fail_after_deletes)
    assert _guest_record_counts(store, guest_id) == before


def test_guest_delete_api_retires_identity_for_anonymous_or_authenticated_browser(
    tmp_path, monkeypatch
) -> None:
    store, claims, auth = _services(tmp_path)
    monkeypatch.setattr(main_module, "guest_progress_service", claims)
    monkeypatch.setattr(main_module, "auth_service", auth)

    store.ensure_profile("demo", "Guest learner")
    with store.connect() as conn:
        _insert_attempt(conn, "demo", "delete-api-guest")

    old_guest_cookie = f"g_{'o' * 24}"
    with TestClient(app) as client:
        client.cookies.set(
            "ecg_guest", old_guest_cookie, domain="testserver.local", path="/"
        )
        deleted = client.delete("/auth/guest-progress")
        assert deleted.status_code == 200, deleted.text
        assert deleted.json()["ok"] is True
        assert deleted.json()["deletedRecords"] > 0
        assert client.cookies.get("ecg_guest") is None
        cookie_header = deleted.headers.get("set-cookie", "").lower()
        assert "ecg_guest=" in cookie_header
        assert "max-age=0" in cookie_header
        assert "httponly" in cookie_header
        assert "samesite=lax" in cookie_header
        assert claims.summary("demo")["hasProgress"] is False

    store.ensure_profile("demo", "Guest learner")
    with store.connect() as conn:
        _insert_attempt(conn, "demo", "must-survive-account-rejection")

    with TestClient(app) as account_client:
        account_client.cookies.set(
            "ecg_guest", old_guest_cookie, domain="testserver.local", path="/"
        )
        username = f"guest_delete_{uuid.uuid4().hex[:8]}"
        registered = account_client.post(
            "/auth/register",
            json={"username": username, "password": _PASSWORD},
        )
        assert registered.status_code == 200, registered.text
        discarded = account_client.delete("/auth/guest-progress")
        assert discarded.status_code == 200
        assert discarded.json()["ok"] is True
        assert account_client.cookies.get("ecg_guest") is None
        assert claims.summary("demo")["attempts"] == 0


def test_claim_merges_existing_account_without_downgrading_or_pk_collisions(tmp_path) -> None:
    store, claims, _ = _services(tmp_path)
    guest_id = f"g_{'a' * 24}"
    user_id = _create_account(store, "existing")
    ids = _seed_every_mode(store, guest_id, user_id)
    with store.connect() as conn:
        create_lease(
            conn,
            lease_id="lease-training-guest",
            owner_id=guest_id,
            mode="training",
            session_id="training-guest",
            ecg_ids=["guest-training"],
            created_at=_NOW,
            expires_at=_LATER,
        )
        append_event(
            conn,
            event_id="presented-training-guest",
            owner_id=guest_id,
            mode="training",
            session_id="training-guest",
            lease_id="lease-training-guest",
            ecg_id="guest-training",
            event_type="item_presented",
            evidence_level="formative",
            integrity_status="atomic_v2",
            occurred_at=_NOW,
        )

    receipt = claims.claim(guest_id, user_id)
    assert receipt["claimed"] is True
    assert receipt["replay"] is False
    assert receipt["guestProgress"]["hasProgress"] is True

    with store.connect() as conn:
        objective = conn.execute(
            "SELECT * FROM objective_mastery WHERE learner_id=? AND objective='rate'",
            (user_id,),
        ).fetchone()
        assert objective["mastery"] == pytest.approx(.70)
        assert (objective["attempts"], objective["correct"], objective["high_confidence_wrong"]) == (5, 3, 1)
        assert objective["last_practiced_at"] == _LATER

        subskill = conn.execute(
            "SELECT * FROM subskill_mastery WHERE learner_id=? AND concept='atrial_fibrillation' AND subskill='identify'",
            (user_id,),
        ).fetchone()
        assert subskill["formative_score"] == pytest.approx(.8)
        assert subskill["independent_mastery"] == pytest.approx(.9)
        assert subskill["attempts"] == 5
        assert subskill["distinct_eligible_ecgs"] == 2

        pathway = conn.execute(
            "SELECT * FROM pathway_progress WHERE learner_id=? AND pathway_id='guided'",
            (user_id,),
        ).fetchone()
        assert pathway["status"] == "complete"
        assert pathway["active_interaction_index"] == 3
        assert json.loads(pathway["completed_action_ids_json"]) == ["account-action", "guest-action"]
        state = json.loads(pathway["state_json"])
        assert state == {"shared": "account", "accountOnly": True, "guestOnly": True}

        # Cross-owner key collisions never delete evidence: deterministic
        # fallback keys can match for two genuine completions of the same task.
        guided_keys = conn.execute(
            "SELECT event_key FROM guided_learning_events WHERE learner_id=?",
            (user_id,),
        ).fetchall()
        assert len(guided_keys) == 4
        assert {row["event_key"] for row in guided_keys} >= {"same-event", "colliding-event"}
        assert sum(row["event_key"].startswith("guest-claim:") for row in guided_keys) == 2

        direct_tables = (
            "attempts", "guided_learning_events", "subskill_retention_events",
            "pathway_progress", "tutor_threads", "review_sessions", "rapid_rounds",
            "clinical_shift_sessions", "training_campaigns",
        )
        for table in direct_tables:
            assert conn.execute(
                f"SELECT COUNT(*) AS n FROM {table} WHERE learner_id=?", (guest_id,)
            ).fetchone()["n"] == 0
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM attempts WHERE learner_id=?", (user_id,)
        ).fetchone()["n"] == 2
        assert conn.execute(
            "SELECT learner_id FROM attempts WHERE id=?", (ids["guestAttempt"],)
        ).fetchone()["learner_id"] == user_id
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM tutor_messages WHERE thread_id='guest-thread'"
        ).fetchone()["n"] == 1
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM rapid_round_answers WHERE round_id='rapid-guest'"
        ).fetchone()["n"] == 1
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM clinical_shift_answers WHERE session_id='clinical-guest'"
        ).fetchone()["n"] == 1
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM training_campaign_answers WHERE campaign_id='training-guest'"
        ).fetchone()["n"] == 1

        for table, resumable in (
            ("review_sessions", "status='active'"),
            ("rapid_rounds", "status='active' OR feedback_case_id IS NOT NULL"),
            ("clinical_shift_sessions", "status='active' OR feedback_item_id IS NOT NULL"),
            ("training_campaigns", "status='active' OR feedback_case_id IS NOT NULL"),
        ):
            assert conn.execute(
                f"SELECT COUNT(*) AS n FROM {table} WHERE learner_id=? AND ({resumable})",
                (user_id,),
            ).fetchone()["n"] == 1
        assert conn.execute(
            "SELECT status, pending_case_id, pending_started_at FROM rapid_rounds WHERE round_id='rapid-guest'"
        ).fetchone()[:] == ("abandoned", None, None)
        assert conn.execute(
            "SELECT status, pending_item_id, pending_orient_started_at FROM clinical_shift_sessions WHERE session_id='clinical-guest'"
        ).fetchone()[:] == ("abandoned", None, None)
        assert conn.execute(
            "SELECT status, pending_case_id FROM training_campaigns WHERE campaign_id='training-guest'"
        ).fetchone()[:] == ("abandoned", None)
        abandoned_lease = conn.execute(
            "SELECT owner_id, state FROM assessment_leases WHERE lease_id='lease-training-guest'"
        ).fetchone()
        assert tuple(abandoned_lease) == (user_id, "abandoned")
        terminal_event = conn.execute(
            "SELECT owner_id, event_type FROM learner_events WHERE lease_id='lease-training-guest' "
            "AND event_type='item_abandoned'"
        ).fetchone()
        assert tuple(terminal_event) == (user_id, "item_abandoned")
        assert conn.execute(
            "SELECT 1 FROM learner_profiles WHERE learner_id=?", (guest_id,)
        ).fetchone() is None


def test_claim_is_idempotent_and_cannot_cross_accounts(tmp_path) -> None:
    store, claims, _ = _services(tmp_path)
    guest_id = f"g_{'b' * 24}"
    first_user = _create_account(store, "first")
    second_user = _create_account(store, "second")
    store.ensure_profile(guest_id, "Guest")
    with store.connect() as conn:
        attempt_id = _insert_attempt(conn, guest_id, "isolated-case")

    first = claims.claim(guest_id, first_user)
    replay = claims.claim(guest_id, first_user)
    assert first["replay"] is False
    assert replay["replay"] is True
    assert replay["claimedAt"] == first["claimedAt"]
    with store.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM attempts WHERE id=? AND learner_id=?",
            (attempt_id, first_user),
        ).fetchone()["n"] == 1

    with pytest.raises(GuestProgressClaimConflict):
        claims.claim(guest_id, second_user)
    with store.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM attempts WHERE learner_id=?", (second_user,)
        ).fetchone()["n"] == 0
        marker = conn.execute(
            "SELECT user_id FROM guest_progress_claims WHERE guest_learner_id=?",
            (guest_id,),
        ).fetchone()
        assert marker["user_id"] == first_user


def test_guest_only_active_sessions_resume_without_losing_pending_state(tmp_path) -> None:
    store, claims, _ = _services(tmp_path)
    guest_id = f"g_{'d' * 24}"
    user_id = _create_account(store, "resume")
    _seed_every_mode(store, guest_id, user_id)
    with store.connect() as conn:
        conn.execute("DELETE FROM review_sessions WHERE session_id='review-account'")
        conn.execute("DELETE FROM rapid_rounds WHERE round_id='rapid-account'")
        conn.execute("DELETE FROM clinical_shift_sessions WHERE session_id='clinical-account'")
        conn.execute("DELETE FROM training_campaigns WHERE campaign_id='training-account'")

    claims.claim(guest_id, user_id)
    with store.connect() as conn:
        review = conn.execute(
            "SELECT learner_id, status FROM review_sessions WHERE session_id='review-guest'"
        ).fetchone()
        rapid = conn.execute(
            "SELECT learner_id, status, pending_case_id, pending_started_at, pending_deadline_at "
            "FROM rapid_rounds WHERE round_id='rapid-guest'"
        ).fetchone()
        clinical = conn.execute(
            "SELECT learner_id, status, pending_item_id, pending_orient_started_at, "
            "pending_orient_deadline_at FROM clinical_shift_sessions "
            "WHERE session_id='clinical-guest'"
        ).fetchone()
        training = conn.execute(
            "SELECT learner_id, status, pending_case_id, abandoned_at "
            "FROM training_campaigns WHERE campaign_id='training-guest'"
        ).fetchone()
    assert tuple(review) == (user_id, "active")
    assert tuple(rapid) == (user_id, "active", "guest-pending", _NOW, _LATER)
    assert tuple(clinical) == (user_id, "active", "guest-item", _NOW, _LATER)
    assert tuple(training) == (user_id, "active", "guest-training", None)


def test_competing_claims_are_serialized_to_one_account(tmp_path) -> None:
    store, claims, _ = _services(tmp_path)
    guest_id = f"g_{'e' * 24}"
    users = [_create_account(store, "race-one"), _create_account(store, "race-two")]
    store.ensure_profile(guest_id, "Guest")
    with store.connect() as conn:
        attempt_id = _insert_attempt(conn, guest_id, "race-case")

    def try_claim(user_id: str) -> tuple[str, str]:
        try:
            claims.claim(guest_id, user_id)
            return user_id, "claimed"
        except GuestProgressClaimConflict:
            return user_id, "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(try_claim, users))
    assert sorted(outcome for _, outcome in outcomes) == ["claimed", "conflict"]
    winner = next(user_id for user_id, outcome in outcomes if outcome == "claimed")
    loser = next(user_id for user_id, outcome in outcomes if outcome == "conflict")
    with store.connect() as conn:
        assert conn.execute(
            "SELECT learner_id FROM attempts WHERE id=?", (attempt_id,)
        ).fetchone()["learner_id"] == winner
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM attempts WHERE learner_id=?", (loser,)
        ).fetchone()["n"] == 0


def test_mid_claim_failure_rolls_back_all_ownership_changes(tmp_path, monkeypatch) -> None:
    store, claims, _ = _services(tmp_path)
    guest_id = f"g_{'f' * 24}"
    user_id = _create_account(store, "rollback")
    store.ensure_profile(guest_id, "Guest")
    with store.connect() as conn:
        attempt_id = _insert_attempt(conn, guest_id, "rollback-case")
        conn.execute(
            "UPDATE objective_mastery SET mastery=.9, attempts=4 "
            "WHERE learner_id=? AND objective='rate'",
            (guest_id,),
        )

    def fail_after_mastery(*_args, **_kwargs):
        raise RuntimeError("injected claim failure")

    monkeypatch.setattr(claims, "_merge_pathway_progress", fail_after_mastery)
    with pytest.raises(RuntimeError, match="injected claim failure"):
        claims.claim(guest_id, user_id)

    with store.connect() as conn:
        assert conn.execute(
            "SELECT learner_id FROM attempts WHERE id=?", (attempt_id,)
        ).fetchone()["learner_id"] == guest_id
        assert conn.execute(
            "SELECT mastery, attempts FROM objective_mastery "
            "WHERE learner_id=? AND objective='rate'",
            (guest_id,),
        ).fetchone()[:] == (.9, 4)
        assert conn.execute(
            "SELECT 1 FROM guest_progress_claims WHERE guest_learner_id=?", (guest_id,)
        ).fetchone() is None


def test_registration_claim_conflict_rolls_back_new_account(tmp_path) -> None:
    store, claims, auth = _services(tmp_path)
    guest_id = f"g_{'c' * 24}"
    owner = _create_account(store, "owner")
    store.ensure_profile(guest_id, "Guest")
    with store.connect() as conn:
        _insert_attempt(conn, guest_id, "claimed-case")
    claims.claim(guest_id, owner)

    blocked_username = f"blocked_{uuid.uuid4().hex[:8]}"
    with pytest.raises(GuestProgressClaimConflict):
        auth.register(
            blocked_username,
            _PASSWORD,
            claim_guest_progress=True,
            guest_id=guest_id,
        )
    assert store.get_user_by_username(blocked_username) is None


def test_auth_api_only_claims_when_explicit_and_retires_guest_cookie(tmp_path, monkeypatch) -> None:
    store, claims, auth = _services(tmp_path)
    store.ensure_profile("demo", "Guest")
    with store.connect() as conn:
        _insert_attempt(conn, "demo", "api-guest-case")
    monkeypatch.setattr(main_module, "guest_progress_service", claims)
    monkeypatch.setattr(main_module, "auth_service", auth)

    username = f"claimapi_{uuid.uuid4().hex[:8]}"
    with TestClient(app) as client:
        summary = client.get("/auth/guest-progress")
        assert summary.status_code == 200
        assert summary.json()["hasProgress"] is True
        assert summary.json()["attempts"] == 1

        registered = client.post(
            "/auth/register",
            json={"username": username, "password": _PASSWORD},
        )
        assert registered.status_code == 200, registered.text
        user_id = registered.json()["user"]["userId"]
        assert registered.json()["guestClaim"] is None
        with store.connect() as conn:
            assert conn.execute(
                "SELECT COUNT(*) AS n FROM attempts WHERE learner_id='demo'"
            ).fetchone()["n"] == 1

        client.post("/auth/logout")
        claimed = client.post(
            "/auth/login",
            json={
                "username": username,
                "password": _PASSWORD,
                "claimGuestProgress": True,
            },
        )
        assert claimed.status_code == 200, claimed.text
        assert claimed.json()["guestClaim"]["claimed"] is True
        assert claimed.json()["guestClaim"]["replay"] is False
        cookie_header = claimed.headers.get("set-cookie", "").lower()
        assert "ecg_guest=" in cookie_header
        assert "max-age=0" in cookie_header
        assert "httponly" in cookie_header
        with store.connect() as conn:
            assert conn.execute(
                "SELECT COUNT(*) AS n FROM attempts WHERE learner_id=?", (user_id,)
            ).fetchone()["n"] == 1
            assert conn.execute(
                "SELECT COUNT(*) AS n FROM attempts WHERE learner_id='demo'"
            ).fetchone()["n"] == 0
