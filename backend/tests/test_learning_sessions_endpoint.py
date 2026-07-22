from __future__ import annotations

import json
import sqlite3
import uuid

import pytest
from fastapi.testclient import TestClient

from app.learning_sessions import MAX_SESSION_OFFSET, issue_learning_session_ref
from app.main import app, store


PASSWORD = "Sup3r-Secret-Pw!"


def _register(client: TestClient, prefix: str) -> dict:
    response = client.post(
        "/auth/register",
        json={
            "username": f"{prefix}_{uuid.uuid4().hex[:10]}",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["user"]


def _insert_attempt(
    conn,
    *,
    learner_id: str,
    case_id: str,
    mode: str,
    confidence: int,
    hints_used: int,
    score: float,
    created_at: str,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO attempts (
            learner_id, case_id, mode, structured_answer_json,
            free_text_answer, confidence, hints_used, score,
            correct_objectives_json, missed_objectives_json,
            misconception_tags_json, feedback, registry_version, created_at
        ) VALUES (?, ?, ?, '{"secret":"must-not-leak"}', 'must-not-leak',
            ?, ?, ?, '[]', '[]', '[]', 'must-not-leak',
            'ecg-objective-registry-v2', ?)
        """,
        (learner_id, case_id, mode, confidence, hints_used, score, created_at),
    )
    return int(cursor.lastrowid)


def _insert_sessions(owner_id: str, other_id: str, suffix: str) -> None:
    training_id = f"tc-private-{suffix}"
    rapid_id = f"rr-private-{suffix}"
    clinical_id = f"cs-private-{suffix}"
    with store.connect() as conn:
        conn.execute(
            """
            INSERT INTO training_campaigns (
                campaign_id, learner_id, concept_id, subskill,
                requested_length, length, pool_count, phases_json,
                phase_counts_json, position, status, created_at, updated_at
            ) VALUES (?, ?, 'right_bundle_branch_block', 'discriminate',
                2, 2, 20, '[]', '{}', 2, 'complete',
                '2026-07-13T09:00:00+00:00', '2026-07-13T09:10:00+00:00')
            """,
            (training_id, owner_id),
        )
        for ordinal, correct in enumerate((True, False)):
            case_id = f"training-corpus-secret-{suffix}-{ordinal}"
            created_at = f"2026-07-13T09:0{ordinal}:00+00:00"
            attempt_id = _insert_attempt(
                conn,
                learner_id=owner_id,
                case_id=case_id,
                mode="concept_practice",
                confidence=5 - ordinal,
                hints_used=ordinal,
                score=1.0 if correct else 0.0,
                created_at=created_at,
            )
            conn.execute(
                """
                INSERT INTO training_campaign_answers (
                    campaign_id, ordinal, case_id, response_json, grade_json,
                    tutor_json, receipt_json, summary_json, integrity_status,
                    attempt_id, created_at
                ) VALUES (?, ?, ?, ?, ?, '{}', '{}', ?, ?, ?, ?)
                """,
                (
                    training_id,
                    ordinal,
                    case_id,
                    json.dumps({"answerKey": "must-not-leak"}),
                    json.dumps({"diagnosis": "must-not-leak"}),
                    json.dumps({"correct": correct}),
                    "atomic_v1" if ordinal == 0 else "atomic_v2",
                    attempt_id,
                    created_at,
                ),
            )
        conn.execute(
            """
            INSERT INTO rapid_rounds (
                round_id, learner_id, pace, length, assessment_scope,
                focus_concept, focus_subskill, position, status, created_at, updated_at
            ) VALUES (?, ?, 'untimed', 2, 'dominant_finding',
                'atrial_fibrillation', 'recognize', 2, 'complete',
                '2026-07-14T10:00:00+00:00', '2026-07-14T10:12:00+00:00')
            """,
            (rapid_id, owner_id),
        )
        for index, score in enumerate((1.0, 0.5), start=1):
            case_id = f"rapid-corpus-secret-{suffix}-{index}"
            created_at = f"2026-07-14T10:0{index}:00+00:00"
            attempt_id = _insert_attempt(
                conn,
                learner_id=owner_id,
                case_id=case_id,
                mode="rapid_practice",
                confidence=6 - index,
                hints_used=index - 1,
                score=score,
                created_at=created_at,
            )
            conn.execute(
                """
                INSERT INTO rapid_round_answers (
                    round_id, case_id, response_json, grade_json, result_json,
                    receipts_json, integrity_status, attempt_id, created_at
                ) VALUES (?, ?, ?, ?, ?, '[{}]', ?, ?, ?)
                """,
                (
                    rapid_id,
                    case_id,
                    json.dumps({"freeText": "must-not-leak"}),
                    json.dumps({"answerKey": "must-not-leak"}),
                    json.dumps(
                        {
                            "caseId": f"rapid-corpus-secret-{suffix}-{index}",
                            "score": score,
                            "revealedDiagnosis": "must-not-leak",
                        }
                    ),
                    "atomic_v1" if index == 1 else "atomic_v2",
                    attempt_id,
                    created_at,
                ),
            )
            if index == 1:
                event_id = f"rapid-answer:{rapid_id}:0:{case_id}"
                conn.execute(
                    """
                    INSERT INTO learner_events (
                        event_id, owner_id, mode, session_id, lease_id, ecg_id,
                        event_type, evidence_level, integrity_status, score,
                        occurred_at, created_at
                    ) VALUES (?, ?, 'rapid', ?, NULL, NULL, 'answer_committed',
                        'independent_transfer', 'atomic_v2', ?, ?, ?)
                    """,
                    (event_id, owner_id, rapid_id, score, created_at, created_at),
                )
                conn.execute(
                    """
                    INSERT INTO learner_event_competencies (
                        event_id, competency_id, competency_score
                    ) VALUES (?, 'st_elevation:localize', 0.8)
                    """,
                    (event_id,),
                )

        conn.execute(
            """
            INSERT INTO clinical_shift_sessions (
                session_id, learner_id, lane, tier, focus_objective,
                focus_subskill, length, requested_length, available_length,
                position, status, created_at, updated_at
            ) VALUES (?, ?, 'ward', 'core', 'bradycardia', 'apply_in_context',
                2, 2, 2, 2, 'complete',
                '2026-07-15T11:00:00+00:00', '2026-07-15T11:15:00+00:00')
            """,
            (clinical_id, owner_id),
        )
        for index, (score, correct) in enumerate(((0.75, 1), (0.5, 0)), start=1):
            case_id = f"clinical-corpus-secret-{suffix}-{index}"
            created_at = f"2026-07-15T11:0{index}:00+00:00"
            attempt_id = _insert_attempt(
                conn,
                learner_id=owner_id,
                case_id=case_id,
                mode="clinical_decision",
                confidence=6 - index,
                hints_used=index - 1,
                score=score,
                created_at=created_at,
            )
            conn.execute(
                """
                INSERT INTO clinical_shift_answers (
                    session_id, item_id, ecg_id, response_json, grade_json,
                    score, correct, attempt_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    clinical_id,
                    f"clinical-item-secret-{suffix}-{index}",
                    case_id,
                    json.dumps({"choice": "must-not-leak"}),
                    json.dumps({"answerKey": "must-not-leak"}),
                    score,
                    correct,
                    attempt_id,
                    created_at,
                ),
            )

        conn.execute(
            """
            INSERT INTO rapid_rounds (
                round_id, learner_id, pace, length, assessment_scope,
                position, status, created_at, updated_at
            ) VALUES (?, ?, 'ward', 5, 'full_read', 1, 'active',
                '2026-07-15T12:00:00+00:00', '2026-07-15T12:01:00+00:00')
            """,
            (f"active-private-{suffix}", owner_id),
        )
        conn.execute(
            """
            INSERT INTO clinical_shift_sessions (
                session_id, learner_id, lane, tier, length, requested_length,
                available_length, position, status, created_at, updated_at
            ) VALUES (?, ?, 'clinic', 'core', 1, 1, 1, 1, 'complete',
                '2026-07-15T13:00:00+00:00', '2026-07-15T13:05:00+00:00')
            """,
            (f"other-owner-private-{suffix}", other_id),
        )


def _insert_legacy_projection_rows(owner_id: str, suffix: str) -> None:
    training_id = f"tc-private-{suffix}"
    rapid_id = f"rr-private-{suffix}"
    created_at = "2026-07-15T14:00:00+00:00"
    with store.connect() as conn:
        training_case_id = f"legacy-training-corpus-secret-{suffix}"
        training_attempt_id = _insert_attempt(
            conn,
            learner_id=owner_id,
            case_id=training_case_id,
            mode="concept_practice",
            confidence=3,
            hints_used=2,
            score=1.0,
            created_at=created_at,
        )
        conn.execute(
            """
            INSERT INTO training_campaign_answers (
                campaign_id, ordinal, case_id, response_json, grade_json,
                tutor_json, receipt_json, summary_json, integrity_status,
                attempt_id, created_at
            ) VALUES (?, 2, ?, '{}', '{}', '{}', '{}', '{"correct":true}',
                'legacy_two_phase', ?, ?)
            """,
            (training_id, training_case_id, training_attempt_id, created_at),
        )

        # A normalized-looking competency attached to a quarantined event must
        # not override the answer-free session focus fallback.
        first_training_case = f"training-corpus-secret-{suffix}-0"
        training_event_id = f"training-answer:{training_id}:0:{first_training_case}"
        conn.execute(
            """
            INSERT INTO learner_events (
                event_id, owner_id, mode, session_id, lease_id, ecg_id,
                event_type, evidence_level, integrity_status, score,
                occurred_at, created_at
            ) VALUES (?, ?, 'training', ?, NULL, NULL, 'answer_committed',
                'legacy_unverified', 'quarantined', 0.99, ?, ?)
            """,
            (training_event_id, owner_id, training_id, created_at, created_at),
        )
        conn.execute(
            """
            INSERT INTO learner_event_competencies (
                event_id, competency_id, competency_score
            ) VALUES (?, 'legacy_projection:recognize', 0.99)
            """,
            (training_event_id,),
        )

        rapid_case_id = f"legacy-rapid-corpus-secret-{suffix}"
        rapid_attempt_id = _insert_attempt(
            conn,
            learner_id=owner_id,
            case_id=rapid_case_id,
            mode="rapid_practice",
            confidence=3,
            hints_used=2,
            score=0.0,
            created_at=created_at,
        )
        conn.execute(
            """
            INSERT INTO rapid_round_answers (
                round_id, case_id, response_json, grade_json, result_json,
                receipts_json, integrity_status, attempt_id, created_at
            ) VALUES (?, ?, '{}', '{}', '{"score":0.0}', '[]',
                'legacy_incomplete', ?, ?)
            """,
            (rapid_id, rapid_case_id, rapid_attempt_id, created_at),
        )

        # Simulate stale pre-projection saved rows. They are outside the valid
        # two-attempt projection and must not count or make a session "saved".
        for mode, session_id in (("training", training_id), ("rapid", rapid_id)):
            conn.execute(
                """
                INSERT INTO learning_session_flags (
                    owner_id, mode, session_id, attempt_index, created_at, updated_at
                ) VALUES (?, ?, ?, 3, ?, ?)
                """,
                (owner_id, mode, session_id, created_at, created_at),
            )


def test_learning_sessions_are_owner_bound_aggregated_and_answer_free() -> None:
    with TestClient(app) as owner, TestClient(app) as other:
        owner_user = _register(owner, "session_owner")
        other_user = _register(other, "session_other")
        suffix = uuid.uuid4().hex
        _insert_sessions(owner_user["userId"], other_user["userId"], suffix)

        response = owner.get("/learning/sessions?limit=10")
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store, private"
        assert response.headers["pragma"] == "no-cache"
        payload = response.json()
        assert payload["version"] == "learning-sessions-v1"
        assert payload["hasMore"] is False
        assert payload["nextOffset"] is None
        assert payload["totalSavedItems"] == 0
        assert [item["mode"] for item in payload["items"]] == [
            "clinical",
            "rapid",
            "training",
        ]

        clinical, rapid, training = payload["items"]
        assert clinical | {"sessionRef": "ignored"} == {
            "sessionRef": "ignored",
            "mode": "clinical",
            "status": "complete",
            "attempted": 2,
            "total": 2,
            "score": 0.625,
            "correctCount": 1,
            "flaggedCount": 0,
            "focusCompetencies": [
                {
                    "objectiveId": "bradycardia",
                    "subskill": "apply_in_context",
                    "mappingSource": "session_focus",
                }
            ],
            "startedAt": "2026-07-15T11:00:00+00:00",
            "completedAt": "2026-07-15T11:15:00+00:00",
            "reviewAvailable": True,
        }
        assert rapid["attempted"] == rapid["total"] == 2
        assert rapid["score"] == 0.75
        assert rapid["correctCount"] is None
        assert rapid["flaggedCount"] == 0
        assert rapid["focusCompetencies"] == [
            {
                "objectiveId": "atrial_fibrillation",
                "subskill": "recognize",
                "mappingSource": "session_focus",
            }
        ]
        assert rapid["reviewAvailable"] is True
        assert training["attempted"] == training["total"] == 2
        assert training["score"] is None
        assert training["correctCount"] == 1
        assert training["flaggedCount"] == 0
        assert training["focusCompetencies"] == [
            {
                "objectiveId": "right_bundle_branch_block",
                "subskill": "discriminate",
                "mappingSource": "session_focus",
            }
        ]
        assert training["reviewAvailable"] is True

        expected_scores = {
            "clinical": [0.75, 0.5],
            "rapid": [1.0, 0.5],
            "training": [1.0, 0.0],
        }
        review_responses = []
        for item in payload["items"]:
            review_response = owner.get(
                f"/learning/sessions/{item['sessionRef']}"
            )
            review_responses.append(review_response)
            assert review_response.status_code == 200, review_response.text
            assert review_response.headers["cache-control"] == "no-store, private"
            assert review_response.headers["pragma"] == "no-cache"
            review = review_response.json()
            assert review["version"] == "learning-session-review-v1"
            assert review["session"] == item
            assert [attempt["index"] for attempt in review["attempts"]] == [1, 2]
            assert [attempt["score"] for attempt in review["attempts"]] == (
                expected_scores[item["mode"]]
            )
            assert [attempt["confidence"] for attempt in review["attempts"]] == (
                [None, None] if item["mode"] == "clinical" else [5, 4]
            )
            assert [attempt["assistance"] for attempt in review["attempts"]] == [
                {"hintsUsed": 0},
                {"hintsUsed": 1},
            ]
            assert all(
                set(attempt) == {
                    "index",
                    "score",
                    "competencies",
                    "confidence",
                    "assistance",
                    "flagged",
                }
                for attempt in review["attempts"]
            )
            assert all(attempt["flagged"] is False for attempt in review["attempts"])
            expected_competencies = [
                [
                    {
                        **item["focusCompetencies"][0],
                        # Session focus is routing metadata. It must never
                        # inherit an item score without normalized evidence.
                        "score": None,
                    }
                ]
                for attempt in review["attempts"]
            ]
            if item["mode"] == "rapid":
                # Exact normalized event evidence wins over the session-level
                # focus fallback, without exposing the underlying ECG/event id.
                expected_competencies[0] = [
                    {
                        "objectiveId": "st_elevation",
                        "subskill": "localize",
                        "score": 0.8,
                        "mappingSource": "committed_event",
                    }
                ]
            assert [
                attempt["competencies"] for attempt in review["attempts"]
            ] == expected_competencies

        repeated = owner.get("/learning/sessions?limit=10").json()
        assert [item["sessionRef"] for item in repeated["items"]] == [
            item["sessionRef"] for item in payload["items"]
        ]
        assert len({item["sessionRef"] for item in payload["items"]}) == 3
        first_page = owner.get("/learning/sessions?limit=2").json()
        assert first_page["items"] == payload["items"][:2]
        assert first_page["hasMore"] is True
        assert first_page["nextOffset"] == 2
        assert first_page["totalSavedItems"] == 0
        second_page = owner.get("/learning/sessions?limit=2&offset=2").json()
        assert second_page["items"] == payload["items"][2:]
        assert second_page["hasMore"] is False
        assert second_page["nextOffset"] is None
        assert second_page["totalSavedItems"] == 0
        other_items = other.get("/learning/sessions").json()["items"]
        # Empty technical completion records do not displace learner-facing
        # performance history.
        assert other_items == []

        unknown_ref = "lsr1_" + ("A" * 43)
        unknown = other.get(f"/learning/sessions/{unknown_ref}")
        cross_owner = other.get(
            f"/learning/sessions/{clinical['sessionRef']}"
        )
        assert unknown.status_code == cross_owner.status_code == 404
        assert unknown.json() == cross_owner.json()
        assert unknown.json()["detail"]["code"] == "learning_session_not_found"

        flag_path = (
            f"/learning/sessions/{clinical['sessionRef']}/attempts/2/flag"
        )
        saved = owner.put(flag_path)
        replayed_save = owner.put(flag_path)
        assert saved.status_code == replayed_save.status_code == 200
        assert saved.headers["cache-control"] == "no-store, private"
        assert saved.json() == replayed_save.json() == {
            "sessionRef": clinical["sessionRef"],
            "attemptIndex": 2,
            "flagged": True,
            "flaggedCount": 1,
        }
        with store.connect() as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM learning_session_flags WHERE owner_id = ?",
                (owner_user["userId"],),
            ).fetchone()[0] == 1

        flagged_items = owner.get("/learning/sessions").json()["items"]
        flagged_clinical = next(
            item for item in flagged_items if item["mode"] == "clinical"
        )
        assert flagged_clinical["flaggedCount"] == 1
        flagged_review = owner.get(
            f"/learning/sessions/{clinical['sessionRef']}"
        )
        assert flagged_review.json()["session"]["flaggedCount"] == 1
        assert [
            attempt["flagged"]
            for attempt in flagged_review.json()["attempts"]
        ] == [False, True]

        unknown_flag = owner.put(
            f"/learning/sessions/{unknown_ref}/attempts/1/flag"
        )
        cross_owner_flag = other.put(
            f"/learning/sessions/{clinical['sessionRef']}/attempts/1/flag"
        )
        out_of_range_flag = owner.put(
            f"/learning/sessions/{clinical['sessionRef']}/attempts/3/flag"
        )
        assert (
            unknown_flag.status_code
            == cross_owner_flag.status_code
            == out_of_range_flag.status_code
            == 404
        )
        assert (
            unknown_flag.json()
            == cross_owner_flag.json()
            == out_of_range_flag.json()
        )

        removed = owner.delete(flag_path)
        replayed_remove = owner.delete(flag_path)
        assert removed.status_code == replayed_remove.status_code == 200
        assert removed.json() == replayed_remove.json() == {
            "sessionRef": clinical["sessionRef"],
            "attemptIndex": 2,
            "flagged": False,
            "flaggedCount": 0,
        }
        assert owner.get(
            f"/learning/sessions/{clinical['sessionRef']}"
        ).json()["attempts"][1]["flagged"] is False

        serialized = response.text + "".join(
            review_response.text for review_response in review_responses
        ) + saved.text + flagged_review.text
        for forbidden in (
            owner_user["userId"],
            other_user["userId"],
            suffix,
            "must-not-leak",
            "answerKey",
            "corpus-secret",
            "item-secret",
            "tc-private",
            "rr-private",
            "cs-private",
            "http://",
            "https://",
        ):
            assert forbidden not in serialized


def test_abandoned_rapid_round_with_committed_answers_is_reviewable_as_partial() -> None:
    with TestClient(app) as owner, TestClient(app) as other:
        owner_user = _register(owner, "partial_rapid_owner")
        _register(other, "partial_rapid_other")
        suffix = uuid.uuid4().hex
        partial_id = f"partial-rapid-private-{suffix}"
        empty_id = f"empty-rapid-private-{suffix}"
        committed_case_id = f"committed-ecg-private-{suffix}"
        pending_case_id = f"pending-ecg-must-not-leak-{suffix}"
        occurred_at = "2026-07-16T10:01:00+00:00"
        with store.connect() as conn:
            conn.execute(
                """
                INSERT INTO rapid_rounds (
                    round_id, learner_id, pace, length, assessment_scope,
                    focus_concept, focus_subskill, pending_case_id, position,
                    status, created_at, updated_at
                ) VALUES (?, ?, 'untimed', 5, 'dominant_finding',
                    'atrial_fibrillation', 'recognize', ?, 1, 'abandoned',
                    '2026-07-16T10:00:00+00:00',
                    '2026-07-16T10:02:00+00:00')
                """,
                (partial_id, owner_user["userId"], pending_case_id),
            )
            attempt_id = _insert_attempt(
                conn,
                learner_id=owner_user["userId"],
                case_id=committed_case_id,
                mode="rapid_practice",
                confidence=4,
                hints_used=0,
                score=0.75,
                created_at=occurred_at,
            )
            conn.execute(
                """
                INSERT INTO rapid_round_answers (
                    round_id, case_id, response_json, grade_json, result_json,
                    receipts_json, integrity_status, attempt_id, created_at
                ) VALUES (?, ?, '{"learner":"private"}',
                    '{"answerKey":"private"}', '{"score":0.75}', ?,
                    'atomic_v2', ?, ?)
                """,
                (
                    partial_id,
                    committed_case_id,
                    json.dumps(
                        [
                            {
                                "concept": "atrial_fibrillation",
                                "subskill": "recognize",
                                "accepted": True,
                                "correct": True,
                                "evidenceLevel": "independent_transfer",
                            }
                        ]
                    ),
                    attempt_id,
                    occurred_at,
                ),
            )
            conn.execute(
                """
                INSERT INTO rapid_rounds (
                    round_id, learner_id, pace, length, assessment_scope,
                    position, status, created_at, updated_at
                ) VALUES (?, ?, 'untimed', 5, 'dominant_finding', 0,
                    'abandoned', '2026-07-16T09:00:00+00:00',
                    '2026-07-16T09:01:00+00:00')
                """,
                (empty_id, owner_user["userId"]),
            )
            before = {
                "attempts": conn.execute(
                    "SELECT COUNT(*) FROM attempts"
                ).fetchone()[0],
                "answers": conn.execute(
                    "SELECT COUNT(*) FROM rapid_round_answers"
                ).fetchone()[0],
                "mastery": conn.execute(
                    "SELECT COUNT(*) FROM subskill_mastery"
                ).fetchone()[0],
            }

        sessions_response = owner.get("/learning/sessions?limit=50")
        assert sessions_response.status_code == 200, sessions_response.text
        partials = [
            item
            for item in sessions_response.json()["items"]
            if item["mode"] == "rapid" and item["status"] == "abandoned"
        ]
        assert len(partials) == 1
        partial = partials[0]
        assert partial["attempted"] == 1
        assert partial["total"] == 5
        assert partial["score"] == 0.75
        assert partial["reviewAvailable"] is True

        review_response = owner.get(
            f"/learning/sessions/{partial['sessionRef']}"
        )
        assert review_response.status_code == 200, review_response.text
        review = review_response.json()
        assert review["session"] == partial
        assert [attempt["index"] for attempt in review["attempts"]] == [1]
        assert review["attempts"][0]["score"] == 0.75
        assert other.get(
            f"/learning/sessions/{partial['sessionRef']}"
        ).status_code == 404

        serialized = sessions_response.text + review_response.text
        for forbidden in (
            partial_id,
            empty_id,
            committed_case_id,
            pending_case_id,
            suffix,
            "answerKey",
        ):
            assert forbidden not in serialized
        with store.connect() as conn:
            after = {
                "attempts": conn.execute(
                    "SELECT COUNT(*) FROM attempts"
                ).fetchone()[0],
                "answers": conn.execute(
                    "SELECT COUNT(*) FROM rapid_round_answers"
                ).fetchone()[0],
                "mastery": conn.execute(
                    "SELECT COUNT(*) FROM subskill_mastery"
                ).fetchone()[0],
            }
        assert after == before


def test_abandoned_focused_set_with_committed_answers_is_reviewable_as_partial() -> None:
    with TestClient(app) as owner, TestClient(app) as other:
        owner_user = _register(owner, "partial_focused_owner")
        _register(other, "partial_focused_other")
        suffix = uuid.uuid4().hex
        partial_id = f"partial-focused-private-{suffix}"
        empty_id = f"empty-focused-private-{suffix}"
        committed_case_id = f"focused-committed-private-{suffix}"
        pending_case_id = f"focused-pending-private-{suffix}"
        occurred_at = "2026-07-16T11:01:00+00:00"
        abandoned_at = "2026-07-16T11:03:00+00:00"
        with store.connect() as conn:
            conn.execute(
                """
                INSERT INTO training_campaigns (
                    campaign_id, learner_id, concept_id, subskill,
                    requested_length, length, pool_count, phases_json,
                    phase_counts_json, pending_case_id, position, status,
                    context_key, created_at, updated_at, abandoned_at
                ) VALUES (?, ?, 'right_bundle_branch_block', 'recognize',
                    5, 5, 20, '[]', '{}', ?, 1, 'abandoned',
                    'receiptConcept=qrs_width_morphology',
                    '2026-07-16T11:00:00+00:00',
                    '2026-07-16T11:02:00+00:00', ?)
                """,
                (partial_id, owner_user["userId"], pending_case_id, abandoned_at),
            )
            attempt_id = _insert_attempt(
                conn,
                learner_id=owner_user["userId"],
                case_id=committed_case_id,
                mode="concept_practice",
                confidence=4,
                hints_used=1,
                score=0.9,
                created_at=occurred_at,
            )
            conn.execute(
                """
                INSERT INTO training_campaign_answers (
                    campaign_id, ordinal, case_id, response_json, grade_json,
                    tutor_json, receipt_json, summary_json, integrity_status,
                    attempt_id, created_at
                ) VALUES (?, 0, ?, '{"learner":"private"}',
                    '{"answerKey":"private"}', '{}', '{}',
                    '{"correct":false,"classificationCorrect":true}',
                    'atomic_v2', ?, ?)
                """,
                (partial_id, committed_case_id, attempt_id, occurred_at),
            )
            conn.execute(
                """
                INSERT INTO training_campaigns (
                    campaign_id, learner_id, concept_id, subskill,
                    requested_length, length, pool_count, phases_json,
                    phase_counts_json, position, status, created_at, updated_at,
                    abandoned_at
                ) VALUES (?, ?, 'right_bundle_branch_block', 'recognize',
                    5, 5, 20, '[]', '{}', 0, 'abandoned',
                    '2026-07-16T10:00:00+00:00',
                    '2026-07-16T10:01:00+00:00',
                    '2026-07-16T10:01:00+00:00')
                """,
                (empty_id, owner_user["userId"]),
            )

        sessions_response = owner.get("/learning/sessions?limit=50")
        assert sessions_response.status_code == 200, sessions_response.text
        partials = [
            item
            for item in sessions_response.json()["items"]
            if item["mode"] == "training" and item["status"] == "abandoned"
        ]
        assert len(partials) == 1
        partial = partials[0]
        assert partial["attempted"] == 1
        assert partial["total"] == 5
        assert partial["score"] is None
        assert partial["correctCount"] == 0
        assert partial["completedAt"] == abandoned_at
        assert partial["reviewAvailable"] is True
        assert partial["focusCompetencies"] == [{
            "objectiveId": "qrs_width_morphology",
            "subskill": "recognize",
            "mappingSource": "session_focus",
        }]

        review_response = owner.get(
            f"/learning/sessions/{partial['sessionRef']}"
        )
        assert review_response.status_code == 200, review_response.text
        review = review_response.json()
        assert review["session"] == partial
        assert [attempt["index"] for attempt in review["attempts"]] == [1]
        # The selected-skill campaign outcome is authoritative; the legacy
        # generic attempt score (0.9 here) must not replace it.
        assert review["attempts"][0]["score"] == 0.0
        assert other.get(
            f"/learning/sessions/{partial['sessionRef']}"
        ).status_code == 404

        serialized = sessions_response.text + review_response.text
        for forbidden in (
            partial_id,
            empty_id,
            committed_case_id,
            pending_case_id,
            suffix,
            "answerKey",
        ):
            assert forbidden not in serialized


def test_learning_sessions_saved_filter_and_pagination_are_owner_bound() -> None:
    with TestClient(app) as owner, TestClient(app) as other:
        owner_user = _register(owner, "session_page_owner")
        other_user = _register(other, "session_page_other")
        suffix = uuid.uuid4().hex
        _insert_sessions(owner_user["userId"], other_user["userId"], suffix)

        all_items = owner.get("/learning/sessions").json()["items"]
        clinical, _, training = all_items
        assert owner.put(
            f"/learning/sessions/{clinical['sessionRef']}/attempts/2/flag"
        ).status_code == 200
        assert owner.put(
            f"/learning/sessions/{training['sessionRef']}/attempts/1/flag"
        ).status_code == 200

        first_saved = owner.get(
            "/learning/sessions?savedOnly=true&limit=1"
        ).json()
        assert first_saved == {
            "version": "learning-sessions-v1",
            "items": [{**clinical, "flaggedCount": 1}],
            "hasMore": True,
            "nextOffset": 1,
            "totalSavedItems": 2,
        }
        second_saved = owner.get(
            "/learning/sessions?savedOnly=true&limit=1&offset=1"
        ).json()
        assert second_saved == {
            "version": "learning-sessions-v1",
            "items": [{**training, "flaggedCount": 1}],
            "hasMore": False,
            "nextOffset": None,
            "totalSavedItems": 2,
        }
        assert owner.get(
            "/learning/sessions?savedOnly=false&limit=1&offset=2"
        ).json()["totalSavedItems"] == 2

        other_page = other.get("/learning/sessions?savedOnly=true").json()
        assert other_page["items"] == []
        assert other_page["totalSavedItems"] == 0
        assert owner.get("/learning/sessions?offset=-1").status_code == 422
        assert owner.get(
            f"/learning/sessions?offset={MAX_SESSION_OFFSET + 1}"
        ).status_code == 422
        assert owner.get("/learning/sessions?savedOnly=maybe").status_code == 422


def test_legacy_training_and_rapid_rows_are_quarantined_from_review() -> None:
    with TestClient(app) as owner, TestClient(app) as other:
        owner_user = _register(owner, "integrity_owner")
        other_user = _register(other, "integrity_other")
        suffix = uuid.uuid4().hex
        _insert_sessions(owner_user["userId"], other_user["userId"], suffix)
        _insert_legacy_projection_rows(owner_user["userId"], suffix)

        payload = owner.get("/learning/sessions").json()
        assert payload["totalSavedItems"] == 0
        assert owner.get(
            "/learning/sessions?savedOnly=true"
        ).json()["items"] == []
        by_mode = {item["mode"]: item for item in payload["items"]}
        assert by_mode["training"]["attempted"] == 2
        assert by_mode["training"]["correctCount"] == 1
        assert by_mode["training"]["flaggedCount"] == 0
        assert by_mode["rapid"]["attempted"] == 2
        assert by_mode["rapid"]["score"] == 0.75
        assert by_mode["rapid"]["flaggedCount"] == 0

        for mode in ("training", "rapid"):
            item = by_mode[mode]
            review_response = owner.get(
                f"/learning/sessions/{item['sessionRef']}"
            )
            assert review_response.status_code == 200
            review = review_response.json()
            assert [attempt["index"] for attempt in review["attempts"]] == [1, 2]
            assert all(
                attempt["confidence"] in {4, 5}
                for attempt in review["attempts"]
            )
            out_of_bounds = owner.put(
                f"/learning/sessions/{item['sessionRef']}/attempts/3/flag"
            )
            assert out_of_bounds.status_code == 404

        valid_save = owner.put(
            f"/learning/sessions/{by_mode['training']['sessionRef']}/attempts/1/flag"
        )
        assert valid_save.json()["flaggedCount"] == 1
        saved_page = owner.get("/learning/sessions?savedOnly=true").json()
        assert saved_page["totalSavedItems"] == 1
        assert [item["mode"] for item in saved_page["items"]] == ["training"]

        training_review = owner.get(
            f"/learning/sessions/{by_mode['training']['sessionRef']}"
        ).json()
        assert training_review["attempts"][0]["competencies"] == [
            {
                "objectiveId": "right_bundle_branch_block",
                "subskill": "discriminate",
                "score": None,
                "mappingSource": "session_focus",
            }
        ]
        serialized = json.dumps(payload) + json.dumps(training_review)
        assert "legacy_projection" not in serialized
        assert "legacy-training" not in serialized
        assert "legacy-rapid" not in serialized


def test_saved_review_uses_stable_answer_identity_when_ordinals_shift() -> None:
    with TestClient(app) as owner, TestClient(app) as other:
        owner_user = _register(owner, "stable_flag_owner")
        other_user = _register(other, "stable_flag_other")
        suffix = uuid.uuid4().hex
        _insert_sessions(owner_user["userId"], other_user["userId"], suffix)
        training = next(
            item
            for item in owner.get("/learning/sessions").json()["items"]
            if item["mode"] == "training"
        )
        save_path = (
            f"/learning/sessions/{training['sessionRef']}/attempts/2/flag"
        )
        assert owner.put(save_path).status_code == 200

        training_id = f"tc-private-{suffix}"
        with store.connect() as conn:
            source_answer_id = int(
                conn.execute(
                    "SELECT source_answer_id FROM learning_session_flags "
                    "WHERE owner_id = ? AND mode = 'training' "
                    "AND session_id = ? AND attempt_index = 2",
                    (owner_user["userId"], training_id),
                ).fetchone()[0]
            )
            # Recreate a v5-style resolvable row and an ambiguous stale row.
            conn.execute(
                "UPDATE learning_session_flags SET source_answer_id = NULL "
                "WHERE owner_id = ? AND mode = 'training' AND session_id = ? "
                "AND attempt_index = 2",
                (owner_user["userId"], training_id),
            )
            conn.execute(
                "INSERT INTO learning_session_flags ("
                "owner_id, mode, session_id, attempt_index, created_at, updated_at"
                ") VALUES (?, 'training', ?, 3, 'now', 'now')",
                (owner_user["userId"], training_id),
            )

        # The schema transaction backfills only identities it can prove.
        store.init_db()
        with store.connect() as conn:
            migrated = conn.execute(
                "SELECT attempt_index, source_answer_id "
                "FROM learning_session_flags WHERE owner_id = ? "
                "AND mode = 'training' AND session_id = ? ORDER BY attempt_index",
                (owner_user["userId"], training_id),
            ).fetchall()
            assert [row["attempt_index"] for row in migrated] == [2, 3]
            assert int(migrated[0]["source_answer_id"]) == source_answer_id
            assert migrated[1]["source_answer_id"] is None

            # Removing an earlier answer from the eligible projection shifts
            # the saved answer from public ordinal 2 to public ordinal 1.
            conn.execute(
                "UPDATE training_campaign_answers "
                "SET integrity_status = 'legacy_two_phase' "
                "WHERE campaign_id = ? AND ordinal = 0",
                (training_id,),
            )

        shifted_review_response = owner.get(
            f"/learning/sessions/{training['sessionRef']}"
        )
        assert shifted_review_response.status_code == 200
        shifted_review = shifted_review_response.json()
        assert shifted_review["session"]["attempted"] == 1
        assert shifted_review["session"]["flaggedCount"] == 1
        assert [attempt["flagged"] for attempt in shifted_review["attempts"]] == [
            True
        ]
        assert "source_answer_id" not in shifted_review_response.text
        assert "sourceAnswerId" not in shifted_review_response.text

        # A legacy row can separately occupy the stable answer's new public
        # ordinal. Re-saving that visible item must collapse the duplicate onto
        # the stable identity instead of returning or persisting a count of two.
        with store.connect() as conn:
            conn.execute(
                "INSERT INTO learning_session_flags ("
                "owner_id, mode, session_id, attempt_index, created_at, updated_at"
                ") VALUES (?, 'training', ?, 1, 'now', 'now')",
                (owner_user["userId"], training_id),
            )
        duplicate_save = owner.put(
            f"/learning/sessions/{training['sessionRef']}/attempts/1/flag"
        )
        assert duplicate_save.status_code == 200
        assert duplicate_save.json()["flagged"] is True
        assert duplicate_save.json()["flaggedCount"] == 1
        with store.connect() as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM learning_session_flags "
                "WHERE owner_id = ? AND mode = 'training' AND session_id = ? "
                "AND attempt_index = 1 AND source_answer_id IS NULL",
                (owner_user["userId"], training_id),
            ).fetchone()[0] == 0
        assert owner.get(
            f"/learning/sessions/{training['sessionRef']}"
        ).json()["session"]["flaggedCount"] == 1

        removed = owner.delete(
            f"/learning/sessions/{training['sessionRef']}/attempts/1/flag"
        )
        assert removed.status_code == 200
        assert removed.json() == {
            "sessionRef": training["sessionRef"],
            "attemptIndex": 1,
            "flagged": False,
            "flaggedCount": 0,
        }
        assert owner.get(
            "/learning/sessions?savedOnly=true"
        ).json()["items"] == []
        with store.connect() as conn:
            remaining = conn.execute(
                "SELECT attempt_index, source_answer_id "
                "FROM learning_session_flags WHERE owner_id = ? "
                "AND mode = 'training' AND session_id = ?",
                (owner_user["userId"], training_id),
            ).fetchall()
            assert len(remaining) == 1
            assert int(remaining[0]["attempt_index"]) == 3
            assert remaining[0]["source_answer_id"] is None


