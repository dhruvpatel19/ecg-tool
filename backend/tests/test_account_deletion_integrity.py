from __future__ import annotations

import asyncio
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from app.account_boundary import (
    AccountGenerationRetiredError,
    CHILD_OWNER_TABLES,
    DIRECT_OWNER_TABLES,
    OwnerParentMissingError,
    expected_guard_triggers,
)
from app.clinical.integrity import claim_pending_item, create_session as create_clinical_session
from app.guest_progress import GuestProgressService
from app.rapid_assessment import RapidAssessmentStore
from app.storage import LEARNER_SCHEMA_VERSION, LearningStore
from app.training_store import TrainingCampaignStore


_PASSWORD_HASH = "test-password-hash"


def _account_graph(tmp_path, suffix: str):
    database = tmp_path / f"retired-generation-{suffix}.sqlite3"
    store = LearningStore(database)
    campaigns = TrainingCampaignStore(database, store.connect)
    GuestProgressService(store)
    user_id = f"u_{uuid.uuid4().hex}"
    store.create_user(
        user_id,
        f"student_{uuid.uuid4().hex[:12]}",
        "Deletion race student",
        _PASSWORD_HASH,
    )
    return store, campaigns, user_id


def _training_plan(case_id: str = "ptb-training-late") -> list[dict]:
    return [
        {
            "caseId": case_id,
            "caseFocus": "atrial_fibrillation",
            "targetPresent": True,
            "phase": "target",
        }
    ]


def _guided_event(event_key: str) -> dict:
    return {
        "moduleId": "rhythm-ectopy",
        "sceneId": "scene-1",
        "interactionId": "identify-af",
        "concept": "atrial_fibrillation",
        "subskills": ["recognize"],
        "score": 0.8,
        "correct": True,
        "attempts": 1,
        "assistance": "independent",
        "hintsUsed": 0,
        "confidence": 3,
        "evidenceLevel": "guided",
        "caseId": "ptb-guided-late",
        "caseProvenance": "real_eligible",
        "caseEligible": True,
        "misconceptions": [],
        "eventKey": event_key,
    }


def _attempt_grade() -> dict:
    return {
        "score": 0.5,
        "correctObjectives": [],
        "missedObjectives": [],
        "misconceptions": [],
        "feedback": "late attempt",
        "masteryDelta": {},
    }


def _assert_zero_owner_rows(store: LearningStore, user_id: str) -> None:
    """Assert the complete fresh test database has no surviving owner graph."""

    with store.connect() as conn:
        for table, owner_column in DIRECT_OWNER_TABLES.items():
            if not store._table_exists(conn, table):
                continue
            count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {owner_column} = ?",
                (user_id,),
            ).fetchone()[0]
            assert count == 0, table
        # This test database has only one account. Any child row is therefore
        # either that account's residue or an orphan created by the late write.
        for table in CHILD_OWNER_TABLES:
            if store._table_exists(conn, table):
                assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table


def _run_after_delete(store: LearningStore, user_id: str, action):
    """Pause a pre-authorized request until the deletion transaction commits."""

    blocked = threading.Event()
    resume = threading.Event()

    def stale_request():
        blocked.set()
        assert resume.wait(timeout=10)
        return action()

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(stale_request)
        assert blocked.wait(timeout=10)
        assert store.delete_user_account(user_id, _PASSWORD_HASH) is True
        resume.set()
        return future


