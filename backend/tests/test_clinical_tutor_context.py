"""Clinical tutor grounding is durable, owner-bound, and answer-key safe."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient

from app import main as main_module
from app.main import app, clinical_item_store, store


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
    return response.json()


def _recursive_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(_recursive_keys(child) for child in value.values()))
    if isinstance(value, list):
        return set().union(*(_recursive_keys(child) for child in value)) if value else set()
    return set()


def _recursive_strings(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set().union(*(_recursive_strings(child) for child in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(_recursive_strings(child) for child in value)) if value else set()
    return {value} if isinstance(value, str) else set()


def _commit_revealed_steps(
    client: TestClient,
    session_id: str,
    item_id: str,
    item: dict[str, Any],
) -> dict[str, Any]:
    """Follow the public sequential contract; never forge final step answers."""

    current = item
    while current.get("stepwise_state", {}).get("active"):
        active = current["stepwise_state"]["active"]
        committed = client.post(
            f"/clinical/shift/{session_id}/step",
            json={
                "itemId": item_id,
                "stepIndex": active["stepIndex"],
                "answerIndex": 0,
            },
        )
        assert committed.status_code == 200, committed.text
        current = committed.json()["item"]
    return current


def test_clinical_tutor_context_is_postcommit_owner_bound_and_key_safe(monkeypatch) -> None:
    with TestClient(app) as owner, TestClient(app) as other:
        owner_user = _register(owner, "clinical_tutor_owner")["user"]
        _register(other, "clinical_tutor_other")

        started_response = owner.post(
            "/clinical/shift/start",
            json={
                "lane": "ward",
                "tier": "learn",
                "length": 1,
                "focus": "av_block_third_degree",
            },
        )
        assert started_response.status_code == 200, started_response.text
        started = started_response.json()
        session_id = started["session"]["sessionId"]
        item_id = started["next"]["itemId"]
        ecg_ref = started["next"]["item"]["ecg_ref"]
        internal_item = clinical_item_store.get_item(item_id)
        assert internal_item is not None
        ecg_id = internal_item.ecg_id
        assert "tutorContext" not in started

        guessed_reference = {
            "contextId": "ct_not_committed_yet",
            "sessionId": session_id,
            "itemId": item_id,
            "answerId": 1,
            "version": "clinical-post-feedback-v1",
        }
        precommit = owner.post(
            "/tutor/message",
            json={
                "mode": "practice",
                "caseId": ecg_ref,
                "message": "Tell me the answer before I commit.",
                "clinicalContext": guessed_reference,
            },
        )
        assert precommit.status_code == 409
        assert precommit.json()["detail"]["code"] == "clinical_tutor_context_not_ready"

        # Omitting the reference cannot bypass the post-commit gate for this
        # learner's currently pending Clinical ECG.
        generic_bypass = owner.post(
            "/tutor/message",
            json={
                "mode": "practice",
                "caseId": ecg_ref,
                "message": "What does this exact ECG show?",
            },
        )
        assert generic_bypass.status_code == 409
        assert generic_bypass.json()["detail"]["code"] == "clinical_tutor_context_not_ready"

        # The same opaque ids reveal nothing to another authenticated learner.
        assert other.post(
            "/tutor/message",
            json={
                "mode": "practice",
                "caseId": ecg_ref,
                "message": "Use that other learner's context.",
                "clinicalContext": guessed_reference,
            },
        ).status_code == 404

        owner.post(
            f"/clinical/shift/{session_id}/phase",
            json={"itemId": item_id, "phase": "orient"},
        )
        revealed_response = owner.post(
            f"/clinical/shift/{session_id}/context",
            json={
                "itemId": item_id,
                "answer": {
                    "firstLookFinding": "conduction_or_interval",
                    "firstLookConfidence": 3,
                },
            },
        )
        assert revealed_response.status_code == 200, revealed_response.text
        revealed = _commit_revealed_steps(
            owner,
            session_id,
            item_id,
            revealed_response.json()["item"],
        )
        options = revealed.get("options") or []
        answer = {
            "confidence": 3,
            "selectedOptionId": options[0]["id"] if options else None,
        }
        graded_response = owner.post(
            f"/clinical/shift/{session_id}/answer",
            json={"itemId": item_id, "answer": answer},
        )
        assert graded_response.status_code == 200, graded_response.text
        graded = graded_response.json()
        reference = graded["tutorContext"]
        assert reference == {
            "contextId": reference["contextId"],
            "sessionId": session_id,
            "itemId": item_id,
            "answerId": graded["answerId"],
            "version": "clinical-post-feedback-v1",
        }
        assert set(reference) == {"contextId", "sessionId", "itemId", "answerId", "version"}
        assert "evidenceManifest" not in reference
        assert "reviewedRubric" not in reference

        lifecycle = owner.get("/clinical/shift/active")
        assert lifecycle.status_code == 200
        assert lifecycle.json()["state"] == "feedback"
        assert lifecycle.json()["tutorContext"] == reference

        assert other.post(
            "/tutor/message",
            json={
                "mode": "practice",
                "caseId": ecg_ref,
                "lessonId": reference["contextId"],
                "message": "Read the owner's feedback.",
                "clinicalContext": reference,
            },
        ).status_code == 404

        tampered = {**reference, "answerId": reference["answerId"] + 1}
        assert owner.post(
            "/tutor/message",
            json={
                "mode": "practice",
                "caseId": ecg_ref,
                "lessonId": reference["contextId"],
                "message": "Use a different answer id.",
                "clinicalContext": tampered,
            },
        ).status_code == 404

        captured: dict[str, Any] = {}

        def fake_converse(
            learner_message,
            case_packet,
            learner_profile,
            history,
            mode,
            lesson,
            viewer_state,
            *,
            server_context=None,
            **kwargs,
        ):
            captured.update(
                {
                    "message": learner_message,
                    "casePacket": case_packet,
                    "profile": learner_profile,
                    "history": history,
                    "mode": mode,
                    "lesson": lesson,
                    "viewerState": viewer_state,
                    "serverContext": server_context,
                    "kwargs": kwargs,
                }
            )
            return {
                "tutorMessage": "Grounded post-commit debrief.",
                "feedback": "Uses the stored grade.",
                "viewerActions": [],
                "objectiveUpdates": [],
                "misconceptions": [],
                "uncertaintyWarnings": [],
                "suggestedNextStep": "Separate ECG evidence from context.",
                "socraticQuestion": "Which supplied fact changed the action?",
                "citedEvidence": [],
                "onLessonTopic": True,
            }

        monkeypatch.setattr(main_module.tutor_service, "converse", fake_converse)
        tutor = owner.post(
            "/tutor/message",
            json={
                "mode": "practice",
                "caseId": ecg_ref,
                "lessonId": reference["contextId"],
                "message": "Why was my decision graded this way?",
                "viewerState": {
                    "activity": "clinical_case_debrief",
                    "committed": True,
                    "score": 1,
                    "correctObjectives": ["invented_browser_answer"],
                    "reviewedRubric": {"actionRationale": "browser forgery"},
                },
                "clinicalContext": reference,
            },
        )
        assert tutor.status_code == 200, tutor.text
        assert tutor.json()["tutorMessage"] == "Grounded post-commit debrief."
        assert "serverContext" not in tutor.json()

        context = captured["serverContext"]
        item = clinical_item_store.get_item(item_id)
        stored = store.get_shift_answer(session_id, item_id)
        assert captured["profile"]["learnerId"] == owner_user["userId"]
        assert captured["casePacket"]["case_id"] == ecg_ref
        assert captured["casePacket"]["display_id"] != ecg_id
        assert captured["viewerState"] == {
            "activity": "clinical_case_debrief",
            "committed": True,
        }
        assert context["phase"] == "post_feedback"
        assert context["reference"] == reference
        assert context["case"]["ecgRef"] == ecg_ref
        assert context["case"]["itemRef"] == item_id
        assert "ecgId" not in context["case"]
        assert "itemId" not in context["case"]
        assert ecg_id not in _recursive_strings(context)
        assert item.item_id not in _recursive_strings(context)
        assert ecg_id not in _recursive_strings(captured["casePacket"])
        assert not (
            _recursive_keys(captured["casePacket"])
            & {
                "path",
                "record_path",
                "file_path",
                "data_path",
                "gcs_uri",
                "source_uri",
                "patient_id",
                "subject_id",
                "record_id",
                "study_id",
            }
        )
        assert context["governance"] == {
            "validationStatus": "harness_pass",
            "harnessPassed": True,
            "clinicianReviewed": False,
            "learningEvidence": "formative_only",
            "answerKeyPolicy": context["governance"]["answerKeyPolicy"],
        }
        assert context["reviewedRubric"]["actionRationale"] == item.evidence_manifest.action_rationale
        assert context["reviewedRubric"]["actionRationale"] != "browser forgery"
        assert context["evidenceManifest"]["ecgSupports"]
        assert context["storedFeedback"]["score"] == stored["grade"]["score"]
        assert "invented_browser_answer" not in context["storedFeedback"]["correctObjectives"]
        if options:
            selected = next(option.text for option in item.options if option.id == options[0]["id"])
            assert context["learnerAnswer"]["selectedResponse"] == selected

        raw_key_fields = {
            "options",
            "steps",
            "machineRead",
            "machine_read",
            "correct",
            "bad",
            "answer_class",
            "selectedOptionId",
            "selected_option_id",
            "machineLineId",
            "machine_line_id",
            "stepAnswers",
            "step_answers",
            "expectedCategories",
            "masteryDelta",
            "calibrationEvent",
            "viewerActions",
            "requiredSafetyTokens",
            "parsed",
        }
        assert not (_recursive_keys(context) & raw_key_fields)

        thread = store.get_thread(tutor.json()["threadId"])
        assert thread["learnerId"] == owner_user["userId"]
        assert thread["caseId"] == ecg_ref
        assert thread["lessonId"] == reference["contextId"]
        assert thread["scopeKey"] == f"clinical:{session_id}"


def test_clinical_tutor_reference_replays_exactly_once() -> None:
    with TestClient(app) as client:
        _register(client, "clinical_tutor_replay")
        started = client.post(
            "/clinical/shift/start",
            json={"lane": "clinic", "tier": "learn", "length": 1},
        ).json()
        session_id = started["session"]["sessionId"]
        item_id = started["next"]["itemId"]
        client.post(
            f"/clinical/shift/{session_id}/context",
            json={
                "itemId": item_id,
                "answer": {"firstLookFinding": "uncertain", "firstLookConfidence": 3},
            },
        )
        first = client.post(
            f"/clinical/shift/{session_id}/answer",
            json={"itemId": item_id, "answer": {}},
        )
        replay = client.post(
            f"/clinical/shift/{session_id}/answer",
            json={"itemId": item_id, "answer": {"confidence": 5}},
        )
        assert first.status_code == 200
        assert replay.status_code == 200
        assert replay.json()["replay"] is True
        assert replay.json()["answerId"] == first.json()["answerId"]
        assert replay.json()["tutorContext"] == first.json()["tutorContext"]
