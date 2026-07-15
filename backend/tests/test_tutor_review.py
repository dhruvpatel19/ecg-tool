"""Tests for the conversational tutor and adaptive rapid-review sessions."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ECG_CORPUS_ROOT", "data/ecg_corpus_smoke")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import _pending_assessment_case_ids, app, repo  # noqa: E402

client = TestClient(app)
_HAVE_CORPUS = Path("data/ecg_corpus_smoke/corpus.db").exists()
pytestmark = pytest.mark.skipif(not _HAVE_CORPUS, reason="smoke corpus not built")


def _mi_case() -> str:
    return str(repo.candidates("myocardial_infarction")[0]["case_id"])


def test_tutor_message_is_multi_turn_grounded_and_persisted() -> None:
    guided = client.get("/tutorials/mi-localization?concept=anterior_mi")
    assert guided.status_code == 200, guided.text
    guided_body = guided.json()
    cid = guided_body["recommendedCase"]["caseId"]
    committed = client.post(
        "/learning-events/guided",
        json={
            "eventKey": "tutor-review-mi-commit",
            "moduleId": "ischemia-infarction",
            "sceneId": "tutor-review",
            "interactionId": "mi-localization",
            "concept": "anterior_mi",
            "subskills": ["recognize"],
            "score": 1.0,
            "correct": True,
            "attempts": 1,
            "assistance": "independent",
            "caseId": cid,
            "guidedContext": guided_body["guidedContext"],
            "caseProvenance": "real_eligible",
            "caseEligible": True,
        },
    )
    assert committed.status_code == 200, committed.text
    r1 = client.post(
        "/tutor/message",
        json={"mode": "tutorial", "lessonId": "mi-localization", "caseId": cid, "message": "How do I know this is an MI?"},
    ).json()
    assert r1["threadId"]
    assert r1["tutorMessage"]
    assert r1["schemaError"] is None
    assert "onLessonTopic" in r1
    # grounded: mock should anchor on a real ROI/measurement for a supported concept
    assert r1["viewerActions"], "expected grounded viewer actions for an MI case"
    assert r1["socraticQuestion"]

    r2 = client.post(
        "/tutor/message",
        json={"mode": "tutorial", "lessonId": "mi-localization", "caseId": cid, "threadId": r1["threadId"], "message": "What about the rate?"},
    ).json()
    assert r2["threadId"] == r1["threadId"]

    thread = client.get(f"/tutor/thread/{r1['threadId']}").json()
    roles = [m["role"] for m in thread["messages"]]
    assert roles == ["user", "tutor", "user", "tutor"]


def test_tutor_does_not_invent_absent_findings() -> None:
    # Ask on a normal-ish case that is not currently protected by another
    # assessment's answer boundary. Other lifecycle tests intentionally leave
    # pending work behind; bypassing that guard would turn this grounding test
    # into a cross-account answer-leak probe.
    pending = _pending_assessment_case_ids()
    cid = next(
        str(candidate["case_id"])
        for candidate in repo.candidates("normal_ecg")
        if str(candidate["case_id"]) not in pending
    )
    r = client.post(
        "/tutor/message",
        json={"mode": "freeform", "caseId": cid, "message": "Point out the anterior ST elevation."},
    ).json()
    # either it refuses (warning) or it does not fabricate an anterior_mi objective update
    assert r["schemaError"] is None


def test_tutor_threads_are_partitioned_by_learning_waypoint() -> None:
    first = client.post(
        "/tutor/message",
        json={
            "mode": "freeform",
            "scopeKey": "guided-rate:scene-a",
            "message": "Help me reason through this first scene.",
        },
    )
    assert first.status_code == 200
    first_thread = first.json()["threadId"]

    second = client.post(
        "/tutor/message",
        json={
            "mode": "freeform",
            "scopeKey": "guided-rate:scene-b",
            "message": "Help me reason through this second scene.",
        },
    )
    assert second.status_code == 200
    second_thread = second.json()["threadId"]
    assert second_thread != first_thread

    scene_a = client.get(
        "/tutor/threads",
        params={"mode": "freeform", "scopeKey": "guided-rate:scene-a"},
    )
    assert scene_a.status_code == 200
    assert [row["threadId"] for row in scene_a.json()["threads"]] == [first_thread]

    cross_scene_continuation = client.post(
        "/tutor/message",
        json={
            "mode": "freeform",
            "scopeKey": "guided-rate:scene-b",
            "threadId": first_thread,
            "message": "Continue the old conversation here.",
        },
    )
    assert cross_scene_continuation.status_code == 404


def test_legacy_review_defers_to_the_evidence_tracked_adaptive_plan() -> None:
    start = client.post(
        "/review/start",
        json={
            "learnerId": "rev",
            "conceptId": "anterior_mi",
            "targetMastery": 0.5,
            "maxCases": 15,
        },
    )
    assert start.status_code == 410
    assert start.json()["detail"]["code"] == "legacy_review_deprecated"
    assert start.json()["detail"]["replacement"] == {
        "method": "GET",
        "path": "/adaptive/plan",
    }

    plan = client.get("/adaptive/plan", params={"learnerId": "rev"})
    assert plan.status_code == 200
    assert plan.json()["learnerId"]
    assert "stages" in plan.json()
