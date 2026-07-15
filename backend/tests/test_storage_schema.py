from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.ontology import DEFAULT_MASTERY
from app.storage import (
    LEARNER_SCHEMA_VERSION,
    LearningStore,
    SchemaCompatibilityError,
)


def test_new_database_records_versioned_schema_and_full_sync(tmp_path) -> None:
    database = tmp_path / "learner.sqlite3"

    store = LearningStore(database)

    with store.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == LEARNER_SCHEMA_VERSION
        migration = connection.execute(
            "SELECT version, description FROM schema_migrations"
        ).fetchone()
        assert migration["version"] == LEARNER_SCHEMA_VERSION
        assert "Versioned baseline" in migration["description"]
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert store.learning_record_integrity() == (True, "ready")


def test_learning_record_integrity_rejects_unknown_cells_and_unfinished_rapid_receipts(tmp_path) -> None:
    store = LearningStore(tmp_path / "integrity.sqlite3")
    with store.connect() as connection:
        connection.execute(
            "INSERT INTO subskill_mastery (learner_id, concept, subskill) "
            "VALUES ('learner', 'retired_unknown_objective', 'recognize')"
        )
    assert store.learning_record_integrity() == (False, "unknown_objective_registry_cell")

    with store.connect() as connection:
        connection.execute("DELETE FROM subskill_mastery")
        connection.execute(
            "INSERT INTO rapid_rounds "
            "(round_id, learner_id, pace, length, assessment_scope, created_at, updated_at) "
            "VALUES ('round', 'learner', 'untimed', 1, 'mixed', 'now', 'now')"
        )
        connection.execute(
            "INSERT INTO rapid_round_answers "
            "(round_id, case_id, response_json, grade_json, result_json, receipts_json, "
            "attempt_id, created_at) VALUES ('round', 'case', '{}', '{}', '{}', '[]', 1, 'now')"
        )
    assert store.learning_record_integrity() == (False, "rapid_answer_receipts_incomplete")

    with store.connect() as connection:
        connection.execute(
            "UPDATE rapid_round_answers SET integrity_status = 'legacy_incomplete'"
        )
    assert store.learning_record_integrity() == (True, "ready")


def test_concurrent_first_requests_create_one_complete_profile(tmp_path) -> None:
    store = LearningStore(tmp_path / "concurrent.sqlite3")
    learner_id = "simultaneous-first-login"
    workers = 12
    start = threading.Barrier(workers)

    def ensure() -> dict:
        start.wait()
        return store.ensure_profile(learner_id, "Concurrent Learner")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        profiles = list(executor.map(lambda _: ensure(), range(workers)))

    assert all(profile["learnerId"] == learner_id for profile in profiles)
    assert all(profile["displayName"] == "Concurrent Learner" for profile in profiles)
    assert all(len(profile["mastery"]) == len(DEFAULT_MASTERY) for profile in profiles)

    with store.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM learner_profiles WHERE learner_id = ?", (learner_id,)
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM objective_mastery WHERE learner_id = ?", (learner_id,)
        ).fetchone()[0] == len(DEFAULT_MASTERY)


def test_legacy_unversioned_database_is_baselined_after_additive_migration(tmp_path) -> None:
    database = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE learner_profiles ("
            "learner_id TEXT PRIMARY KEY, display_name TEXT NOT NULL, "
            "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO learner_profiles VALUES ('learner-1', 'Student', 'before', 'before')"
        )

    LearningStore(database)

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == LEARNER_SCHEMA_VERSION
        assert connection.execute(
            "SELECT display_name FROM learner_profiles WHERE learner_id = 'learner-1'"
        ).fetchone()[0] == "Student"
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_version_one_database_migrates_to_registry_versioned_schema(tmp_path) -> None:
    database = tmp_path / "version-one.sqlite3"
    original = LearningStore(database)
    with original.connect() as connection:
        connection.execute("PRAGMA user_version=1")
        connection.execute(
            "INSERT INTO learner_profiles VALUES ('v1-learner', 'V1 Learner', 'before', 'before')"
        )

    migrated = LearningStore(database)
    with migrated.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == LEARNER_SCHEMA_VERSION
        assert connection.execute(
            "SELECT display_name FROM learner_profiles WHERE learner_id = 'v1-learner'"
        ).fetchone()[0] == "V1 Learner"
        assert "registry_version" in {
            row["name"] for row in connection.execute("PRAGMA table_info(attempts)")
        }


def test_newer_schema_is_rejected_before_any_mutation(tmp_path) -> None:
    database = tmp_path / "future.sqlite3"
    future_version = LEARNER_SCHEMA_VERSION + 1
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE future_only (value TEXT NOT NULL)")
        connection.execute("INSERT INTO future_only VALUES ('preserve-me')")
        connection.execute(f"PRAGMA user_version={future_version}")

    with pytest.raises(SchemaCompatibilityError, match="newer than this binary"):
        LearningStore(database)

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == future_version
        assert connection.execute("SELECT value FROM future_only").fetchone()[0] == "preserve-me"
        assert connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'learner_profiles'"
        ).fetchone()[0] == 0
