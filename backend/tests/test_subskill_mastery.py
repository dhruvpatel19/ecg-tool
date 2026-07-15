from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app, store
from app.objectives import REGISTRY_VERSION


client = TestClient(app)


def _test_owner_session() -> tuple[str, str]:
    suffix = uuid4().hex
    owner_id = f"u_{suffix[:16]}"
    username = f"subskill_{suffix[:20]}"
    token = f"test-session-{suffix}"
    store.create_user(owner_id, username, "Subskill test learner", "unused-test-hash")
    store.ensure_profile(owner_id, "Subskill test learner")
    store.create_session(
        token,
        owner_id,
        (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    )
    return owner_id, token


@pytest.fixture(autouse=True)
def _isolated_authenticated_owner():
    """Give every test one real owner instead of sharing the test-mode guest.

    Learner ids in request paths and bodies are advisory by design. Reusing the
    anonymous ``demo`` owner made earlier tests' valid evidence look like a
    double projection in later tests. A direct test session keeps these focused
    checks fast while exercising the production owner-binding boundary.
    """

    owner_id, token = _test_owner_session()
    client.cookies.clear()
    client.headers["Authorization"] = f"Bearer {token}"
    try:
        yield owner_id
    finally:
        client.headers.pop("Authorization", None)
        client.cookies.clear()


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
    assert body["registryVersion"] == REGISTRY_VERSION
    assert body["receipts"][0]["registryVersion"] == REGISTRY_VERSION
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


def test_guided_event_key_replays_one_checkpoint_but_preserves_a_later_identical_attempt() -> None:
    learner = f"subskill_{uuid4().hex}"
    first_key = f"foundations:{uuid4().hex}"
    second_key = f"foundations:{uuid4().hex}"
    payload = _event(
        learner,
        eventKey=first_key,
        moduleId="foundations",
        sceneId="S3",
        interactionId="wave-checkpoint",
        evidenceLevel="guided",
        caseId=None,
        caseProvenance="authored_simulation",
        caseEligible=False,
    )

    first = client.post("/learning-events/guided", json=payload)
    retry = client.post("/learning-events/guided", json=payload)
    later = client.post(
        "/learning-events/guided",
        json={**payload, "eventKey": second_key},
    )

    assert first.status_code == retry.status_code == later.status_code == 200
    assert first.json()["replay"] is False
    assert retry.json()["replay"] is True
    assert retry.json()["eventId"] == first.json()["eventId"]
    assert later.json()["replay"] is False
    assert later.json()["eventId"] != first.json()["eventId"]

    profile = client.get(f"/learners/{learner}/mastery").json()
    owner_id = profile["learnerId"]
    assert owner_id.startswith("u_")
    assert owner_id != learner
    row = next(
        item
        for item in profile["subskillMastery"]
        if item["concept"] == "axis_normal" and item["subskill"] == "recognize"
    )
    assert row["attempts"] == 2
    assert row["independentAttempts"] == 0
    with store.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM guided_learning_events WHERE learner_id = ? "
            "AND event_key IN (?, ?)",
            (owner_id, first_key, second_key),
        ).fetchone()[0] == 2
        assert conn.execute(
            "SELECT COUNT(*) FROM learner_events WHERE owner_id = ? "
            "AND mode = 'guided' AND event_type = 'interaction_committed'",
            (owner_id,),
        ).fetchone()[0] == 2
        assert conn.execute(
            "SELECT COUNT(*) FROM guided_learning_events WHERE learner_id = ?",
            (learner,),
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM learner_events WHERE owner_id = ?",
            (learner,),
        ).fetchone()[0] == 0


def test_guided_event_key_is_owner_scoped_and_changed_payload_returns_conflict(
    _isolated_authenticated_owner,
) -> None:
    first_owner = _isolated_authenticated_owner
    shared_key = f"same-action:{uuid4().hex}"
    payload = _event(
        "untrusted-client-owner",
        eventKey=shared_key,
        moduleId="foundations",
        sceneId="S3",
        interactionId="wave-checkpoint",
        evidenceLevel="guided",
        caseId=None,
        caseProvenance="authored_simulation",
        caseEligible=False,
    )

    first = client.post("/learning-events/guided", json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["replay"] is False

    second_owner, second_token = _test_owner_session()
    with TestClient(app) as second_client:
        second_client.headers["Authorization"] = f"Bearer {second_token}"
        second = second_client.post("/learning-events/guided", json=payload)
    assert second.status_code == 200, second.text
    assert second.json()["replay"] is False

    conflict = client.post(
        "/learning-events/guided",
        json={**payload, "score": 0.25, "correct": False},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "guided_event_idempotency_conflict"
    replay = client.post("/learning-events/guided", json=payload)
    assert replay.status_code == 200
    assert replay.json()["replay"] is True

    with store.connect() as conn:
        normalized = conn.execute(
            "SELECT event_id, owner_id FROM learner_events "
            "WHERE owner_id IN (?, ?) AND mode = 'guided'",
            (first_owner, second_owner),
        ).fetchall()
        assert len(normalized) == 2
        assert {row["owner_id"] for row in normalized} == {
            first_owner,
            second_owner,
        }
        assert len({row["event_id"] for row in normalized}) == 2
        for owner_id in (first_owner, second_owner):
            assert conn.execute(
                "SELECT attempts FROM subskill_mastery WHERE learner_id = ? "
                "AND concept = 'axis_normal' AND subskill = 'recognize'",
                (owner_id,),
            ).fetchone()[0] == 1


def test_guided_event_rejects_unknown_or_unregistered_competency_cells() -> None:
    unknown_learner = f"subskill_{uuid4().hex}"
    unknown = client.post(
        "/learning-events/guided",
        json=_event(unknown_learner, concept="invented_hidden_objective"),
    )
    assert unknown.status_code == 422

    mismatch_learner = f"subskill_{uuid4().hex}"
    mismatch = client.post(
        "/learning-events/guided",
        json=_event(
            mismatch_learner,
            concept="qrs_complex",
            subskills=["recognize"],
        ),
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["detail"]["code"] == "objective_subskill_not_registered"

    for learner in (unknown_learner, mismatch_learner):
        profile = client.get(f"/learners/{learner}/mastery").json()
        assert not any(
            row["concept"] in {"invented_hidden_objective", "qrs_complex"}
            for row in profile["subskillMastery"]
        )


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
