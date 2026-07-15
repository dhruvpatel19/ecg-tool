from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient

from app.main import app, repo, store


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
    assert "token" not in response.json()
    return response.json()["user"]


def test_pathway_progress_is_cookie_owned_merge_safe_and_idempotent() -> None:
    pathway_id = f"production-{uuid.uuid4().hex[:8]}"
    with TestClient(app) as owner, TestClient(app) as other, TestClient(app) as guest:
        owner_user = _register(owner, "path_owner")
        other_user = _register(other, "path_other")
        body = {
            "learnerId": other_user["userId"],
            "items": [{
                "pathwayId": pathway_id,
                "moduleId": "m05",
                "sceneId": "m05-s2",
                "status": "complete",
                "activeInteractionIndex": 2,
                "completedActionIds": ["measure-qrs", "mark-v1"],
                "state": {"equivalentRetryCount": 1},
            }],
        }
        first = owner.post(
            f"/learners/{other_user['userId']}/pathway-progress", json=body
        )
        assert first.status_code == 200, first.text
        assert first.json()["learnerId"] == owner_user["userId"]
        first_item = first.json()["items"][0]

        replay = owner.post(
            f"/learners/{other_user['userId']}/pathway-progress", json=body
        ).json()["items"][0]
        assert replay == first_item

        imported = owner.post(
            f"/learners/{owner_user['userId']}/pathway-progress",
            json={
                **body,
                "source": "guest_import",
                "items": [{
                    **body["items"][0],
                    "status": "viewed",
                    "activeInteractionIndex": 1,
                    "completedActionIds": ["guest-note"],
                    "state": {"imported": True},
                }],
            },
        ).json()["items"][0]
        assert imported["status"] == "complete"
        assert imported["activeInteractionIndex"] == 2
        assert set(imported["completedActionIds"]) == {"measure-qrs", "mark-v1", "guest-note"}
        assert imported["state"] == {"equivalentRetryCount": 1, "imported": True}

        owner_read = owner.get(
            f"/learners/{owner_user['userId']}/pathway-progress?pathwayId={pathway_id}"
        ).json()
        assert owner_read["items"] == [imported]
        assert other.get(
            f"/learners/{owner_user['userId']}/pathway-progress?pathwayId={pathway_id}"
        ).json() == {"learnerId": other_user["userId"], "items": []}
        assert guest.get(
            f"/learners/{owner_user['userId']}/pathway-progress?pathwayId={pathway_id}"
        ).json() == {"learnerId": "demo", "items": []}


