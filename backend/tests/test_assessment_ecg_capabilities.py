from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.ecg_capability import (
    is_ecg_capability,
    issue_ecg_capability,
    matches_ecg_capability,
)
from app.main import app, store, training_campaign_store


PASSWORD = "Sup3r-Secret-Pw!"
_SOURCE_ID_KEYS = {
    "patientId",
    "patient_id",
    "subjectId",
    "subject_id",
    "recordId",
    "record_id",
    "sourceRecordId",
    "source_record_id",
    "parentRecordId",
    "parent_record_id",
    "filename",
    "filename_lr",
    "filename_hr",
    "path",
    "record_path",
    "file_path",
    "data_path",
    "uri",
    "gcs_uri",
    "source_uri",
    "record_identity",
    "source_provenance",
}
_ECG_ID_KEYS = {
    "caseId",
    "case_id",
    "ecgId",
    "ecg_id",
    "pendingCaseId",
    "feedbackCaseId",
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


def _assert_public_identity_boundary(
    value: object, *, reference: str, canonical_id: str
) -> None:
    """Every ECG identity is opaque and every source lookup coordinate is gone."""

    if isinstance(value, list):
        for item in value:
            _assert_public_identity_boundary(
                item, reference=reference, canonical_id=canonical_id
            )
        return
    if not isinstance(value, dict):
        return
    for key, item in value.items():
        assert key not in _SOURCE_ID_KEYS
        if key in _ECG_ID_KEYS and item is not None:
            assert item != canonical_id
            assert is_ecg_capability(item)
        _assert_public_identity_boundary(
            item, reference=reference, canonical_id=canonical_id
        )


def test_capability_is_payload_free_stable_and_exactly_scoped() -> None:
    secret = "test-capability-secret-with-at-least-32-bytes"
    reference = issue_ecg_capability(
        secret, "learner-a", "training", "campaign-a", "ptbxl:12345"
    )

    assert is_ecg_capability(reference)
    assert len(reference) == 46
    assert "12345" not in reference
    assert reference == issue_ecg_capability(
        secret, "learner-a", "training", "campaign-a", "ptbxl:12345"
    )
    assert matches_ecg_capability(
        reference, secret, "learner-a", "training", "campaign-a", "ptbxl:12345"
    )
    for owner, mode, session, canonical in (
        ("learner-b", "training", "campaign-a", "ptbxl:12345"),
        ("learner-a", "rapid", "campaign-a", "ptbxl:12345"),
        ("learner-a", "training", "campaign-b", "ptbxl:12345"),
        ("learner-a", "training", "campaign-a", "ptbxl:12346"),
    ):
        assert not matches_ecg_capability(
            reference, secret, owner, mode, session, canonical
        )


def test_training_capability_covers_resume_submit_feedback_and_waveform() -> None:
    with TestClient(app) as owner, TestClient(app) as other:
        _register(owner, "training_cap_owner")
        _register(other, "training_cap_other")
        started = owner.post(
            "/training/campaigns",
            json={
                "conceptId": "normal_ecg",
                "subskill": "recognize",
                "length": 10,
            },
        )
        assert started.status_code == 200, started.text
        payload = started.json()
        campaign_id = payload["campaign"]["campaignId"]
        reference = payload["current"]["case"]["caseId"]
        internal = training_campaign_store.get_campaign(campaign_id)
        canonical_id = str(internal["pendingCaseId"])

        assert is_ecg_capability(reference)
        assert payload["campaign"]["pendingCaseId"] == reference
        assert payload["current"]["slot"]["caseId"] == reference
        assert payload["current"]["packet"]["case_id"] == reference
        _assert_public_identity_boundary(
            payload, reference=reference, canonical_id=canonical_id
        )

        resumed = owner.get(f"/training/campaigns/{campaign_id}")
        assert resumed.status_code == 200
        assert resumed.json()["current"]["case"]["caseId"] == reference

        waveform = owner.get(
            f"/training/campaigns/{campaign_id}/waveform/{reference}",
            params={"leads": "II", "maxPoints": 100},
        )
        assert waveform.status_code == 200, waveform.text
        assert waveform.json()["caseId"] == reference
        assert waveform.headers["cache-control"] == "private, no-store"
        assert waveform.headers["pragma"] == "no-cache"
        assert waveform.headers["vary"] == "Authorization, Cookie"
        assert other.get(
            f"/training/campaigns/{campaign_id}/waveform/{reference}"
        ).status_code == 404
        tampered = reference[:-1] + ("A" if reference[-1] != "A" else "B")
        assert owner.get(
            f"/training/campaigns/{campaign_id}/waveform/{tampered}"
        ).status_code == 404

        raw_submit = owner.post(
            f"/training/campaigns/{campaign_id}/submit",
            json={"caseId": canonical_id, "selectedAnswer": "present"},
        )
        assert raw_submit.status_code == 409
        assert raw_submit.json()["detail"]["pendingCaseId"] == reference

        submitted = owner.post(
            f"/training/campaigns/{campaign_id}/submit",
            json={"caseId": reference, "selectedAnswer": "present"},
        )
        assert submitted.status_code == 200, submitted.text
        feedback = submitted.json()
        assert feedback["campaign"]["feedbackCaseId"] == reference
        assert feedback["answer"]["caseId"] == reference
        _assert_public_identity_boundary(
            feedback, reference=reference, canonical_id=canonical_id
        )


def test_rapid_capability_covers_resume_results_submit_and_waveform() -> None:
    with TestClient(app) as owner, TestClient(app) as other:
        _register(owner, "rapid_cap_owner")
        _register(other, "rapid_cap_other")
        started = owner.post(
            "/rapid/rounds",
            json={"pace": "emergency", "length": 1, "exclusions": []},
        )
        assert started.status_code == 200, started.text
        round_id = started.json()["round"]["roundId"]
        pending = owner.post(f"/rapid/rounds/{round_id}/next", json={})
        assert pending.status_code == 200, pending.text
        payload = pending.json()
        reference = payload["current"]["case"]["caseId"]
        internal = store.get_rapid_round(round_id)
        canonical_id = str(internal["pendingCaseId"])

        assert is_ecg_capability(reference)
        assert payload["round"]["pendingCaseId"] == reference
        assert "exclusions" not in payload["round"]
        _assert_public_identity_boundary(
            payload, reference=reference, canonical_id=canonical_id
        )

        resumed = owner.get(f"/rapid/rounds/{round_id}")
        assert resumed.status_code == 200
        assert resumed.json()["current"]["case"]["caseId"] == reference

        waveform = owner.get(
            f"/rapid/rounds/{round_id}/waveform/{reference}",
            params={"leads": "II", "maxPoints": 100},
        )
        assert waveform.status_code == 200, waveform.text
        assert waveform.json()["caseId"] == reference
        assert waveform.headers["cache-control"] == "private, no-store"
        assert waveform.headers["pragma"] == "no-cache"
        assert waveform.headers["vary"] == "Authorization, Cookie"
        assert other.get(
            f"/rapid/rounds/{round_id}/waveform/{reference}"
        ).status_code == 404

        owner.post(f"/rapid/rounds/{round_id}/next", json={"activate": True})
        raw_submit = owner.post(
            f"/rapid/rounds/{round_id}/submit", json={"caseId": canonical_id}
        )
        assert raw_submit.status_code == 409
        assert raw_submit.json()["detail"]["pendingCaseId"] == reference

        submitted = owner.post(
            f"/rapid/rounds/{round_id}/submit",
            json={"caseId": reference, "confidence": 3},
        )
        assert submitted.status_code == 200, submitted.text
        feedback = submitted.json()
        assert feedback["round"]["feedbackCaseId"] == reference
        assert feedback["answer"]["caseId"] == reference
        assert feedback["results"][0]["caseId"] == reference
        _assert_public_identity_boundary(
            feedback, reference=reference, canonical_id=canonical_id
        )

        ledger = owner.get(f"/rapid/rounds/{round_id}/results")
        assert ledger.status_code == 200
        assert ledger.json()["results"][0]["caseId"] == reference
        _assert_public_identity_boundary(
            ledger.json(), reference=reference, canonical_id=canonical_id
        )
