from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

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


def _event(
    *,
    owner_id: str,
    competency_id: str,
    score: float,
    occurred_at: str,
    mode: str = "training",
    evidence_level: str = "independent_transfer",
    integrity_status: str = "atomic_v2",
    event_type: str = "answer_committed",
) -> str:
    event_id = f"trend:{uuid.uuid4().hex}"
    with store.connect() as conn:
        conn.execute(
            """
            INSERT INTO learner_events (
                event_id, owner_id, mode, session_id, lease_id, ecg_id,
                event_type, evidence_level, integrity_status, score,
                occurred_at, created_at
            ) VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                owner_id,
                mode,
                f"private-session-{uuid.uuid4().hex}",
                event_type,
                evidence_level,
                integrity_status,
                score if event_type in {"interaction_committed", "answer_committed"} else None,
                occurred_at,
                occurred_at,
            ),
        )
        conn.execute(
            """
            INSERT INTO learner_event_competencies (
                event_id, competency_id, competency_score
            ) VALUES (?, ?, ?)
            """,
            (event_id, competency_id, score),
        )
    return event_id


def test_competency_trend_is_owner_bound_chronological_and_answer_free() -> None:
    with TestClient(app) as owner, TestClient(app) as other:
        owner_user = _register(owner, "trend_owner")
        other_user = _register(other, "trend_other")
        competency_id = "atrial_fibrillation:recognize"

        _event(
            owner_id=owner_user["userId"],
            competency_id=competency_id,
            score=0.35,
            occurred_at="2026-07-10T12:00:00+00:00",
            mode="guided",
            evidence_level="guided",
        )
        _event(
            owner_id=owner_user["userId"],
            competency_id=competency_id,
            score=0.8,
            occurred_at="2026-07-12T12:00:00+00:00",
        )
        _event(
            owner_id=owner_user["userId"],
            competency_id=competency_id,
            score=0.95,
            occurred_at="2026-07-13T12:00:00+00:00",
            integrity_status="quarantined",
        )
        _event(
            owner_id=other_user["userId"],
            competency_id=competency_id,
            score=0.1,
            occurred_at="2026-07-11T12:00:00+00:00",
        )
        _event(
            owner_id=owner_user["userId"],
            competency_id="atrial_fibrillation:discriminate",
            score=0.2,
            occurred_at="2026-07-11T12:00:00+00:00",
        )

        response = owner.get(
            "/learners/demo/competencies/atrial_fibrillation/recognize/trend"
        )
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store, private"
        assert response.headers["vary"] == "Authorization, Cookie"
        payload = response.json()
        assert payload["version"] == "competency-trend-v1"
        assert [point["score"] for point in payload["points"]] == [0.35, 0.8]
        assert payload["points"][0]["independent"] is False
        assert payload["points"][1]["independent"] is True
        serialized = response.text.lower()
        for forbidden in (
            "private-session",
            "event_id",
            "session_id",
            "ecg_id",
            "lease_id",
        ):
            assert forbidden not in serialized

        isolated = other.get(
            f"/learners/{owner_user['userId']}/competencies/"
            "atrial_fibrillation/recognize/trend"
        )
        assert isolated.status_code == 200
        assert [point["score"] for point in isolated.json()["points"]] == [0.1]


def test_competency_trend_validates_registry_and_reports_real_pagination() -> None:
    with TestClient(app) as client:
        user = _register(client, "trend_limit")
        for index in range(3):
            _event(
                owner_id=user["userId"],
                competency_id="atrial_fibrillation:recognize",
                score=index / 2,
                occurred_at=f"2026-07-{10 + index:02d}T12:00:00+00:00",
            )

        limited = client.get(
            "/learners/demo/competencies/atrial_fibrillation/recognize/trend",
            params={"limit": 2},
        )
        assert limited.status_code == 200, limited.text
        assert limited.json()["hasMore"] is True
        assert [point["score"] for point in limited.json()["points"]] == [0.5, 1.0]

        missing = client.get(
            "/learners/demo/competencies/not_a_real_objective/recognize/trend"
        )
        assert missing.status_code == 404


def test_competency_trend_has_stable_order_for_equal_timestamps() -> None:
    with TestClient(app) as client:
        user = _register(client, "trend_stable")
        occurred_at = "2026-07-14T12:00:00+00:00"
        first_id = _event(
            owner_id=user["userId"],
            competency_id="sinus_rhythm:recognize",
            score=0.25,
            occurred_at=occurred_at,
        )
        second_id = _event(
            owner_id=user["userId"],
            competency_id="sinus_rhythm:recognize",
            score=0.75,
            occurred_at=occurred_at,
        )

        response = client.get(
            "/learners/demo/competencies/sinus_rhythm/recognize/trend"
        )
        assert response.status_code == 200, response.text
        expected = [0.25, 0.75] if first_id < second_id else [0.75, 0.25]
        assert [point["score"] for point in response.json()["points"]] == expected