@pytest.mark.parametrize(
    "write_kind",
    [
        "profile",
        "attempt",
        "pathway",
        "training",
        "rapid",
        "clinical",
        "tutor",
        "activity",
        "auth",
    ],
)
def test_deletion_wins_before_blocked_owner_graph_creation(
    tmp_path, write_kind: str
) -> None:
    """A stale request cannot recreate any representative account-owned row."""

    store, campaigns, user_id = _account_graph(tmp_path, write_kind)
    rapid = RapidAssessmentStore(store)

    def late_write():
        if write_kind == "profile":
            return store.ensure_profile(user_id, "Should not return")
        if write_kind == "attempt":
            return store.save_attempt(
                user_id,
                "ptb-attempt-late",
                "concept_practice",
                {},
                "late",
                3,
                0,
                _attempt_grade(),
            )
        if write_kind == "pathway":
            return store.upsert_pathway_progress(
                user_id,
                [
                    {
                        "pathwayId": "production-curriculum",
                        "moduleId": "rhythm-ectopy",
                        "sceneId": "M03.S01",
                        "status": "attempted",
                        "activeInteractionIndex": 1,
                        "completedActionIds": ["late-action"],
                        "state": {},
                    }
                ],
            )
        if write_kind == "training":
            return campaigns.create_campaign(
                user_id,
                "atrial_fibrillation",
                "recognize",
                1,
                1,
                _training_plan(),
            )
        if write_kind == "rapid":
            return rapid.create_round(
                learner_id=user_id,
                pace="untimed",
                length=1,
                assessment_scope="mixed",
                deadline_seconds=None,
                focus_concept=None,
                focus_subskill=None,
                context_key="",
                exclusions=[],
            )
        if write_kind == "clinical":
            return create_clinical_session(
                store,
                learner_id=user_id,
                lane="chest_pain",
                tier="core",
                length=1,
                focus_objective=None,
                focus_subskill=None,
            )
        if write_kind == "tutor":
            return store.ensure_thread(user_id, mode="freeform")
        if write_kind == "activity":
            return store.save_guided_learning_event(
                user_id, _guided_event(f"late-{uuid.uuid4().hex}")
            )
        if write_kind == "auth":
            return store.create_session(
                f"late-session-{uuid.uuid4().hex}",
                user_id,
                (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            )
        raise AssertionError(f"unhandled write kind: {write_kind}")

    future = _run_after_delete(store, user_id, late_write)
    with pytest.raises(AccountGenerationRetiredError, match="account was deleted"):
        future.result(timeout=10)
    _assert_zero_owner_rows(store, user_id)


@pytest.mark.parametrize("write_kind", ["training", "rapid", "clinical", "tutor"])
def test_deletion_wins_before_blocked_existing_mode_mutation(
    tmp_path, write_kind: str
) -> None:
    """A stale mode request cannot append children after its parent is purged."""

    store, campaigns, user_id = _account_graph(tmp_path, f"existing-{write_kind}")

    if write_kind == "training":
        campaign = campaigns.create_campaign(
            user_id,
            "atrial_fibrillation",
            "recognize",
            1,
            1,
            _training_plan("ptb-training-existing"),
        )
        action = lambda: campaigns.claim_next(campaign["campaignId"])
    elif write_kind == "rapid":
        rapid = RapidAssessmentStore(store)
        round_row = rapid.create_round(
            learner_id=user_id,
            pace="untimed",
            length=1,
            assessment_scope="mixed",
            deadline_seconds=None,
            focus_concept=None,
            focus_subskill=None,
            context_key="",
            exclusions=[],
        )
        action = lambda: rapid.freeze_pending(
            round_id=round_row["roundId"],
            learner_id=user_id,
            case_id="ptb-rapid-existing",
            tested_objective_manifest={},
        )
    elif write_kind == "clinical":
        session_id = create_clinical_session(
            store,
            learner_id=user_id,
            lane="chest_pain",
            tier="core",
            length=1,
            focus_objective=None,
            focus_subskill=None,
        )
        action = lambda: claim_pending_item(
            store,
            session_id=session_id,
            item_id="clinical-item-late",
            ecg_id="ptb-clinical-existing",
        )
    else:
        thread_id = store.ensure_thread(user_id, mode="freeform")
        action = lambda: store.append_tutor_message(
            thread_id,
            "user",
            "This message must not survive account deletion.",
        )

    future = _run_after_delete(store, user_id, action)
    if write_kind == "tutor":
        with pytest.raises(OwnerParentMissingError, match="parent no longer exists"):
            future.result(timeout=10)
    else:
        result = future.result(timeout=10)
        if write_kind in {"training", "rapid"}:
            assert result is None
        else:
            assert result == {"status": "missing"}
    _assert_zero_owner_rows(store, user_id)


def test_schema_v4_migrates_and_installs_complete_owner_guard_inventory(tmp_path) -> None:
    database = tmp_path / "owner-boundary-migration.sqlite3"
    original = LearningStore(database)
    TrainingCampaignStore(database, original.connect)
    GuestProgressService(original)
    with original.connect() as conn:
        conn.execute("PRAGMA user_version=3")
        conn.execute("DELETE FROM schema_migrations WHERE version = 4")
        triggers = [
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger' "
                "AND (name LIKE 'account_generation_guard_%' "
                "OR name LIKE 'account_owner_parent_guard_%')"
            ).fetchall()
        ]
        for trigger in triggers:
            conn.execute(f"DROP TRIGGER {trigger}")
        conn.execute("DROP TABLE account_tombstones")

    migrated = LearningStore(database)
    TrainingCampaignStore(database, migrated.connect)
    GuestProgressService(migrated)
    with migrated.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == LEARNER_SCHEMA_VERSION == 4
        actual_triggers = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            ).fetchall()
        }
        assert expected_guard_triggers(conn) <= actual_triggers

        discovered_direct: dict[str, str] = {}
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall():
            table = str(row[0])
            columns = {
                str(column[1]) for column in conn.execute(f"PRAGMA table_info({table})")
            }
            for owner_column in ("user_id", "learner_id", "owner_id"):
                if owner_column in columns:
                    discovered_direct[table] = owner_column
        assert discovered_direct == dict(DIRECT_OWNER_TABLES)