def test_guided_competency_event_replay_is_exactly_once() -> None:
    with TestClient(app) as client:
        user = _register(client, "event_owner")
        event_key = f"evt-{uuid.uuid4().hex}"
        body = {
            "learnerId": "demo",
            "eventKey": event_key,
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
        first = client.post("/learning-events/guided", json=body)
        second = client.post("/learning-events/guided", json=body)
        assert first.status_code == second.status_code == 200
        assert first.json()["replay"] is False
        assert first.json()["effectiveEvidenceLevel"] == "guided"
        assert first.json()["receipts"][0]["retentionEligible"] is False
        assert first.json()["receipts"][0]["distinctSuccessfulEcgs"] == 0
        assert second.json()["replay"] is True
        assert second.json()["eventId"] == first.json()["eventId"]
        assert second.json()["receipts"] == first.json()["receipts"]

        profile = client.get(f"/learners/{user['userId']}/mastery").json()
        row = next(
            item for item in profile["subskillMastery"]
            if item["concept"] == "axis_normal" and item["subskill"] == "recognize"
        )
        assert row["attempts"] == 1
        assert row["independentAttempts"] == 0
        assert row["distinctEligibleEcgs"] == 0
        assert row["nextDueAt"] is None


def test_concept_practice_attempt_is_audit_only_for_legacy_objective_mastery() -> None:
    with TestClient(app) as client:
        user = _register(client, "training_owner")
        # The global case listing may begin with an ECG currently protected by
        # another test learner's active assessment. Guided's selector declares
        # and enforces a non-pending case, so this generic audit submission does
        # not bypass the pending-assessment commit gate.
        guided = client.get("/tutorials/orientation")
        assert guided.status_code == 200, guided.text
        case = guided.json()["recommendedCase"]
        # The learner packet is intentionally answer-blind. Test setup may use
        # the server repository to choose a valid objective for this audit.
        with store.connect() as conn:
            canonical_id = str(conn.execute(
                "SELECT ecg_id FROM learner_events WHERE owner_id = ? "
                "AND mode = 'guided' AND session_id = 'tutorial:orientation' "
                "ORDER BY occurred_at DESC LIMIT 1",
                (user["userId"],),
            ).fetchone()[0])
        assert case["caseId"] != canonical_id
        assert case["caseId"].startswith("ec_")
        packet = repo.get_case(canonical_id)
        assert packet is not None
        focus = packet["supported_objectives"][0]
        before = client.get(f"/learners/{user['userId']}").json()
        before_mastery = before["mastery"]

        response = client.post(
            "/attempts",
            json={
                "learnerId": "demo",
                "caseId": canonical_id,
                "mode": "concept_practice",
                "focusObjective": focus,
                "structuredAnswer": {"framework": "clerkship", "selectedConcepts": []},
                "freeTextAnswer": f"{focus}: target absent",
                "confidence": 5,
                "hintsUsed": 0,
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["grade"]["masteryDelta"] == {}
        assert response.json()["grade"]["legacyObjectiveMasterySuppressed"] is True

        after = client.get(f"/learners/{user['userId']}").json()
        assert after["mastery"] == before_mastery
        assert after["attemptCount"] == before["attemptCount"] + 1


def test_objective_registry_and_complete_unseen_competency_matrix() -> None:
    with TestClient(app) as client:
        user = _register(client, "objective_owner")
        registry = client.get("/objectives")
        assert registry.status_code == 200
        body = registry.json()
        assert body["registryVersion"]
        assert len(body["subskills"]) == 8
        by_id = {row["id"]: row for row in body["objectives"]}
        for objective_id in ("r_wave_progression", "poor_r_wave_progression", "pericarditis_pattern"):
            row = by_id[objective_id]
            assert row["unavailableReason"]
            assert row["coverage"]["independentEvidenceAvailable"] is False
        assert "reliableDistinctCases" in by_id["av_block_second_degree_mobitz_i"]["coverage"]

        state = client.get(f"/learners/{user['userId']}/competencies")
        assert state.status_code == 200
        state_body = state.json()
        assert state_body["learnerId"] == user["userId"]
        assert len(state_body["objectives"]) == len(body["objectives"])
        assert all(item["subskills"] for item in state_body["objectives"])
        assert all(
            cell["state"] == "unseen"
            for objective in state_body["objectives"]
            for cell in objective["subskills"]
        )
        assert all(
            cell["independentMastery"] == 0.0
            for objective in state_body["objectives"]
            for cell in objective["subskills"]
        )

        competency_by_id = {
            row["objectiveId"]: row for row in state_body["objectives"]
        }
        brady_application = next(
            cell
            for cell in competency_by_id["brady_context"]["subskills"]
            if cell["subskill"] == "apply_in_context"
        )
        assert brady_application["independentEvidenceAvailable"] is False
        assert brady_application["independentReceipt"] is None

        synthesis = next(
            cell
            for cell in competency_by_id["integrated_interpretation"]["subskills"]
            if cell["subskill"] == "synthesize"
        )
        assert synthesis["independentEvidenceAvailable"] is False
        assert synthesis["independentReceipt"] is None

        rbbb_recognition = next(
            cell
            for cell in competency_by_id["right_bundle_branch_block"]["subskills"]
            if cell["subskill"] == "recognize"
        )
        assert rbbb_recognition["independentEvidenceAvailable"] is True
        assert rbbb_recognition["independentReceipt"] == {
            "mode": "rapid",
            "caseConcept": "right_bundle_branch_block",
            "receiptConcept": "right_bundle_branch_block",
            "subskill": "recognize",
        }


def test_supported_selector_concepts_are_exposed_by_the_live_catalog() -> None:
    with TestClient(app) as client:
        groups = client.get("/concepts").json()["practiceGroups"]
        available = {
            concept["id"]
            for group in groups
            for concept in group["concepts"]
            if concept["available"]
        }
        if os.getenv("ECG_TEST_USE_CI_CORPUS") == "1":
            # The committed clean-runner fixture is intentionally only the 103
            # real PTB ECGs bound to the Clinical bank. It must fail closed for
            # concepts below the same three-case release threshold; exhaustive
            # selector coverage is asserted against the full release corpus.
            assert "electrolyte_drug_pattern" in available
            assert {"paced_rhythm", "posterior_mi"}.isdisjoint(available)
        else:
            assert {
                "paced_rhythm",
                "electrolyte_drug_pattern",
                "posterior_mi",
            } <= available
