"""Clinical ECG identity stays behind owner/session-scoped capabilities."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient

from app import main as main_module
from app.clinical import integrity
from app.ecg_capability import (
    is_ecg_capability,
    issue_ecg_capability,
    matches_ecg_capability,
)
from app.main import app, clinical_item_store, store


def _register(client: TestClient, prefix: str) -> str:
    response = client.post(
        "/auth/register",
        json={
            "username": f"{prefix}_{uuid.uuid4().hex[:10]}",
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


def _assert_public(value: Any, *internal_values: str) -> None:
    assert not (
        _keys(value)
        & {
            "ecg_id",
            "ecgId",
            "prior_ecg_id",
            "priorEcgId",
            "servedEcgs",
            "case_id",
            "display_id",
            "sourcePath",
            "source_path",
            "recordPath",
            "record_path",
            "waveformPath",
            "waveform_path",
            "filePath",
            "file_path",
            "path",
        }
    )
    public_strings = _strings(value)
    for internal in internal_values:
        if internal:
            assert internal not in public_strings


def _commit_any_public_item(
    client: TestClient,
    session_id: str,
    item_id: str,
    revealed_item: dict[str, Any],
) -> dict[str, Any]:
    current = revealed_item
    while current.get("stepwise_state", {}).get("active"):
        active = current["stepwise_state"]["active"]
        committed = client.post(
            f"/clinical/shift/{session_id}/step",
            json={
                "itemId": item_id,
                "stepIndex": active["stepIndex"],
                "answerIndex": 0,
            },
        )
        assert committed.status_code == 200, committed.text
        current = committed.json()["item"]

    answer: dict[str, Any] = {"confidence": 3}
    if current.get("options"):
        answer["selectedOptionId"] = current["options"][0]["id"]
    if current.get("machine_read"):
        answer["machineLineId"] = current["machine_read"][0]["id"]
    if current.get("fill_in_task"):
        answer["fillInValue"] = current["fill_in_task"]["min_value"]
    matching = current.get("matching_task") or {}
    if matching.get("rows") and matching.get("choices"):
        answer["matches"] = {
            row["id"]: choice["id"]
            for row, choice in zip(matching["rows"], matching["choices"])
        }
    if current.get("clickable_leads"):
        answer["click"] = {
            "lead": current["clickable_leads"][0],
            "timeSec": 1.0,
            "amplitudeMv": 0.0,
        }
    graded = client.post(
        f"/clinical/shift/{session_id}/answer",
        json={"itemId": item_id, "answer": answer},
    )
    assert graded.status_code == 200, graded.text
    return graded.json()


def test_ecg_capability_has_no_payload_and_is_bound_to_every_scope() -> None:
    secret = "test-secret-with-enough-entropy-for-capabilities"
    canonical = "mimic/path/p10000032/s40689238"
    reference = issue_ecg_capability(
        secret, "owner-a", "clinical", "session-a", canonical
    )

    assert is_ecg_capability(reference)
    assert canonical not in reference
    assert matches_ecg_capability(
        reference, secret, "owner-a", "clinical", "session-a", canonical
    )
    assert not matches_ecg_capability(
        reference, secret, "owner-b", "clinical", "session-a", canonical
    )
    assert not matches_ecg_capability(
        reference, secret, "owner-a", "rapid", "session-a", canonical
    )
    assert not matches_ecg_capability(
        reference, secret, "owner-a", "clinical", "session-b", canonical
    )
    assert not matches_ecg_capability(
        reference, secret, "owner-a", "clinical", "session-a", "other-ecg"
    )
    assert not matches_ecg_capability(
        canonical, secret, "owner-a", "clinical", "session-a", canonical
    )


def test_clinical_lifecycle_waveform_feedback_and_report_never_expose_raw_ids() -> None:
    with TestClient(app) as owner, TestClient(app) as other:
        _register(owner, "clinical_cap_owner")
        _register(other, "clinical_cap_other")
        started_response = owner.post(
            "/clinical/shift/start",
            json={
                "lane": "clinic",
                "tier": "learn",
                "length": 1,
                "focus": "normal_ecg",
            },
        )
        assert started_response.status_code == 200, started_response.text
        started = started_response.json()
        session_id = started["session"]["sessionId"]
        item_id = started["next"]["itemId"]
        item = clinical_item_store.get_item(item_id)
        assert item is not None
        canonical = str(item.ecg_id)
        internal_item_id = str(item.item_id)
        ecg_ref = started["next"]["item"]["ecg_ref"]

        assert is_ecg_capability(ecg_ref)
        assert started["session"]["servedEcgRefs"] == []
        assert "ecg_id" not in started["next"]["item"]
        assert started["next"]["item"]["prior_ecg_ref"] is None
        _assert_public(started, canonical, internal_item_id)

        refreshed = owner.get("/clinical/shift/active")
        assert refreshed.status_code == 200, refreshed.text
        assert refreshed.json()["current"]["item"]["ecg_ref"] == ecg_ref
        _assert_public(refreshed.json(), canonical, internal_item_id)

        waveform = owner.get(
            f"/clinical/shift/{session_id}/waveform/{ecg_ref}",
            params={"leads": "II,V1", "maxPoints": 200},
        )
        assert waveform.status_code == 200, waveform.text
        assert waveform.json()["caseId"] == ecg_ref
        assert waveform.json()["ecgRef"] == ecg_ref
        assert waveform.headers["cache-control"] == "private, no-store"
        _assert_public(waveform.json(), canonical, internal_item_id)
        for invalid_leads in (
            ",".join(["II"] * 13),
            "II,,V1",
            "lead-name-too-long",
        ):
            invalid = owner.get(
                f"/clinical/shift/{session_id}/waveform/{ecg_ref}",
                params={"leads": invalid_leads},
            )
            assert invalid.status_code == 422
            assert canonical not in _strings(invalid.json())

        tampered = f"{ecg_ref[:-1]}{'A' if ecg_ref[-1] != 'A' else 'B'}"
        tampered_response = owner.get(
            f"/clinical/shift/{session_id}/waveform/{tampered}"
        )
        foreign_response = other.get(
            f"/clinical/shift/{session_id}/waveform/{ecg_ref}"
        )
        raw_response = owner.get(
            f"/clinical/shift/{session_id}/waveform/{canonical}"
        )
        assert tampered_response.status_code == 404
        assert foreign_response.status_code == 404
        assert raw_response.status_code == 404
        assert tampered_response.json() == foreign_response.json() == raw_response.json()
        assert canonical not in _strings(raw_response.json())

        revealed_response = owner.post(
            f"/clinical/shift/{session_id}/context",
            json={
                "itemId": item_id,
                "answer": {
                    "firstLookFinding": "normal_or_no_dominant_abnormality",
                    "firstLookConfidence": 3,
                },
            },
        )
        assert revealed_response.status_code == 200, revealed_response.text
        revealed = revealed_response.json()
        assert revealed["item"]["ecg_ref"] == ecg_ref
        _assert_public(revealed, canonical, internal_item_id)

        graded = _commit_any_public_item(
            owner, session_id, item_id, revealed["item"]
        )
        assert graded["grade"]["caseId"] == item_id
        assert graded["tutorContext"]["itemId"] == item_id
        _assert_public(graded, canonical, internal_item_id)

        internal_answer = store.get_shift_answer(session_id, item_id)
        assert internal_answer is not None
        assert internal_answer["ecgId"] == canonical
        assert internal_answer["grade"]["caseId"] == internal_item_id

        feedback = owner.get("/clinical/shift/active")
        assert feedback.status_code == 200, feedback.text
        assert feedback.json()["state"] == "feedback"
        assert feedback.json()["current"]["item"]["ecg_ref"] == ecg_ref
        _assert_public(feedback.json(), canonical, internal_item_id)

        advanced = owner.post(f"/clinical/shift/{session_id}/next")
        assert advanced.status_code == 200, advanced.text
        _assert_public(advanced.json(), canonical, internal_item_id)
        lifecycle = owner.get("/clinical/shift/active")
        assert lifecycle.status_code == 200, lifecycle.text
        assert lifecycle.json()["state"] == "report"
        _assert_public(lifecycle.json(), canonical, internal_item_id)
        report = owner.get(f"/clinical/shift/{session_id}/report")
        assert report.status_code == 200, report.text
        _assert_public(report.json(), canonical, internal_item_id)


def test_legacy_raw_item_session_resumes_and_debriefs_with_public_refs(monkeypatch) -> None:
    with TestClient(app) as client:
        learner_id = _register(client, "clinical_cap_legacy")
        item = next(
            candidate
            for candidate in clinical_item_store.iter_items()
            if candidate.situation == "clinic" and candidate.question_type == "triage"
        )
        session_id = integrity.create_session(
            store,
            learner_id=learner_id,
            lane="clinic",
            tier="learn",
            length=1,
            focus_objective=None,
            focus_subskill=None,
        )
        claim = integrity.claim_pending_item(
            store,
            session_id=session_id,
            item_id=item.item_id,
            ecg_id=item.ecg_id,
        )
        assert claim["status"] == "claimed"

        resumed = client.get("/clinical/shift/active")
        assert resumed.status_code == 200, resumed.text
        payload = resumed.json()
        public_item_id = payload["current"]["itemId"]
        ecg_ref = payload["current"]["item"]["ecg_ref"]
        assert public_item_id != item.item_id
        assert payload["session"]["pendingItemId"] == public_item_id
        _assert_public(payload, item.ecg_id, item.item_id)

        waveform = client.get(
            f"/clinical/shift/{session_id}/waveform/{ecg_ref}"
        )
        assert waveform.status_code == 200, waveform.text
        assert waveform.json()["caseId"] == ecg_ref

        revealed = client.post(
            f"/clinical/shift/{session_id}/context",
            json={
                "itemId": public_item_id,
                "answer": {
                    "firstLookFinding": "normal_or_no_dominant_abnormality",
                    "firstLookConfidence": 3,
                },
            },
        )
        assert revealed.status_code == 200, revealed.text
        graded = _commit_any_public_item(
            client, session_id, public_item_id, revealed.json()["item"]
        )
        assert graded["tutorContext"]["itemId"] == public_item_id
        _assert_public(graded, item.ecg_id, item.item_id)
        internal_answer = store.get_shift_answer(session_id, item.item_id)
        assert internal_answer is not None
        assert internal_answer["ecgId"] == item.ecg_id

        def fake_converse(*args, **kwargs):
            return {
                "tutorMessage": "Legacy case debrief restored.",
                "feedback": "",
                "viewerActions": [],
                "objectiveUpdates": [],
                "misconceptions": [],
                "uncertaintyWarnings": [],
                "suggestedNextStep": "Continue.",
                "socraticQuestion": "What evidence was decisive?",
                "citedEvidence": [],
                "onLessonTopic": True,
            }

        monkeypatch.setattr(main_module.tutor_service, "converse", fake_converse)
        tutor = client.post(
            "/tutor/message",
            json={
                "mode": "practice",
                "caseId": ecg_ref,
                "lessonId": graded["tutorContext"]["contextId"],
                "message": "Explain my completed case.",
                "clinicalContext": graded["tutorContext"],
            },
        )
        assert tutor.status_code == 200, tutor.text
        thread = store.get_thread(tutor.json()["threadId"])
        assert thread is not None
        assert thread["caseId"] == ecg_ref
        assert thread["scopeKey"] == f"clinical:{session_id}"
