from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.assessment_contracts import rapid_tested_objective_manifest
from app.fixtures import build_fixture_cases
from app.ecg_capability import is_ecg_capability
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


def _multilabel_case() -> dict:
    case = _legacy_case()
    case.update({"case_id": "88002", "display_id": "PTB-XL 88002"})
    supported = [
        # Deliberately put incidental labels first. The assessment contract must
        # choose clinically prioritized targets rather than trusting storage
        # order or treating every co-label as lapse-eligible.
        "rate",
        "sinus_rhythm",
        "qt_interval",
        "myocardial_infarction",
        "anterior_mi",
        "st_elevation",
    ]
    case["supported_objectives"] = supported
    case["concept_confidence"] = {
        objective_id: {"tier": "A", "score": 0.9}
        for objective_id in supported
    }
    case["concept_confidence"]["right_axis_deviation"] = {
        "tier": "C",
        "score": 0.2,
    }
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


def _complete_sweep(selected: list[str], **overrides: str) -> dict:
    answer = {
        "framework": "clerkship",
        "rate": "75 bpm",
        "rhythm": "rhythm assessed from atrial and ventricular timing",
        "axis": "axis assessed from limb-lead QRS polarity",
        "intervals": "PR, QRS, and QT intervals assessed",
        "conduction": "QRS width and terminal morphology assessed",
        "st_t": "ST segments and T waves assessed",
        "hypertrophy": "chamber voltage and morphology assessed",
        "synthesis": "Evidence-limited complete ECG interpretation.",
        "selectedConcepts": selected,
    }
    answer.update(overrides)
    return answer


def _public_case_reference(pending: dict, canonical_id: str) -> str:
    reference = str(pending["current"]["case"]["caseId"])
    assert is_ecg_capability(reference)
    assert reference != canonical_id
    assert pending["round"]["pendingCaseId"] == reference
    assert pending["current"]["packet"]["case_id"] == reference
    return reference


