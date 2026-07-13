from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.fixtures import build_fixture_cases
from app.ingest.leipzig import SURFACE_LEADS, WindowSpec, build_window_packet
from app.rapid_routes import _broad_corpus_selection, build_rapid_router
from app.source_policy import packet_allows_learning_evidence, packet_mode_policy
from app.storage import LearningStore


class FakeRepo:
    def __init__(self, cases: list[dict]):
        self.cases = {case["case_id"]: case for case in cases}

    def candidates(self, concept_id: str | None = None) -> list[dict]:
        return [
            {
                "case_id": case["case_id"],
                "source": case["source"],
                "teaching_tier": case["teaching_tier"],
                "supported_objectives": case.get("supported_objectives", []),
            }
            for case in self.cases.values()
            if not concept_id or concept_id in set(case.get("supported_objectives") or [])
        ]

    def get_case(self, case_id: str) -> dict | None:
        return self.cases.get(case_id)

    def concept_ab_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for case in self.cases.values():
            for concept in case.get("supported_objectives") or []:
                counts[concept] = counts.get(concept, 0) + 1
        return counts


def _legacy_case() -> dict:
    case = deepcopy(build_fixture_cases()[0])
    case.update({"case_id": "88001", "display_id": "PTB-XL 88001", "source": "ptbxl"})
    case["waveform"] = {**case["waveform"], "source": "corpus_store"}
    case["ptbxl_plus"]["fiducials"]["rois"] = [
        {
            "concept": "qrs_complex",
            "lead": "II",
            "label": "QRS complex",
            "timeStartSec": 0.42,
            "timeEndSec": 0.54,
            "ampMinMv": -0.8,
            "ampMaxMv": 1.2,
        }
    ]
    return case


def _leipzig_case() -> dict:
    spec = WindowSpec(
        record_name="x0010",
        patient_id="0010",
        sampling_frequency=1_000,
        start_sample=10_000,
        end_sample=20_000,
        episode_start_sample=9_500,
        episode_end_sample=20_500,
        raw_rhythm_aux="(AVNRT",
        rhythm_code="AVNRT",
        concept_id="supraventricular_tachycardia",
        beat_samples=tuple(range(10_300, 20_000, 350)),
    )
    signal = {
        lead: [((index % 31) - 15) / 100 for index in range(1_000)]
        for lead in SURFACE_LEADS
    }
    return build_window_packet(spec, signal)


def _point(packet: dict) -> dict:
    roi = next(
        row for row in packet["ptbxl_plus"]["fiducials"]["rois"]
        if row["lead"] == "II" and row["concept"] == "qrs_complex"
    )
    return {
        "lead": "II",
        "timeSec": (roi["timeStartSec"] + roi["timeEndSec"]) / 2,
        "amplitudeMv": (roi["ampMinMv"] + roi["ampMaxMv"]) / 2,
    }


def _client(tmp_path, cases: list[dict]):
    store = LearningStore(tmp_path / "rapid-policy.sqlite3")
    repo = FakeRepo(cases)
    app = FastAPI()
    app.include_router(
        build_rapid_router(
            repo,
            store,
            lambda case: case,
            lambda packet: {**packet, "blinded": True},
            lambda summary: {**summary, "report": "", "topConcepts": []},
            lambda authorization, requested, cookie: authorization or requested,
        )
    )
    return TestClient(app), store


def _start_next(client: TestClient, *, pace: str, focus: str | None = None) -> dict:
    started = client.post(
        "/rapid/rounds",
        headers={"Authorization": "learner-a"},
        json={"pace": pace, "length": 1, "focusConcept": focus, "exclusions": []},
    ).json()
    round_id = started["round"]["roundId"]
    pending = client.post(
        f"/rapid/rounds/{round_id}/next", headers={"Authorization": "learner-a"}, json={}
    )
    assert pending.status_code == 200, pending.text
    return pending.json()


def test_broad_selection_rejects_forged_and_research_only_new_sources() -> None:
    valid = _leipzig_case()
    forged = deepcopy(valid)
    forged["case_id"] = "leipzig-heart-center:forged"
    forged["record_identity"]["sourceRecordId"] = "forged"
    forged["educational_eligibility"]["eligibleModes"] = ["training"]

    research = deepcopy(valid)
    research.update({"case_id": "mimic-iv-ecg-ext:forged", "source": "mimic-iv-ecg-ext"})
    research["record_identity"].update(
        {
            "sourceId": "mimic-iv-ecg-ext",
            "sourceRecordId": "forged",
            "sourceVersion": "1.0.1",
            "licenseId": "PhysioNet-Credentialed-Health-Data-License-1.5.0",
        }
    )
    research["source_provenance"].update(
        {
            "sourceId": "mimic-iv-ecg-ext",
            "sourceVersion": "1.0.1",
            "licenseId": "PhysioNet-Credentialed-Health-Data-License-1.5.0",
            "labelAuthority": "encounter-linked ICD-10 labels; not ECG morphology ground truth",
        }
    )

    mimic_waveform = deepcopy(valid)
    mimic_waveform.update(
        {"case_id": "mimic-iv-ecg:forged", "source": "mimic-iv-ecg"}
    )
    mimic_waveform["record_identity"].update(
        {
            "sourceId": "mimic-iv-ecg",
            "sourceRecordId": "forged",
            "sourceVersion": "1.0",
            "licenseId": "ODbL-1.0",
        }
    )
    mimic_waveform["source_provenance"].update(
        {
            "sourceId": "mimic-iv-ecg",
            "sourceVersion": "1.0",
            "licenseId": "ODbL-1.0",
            "labelAuthority": "linked cardiologist reports when available",
        }
    )
    mimic_waveform["educational_eligibility"].update(
        {
            "educationalUse": "static_12_lead",
            "eligibleModes": ["training", "rapid"],
        }
    )

    assert packet_mode_policy(forged, "rapid").allowed is False
    assert packet_mode_policy(research, "rapid").allowed is False
    assert packet_mode_policy(mimic_waveform, "rapid").allowed is False
    assert packet_allows_learning_evidence(
        mimic_waveform,
        "rapid",
        "supraventricular_tachycardia",
        "recognize",
    ).allowed is False
    selection = _broad_corpus_selection(
        FakeRepo([forged, research, mimic_waveform]), set(), "forged-only"
    )
    assert selection["case"] is None