def test_stable_flags_can_share_a_historical_ordinal_after_projection_shift() -> None:
    with TestClient(app) as owner, TestClient(app) as other:
        owner_user = _register(owner, "stable2_owner")
        other_user = _register(other, "stable2_other")
        suffix = uuid.uuid4().hex
        _insert_sessions(owner_user["userId"], other_user["userId"], suffix)
        training = next(
            item
            for item in owner.get("/learning/sessions").json()["items"]
            if item["mode"] == "training"
        )
        training_id = f"tc-private-{suffix}"

        first_save = owner.put(
            f"/learning/sessions/{training['sessionRef']}/attempts/1/flag"
        )
        assert first_save.status_code == 200
        assert first_save.json()["flaggedCount"] == 1
        with store.connect() as conn:
            answer_rows = conn.execute(
                "SELECT id, ordinal FROM training_campaign_answers "
                "WHERE campaign_id = ? ORDER BY ordinal, id",
                (training_id,),
            ).fetchall()
            first_answer_id = int(answer_rows[0]["id"])
            second_answer_id = int(answer_rows[1]["id"])
            conn.execute(
                "UPDATE training_campaign_answers "
                "SET integrity_status = 'legacy_two_phase' "
                "WHERE id = ?",
                (first_answer_id,),
            )

        shifted = owner.get(
            f"/learning/sessions/{training['sessionRef']}"
        ).json()
        assert shifted["session"]["attempted"] == 1
        assert shifted["session"]["flaggedCount"] == 0
        assert shifted["attempts"][0]["flagged"] is False

        # The second answer now occupies public ordinal 1. Its stable save must
        # coexist with the first answer's historical ordinal-1 snapshot.
        second_save_path = (
            f"/learning/sessions/{training['sessionRef']}/attempts/1/flag"
        )
        second_save = owner.put(second_save_path)
        replayed_second_save = owner.put(second_save_path)
        assert second_save.status_code == replayed_second_save.status_code == 200
        assert second_save.json() == replayed_second_save.json()
        assert second_save.json()["flaggedCount"] == 1
        with store.connect() as conn:
            stable_rows = conn.execute(
                "SELECT flag_id, attempt_index, source_answer_id "
                "FROM learning_session_flags WHERE owner_id = ? "
                "AND mode = 'training' AND session_id = ? "
                "ORDER BY flag_id",
                (owner_user["userId"], training_id),
            ).fetchall()
            assert len(stable_rows) == 2
            assert {int(row["attempt_index"]) for row in stable_rows} == {1}
            assert {int(row["source_answer_id"]) for row in stable_rows} == {
                first_answer_id,
                second_answer_id,
            }
            assert len({int(row["flag_id"]) for row in stable_rows}) == 2

            conn.execute(
                "UPDATE training_campaign_answers "
                "SET integrity_status = 'atomic_v1' WHERE id = ?",
                (first_answer_id,),
            )

        restored = owner.get(
            f"/learning/sessions/{training['sessionRef']}"
        ).json()
        assert restored["session"]["attempted"] == 2
        assert restored["session"]["flaggedCount"] == 2
        assert [attempt["flagged"] for attempt in restored["attempts"]] == [
            True,
            True,
        ]

        # Re-saving the second answer at its restored public ordinal remains
        # idempotent and does not create a third stable row.
        replay_at_restored_ordinal = owner.put(
            f"/learning/sessions/{training['sessionRef']}/attempts/2/flag"
        )
        assert replay_at_restored_ordinal.status_code == 200
        assert replay_at_restored_ordinal.json()["flaggedCount"] == 2
        with store.connect() as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM learning_session_flags WHERE owner_id = ? "
                "AND mode = 'training' AND session_id = ?",
                (owner_user["userId"], training_id),
            ).fetchone()[0] == 2


