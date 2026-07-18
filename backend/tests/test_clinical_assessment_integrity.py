from __future__ import annotations

from datetime import UTC, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import uuid

import pytest
from fastapi.testclient import TestClient

from app.assessment_ledger import create_lease, record_guided_packet_exposure
from app.clinical import shift
from app.main import app, clinical_item_store, clinical_packet, store


PASSWORD = "Clinical-Ledger-9!"


def _register(client: TestClient, prefix: str) -> str:
    response = client.post(
        "/auth/register",
        json={
            "username": f"{prefix}_{uuid.uuid4().hex[:10]}",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["user"]["userId"]


def _start(client: TestClient, *, length: int = 1) -> tuple[str, str, str]:
    response = client.post(
        "/clinical/shift/start",
        json={"lane": "clinic", "tier": "learn", "length": length},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    session_id = payload["session"]["sessionId"]
    item_id = payload["next"]["itemId"]
    authored = clinical_item_store.get_item(
        store.get_shift_session(session_id)["pendingItemId"]
    )
    assert authored is not None
    return session_id, item_id, authored.ecg_id


def _reveal(client: TestClient, session_id: str, item_id: str) -> dict:
    response = client.post(
        f"/clinical/shift/{session_id}/context",
        json={
            "itemId": item_id,
            "answer": {
                "firstLookFinding": "uncertain",
                "firstLookConfidence": 3,
            },
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _answer_payload(client: TestClient, session_id: str, item_id: str) -> dict:
    current = _reveal(client, session_id, item_id)
    item = current["item"]
    answer: dict = {"confidence": 3}
    if item.get("stepwise_state"):
        while item["stepwise_state"]["active"] is not None:
            active = item["stepwise_state"]["active"]
            committed = client.post(
                f"/clinical/shift/{session_id}/step",
                json={
                    "itemId": item_id,
                    "stepIndex": active["stepIndex"],
                    "answerIndex": 0,
                },
            )
            assert committed.status_code == 200, committed.text
            item = committed.json()["item"]
    if item.get("matching_task"):
        answer["matches"] = {
            row["id"]: item["matching_task"]["choices"][index]["id"]
            for index, row in enumerate(item["matching_task"]["rows"])
        }
    elif item.get("fill_in_task"):
        answer["fillInValue"] = item["fill_in_task"]["min_value"]
    elif item.get("options"):
        answer["selectedOptionId"] = item["options"][0]["id"]
    elif item["question_type"] in {"click", "spoterror"}:
        lead = (item.get("clickable_leads") or ["II"])[0]
        answer["click"] = {"lead": lead, "timeSec": 0.5}
        if item["question_type"] == "spoterror":
            answer["machineLineId"] = item["machine_read"][0]["id"]
    return {"itemId": item_id, "answer": answer}


def test_presentation_freezes_real_ecg_and_emits_answer_free_event() -> None:
    with TestClient(app) as client:
        learner_id = _register(client, "clinical_presented")
        session_id, item_id, ecg_id = _start(client)
        with store.connect() as conn:
            lease = conn.execute(
                "SELECT lease_id, owner_id, mode, session_id, state, integrity_status "
                "FROM assessment_leases WHERE owner_id = ? AND mode = 'clinical' "
                "AND session_id = ?",
                (learner_id, session_id),
            ).fetchone()
            assert lease is not None
            assert tuple(lease)[1:] == (
                learner_id,
                "clinical",
                session_id,
                "active",
                "atomic_v2",
            )
            cases = conn.execute(
                "SELECT ecg_id, ordinal FROM assessment_lease_cases WHERE lease_id = ?",
                (lease["lease_id"],),
            ).fetchall()
            assert [tuple(row) for row in cases] == [(ecg_id, 0)]
            event = conn.execute(
                "SELECT event_type, score FROM learner_events WHERE lease_id = ?",
                (lease["lease_id"],),
            ).fetchone()
            assert tuple(event) == ("item_presented", None)
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(learner_events)").fetchall()
            }
        assert item_id
        assert not columns.intersection({"answer", "response", "grade", "feedback"})


def test_answer_atomically_submits_lease_event_attempt_and_progress_then_replays() -> None:
    with TestClient(app) as client:
        learner_id = _register(client, "clinical_atomic")
        session_id, item_id, ecg_id = _start(client)
        payload = _answer_payload(client, session_id, item_id)
        first = client.post(f"/clinical/shift/{session_id}/answer", json=payload)
        assert first.status_code == 200, first.text
        replay = client.post(
            f"/clinical/shift/{session_id}/answer",
            json={"itemId": item_id, "answer": {"confidence": 5}},
        )
        assert replay.status_code == 200
        assert replay.json()["replay"] is True
        assert replay.json()["answerId"] == first.json()["answerId"]
        with store.connect() as conn:
            lease = conn.execute(
                "SELECT lease_id, state, integrity_status FROM assessment_leases "
                "WHERE owner_id = ? AND mode = 'clinical' AND session_id = ?",
                (learner_id, session_id),
            ).fetchone()
            assert (lease["state"], lease["integrity_status"]) == (
                "submitted",
                "atomic_v2",
            )
            event = conn.execute(
                "SELECT event_type, ecg_id, score, evidence_level FROM learner_events "
                "WHERE lease_id = ? AND event_type = 'answer_committed'",
                (lease["lease_id"],),
            ).fetchone()
            assert event is not None
            assert (event["event_type"], event["ecg_id"], event["evidence_level"]) == (
                "answer_committed",
                ecg_id,
                "formative",
            )
            assert 0.0 <= float(event["score"]) <= 1.0
            assert conn.execute(
                "SELECT COUNT(*) FROM clinical_shift_answers WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0] == 1
            assert conn.execute(
                "SELECT COUNT(*) FROM attempts WHERE learner_id = ? "
                "AND mode = 'clinical_decision' AND case_id = ?",
                (learner_id, ecg_id),
            ).fetchone()[0] == 1
            assert conn.execute(
                "SELECT COUNT(*) FROM learner_events WHERE lease_id = ? "
                "AND event_type = 'answer_committed'",
                (lease["lease_id"],),
            ).fetchone()[0] == 1
            assert {
                row["event_type"]
                for row in conn.execute(
                    "SELECT event_type FROM learner_events WHERE owner_id = ? "
                    "AND mode = 'clinical' AND session_id = ?",
                    (learner_id, session_id),
                ).fetchall()
            } == {"session_started", "item_presented", "answer_committed", "session_completed"}


def test_recoverable_finalization_failure_rolls_back_and_releases_claim(monkeypatch) -> None:
    with TestClient(app) as client:
        learner_id = _register(client, "clinical_release")
        session_id, item_id, ecg_id = _start(client)
        payload = _answer_payload(client, session_id, item_id)
        original = store._save_attempt_in_transaction

        def fail_after_formative_write(*args, **kwargs):
            raise RuntimeError("injected Clinical finalization failure")

        monkeypatch.setattr(store, "_save_attempt_in_transaction", fail_after_formative_write)
        with pytest.raises(RuntimeError, match="injected Clinical"):
            client.post(f"/clinical/shift/{session_id}/answer", json=payload)
        monkeypatch.setattr(store, "_save_attempt_in_transaction", original)

        with store.connect() as conn:
            lease = conn.execute(
                "SELECT state, submission_key_hash FROM assessment_leases "
                "WHERE owner_id = ? AND mode = 'clinical' AND session_id = ?",
                (learner_id, session_id),
            ).fetchone()
            assert tuple(lease) == ("active", None)
            assert conn.execute(
                "SELECT COUNT(*) FROM clinical_shift_answers WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT COUNT(*) FROM attempts WHERE learner_id = ? "
                "AND mode = 'clinical_decision' AND case_id = ?",
                (learner_id, ecg_id),
            ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT COUNT(*) FROM learner_events WHERE owner_id = ? "
                "AND mode = 'clinical' AND event_type = 'answer_committed'",
                (learner_id,),
            ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT COUNT(*) FROM subskill_mastery WHERE learner_id = ?",
                (learner_id,),
            ).fetchone()[0] == 0

        retry = client.post(f"/clinical/shift/{session_id}/answer", json=payload)
        assert retry.status_code == 200, retry.text


def test_concurrent_same_case_submissions_commit_one_answer_and_one_event() -> None:
    username = f"clinical_race_{uuid.uuid4().hex[:8]}"
    with TestClient(app) as first, TestClient(app) as second:
        registered = first.post(
            "/auth/register", json={"username": username, "password": PASSWORD}
        )
        assert registered.status_code == 200, registered.text
        learner_id = registered.json()["user"]["userId"]
        login = second.post(
            "/auth/login", json={"username": username, "password": PASSWORD}
        )
        assert login.status_code == 200, login.text
        session_id, item_id, _ = _start(first)
        payload = _answer_payload(first, session_id, item_id)

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(
                    lambda client: client.post(
                        f"/clinical/shift/{session_id}/answer", json=payload
                    ),
                    (first, second),
                )
            )
        assert [response.status_code for response in responses] == [200, 200]
        assert len({response.json()["answerId"] for response in responses}) == 1
        assert sum(bool(response.json()["replay"]) for response in responses) == 1
        with store.connect() as conn:
            lease = conn.execute(
                "SELECT lease_id, state FROM assessment_leases WHERE owner_id = ? "
                "AND mode = 'clinical' AND session_id = ?",
                (learner_id, session_id),
            ).fetchone()
            assert lease["state"] == "submitted"
            assert conn.execute(
                "SELECT COUNT(*) FROM clinical_shift_answers WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0] == 1
            assert conn.execute(
                "SELECT COUNT(*) FROM learner_events WHERE lease_id = ? "
                "AND event_type = 'answer_committed'",
                (lease["lease_id"],),
            ).fetchone()[0] == 1


def test_owner_live_exposure_is_hard_excluded_across_modes() -> None:
    with TestClient(app) as client:
        learner_id = _register(client, "clinical_exposure")
        blocked = [
            item
            for item in clinical_item_store.list_for_serving(
                situation="clinic", status="harness_pass"
            )
        ][:3]
        now = datetime.now(UTC)
        with store.connect() as conn:
            create_lease(
                conn,
                lease_id=f"cross_{uuid.uuid4().hex}",
                owner_id=learner_id,
                mode="training",
                session_id=f"cross-training-{uuid.uuid4().hex}",
                ecg_ids=(blocked[0].ecg_id,),
                created_at=now,
                expires_at=now + timedelta(days=1),
            )
            record_guided_packet_exposure(
                conn,
                owner_id=learner_id,
                lesson_id="clinical-cross-mode",
                ecg_id=blocked[1].ecg_id,
                occurred_at=now,
            )
        store.save_attempt(
            learner_id=learner_id,
            case_id=blocked[2].ecg_id,
            mode="concept_practice",
            structured_answer={},
            free_text_answer="",
            confidence=3,
            hints_used=0,
            grade={
                "score": 0.0,
                "correctObjectives": [],
                "missedObjectives": [],
                "misconceptions": [],
                "feedback": "",
                "masteryDelta": {},
            },
        )
        _, item_id, served_ecg = _start(client)
        assert item_id
        assert served_ecg not in {item.ecg_id for item in blocked}


def test_full_103_case_bank_is_reachable_without_shortlist_or_repeat_bias() -> None:
    """Exhaust the three honest setting pools through the production selector.

    Session setup caps each lane to its real distinct-ECG depth, so the complete
    bank is covered by three pedagogically coherent sets rather than one mixed
    103-case marathon.
    """

    learner_id = f"u_clinical_reach_{uuid.uuid4().hex}"
    store.ensure_profile(learner_id)
    reached: set[str] = set()
    expected_by_lane = {"clinic": 35, "ed": 34, "ward": 34}
    for lane, expected_count in expected_by_lane.items():
        served_items: list[str] = []
        served_ecgs: set[str] = set()
        while True:
            item = shift._select_next(
                store,
                clinical_item_store,
                clinical_packet,
                lane,
                served_items,
                served_ecgs,
                learner_id,
            )
            if item is None:
                break
            assert item.situation == lane
            assert item.item_id not in served_items
            assert item.ecg_id not in served_ecgs
            served_items.append(item.item_id)
            served_ecgs.add(item.ecg_id)
        assert len(served_items) == expected_count
        assert len(served_ecgs) == expected_count
        assert not reached.intersection(served_ecgs)
        reached.update(served_ecgs)
    assert len(reached) == 103
    assert reached == {
        item.ecg_id
        for item in clinical_item_store.list_for_serving(status="harness_pass")
    }


def test_stale_presentation_expires_once_and_active_resume_rotates_case() -> None:
    with TestClient(app) as client:
        learner_id = _register(client, "clinical_expiry")
        session_id, _, first_ecg = _start(client, length=2)
        now = datetime.now(UTC)
        with store.connect() as conn:
            lease_id = conn.execute(
                "SELECT lease_id FROM assessment_leases WHERE owner_id = ? "
                "AND mode = 'clinical' AND session_id = ? AND state = 'active'",
                (learner_id, session_id),
            ).fetchone()["lease_id"]
            conn.execute(
                "UPDATE assessment_leases SET expires_at = ? WHERE lease_id = ?",
                ((now - timedelta(seconds=1)).isoformat(), lease_id),
            )
        resumed = client.get("/clinical/shift/active")
        assert resumed.status_code == 200, resumed.text
        assert resumed.json()["state"] == "orient"
        replacement_id = resumed.json()["current"]["itemId"]
        replacement = clinical_item_store.get_item(
            store.get_shift_session(session_id)["pendingItemId"]
        )
        assert replacement is not None and replacement.ecg_id != first_ecg
        assert client.get("/clinical/shift/active").status_code == 200
        with store.connect() as conn:
            assert conn.execute(
                "SELECT state FROM assessment_leases WHERE lease_id = ?", (lease_id,)
            ).fetchone()["state"] == "expired"
            assert conn.execute(
                "SELECT COUNT(*) FROM learner_events WHERE lease_id = ? "
                "AND event_type = 'item_expired'",
                (lease_id,),
            ).fetchone()[0] == 1


def test_answer_at_inclusive_lease_expiry_fails_closed_and_clears_stale_case() -> None:
    with TestClient(app) as client:
        learner_id = _register(client, "clinical_due")
        session_id, item_id, _ = _start(client)
        payload = _answer_payload(client, session_id, item_id)
        with store.connect() as conn:
            lease_id = conn.execute(
                "SELECT lease_id FROM assessment_leases WHERE owner_id = ? "
                "AND mode = 'clinical' AND session_id = ? AND state = 'active'",
                (learner_id, session_id),
            ).fetchone()["lease_id"]
            conn.execute(
                "UPDATE assessment_leases SET expires_at = ? WHERE lease_id = ?",
                ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(), lease_id),
            )
        response = client.post(f"/clinical/shift/{session_id}/answer", json=payload)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "clinical_item_expired"
        assert store.get_shift_session(session_id)["pendingItemId"] is None
        with store.connect() as conn:
            assert conn.execute(
                "SELECT state FROM assessment_leases WHERE lease_id = ?", (lease_id,)
            ).fetchone()["state"] == "expired"
            assert conn.execute(
                "SELECT COUNT(*) FROM learner_events WHERE lease_id = ? "
                "AND event_type = 'item_expired'",
                (lease_id,),
            ).fetchone()[0] == 1


def test_abandon_terminalizes_pending_lease_once_without_erasing_evidence() -> None:
    with TestClient(app) as client:
        learner_id = _register(client, "clinical_abandon")
        session_id, _, _ = _start(client, length=2)
        with store.connect() as conn:
            lease_id = conn.execute(
                "SELECT lease_id FROM assessment_leases WHERE owner_id = ? "
                "AND mode = 'clinical' AND session_id = ? AND state = 'active'",
                (learner_id, session_id),
            ).fetchone()["lease_id"]
        first = client.post(f"/clinical/shift/{session_id}/abandon")
        assert first.status_code == 200, first.text
        replay = client.post(f"/clinical/shift/{session_id}/abandon")
        assert replay.status_code == 200
        assert replay.json()["session"]["updatedAt"] == first.json()["session"]["updatedAt"]
        with store.connect() as conn:
            assert conn.execute(
                "SELECT state FROM assessment_leases WHERE lease_id = ?", (lease_id,)
            ).fetchone()["state"] == "abandoned"
            assert conn.execute(
                "SELECT COUNT(*) FROM learner_events WHERE lease_id = ? "
                "AND event_type = 'item_abandoned'",
                (lease_id,),
            ).fetchone()[0] == 1
