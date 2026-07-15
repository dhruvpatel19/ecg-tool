from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.ecg_capability import is_ecg_capability
from app.main import app, repo, store, tutor_service


PASSWORD = "Guided-capability-password!"
_IDENTITY_KEYS = {
    "caseId",
    "case_id",
    "ecgId",
    "ecg_id",
    "recordId",
    "record_id",
    "sourceRecordId",
    "source_record_id",
    "path",
    "filename",
    "filename_lr",
    "filename_hr",
    "uri",
    "gcs_uri",
}


def _register(client: TestClient, prefix: str) -> dict:
    response = client.post(
        "/auth/register",
        json={
            "username": f"{prefix}_{uuid.uuid4().hex[:10]}",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["user"]


def _guided_canonical(owner_id: str, lesson_id: str) -> str:
    with store.connect() as conn:
        row = conn.execute(
            "SELECT ecg_id FROM learner_events WHERE owner_id = ? "
            "AND mode = 'guided' AND session_id = ? "
            "AND event_type = 'item_presented' ORDER BY occurred_at DESC LIMIT 1",
            (owner_id, f"tutorial:{lesson_id}"),
        ).fetchone()
    assert row is not None
    return str(row[0])


def _event(case_ref: str, guided_context: str) -> dict:
    return {
        "eventKey": f"guided-cap-{uuid.uuid4().hex}",
        "moduleId": "leads-vectors",
        "sceneId": "guided-capability-test",
        "interactionId": "normal-recognition",
        "concept": "normal_ecg",
        "subskills": ["recognize"],
        "score": 1.0,
        "correct": True,
        "attempts": 1,
        "assistance": "independent",
        "caseId": case_ref,
        "guidedContext": guided_context,
        "caseProvenance": "real_eligible",
        "caseEligible": True,
    }


def _assert_no_canonical_identity(value: object, canonical_id: str) -> None:
    if isinstance(value, list):
        for item in value:
            _assert_no_canonical_identity(item, canonical_id)
        return
    if not isinstance(value, dict):
        return
    for key, item in value.items():
        if key in _IDENTITY_KEYS and item is not None:
            assert str(item) != canonical_id
        _assert_no_canonical_identity(item, canonical_id)


def test_guided_packet_waveform_grading_and_progress_use_only_owner_capabilities() -> None:
    with TestClient(app) as owner, TestClient(app) as other:
        owner_user = _register(owner, "guided_cap_owner")
        _register(other, "guided_cap_other")

        selected = owner.get(
            "/tutorials/orientation",
            params={
                "concept": "normal_ecg",
                "minimumTier": "A",
                "requiredLeads": "II",
                "requiredRois": "qrs_complex",
            },
        )
        assert selected.status_code == 200, selected.text
        body = selected.json()
        case_ref = body["recommendedCase"]["caseId"]
        guided_context = body["guidedContext"]
        canonical_id = _guided_canonical(owner_user["userId"], "orientation")

        assert is_ecg_capability(case_ref)
        assert is_ecg_capability(guided_context)
        assert case_ref != guided_context
        _assert_no_canonical_identity(body, canonical_id)
        assert body["recommendedPacket"]["case_id"] == case_ref
        assert body["recommendedPacket"]["display_id"] == "Guided teaching ECG"
        assert "ptbxl" not in body["recommendedPacket"]
        assert "supported_objectives" not in body["recommendedPacket"]
        assert "concept_confidence" not in body["recommendedPacket"]
        assert body["recommendedPacket"]["ptbxl_plus"]["features"] == {}
        assert body["recommendedPacket"]["ptbxl_plus"]["measurements"] == {}
        assert body["recommendedPacket"]["ptbxl_plus"]["fiducials"]["rois"] == []
        assert "targetObjectives" not in body["selection"]
        assert "exemplarRejections" not in body["selection"]
        assert body["assessmentPrivacy"] == {
            "opaqueEcgReference": True,
            "answerFieldsWithheldUntilCommit": True,
            "sourceRecordIdentityWithheld": True,
        }

        waveform = owner.get(
            f"/tutorials/orientation/waveform/{case_ref}",
            params={"leads": "II", "maxPoints": 100},
        )
        assert waveform.status_code == 200, waveform.text
        assert waveform.json()["caseId"] == case_ref
        assert waveform.headers["cache-control"] == "private, no-store"
        assert waveform.headers["pragma"] == "no-cache"
        assert waveform.headers["vary"] == "Authorization, Cookie"
        assert other.get(
            f"/tutorials/orientation/waveform/{case_ref}"
        ).status_code == 404
        assert owner.get(
            f"/tutorials/orientation/waveform/{canonical_id}"
        ).status_code == 404

        internal = repo.get_case(canonical_id)
        assert internal is not None
        qrs = next(
            roi
            for roi in internal["ptbxl_plus"]["fiducials"]["rois"]
            if roi["concept"] == "qrs_complex" and roi["lead"] == "II"
        )
        click = owner.post(
            f"/grade/click/{case_ref}",
            json={
                "lead": "II",
                "timeSec": (qrs["timeStartSec"] + qrs["timeEndSec"]) / 2,
                "amplitudeMv": 0.0,
                "concept": "qrs_complex",
                "guidedContext": guided_context,
            },
        )
        assert click.status_code == 200, click.text
        _assert_no_canonical_identity(click.json(), canonical_id)
        assert other.post(
            f"/grade/click/{case_ref}",
            json={
                "lead": "II",
                "timeSec": 1.0,
                "amplitudeMv": 0.0,
                "guidedContext": guided_context,
            },
        ).status_code == 403
        assert owner.post(
            f"/grade/click/{canonical_id}",
            json={
                "lead": "II",
                "timeSec": 1.0,
                "amplitudeMv": 0.0,
                "guidedContext": guided_context,
            },
        ).status_code == 403

        measurement_key = ""
        raw_measurement: float | int | None = None
        for key, value in internal["ptbxl_plus"]["measurements"].items():
            candidate = value
            if isinstance(value, dict):
                candidate = value.get("value", value.get("value_ms"))
            if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
                measurement_key = key
                raw_measurement = candidate
                break
        assert measurement_key and raw_measurement is not None
        measurement = owner.post(
            f"/grade/measurement/{case_ref}",
            json={
                "measurementKey": measurement_key,
                "value": raw_measurement,
                "tolerance": 1,
                "guidedContext": guided_context,
            },
        )
        assert measurement.status_code == 200, measurement.text
        assert measurement.json()["correct"] is True
        assert set(measurement.json()) == {"correct", "noTarget", "feedback"}

        saved = owner.post(
            "/learning-events/guided",
            json=_event(case_ref, guided_context),
        )
        assert saved.status_code == 200, saved.text
        with store.connect() as conn:
            stored = conn.execute(
                "SELECT case_id FROM guided_learning_events WHERE learner_id = ? "
                "ORDER BY id DESC LIMIT 1",
                (owner_user["userId"],),
            ).fetchone()
        assert stored is not None and str(stored[0]) == canonical_id
        assert case_ref not in str(stored[0])

        replacement = owner.get(
            "/tutorials/orientation",
            params={"concept": "normal_ecg", "excludeCaseId": case_ref},
        )
        assert replacement.status_code == 200, replacement.text
        assert replacement.json()["recommendedCase"]["caseId"] != case_ref
        assert _guided_canonical(owner_user["userId"], "orientation") != canonical_id


def test_guided_tutor_gets_blind_precommit_context_and_sanitized_postcommit_grounding(
    monkeypatch,
) -> None:
    captured_packets: list[dict] = []

    def fake_converse(
        message,
        case_packet,
        profile,
        history,
        mode,
        lesson,
        viewer_state,
        **kwargs,
    ):
        del message, profile, history, mode, lesson, viewer_state, kwargs
        captured_packets.append(case_packet)
        return {
            "tutorMessage": "Use the visible waveform evidence one step at a time.",
            "viewerActions": [],
            "socraticQuestion": "What do you see first?",
            "onLessonTopic": True,
            "citedEvidence": [],
            "uncertaintyWarnings": [],
            "suggestedNextStep": "Commit the current task.",
        }

    monkeypatch.setattr(tutor_service, "converse", fake_converse)
    with TestClient(app) as client:
        user = _register(client, "guided_tutor_cap")
        selected = client.get("/tutorials/orientation?concept=normal_ecg")
        assert selected.status_code == 200, selected.text
        body = selected.json()
        case_ref = body["recommendedCase"]["caseId"]
        canonical_id = _guided_canonical(user["userId"], "orientation")

        precommit = client.post(
            "/tutor/message",
            json={
                "mode": "tutorial",
                "lessonId": "orientation",
                "caseId": case_ref,
                "scopeKey": "guided-capability:precommit",
                "message": "Tell me the answer before I commit.",
            },
        )
        assert precommit.status_code == 200, precommit.text
        _assert_no_canonical_identity(precommit.json(), canonical_id)
        assert captured_packets[0]["case_id"] == case_ref
        assert captured_packets[0]["ptbxl_plus"]["measurements"] == {}
        assert captured_packets[0]["ptbxl_plus"]["fiducials"]["rois"] == []
        assert "supported_objectives" not in captured_packets[0]

        committed = client.post(
            "/learning-events/guided",
            json=_event(case_ref, body["guidedContext"]),
        )
        assert committed.status_code == 200, committed.text
        postcommit = client.post(
            "/tutor/message",
            json={
                "mode": "tutorial",
                "lessonId": "orientation",
                "caseId": case_ref,
                "scopeKey": "guided-capability:postcommit",
                "message": "Now help me review my committed answer.",
            },
        )
        assert postcommit.status_code == 200, postcommit.text
        _assert_no_canonical_identity(postcommit.json(), canonical_id)
        assert captured_packets[1]["case_id"] == case_ref
        assert captured_packets[1]["supported_objectives"]
        _assert_no_canonical_identity(captured_packets[1], canonical_id)