def test_corrupt_attempt_and_competency_scores_project_as_unavailable() -> None:
    with TestClient(app) as owner, TestClient(app) as other:
        owner_user = _register(owner, "corrupt_score_owner")
        other_user = _register(other, "corrupt_score_other")
        suffix = uuid.uuid4().hex
        _insert_sessions(owner_user["userId"], other_user["userId"], suffix)

        training_id = f"tc-private-{suffix}"
        rapid_id = f"rr-private-{suffix}"
        clinical_id = f"cs-private-{suffix}"
        with store.connect() as conn:
            training_attempt_ids = [
                int(row[0])
                for row in conn.execute(
                    "SELECT attempt_id FROM training_campaign_answers "
                    "WHERE campaign_id = ? ORDER BY ordinal",
                    (training_id,),
                ).fetchall()
            ]
            conn.execute(
                "UPDATE attempts SET score = 1.25 WHERE id = ?",
                (training_attempt_ids[0],),
            )
            conn.execute(
                "UPDATE attempts SET score = -0.25 WHERE id = ?",
                (training_attempt_ids[1],),
            )
            conn.execute(
                "UPDATE clinical_shift_answers SET score = -0.5 "
                "WHERE session_id = ? AND id = ("
                "SELECT MIN(id) FROM clinical_shift_answers WHERE session_id = ?)",
                (clinical_id, clinical_id),
            )
            conn.execute("PRAGMA ignore_check_constraints = ON")
            conn.execute(
                "UPDATE learner_event_competencies SET competency_score = ? "
                "WHERE event_id LIKE ?",
                (float("inf"), f"rapid-answer:{rapid_id}:%"),
            )
            conn.execute("PRAGMA ignore_check_constraints = OFF")

        try:
            items = {
                item["mode"]: item
                for item in owner.get("/learning/sessions").json()["items"]
            }
            training_review = owner.get(
                f"/learning/sessions/{items['training']['sessionRef']}"
            ).json()
            # Focused Practice review uses the immutable selected-skill
            # outcome, so corrupt legacy generic attempt scores cannot erase
            # or replace the saved result.
            assert [attempt["score"] for attempt in training_review["attempts"]] == [
                1.0,
                0.0,
            ]

            clinical_review = owner.get(
                f"/learning/sessions/{items['clinical']['sessionRef']}"
            ).json()
            assert clinical_review["attempts"][0]["score"] is None
            assert clinical_review["attempts"][1]["score"] == 0.5

            rapid_review = owner.get(
                f"/learning/sessions/{items['rapid']['sessionRef']}"
            ).json()
            assert rapid_review["attempts"][0]["competencies"] == [
                {
                    "objectiveId": "st_elevation",
                    "subskill": "localize",
                    "score": None,
                    "mappingSource": "committed_event",
                }
            ]
        finally:
            # This suite shares one in-memory learner store. Restore the
            # deliberately malformed rows so a later integrity probe does not
            # correctly report the fixture's CHECK-constraint violation.
            with store.connect() as conn:
                conn.execute(
                    "UPDATE attempts SET score = 1.0 WHERE id = ?",
                    (training_attempt_ids[0],),
                )
                conn.execute(
                    "UPDATE attempts SET score = 0.0 WHERE id = ?",
                    (training_attempt_ids[1],),
                )
                conn.execute(
                    "UPDATE clinical_shift_answers SET score = 0.75 "
                    "WHERE session_id = ? AND id = ("
                    "SELECT MIN(id) FROM clinical_shift_answers WHERE session_id = ?)",
                    (clinical_id, clinical_id),
                )
                conn.execute(
                    "UPDATE learner_event_competencies SET competency_score = 0.8 "
                    "WHERE event_id LIKE ?",
                    (f"rapid-answer:{rapid_id}:%",),
                )


