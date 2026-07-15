from __future__ import annotations

import uuid
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.main import app


_PASSWORD = "Preference-Test-Password!"


def _register(client: TestClient, prefix: str, *, claim_guest: bool = False) -> dict:
    response = client.post(
        "/auth/register",
        json={
            "username": f"{prefix}_{uuid.uuid4().hex[:10]}",
            "password": _PASSWORD,
            "claimGuestProgress": claim_guest,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_preferences_are_owner_bound_partial_and_strict() -> None:
    with TestClient(app) as first, TestClient(app) as second:
        _register(first, "prefs_first")
        _register(second, "prefs_second")

        defaults = first.get("/learning/preferences")
        assert defaults.status_code == 200
        assert defaults.headers["cache-control"] == "no-store, private"
        assert defaults.json() | {"updatedAt": "ignored"} == {
            "trainingStage": "not_set",
            "primaryGoal": "build_fundamentals",
            "defaultSessionLength": 10,
            "rapidPace": "untimed",
            "guidanceLevel": "balanced",
            "reduceMotion": False,
            "largeControls": False,
            "updatedAt": "ignored",
        }

        saved = first.put(
            "/learning/preferences",
            json={
                "trainingStage": "core_clerkship",
                "primaryGoal": "clinical_reading",
                "defaultSessionLength": 25,
                "rapidPace": "ward",
                "guidanceLevel": "step_by_step",
                "reduceMotion": True,
                "largeControls": True,
            },
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["defaultSessionLength"] == 25
        assert saved.json()["largeControls"] is True

        partial = first.put("/learning/preferences", json={"guidanceLevel": "minimal"})
        assert partial.status_code == 200
        assert partial.json()["trainingStage"] == "core_clerkship"
        assert partial.json()["guidanceLevel"] == "minimal"

        assert second.get("/learning/preferences").json()["trainingStage"] == "not_set"
        assert first.put(
            "/learning/preferences", json={"defaultSessionLength": 5000}
        ).status_code == 422
        assert first.put(
            "/learning/preferences", json={"reduceMotion": "true"}
        ).status_code == 422


def test_guest_preferences_follow_an_explicit_account_claim() -> None:
    with TestClient(app) as client:
        guest_saved = client.put(
            "/learning/preferences",
            json={
                "trainingStage": "advanced_clerkship",
                "primaryGoal": "medication_safety",
                "defaultSessionLength": 5,
                "rapidPace": "untimed",
                "guidanceLevel": "step_by_step",
                "reduceMotion": True,
            },
        )
        assert guest_saved.status_code == 200, guest_saved.text

        registration = _register(client, "prefs_claim", claim_guest=True)
        assert registration["guestClaim"]["guestProgress"]["learningPreferences"] == 1
        claimed = client.get("/learning/preferences").json()
        assert claimed["trainingStage"] == "advanced_clerkship"
        assert claimed["primaryGoal"] == "medication_safety"
        assert claimed["defaultSessionLength"] == 5
        assert claimed["reduceMotion"] is True


def test_reading_default_guest_preferences_does_not_create_claimable_work() -> None:
    with TestClient(app) as client:
        before = client.get("/auth/guest-progress")
        assert before.status_code == 200
        assert before.json()["hasProgress"] is False

        defaults = client.get("/learning/preferences")
        assert defaults.status_code == 200
        assert defaults.json()["updatedAt"] is None

        after = client.get("/auth/guest-progress")
        assert after.status_code == 200
        assert after.json()["hasProgress"] is False
        assert after.json()["learningPreferences"] == 0


def test_adaptive_plan_applies_saved_session_defaults_to_its_runnable_link() -> None:
    with TestClient(app) as client:
        _register(client, "prefs_plan")
        saved = client.put(
            "/learning/preferences",
            json={
                "trainingStage": "core_clerkship",
                "primaryGoal": "clinical_reading",
                "defaultSessionLength": 50,
                "rapidPace": "emergency",
                "guidanceLevel": "minimal",
            },
        )
        assert saved.status_code == 200

        response = client.get("/adaptive/plan")
        assert response.status_code == 200, response.text
        plan = response.json()
        assert plan["preferenceContext"] == {
            "trainingStage": "core_clerkship",
            "primaryGoal": "clinical_reading",
            "defaultSessionLength": 50,
            "rapidPace": "emergency",
            "guidanceLevel": "minimal",
        }
        stage = plan["stages"][0]
        assert stage["mode"] == "rapid"
        assert stage["suggestedLength"] == 50
        assert stage["suggestedPace"] == "emergency"
        query = parse_qs(urlparse(stage["href"]).query)
        assert query["suggestedLength"] == ["50"]
        assert query["pace"] == ["emergency"]
