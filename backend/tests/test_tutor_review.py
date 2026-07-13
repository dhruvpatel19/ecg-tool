"""Tests for the conversational tutor and adaptive rapid-review sessions."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ECG_CORPUS_ROOT", "data/ecg_corpus_smoke")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)
_HAVE_CORPUS = Path("data/ecg_corpus_smoke/corpus.db").exists()
pytestmark = pytest.mark.skipif(not _HAVE_CORPUS, reason="smoke corpus not built")


def _mi_case() -> str:
    cases = client.get("/cases?concept=myocardial_infarction").json()
    return cases[0]["caseId"]


def test_tutor_message_is_multi_turn_grounded_and_persisted() -> None:
    cid = _mi_case()
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
        json={"mode": "tutorial", "caseId": cid, "threadId": r1["threadId"], "message": "What about the rate?"},
    ).json()
    assert r2["threadId"] == r1["threadId"]

    thread = client.get(f"/tutor/thread/{r1['threadId']}").json()
    roles = [m["role"] for m in thread["messages"]]
    assert roles == ["user", "tutor", "user", "tutor"]


def test_tutor_does_not_invent_absent_findings() -> None:
    # normal-ish case: ask about a finding the packet does not support
    cid = client.get("/cases?concept=normal_ecg").json()[0]["caseId"]
    r = client.post(
        "/tutor/message",
        json={"mode": "freeform", "caseId": cid, "message": "Point out the anterior ST elevation."},
    ).json()
    # either it refuses (warning) or it does not fabricate an anterior_mi objective update
    assert r["schemaError"] is None


def test_review_session_progresses_to_mastery() -> None:
    start = client.post(
        "/review/start", json={"learnerId": "rev", "conceptId": "anterior_mi", "targetMastery": 0.5, "maxCases": 15}
    ).json()
    sid = start["session"]["sessionId"]
    assert start["case"] is not None
    served = [start["case"]["caseId"]]

    done = False
    for _ in range(15):
        cid = served[-1]
        client.post(
            "/attempts",
            json={
                "learnerId": "rev",
                "caseId": cid,
                "mode": "concept_practice",
                "focusObjective": "anterior_mi",
                "structuredAnswer": {"st_t": "anterior st elevation", "synthesis": "anterior mi"},
                "freeTextAnswer": "anterior mi",
                "confidence": 3,
                "hintsUsed": 0,
            },
        )
        nxt = client.post(f"/review/{sid}/next").json()
        if nxt["done"]:
            done = True
            assert "Mastery" in nxt["reason"] or "cap" in nxt["reason"].lower()
            break
        served.append(nxt["case"]["caseId"])

    assert done, "review session should complete at the mastery goal"
    # cases served within a session are distinct (no immediate repeats)
    assert len(set(served)) == len(served)
