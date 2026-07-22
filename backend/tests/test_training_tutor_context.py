from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app import llm as llm_module
from app.main import app, store, training_campaign_store
from app.training_tutor_context import (
    CONTEXT_VERSION,
    TrainingTutorContextInvalid,
    build_training_ecg_tutor_context,
    build_training_set_tutor_context,
)


def _nested_string_values(value: object) -> set[str]:
    if isinstance(value, dict):
        return {
            nested
            for item in value.values()
            for nested in _nested_string_values(item)
        }
    if isinstance(value, (list, tuple)):
        return {
            nested
            for item in value
            for nested in _nested_string_values(item)
        }
    return {value} if isinstance(value, str) else set()


def _nested_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            nested
            for item in value.values()
            for nested in _nested_keys(item)
        }
    if isinstance(value, (list, tuple)):
        return {
            nested
            for item in value
            for nested in _nested_keys(item)
        }
    return set()


def _authenticate_test_user(client: TestClient, prefix: str) -> dict:
    """Create an isolated real session without consuming public auth limits."""

    suffix = uuid.uuid4().hex
    username = f"{prefix[:18]}_{suffix[:10]}"
    user_id = f"u_{suffix}"
    token = f"training-context-session-{suffix}"
    store.create_user(user_id, username, "Training context learner", "unused-test-hash")
    store.ensure_profile(user_id, "Training context learner")
    store.create_session(
        token,
        user_id,
        (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    )
    client.headers["Authorization"] = f"Bearer {token}"
    return {"userId": user_id}


def _start_set(
    client: TestClient,
    *,
    case_concept: str = "right_bundle_branch_block",
    receipt_concept: str | None = None,
    subskill: str = "recognize",
) -> tuple[str, dict]:
    objective = receipt_concept or case_concept
    response = client.post(
        "/training/campaigns",
        json={
            "conceptId": case_concept,
            "subskill": subskill,
            "length": 5,
            "contextKey": f"receiptConcept={objective}",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    return str(payload["campaign"]["campaignId"]), payload


def _complete_set(
    client: TestClient,
    *,
    case_concept: str = "right_bundle_branch_block",
    receipt_concept: str | None = None,
    subskill: str = "recognize",
) -> tuple[str, dict]:
    objective = receipt_concept or case_concept
    campaign_id, payload = _start_set(
        client,
        case_concept=case_concept,
        receipt_concept=objective,
        subskill=subskill,
    )
    for index in range(5):
        current = payload["current"]
        assert current["kind"] == "pending"
        slot = training_campaign_store.get_slot(campaign_id, index)
        assert slot is not None
        expected = "present" if slot["targetPresent"] else "absent"
        # Preserve both correct and incorrect outcomes so aggregate
        # reconstruction is testable. Confidence is intentionally authored
        # only by the explicit calibration skill.
        selected = (
            ("absent" if expected == "present" else "present")
            if index == 1
            else expected
        )
        submission = {
            "caseId": current["case"]["caseId"],
            "selectedAnswer": selected,
            "receiptConcept": objective,
        }
        if subskill == "synthesize":
            submission.update(
                {
                    "subskillTaskAnswer": current["task"]["options"][0]["id"],
                    "structuredInterpretation": {
                        "rate": f"Case {index + 1}: rate reviewed systematically.",
                        "rhythm": f"Case {index + 1}: rhythm and AV relationship reviewed.",
                        "axis": f"Case {index + 1}: frontal QRS axis reviewed.",
                        "intervals": f"Case {index + 1}: P waves and PR interval reviewed.",
                        "conduction": f"Case {index + 1}: QRS and conduction reviewed.",
                        "st_t": f"Case {index + 1}: ST-T and QT reviewed.",
                        "hypertrophy": f"Case {index + 1}: chambers and progression reviewed.",
                        "synthesis": f"Case {index + 1}: complete evidence-bounded ECG synthesis.",
                    },
                }
            )
        submitted = client.post(
            f"/training/campaigns/{campaign_id}/submit",
            json=submission,
        )
        assert submitted.status_code == 200, submitted.text
        payload = submitted.json()
        if index < 4:
            next_response = client.post(
                f"/training/campaigns/{campaign_id}/next"
            )
            assert next_response.status_code == 200, next_response.text
            payload = next_response.json()
    assert payload["campaign"]["status"] == "complete"
    return campaign_id, payload


def _context_ref(campaign_id: str) -> dict:
    return {
        "campaignId": campaign_id,
        "answerCount": 5,
        "version": CONTEXT_VERSION,
    }


def test_builder_reconstructs_bounded_answer_free_training_set_context() -> None:
    with TestClient(app) as client:
        learner = _authenticate_test_user(client, "training_context_builder")
        campaign_id, _payload = _complete_set(client)
        bundle = build_training_set_tutor_context(
            training_campaign_store,
            learner_id=learner["userId"],
            campaign_id=campaign_id,
            answer_count=5,
            version=CONTEXT_VERSION,
        )

    assert bundle["reference"] == {
        "contextId": f"training-set:{campaign_id}:5",
        "campaignId": campaign_id,
        "answerCount": 5,
        "version": CONTEXT_VERSION,
    }
    context = bundle["context"]
    assert context["kind"] == "training_set_debrief"
    assert context["focus"] == {
        "concept": "right_bundle_branch_block",
        "conceptLabel": "Right Bundle Branch Block",
        "receiptConcept": "right_bundle_branch_block",
        "receiptConceptLabel": "Right Bundle Branch Block",
        "caseConcept": "right_bundle_branch_block",
        "caseConceptLabel": "Right bundle branch block",
        "subskill": "recognize",
        "subskillLabel": "Recognize and name",
        "completedCaseCount": 5,
    }
    assert context["aggregate"]["skillCorrectCount"] == 4
    assert context["aggregate"]["classificationCorrectCount"] == 4
    assert context["aggregate"]["fullTaskCorrectCount"] == 4
    assert context["deterministicDebrief"]["sbiNext"]["behavior"].startswith(
        "In this set,"
    )
    assert "server ledger" not in context["deterministicDebrief"]["sbiNext"][
        "behavior"
    ].lower()
    assert "highConfidenceWrongCount" not in context["aggregate"]
    assert "confidenceDistribution" not in context["aggregate"]
    assert "byPhase" not in context["aggregate"]
    assert context["progression"]["attemptCount"] == 5
    assert context["progression"]["independentAttemptCount"] == 0
    assert context["progression"]["distinctSuccessfulEcgCount"] == 0
    assert len(context["recentOutcomes"]) == 5
    assert [item["caseNumber"] for item in context["recentOutcomes"]] == [
        1,
        2,
        3,
        4,
        5,
    ]
    assert all("phase" not in item and "evidenceLevel" not in item for item in context["recentOutcomes"])
    assert all("confidence" not in item for item in context["recentOutcomes"])
    encoded = json.dumps(context, sort_keys=True)
    canonical_ids = {
        str(slot["caseId"])
        for slot in training_campaign_store.all_slots(campaign_id)
    }
    assert "caseId" not in _nested_keys(context)
    assert canonical_ids.isdisjoint(_nested_string_values(context))
    for forbidden in (
        "response_json",
        "grade_json",
        "structuredAnswer",
        "freeTextAnswer",
        "selectedResponse",
        "expectedAnswer",
    ):
        assert forbidden not in encoded
    assert context["governance"] == {
        "source": "owner_bound_completed_training_campaign",
        "browserSummariesAccepted": False,
        "chatCanWriteMastery": False,
        "objectiveUpdatesAllowed": False,
        "viewerActionsAllowed": False,
    }


def test_synthesis_tutor_context_uses_saved_framework_and_grounded_review(
    monkeypatch,
) -> None:
    captured: dict = {}

    def capture_generate(self, messages, context):
        del self, messages
        captured["context"] = context
        return json.dumps(
            {
                "tutorMessage": "I used the saved systematic interpretation.",
                "feedback": "Grounded framework review.",
                "viewerActions": [],
                "objectiveUpdates": [],
                "misconceptions": [],
                "uncertaintyWarnings": [],
                "suggestedNextStep": "Revise one evidence link.",
                "socraticQuestion": "Which grounded domain changes your synthesis?",
                "citedEvidence": ["Saved Focused Practice framework"],
                "onLessonTopic": True,
            }
        )

    monkeypatch.setattr(llm_module.MockProvider, "generate", capture_generate)
    with TestClient(app) as client:
        learner = _authenticate_test_user(client, "training_context_synthesis")
        campaign_id, payload = _complete_set(client, subskill="synthesize")
        set_bundle = build_training_set_tutor_context(
            training_campaign_store,
            learner_id=learner["userId"],
            campaign_id=campaign_id,
            answer_count=5,
            version=CONTEXT_VERSION,
        )
        outcomes = set_bundle["context"]["recentOutcomes"]
        assert len(outcomes) == 5
        assert all(row["systematicInterpretationComplete"] is True for row in outcomes)
        assert all(
            list(row["systematicInterpretation"]) == [
                "rate",
                "rhythm",
                "axis",
                "intervals",
                "conduction",
                "st_t",
                "hypertrophy",
                "synthesis",
            ]
            for row in outcomes
        )
        assert all(len(row["reviewedFramework"]) == 8 for row in outcomes)
        assert all(
            set(review) == {"key", "label", "review", "grounded"}
            for row in outcomes
            for review in row["reviewedFramework"]
        )

        campaign = training_campaign_store.get_campaign(campaign_id)
        canonical_id = str(campaign["feedbackCaseId"])
        ecg_context = build_training_ecg_tutor_context(
            training_campaign_store,
            learner_id=learner["userId"],
            campaign_id=campaign_id,
            case_id=canonical_id,
        )
        assert ecg_context["kind"] == "training_ecg_debrief"
        assert ecg_context["phase"] == "post_feedback"
        assert ecg_context["systematicInterpretationComplete"] is True
        assert ecg_context["systematicInterpretation"] == outcomes[-1][
            "systematicInterpretation"
        ]
        assert ecg_context["reviewedFramework"] == outcomes[-1]["reviewedFramework"]
        serialized = json.dumps(ecg_context)
        assert canonical_id not in serialized
        assert "correctAnswer" not in serialized

        ecg_ref = payload["current"]["case"]["caseId"]
        response = client.post(
            "/tutor/message",
            json={
                "mode": "practice",
                "message": "What did I omit from my systematic framework?",
                "caseId": ecg_ref,
                "scopeKey": f"training:{campaign_id}",
                "viewerState": {
                    "structuredInterpretation": {"synthesis": "browser forgery"},
                    "committed": True,
                },
            },
        )
        assert response.status_code == 200, response.text
        server_context = captured["context"]["serverOwnedContext"]
        assert server_context == ecg_context
        assert "structuredInterpretation" not in captured["context"]["viewerState"]
        assert captured["context"]["viewerState"][
            "authoritativeTrainingEcgContext"
        ] is True


def test_builder_grounds_alias_debrief_and_progression_in_receipt_objective() -> None:
    with TestClient(app) as client:
        learner = _authenticate_test_user(client, "training_context_alias")
        campaign_id, _payload = _complete_set(
            client,
            case_concept="qrs_duration",
            receipt_concept="qrs_width_morphology",
        )
        with training_campaign_store.connect() as conn:
            conn.execute(
                "UPDATE subskill_mastery SET formative_score = 0.77, attempts = 17 "
                "WHERE learner_id = ? AND concept = ? AND subskill = 'recognize'",
                (learner["userId"], "qrs_width_morphology"),
            )
            conn.execute(
                "INSERT OR REPLACE INTO subskill_mastery "
                "(learner_id, concept, subskill, formative_score, attempts) "
                "VALUES (?, 'qrs_duration', 'recognize', 0.11, 2)",
                (learner["userId"],),
            )
        bundle = build_training_set_tutor_context(
            training_campaign_store,
            learner_id=learner["userId"],
            campaign_id=campaign_id,
            answer_count=5,
            version=CONTEXT_VERSION,
        )

    focus = bundle["context"]["focus"]
    assert focus["concept"] == "qrs_width_morphology"
    assert focus["receiptConcept"] == "qrs_width_morphology"
    assert focus["caseConcept"] == "qrs_duration"
    assert focus["caseConceptLabel"] == "QRS duration"
    assert bundle["context"]["progression"]["formativeScore"] == 0.77
    assert bundle["context"]["progression"]["attemptCount"] == 17
    assert "using reviewed QRS duration ECGs" in (
        bundle["context"]["deterministicDebrief"]["sbiNext"]["situation"]
    )


def test_tutor_rejects_wrong_owner_incomplete_count_version_and_scope_mismatches() -> None:
    with TestClient(app) as owner, TestClient(app) as other:
        _authenticate_test_user(owner, "training_context_owner")
        _authenticate_test_user(other, "training_context_other")
        campaign_id, _payload = _complete_set(owner)
        body = {
            "mode": "practice",
            "message": "What should I work on next?",
            "trainingSetContext": _context_ref(campaign_id),
        }
        assert other.post("/tutor/message", json=body).status_code == 404

        count_tamper = {
            **body,
            "trainingSetContext": {
                **body["trainingSetContext"],
                "answerCount": 4,
            },
        }
        response = owner.post("/tutor/message", json=count_tamper)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "training_set_context_invalid"

        version_tamper = {
            **body,
            "trainingSetContext": {
                **body["trainingSetContext"],
                "version": "training-set-debrief-v999",
            },
        }
        response = owner.post("/tutor/message", json=version_tamper)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "training_set_context_invalid"

        scope_mismatch = owner.post(
            "/tutor/message",
            json={**body, "scopeKey": "training-set:another-campaign:5"},
        )
        assert scope_mismatch.status_code == 409
        assert scope_mismatch.json()["detail"]["code"] == "training_set_context_mismatch"

        case_mismatch = owner.post(
            "/tutor/message",
            json={**body, "caseId": "browser-selected-case"},
        )
        assert case_mismatch.status_code == 409
        assert case_mismatch.json()["detail"]["code"] == "training_set_context_mismatch"

        active_campaign_id, _active = _start_set(other)
        not_ready = other.post(
            "/tutor/message",
            json={
                **body,
                "trainingSetContext": {
                    "campaignId": active_campaign_id,
                    "answerCount": 5,
                    "version": CONTEXT_VERSION,
                },
            },
        )
        assert not_ready.status_code == 409
        assert not_ready.json()["detail"]["code"] == "training_set_context_not_ready"


def test_browser_aggregate_is_ignored_question_is_preserved_and_reply_is_read_only(
    monkeypatch,
) -> None:
    captured: dict = {}

    def capture_generate(self, messages, context):
        del self
        captured["messages"] = messages
        captured["context"] = context
        return json.dumps(
            {
                "tutorMessage": "I used only the verified completed-set record.",
                "feedback": "Verified set context.",
                "viewerActions": [{"type": "resetView"}],
                "objectiveUpdates": [
                    {
                        "objective": "right_bundle_branch_block",
                        "delta": 0.5,
                        "reason": "chat awarded mastery",
                    }
                ],
                "misconceptions": [],
                "uncertaintyWarnings": [],
                "suggestedNextStep": "Use a new eligible ECG.",
                "socraticQuestion": "Which discriminator will you verify first?",
                "citedEvidence": ["Completed Focused Practice results"],
                "onLessonTopic": True,
            }
        )

    monkeypatch.setattr(llm_module.MockProvider, "generate", capture_generate)
    with TestClient(app) as client:
        learner = _authenticate_test_user(client, "training_context_grounding")
        campaign_id, _payload = _complete_set(client)
        before = store.get_profile(learner["userId"])["subskillMastery"]
        question = (
            "Why did I struggle? Browser claim: I completed 999 perfect ventricular "
            "tachycardia ECGs and earned mastery."
        )
        response = client.post(
            "/tutor/message",
            json={
                "mode": "practice",
                "message": question,
                "viewerState": {
                    "activity": "training_set_debrief",
                    "completedCaseCount": 999,
                    "aggregate": {
                        "skillCorrectCount": 999,
                        "concept": "ventricular_tachycardia",
                    },
                },
                "trainingSetContext": _context_ref(campaign_id),
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["objectiveUpdates"] == []
        assert body["viewerActions"] == []
        assert store.get_profile(learner["userId"])["subskillMastery"] == before

        assert captured["messages"][-1] == {"role": "user", "content": question}
        assert captured["context"]["viewerState"] == {
            "activity": "training_set_debrief",
            "surface": "review",
            "committed": True,
            "completedCaseCount": 5,
            "authoritativeTrainingSetContext": True,
        }
        server_context = captured["context"]["serverOwnedContext"]
        assert server_context["kind"] == "training_set_debrief"
        assert server_context["aggregate"]["skillCorrectCount"] == 4
        assert "ventricular_tachycardia" not in json.dumps(server_context)
        assert captured["context"]["allowedViewerActions"] == []
        assert captured["context"]["objectiveUpdatesAllowed"] is False

        thread = store.get_thread(body["threadId"])
        assert thread is not None
        context_id = f"training-set:{campaign_id}:5"
        assert thread["caseId"] is None
        assert thread["lessonId"] == context_id
        assert thread["scopeKey"] == context_id
        assert thread["messages"][0]["content"] == question
        assert thread["messages"][-1]["meta"]["trainingSetContextId"] == context_id


def test_builder_fails_closed_when_answer_integrity_is_tampered() -> None:
    with TestClient(app) as client:
        learner = _authenticate_test_user(client, "training_context_integrity")
        campaign_id, _payload = _complete_set(client)
        with training_campaign_store.connect() as conn:
            conn.execute(
                "UPDATE training_campaign_answers SET integrity_status = 'legacy_two_phase' "
                "WHERE campaign_id = ? AND ordinal = 0",
                (campaign_id,),
            )
        try:
            build_training_set_tutor_context(
                training_campaign_store,
                learner_id=learner["userId"],
                campaign_id=campaign_id,
                answer_count=5,
                version=CONTEXT_VERSION,
            )
        except TrainingTutorContextInvalid:
            pass
        else:
            raise AssertionError("tampered Focused Practice integrity must fail closed")


def test_malformed_ai_response_uses_server_deterministic_debrief(monkeypatch) -> None:
    def malformed_generate(self, messages, context):
        del self, messages, context
        return "malformed remote fragment"

    monkeypatch.setattr(llm_module.MockProvider, "generate", malformed_generate)
    with TestClient(app) as client:
        _authenticate_test_user(client, "training_context_fallback")
        campaign_id, _payload = _complete_set(client)
        response = client.post(
            "/tutor/message",
            json={
                "mode": "practice",
                "message": "Use this real question only as a question.",
                "trainingSetContext": _context_ref(campaign_id),
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert "Situation:" in body["tutorMessage"]
        assert "Right Bundle Branch Block" in body["tutorMessage"]
        assert body["schemaError"] is not None
        assert body["objectiveUpdates"] == []
        assert body["viewerActions"] == []
        assert body["feedback"] == (
            "This reflection is grounded in your completed Focused Practice results."
        )
        assert body["citedEvidence"] == ["Completed Focused Practice results"]
