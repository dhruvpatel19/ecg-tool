from __future__ import annotations

import json
import sqlite3

import pytest

from app.learning_activity import ActivityCursorError, get_learning_activity


SECRET = "activity-test-secret"


def _database() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE attempts (
            id INTEGER PRIMARY KEY,
            learner_id TEXT NOT NULL,
            mode TEXT NOT NULL,
            score REAL NOT NULL,
            confidence INTEGER NOT NULL,
            hints_used INTEGER NOT NULL,
            misconception_tags_json TEXT NOT NULL,
            structured_answer_json TEXT NOT NULL,
            free_text_answer TEXT NOT NULL,
            feedback TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE guided_learning_events (
            id INTEGER PRIMARY KEY,
            learner_id TEXT NOT NULL,
            module_id TEXT NOT NULL,
            score REAL NOT NULL,
            confidence INTEGER,
            assistance TEXT NOT NULL,
            correct INTEGER NOT NULL,
            concept TEXT NOT NULL,
            subskills_json TEXT NOT NULL,
            effective_evidence_level TEXT NOT NULL,
            misconception_tags_json TEXT NOT NULL,
            receipt_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE training_campaign_answers (
            id INTEGER PRIMARY KEY,
            attempt_id INTEGER NOT NULL,
            receipt_json TEXT NOT NULL,
            integrity_status TEXT NOT NULL,
            response_json TEXT NOT NULL,
            grade_json TEXT NOT NULL,
            tutor_json TEXT NOT NULL
        );
        CREATE TABLE rapid_round_answers (
            id INTEGER PRIMARY KEY,
            attempt_id INTEGER NOT NULL,
            receipts_json TEXT NOT NULL,
            integrity_status TEXT NOT NULL,
            response_json TEXT NOT NULL,
            grade_json TEXT NOT NULL,
            tested_manifest_json TEXT NOT NULL
        );
        CREATE TABLE clinical_shift_answers (
            id INTEGER PRIMARY KEY,
            attempt_id INTEGER NOT NULL,
            receipts_json TEXT NOT NULL,
            response_json TEXT NOT NULL,
            grade_json TEXT NOT NULL
        );
        """
    )
    return conn


def _attempt(
    conn: sqlite3.Connection,
    *,
    row_id: int,
    learner: str = "learner-a",
    mode: str = "concept_practice",
    score: float = 0.8,
    occurred_at: str = "2026-07-13T12:00:00+00:00",
) -> None:
    conn.execute(
        "INSERT INTO attempts VALUES (?, ?, ?, ?, 4, 0, '[]', ?, ?, ?, ?)",
        (
            row_id,
            learner,
            mode,
            score,
            json.dumps({"correctAnswer": "must-not-leak"}),
            "private learner response",
            "answer-bearing feedback",
            occurred_at,
        ),
    )


def _training_answer(
    conn: sqlite3.Connection,
    *,
    row_id: int,
    attempt_id: int,
    integrity: str = "atomic_v1",
) -> None:
    receipt = {
        "effectiveEvidenceLevel": "independent_transfer",
        "receipts": [
            {
                "concept": "right_bundle_branch_block",
                "subskill": "discriminate",
                "evidenceLevel": "independent_transfer",
                "correct": True,
            }
        ],
    }
    conn.execute(
        "INSERT INTO training_campaign_answers VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            row_id,
            attempt_id,
            json.dumps(receipt),
            integrity,
            json.dumps({"selectedAnswer": "present"}),
            json.dumps({"correctAnswer": "present"}),
            json.dumps({"tutorMessage": "secret"}),
        ),
    )


def test_activity_is_stably_paginated_and_answer_key_free() -> None:
    conn = _database()
    for row_id in range(1, 5):
        _attempt(conn, row_id=row_id)
        _training_answer(conn, row_id=row_id, attempt_id=row_id)
    conn.commit()

    first = get_learning_activity(
        conn, "learner-a", secret=SECRET, limit=2
    )
    assert [item["objectiveId"] for item in first["items"]] == [
        "right_bundle_branch_block",
        "right_bundle_branch_block",
    ]
    assert first["hasMore"] is True
    assert first["nextCursor"]
    second = get_learning_activity(
        conn,
        "learner-a",
        secret=SECRET,
        limit=2,
        cursor=first["nextCursor"],
    )
    ids = [item["id"] for item in first["items"] + second["items"]]
    assert len(ids) == len(set(ids)) == 4
    serialized = json.dumps(first) + json.dumps(second)
    for forbidden in (
        "must-not-leak",
        "private learner response",
        "answer-bearing feedback",
        "selectedAnswer",
        "correctAnswer",
        "tutorMessage",
        "caseId",
        "learner-a",
    ):
        assert forbidden not in serialized


def test_cursor_is_tamper_resistant_owner_bound_and_filter_bound() -> None:
    conn = _database()
    for row_id in range(1, 3):
        _attempt(conn, row_id=row_id)
        _training_answer(conn, row_id=row_id, attempt_id=row_id)
    conn.commit()
    page = get_learning_activity(conn, "learner-a", secret=SECRET, limit=1)
    cursor = page["nextCursor"]
    assert cursor

    with pytest.raises(ActivityCursorError, match="invalid_activity_cursor"):
        get_learning_activity(
            conn, "learner-a", secret=SECRET, limit=1, cursor=cursor[:-1] + "x"
        )
    with pytest.raises(ActivityCursorError, match="invalid_activity_cursor"):
        get_learning_activity(
            conn, "learner-b", secret=SECRET, limit=1, cursor=cursor
        )
    with pytest.raises(ActivityCursorError, match="invalid_activity_cursor"):
        get_learning_activity(
            conn,
            "learner-a",
            secret=SECRET,
            mode="training",
            limit=1,
            cursor=cursor,
        )


def test_guided_rows_are_projected_and_assessment_receipt_events_are_deduplicated() -> None:
    conn = _database()
    conn.execute(
        "INSERT INTO guided_learning_events VALUES "
        "(1, 'learner-a', 'leads-vectors', .5, 3, 'assisted', 0, 'axis_normal', "
        "'[\"localize\"]', 'guided', '[\"axis_confusion\"]', '{\"answer\":\"secret\"}', "
        "'2026-07-13T13:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO guided_learning_events VALUES "
        "(2, 'learner-a', 'train', 1, 5, 'unassisted', 1, 'axis_normal', "
        "'[\"localize\"]', 'independent_transfer', '[]', '{}', "
        "'2026-07-13T13:01:00+00:00')"
    )
    conn.commit()
    page = get_learning_activity(
        conn, "learner-a", secret=SECRET, mode="guided"
    )
    assert len(page["items"]) == 1
    item = page["items"][0]
    assert item == {
        "id": item["id"],
        "mode": "guided",
        "kind": "guided_task",
        "occurredAt": "2026-07-13T13:00:00+00:00",
        "objectiveId": "axis_normal",
        "subskill": "localize",
        "testedCompetencies": [
            {
                "objectiveId": "axis_normal",
                "subskill": "localize",
                "evidence": "formative",
            }
        ],
        "score": 0.5,
        "confidence": 3,
        "assistance": "assisted",
        "evidence": "formative",
        "reviewRecommended": True,
    }


def test_legacy_incomplete_assessment_is_neutral() -> None:
    conn = _database()
    _attempt(conn, row_id=1, score=1.0)
    _training_answer(conn, row_id=1, attempt_id=1, integrity="legacy_incomplete")
    conn.commit()
    item = get_learning_activity(conn, "learner-a", secret=SECRET)["items"][0]
    assert item["evidence"] == "legacy_unverified"
    assert item["score"] is None
    assert item["objectiveId"] is None
    assert item["testedCompetencies"] == []
    assert item["reviewRecommended"] is False


def test_training_atomic_v2_remains_verified_in_activity_projection() -> None:
    conn = _database()
    _attempt(conn, row_id=1, score=0.9)
    _training_answer(conn, row_id=1, attempt_id=1, integrity="atomic_v2")
    conn.commit()
    item = get_learning_activity(conn, "learner-a", secret=SECRET)["items"][0]
    assert item["evidence"] == "independent"
    assert item["score"] == 0.9
    assert item["objectiveId"] == "right_bundle_branch_block"
    assert item["subskill"] == "discriminate"


def test_mode_filter_and_owner_isolation() -> None:
    conn = _database()
    _attempt(conn, row_id=1, mode="concept_practice")
    _training_answer(conn, row_id=1, attempt_id=1)
    _attempt(conn, row_id=2, mode="rapid_practice")
    conn.execute(
        "INSERT INTO rapid_round_answers VALUES "
        "(1, 2, '[{\"concept\":\"sinus_rhythm\",\"subskill\":\"recognize\","
        "\"accepted\":true,\"correct\":false,\"evidenceLevel\":\"independent_transfer\"},"
        "{\"concept\":\"axis_normal\",\"subskill\":\"recognize\",\"accepted\":true,"
        "\"correct\":false,\"evidenceLevel\":\"independent_transfer\"},"
        "{\"concept\":\"nonspecific_st_t_change\",\"subskill\":\"recognize\","
        "\"accepted\":true,\"correct\":false,\"evidenceLevel\":\"independent_transfer\"}]', 'atomic_v2', "
        "'{}', '{\"answer\":\"secret\"}', '{\"manifest\":\"secret\"}')"
    )
    _attempt(conn, row_id=3, learner="learner-b")
    _training_answer(conn, row_id=3, attempt_id=3)
    conn.commit()
    rapid = get_learning_activity(
        conn, "learner-a", secret=SECRET, mode="rapid"
    )
    assert len(rapid["items"]) == 1
    assert rapid["items"][0]["mode"] == "rapid"
    assert rapid["items"][0]["testedCompetencies"] == [
        {
            "objectiveId": "sinus_rhythm",
            "subskill": "recognize",
            "evidence": "independent",
        },
        {
            "objectiveId": "axis_normal",
            "subskill": "recognize",
            "evidence": "independent",
        },
        {
            "objectiveId": "nonspecific_st_t_change",
            "subskill": "recognize",
            "evidence": "independent",
        },
    ]
    assert all("learner-b" not in json.dumps(item) for item in rapid["items"])