def test_tombstone_is_non_identifying_and_not_removed_by_retention(tmp_path) -> None:
    store, _campaigns, user_id = _account_graph(tmp_path, "privacy")
    assert store.delete_user_account(user_id, _PASSWORD_HASH) is True
    far_future = datetime.now(UTC) + timedelta(days=3650)
    store.cleanup_retention(
        now=far_future,
        guest_inactivity_days=30,
        batch_size=100,
        unverified_account_expiry_days=7,
    )
    with store.connect() as conn:
        rows = conn.execute("SELECT * FROM account_tombstones").fetchall()
        assert len(rows) == 1
        record = dict(rows[0])
        assert set(record) == {
            "owner_key",
            "retired_at",
            "reason",
            "boundary_version",
        }
        assert len(record["owner_key"]) == 64
        assert user_id not in json.dumps(record)
        assert "student_" not in json.dumps(record)


def test_legacy_guest_erasure_does_not_retire_or_block_guest_namespace(tmp_path) -> None:
    store = LearningStore(tmp_path / "guest-generation.sqlite3")
    guest_id = f"g_{uuid.uuid4().hex[:28]}"
    store.ensure_profile(guest_id, "Legacy guest")
    assert store.delete_guest_learning_record(guest_id) > 0
    restored = store.ensure_profile(guest_id, "Returning legacy guest")
    assert restored["displayName"] == "Returning legacy guest"
    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM account_tombstones").fetchone()[0] == 0


def test_retired_generation_has_one_neutral_no_store_http_contract() -> None:
    from app.main import _account_unavailable_error, app

    assert app.exception_handlers[AccountGenerationRetiredError] is _account_unavailable_error
    assert app.exception_handlers[OwnerParentMissingError] is _account_unavailable_error
    response = asyncio.run(
        _account_unavailable_error(
            None,  # type: ignore[arg-type]
            AccountGenerationRetiredError("private trigger detail"),
        )
    )
    assert response.status_code == 409
    assert response.headers["cache-control"] == "no-store"
    payload = json.loads(response.body)
    assert payload == {
        "detail": {
            "code": "account_unavailable",
            "message": (
                "This account is no longer available. Sign in again or create a new account."
            ),
        }
    }
    assert "trigger" not in response.body.decode("utf-8")