def test_session_flags_export_delete_and_prevent_guest_persistence() -> None:
    with TestClient(app) as owner, TestClient(app) as other, TestClient(app) as guest:
        owner_user = _register(owner, "flag_lifecycle_owner")
        other_user = _register(other, "flag_lifecycle_other")
        suffix = uuid.uuid4().hex
        _insert_sessions(owner_user["userId"], other_user["userId"], suffix)
        rapid = next(
            item
            for item in owner.get("/learning/sessions").json()["items"]
            if item["mode"] == "rapid"
        )
        flag_path = (
            f"/learning/sessions/{rapid['sessionRef']}/attempts/1/flag"
        )

        guest_response = guest.put(flag_path)
        assert guest_response.status_code == 401
        assert guest_response.json()["detail"]["code"] == "authentication_required"
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            with store.connect() as conn:
                conn.execute(
                    "INSERT INTO learning_session_flags ("
                    "owner_id, mode, session_id, attempt_index, created_at, updated_at"
                    ") VALUES (?, 'training', ?, 1, 'now', 'now')",
                    (f"g_{uuid.uuid4().hex}", f"tc-private-{suffix}"),
                )

        assert owner.put(flag_path).status_code == 200
        exported = store.export_user_progress(owner_user["userId"])
        assert exported is not None
        flag_records = exported["records"]["learningSessionFlags"]
        assert exported["recordCounts"]["learningSessionFlags"] == 1
        assert len(flag_records) == 1
        exported_flag = flag_records[0]
        assert set(exported_flag) == {
            "mode",
            "sessionRef",
            "attemptIndex",
            "flagged",
            "createdAt",
            "updatedAt",
        }
        assert exported_flag["mode"] == "rapid"
        assert exported_flag["attemptIndex"] == 1
        assert exported_flag["flagged"] is True
        assert exported_flag["sessionRef"].startswith("lr_")
        exported_rapid = next(
            row
            for row in exported["records"]["rapidRounds"]
            if row["sessionRef"] == exported_flag["sessionRef"]
        )
        assert exported_rapid["sessionRef"] == exported_flag["sessionRef"]
        assert exported_rapid["sessionRef"] != rapid["sessionRef"]
        assert all(
            row["sessionRef"].startswith("lr_")
            for record_name in (
                "trainingCampaigns",
                "rapidRounds",
                "clinicalShiftSessions",
            )
            for row in exported["records"][record_name]
        )
        assert suffix not in json.dumps(exported_flag)
        assert suffix not in exported_rapid["sessionRef"]

        with store.connect() as conn:
            password_hash = str(
                conn.execute(
                    "SELECT password_hash FROM users WHERE user_id = ?",
                    (owner_user["userId"],),
                ).fetchone()[0]
            )
        assert store.delete_user_account(owner_user["userId"], password_hash) is True
        with store.connect() as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM learning_session_flags WHERE owner_id = ?",
                (owner_user["userId"],),
            ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT COUNT(*) FROM users WHERE user_id = ?",
                (other_user["userId"],),
            ).fetchone()[0] == 1


def test_session_reference_is_deterministic_owner_and_mode_bound() -> None:
    first = issue_learning_session_ref(
        secret="test-secret",
        learner_id="owner-a",
        mode="rapid",
        session_id="private-session-id",
    )
    assert first == issue_learning_session_ref(
        secret="test-secret",
        learner_id="owner-a",
        mode="rapid",
        session_id="private-session-id",
    )
    assert first != issue_learning_session_ref(
        secret="test-secret",
        learner_id="owner-b",
        mode="rapid",
        session_id="private-session-id",
    )
    assert first != issue_learning_session_ref(
        secret="test-secret",
        learner_id="owner-a",
        mode="clinical",
        session_id="private-session-id",
    )
    assert first.startswith("lsr1_")
    assert "owner-a" not in first
    assert "private-session-id" not in first
