from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from typing import Any

from fastapi.testclient import TestClient

from app.learning_replay import (
    _safe_task,
    _safe_task_result,
    _safe_viewer_task_evidence,
)
from app.learning_sessions import issue_learning_session_ref
from app.main import app, clinical_item_store, repo, settings, store
from app.training_routes import build_training_classification_contract


PASSWORD = "Sup3r-Secret-Pw!"
REPLAY_KEYS = {
    "version",
    "fidelity",
    "sessionRef",
    "attemptIndex",
    "mode",
    "sessionStatus",
    "displayId",
    "submittedAt",
    "ecgRef",
    "waveformAvailable",
    "waveformPresentation",
    "comparison",
    "question",
    "submission",
    "feedback",
    "answerGuide",
    "provenance",
}
FROZEN_TRAINING_CLASSIFICATION = {
    "version": "focused-classification-v1",
    "kind": "single_choice",
    "prompt": "Frozen authored sinus-rhythm question?",
    "presentLabel": "Frozen target supported",
    "absentLabel": "Frozen target not supported",
    "options": [
        {"id": "absent", "label": "Frozen target not supported"},
        {"id": "present", "label": "Frozen target supported"},
    ],
    "required": True,
}
FROZEN_TRAINING_TASK = {
    "kind": "single_choice",
    "subskill": "recognize",
    "variant": 0,
    "prompt": "Frozen secondary recognition check.",
    "options": [
        {"id": "choice_1", "label": "Frozen evidence option one"},
        {"id": "choice_2", "label": "Frozen evidence option two"},
    ],
    "required": True,
    "gradingBoundary": "Frozen answer-free review boundary.",
}


