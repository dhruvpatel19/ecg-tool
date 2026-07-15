from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app import main as main_module
from app.main import app


def _register(client: TestClient, prefix: str) -> dict:
    response = client.post(
        "/auth/register",
        json={
            "username": f"{prefix}_{uuid.uuid4().hex[:10]}",
            "password": "Backend-integrity-password!",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["user"]


def test_invalid_practice_target_fails_before_repository_selection(monkeypatch) -> None:
    calls: list[dict] = []

    def should_not_select(*_args, **kwargs):
        calls.append(kwargs)
        raise AssertionError("invalid selector reached the corpus")

    monkeypatch.setattr(main_module, "next_case", should_not_select)

    with TestClient(app) as client:
        unknown_concept = client.get(
            "/practice/next", params={"conceptId": "not_a_registered_ecg_concept"}
        )
        unknown_subskill = client.get(
            "/practice/next",
            params={"conceptId": "normal_ecg", "subskill": "recognise"},
        )

    assert unknown_concept.status_code == 422
    assert unknown_concept.json()["detail"]["code"] == "unknown_practice_concept"
    assert unknown_subskill.status_code == 422
    assert unknown_subskill.json()["detail"]["code"] == "unknown_practice_subskill"
    assert calls == []


def test_guided_capability_cannot_bypass_its_commit_endpoint() -> None:
    with TestClient(app) as client:
        user = _register(client, "tutorial_audit_only")
        guided = client.get("/tutorials/orientation")
        assert guided.status_code == 200, guided.text
        packet = guided.json()["recommendedPacket"]
        case_id = packet["case_id"]
        assert case_id.startswith("ec_")
        assert "supported_objectives" not in packet
        assert packet["ptbxl_plus"]["measurements"] == {}
        assert packet["ptbxl_plus"]["fiducials"]["rois"] == []

        before = client.get(f"/learners/{user['userId']}").json()
        response = client.post(
            "/attempts",
            json={
                "caseId": case_id,
                "mode": "tutorial",
                "structuredAnswer": {"framework": "clerkship"},
                "freeTextAnswer": "A guessed interpretation",
                "confidence": 4,
                "hintsUsed": 0,
            },
        )
        assert response.status_code == 404

        after = client.get(f"/learners/{user['userId']}").json()
        assert after["mastery"] == before["mastery"]
        assert after["attemptCount"] == before["attemptCount"]
