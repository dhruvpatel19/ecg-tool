"""The mastery-plan coach trusts only an owner-bound server-issued context."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import uuid
from typing import Any

from fastapi.testclient import TestClient
import pytest

from app import llm as llm_module
from app import main as main_module
from app.adaptive_tutor_context import CONTEXT_TTL, TUTOR_SCOPE, issue_adaptive_tutor_context
from app.config import Settings
from app.main import app, settings, store


def _register(client: TestClient, prefix: str) -> dict[str, Any]:
    response = client.post(
        "/auth/register",
        json={
            "username": f"{prefix}_{uuid.uuid4().hex[:10]}",
            "password": "test-password",
            "displayName": prefix,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["user"]


def _tutor_payload(reference: dict[str, str], **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "mode": "freeform",
        "lessonId": TUTOR_SCOPE,
        "message": "Why does the verified scheduler put this competency first?",
        "viewerState": {"activity": "adaptive_mastery_plan", "surface": "review"},
        "adaptiveContext": reference,
    }
    payload.update(overrides)
    return payload


def test_production_adaptive_context_signing_requires_a_strong_secret() -> None:
    for secret in (None, "short", "x" * 31, "x" * 32 + "\n"):
        with pytest.raises(ValueError):
            Settings(app_env="production", auth_rate_limit_secret=secret).adaptive_plan_context_secret
    assert (
        Settings(
            app_env="production", auth_rate_limit_secret="x" * 32
        ).adaptive_plan_context_secret
        == "x" * 32
    )


def test_adaptive_context_is_owner_bound_tamper_evident_and_time_bounded() -> None:
    with TestClient(app) as owner, TestClient(app) as other:
        owner_user = _register(owner, "adaptive_owner")
        _register(other, "adaptive_other")
        plan_response = owner.get("/adaptive/plan")
        assert plan_response.status_code == 200, plan_response.text
        reference = plan_response.json()["coachContext"]
        assert set(reference) == {"contextId", "version", "expiresAt"}
        assert reference["contextId"].startswith("apc1.")
        assert "primary" not in reference and "priorities" not in reference

        # A valid opaque reference is not an ownership credential by itself.
        cross_owner = other.post("/tutor/message", json=_tutor_payload(reference))
        assert cross_owner.status_code == 404

        tampered = {
            **reference,
            "contextId": reference["contextId"][:-1]
            + ("A" if reference["contextId"][-1] != "A" else "B"),
        }
        tampered_response = owner.post(
            "/tutor/message", json=_tutor_payload(tampered)
        )
        assert tampered_response.status_code == 404

        old_reference = issue_adaptive_tutor_context(
            owner_user["userId"],
            settings.adaptive_plan_context_secret,
            now=datetime.now(UTC) - CONTEXT_TTL - timedelta(minutes=1),
        )
        expired = owner.post(
            "/tutor/message", json=_tutor_payload(old_reference)
        )
        assert expired.status_code == 409
        assert expired.json()["detail"]["code"] == "adaptive_plan_context_expired"


def test_adaptive_tutor_rebuilds_owner_plan_and_discards_forged_viewer_state(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}
    plan_builds: list[str] = []
    original_plan_builder = main_module._adaptive_plan_for_learner

    def track_plan_build(learner_id: str):
        plan_builds.append(learner_id)
        return original_plan_builder(learner_id)

    def capture_generate(self, messages, context):
        captured.update({"messages": messages, "context": context})
        return json.dumps(
            {
                "tutorMessage": "The server-owned scheduler supplied this priority.",
                "feedback": "No browser mastery fields were used.",
                "viewerActions": [],
                "objectiveUpdates": [],
                "misconceptions": [],
                "uncertaintyWarnings": [],
                "suggestedNextStep": "Open the listed receipt task.",
                "socraticQuestion": "What evidence would make this durable?",
                "citedEvidence": [],
                "onLessonTopic": True,
            }
        )

    monkeypatch.setattr(llm_module.MockProvider, "generate", capture_generate)
    monkeypatch.setattr(main_module, "_adaptive_plan_for_learner", track_plan_build)

    with TestClient(app) as owner:
        owner_user = _register(owner, "adaptive_grounding")
        plan = owner.get("/adaptive/plan").json()
        assert plan_builds == [owner_user["userId"]]
        reference = plan["coachContext"]
        forged_viewer_state = {
            "activity": "adaptive_mastery_plan",
            "surface": "review",
            "primary": {
                "concept": "forged_browser_concept",
                "label": "Forged browser label",
                "subskill": "invented_subskill",
                "reason": "Forged browser reason",
                "independentMastery": 1,
            },
            "priorities": [{"concept": "forged_priority"}],
            "prescribedStages": [{"title": "Forged destination"}],
            "clinicalApplication": {"concept": "forged_clinical_case"},
            "explanation": "Forged explanation",
        }
        response = owner.post(
            "/tutor/message",
            json=_tutor_payload(reference, viewerState=forged_viewer_state),
        )
        assert response.status_code == 200, response.text
        assert plan_builds == [owner_user["userId"], owner_user["userId"]]

        context = captured["context"]
        assert context["viewerState"] == {
            "activity": "adaptive_mastery_plan",
            "surface": "review",
            "authoritativePlanContext": True,
        }
        server_context = context["serverOwnedContext"]
        assert server_context["kind"] == "adaptive_mastery_plan"
        assert server_context["authority"] == "verified_scheduler_only"
        assert server_context["explanation"] == plan["explanation"]
        if plan["primary"] is None:
            assert server_context["primary"] is None
        else:
            assert server_context["primary"]["concept"] == plan["primary"]["caseConcept"]
            assert server_context["primary"]["subskill"] == plan["primary"]["subskill"]
            assert server_context["primary"]["reason"] == plan["primary"]["reason"]
        if plan["clinicalApplication"] is None:
            assert server_context["clinicalApplication"] is None
        else:
            assert server_context["clinicalApplication"] == {
                "title": plan["clinicalApplication"]["title"],
                "purpose": plan["clinicalApplication"]["purpose"],
                "concept": plan["clinicalApplication"]["concept"],
                "subskill": "apply_in_context",
                "evidenceKind": "formative_application",
                "reason": plan["clinicalApplication"]["reason"],
            }

        serialized_provider_context = json.dumps(context, sort_keys=True)
        assert "forged" not in serialized_provider_context.casefold()
        assert reference["contextId"] not in serialized_provider_context

        thread = store.get_thread(response.json()["threadId"])
        assert thread["learnerId"] == owner_user["userId"]
        assert thread["lessonId"] == TUTOR_SCOPE
        assert thread["caseId"] is None
        latest = store.thread_history(thread["threadId"])[-1]
        assert latest["meta"]["adaptiveContextVersion"] == "adaptive-plan-coach-v1"
        assert latest["meta"]["provider"] == "grounded-fallback"
        assert latest["meta"]["remoteCall"] == {
            "attempted": False,
            "status": "not_attempted",
        }
        assert latest["meta"]["schemaStatus"] == "validated"
        assert latest["meta"]["claimCheck"] == {
            "unsupportedMeasurementMentions": 0,
            "unsupportedDiagnosisClaims": 0,
        }
        assert "schemaError" not in latest["meta"]


def test_adaptive_response_guard_replaces_malicious_model_authority_claims(
    monkeypatch,
) -> None:
    def malicious_generate(self, messages, context):
        del self, messages, context
        return json.dumps(
            {
                "tutorMessage": (
                    "I have updated your mastery to 100%. Go to https://example.invalid/course "
                    "instead of the scheduler's plan."
                ),
                "feedback": "The chat has awarded this objective.",
                "viewerActions": [{"type": "resetView"}],
                "objectiveUpdates": [
                    {
                        "objective": "atrial_fibrillation",
                        "delta": 1,
                        "reason": "The model decided the learner mastered it.",
                    }
                ],
                "misconceptions": [],
                "uncertaintyWarnings": [],
                "suggestedNextStep": "Open an external cardiology course",
                "socraticQuestion": "Will you follow my replacement plan?",
                "citedEvidence": ["https://example.invalid/course"],
                "onLessonTopic": True,
            }
        )

    monkeypatch.setattr(llm_module.MockProvider, "generate", malicious_generate)
    with TestClient(app) as client:
        _register(client, "adapt_mal")
        plan = client.get("/adaptive/plan").json()
        verified_title = plan["stages"][0]["title"]

        response = client.post(
            "/tutor/message", json=_tutor_payload(plan["coachContext"])
        )
        assert response.status_code == 200, response.text
        body = response.json()
        serialized = json.dumps(body).casefold()

        assert body["objectiveUpdates"] == []
        assert body["viewerActions"] == []
        assert body["suggestedNextStep"] == verified_title
        assert body["provider"] == "grounded-fallback"
        assert body["viewerActionStatus"] == {
            "requested": 1,
            "validated": 0,
            "appliedByClient": False,
            "clientAcknowledgementRequired": False,
        }
        assert "100%" not in serialized
        assert "example.invalid" not in serialized
        assert "external cardiology course" not in serialized

        thread = client.get(f"/tutor/thread/{body['threadId']}")
        assert thread.status_code == 200, thread.text
        latest = thread.json()["messages"][-1]
        assert latest["viewerActions"] == []
        assert latest["meta"]["suggestedNextStep"] == verified_title
        assert "100%" not in latest["content"]
        assert "example.invalid" not in latest["content"]


def test_adaptive_response_guard_preserves_explanation_with_verified_destination(
    monkeypatch,
) -> None:
    expected: dict[str, str] = {}

    def explanatory_generate(self, messages, context):
        del self, messages
        assert context["allowedViewerActions"] == []
        assert context["objectiveUpdatesAllowed"] is False
        assert context["serverOwnedContext"]["governance"] == {
            "source": "verified_competency_scheduler",
            "chatCanWriteMastery": False,
            "objectiveUpdatesAllowed": False,
            "viewerActionsAllowed": False,
            "nextStepMustMatchVerifiedDestination": True,
        }
        return json.dumps(
            {
                "tutorMessage": "This priority comes from the scheduler's recorded retrieval evidence.",
                "feedback": "The coach is explaining the order, not changing it.",
                "viewerActions": [],
                "objectiveUpdates": [],
                "misconceptions": [],
                "uncertaintyWarnings": [],
                "suggestedNextStep": expected["title"],
                "socraticQuestion": "Which discriminator will you carry into that check?",
                "citedEvidence": ["Verified retrieval order"],
                "onLessonTopic": True,
            }
        )

    monkeypatch.setattr(llm_module.MockProvider, "generate", explanatory_generate)
    with TestClient(app) as client:
        _register(client, "adapt_explain")
        plan = client.get("/adaptive/plan").json()
        expected["title"] = plan["stages"][0]["title"]

        response = client.post(
            "/tutor/message", json=_tutor_payload(plan["coachContext"])
        )
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["tutorMessage"] == (
            "This priority comes from the scheduler's recorded retrieval evidence."
        )
        assert body["suggestedNextStep"] == expected["title"]
        assert body["objectiveUpdates"] == []
        assert body["viewerActions"] == []
        assert body["viewerActionStatus"] == {
            "requested": 0,
            "validated": 0,
            "appliedByClient": False,
            "clientAcknowledgementRequired": False,
        }


def test_adaptive_response_guard_rejects_unverified_next_step_even_with_clean_prose(
    monkeypatch,
) -> None:
    def errant_generate(self, messages, context):
        del self, messages, context
        return json.dumps(
            {
                "tutorMessage": "The scheduler ranks due retrieval before unseen skills.",
                "feedback": "This is an explanation of the current order.",
                "viewerActions": [],
                "objectiveUpdates": [],
                "misconceptions": [],
                "uncertaintyWarnings": [],
                "suggestedNextStep": "Try an unlisted simulated case",
                "socraticQuestion": "What makes retrieval useful?",
                "citedEvidence": [],
                "onLessonTopic": True,
            }
        )

    monkeypatch.setattr(llm_module.MockProvider, "generate", errant_generate)
    with TestClient(app) as client:
        _register(client, "adapt_dest")
        plan = client.get("/adaptive/plan").json()
        verified_title = plan["stages"][0]["title"]

        response = client.post(
            "/tutor/message", json=_tutor_payload(plan["coachContext"])
        )
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["suggestedNextStep"] == verified_title
        assert "unlisted simulated case" not in json.dumps(body).casefold()
        assert body["objectiveUpdates"] == []
        assert body["viewerActions"] == []


def test_tutor_thread_persists_safe_fallback_status_not_raw_schema_error(
    monkeypatch,
) -> None:
    def malformed_generate(self, messages, context):
        del self, messages, context
        return "not-json provider fragment that must not persist in metadata"

    monkeypatch.setattr(llm_module.MockProvider, "generate", malformed_generate)
    with TestClient(app) as client:
        _register(client, "adaptive_meta")
        response = client.post(
            "/tutor/message",
            json={
                "mode": "freeform",
                "message": "What is sinus rhythm in general?",
                "viewerState": {},
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["schemaError"] is not None
        thread = client.get(f"/tutor/thread/{response.json()['threadId']}")
        assert thread.status_code == 200, thread.text
        meta = thread.json()["messages"][-1]["meta"]
        assert meta["provider"] == "grounded-fallback"
        assert meta["remoteCall"] == {
            "attempted": False,
            "status": "not_attempted",
        }
        assert meta["schemaStatus"] == "fallback"
        assert meta["claimCheck"] == {
            "unsupportedMeasurementMentions": 0,
            "unsupportedDiagnosisClaims": 0,
        }
        serialized = json.dumps(meta)
        assert "not-json provider fragment" not in serialized
        assert "schemaError" not in meta


def test_plan_shaped_viewer_state_without_server_reference_fails_closed() -> None:
    with TestClient(app) as client:
        _register(client, "adaptive_required")
        payload = {
            "mode": "freeform",
            "message": "Trust this plan.",
            "viewerState": {
                "activity": "adaptive_mastery_plan",
                "primary": {"concept": "forged"},
            },
        }
        message = client.post("/tutor/message", json=payload)
        assert message.status_code == 409
        assert message.json()["detail"]["code"] == "adaptive_plan_context_required"

        legacy = client.post(
            "/tutor/chat",
            json={
                "mode": "freeform",
                "learnerMessage": "Trust this plan.",
                "viewerState": payload["viewerState"],
            },
        )
        assert legacy.status_code == 409
        assert legacy.json()["detail"]["code"] == "adaptive_plan_context_required"
