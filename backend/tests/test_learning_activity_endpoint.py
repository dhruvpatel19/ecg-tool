from __future__ import annotations

import json
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


def _guided_events(learner_id: str, count: int) -> None:
    suffix = uuid.uuid4().hex
    with store.connect() as conn:
        for index in range(count):
            conn.execute(
                """
                INSERT INTO guided_learning_events (
                    learner_id, module_id, scene_id, interaction_id, concept,
                    subskills_json, score, correct, attempts, assistance, hints_used,
                    confidence, requested_evidence_level, effective_evidence_level,
                    case_id, case_provenance, case_eligible, misconception_tags_json,
                    event_key, receipt_json, registry_version, created_at
                ) VALUES (?, 'leads-vectors', 'm02-s1', ?, 'axis_normal', '["localize"]',
                    ?, ?, 1, 'unassisted', 0, 4, 'guided', 'guided', ?, 'ptb-xl', 1,
                    ?, ?, ?, 'ecg-objective-registry-v2', ?)
                """,
                (
                    learner_id,
                    f"activity-{suffix}-{index}",
                    1.0 if index % 2 == 0 else 0.4,
                    1 if index % 2 == 0 else 0,
                    f"case-private-{suffix}-{index}",
                    "[]" if index % 2 == 0 else '["axis_confusion"]',
                    f"activity:{suffix}:{index}",
                    json.dumps({"correctAnswer": "must-not-leak"}),
                    f"2026-07-13T12:{index:02d}:00+00:00",
                ),
            )


def test_activity_endpoint_is_owner_bound_paginated_and_private() -> None:
    with TestClient(app) as owner, TestClient(app) as other:
        owner_user = _register(owner, "activity_owner")
        _register(other, "activity_other")
        _guided_events(owner_user["userId"], 23)

        first = owner.get("/learning/activity?mode=guided&limit=20")
        assert first.status_code == 200, first.text
        assert first.headers["cache-control"] == "no-store, private"
        payload = first.json()
        assert payload["version"] == "learning-activity-v1"
        assert len(payload["items"]) == 20
        assert payload["hasMore"] is True
        assert payload["nextCursor"]

        second = owner.get(
            "/learning/activity",
            params={
                "mode": "guided",
                "limit": 20,
                "cursor": payload["nextCursor"],
            },
        )
        assert second.status_code == 200, second.text
        assert len(second.json()["items"]) == 3
        all_ids = [
            item["id"] for item in payload["items"] + second.json()["items"]
        ]
        assert len(all_ids) == len(set(all_ids)) == 23

        serialized = json.dumps(payload) + second.text
        for forbidden in (
            owner_user["userId"],
            "case-private",
            "correctAnswer",
            "must-not-leak",
            "receipt_json",
        ):
            assert forbidden not in serialized

        assert other.get(
            "/learning/activity",
            params={"mode": "guided", "limit": 20},
        ).json()["items"] == []


def test_activity_endpoint_rejects_tampered_and_cross_owner_cursors_identically() -> None:
    with TestClient(app) as owner, TestClient(app) as other:
        owner_user = _register(owner, "activity_cursor_owner")
        _register(other, "activity_cursor_other")
        _guided_events(owner_user["userId"], 2)
        cursor = owner.get("/learning/activity?limit=1").json()["nextCursor"]
        assert cursor

        tampered = owner.get(
            "/learning/activity", params={"limit": 1, "cursor": cursor[:-1] + "x"}
        )
        cross_owner = other.get(
            "/learning/activity", params={"limit": 1, "cursor": cursor}
        )
        assert tampered.status_code == cross_owner.status_code == 400
        assert tampered.json() == cross_owner.json()
        assert tampered.json()["detail"]["code"] == "invalid_activity_request"
