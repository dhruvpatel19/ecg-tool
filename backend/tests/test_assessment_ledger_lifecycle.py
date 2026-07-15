from __future__ import annotations

import uuid

import pytest

from app.assessment_ledger import IdempotencyConflictError, append_event, create_lease
from app.guest_progress import GuestProgressService
from app.storage import LearningStore


_NOW = "2026-07-13T12:00:00+00:00"
_LATER = "2026-07-13T13:00:00+00:00"


def _guest() -> str:
    return f"g_{uuid.uuid4().hex[:28]}"


def _seed_ledger(store: LearningStore, owner_id: str, suffix: str) -> None:
    store.ensure_profile(owner_id)
    with store.connect() as conn:
        create_lease(
            conn,
            lease_id=f"lease_{suffix}",
            owner_id=owner_id,
            mode="training",
            session_id=f"session_{suffix}",
            ecg_ids=[f"ecg_{suffix}"],
            created_at=_NOW,
            expires_at=_LATER,
        )
        append_event(
            conn,
            event_id=f"presented_{suffix}",
            owner_id=owner_id,
            mode="training",
            session_id=f"session_{suffix}",
            lease_id=f"lease_{suffix}",
            ecg_id=f"ecg_{suffix}",
            event_type="item_presented",
            evidence_level="formative",
            integrity_status="atomic_v2",
            occurred_at=_NOW,
        )
        append_event(
            conn,
            event_id=f"interaction_{suffix}",
            owner_id=owner_id,
            mode="guided",
            session_id=f"guided_{suffix}",
            ecg_id=f"ecg_{suffix}",
            event_type="interaction_committed",
            evidence_level="guided",
            integrity_status="atomic_v2",
            score=0.8,
            competencies={"atrial_fibrillation:recognize": 0.8},
            occurred_at=_NOW,
        )


def test_learning_store_installs_normalized_assessment_schema(tmp_path) -> None:
    store = LearningStore(tmp_path / "assessment-schema.db")
    with store.connect() as conn:
        tables = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert {
            "assessment_leases",
            "assessment_lease_cases",
            "learner_events",
            "learner_event_competencies",
        }.issubset(tables)
        assert conn.execute("PRAGMA foreign_key_check").fetchone() is None


def _guided_event(event_key: str, *, scene_id: str = "scene-1") -> dict:
    return {
        "moduleId": "rhythm-ectopy",
        "sceneId": scene_id,
        "interactionId": "identify-af",
        "concept": "atrial_fibrillation",
        "subskills": ["recognize"],
        "score": 0.8,
        "correct": True,
        "attempts": 1,
        "assistance": "independent",
        "hintsUsed": 0,
        "confidence": 3,
        "evidenceLevel": "guided",
        "caseId": "ptb-guided-1",
        "caseProvenance": "real_eligible",
        "caseEligible": True,
        "misconceptions": [],
        "eventKey": event_key,
    }


def test_native_guided_commit_dual_writes_one_idempotent_normalized_event(tmp_path) -> None:
    store = LearningStore(tmp_path / "guided-event-ledger.db")
    owner_id = _guest()
    first = store.save_guided_learning_event(owner_id, _guided_event("guided-ledger-1"))
    replay = store.save_guided_learning_event(owner_id, _guided_event("guided-ledger-1"))
    assert first["replay"] is False
    assert replay["replay"] is True

    with store.connect() as conn:
        event = conn.execute(
            "SELECT mode, event_type, evidence_level, score FROM learner_events "
            "WHERE owner_id = ?",
            (owner_id,),
        ).fetchone()
        assert tuple(event) == ("guided", "interaction_committed", "guided", 0.8)
        competency = conn.execute(
            "SELECT competency_id, competency_score FROM learner_event_competencies"
        ).fetchone()
        assert tuple(competency) == ("atrial_fibrillation:recognize", 0.8)

    with pytest.raises(ValueError):
        store.save_guided_learning_event(
            owner_id,
            _guided_event("guided-ledger-invalid", scene_id="bad\nscene"),
        )
    with store.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM guided_learning_events WHERE event_key = ?",
            ("guided-ledger-invalid",),
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM learner_events WHERE owner_id = ?",
            (owner_id,),
        ).fetchone()[0] == 1


