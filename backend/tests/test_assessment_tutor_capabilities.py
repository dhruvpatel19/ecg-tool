"""Post-commit Training/Rapid tutor grounding uses scoped ECG capabilities."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient

from app import main as main_module
from app.ecg_capability import is_ecg_capability
from app.main import app, store, training_campaign_store


def _register(client: TestClient, prefix: str) -> str:
    response = client.post(
        "/auth/register",
        json={
            "username": f"{prefix[:18]}_{uuid.uuid4().hex[:10]}",
            "password": "test-password",
            "displayName": prefix,
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["user"]["userId"])


def _strings(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set().union(*(_strings(child) for child in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(_strings(child) for child in value)) if value else set()
    return {value} if isinstance(value, str) else set()


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        nested = set().union(*(_keys(child) for child in value.values())) if value else set()
        return set(value) | nested
    if isinstance(value, list):
        return set().union(*(_keys(child) for child in value)) if value else set()
    return set()


def _fake_converse(captured: dict[str, Any]):
    def converse(
        learner_message,
        case_packet,
        learner_profile,
        history,
        mode,
        lesson,
        viewer_state,
        **kwargs,
    ):
        captured.update(
            {
                "message": learner_message,
                "casePacket": case_packet,
                "profile": learner_profile,
                "history": history,
                "mode": mode,
                "lesson": lesson,
                "viewerState": viewer_state,
                "kwargs": kwargs,
            }
        )
        return {
            "tutorMessage": "Grounded committed assessment debrief.",
            "feedback": "",
            "viewerActions": [],
            "objectiveUpdates": [],
            "misconceptions": [],
            "uncertaintyWarnings": [],
            "suggestedNextStep": "Continue.",
            "socraticQuestion": "What evidence supported your interpretation?",
            "citedEvidence": [],
            "onLessonTopic": True,
        }

    return converse


def _assert_provider_packet(
    packet: dict[str, Any], *, reference: str, canonical_id: str
) -> None:
    assert packet["case_id"] == reference
    assert packet["display_id"].startswith("Assessment ECG ")
    assert canonical_id not in _strings(packet)
    assert not (
        _keys(packet)
        & {
            "path",
            "record_path",
            "file_path",
            "data_path",
            "gcs_uri",
            "source_uri",
            "patientId",
            "patient_id",
            "subjectId",
            "subject_id",
            "recordId",
            "record_id",
            "studyId",
            "study_id",
            "filename",
            "filename_lr",
            "filename_hr",
        }
    )


def _tutor(
    client: TestClient,
    *,
    case_reference: str,
    scope_key: str | None,
) -> Any:
    payload: dict[str, Any] = {
        "mode": "practice",
        "caseId": case_reference,
        "message": "Explain the ECG I just committed.",
    }
    if scope_key is not None:
        payload["scopeKey"] = scope_key
    return client.post("/tutor/message", json=payload)


def test_training_tutor_requires_exact_owner_campaign_capability(monkeypatch) -> None:
    with TestClient(app) as owner, TestClient(app) as other:
        learner_id = _register(owner, "training_tutor_cap_owner")
        _register(other, "training_tutor_cap_other")
        started = owner.post(
            "/training/campaigns",
            json={
                "conceptId": "normal_ecg",
                "subskill": "recognize",
                "length": 10,
            },
        )
        assert started.status_code == 200, started.text
        body = started.json()
        campaign_id = body["campaign"]["campaignId"]
        reference = body["current"]["case"]["caseId"]
        canonical_id = str(
            training_campaign_store.get_campaign(campaign_id)["pendingCaseId"]
        )
        scope_key = f"training:{campaign_id}"
        assert is_ecg_capability(reference)
        assert canonical_id != reference

        # A current presentation is still sealed even with its exact public
        # reference and session scope.
        assert _tutor(
            owner, case_reference=reference, scope_key=scope_key
        ).status_code in {404, 409}

        committed = owner.post(
            f"/training/campaigns/{campaign_id}/submit",
            json={
                "caseId": reference,
                "selectedAnswer": "present",
                "confidence": 3,
            },
        )
        assert committed.status_code == 200, committed.text
        assert committed.json()["current"]["kind"] == "feedback"
        assert (
            training_campaign_store.get_campaign(campaign_id)["feedbackCaseId"]
            == canonical_id
        )

        tampered = f"{reference[:-1]}{'A' if reference[-1] != 'A' else 'B'}"
        for client, candidate, scope in (
            (owner, reference, None),
            (owner, reference, "training:not-the-campaign"),
            (owner, reference, f"rapid:{campaign_id}"),
            (owner, tampered, scope_key),
            (other, reference, scope_key),
            (owner, canonical_id, scope_key),
        ):
            rejected = _tutor(
                client, case_reference=candidate, scope_key=scope
            )
            assert rejected.status_code == 404, rejected.text

        captured: dict[str, Any] = {}
        monkeypatch.setattr(
            main_module.tutor_service, "converse", _fake_converse(captured)
        )
        accepted = _tutor(
            owner, case_reference=reference, scope_key=scope_key
        )
        assert accepted.status_code == 200, accepted.text
        _assert_provider_packet(
            captured["casePacket"],
            reference=reference,
            canonical_id=canonical_id,
        )
        assert captured["profile"]["learnerId"] == learner_id
        thread = store.get_thread(accepted.json()["threadId"])
        assert thread is not None
        assert thread["caseId"] == reference
        assert thread["scopeKey"] == scope_key


def test_rapid_tutor_requires_exact_owner_round_capability(monkeypatch) -> None:
    with TestClient(app) as owner, TestClient(app) as other:
        learner_id = _register(owner, "rapid_tutor_cap_owner")
        _register(other, "rapid_tutor_cap_other")
        started = owner.post(
            "/rapid/rounds",
            json={
                "pace": "untimed",
                "length": 1,
                "focusConcept": "normal_ecg",
            },
        )
        assert started.status_code == 200, started.text
        round_id = started.json()["round"]["roundId"]
        pending = owner.post(f"/rapid/rounds/{round_id}/next", json={})
        assert pending.status_code == 200, pending.text
        reference = pending.json()["current"]["case"]["caseId"]
        canonical_id = str(store.get_rapid_round(round_id)["pendingCaseId"])
        scope_key = f"rapid:{round_id}"
        assert is_ecg_capability(reference)
        assert canonical_id != reference
        assert _tutor(
            owner, case_reference=reference, scope_key=scope_key
        ).status_code in {404, 409}

        committed = owner.post(
            f"/rapid/rounds/{round_id}/submit",
            json={
                "caseId": reference,
                "structuredAnswer": {
                    "framework": "clerkship",
                    "rate": "rate assessed",
                    "rhythm": "rhythm assessed",
                    "axis": "axis assessed",
                    "intervals": "intervals assessed",
                    "conduction": "conduction assessed",
                    "st_t": "ST-T assessed",
                    "hypertrophy": "voltage assessed",
                    "synthesis": "Committed evidence-limited interpretation.",
                    "selectedConcepts": ["normal_ecg"],
                },
                "freeTextAnswer": "Committed evidence-limited interpretation.",
                "confidence": 3,
                "traceEvidence": {
                    "mode": "point",
                    "point": {
                        "lead": "II",
                        "timeSec": 0.0,
                        "amplitudeMv": 9.0,
                    },
                },
            },
        )
        assert committed.status_code == 200, committed.text
        assert committed.json()["current"]["kind"] == "feedback"
        assert store.get_rapid_round(round_id)["feedbackCaseId"] == canonical_id

        tampered = f"{reference[:-1]}{'A' if reference[-1] != 'A' else 'B'}"
        for client, candidate, scope in (
            (owner, reference, None),
            (owner, reference, "rapid:not-the-round"),
            (owner, reference, f"training:{round_id}"),
            (owner, tampered, scope_key),
            (other, reference, scope_key),
            (owner, canonical_id, scope_key),
        ):
            rejected = _tutor(
                client, case_reference=candidate, scope_key=scope
            )
            assert rejected.status_code == 404, rejected.text

        captured: dict[str, Any] = {}
        monkeypatch.setattr(
            main_module.tutor_service, "converse", _fake_converse(captured)
        )
        accepted = _tutor(
            owner, case_reference=reference, scope_key=scope_key
        )
        assert accepted.status_code == 200, accepted.text
        _assert_provider_packet(
            captured["casePacket"],
            reference=reference,
            canonical_id=canonical_id,
        )
        assert captured["profile"]["learnerId"] == learner_id
        thread = store.get_thread(accepted.json()["threadId"])
        assert thread is not None
        assert thread["caseId"] == reference
        assert thread["scopeKey"] == scope_key
