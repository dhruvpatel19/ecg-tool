from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import uuid

from fastapi.testclient import TestClient

from app import rapid_routes
from app.grading import ANSWER_KEYWORDS
from app.main import app, repo, store
from app.ontology import concept_label
from app.rapid_tutor_context import (
    CONTEXT_VERSION,
    build_rapid_round_tutor_context,
    deterministic_rapid_tutor_response,
)


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


def _start(client: TestClient, **overrides) -> dict:
    body = {
        "learnerId": "demo",
        "pace": "untimed",
        "length": 1,
        "contextKey": "?surface=rapid-v2",
        "exclusions": [],
        "contractVersion": "mixed-v2",
        "practiceMode": "mixed",
        "questionDepth": "focused",
    }
    body.update(overrides)
    response = client.post("/rapid/rounds", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def _correct_task_responses(round_id: str) -> dict[str, object]:
    session = store.get_rapid_round(round_id)
    assert session is not None
    case_id = str(session["pendingCaseId"])
    case = repo.get_case(case_id)
    assert case is not None
    packet = session["pendingTestedObjectiveManifest"]["taskPacket"]
    responses: dict[str, object] = {}
    for task in packet["tasks"]:
        grading = task["grading"]
        task_id = task["id"]
        objective_id = grading["objectiveId"]
        answer_text = (
            f"{(case.get('ptbxl_plus') or {}).get('features', {}).get('heart_rate')} bpm"
            if objective_id == "rate"
            else (ANSWER_KEYWORDS.get(objective_id) or [concept_label(objective_id)])[0]
        )
        if task["type"] == "short_answer":
            responses[task_id] = answer_text
        elif task["type"] == "full_interpretation":
            responses[task_id] = {
                "impression": answer_text,
                "rhythm": "Concise rhythm assessment",
            }
        elif task["type"] == "single_choice":
            responses[task_id] = grading["correctOptionId"]
        elif task["type"] == "numeric_fill_in":
            responses[task_id] = grading["expectedValue"]
        elif task["type"] == "point_localization":
            roi = next(
                row
                for row in case["ptbxl_plus"]["fiducials"]["rois"]
                if row["concept"] == grading["objectiveId"]
            )
            responses[task_id] = {
                "point": {
                    "lead": roi["lead"],
                    "timeSec": (roi["timeStartSec"] + roi["timeEndSec"]) / 2,
                    "amplitudeMv": (roi["ampMinMv"] + roi["ampMaxMv"]) / 2,
                }
            }
        else:
            raise AssertionError(f"Unhandled mixed task type: {task['type']}")
    return responses


def test_public_numeric_task_exposes_input_bounds_without_answer_key() -> None:
    public = rapid_routes._public_task_packet(
        {
            "version": "rapid-task-packet-v1",
            "display": {"kind": "twelve_lead"},
            "tasks": [
                {
                    "id": "task_rate",
                    "type": "numeric_fill_in",
                    "prompt": "Estimate the ventricular rate.",
                    "unit": "bpm",
                    "minValue": 20,
                    "maxValue": 250,
                    "step": 1,
                    "required": True,
                    "grading": {"expectedValue": 72, "tolerance": 5},
                }
            ],
        }
    )
    assert public is not None
    task = public["tasks"][0]
    assert task["minValue"] == 20
    assert task["maxValue"] == 250
    assert task["step"] == 1
    assert "grading" not in task
    assert "expectedValue" not in json.dumps(public)


def test_rate_never_becomes_a_generic_finding_choice_against_rhythm_labels() -> None:
    case = {
        "case_id": "rate-choice-regression",
        "supported_objectives": [
            "normal_ecg",
            "rate",
            "sinus_rhythm",
            "axis_normal",
            "qt_interval",
        ],
    }
    session = {"roundId": "rate-choice-regression", "position": 0}

    assert rapid_routes._choice_distractors(case, "rate") == []
    assert rapid_routes._single_choice_task(case, session, "rate", 1) is None


def test_single_choice_options_stay_within_one_clinical_answer_class() -> None:
    mapped_count = sum(
        len(answer_class)
        for answer_class in rapid_routes._SINGLE_CHOICE_ANSWER_CLASSES
    )
    assert len(rapid_routes._SINGLE_CHOICE_CLASS_BY_OBJECTIVE) == mapped_count

    for answer_class in rapid_routes._SINGLE_CHOICE_ANSWER_CLASSES:
        for objective_id in answer_class:
            case = {
                "case_id": f"choice-{objective_id}",
                "supported_objectives": [objective_id],
            }
            distractors = rapid_routes._choice_distractors(case, objective_id)
            assert 2 <= len(distractors) <= 3, objective_id
            assert set(distractors).issubset(answer_class), objective_id

            task = rapid_routes._single_choice_task(
                case,
                {"roundId": "answer-class-audit", "position": 0},
                objective_id,
                1,
            )
            assert task is not None, objective_id
            expected_labels = {
                concept_label(value) for value in (objective_id, *distractors)
            }
            assert {option["label"] for option in task["options"]} == expected_labels
            correct_label = next(
                option["label"]
                for option in task["options"]
                if option["id"] == task["grading"]["correctOptionId"]
            )
            assert correct_label == concept_label(objective_id)


def test_single_choice_fails_closed_when_supported_truths_exhaust_contrasts() -> None:
    case = {
        "case_id": "axis-choice-exhausted",
        "supported_objectives": ["axis_normal", "left_axis_deviation"],
    }
    session = {"roundId": "axis-choice-exhausted", "position": 0}

    assert rapid_routes._choice_distractors(case, "axis_normal") == [
        "right_axis_deviation"
    ]
    assert rapid_routes._single_choice_task(case, session, "axis_normal", 1) is None


def test_focused_packet_skips_rate_choice_and_keeps_task_diversity(monkeypatch) -> None:
    case = {
        "case_id": "mixed-choice-fallback",
        "supported_objectives": [
            "normal_ecg",
            "rate",
            "atrial_fibrillation",
        ],
    }
    session = {
        "roundId": "mixed-choice-fallback",
        "position": 0,
        "contextKey": rapid_routes._with_round_contract(
            "",
            contract_version="mixed-v2",
            practice_mode="mixed",
            question_depth="focused",
        ),
    }
    monkeypatch.setattr(
        rapid_routes,
        "_ordered_task_targets",
        lambda _case, _focus: ["normal_ecg", "rate", "atrial_fibrillation"],
    )

    def numeric_task(_case, _session, index, *, preferred_objective=None):
        del preferred_objective
        return {
            "id": f"task_numeric_{index}",
            "type": "numeric_fill_in",
            "prompt": "Estimate the ventricular rate.",
            "skillId": "measure",
            "grading": {
                "objectiveId": "rate",
                "subskill": "measure",
            },
        }

    monkeypatch.setattr(rapid_routes, "_numeric_task", numeric_task)
    monkeypatch.setattr(rapid_routes, "_localization_task", lambda *args, **kwargs: None)

    packet = rapid_routes._build_mixed_task_packet(
        case,
        session,
        focus_concept=None,
    )
    assert [task["type"] for task in packet["tasks"]] == [
        "short_answer",
        "single_choice",
        "numeric_fill_in",
    ]
    choice = packet["tasks"][1]
    assert choice["grading"]["objectiveId"] == "atrial_fibrillation"
    assert "Rate" not in {option["label"] for option in choice["options"]}


def test_mixed_v2_pending_packet_is_blinded_and_grades_only_frozen_tasks() -> None:
    with TestClient(app) as client:
        _register(client, "rapid_mixed_contract")
        started = _start(client, questionDepth="complete")
        round_id = started["round"]["roundId"]
        assert started["round"]["contractVersion"] == "mixed-v2"
        assert started["round"]["practiceMode"] == "mixed"
        assert started["round"]["questionDepth"] == "complete"
        assert started["round"]["contextKey"] == "?surface=rapid-v2"

        served = client.post(f"/rapid/rounds/{round_id}/next", json={})
        assert served.status_code == 200, served.text
        current = served.json()["current"]
        task_packet = current["taskPacket"]
        assert task_packet["version"] == "rapid-task-packet-v1"
        assert 1 <= len(task_packet["tasks"]) <= 5
        assert task_packet["tasks"][0]["type"] == "full_interpretation"
        encoded_pending = json.dumps(task_packet, sort_keys=True)
        for forbidden in (
            '"grading"',
            '"objectiveId"',
            '"correctOptionId"',
            '"expectedValue"',
            '"tolerance"',
        ):
            assert forbidden not in encoded_pending

        unknown = client.post(
            f"/rapid/rounds/{round_id}/submit",
            json={
                "caseId": current["case"]["caseId"],
                "taskResponses": {"not-a-frozen-task": "probe"},
                "structuredAnswer": {
                    "selectedConcepts": ["atrial_fibrillation"]
                },
            },
        )
        assert unknown.status_code == 422
        assert unknown.json()["detail"]["code"] == "rapid_task_response_unknown"

        responses = _correct_task_responses(round_id)
        submitted = client.post(
            f"/rapid/rounds/{round_id}/submit",
            json={
                "caseId": current["case"]["caseId"],
                "taskResponses": responses,
                # Legacy selections are deliberately ignored by mixed-v2; an
                # unasked claim cannot become a receipt or an overcall penalty.
                "structuredAnswer": {
                    "selectedConcepts": ["definitely_not_a_real_objective"]
                },
            },
        )
        assert submitted.status_code == 200, submitted.text
        body = submitted.json()
        feedback = body["answer"]["grade"]["taskFeedback"]
        assert len(feedback) == len(task_packet["tasks"])
        assert all(row["correct"] for row in feedback)
        assert feedback[0]["supportingFieldsEvidence"] == "formative_only"
        assert body["answer"]["grade"]["overcalledObjectives"] == []
        assert len(body["answer"]["result"]["competencyOutcomes"]) == len(task_packet["tasks"])
        assert all(
            row["correct"]
            for row in body["answer"]["result"]["competencyOutcomes"]
        )
        assert all(
            receipt["concept"] != "definitely_not_a_real_objective"
            for receipt in body["receipts"]
        )
        stored = store.get_rapid_answer(
            round_id, str(store.get_rapid_round(round_id)["feedbackCaseId"])
        )
        assert stored is not None
        assert stored["response"]["taskResponses"] == responses
        assert stored["integrityStatus"] == "atomic_v2"


def test_timed_mixed_v2_requires_readiness_activation_and_uses_depth_clock() -> None:
    with TestClient(app) as client:
        _register(client, "rapid_mixed_clock")
        started = _start(
            client,
            pace="ward",
            questionDepth="quick",
        )
        round_id = started["round"]["roundId"]
        assert started["round"]["deadlineSeconds"] == 60
        served = client.post(f"/rapid/rounds/{round_id}/next", json={}).json()
        responses = _correct_task_responses(round_id)

        early = client.post(
            f"/rapid/rounds/{round_id}/submit",
            json={
                "caseId": served["current"]["case"]["caseId"],
                "taskResponses": responses,
            },
        )
        assert early.status_code == 409
        assert early.json()["detail"]["code"] == "rapid_item_not_ready"
        assert store.get_rapid_answer(
            round_id, str(store.get_rapid_round(round_id)["pendingCaseId"])
        ) is None

        activated = client.post(
            f"/rapid/rounds/{round_id}/next", json={"activate": True}
        )
        assert activated.status_code == 200, activated.text
        assert activated.json()["round"]["pendingStartedAt"] is not None
        committed = client.post(
            f"/rapid/rounds/{round_id}/submit",
            json={
                "caseId": served["current"]["case"]["caseId"],
                "taskResponses": responses,
            },
        )
        assert committed.status_code == 200, committed.text
        assert committed.json()["answer"]["result"]["responseMs"] >= 0


def test_timed_out_mixed_v2_keeps_formative_feedback_but_scores_zero() -> None:
    with TestClient(app) as client:
        _register(client, "rapid_mix_timeout")
        started = _start(client, pace="ward", questionDepth="quick")
        round_id = started["round"]["roundId"]
        served = client.post(f"/rapid/rounds/{round_id}/next", json={}).json()
        activated = client.post(
            f"/rapid/rounds/{round_id}/next", json={"activate": True}
        )
        assert activated.status_code == 200, activated.text
        expired = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        with store.connect() as conn:
            conn.execute(
                "UPDATE rapid_rounds SET pending_deadline_at = ? WHERE round_id = ?",
                (expired, round_id),
            )

        submitted = client.post(
            f"/rapid/rounds/{round_id}/submit",
            json={
                "caseId": served["current"]["case"]["caseId"],
                "taskResponses": _correct_task_responses(round_id),
            },
        )
        assert submitted.status_code == 200, submitted.text
        answer = submitted.json()["answer"]
        assert answer["grade"]["score"] == 0.0
        assert answer["result"]["score"] == 0.0
        assert answer["result"]["timedOut"] is True
        assert all(row["correct"] for row in answer["grade"]["taskFeedback"])
        assert all(row["timedOut"] for row in answer["grade"]["taskFeedback"])
        assert "scored 0" in answer["grade"]["feedback"]
        assert not any(
            receipt.get("accepted") and receipt.get("correct", True)
            for receipt in submitted.json()["receipts"]
        )


def test_focused_measurement_handoff_freezes_and_records_the_exact_skill() -> None:
    with TestClient(app) as client:
        _register(client, "rapid_mix_measure")
        started = _start(
            client,
            focusConcept="rate",
            focusSubskill="measure",
            questionDepth="focused",
        )
        round_id = started["round"]["roundId"]
        served = client.post(f"/rapid/rounds/{round_id}/next", json={})
        assert served.status_code == 200, served.text
        public_tasks = served.json()["current"]["taskPacket"]["tasks"]
        assert any(task["skillId"] == "measure" for task in public_tasks)
        private_tasks = store.get_rapid_round(round_id)[
            "pendingTestedObjectiveManifest"
        ]["taskPacket"]["tasks"]
        assert any(
            task["grading"]["objectiveId"] == "rate"
            and task["grading"]["subskill"] == "measure"
            for task in private_tasks
        )
        submitted = client.post(
            f"/rapid/rounds/{round_id}/submit",
            json={
                "caseId": served.json()["current"]["case"]["caseId"],
                "taskResponses": _correct_task_responses(round_id),
            },
        )
        assert submitted.status_code == 200, submitted.text
        assert any(
            receipt["concept"] == "rate"
            and receipt["subskill"] == "measure"
            and receipt["accepted"] is True
            for receipt in submitted.json()["receipts"]
        )


def test_complete_synthesis_handoff_runs_but_cannot_mint_unverified_mastery() -> None:
    with TestClient(app) as client:
        user = _register(client, "rapid_mix_synthesis")
        before_synthesis = [
            row
            for row in store.get_profile(user["userId"])["subskillMastery"]
            if row["concept"] == "integrated_interpretation"
            and row["subskill"] == "synthesize"
        ]
        started = _start(
            client,
            focusConcept="normal_ecg",
            focusSubskill="synthesize",
            questionDepth="complete",
            contextKey=(
                "?focus=normal_ecg&receiptConcept=integrated_interpretation"
                "&subskill=synthesize"
            ),
        )
        round_id = started["round"]["roundId"]
        served = client.post(f"/rapid/rounds/{round_id}/next", json={})
        assert served.status_code == 200, served.text
        assert served.json()["current"]["taskPacket"]["tasks"][0]["type"] == "full_interpretation"

        submitted = client.post(
            f"/rapid/rounds/{round_id}/submit",
            json={
                "caseId": served.json()["current"]["case"]["caseId"],
                "taskResponses": _correct_task_responses(round_id),
            },
        )
        assert submitted.status_code == 200, submitted.text
        synthesis_receipts = [
            receipt
            for receipt in submitted.json()["receipts"]
            if receipt["subskill"] == "synthesize"
        ]
        assert len(synthesis_receipts) == 1
        assert synthesis_receipts[0]["concept"] == "integrated_interpretation"
        assert synthesis_receipts[0]["accepted"] is False
        assert synthesis_receipts[0]["evidenceLevel"] == "none"
        assert not any(
            entry["subskill"] == "synthesize"
            for entry in submitted.json()["answer"]["testedObjectiveManifest"][
                "objectives"
            ]
        )
        after_synthesis = [
            row
            for row in store.get_profile(user["userId"])["subskillMastery"]
            if row["concept"] == "integrated_interpretation"
            and row["subskill"] == "synthesize"
        ]
        assert after_synthesis == before_synthesis


def test_complete_synthesis_handoff_rejects_unregistered_or_ambiguous_targets() -> None:
    with TestClient(app) as client:
        _register(client, "rapid_synth_guard")
        common = {
            "pace": "untimed",
            "length": 1,
            "contractVersion": "mixed-v2",
            "questionDepth": "complete",
            "focusSubskill": "synthesize",
        }
        for payload in (
            common,
            {
                **common,
                "focusConcept": "normal_ecg",
                "contextKey": "?receiptConcept=not_a_registered_objective",
            },
            {
                **common,
                "focusConcept": "normal_ecg",
                "contextKey": (
                    "?receiptConcept=integrated_interpretation"
                    "&receiptConcept=normal_ecg"
                ),
            },
        ):
            response = client.post("/rapid/rounds", json=payload)
            assert response.status_code == 422
            assert (
                response.json()["detail"]["code"]
                == "rapid_mixed_synthesis_target_invalid"
            )


def test_adaptive_mixed_v2_reranks_each_slot_and_atomic_v2_debrief_is_sbi_next(
    monkeypatch,
) -> None:
    calls = 0
    original_next_case = rapid_routes.next_case

    def counted_next_case(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original_next_case(*args, **kwargs)

    monkeypatch.setattr(rapid_routes, "next_case", counted_next_case)
    with TestClient(app) as client:
        user = _register(client, "rapid_mixed_adaptive")
        started = _start(
            client,
            length=2,
            practiceMode="adaptive",
            questionDepth="quick",
        )
        round_id = started["round"]["roundId"]
        first = client.post(f"/rapid/rounds/{round_id}/next", json={}).json()
        first_submit = client.post(
            f"/rapid/rounds/{round_id}/submit",
            json={
                "caseId": first["current"]["case"]["caseId"],
                "taskResponses": _correct_task_responses(round_id),
            },
        )
        assert first_submit.status_code == 200, first_submit.text

        second = client.post(f"/rapid/rounds/{round_id}/next", json={})
        assert second.status_code == 200, second.text
        second_body = second.json()
        second_submit = client.post(
            f"/rapid/rounds/{round_id}/submit",
            json={
                "caseId": second_body["current"]["case"]["caseId"],
                "taskResponses": _correct_task_responses(round_id),
            },
        )
        assert second_submit.status_code == 200, second_submit.text
        assert calls >= 2

        bundle = build_rapid_round_tutor_context(
            store,
            learner_id=user["userId"],
            round_id=round_id,
            answer_count=2,
            version=CONTEXT_VERSION,
        )
        sbi_next = bundle["context"]["deterministicDebrief"]["sbiNext"]
        assert set(sbi_next) == {"situation", "behavior", "impact", "next"}
        response = deterministic_rapid_tutor_response(bundle["context"])
        assert response["tutorMessage"].startswith("Situation:")
        assert "Behavior:" in response["tutorMessage"]
        assert "Impact:" in response["tutorMessage"]
        assert "Next:" in response["tutorMessage"]


def test_invalid_focus_subskill_and_oversized_free_text_fail_closed() -> None:
    with TestClient(app) as client:
        _register(client, "rapid_mix_valid")
        invalid = client.post(
            "/rapid/rounds",
            json={
                "pace": "untimed",
                "length": 1,
                "focusSubskill": "invented_skill",
                "contractVersion": "mixed-v2",
            },
        )
        assert invalid.status_code == 422
        assert invalid.json()["detail"]["code"] == "rapid_focus_subskill_invalid"

        started = _start(client, questionDepth="quick")
        round_id = started["round"]["roundId"]
        served = client.post(f"/rapid/rounds/{round_id}/next", json={}).json()
        oversized = client.post(
            f"/rapid/rounds/{round_id}/submit",
            json={
                "caseId": served["current"]["case"]["caseId"],
                "freeTextAnswer": "x" * 6001,
                "taskResponses": _correct_task_responses(round_id),
            },
        )
        assert oversized.status_code == 422
