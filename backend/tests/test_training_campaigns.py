from __future__ import annotations

from copy import deepcopy

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.fixtures import build_fixture_cases
from app.storage import LearningStore
from app.subskill_tasks import build_subskill_task
from app.training_routes import _contrast_family, _public_campaign, build_training_router
from app.training_store import TrainingCampaignStore


class FakeRepo:
    def __init__(self, cases: list[dict]):
        self.cases = {case["case_id"]: case for case in cases}

    def candidates(self, concept_id: str | None = None) -> list[dict]:
        rows = []
        for case in self.cases.values():
            if concept_id and concept_id not in case["supported_objectives"]:
                continue
            rows.append(
                {
                    "case_id": case["case_id"],
                    "source": case["source"],
                    "teaching_tier": case["teaching_tier"],
                    "supported_objectives": case["supported_objectives"],
                }
            )
        return rows

    def get_case(self, case_id: str) -> dict | None:
        return self.cases.get(case_id)


def _cases() -> list[dict]:
    template = build_fixture_cases()[0]
    cases: list[dict] = []
    for index in range(8):
        case = deepcopy(template)
        case_id = str(7000 + index)
        target = index < 3
        supported = ["right_bundle_branch_block", "qrs_duration"] if target else (
            ["left_bundle_branch_block", "qrs_duration"] if index < 5 else ["normal_ecg", "sinus_rhythm"]
        )
        case.update(
            {
                "case_id": case_id,
                "display_id": f"PTB-XL {case_id}",
                "source": "ptbxl",
                "teaching_tier": "A",
                "supported_objectives": supported,
            }
        )
        case["concept_confidence"] = {
            concept: {"tier": "A", "score": 0.95, "evidence": [], "warnings": []}
            for concept in supported
        }
        # Ensure the localize pool has a reviewed V1 QRS target too.
        case["ptbxl_plus"]["fiducials"]["rois"].append(
            {
                "concept": "qrs_complex", "lead": "V1", "label": "QRS complex",
                "timeStartSec": 0.30, "timeEndSec": 0.44,
                "ampMinMv": -0.8, "ampMaxMv": 1.2,
            }
        )
        cases.append(case)
    synthetic = deepcopy(cases[0])
    synthetic.update({"case_id": "fixture-never", "source": "fixture"})
    cases.append(synthetic)
    return cases


def _client(tmp_path, cases: list[dict] | None = None):
    db = tmp_path / "campaign.sqlite3"
    learning = LearningStore(db)
    campaigns = TrainingCampaignStore(db)
    repo = FakeRepo(cases or _cases())
    app = FastAPI()
    app.include_router(
        build_training_router(
            repo,
            learning,
            campaigns,
            lambda case: case,
            lambda packet: {**packet, "blinded": True, "supported_objectives": []},
            lambda summary: {**summary, "report": "", "topConcepts": []},
            lambda authorization, requested, cookie: authorization or requested,
        )
    )
    return TestClient(app), learning, campaigns


def _reach_transfer(client, campaigns, *, learner: str, subskill: str):
    started = client.post(
        "/training/campaigns",
        headers={"Authorization": learner},
        json={
            "conceptId": "right_bundle_branch_block",
            "subskill": subskill,
            "length": 10,
            "contextKey": "receiptConcept=right_bundle_branch_block&returnTo=%2Freview",
        },
    ).json()
    campaign_id = started["campaign"]["campaignId"]
    current = started
    while current["current"]["slot"]["phase"] != "transfer":
        case_id = current["current"]["case"]["caseId"]
        private_slot = campaigns.get_slot_for_case(campaign_id, case_id)
        assert private_slot
        contract = build_subskill_task(
            case_id=case_id,
            case_concept="right_bundle_branch_block",
            subskill=subskill,
            case_focus=private_slot["caseFocus"],
            contrast_family=_contrast_family("right_bundle_branch_block"),
        )
        body = {
            "caseId": case_id,
            "selectedAnswer": "present" if private_slot["targetPresent"] else "absent",
            "confidence": 4,
            "subskillTaskAnswer": (contract.correct_answer or "") if contract else "",
        }
        submitted = client.post(
            f"/training/campaigns/{campaign_id}/submit",
            headers={"Authorization": learner},
            json=body,
        )
        assert submitted.status_code == 200, submitted.text
        current = client.post(
            f"/training/campaigns/{campaign_id}/next",
            headers={"Authorization": learner},
        ).json()
    return campaign_id, current