def test_synthesis_manifest_cannot_be_enabled_by_a_caller_flag() -> None:
    case = _legacy_case()
    manifest = rapid_tested_objective_manifest(
        case,
        assessment_scope="full_read",
        focus_concept="normal_ecg",
        focus_subskill="synthesize",
        receipt_concept="integrated_interpretation",
        synthesis_allowed=True,
    )
    assert manifest["objectives"] == []
    assert manifest["allowSelectedExtras"] is False


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
    case_ref = _public_case_reference(pending, case["case_id"])
    # Selection targets remain server-owned until commitment; the learner
    # already chose the focus but cannot use this payload as a case label oracle.
    assert "targetObjectives" not in pending

    response = client.post(
        f"/rapid/rounds/{round_id}/submit",
        headers={"Authorization": "learner-a"},
        json={
            "caseId": case_ref,
            "structuredAnswer": _complete_sweep(
                ["supraventricular_tachycardia"],
                synthesis="Regular supraventricular tachycardia in a complete read.",
            ),
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
    case_ref = _public_case_reference(pending, case["case_id"])

    response = client.post(
        f"/rapid/rounds/{round_id}/submit",
        headers={"Authorization": "learner-a"},
        json={
            "caseId": case_ref,
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
    case_ref = _public_case_reference(pending, case["case_id"])
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
            "caseId": case_ref,
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
    lapse = next(row for row in body["receipts"] if row.get("correct") is False)
    assert lapse["concept"] == "normal_ecg"
    assert lapse["accepted"] is True
    assert "deadline" in lapse["reason"].lower()


def test_full_read_freezes_three_prioritized_targets_and_broad_miss_lapses_only_them(
    tmp_path,
) -> None:
    case = _multilabel_case()
    client, store = _client(tmp_path, [case])
    pending = _start_next(client, pace="ward")
    round_id = pending["round"]["roundId"]
    case_ref = _public_case_reference(pending, case["case_id"])

    # The contract exists durably before commitment but remains an answer key,
    # so neither the round metadata nor blinded current item may expose it.
    assert "pendingTestedObjectiveManifest" not in pending["round"]
    assert "testedObjectiveManifest" not in pending["current"]
    private_manifest = store.get_rapid_round(round_id)[
        "pendingTestedObjectiveManifest"
    ]
    required = [
        entry["objectiveId"] for entry in private_manifest["objectives"]
    ]
    assert private_manifest["taskKind"] == "full_read"
    assert required == ["myocardial_infarction", "anterior_mi", "st_elevation"]
    assert len(required) == 3

    response = client.post(
        f"/rapid/rounds/{round_id}/submit",
        headers={"Authorization": "learner-a"},
        json={
            "caseId": case_ref,
            "structuredAnswer": _complete_sweep(
                ["uncertain"],
                synthesis="No dominant abnormality identified after a complete read.",
            ),
            "freeTextAnswer": "No dominant abnormality identified.",
            "confidence": 4,
            "traceEvidence": {"mode": "point", "point": _point(case)},
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    public_manifest = body["answer"]["testedObjectiveManifest"]
    assert public_manifest["caseId"] == case_ref
    assert private_manifest["caseId"] == case["case_id"]
    assert {
        key: value for key, value in public_manifest.items() if key != "caseId"
    } == {
        key: value for key, value in private_manifest.items() if key != "caseId"
    }
    lapses = {
        row["concept"]
        for row in body["receipts"]
        if row.get("correct") is False and row["subskill"] == "recognize"
    }
    assert lapses == set(required)

    profile = store.get_profile("learner-a")
    recognition_rows = {
        row["concept"]: row
        for row in profile["subskillMastery"]
        if row["subskill"] == "recognize"
    }
    assert set(recognition_rows) == set(required)
    assert all(recognition_rows[concept]["lapses"] == 1 for concept in required)
    assert not ({"rate", "sinus_rhythm", "qt_interval"} & set(recognition_rows))


def test_timeout_lapses_only_frozen_required_manifest_targets(
    tmp_path,
) -> None:
    case = _multilabel_case()
    client, store = _client(tmp_path, [case])
    pending = _start_next(client, pace="ward")
    round_id = pending["round"]["roundId"]
    case_ref = _public_case_reference(pending, case["case_id"])
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
            "caseId": case_ref,
            "structuredAnswer": {
                "framework": "clerkship",
                "selectedConcepts": list(case["supported_objectives"]),
                "synthesis": "All packet-supported findings selected after timeout.",
            },
            "freeTextAnswer": "All packet-supported findings selected after timeout.",
            "confidence": 5,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    manifest = body["answer"]["testedObjectiveManifest"]
    required = {
        entry["objectiveId"] for entry in manifest["objectives"]
    }
    extras = {
        entry["objectiveId"]
        for entry in manifest["selectedSupportedExtras"]
    }
    assert required == {"myocardial_infarction", "anterior_mi", "st_elevation"}
    assert extras == set()
    lapses = {
        row["concept"]
        for row in body["receipts"]
        if row.get("correct") is False and row["subskill"] == "recognize"
    }
    assert lapses == required

    profile = store.get_profile("learner-a")
    recognition_rows = {
        row["concept"]: row
        for row in profile["subskillMastery"]
        if row["subskill"] == "recognize"
    }
    assert set(recognition_rows) == required
    assert not (extras & set(recognition_rows))


def test_emergency_overselection_blocks_target_success_and_incidental_receipts(
    tmp_path,
) -> None:
    case = _multilabel_case()
    client, store = _client(tmp_path, [case])
    pending = _start_next(client, pace="emergency")
    round_id = pending["round"]["roundId"]
    case_ref = _public_case_reference(pending, case["case_id"])
    response = client.post(
        f"/rapid/rounds/{round_id}/submit",
        headers={"Authorization": "learner-a"},
        json={
            "caseId": case_ref,
            "structuredAnswer": {
                "framework": "clerkship",
                "selectedConcepts": [
                    "myocardial_infarction",
                    "sinus_rhythm",
                    "right_axis_deviation",
                    "atrial_flutter",
                ],
                "synthesis": "MI with sinus rhythm and an unsupported axis overcall.",
            },
            "freeTextAnswer": "MI with sinus rhythm and right axis deviation.",
            "confidence": 5,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    manifest = body["answer"]["testedObjectiveManifest"]
    assert manifest["taskKind"] == "dominant_finding"
    assert [entry["objectiveId"] for entry in manifest["objectives"]] == [
        "myocardial_infarction"
    ]
    assert [
        entry["objectiveId"] for entry in manifest["selectedSupportedExtras"]
    ] == []
    assert body["answer"]["grade"]["overcalledObjectives"] == [
        "atrial_flutter",
        "right_axis_deviation",
    ]
    assert body["answer"]["grade"]["score"] < 1.0

    accepted = {
        row["concept"]
        for row in body["receipts"]
        if row.get("accepted") and row.get("correct", True)
        and row["subskill"] == "recognize"
    }
    assert accepted == set()
    overcall = next(
        row
        for row in body["receipts"]
        if row["concept"] == "right_axis_deviation"
    )
    assert overcall["accepted"] is False

    profile = store.get_profile("learner-a")
    recognition_rows = {
        row["concept"]: row
        for row in profile["subskillMastery"]
        if row["subskill"] == "recognize"
    }
    assert set(recognition_rows) == {"myocardial_infarction"}
    assert "right_axis_deviation" not in recognition_rows
    assert recognition_rows["myocardial_infarction"]["lapses"] == 1


def test_select_all_payload_is_rejected_before_grading(tmp_path) -> None:
    case = _multilabel_case()
    client, store = _client(tmp_path, [case])
    pending = _start_next(client, pace="emergency")
    round_id = pending["round"]["roundId"]
    case_ref = _public_case_reference(pending, case["case_id"])
    response = client.post(
        f"/rapid/rounds/{round_id}/submit",
        headers={"Authorization": "learner-a"},
        json={
            "caseId": case_ref,
            "structuredAnswer": {
                "framework": "clerkship",
                "selectedConcepts": [
                    "myocardial_infarction",
                    "anterior_mi",
                    "st_elevation",
                    "sinus_rhythm",
                    "rate",
                    "qt_interval",
                    "right_axis_deviation",
                    "left_axis_deviation",
                    "atrial_fibrillation",
                ],
            },
            "freeTextAnswer": "Select every offered finding.",
            "confidence": 5,
        },
    )
    assert response.status_code == 422, response.text
    assert store.get_profile("learner-a")["subskillMastery"] == []


def test_focused_handoff_persists_only_exact_target_and_rejects_incidental_success(
    tmp_path,
) -> None:
    case = _multilabel_case()
    client, store = _client(tmp_path, [case])
    pending = _start_next(client, pace="ward", focus="st_elevation")
    round_id = pending["round"]["roundId"]
    case_ref = _public_case_reference(pending, case["case_id"])
    response = client.post(
        f"/rapid/rounds/{round_id}/submit",
        headers={"Authorization": "learner-a"},
        json={
            "caseId": case_ref,
            "structuredAnswer": _complete_sweep(
                ["st_elevation", "myocardial_infarction"],
                synthesis="ST elevation with a related infarction label in the complete read.",
            ),
            "freeTextAnswer": "ST elevation with myocardial infarction.",
            "confidence": 4,
            "traceEvidence": {"mode": "point", "point": _point(case)},
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    manifest = body["answer"]["testedObjectiveManifest"]
    assert manifest["taskKind"] == "focused_handoff"
    assert manifest["allowSelectedExtras"] is False
    assert manifest["selectedSupportedExtras"] == []
    assert [
        (entry["objectiveId"], entry["subskill"])
        for entry in manifest["objectives"]
    ] == [("st_elevation", "recognize")]

    exact = next(
        row for row in body["receipts"] if row["concept"] == "st_elevation"
    )
    incidental = next(
        row
        for row in body["receipts"]
        if row["concept"] == "myocardial_infarction"
    )
    assert exact["accepted"] is True
    assert incidental["accepted"] is False
    assert "exact server-owned" in incidental["reason"]
    profile = store.get_profile("learner-a")
    recognition = {
        row["concept"]
        for row in profile["subskillMastery"]
        if row["subskill"] == "recognize"
    }
    assert recognition == {"st_elevation"}
