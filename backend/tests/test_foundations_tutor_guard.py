from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app, tutor_service


def test_foundations_tutor_response_cannot_emit_progress_or_mastery_updates(
    monkeypatch,
) -> None:
    def fake_converse(
        message,
        case_packet,
        profile,
        history,
        mode,
        lesson,
        viewer_state,
        **kwargs,
    ):
        del message, case_packet, profile, history, mode, lesson, viewer_state, kwargs
        return {
            "tutorMessage": "Use the visible evidence, then return to the sweep.",
            "feedback": "Explanatory feedback only.",
            "viewerActions": [],
            "objectiveUpdates": [
                {
                    "objective": "foundations_systematic_sweep",
                    "delta": 1.0,
                    "reason": "Chat must never award this.",
                }
            ],
            "misconceptions": [],
            "uncertaintyWarnings": [],
            "suggestedNextStep": "Return to the sweep.",
            "socraticQuestion": "Which visible anchor supports your next clause?",
            "citedEvidence": [],
            "onLessonTopic": True,
        }

    monkeypatch.setattr(tutor_service, "converse", fake_converse)
    with TestClient(app) as client:
        response = client.post(
            "/tutor/message",
            json={
                "mode": "tutorial",
                "lessonId": "integrated-interpretation",
                "scopeKey": "foundations:S12",
                "message": "Did this answer make me master Foundations?",
                "viewerState": {
                    "moduleId": "foundations",
                    "sceneId": "S12",
                },
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["objectiveUpdates"] == []


def test_foundations_tutor_context_disallows_objective_updates_but_keeps_learning_actions() -> None:
    context = tutor_service._context(
        "tutorial",
        None,
        {"learnerId": "foundations-context-test"},
        None,
        {"moduleId": "foundations", "sceneId": "S12"},
    )

    assert context["objectiveUpdatesAllowed"] is False
    assert "highlightROI" in context["allowedViewerActions"]
    assert any(
        "explanatory only" in rule for rule in context["groundingRules"]
    )


def test_compatibility_foundations_tutor_also_strips_objective_updates(
    monkeypatch,
) -> None:
    def fake_foundations(*args, **kwargs):
        del args, kwargs
        return {
            "tutorMessage": "Compatibility explanation.",
            "objectiveUpdates": [
                {
                    "objective": "foundations_calibration",
                    "delta": 1.0,
                    "reason": "Must be removed.",
                }
            ],
        }

    monkeypatch.setattr(tutor_service, "foundations", fake_foundations)
    with TestClient(app) as client:
        response = client.post(
            "/tutor/foundations",
            json={"learnerMessage": "Explain calibration.", "scope": "S2"},
        )

    assert response.status_code == 200, response.text
    assert response.json()["objectiveUpdates"] == []
