from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _event(learner: str, **overrides):
    event = {
        "learnerId": learner,
        "eventKey": f"evt-{uuid4().hex}",
        "moduleId": "leads-vectors",
        "sceneId": "M02.S10",
        "interactionId": "axis-transfer",
        "concept": "axis_normal",
        "subskills": ["recognize"],
        "score": 1.0,
        "correct": True,
        "attempts": 1,
        "assistance": "independent",
        "hintsUsed": 0,
        "confidence": 3,
        "evidenceLevel": "independent_transfer",
        "caseId": "3",
        "caseProvenance": "real_eligible",
        "caseEligible": True,
        "misconceptions": [],
    }
    event.update(overrides)
    return event


def test_scaffolded_success_is_formative_not_independent_mastery() -> None:
    learner = f"subskill_{uuid4().hex}"
    response = client.post(
        "/learning-events/guided",
        json=_event(learner, assistance="scaffolded", attempts=2, hintsUsed=1),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["requestedEvidenceLevel"] == "independent_transfer"
    assert body["effectiveEvidenceLevel"] == "guided"
    assert body["receipts"][0]["formativeScore"] > 0
    assert body["receipts"][0]["independentMastery"] == 0.15


def test_client_scored_visual_transfer_is_formative_even_on_an_eligible_case() -> None:
    learner = f"subskill_{uuid4().hex}"
    response = client.post("/learning-events/guided", json=_event(learner))
    assert response.status_code == 200
    receipt = response.json()["receipts"][0]
    assert receipt["concept"] == "axis_normal"
    assert receipt["subskill"] == "recognize"
    assert receipt["evidenceLevel"] == "guided"
    assert receipt["independentMastery"] == 0.15
    assert receipt["retentionEligible"] is False
    assert receipt["distinctEligibleEcgs"] == 0
    assert receipt["nextDueAt"] is None

    profile = client.get(f"/learners/{learner}/mastery").json()
    row = next(item for item in profile["subskillMastery"] if item["concept"] == "axis_normal" and item["subskill"] == "recognize")
    assert row["independentAttempts"] == 0
    assert row["distinctSuccessfulEcgs"] == 0
    assert row["stabilityDays"] == 0.0

    registry = client.get(f"/learners/{learner}/competencies").json()
    objective = next(item for item in registry["objectives"] if item["objectiveId"] == "axis_normal")
    cell = next(item for item in objective["subskills"] if item["subskill"] == "recognize")
    assert cell["state"] != "durable"
    assert cell["distinctSuccessfulEcgs"] == 0
    assert cell["nextDueAt"] is None
    assert cell["evidenceUncertainty"]


def test_clinical_application_requires_reviewed_case_content() -> None:
    learner = f"subskill_{uuid4().hex}"
    response = client.post(
        "/learning-events/guided",
        json=_event(learner, subskills=["apply_in_context"], caseProvenance="real_eligible"),
    )
    assert response.status_code == 200
    assert response.json()["effectiveEvidenceLevel"] == "guided"


def test_authored_simulation_can_prove_mechanism_but_not_visual_recognition() -> None:
    mechanism_learner = f"subskill_{uuid4().hex}"
    mechanism = client.post(
        "/learning-events/guided",
        json=_event(
            mechanism_learner,
            subskills=["explain_mechanism"],
            caseId=None,
            caseProvenance="authored_simulation",
            caseEligible=True,
        ),
    ).json()
    assert mechanism["effectiveEvidenceLevel"] == "guided"

    recognition_learner = f"subskill_{uuid4().hex}"
    recognition = client.post(
        "/learning-events/guided",
        json=_event(
            recognition_learner,
            caseId=None,
            caseProvenance="authored_simulation",
            caseEligible=True,
        ),
    ).json()
    assert recognition["effectiveEvidenceLevel"] == "guided"


def test_training_independent_receipt_requires_transfer_trace_localize_or_measure() -> None:
    rejected = [
        {"subskills": ["recognize"], "trainingPhase": "transfer", "evidenceSource": "trace_native"},
        {"subskills": ["measure"], "trainingPhase": "target", "evidenceSource": "trace_native"},
        {"subskills": ["measure"], "trainingPhase": "transfer", "evidenceSource": "response"},
    ]
    for overrides in rejected:
        learner = f"subskill_{uuid4().hex}"
        response = client.post(
            "/learning-events/guided",
            json=_event(
                learner,
                moduleId="train",
                sceneId="rate:transfer",
                interactionId=f"training-boundary-{uuid4().hex}",
                concept="rate",
                **overrides,
            ),
        )
        assert response.status_code == 200
        assert response.json()["effectiveEvidenceLevel"] == "guided"

    learner = f"subskill_{uuid4().hex}"
    accepted = client.post(
        "/learning-events/guided",
        json=_event(
            learner,
            moduleId="train",
            sceneId="rate:transfer",
            interactionId="training-rate-trace-transfer",
            concept="rate",
            subskills=["measure"],
            trainingPhase="transfer",
            evidenceSource="trace_native",
        ),
    )
    assert accepted.status_code == 200
    assert accepted.json()["effectiveEvidenceLevel"] == "guided"


def test_client_scored_event_cannot_move_independent_adaptive_evidence() -> None:
    learner = f"subskill_{uuid4().hex}"
    first = client.get(f"/practice/next?learnerId={learner}&subskill=recognize")
    assert first.status_code == 200
    assert "· recognize" in first.json()["reason"]

    learned = client.post(
        "/learning-events/guided",
        json=_event(
            learner,
            moduleId="rapid",
            sceneId="normal_ecg",
            interactionId="normal-recognition",
            concept="normal_ecg",
            subskills=["recognize"],
            caseId="3",
        ),
    )
    assert learned.status_code == 200
    assert learned.json()["effectiveEvidenceLevel"] == "guided"

    second = client.get(f"/practice/next?learnerId={learner}&subskill=recognize")
    assert second.status_code == 200
    assert "· recognize" in second.json()["reason"]
    profile = client.get(f"/learners/{learner}/mastery").json()
    row = next(
        item for item in profile["subskillMastery"]
        if item["concept"] == "normal_ecg" and item["subskill"] == "recognize"
    )
    assert row["independentAttempts"] == 0