def _register(client: TestClient, prefix: str) -> dict[str, Any]:
    response = client.post(
        "/auth/register",
        json={
            "username": f"{prefix}_{uuid.uuid4().hex[:10]}",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["user"]


def _strings(value: object) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _strings(item)


def _insert_attempt(
    conn,
    *,
    learner_id: str,
    case_id: str,
    mode: str,
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
        ) VALUES (?, ?, ?, '{}', '', 4, 0, ?, '[]', '[]', '[]', '',
            'ecg-objective-registry-v2', ?)
        """,
        (learner_id, case_id, mode, score, created_at),
    )
    return int(cursor.lastrowid)


def _session_ref(owner_id: str, mode: str, session_id: str) -> str:
    return issue_learning_session_ref(
        secret=settings.registration_rate_limit_secret,
        learner_id=owner_id,
        mode=mode,
        session_id=session_id,
    )


def _seed_replays(
    owner_id: str,
    suffix: str,
    *,
    include_training_snapshot: bool = True,
) -> tuple[dict[str, str], str, str]:
    item = next(
        candidate
        for candidate in clinical_item_store.list_for_serving(status="harness_pass")
        if candidate.ecg_id == "948" and candidate.prior_ecg_id == "942"
    )
    case_id = str(item.ecg_id)
    assert repo.get_case(case_id) is not None
    step_answers = [
        next(index for index, option in enumerate(step.options) if option.correct)
        for step in item.steps
    ]
    secret = f"private-replay-material-{suffix}"
    training_id = f"replay-training-{suffix}"
    rapid_id = f"replay-rapid-{suffix}"
    clinical_id = f"replay-clinical-{suffix}"
    created_at = "2026-07-16T12:00:00+00:00"

    with store.connect() as conn:
        conn.execute(
            """
            INSERT INTO training_campaigns (
                campaign_id, learner_id, concept_id, subskill,
                requested_length, length, pool_count, phases_json,
                phase_counts_json, position, status, context_key,
                created_at, updated_at
            ) VALUES (?, ?, 'sinus_rhythm', 'recognize', 1, 1, 1,
                '["transfer"]', '{"transfer":1}', 1, 'complete',
                'receiptConcept=rhythm_basics', ?, ?)
            """,
            (training_id, owner_id, created_at, created_at),
        )
        conn.execute(
            """
            INSERT INTO training_campaign_slots (
                campaign_id, ordinal, phase, case_id, case_focus,
                target_present, status, served_at, answered_at
            ) VALUES (?, 0, 'transfer', ?, 'sinus_rhythm', 1,
                'answered', ?, ?)
            """,
            (training_id, case_id, created_at, created_at),
        )
        training_attempt = _insert_attempt(
            conn,
            learner_id=owner_id,
            case_id=case_id,
            mode="concept_practice",
            score=1.0,
            created_at=created_at,
        )
        conn.execute(
            """
            INSERT INTO training_campaign_answers (
                campaign_id, ordinal, case_id, response_json, grade_json,
                tutor_json, receipt_json, summary_json, integrity_status,
                attempt_id, created_at
            ) VALUES (?, 0, ?, ?, ?, '{}', '{}', ?, 'atomic_v2', ?, ?)
            """,
            (
                training_id,
                case_id,
                json.dumps(
                    {
                        "selectedAnswer": "present",
                        "expectedAnswer": "present",
                        "confidence": 4,
                        "hintsUsed": 0,
                        "evidenceNote": "Regular P waves precede each QRS.",
                        "viewerTaskEvidence": {
                            "mode": "point",
                            "point": {
                                "lead": "II",
                                "timeSec": 0.5,
                                "amplitudeMv": 0.8,
                            },
                        },
                        "subskillTaskAnswer": "",
                        **(
                            {
                                "questionSnapshot": {
                                    "version": "focused-question-v1",
                                    "classification": FROZEN_TRAINING_CLASSIFICATION,
                                    "task": FROZEN_TRAINING_TASK,
                                }
                            }
                            if include_training_snapshot
                            else {}
                        ),
                        "privateAnswerKey": secret,
                    }
                ),
                json.dumps(
                    {
                        "score": 1.0,
                        "feedback": "The submitted classification was supported.",
                        "trainingClassificationCorrect": True,
                        "trainingSubskillTaskResult": None,
                        "privatePacket": secret,
                    }
                ),
                json.dumps(
                    {
                        "correct": True,
                        "misconceptions": [],
                        "evidenceLevel": "independent_transfer",
                        "privateReceipt": secret,
                    }
                ),
                training_attempt,
                created_at,
            ),
        )

        conn.execute(
            """
            INSERT INTO rapid_rounds (
                round_id, learner_id, pace, length, assessment_scope,
                focus_concept, focus_subskill, position, status,
                created_at, updated_at
            ) VALUES (?, ?, 'untimed', 1, 'dominant_finding',
                'sinus_rhythm', 'recognize', 1, 'complete', ?, ?)
            """,
            (rapid_id, owner_id, created_at, created_at),
        )
        rapid_attempt = _insert_attempt(
            conn,
            learner_id=owner_id,
            case_id=case_id,
            mode="rapid_practice",
            score=0.8,
            created_at=created_at,
        )
        conn.execute(
            """
            INSERT INTO rapid_round_answers (
                round_id, case_id, response_json, grade_json, result_json,
                trace_grade_json, tested_manifest_json, receipts_json,
                integrity_status, attempt_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, '[{}]', 'atomic_v2', ?, ?)
            """,
            (
                rapid_id,
                case_id,
                json.dumps(
                    {
                        "structuredAnswer": {
                            "framework": "clerkship",
                            "rate": "70 bpm",
                            "rhythm": "Regular sinus rhythm",
                            "axis": "Normal",
                            "intervals": "Within expected limits",
                            "conduction": "No delay",
                            "st_t": "No acute change",
                            "hypertrophy": "None",
                            "synthesis": "Sinus rhythm",
                            "selectedConcepts": ["sinus_rhythm"],
                            "privateStructuredKey": secret,
                        },
                        "freeTextAnswer": "Sinus rhythm without an acute change.",
                        "confidence": 4,
                        "taskResponses": {
                            "task_replay_mixed_v2": "option_2",
                        },
                        "privateResponse": secret,
                    }
                ),
                json.dumps(
                    {
                        "feedback": "The dominant finding was supported.",
                        "taskFeedback": [
                            {
                                "taskId": "task_replay_mixed_v2",
                                "type": "single_choice",
                                "topicId": "rhythm",
                                "skillId": "recognize",
                                "objectiveId": "sinus_rhythm",
                                "complete": True,
                                "correct": True,
                                "score": 1.0,
                                "timedOut": False,
                                "formativeOnly": False,
                                "feedback": "The rhythm choice matched the ECG.",
                                "correctChoiceId": "option_2",
                                "privateTaskFeedback": secret,
                            }
                        ],
                        "privateGrade": secret,
                    }
                ),
                json.dumps(
                    {
                        "score": 0.8,
                        "correctObjectives": ["sinus_rhythm"],
                        "missedObjectives": [],
                        "overcalledObjectives": [],
                        "revealedDiagnosis": "Sinus rhythm",
                        "timedOut": False,
                        "responseMs": 12500,
                        "privateResult": secret,
                    }
                ),
                json.dumps(
                    {
                        "correct": True,
                        "noTarget": False,
                        "feedback": "The point was acceptable.",
                        "privateTraceGeometry": secret,
                    }
                ),
                json.dumps(
                    {
                        "taskKind": "mixed_v2",
                        "assessmentScope": "dominant_finding",
                        "objectives": [
                            {
                                "objectiveId": "sinus_rhythm",
                                "subskill": "recognize",
                                "role": "primary",
                                "source": "case_manifest",
                                "lapseEligible": True,
                                "privateManifest": secret,
                            }
                        ],
                        "contractVersion": "mixed-v2",
                        "taskPacket": {
                            "version": "rapid-task-packet-v1",
                            "display": {"kind": "twelve_lead"},
                            "estimatedSeconds": 90,
                            "tasks": [
                                {
                                    "id": "task_replay_mixed_v2",
                                    "type": "single_choice",
                                    "prompt": "Which rhythm is best supported by this ECG?",
                                    "options": [
                                        {"id": "option_1", "label": "Atrial flutter"},
                                        {"id": "option_2", "label": "Sinus rhythm"},
                                    ],
                                    "bloomLevel": "analyze",
                                    "topicId": "rhythm",
                                    "skillId": "recognize",
                                    "required": True,
                                    "grading": {
                                        "correctOptionId": "option_2",
                                        "privateAnswerKey": secret,
                                    },
                                }
                            ],
                        },
                        "privateRoster": secret,
                    }
                ),
                rapid_attempt,
                created_at,
            ),
        )

        conn.execute(
            """
            INSERT INTO clinical_shift_sessions (
                session_id, learner_id, lane, tier, focus_objective,
                focus_subskill, length, requested_length, available_length,
                position, status, created_at, updated_at
            ) VALUES (?, ?, ?, 'learn', 'sinus_rhythm', 'apply_in_context',
                1, 1, 1, 1, 'complete', ?, ?)
            """,
            (clinical_id, owner_id, item.situation, created_at, created_at),
        )
        clinical_attempt = _insert_attempt(
            conn,
            learner_id=owner_id,
            case_id=case_id,
            mode="clinical_decision",
            score=1.0,
            created_at=created_at,
        )
        selected = item.options[0].id if item.options else None
        conn.execute(
            """
            INSERT INTO clinical_shift_answers (
                session_id, item_id, ecg_id, response_json, grade_json,
                score, correct, answer_time_ms, attempt_id, created_at
            ) VALUES (?, ?, ?, ?, ?, 1.0, 1, 9000, ?, ?)
            """,
            (
                clinical_id,
                item.item_id,
                case_id,
                json.dumps(
                    {
                        "selected_option_id": selected,
                        "first_look_finding": "normal_or_no_dominant_abnormality",
                        "first_look_confidence": 3,
                        "confidence": 4,
                        "answer_time_ms": 9000,
                        "timed_out": False,
                        "step_answers": step_answers,
                        "matches": {},
                        "privateResponse": secret,
                    }
                ),
                json.dumps(
                    {
                        "score": 1.0,
                        "feedback": "The submitted action was defensible.",
                        "teachingPoints": ["Tie the action to the visible ECG evidence."],
                        "axisScores": {"action": 1.0},
                        "safetyFlags": [],
                        "timedOut": False,
                        "clinicalApplicationEvidence": "formative_only",
                        "stepFeedback": [
                            {
                                "stageIndex": index,
                                "stageKind": step.stage_kind,
                                "stageTitle": step.stage_title,
                                "elapsedLabel": step.elapsed_label,
                                "clinicalUpdate": step.clinical_update,
                                "dataPoints": [
                                    point.model_dump(mode="json")
                                    for point in step.data_points
                                ],
                                "prompt": step.prompt,
                                "learnerOptionIndex": step_answers[index],
                                "learnerAnswer": step.options[step_answers[index]].text,
                                "supportedOptionIndex": step_answers[index],
                                "supportedAnswer": step.options[step_answers[index]].text,
                                "correct": True,
                                "selectionCorrect": True,
                                "timedOut": False,
                                "explanation": step.options[step_answers[index]].rationale,
                                "privateFeedback": secret,
                            }
                            for index, step in enumerate(item.steps)
                        ],
                        "competencyOutcomes": [
                            {
                                "concept": "sinus_rhythm",
                                "subskill": "synthesize",
                                "score": 1.0,
                                "correct": True,
                                "stageIndex": 0,
                                "stageTitle": item.steps[0].stage_title,
                                "stageKind": item.steps[0].stage_kind,
                                "evidenceSource": "clinical_step_server_grade",
                                "privateOutcome": secret,
                            }
                        ],
                        "privateEvidenceManifest": secret,
                    }
                ),
                clinical_attempt,
                created_at,
            ),
        )

    ids = {"training": training_id, "rapid": rapid_id, "clinical": clinical_id}
    return (
        {mode: _session_ref(owner_id, mode, session_id) for mode, session_id in ids.items()},
        case_id,
        secret,
    )


def _seed_missed_trace_replay(
    owner_id: str, suffix: str, *, subskill: str
) -> str:
    assert subskill in {"localize", "measure"}
    case_id = "948"
    assert repo.get_case(case_id) is not None
    campaign_id = f"replay-training-{subskill}-{suffix}"
    created_at = "2026-07-17T12:00:00+00:00"
    concept = "sinus_rhythm" if subskill == "localize" else "qtc_prolongation"
    expected_answer = "present" if subskill == "localize" else "absent"
    learner_evidence = (
        {
            "mode": "point",
            "point": {"lead": "II", "timeSec": 0.5, "amplitudeMv": 0.8},
        }
        if subskill == "localize"
        else {
            "mode": "caliper",
            "lead": "II",
            "timeStartSec": 1.0,
            "timeEndSec": 1.1,
            "valueMs": 100.0,
        }
    )
    task_result = (
        None
        if subskill == "localize"
        else {
            "kind": "numeric_fill_in",
            "complete": True,
            "correct": False,
            "score": 0.0,
            "submittedValue": 600.0,
            "expectedValue": 464.0,
            "tolerance": 35.0,
            "unit": "ms",
        }
    )

    with store.connect() as conn:
        conn.execute(
            """
            INSERT INTO training_campaigns (
                campaign_id, learner_id, concept_id, subskill,
                requested_length, length, pool_count, phases_json,
                phase_counts_json, position, status, context_key,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, 1, 1, 1, '["transfer"]',
                '{"transfer":1}', 1, 'complete', ?, ?, ?)
            """,
            (
                campaign_id,
                owner_id,
                concept,
                subskill,
                f"receiptConcept={concept}",
                created_at,
                created_at,
            ),
        )
        conn.execute(
            """
            INSERT INTO training_campaign_slots (
                campaign_id, ordinal, phase, case_id, case_focus,
                target_present, status, served_at, answered_at
            ) VALUES (?, 0, 'transfer', ?, ?, ?, 'answered', ?, ?)
            """,
            (
                campaign_id,
                case_id,
                concept,
                int(expected_answer == "present"),
                created_at,
                created_at,
            ),
        )
        attempt_id = _insert_attempt(
            conn,
            learner_id=owner_id,
            case_id=case_id,
            mode="concept_practice",
            score=0.0,
            created_at=created_at,
        )
        conn.execute(
            """
            INSERT INTO training_campaign_answers (
                campaign_id, ordinal, case_id, response_json, grade_json,
                tutor_json, receipt_json, summary_json, integrity_status,
                attempt_id, created_at
            ) VALUES (?, 0, ?, ?, ?, '{}', '{}', ?, 'atomic_v2', ?, ?)
            """,
            (
                campaign_id,
                case_id,
                json.dumps(
                    {
                        "selectedAnswer": expected_answer,
                        "expectedAnswer": expected_answer,
                        "hintsUsed": 0,
                        "evidenceNote": "Saved learner trace evidence.",
                        "viewerTaskEvidence": learner_evidence,
                        "subskillTaskAnswer": "",
                        "subskillTaskValue": 600.0 if subskill == "measure" else None,
                    }
                ),
                json.dumps(
                    {
                        "feedback": "The selected trace evidence needs review.",
                        "trainingClassificationCorrect": True,
                        "trainingSubskillEvidenceCorrect": False,
                        "trainingSubskillTaskResult": task_result,
                    }
                ),
                json.dumps(
                    {
                        "correct": False,
                        "classificationCorrect": True,
                        "misconceptions": [f"subskill_task_error:{subskill}"],
                    }
                ),
                attempt_id,
                created_at,
            ),
        )
    return _session_ref(owner_id, "training", campaign_id)


def _assessment_counts() -> dict[str, int]:
    tables = (
        "attempts",
        "training_campaign_answers",
        "rapid_round_answers",
        "clinical_shift_answers",
        "learner_events",
        "learner_event_competencies",
        "subskill_mastery",
        "learning_session_flags",
    )
    with store.connect() as conn:
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in tables
        }


def _assert_private_headers(response) -> None:
    assert response.headers["cache-control"] == "no-store, private"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["vary"] == "Authorization, Cookie"


def test_review_evidence_projection_keeps_only_safe_learner_geometry() -> None:
    assert _safe_viewer_task_evidence(
        {
            "mode": "region",
            "roi": {
                "lead": "V2",
                "timeStartSec": 1.1,
                "timeEndSec": 1.3,
                "ampMinMv": -0.2,
                "ampMaxMv": 0.9,
                "label": "private answer label",
                "concept": "private_answer_concept",
            },
            "feedback": "private grading feedback",
        }
    ) == {
        "mode": "region",
        "roi": {
            "lead": "V2",
            "timeStartSec": 1.1,
            "timeEndSec": 1.3,
            "ampMinMv": -0.2,
            "ampMaxMv": 0.9,
            "label": "Your selected region",
            "concept": "learner_evidence",
            "source": "user",
            "confidence": "recorded",
        },
    }
    assert _safe_viewer_task_evidence(
        {
            "mode": "caliper",
            "lead": "II",
            "timeStartSec": 0.5,
            "timeEndSec": 0.7,
            "valueMs": 200,
            "correct": True,
        }
    ) == {
        "mode": "caliper",
        "lead": "II",
        "timeStartSec": 0.5,
        "timeEndSec": 0.7,
        "valueMs": 200.0,
    }
    assert _safe_viewer_task_evidence(
        {"mode": "point", "point": {"lead": "II", "timeSec": 0.5}}
    ) is None


def test_training_replay_projects_systematic_framework_without_raw_internals() -> None:
    keys = [
        "rate",
        "rhythm",
        "axis",
        "intervals",
        "conduction",
        "st_t",
        "hypertrophy",
        "synthesis",
    ]
    framework_steps = [
        {
            "key": key,
            "label": key.replace("_", " ").title(),
            "prompt": f"Review {key}.",
            "placeholder": f"Enter {key}.",
            "privateAnswer": "never expose",
        }
        for key in keys
    ]
    task = _safe_task(
        {
            "kind": "single_choice",
            "subskill": "synthesize",
            "variant": 0,
            "prompt": "Choose the reviewed synthesis.",
            "options": [{"id": "choice_1", "label": "Bounded synthesis"}],
            "required": True,
            "frameworkVersion": "focused-systematic-interpretation-v1",
            "frameworkSteps": framework_steps,
            "correctAnswer": "private-choice",
        }
    )
    assert task["frameworkVersion"] == "focused-systematic-interpretation-v1"
    assert [row["key"] for row in task["frameworkSteps"]] == keys
    assert all(
        set(row) == {"key", "label", "prompt", "placeholder"}
        for row in task["frameworkSteps"]
    )
    assert "private" not in json.dumps(task)

    interpretation = {key: f"Saved {key} response" for key in keys}
    reviewed = [
        {
            "key": key,
            "label": key.replace("_", " ").title(),
            "review": (
                f"Packet-grounded review for {key}."
                if index % 2 == 0
                else "Not verified by this packet."
            ),
            "grounded": index % 2 == 0,
            "privateEvidence": "never expose",
        }
        for index, key in enumerate(keys)
    ]
    result = _safe_task_result(
        {
            "kind": "single_choice",
            "complete": True,
            "correct": True,
            "score": 1.0,
            "systematicInterpretationComplete": True,
            "systematicInterpretation": interpretation,
            "reviewedFramework": reviewed,
            "privatePacket": "never expose",
        }
    )
    assert result["systematicInterpretationComplete"] is True
    assert result["systematicInterpretation"] == interpretation
    assert result["reviewedFramework"] == [
        {key: row[key] for key in ("key", "label", "review", "grounded")}
        for row in reviewed
    ]
    assert "private" not in json.dumps(result)


def test_missed_focused_trace_tasks_replay_learner_evidence_with_reviewed_geometry() -> None:
    with TestClient(app) as client:
        owner = _register(client, "replay_trace_review")
        for subskill in ("localize", "measure"):
            session_ref = _seed_missed_trace_replay(
                owner["userId"], uuid.uuid4().hex, subskill=subskill
            )
            response = client.get(
                f"/learning/sessions/{session_ref}/attempts/1/replay"
            )
            assert response.status_code == 200, response.text
            _assert_private_headers(response)
            payload = response.json()
            learner_evidence = payload["submission"]["viewerTaskEvidence"]
            assert learner_evidence["mode"] == (
                "point" if subskill == "localize" else "caliper"
            )

            actions = payload["reviewActions"]
            assert len(actions) == 1
            action = actions[0]
            assert action["lead"] == "II"
            assert action["timeEnd"] > action["timeStart"]
            assert action["label"] == (
                "Reviewed localization"
                if subskill == "localize"
                else "Reviewed interval"
            )
            assert set(action) == (
                {
                    "type",
                    "lead",
                    "timeStart",
                    "timeEnd",
                    "ampMin",
                    "ampMax",
                    "label",
                }
                if subskill == "localize"
                else {"type", "lead", "timeStart", "timeEnd", "label"}
            )
            assert action["type"] == (
                "highlightROI" if subskill == "localize" else "drawCaliper"
            )
            assert not {
                "concept",
                "source",
                "confidence",
                "correct",
                "score",
                "grade",
                "expectedValue",
                "tolerance",
            }.intersection(action)


def test_completed_replays_are_strict_owner_bound_and_read_only() -> None:
    with TestClient(app) as owner, TestClient(app) as other:
        owner_user = _register(owner, "replay_owner")
        _register(other, "replay_other")
        suffix = uuid.uuid4().hex
        refs, canonical_case_id, private_secret = _seed_replays(
            owner_user["userId"], suffix
        )
        before = _assessment_counts()
        payloads: dict[str, dict[str, Any]] = {}

        expected_question_keys = {
            "training": {
                "kind",
                "prompt",
                "target",
                "classificationOptions",
                "subskillTask",
            },
            "rapid": {
                "kind",
                "pace",
                "assessmentScope",
                "testedObjectiveManifest",
                "taskPacket",
            },
        }
        for mode, session_ref in refs.items():
            response = owner.get(
                f"/learning/sessions/{session_ref}/attempts/1/replay"
            )
            assert response.status_code == 200, response.text
            _assert_private_headers(response)
            payload = response.json()
            payloads[mode] = payload
            assert set(payload) == REPLAY_KEYS
            assert payload["version"] == "learning-session-replay-v1"
            assert payload["fidelity"] == "reconstructed"
            assert payload["mode"] == mode
            assert payload["sessionStatus"] == "complete"
            assert payload["attemptIndex"] == 1
            assert payload["sessionRef"] == session_ref
            assert payload["ecgRef"].startswith("ec_")
            assert payload["waveformAvailable"] is True
            assert (payload["comparison"] is not None) is (mode == "clinical")
            all_strings = set(_strings(payload))
            assert canonical_case_id not in all_strings
            assert "942" not in all_strings
            assert private_secret not in all_strings
            assert f"replay-{mode}-{suffix}" not in all_strings
            if mode in expected_question_keys:
                assert set(payload["question"]) == expected_question_keys[mode]
                if mode == "rapid":
                    assert payload["question"]["taskPacket"] == {
                        "version": "rapid-task-packet-v1",
                        "display": {"kind": "twelve_lead"},
                        "estimatedSeconds": 90,
                        "tasks": [
                            {
                                "id": "task_replay_mixed_v2",
                                "type": "single_choice",
                                "prompt": "Which rhythm is best supported by this ECG?",
                                "options": [
                                    {"id": "option_1", "label": "Atrial flutter"},
                                    {"id": "option_2", "label": "Sinus rhythm"},
                                ],
                                "bloomLevel": "analyze",
                                "topicId": "rhythm",
                                "skillId": "recognize",
                                "required": True,
                            }
                        ],
                    }
                    assert payload["submission"]["taskResponses"] == {
                        "task_replay_mixed_v2": "option_2"
                    }
                    assert payload["feedback"]["taskFeedback"] == [
                        {
                            "taskId": "task_replay_mixed_v2",
                            "type": "single_choice",
                            "topicId": "rhythm",
                            "skillId": "recognize",
                            "objectiveId": "sinus_rhythm",
                            "complete": True,
                            "correct": True,
                            "score": 1.0,
                            "timedOut": False,
                            "formativeOnly": False,
                            "feedback": "The rhythm choice matched the ECG.",
                            "correctChoiceId": "option_2",
                        }
                    ]
                else:
                    assert payload["question"]["prompt"] == (
                        FROZEN_TRAINING_CLASSIFICATION["prompt"]
                    )
                    assert payload["question"]["classificationOptions"] == (
                        FROZEN_TRAINING_CLASSIFICATION["options"]
                    )
                    assert payload["question"]["subskillTask"] == FROZEN_TRAINING_TASK
                    assert payload["question"]["target"] == {
                        "objectiveId": "rhythm_basics",
                        "objectiveLabel": "Rhythm Basics",
                        "caseConceptId": "sinus_rhythm",
                        "caseConceptLabel": "Sinus rhythm",
                        "subskill": "recognize",
                    }
                    assert "phase" not in payload["question"]
                    assert "confidence" not in payload["submission"]
                    assert payload["submission"]["viewerTaskEvidence"] == {
                        "mode": "point",
                        "point": {
                            "lead": "II",
                            "timeSec": 0.5,
                            "amplitudeMv": 0.8,
                        },
                    }
            else:
                assert payload["question"]["kind"] == "clinical"
                assert "itemId" not in payload["question"]
                assert "ecgId" not in payload["question"]
                assert "evidenceManifest" not in payload["question"]
                assert "firstLookConfidence" not in payload["submission"]
                assert "confidence" not in payload["submission"]
                assert "confidenceTimeMs" not in payload["submission"]
                stages = payload["question"]["steps"]
                assert [stage["stageKind"] for stage in stages] == [
                    "ecg",
                    "reassessment",
                    "handoff",
                ]
                assert all(
                    stage.get("stageTitle")
                    and stage.get("elapsedLabel")
                    and stage.get("clinicalUpdate")
                    and stage.get("dataPoints")
                    for stage in stages
                )
                assert {
                    point["source"]
                    for stage in stages
                    for point in stage["dataPoints"]
                } == {"source_metadata", "authored_simulation"}
                comparison = payload["comparison"]
                assert comparison["role"] == "prior"
                assert comparison["ecgRef"].startswith("ec_")
                assert comparison["ecgRef"] != payload["ecgRef"]
                assert comparison["waveformAvailable"] is True
                assert comparison["provenance"] == (
                    "same_patient_time_ordered_real_ecgs"
                )
                assert payload["provenance"]["comparison"] == (
                    "same_patient_time_ordered_real_ecgs"
                )
                assert len(payload["feedback"]["stepFeedback"]) == 3
                assert all(
                    row["supportedAnswer"]
                    and row["learnerAnswer"]
                    and row["explanation"]
                    and row["correct"] is True
                    for row in payload["feedback"]["stepFeedback"]
                )
                assert payload["feedback"]["competencyOutcomes"] == [
                    {
                        "concept": "sinus_rhythm",
                        "subskill": "synthesize",
                        "score": 1.0,
                        "correct": True,
                        "stageIndex": 0,
                        "stageTitle": stages[0]["stageTitle"],
                        "stageKind": "ecg",
                        "evidenceSource": "clinical_step_server_grade",
                    }
                ]

            denied = other.get(
                f"/learning/sessions/{session_ref}/attempts/1/replay"
            )
            assert denied.status_code == 404
            assert denied.json()["detail"]["code"] == "learning_session_not_found"
            _assert_private_headers(denied)

        # The ordinary review remains deliberately answer-free.
        review = owner.get(f"/learning/sessions/{refs['rapid']}")
        assert review.status_code == 200
        review_text = json.dumps(review.json())
        assert "ecgRef" not in review_text
        assert "answerGuide" not in review_text
        assert "question" not in review_text

        rapid_ref = refs["rapid"]
        rapid_ecg_ref = payloads["rapid"]["ecgRef"]
        waveform = owner.get(
            f"/learning/sessions/{rapid_ref}/attempts/1/waveform/{rapid_ecg_ref}",
            params={"leads": "II", "start": 0, "end": 1, "maxPoints": 100},
        )
        assert waveform.status_code == 200, waveform.text
        _assert_private_headers(waveform)
        waveform_payload = waveform.json()
        assert waveform_payload["caseId"] == rapid_ecg_ref
        assert [lead["lead"] for lead in waveform_payload["leads"]] == ["II"]
        assert canonical_case_id not in set(_strings(waveform_payload))

        invalid_lead = owner.get(
            f"/learning/sessions/{rapid_ref}/attempts/1/waveform/{rapid_ecg_ref}",
            params={"leads": "not-a-lead"},
        )
        assert invalid_lead.status_code == 422
        _assert_private_headers(invalid_lead)

        canonical_denied = owner.get(
            f"/learning/sessions/{rapid_ref}/attempts/1/waveform/{canonical_case_id}"
        )
        assert canonical_denied.status_code == 404
        _assert_private_headers(canonical_denied)
        cross_attempt = owner.get(
            f"/learning/sessions/{rapid_ref}/attempts/1/waveform/"
            f"{payloads['clinical']['ecgRef']}"
        )
        assert cross_attempt.status_code == 404
        _assert_private_headers(cross_attempt)
        other_waveform = other.get(
            f"/learning/sessions/{rapid_ref}/attempts/1/waveform/{rapid_ecg_ref}"
        )
        assert other_waveform.status_code == 404
        _assert_private_headers(other_waveform)

        clinical_ref = refs["clinical"]
        comparison_ref = payloads["clinical"]["comparison"]["ecgRef"]
        comparison_waveform = owner.get(
            f"/learning/sessions/{clinical_ref}/attempts/1/waveform/{comparison_ref}",
            params={"leads": "II", "start": 0, "end": 1, "maxPoints": 100},
        )
        assert comparison_waveform.status_code == 200, comparison_waveform.text
        _assert_private_headers(comparison_waveform)
        assert comparison_waveform.json()["caseId"] == comparison_ref
        assert [
            lead["lead"] for lead in comparison_waveform.json()["leads"]
        ] == ["II"]
        assert "942" not in set(_strings(comparison_waveform.json()))
        prior_canonical_denied = owner.get(
            f"/learning/sessions/{clinical_ref}/attempts/1/waveform/942"
        )
        assert prior_canonical_denied.status_code == 404
        _assert_private_headers(prior_canonical_denied)
        other_comparison = other.get(
            f"/learning/sessions/{clinical_ref}/attempts/1/waveform/{comparison_ref}"
        )
        assert other_comparison.status_code == 404
        _assert_private_headers(other_comparison)

        assert _assessment_counts() == before


def test_legacy_training_replay_uses_deterministic_question_fallback() -> None:
    with TestClient(app) as client:
        user = _register(client, "legacy_replay")
        refs, _, _ = _seed_replays(
            user["userId"],
            uuid.uuid4().hex,
            include_training_snapshot=False,
        )
        response = client.get(
            f"/learning/sessions/{refs['training']}/attempts/1/replay"
        )
        assert response.status_code == 200, response.text
        _assert_private_headers(response)
        question = response.json()["question"]
        expected = build_training_classification_contract("sinus_rhythm", 0)
        assert question["prompt"] == expected["prompt"]
        assert question["classificationOptions"] == expected["options"]
        assert question["subskillTask"] is None
        assert question["prompt"] != FROZEN_TRAINING_CLASSIFICATION["prompt"]


def test_abandoned_rapid_round_replays_only_its_committed_attempts() -> None:
    with TestClient(app) as owner, TestClient(app) as other:
        owner_user = _register(owner, "partial_replay_owner")
        _register(other, "partial_replay_other")
        suffix = uuid.uuid4().hex
        refs, canonical_case_id, private_secret = _seed_replays(
            owner_user["userId"], suffix
        )
        internal_round_id = f"replay-rapid-{suffix}"
        pending_case_id = f"pending-private-{suffix}"
        with store.connect() as conn:
            conn.execute(
                """
                UPDATE rapid_rounds
                SET status = 'abandoned', length = 5, position = 1,
                    pending_case_id = ?, updated_at = '2026-07-16T12:10:00+00:00'
                WHERE round_id = ?
                """,
                (pending_case_id, internal_round_id),
            )
        before = _assessment_counts()

        sessions = owner.get("/learning/sessions?limit=50")
        assert sessions.status_code == 200, sessions.text
        partial = next(
            item
            for item in sessions.json()["items"]
            if item["sessionRef"] == refs["rapid"]
        )
        assert partial["status"] == "abandoned"
        assert partial["attempted"] == 1
        assert partial["total"] == 5

        replay_response = owner.get(
            f"/learning/sessions/{refs['rapid']}/attempts/1/replay"
        )
        assert replay_response.status_code == 200, replay_response.text
        _assert_private_headers(replay_response)
        replay = replay_response.json()
        assert replay["mode"] == "rapid"
        assert replay["sessionStatus"] == "abandoned"
        assert replay["attemptIndex"] == 1
        assert replay["sessionRef"] == refs["rapid"]

        unanswered = owner.get(
            f"/learning/sessions/{refs['rapid']}/attempts/2/replay"
        )
        cross_owner = other.get(
            f"/learning/sessions/{refs['rapid']}/attempts/1/replay"
        )
        assert unanswered.status_code == cross_owner.status_code == 404
        assert unanswered.json() == cross_owner.json()
        serialized = sessions.text + replay_response.text
        for forbidden in (
            internal_round_id,
            canonical_case_id,
            pending_case_id,
            private_secret,
            suffix,
        ):
            assert forbidden not in serialized
        assert _assessment_counts() == before


def test_replay_and_waveform_preserve_the_pending_case_guard() -> None:
    with TestClient(app) as client:
        user = _register(client, "replay_pending")
        suffix = uuid.uuid4().hex
        refs, case_id, _ = _seed_replays(user["userId"], suffix)
        initial = client.get(
            f"/learning/sessions/{refs['rapid']}/attempts/1/replay"
        )
        assert initial.status_code == 200, initial.text
        ecg_ref = initial.json()["ecgRef"]
        active_id = f"replay-pending-{suffix}"
        now = "2026-07-16T12:05:00+00:00"
        with store.connect() as conn:
            conn.execute(
                """
                INSERT INTO rapid_rounds (
                    round_id, learner_id, pace, length, assessment_scope,
                    pending_case_id, position, status, created_at, updated_at
                ) VALUES (?, ?, 'untimed', 1, 'dominant_finding', ?, 0,
                    'active', ?, ?)
                """,
                (active_id, user["userId"], case_id, now, now),
            )
        try:
            replay = client.get(
                f"/learning/sessions/{refs['rapid']}/attempts/1/replay"
            )
            waveform = client.get(
                f"/learning/sessions/{refs['rapid']}/attempts/1/waveform/{ecg_ref}"
            )
            for response in (replay, waveform):
                assert response.status_code == 409, response.text
                assert response.json()["detail"]["code"] == (
                    "assessment_case_not_committed"
                )
                _assert_private_headers(response)
        finally:
            with store.connect() as conn:
                conn.execute(
                    "UPDATE rapid_rounds SET pending_case_id = NULL, "
                    "status = 'abandoned' WHERE round_id = ?",
                    (active_id,),
                )


def test_clinical_replay_fails_closed_when_the_authored_item_is_unavailable() -> None:
    with TestClient(app) as client:
        user = _register(client, "replay_missing")
        suffix = uuid.uuid4().hex
        refs, _, _ = _seed_replays(user["userId"], suffix)
        initial = client.get(
            f"/learning/sessions/{refs['clinical']}/attempts/1/replay"
        )
        assert initial.status_code == 200, initial.text
        ecg_ref = initial.json()["ecgRef"]
        with store.connect() as conn:
            conn.execute(
                "UPDATE clinical_shift_answers SET item_id = ? "
                "WHERE session_id = ?",
                (f"unavailable-item-{suffix}", f"replay-clinical-{suffix}"),
            )
        response = client.get(
            f"/learning/sessions/{refs['clinical']}/attempts/1/replay"
        )
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "learning_session_not_found"
        _assert_private_headers(response)
        waveform = client.get(
            f"/learning/sessions/{refs['clinical']}/attempts/1/waveform/{ecg_ref}"
        )
        assert waveform.status_code == 404
        assert waveform.json()["detail"]["code"] == "learning_session_not_found"
        _assert_private_headers(waveform)