def test_native_guided_event_key_is_owner_scoped_and_payload_bound(tmp_path) -> None:
    store = LearningStore(tmp_path / "guided-owner-idempotency.db")
    first_owner = _guest()
    second_owner = _guest()
    shared_key = "same-authored-action"
    payload = _guided_event(shared_key)

    first = store.save_guided_learning_event(first_owner, payload)
    replay = store.save_guided_learning_event(first_owner, payload)
    second = store.save_guided_learning_event(second_owner, payload)

    assert first["replay"] is False
    assert replay["replay"] is True
    assert replay["eventId"] == first["eventId"]
    assert second["replay"] is False
    with pytest.raises(IdempotencyConflictError, match="different Guided evidence"):
        store.save_guided_learning_event(
            first_owner,
            {**payload, "score": 0.2, "correct": False},
        )

    with store.connect() as conn:
        events = conn.execute(
            "SELECT event_id, owner_id FROM learner_events "
            "WHERE owner_id IN (?, ?) ORDER BY owner_id",
            (first_owner, second_owner),
        ).fetchall()
        assert len(events) == 2
        assert {row["owner_id"] for row in events} == {first_owner, second_owner}
        assert len({row["event_id"] for row in events}) == 2
        assert all(str(row["event_id"]).startswith("guided:v2:") for row in events)
        for owner_id in (first_owner, second_owner):
            assert conn.execute(
                "SELECT attempts FROM subskill_mastery WHERE learner_id = ? "
                "AND concept = 'atrial_fibrillation' AND subskill = 'recognize'",
                (owner_id,),
            ).fetchone()[0] == 1


def test_pre_fingerprint_guided_event_still_replays_but_rejects_changed_evidence(
    tmp_path,
) -> None:
    store = LearningStore(tmp_path / "guided-legacy-replay.db")
    owner_id = _guest()
    payload = _guided_event("legacy-guided-action")
    first = store.save_guided_learning_event(owner_id, payload)
    with store.connect() as conn:
        conn.execute(
            "UPDATE guided_learning_events SET request_fingerprint = NULL "
            "WHERE learner_id = ? AND event_key = ?",
            (owner_id, payload["eventKey"]),
        )

    replay = store.save_guided_learning_event(owner_id, payload)
    assert replay["replay"] is True
    assert replay["eventId"] == first["eventId"]
    with pytest.raises(IdempotencyConflictError, match="different Guided evidence"):
        store.save_guided_learning_event(
            owner_id,
            {**payload, "interactionId": "different-checkpoint"},
        )

    with store.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM guided_learning_events WHERE learner_id = ?",
            (owner_id,),
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT attempts FROM subskill_mastery WHERE learner_id = ? "
            "AND concept = 'atrial_fibrillation' AND subskill = 'recognize'",
            (owner_id,),
        ).fetchone()[0] == 1


def test_guest_claim_export_and_account_deletion_cover_the_event_ledger(tmp_path) -> None:
    store = LearningStore(tmp_path / "assessment-lifecycle.db")
    claims = GuestProgressService(store)
    guest_id = _guest()
    user_id = f"u_{uuid.uuid4().hex}"
    password_hash = "stored-password-hash"
    store.create_user(user_id, f"learner_{uuid.uuid4().hex[:10]}", "Learner", password_hash)
    store.ensure_profile(user_id, "Learner")
    _seed_ledger(store, guest_id, "claim")

    summary = claims.claim(guest_id, user_id)
    assert summary["claimed"] is True
    assert summary["guestProgress"]["learnerEvents"] == 2

    with store.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM assessment_leases WHERE owner_id = ?", (user_id,)
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM learner_events WHERE owner_id = ?", (user_id,)
        ).fetchone()[0] == 2
        assert conn.execute("PRAGMA foreign_key_check").fetchone() is None

    exported = store.export_user_progress(user_id)
    assert exported is not None
    records = exported["records"]
    assert len(records["learnerEvents"]) == 2
    assert records["learnerEventCompetencies"] == [{
        "event_id": "interaction_claim",
        "competency_id": "atrial_fibrillation:recognize",
        "competency_score": 0.8,
    }]
    assert len(records["assessmentLeases"]) == 1
    assert "submission_key_hash" not in records["assessmentLeases"][0]
    assert records["assessmentLeaseCases"] == []

    assert store.delete_user_account(user_id, password_hash) is True
    with store.connect() as conn:
        for table in (
            "learner_event_competencies",
            "learner_events",
            "assessment_lease_cases",
            "assessment_leases",
        ):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        assert conn.execute("PRAGMA foreign_key_check").fetchone() is None


def test_explicit_guest_erasure_removes_ledger_children_before_parents(tmp_path) -> None:
    store = LearningStore(tmp_path / "assessment-guest-delete.db")
    guest_id = _guest()
    _seed_ledger(store, guest_id, "erase")

    deleted = store.delete_guest_learning_record(guest_id)
    assert deleted >= 5
    with store.connect() as conn:
        for table in (
            "learner_event_competencies",
            "learner_events",
            "assessment_lease_cases",
            "assessment_leases",
        ):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        assert conn.execute("PRAGMA foreign_key_check").fetchone() is None
