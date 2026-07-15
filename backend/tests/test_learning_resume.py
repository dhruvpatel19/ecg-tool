from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient

from app import main as main_module
from app.auth import AuthService
from app.guest_progress import GuestProgressService
from app.main import app, store
from app.storage import LearningStore


_PASSWORD = "Sup3r-Secret-Pw!"


def _register(client: TestClient, prefix: str) -> dict:
    response = client.post(
        "/auth/register",
        json={
            "username": f"{prefix}_{uuid.uuid4().hex[:10]}",
            "password": _PASSWORD,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["user"]


def _insert_resume_rows(learner_id: str) -> None:
    with store.connect() as conn:
        guided = [
            # Scene order intentionally disagrees with activity order. M02.S2 is
            # the actual newest resumable scene; complete/skipped and an
            # unallowlisted client-written destination must not win.
            ("production-curriculum", "leads-vectors", "M02.S10", "attempted", "2026-07-14T09:00:00+00:00"),
            ("production-curriculum", "leads-vectors", "M02.S2", "viewed", "2026-07-14T10:00:00+00:00"),
            ("production-curriculum", "leads-vectors", "M02.S3", "complete", "2026-07-14T11:00:00+00:00"),
            ("production-curriculum", "leads-vectors", "M02.S4", "skipped", "2026-07-14T12:00:00+00:00"),
            ("production-curriculum", "https:evil.example", "redirect", "viewed", "2026-07-14T13:00:00+00:00"),
        ]
        conn.executemany(
            "INSERT INTO pathway_progress (learner_id, pathway_id, module_id, scene_id, "
            "status, active_interaction_index, completed_action_ids_json, state_json, "
            "source, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 0, '[]', '{}', "
            "'server', ?, ?)",
            [(learner_id, *row[:4], row[4], row[4]) for row in guided],
        )
        conn.execute(
            "INSERT INTO training_campaigns (campaign_id, learner_id, concept_id, subskill, "
            "requested_length, length, pool_count, phases_json, phase_counts_json, position, "
            "feedback_case_id, status, context_key, roster_policy_json, created_at, updated_at) "
            "VALUES ('tc_resume_secret', ?, 'atrial_fibrillation', 'recognize', 10, 10, 100, "
            "'[]', '{}', 3, 'training_case_secret', 'active', 'context_secret', '{}', ?, ?)",
            (learner_id, "2026-07-14T12:00:00+00:00", "2026-07-14T12:00:00+00:00"),
        )
        conn.execute(
            "INSERT INTO rapid_rounds (round_id, learner_id, pace, length, assessment_scope, "
            "pending_case_id, pending_manifest_json, pending_started_at, pending_deadline_at, "
            "deadline_seconds, position, status, created_at, updated_at) "
            "VALUES ('rr_resume_secret', ?, 'emergency', 5, 'dominant_finding', "
            "'rapid_case_secret', '{\"answerKey\":\"secret\"}', ?, '2099-01-01T00:00:00+00:00', "
            "30, 1, 'active', ?, ?)",
            (
                learner_id,
                "2026-07-14T01:00:00+00:00",
                "2026-07-14T01:00:00+00:00",
                "2026-07-14T01:00:00+00:00",
            ),
        )
        conn.execute(
            "INSERT INTO clinical_shift_sessions (session_id, learner_id, lane, tier, length, "
            "requested_length, available_length, served_json, served_ecgs_json, calibration_json, "
            "feedback_item_id, position, status, created_at, updated_at) "
            "VALUES ('cs_resume_secret', ?, 'ward', 'core', 5, 5, 5, "
            "'[\"clinical_item_secret\"]', '[\"clinical_ecg_secret\"]', '[]', "
            "'clinical_item_secret', 2, 'active', ?, ?)",
            (learner_id, "2026-07-14T13:00:00+00:00", "2026-07-14T13:00:00+00:00"),
        )


def test_resume_is_owner_bound_read_only_structured_and_priority_ordered() -> None:
    with TestClient(app) as owner, TestClient(app) as other:
        owner_user = _register(owner, "resume_owner")
        _register(other, "resume_other")
        _insert_resume_rows(owner_user["userId"])

        with store.connect() as conn:
            before = tuple(conn.execute(
                "SELECT pending_case_id, feedback_case_id, pending_deadline_at, status, updated_at "
                "FROM rapid_rounds WHERE round_id = 'rr_resume_secret'"
            ).fetchone())

        response = owner.get("/learning/resume?learnerId=somebody-else")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store, private"
        assert response.headers["pragma"] == "no-cache"
        payload = response.json()
        assert payload["version"] == "learning-resume-v1"

        assert payload["primary"] == {
            "mode": "rapid",
            "phase": "deadline",
            "completed": 1,
            "total": 5,
            "updatedAt": "2026-07-14T01:00:00+00:00",
            "destination": {"kind": "rapid"},
        }
        assert [item["mode"] for item in payload["additional"]] == [
            "clinical",
            "training",
            "guided",
        ]
        guided = payload["additional"][-1]
        assert guided == {
            "mode": "guided",
            "phase": "in_progress",
            "completed": 1,
            "total": 15,
            "updatedAt": "2026-07-14T10:00:00+00:00",
            "destination": {
                "kind": "guided",
                "moduleId": "leads-vectors",
                "sceneId": "M02.S2",
            },
        }

        serialized = json.dumps(payload, sort_keys=True)
        for secret in (
            "rr_resume_secret",
            "tc_resume_secret",
            "cs_resume_secret",
            "rapid_case_secret",
            "training_case_secret",
            "clinical_item_secret",
            "clinical_ecg_secret",
            "context_secret",
            "answerKey",
            "evil.example",
        ):
            assert secret not in serialized

        with store.connect() as conn:
            after = tuple(conn.execute(
                "SELECT pending_case_id, feedback_case_id, pending_deadline_at, status, updated_at "
                "FROM rapid_rounds WHERE round_id = 'rr_resume_secret'"
            ).fetchone())
        assert after == before

        # Neither an advisory query parameter nor another signed-in account can
        # select the owner's snapshot.
        assert other.get(
            f"/learning/resume?learnerId={owner_user['userId']}"
        ).json()["primary"] is None


def test_resume_tie_break_is_deterministic_and_invalid_guided_rows_are_ignored() -> None:
    with TestClient(app) as client:
        user = _register(client, "resume_tie")
        learner_id = user["userId"]
        timestamp = "2026-07-14T15:00:00+00:00"
        with store.connect() as conn:
            conn.execute(
                "INSERT INTO pathway_progress (learner_id, pathway_id, module_id, scene_id, "
                "status, active_interaction_index, completed_action_ids_json, state_json, source, "
                "created_at, updated_at) VALUES (?, 'production-curriculum', 'leads-vectors', "
                "'m99-s999', 'viewed', 0, '[]', '{}', 'server', ?, ?)",
                (learner_id, timestamp, timestamp),
            )
            conn.execute(
                "INSERT INTO training_campaigns (campaign_id, learner_id, concept_id, subskill, "
                "requested_length, length, pool_count, phases_json, phase_counts_json, position, "
                "feedback_case_id, status, context_key, roster_policy_json, created_at, updated_at) "
                "VALUES (?, ?, 'normal_ecg', 'recognize', 5, 5, 5, '[]', '{}', 1, "
                "'training_feedback', 'active', '', '{}', ?, ?)",
                (f"tc_{uuid.uuid4().hex}", learner_id, timestamp, timestamp),
            )
            conn.execute(
                "INSERT INTO clinical_shift_sessions (session_id, learner_id, lane, tier, length, "
                "requested_length, available_length, served_json, served_ecgs_json, calibration_json, "
                "feedback_item_id, position, status, created_at, updated_at) VALUES (?, ?, 'ward', "
                "'core', 5, 5, 5, '[]', '[]', '[]', 'clinical_feedback', 1, 'active', ?, ?)",
                (f"cs_{uuid.uuid4().hex}", learner_id, timestamp, timestamp),
            )

        first = client.get("/learning/resume").json()
        second = client.get("/learning/resume").json()
        assert first["primary"]["mode"] == "training"
        assert first["additional"][0]["mode"] == "clinical"
        assert all(item["mode"] != "guided" for item in [first["primary"], *first["additional"]])
        # generatedAt is intentionally fresh; the ordered projection is stable.
        assert first["primary"] == second["primary"]
        assert first["additional"] == second["additional"]


def test_expired_clocks_are_not_presented_as_running_deadlines() -> None:
    with TestClient(app) as client:
        user = _register(client, "resume_expired")
        learner_id = user["userId"]
        expired = "2000-01-01T00:00:00+00:00"
        updated = "2026-07-14T16:00:00+00:00"
        with store.connect() as conn:
            conn.execute(
                "INSERT INTO rapid_rounds (round_id, learner_id, pace, length, assessment_scope, "
                "pending_case_id, pending_manifest_json, pending_started_at, pending_deadline_at, "
                "deadline_seconds, position, status, created_at, updated_at) VALUES (?, ?, "
                "'emergency', 5, 'dominant_finding', 'expired_rapid_case', '{}', ?, ?, 30, 1, "
                "'active', ?, ?)",
                (f"rr_{uuid.uuid4().hex}", learner_id, expired, expired, updated, updated),
            )
            conn.execute(
                "INSERT INTO clinical_shift_sessions (session_id, learner_id, lane, tier, length, "
                "requested_length, available_length, served_json, served_ecgs_json, calibration_json, "
                "pending_item_id, pending_orient_started_at, pending_orient_deadline_at, position, "
                "status, created_at, updated_at) VALUES (?, ?, 'ed', 'core', 5, 5, 5, '[]', '[]', "
                "'[]', 'expired_clinical_item', ?, ?, 0, 'active', ?, ?)",
                (f"cs_{uuid.uuid4().hex}", learner_id, expired, expired, updated, updated),
            )

        payload = client.get("/learning/resume").json()
        candidates = [payload["primary"], *payload["additional"]]
        phases = {item["mode"]: item["phase"] for item in candidates}
        assert phases["rapid"] == "in_progress"
        assert phases["clinical"] == "in_progress"


def test_guest_guided_resume_is_server_hydratable_and_survives_account_claim(
    tmp_path, monkeypatch
) -> None:
    # Test mode intentionally maps anonymous requests to the legacy ``demo``
    # owner. Other guest-claim tests also exercise that owner, so this lifecycle
    # contract needs its own store instead of depending on suite order or
    # deleting another test's durable claim receipt.
    isolated_store = LearningStore(tmp_path / f"resume-claim-{uuid.uuid4().hex}.db")
    isolated_claims = GuestProgressService(isolated_store)
    isolated_auth = AuthService(isolated_store, isolated_claims)
    monkeypatch.setattr(main_module, "store", isolated_store)
    monkeypatch.setattr(main_module, "guest_progress_service", isolated_claims)
    monkeypatch.setattr(main_module, "auth_service", isolated_auth)

    with TestClient(app) as client:
        assert client.get("/auth/me").status_code == 200
        saved = client.post(
            "/learners/demo/pathway-progress",
            json={
                "learnerId": "an-arbitrary-client-value",
                "source": "server",
                "merge": True,
                "items": [
                    {
                        "pathwayId": "foundations-curriculum",
                        "moduleId": "foundations",
                        "sceneId": "foundations-progress",
                        "status": "attempted",
                        "activeInteractionIndex": 4,
                        "completedActionIds": ["S0", "S1", "S2"],
                        "state": {
                            "completedScenes": 3,
                            "totalScenes": 13,
                            "foundationState": {
                                "completed": ["S0", "S1", "S2"],
                                "skipped": [],
                                "current": 4,
                                "bestAccuracy": 0,
                                "nv": {},
                                "testedOut": {},
                            },
                        },
                    }
                ],
            },
        )
        assert saved.status_code == 200, saved.text

        guest_resume = client.get("/learning/resume").json()
        assert guest_resume["version"] == "learning-resume-v1"
        assert guest_resume["primary"] == {
            "mode": "guided",
            "phase": "in_progress",
            "completed": 3,
            "total": 13,
            "updatedAt": saved.json()["items"][0]["updatedAt"],
            "destination": {
                "kind": "guided",
                "moduleId": "foundations",
                "sceneId": None,
            },
        }

        registration = client.post(
            "/auth/register",
            json={
                "username": f"resume_claim_{uuid.uuid4().hex[:10]}",
                "password": _PASSWORD,
                "claimGuestProgress": True,
            },
        )
        assert registration.status_code == 200, registration.text
        assert registration.json()["guestClaim"]["guestProgress"]["lessonScenes"] == 1

        account_resume = client.get("/learning/resume").json()
        assert account_resume["primary"]["mode"] == "guided"
        assert account_resume["primary"]["completed"] == 3
        assert account_resume["primary"]["destination"] == guest_resume["primary"]["destination"]