def test_pool_cap_unique_plan_pending_resume_and_never_synthetic(tmp_path):
    client, _, campaigns = _client(tmp_path)
    pool = client.get(
        "/training/campaigns/pool",
        params={"conceptId": "right_bundle_branch_block", "subskill": "recognize"},
    ).json()
    assert pool["eligibleDistinct"] == 8
    assert sum(pool["roleCounts"].values()) == pool["eligibleDistinct"]
    assert pool["roleCounts"]["target"] > 0
    assert pool["allowedLengths"] == [10, 25, 50, 100, 500, 1000, 5000]
    assert pool["source"] == "audited_waveform_only"
    unsupported = client.get(
        "/training/campaigns/pool",
        params={"conceptId": "right_bundle_branch_block", "subskill": "synthesize"},
    ).json()
    assert unsupported["eligibleDistinct"] == 0
    measure = client.get(
        "/training/campaigns/pool",
        params={"conceptId": "right_bundle_branch_block", "subskill": "measure"},
    ).json()
    assert measure["eligibleDistinct"] == 8
    assert measure["roleCounts"]["target"] == 3

    started = client.post(
        "/training/campaigns",
        headers={"Authorization": "learner-a"},
        json={
            "conceptId": "right_bundle_branch_block",
            "subskill": "recognize",
            "length": 25,
        },
    ).json()
    campaign = started["campaign"]
    assert campaign["requestedLength"] == 25
    assert campaign["length"] == 8
    assert campaign["poolCount"] == 8
    assert started["current"]["kind"] == "pending"
    assert started["current"]["packet"]["blinded"] is True
    assert "caseFocus" not in started["current"]["slot"]
    assert "targetPresent" not in started["current"]["slot"]

    slots = campaigns.all_slots(campaign["campaignId"])
    assert len(slots) == 8
    assert len({slot["caseId"] for slot in slots}) == 8
    assert all(not slot["caseId"].startswith("fixture") for slot in slots)
    immutable_plan = [(slot["phase"], slot["caseId"]) for slot in slots]

    resumed = client.get(
        "/training/campaigns/active", headers={"Authorization": "learner-a"}
    ).json()
    assert resumed["campaign"]["campaignId"] == campaign["campaignId"]
    assert resumed["current"]["case"]["caseId"] == started["current"]["case"]["caseId"]
    again = client.post(
        f"/training/campaigns/{campaign['campaignId']}/next",
        headers={"Authorization": "learner-a"},
    ).json()
    assert again["current"]["case"]["caseId"] == started["current"]["case"]["caseId"]
    assert [(slot["phase"], slot["caseId"]) for slot in campaigns.all_slots(campaign["campaignId"])] == immutable_plan


def test_public_campaign_metadata_does_not_repeat_the_5000_slot_phase_ledger():
    campaign = {
        "campaignId": "tc_scale",
        "length": 5000,
        "phases": ["target", "mimic", "negative", "transfer"] * 1250,
        "phaseCounts": {"target": 1250, "mimic": 1250, "negative": 1250, "transfer": 1250},
    }

    public = _public_campaign(campaign)

    assert "phases" not in public
    assert public["phaseCounts"] == campaign["phaseCounts"]
    assert len(campaign["phases"]) == 5000