def test_leipzig_exact_rapid_recognition_contract_is_admitted(tmp_path) -> None:
    case = _leipzig_case()
    client, _ = _client(tmp_path, [case])
    assert _broad_corpus_selection(FakeRepo([case]), set(), "mixed") ["case"] is None
    pending = _start_next(client, pace="untimed", focus="supraventricular_tachycardia")
    round_id = pending["round"]["roundId"]
    assert pending["current"]["case"]["caseId"] == case["case_id"]
    assert pending["targetObjectives"] == ["supraventricular_tachycardia"]

    response = client.post(
        f"/rapid/rounds/{round_id}/submit",
        headers={"Authorization": "learner-a"},
        json={
            "caseId": case["case_id"],
            "structuredAnswer": {
                "framework": "clerkship",
                "selectedConcepts": ["supraventricular_tachycardia"],
                "synthesis": "Regular supraventricular tachycardia.",
            },
            "freeTextAnswer": "Regular supraventricular tachycardia.",
            "confidence": 4,
            "traceEvidence": {"mode": "point", "point": _point(case)},
        },
    )
    assert response.status_code == 200, response.text
    receipt = next(
        row for row in response.json()["receipts"]
        if row["concept"] == "supraventricular_tachycardia"
    )
    assert receipt["accepted"] is True
    assert receipt["evidenceLevel"] == "independent_transfer"
    assert response.json()["answer"]["grade"]["labelCompleteness"] == "target_only"
    assert response.json()["answer"]["grade"]["overcalledObjectives"] == []


@pytest.mark.parametrize("pace", ["ward", "untimed"])
def test_on_time_nonemergency_submission_requires_server_trace_proof(tmp_path, pace: str) -> None:
    case = _legacy_case()
    client, store = _client(tmp_path, [case])
    pending = _start_next(client, pace=pace, focus="normal_ecg")
    round_id = pending["round"]["roundId"]

    response = client.post(
        f"/rapid/rounds/{round_id}/submit",
        headers={"Authorization": "learner-a"},
        json={
            "caseId": case["case_id"],
            "structuredAnswer": {"framework": "clerkship", "selectedConcepts": ["normal_ecg"]},
            "freeTextAnswer": "Normal ECG.",
            "confidence": 4,
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "rapid_trace_proof_required"
    assert store.rapid_answer_count(round_id) == 0


def test_timed_out_answer_is_stored_but_never_earns_positive_receipt(tmp_path) -> None:
    case = _legacy_case()
    client, store = _client(tmp_path, [case])
    pending = _start_next(client, pace="ward", focus="normal_ecg")
    round_id = pending["round"]["roundId"]
    client.post(
        f"/rapid/rounds/{round_id}/next",
        headers={"Authorization": "learner-a"},
        json={"activate": True},
    )
    expired = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    with store.connect() as conn:
        conn.execute(
            "UPDATE rapid_rounds SET pending_deadline_at = ? WHERE round_id = ?",
            (expired, round_id),
        )

    response = client.post(
        f"/rapid/rounds/{round_id}/submit",
        headers={"Authorization": "learner-a"},
        json={
            "caseId": case["case_id"],
            "structuredAnswer": {"framework": "clerkship", "selectedConcepts": ["normal_ecg"]},
            "freeTextAnswer": "Normal ECG.",
            "confidence": 5,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answer"]["result"]["timedOut"] is True
    assert store.rapid_answer_count(round_id) == 1
    assert not any(row.get("accepted") and row.get("correct", True) for row in body["receipts"])
    rejected_success = next(
        row for row in body["receipts"]
        if row["concept"] == "normal_ecg" and row.get("correct") is not False
    )
    assert rejected_success["accepted"] is False
    lapse = next(row for row in body["receipts"] if row.get("correct") is False)
    assert lapse["concept"] == "normal_ecg"
    assert lapse["accepted"] is True
    assert "deadline" in lapse["reason"].lower()
