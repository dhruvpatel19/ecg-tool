from __future__ import annotations

from datetime import UTC, datetime, timedelta
import uuid

from fastapi.testclient import TestClient

from app.main import app, store


PASSWORD = "Sup3r-Clinical-Pw!"


def _register(client: TestClient, prefix: str) -> dict:
    username = f"{prefix}_{uuid.uuid4().hex[:10]}"
    response = client.post(
        "/auth/register", json={"username": username, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return {"username": username, **response.json()["user"]}


def _start(client: TestClient, *, tier: str = "shift", length: int = 2) -> tuple[str, str, dict]:
    response = client.post(
        "/clinical/shift/start",
        json={"lane": "clinic", "tier": tier, "length": length},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return body["session"]["sessionId"], body["next"]["itemId"], body


def _activate(client: TestClient, session_id: str, item_id: str, phase: str) -> dict:
    response = client.post(
        f"/clinical/shift/{session_id}/phase",
        json={"itemId": item_id, "phase": phase},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _reveal(client: TestClient, session_id: str, item_id: str) -> dict:
    response = client.post(
        f"/clinical/shift/{session_id}/context",
        json={
            "itemId": item_id,
            "answer": {"firstLookFinding": "uncertain", "firstLookConfidence": 3},
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_active_discovery_and_all_lifecycle_routes_are_owner_scoped() -> None:
    with TestClient(app) as owner, TestClient(app) as other:
        _register(owner, "clinical_owner")
        _register(other, "clinical_other")
        session_id, item_id, _ = _start(owner)

        active = owner.get("/clinical/shift/active")
        assert active.status_code == 200
        assert active.json()["session"]["sessionId"] == session_id
        assert active.json()["state"] == "orient"
        assert other.get("/clinical/shift/active").json()["session"] is None

        assert other.get(f"/clinical/shift/{session_id}").status_code == 404
        assert other.post(
            f"/clinical/shift/{session_id}/phase",
            json={"itemId": item_id, "phase": "orient"},
        ).status_code == 404
        assert other.post(
            f"/clinical/shift/{session_id}/context",
            json={
                "itemId": item_id,
                "answer": {"firstLookFinding": "uncertain", "firstLookConfidence": 3},
            },
        ).status_code == 404


def test_phase_activation_is_exactly_once_and_cross_device_resume_keeps_deadlines() -> None:
    with TestClient(app) as first, TestClient(app) as second:
        user = _register(first, "clinical_deadline")
        session_id, item_id, started = _start(first)
        assert started["session"]["orientStartedAt"] is None
        assert started["next"]["clock"]["phaseDeadlineAt"] is None

        activated = _activate(first, session_id, item_id, "orient")
        orient_start = activated["clock"]["orientStartedAt"]
        orient_deadline = activated["clock"]["orientDeadlineAt"]
        assert orient_start and orient_deadline
        replay = _activate(first, session_id, item_id, "orient")
        assert replay["clock"]["orientStartedAt"] == orient_start
        assert replay["clock"]["orientDeadlineAt"] == orient_deadline

        login = second.post(
            "/auth/login", json={"username": user["username"], "password": PASSWORD}
        )
        assert login.status_code == 200
        resumed_orient = second.get("/clinical/shift/active").json()
        assert resumed_orient["current"]["clock"]["orientDeadlineAt"] == orient_deadline

        revealed = _reveal(second, session_id, item_id)
        assert revealed["clock"]["decideStartedAt"] is None
        assert revealed["clock"]["decideDeadlineAt"] is None
        assert revealed["clock"]["activePhase"] == "decide"

        activated_decide = _activate(second, session_id, item_id, "decide")
        decide_start = activated_decide["clock"]["decideStartedAt"]
        decide_deadline = activated_decide["clock"]["decideDeadlineAt"]
        assert decide_start and decide_deadline
        decide_replay = _activate(second, session_id, item_id, "decide")
        assert decide_replay["clock"]["decideStartedAt"] == decide_start
        assert decide_replay["clock"]["decideDeadlineAt"] == decide_deadline
        resumed_decide = first.get("/clinical/shift/active").json()
        assert resumed_decide["state"] == "decide"
        assert resumed_decide["current"]["clock"]["decideDeadlineAt"] == decide_deadline


def test_timed_context_cannot_reveal_before_viewer_ready_activation() -> None:
    with TestClient(app) as client:
        _register(client, "clinical_ready")
        session_id, item_id, _ = _start(client)
        response = client.post(
            f"/clinical/shift/{session_id}/context",
            json={
                "itemId": item_id,
                "answer": {"firstLookFinding": "uncertain", "firstLookConfidence": 3},
            },
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "clinical_orient_not_activated"
        assert store.get_shift_session(session_id)["orientStartedAt"] is None


def test_server_derives_timeout_and_answer_time_ignoring_forged_client_timing() -> None:
    with TestClient(app) as client:
        _register(client, "clinical_forged")
        session_id, item_id, _ = _start(client)
        _activate(client, session_id, item_id, "orient")
        _reveal(client, session_id, item_id)
        _activate(client, session_id, item_id, "decide")
        durable = store.get_shift_session(session_id)
        assert durable is not None
        canonical_item_id = durable["pendingItemId"]

        now = datetime.now(UTC)
        with store.connect() as conn:
            conn.execute(
                "UPDATE clinical_shift_sessions SET pending_decide_started_at = ?, "
                "pending_decide_deadline_at = ? WHERE session_id = ?",
                (
                    (now - timedelta(seconds=10)).isoformat(),
                    (now - timedelta(seconds=1)).isoformat(),
                    session_id,
                ),
            )

        response = client.post(
            f"/clinical/shift/{session_id}/answer",
            json={
                "itemId": item_id,
                "answer": {
                    "confidence": 3,
                    "answerTimeMs": 1,
                    "confidenceTimeMs": 777_777,
                    "timedOut": False,
                },
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["grade"]["timedOut"] is True
        stored = store.get_shift_answer(session_id, canonical_item_id)
        assert stored is not None
        assert stored["response"]["timed_out"] is True
        assert stored["answerTimeMs"] >= 9_000
        assert stored["answerTimeMs"] != 1
        assert stored["response"]["confidence_time_ms"] is None
        assert stored["response"]["serverStartedAt"]
        assert stored["response"]["serverDeadlineAt"]


def test_feedback_and_report_hydrate_and_answer_replay_is_exactly_once() -> None:
    with TestClient(app) as first, TestClient(app) as second:
        user = _register(first, "clinical_feedback")
        session_id, item_id, _ = _start(first, tier="learn", length=1)
        _activate(first, session_id, item_id, "orient")
        _reveal(first, session_id, item_id)
        payload = {
            "itemId": item_id,
            "answer": {"confidence": 3, "answerTimeMs": 999_999, "timedOut": True},
        }
        first_answer = first.post(f"/clinical/shift/{session_id}/answer", json=payload)
        assert first_answer.status_code == 200, first_answer.text

        login = second.post(
            "/auth/login", json={"username": user["username"], "password": PASSWORD}
        )
        assert login.status_code == 200
        feedback = second.get("/clinical/shift/active").json()
        assert feedback["state"] == "feedback"
        assert feedback["current"]["itemId"] == item_id
        assert feedback["grade"] == first_answer.json()["grade"]
        assert feedback["answer"]["answerTimeMs"] != 999_999
        assert feedback["answer"]["timedOut"] is False

        replay = second.post(f"/clinical/shift/{session_id}/answer", json=payload)
        assert replay.status_code == 200
        assert replay.json()["replay"] is True
        assert replay.json()["answerId"] == first_answer.json()["answerId"]
        assert len(store.get_shift_answers(session_id)) == 1

        done = second.post(f"/clinical/shift/{session_id}/next")
        assert done.status_code == 200 and done.json()["done"] is True
        report = first.get("/clinical/shift/active").json()
        assert report["state"] == "report"
        assert report["report"]["answered"] == 1