def test_multisource_packet_contract_admits_only_exact_audited_training_lanes(tmp_path):
    leipzig = deepcopy(_cases()[0])
    leipzig.update(
        {
            "case_id": "leipzig-heart-center:x001@0000100-0002600",
            "display_id": "Leipzig x001 · 1.0s",
            "source": "leipzig-heart-center",
            "teaching_tier": "B",
            "supported_objectives": ["sinus_rhythm", "rate"],
            "signal_fingerprint": "a" * 64,
            "concept_confidence": {
                "sinus_rhythm": {"tier": "B", "score": 0.96, "evidence": [], "warnings": []},
                "rate": {"tier": "B", "score": 0.90, "evidence": [], "warnings": []},
            },
            "record_identity": {
                "sourceId": "leipzig-heart-center",
                "sourceRecordId": "x001@0000100-0002600",
                "patientId": "001",
                "sourceVersion": "1.0.0",
                "licenseId": "ODC-BY-1.0",
            },
            "source_provenance": {
                "sourceId": "leipzig-heart-center",
                "sourceVersion": "1.0.0",
                "licenseId": "ODC-BY-1.0",
                "labelAuthority": "expert beat and rhythm annotations",
                "patientId": "001",
            },
            "educational_eligibility": {
                "educationalUse": "rhythm_stream",
                "eligibleModes": ["training", "rapid"],
                "eligibleSubskills": {
                    "sinus_rhythm": ["recognize", "discriminate"],
                    "rate": ["measure"],
                    "qrs_complex": ["localize"],
                },
                "clinicalCaseEligible": False,
                "clinicalManagementEligible": False,
            },
        }
    )
    leipzig["ptbxl_plus"]["features"]["heart_rate"] = 75.0
    leipzig["ptbxl_plus"]["measurements"]["heart_rate"] = 75.0

    mimic_ext = deepcopy(leipzig)
    mimic_ext.update(
        {
            "case_id": "mimic-iv-ecg-ext:forbidden",
            "source": "mimic-iv-ecg-ext",
            "supported_objectives": ["right_bundle_branch_block"],
            "record_identity": {
                **mimic_ext["record_identity"],
                "sourceId": "mimic-iv-ecg-ext",
                "sourceRecordId": "forbidden",
                "licenseId": "PhysioNet-Credentialed-Health-Data-License-1.5.0",
            },
            "source_provenance": {
                **mimic_ext["source_provenance"],
                "sourceId": "mimic-iv-ecg-ext",
                "licenseId": "PhysioNet-Credentialed-Health-Data-License-1.5.0",
            },
            "educational_eligibility": {
                **mimic_ext["educational_eligibility"],
                "eligibleSubskills": {"right_bundle_branch_block": ["recognize"]},
            },
        }
    )

    mimic_waveform = deepcopy(leipzig)
    mimic_waveform.update(
        {
            "case_id": "mimic-iv-ecg:forbidden",
            "source": "mimic-iv-ecg",
            "supported_objectives": ["right_bundle_branch_block"],
            "concept_confidence": {
                "right_bundle_branch_block": {
                    "tier": "B",
                    "score": 0.96,
                    "evidence": [],
                    "warnings": [],
                }
            },
            "record_identity": {
                **mimic_waveform["record_identity"],
                "sourceId": "mimic-iv-ecg",
                "sourceRecordId": "forbidden",
                "sourceVersion": "1.0",
                "licenseId": "ODbL-1.0",
            },
            "source_provenance": {
                **mimic_waveform["source_provenance"],
                "sourceId": "mimic-iv-ecg",
                "sourceVersion": "1.0",
                "licenseId": "ODbL-1.0",
                "labelAuthority": "linked cardiologist reports when available",
            },
            "educational_eligibility": {
                **mimic_waveform["educational_eligibility"],
                "educationalUse": "static_12_lead",
                "eligibleModes": ["training", "rapid"],
                "eligibleSubskills": {"right_bundle_branch_block": ["recognize"]},
            },
        }
    )
    client, _, _ = _client(tmp_path, [leipzig, mimic_ext, mimic_waveform])

    def count(concept: str, subskill: str) -> int:
        return client.get(
            "/training/campaigns/pool", params={"conceptId": concept, "subskill": subskill}
        ).json()["eligibleDistinct"]

    assert count("sinus_rhythm", "recognize") == 1
    assert count("sinus_rhythm", "discriminate") == 1
    assert count("rate", "measure") == 1
    assert count("qrs_complex", "localize") == 1
    assert count("sinus_rhythm", "measure") == 0
    assert count("normal_ecg", "recognize") == 0
    assert count("qrs_duration", "localize") == 0
    assert count("right_bundle_branch_block", "recognize") == 0


def test_ownership_exactly_once_replay_summary_and_abandon(tmp_path):
    client, learning, campaigns = _client(tmp_path)
    started = client.post(
        "/training/campaigns",
        headers={"Authorization": "learner-a"},
        json={"conceptId": "right_bundle_branch_block", "subskill": "recognize", "length": 10},
    ).json()
    campaign_id = started["campaign"]["campaignId"]
    case_id = started["current"]["case"]["caseId"]

    assert client.get(
        f"/training/campaigns/{campaign_id}", headers={"Authorization": "learner-b"}
    ).status_code == 404
    conflict = client.post(
        "/training/campaigns",
        headers={"Authorization": "learner-a"},
        json={"conceptId": "right_bundle_branch_block", "subskill": "recognize", "length": 10},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "active_training_campaign"

    body = {
        "caseId": case_id,
        "selectedAnswer": "present",
        "confidence": 4,
        "hintsUsed": 0,
        "evidenceNote": "Wide QRS with compatible terminal morphology in V1.",
    }
    first = client.post(
        f"/training/campaigns/{campaign_id}/submit",
        headers={"Authorization": "learner-a"},
        json=body,
    )
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["replay"] is False
    assert first_body["answer"]["tutor"] is None
    assert first_body["campaign"]["position"] == 1
    assert first_body["summary"]["attempted"] == 1

    replay = client.post(
        f"/training/campaigns/{campaign_id}/submit",
        headers={"Authorization": "learner-a"},
        json={**body, "selectedAnswer": "absent", "confidence": 1},
    ).json()
    assert replay["replay"] is True
    assert replay["answer"]["answerId"] == first_body["answer"]["answerId"]
    assert replay["answer"]["response"] == first_body["answer"]["response"]

    with learning.connect() as conn:
        attempt_count = conn.execute(
            "SELECT COUNT(*) n FROM attempts WHERE learner_id = 'learner-a' AND mode = 'concept_practice'"
        ).fetchone()["n"]
        event_count = conn.execute(
            "SELECT COUNT(*) n FROM guided_learning_events WHERE learner_id = 'learner-a' AND module_id = 'train'"
        ).fetchone()["n"]
    assert attempt_count == 1
    assert event_count == 1
    assert len(campaigns.all_slots(campaign_id)) == 8

    abandoned = client.post(
        f"/training/campaigns/{campaign_id}/abandon",
        headers={"Authorization": "learner-a"},
    ).json()
    assert abandoned["campaign"]["status"] == "abandoned"
    assert client.get(
        "/training/campaigns/active", headers={"Authorization": "learner-a"}
    ).json()["campaign"] is None


def test_training_evidence_ceiling_keeps_recognition_formative(tmp_path):
    client, _, _ = _client(tmp_path)
    started = client.post(
        "/training/campaigns",
        headers={"Authorization": "learner-a"},
        json={"conceptId": "right_bundle_branch_block", "subskill": "recognize", "length": 10},
    ).json()
    response = client.post(
        f"/training/campaigns/{started['campaign']['campaignId']}/submit",
        headers={"Authorization": "learner-a"},
        json={
            "caseId": started["current"]["case"]["caseId"],
            "selectedAnswer": "present",
            "confidence": 5,
            "evidenceNote": "Wide QRS with a compatible V1/V6 pattern.",
        },
    ).json()
    assert response["answer"]["receipt"]["requestedEvidenceLevel"] == "guided"
    assert response["answer"]["receipt"]["effectiveEvidenceLevel"] == "guided"


def test_discrimination_transfer_uses_blinded_server_label_task_and_updates_exact_mastery(tmp_path):
    client, learning, campaigns = _client(tmp_path)
    campaign_id, pending = _reach_transfer(
        client, campaigns, learner="discriminator", subskill="discriminate"
    )
    assert pending["current"]["task"]["kind"] == "single_choice"
    assert "correctAnswer" not in pending["current"]["task"]
    assert "caseFocus" not in pending["current"]["slot"]
    case_id = pending["current"]["case"]["caseId"]
    slot = campaigns.get_slot_for_case(campaign_id, case_id)
    contract = build_subskill_task(
        case_id=case_id,
        case_concept="right_bundle_branch_block",
        subskill="discriminate",
        case_focus=slot["caseFocus"],
        contrast_family=_contrast_family("right_bundle_branch_block"),
    )
    response = client.post(
        f"/training/campaigns/{campaign_id}/submit",
        headers={"Authorization": "discriminator"},
        json={
            "caseId": case_id,
            "selectedAnswer": "present" if slot["targetPresent"] else "absent",
            "confidence": 4,
            "subskillTaskAnswer": contract.correct_answer,
            "receiptConcept": "right_bundle_branch_block",
        },
    )
    assert response.status_code == 200, response.text
    answer = response.json()["answer"]
    assert answer["receipt"]["effectiveEvidenceLevel"] == "independent_transfer"
    assert answer["grade"]["trainingEvidenceSource"] == "labeled_contrast_task"
    profile = learning.get_profile("discriminator")
    row = next(
        item for item in profile["subskillMastery"]
        if item["concept"] == "right_bundle_branch_block"
        and item["subskill"] == "discriminate"
    )
    assert row["independentAttempts"] == 1
    assert row["distinctSuccessfulEcgs"] == 1


def test_mechanism_transfer_requires_reviewed_choice_not_a_long_free_text_claim(tmp_path):
    client, learning, campaigns = _client(tmp_path)
    campaign_id, pending = _reach_transfer(
        client, campaigns, learner="mechanism", subskill="explain_mechanism"
    )
    case_id = pending["current"]["case"]["caseId"]
    slot = campaigns.get_slot_for_case(campaign_id, case_id)
    contract = build_subskill_task(
        case_id=case_id,
        case_concept="right_bundle_branch_block",
        subskill="explain_mechanism",
        case_focus=slot["caseFocus"],
        contrast_family=_contrast_family("right_bundle_branch_block"),
    )
    wrong = next(
        option["id"] for option in pending["current"]["task"]["options"]
        if option["id"] != contract.correct_answer
    )
    response = client.post(
        f"/training/campaigns/{campaign_id}/submit",
        headers={"Authorization": "mechanism"},
        json={
            "caseId": case_id,
            "selectedAnswer": "present" if slot["targetPresent"] else "absent",
            "confidence": 4,
            "evidenceNote": "This is a deliberately long but unsupported free text explanation that must not earn credit.",
            "subskillTaskAnswer": wrong,
            "receiptConcept": "right_bundle_branch_block",
        },
    )
    assert response.status_code == 200, response.text
    answer = response.json()["answer"]
    assert answer["receipt"]["effectiveEvidenceLevel"] == "independent_transfer"
    assert answer["summary"]["correct"] is False
    assert answer["grade"]["trainingEvidenceSource"] == "curated_mechanism_task"
    row = next(
        item for item in learning.get_profile("mechanism")["subskillMastery"]
        if item["concept"] == "right_bundle_branch_block"
        and item["subskill"] == "explain_mechanism"
    )
    assert row["independentAttempts"] == 1
    assert row["independentMastery"] < 0.15


def test_confidence_transfer_records_calibration_separately_from_recognition(tmp_path):
    client, learning, campaigns = _client(tmp_path)
    campaign_id, pending = _reach_transfer(
        client, campaigns, learner="calibrator", subskill="calibrate_confidence"
    )
    case_id = pending["current"]["case"]["caseId"]
    slot = campaigns.get_slot_for_case(campaign_id, case_id)
    # A deliberately low-confidence miss is a calibrated confidence outcome,
    # while the separate classificationCorrect flag remains false.
    response = client.post(
        f"/training/campaigns/{campaign_id}/submit",
        headers={"Authorization": "calibrator"},
        json={
            "caseId": case_id,
            "selectedAnswer": "absent" if slot["targetPresent"] else "present",
            "confidence": 1,
            "receiptConcept": "right_bundle_branch_block",
        },
    )
    assert response.status_code == 200, response.text
    answer = response.json()["answer"]
    assert answer["summary"]["classificationCorrect"] is False
    assert answer["summary"]["correct"] is True
    assert answer["grade"]["trainingSubskillTaskScore"] == 0.96
    assert answer["receipt"]["effectiveEvidenceLevel"] == "independent_transfer"
    row = next(
        item for item in learning.get_profile("calibrator")["subskillMastery"]
        if item["concept"] == "right_bundle_branch_block"
        and item["subskill"] == "calibrate_confidence"
    )
    assert row["independentAttempts"] == 1
    assert row["distinctSuccessfulEcgs"] == 1
