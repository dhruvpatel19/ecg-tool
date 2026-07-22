from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import random
import sqlite3
import threading
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import app.training_routes as training_routes_module
import app.training_store as training_store_module
from app.assessment_ledger import create_lease, record_guided_packet_exposure
from app.fixtures import build_fixture_cases
from app.storage import LearningStore
from app.subskill_tasks import MECHANISM_EXPLANATIONS, build_subskill_task, grade_subskill_task
from app.training_routes import (
    TrainingPoolResolver,
    _build_plan,
    _contrast_family,
    _evidence_valid,
    _expected_answer,
    _public_campaign,
    _public_pending_slot,
    build_training_classification_contract,
    build_training_router,
)
from app.training_store import TrainingCampaignStore


SYSTEMATIC_INTERPRETATION = {
    "rate": "Ventricular rate approximately 72 bpm.",
    "rhythm": "Regular rhythm with one P wave before every QRS.",
    "axis": "Frontal QRS axis is within the normal quadrant.",
    "intervals": "P waves are consistent and the PR interval is measurable.",
    "conduction": "QRS duration and morphology were reviewed in all leads.",
    "st_t": "ST segments, T waves, QT, and QTc were reviewed.",
    "hypertrophy": "No chamber claim is made beyond reviewed ECG evidence.",
    "synthesis": "Complete evidence-bounded final ECG interpretation.",
}


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


class CountingExactRepo(FakeRepo):
    def __init__(self, cases: list[dict]):
        super().__init__(cases)
        self.exact_candidate_calls = 0
        self.full_candidate_calls = 0

    def candidates(self, concept_id: str | None = None) -> list[dict]:
        if concept_id is None:
            self.full_candidate_calls += 1
        else:
            self.exact_candidate_calls += 1
        return super().candidates(concept_id)


class CountingIndexedRepo:
    """Minimal indexed repository that makes full-pool scans observable."""

    def __init__(self, supported_objectives: list[str]):
        self.supported_objectives = supported_objectives
        self.training_candidate_calls = 0

    def training_candidates(self, **_filters) -> list[dict]:
        self.training_candidate_calls += 1
        return [
            {
                "case_id": "99001",
                "source": "ptbxl",
                "teaching_tier": "A",
                "supported_objectives": self.supported_objectives,
                "training_indexed": True,
            }
        ]

    def candidates(self, concept_id: str | None = None) -> list[dict]:
        raise AssertionError(f"indexed test repository fell back to candidates({concept_id!r})")

    def get_case(self, case_id: str) -> dict | None:
        return None


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


def _qt_cases() -> list[dict]:
    template = build_fixture_cases()[0]
    cases: list[dict] = []
    for index in range(8):
        case = deepcopy(template)
        case_id = str(7600 + index)
        qtc_ms = 500.0 if index < 4 else 440.0
        supported = ["qtc_prolongation", "qt_interval"]
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
            concept: {
                "tier": "A",
                "score": 0.95,
                "evidence": [],
                "warnings": [],
            }
            for concept in supported
        }
        case["ptbxl_plus"]["measurements"].update(
            {"qt_ms": 380.0, "qtc_ms": qtc_ms}
        )
        case["ptbxl_plus"]["fiducials"]["rois"].append(
            {
                "concept": "qt_segment",
                "lead": "II",
                "label": "QT interval",
                "timeStartSec": 0.50,
                "timeEndSec": 0.88,
                "ampMinMv": -0.5,
                "ampMaxMv": 1.0,
            }
        )
        cases.append(case)
    return cases


def _client(tmp_path, cases: list[dict] | None = None):
    db = tmp_path / "campaign.sqlite3"
    learning = LearningStore(db)
    campaigns = TrainingCampaignStore(db, learning.connect)
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


def _client_for_repo(tmp_path, repo):
    db = tmp_path / "indexed-campaign.sqlite3"
    learning = LearningStore(db)
    campaigns = TrainingCampaignStore(db, learning.connect)
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
    return TestClient(app)


def _role_pool(
    *, target: int, mimic: int, negative: int, prefix: str = "pool"
) -> list[dict]:
    rows: list[dict] = []
    for role, count in (("target", target), ("mimic", mimic), ("negative", negative)):
        for index in range(count):
            rows.append(
                {
                    "caseId": f"{prefix}-{role}-{index:05d}",
                    "caseFocus": (
                        "right_bundle_branch_block"
                        if role == "target"
                        else "left_bundle_branch_block"
                        if role == "mimic"
                        else "normal_ecg"
                    ),
                    "targetPresent": role == "target",
                    "role": role,
                }
            )
    return rows


def _seed_recent_independent_training_events(
    learning: LearningStore, learner_id: str, case_ids: list[str]
) -> None:
    with learning.connect() as conn:
        conn.executemany(
            """INSERT INTO guided_learning_events (
                learner_id, module_id, scene_id, interaction_id, concept,
                subskills_json, score, correct, attempts, assistance, hints_used,
                confidence, requested_evidence_level, effective_evidence_level,
                case_id, case_provenance, case_eligible, misconception_tags_json,
                event_key, receipt_json, registry_version, created_at
            ) VALUES (?, 'train', 'prior-campaign', ?, 'right_bundle_branch_block',
                      '["discriminate"]', 1.0, 1, 1, 'independent', 0, 4,
                      'independent_transfer', 'independent_transfer', ?,
                      'real_eligible', 1, '[]', ?, '[]', 'test-registry',
                      '2025-01-14T12:00:00+00:00')""",
            [
                (
                    learner_id,
                    f"prior:{case_id}",
                    case_id,
                    f"prior-independent:{learner_id}:{case_id}",
                )
                for case_id in case_ids
            ],
        )


def _training_atomic_snapshot(
    learning: LearningStore,
    campaign_id: str,
    learner_id: str,
    case_id: str,
) -> dict:
    """Read every durable ledger touched by one Training finalization."""

    with learning.connect() as conn:
        campaign = conn.execute(
            "SELECT position, pending_case_id, feedback_case_id, status, updated_at "
            "FROM training_campaigns WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()
        slots = conn.execute(
            "SELECT ordinal, phase, case_id, selection_reason, status, served_at, answered_at "
            "FROM training_campaign_slots WHERE campaign_id = ? ORDER BY ordinal",
            (campaign_id,),
        ).fetchall()
        mastery = conn.execute(
            "SELECT * FROM subskill_mastery WHERE learner_id = ? ORDER BY concept, subskill",
            (learner_id,),
        ).fetchall()
        profile = conn.execute(
            "SELECT display_name, created_at, updated_at FROM learner_profiles WHERE learner_id = ?",
            (learner_id,),
        ).fetchone()
        answers = conn.execute(
            "SELECT integrity_status FROM training_campaign_answers "
            "WHERE campaign_id = ? AND case_id = ? ORDER BY id",
            (campaign_id, case_id),
        ).fetchall()
        leases = conn.execute(
            "SELECT lease_id, state, integrity_status, submission_key_hash, "
            "claimed_at, terminal_at FROM assessment_leases "
            "WHERE owner_id = ? AND mode = 'training' AND session_id = ? "
            "ORDER BY created_at, lease_id",
            (learner_id, campaign_id),
        ).fetchall()
        ledger_events = conn.execute(
            "SELECT event_id, lease_id, ecg_id, event_type, evidence_level, "
            "integrity_status, score FROM learner_events "
            "WHERE owner_id = ? AND mode = 'training' AND session_id = ? "
            "ORDER BY occurred_at, event_id",
            (learner_id, campaign_id),
        ).fetchall()
        competency_rows = conn.execute(
            "SELECT competencies.event_id, competencies.competency_id, "
            "competencies.competency_score "
            "FROM learner_event_competencies AS competencies "
            "JOIN learner_events AS events ON events.event_id = competencies.event_id "
            "WHERE events.owner_id = ? AND events.mode = 'training' "
            "AND events.session_id = ? ORDER BY competencies.event_id, competencies.competency_id",
            (learner_id, campaign_id),
        ).fetchall()
        return {
            "campaign": tuple(campaign) if campaign else None,
            "slots": [tuple(row) for row in slots],
            "answers": [str(row["integrity_status"]) for row in answers],
            "leases": [tuple(row) for row in leases],
            "ledgerEvents": [tuple(row) for row in ledger_events],
            "competencyRows": [tuple(row) for row in competency_rows],
            "attempts": int(conn.execute(
                "SELECT COUNT(*) FROM attempts WHERE learner_id = ? AND case_id = ? "
                "AND mode = 'concept_practice'",
                (learner_id, case_id),
            ).fetchone()[0]),
            "events": int(conn.execute(
                "SELECT COUNT(*) FROM guided_learning_events WHERE learner_id = ? "
                "AND event_key LIKE ?",
                (learner_id, f"train:{campaign_id}:%:{case_id}:%"),
            ).fetchone()[0]),
            "retention": int(conn.execute(
                "SELECT COUNT(*) FROM subskill_retention_events WHERE learner_id = ? "
                "AND case_id = ? AND mode = 'train'",
                (learner_id, case_id),
            ).fetchone()[0]),
            "mastery": [tuple(row) for row in mastery],
            "profile": tuple(profile) if profile else None,
        }


def _pending_canonical(campaigns: TrainingCampaignStore, campaign_id: str) -> str:
    campaign = campaigns.get_campaign(campaign_id)
    assert campaign and campaign["pendingCaseId"]
    return str(campaign["pendingCaseId"])


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
    while True:
        case_ref = current["current"]["case"]["caseId"]
        case_id = _pending_canonical(campaigns, campaign_id)
        private_slot = campaigns.get_slot_for_case(campaign_id, case_id)
        assert private_slot
        if private_slot["phase"] == "transfer":
            assert "phase" not in current["current"]["slot"]
            break
        contract = build_subskill_task(
            case_id=case_id,
            case_concept="right_bundle_branch_block",
            subskill=subskill,
            case_focus=private_slot["caseFocus"],
            contrast_family=_contrast_family("right_bundle_branch_block"),
            variant=int(private_slot["position"]),
        )
        body = {
            "caseId": case_ref,
            "selectedAnswer": "present" if private_slot["targetPresent"] else "absent",
            "confidence": 4,
            "subskillTaskAnswer": (contract.correct_answer or "") if contract else "",
        }
        if subskill == "synthesize":
            body["structuredInterpretation"] = SYSTEMATIC_INTERPRETATION
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


def test_unknown_training_objective_is_rejected_before_indexed_pool_scan(tmp_path):
    repo = CountingIndexedRepo(["normal_ecg"])
    client = _client_for_repo(tmp_path, repo)

    pool = client.get(
        "/training/campaigns/pool",
        params={"conceptId": "client_invented_objective", "subskill": "recognize"},
    )
    assert pool.status_code == 422
    assert pool.json()["detail"]["code"] == "unknown_training_objective"

    start = client.post(
        "/training/campaigns",
        headers={"Authorization": "learner-a"},
        json={
            "conceptId": "client_invented_objective",
            "subskill": "recognize",
            "length": 10,
        },
    )
    assert start.status_code == 422
    assert start.json()["detail"]["code"] == "unknown_training_objective"

    oversized = client.get(
        "/training/campaigns/pool",
        params={"conceptId": "x" * 161, "subskill": "recognize"},
    )
    assert oversized.status_code == 422
    assert repo.training_candidate_calls == 0


def test_receipt_contract_rejects_unknown_disallowed_and_unrelated_claims(tmp_path):
    client, learning, campaigns = _client(tmp_path)
    invalid_starts = [
        (
            "receipt-unknown",
            "right_bundle_branch_block",
            "recognize",
            "not_a_registered_objective",
            "unknown_objective",
        ),
        (
            "receipt-disallowed",
            "sinus_rhythm",
            "measure",
            "rhythm_basics",
            "subskill_not_authored",
        ),
        (
            "receipt-unrelated",
            "right_bundle_branch_block",
            "recognize",
            "atrial_fibrillation",
            "case_concept_not_authored",
        ),
        (
            "receipt-qt-proxy-scope",
            "qtc_prolongation",
            "recognize",
            "qt_interval",
            "proxy_subskill_not_authored",
        ),
        (
            "receipt-qt-proxy-explanation",
            "qtc_prolongation",
            "explain_mechanism",
            "qt_interval",
            "proxy_subskill_not_authored",
        ),
    ]
    for learner, concept, subskill, receipt, reason in invalid_starts:
        response = client.post(
            "/training/campaigns",
            headers={"Authorization": learner},
            json={
                "conceptId": concept,
                "subskill": subskill,
                "length": 5,
                "contextKey": f"receiptConcept={receipt}",
            },
        )
        assert response.status_code == 422, response.text
        assert response.json()["detail"] == {
            "code": "training_receipt_contract_invalid",
            "message": (
                "This Focused Practice receipt target is not authored for the "
                "selected ECG concept and skill."
            ),
            "reason": reason,
        }

    with learning.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM learner_profiles WHERE learner_id LIKE 'receipt-%'"
        ).fetchone()[0] == 0

    duplicate = client.post(
        "/training/campaigns",
        headers={"Authorization": "receipt-duplicate"},
        json={
            "conceptId": "right_bundle_branch_block",
            "subskill": "recognize",
            "length": 5,
            "contextKey": (
                "receiptConcept=right_bundle_branch_block"
                "&receiptConcept=atrial_fibrillation"
            ),
        },
    )
    assert duplicate.status_code == 422, duplicate.text
    assert duplicate.json()["detail"]["reason"] == "duplicate_receipt_target"

    learner = "receipt-submit-tamper"
    started = client.post(
        "/training/campaigns",
        headers={"Authorization": learner},
        json={
            "conceptId": "right_bundle_branch_block",
            "subskill": "recognize",
            "length": 5,
            "contextKey": "receiptConcept=right_bundle_branch_block",
        },
    ).json()
    assert started["campaign"]["contextKey"] == (
        "receiptConcept=right_bundle_branch_block"
    )
    campaign_id = started["campaign"]["campaignId"]
    case_id = _pending_canonical(campaigns, campaign_id)
    slot = campaigns.get_slot_for_case(campaign_id, case_id)
    assert slot is not None
    with learning.connect() as conn:
        conn.execute(
            "UPDATE training_campaigns SET context_key = ? WHERE campaign_id = ?",
            ("receiptConcept=atrial_fibrillation", campaign_id),
        )

    rejected = client.post(
        f"/training/campaigns/{campaign_id}/submit",
        headers={"Authorization": learner},
        json={
            "caseId": started["current"]["case"]["caseId"],
            "selectedAnswer": "present" if slot["targetPresent"] else "absent",
            "receiptConcept": "atrial_fibrillation",
        },
    )
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["detail"]["reason"] == "case_concept_not_authored"
    with learning.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM training_campaign_answers WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM guided_learning_events WHERE learner_id = ?",
            (learner,),
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM subskill_mastery WHERE learner_id = ?",
            (learner,),
        ).fetchone()[0] == 0


def test_exact_target_eligibility_uses_the_same_trace_requirements_as_the_pool() -> None:
    cases = _cases()
    resolver = TrainingPoolResolver(FakeRepo(cases))

    assert resolver.has_exact_target("right_bundle_branch_block", "localize") is True
    assert resolver.exact_target_depth("right_bundle_branch_block", "localize") == 3
    assert resolver.has_durable_exact_target(
        "right_bundle_branch_block", "localize"
    ) is True
    assert resolver.eligible_pool("right_bundle_branch_block", "localize")

    sparse_cases = deepcopy(cases)
    for case in sparse_cases[1:]:
        case["ptbxl_plus"]["fiducials"]["rois"] = [
            roi
            for roi in case["ptbxl_plus"]["fiducials"]["rois"]
            if not (roi.get("concept") == "qrs_complex" and roi.get("lead") == "V1")
        ]
    sparse = TrainingPoolResolver(FakeRepo(sparse_cases))
    assert sparse.has_exact_target("right_bundle_branch_block", "localize") is True
    assert sparse.exact_target_depth("right_bundle_branch_block", "localize") == 1
    assert sparse.has_durable_exact_target(
        "right_bundle_branch_block", "localize"
    ) is False

    for case in cases:
        case["ptbxl_plus"]["fiducials"]["rois"] = [
            roi
            for roi in case["ptbxl_plus"]["fiducials"]["rois"]
            if not (roi.get("concept") == "qrs_complex" and roi.get("lead") == "V1")
        ]
    unavailable = TrainingPoolResolver(FakeRepo(cases))
    assert unavailable.has_exact_target("right_bundle_branch_block", "localize") is False
    assert unavailable.eligible_pool("right_bundle_branch_block", "localize") == []


def test_availability_matrix_uses_exact_depth_without_materializing_full_pools(tmp_path):
    repo = CountingExactRepo(_cases())
    client = _client_for_repo(tmp_path, repo)
    response = client.get(
        "/training/campaigns/availability",
        params={"conceptId": "right_bundle_branch_block"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["conceptId"] == "right_bundle_branch_block"
    assert payload["source"] == "exact_target_index"
    assert list(payload["subskills"]) == [
        "recognize",
        "localize",
        "measure",
        "discriminate",
        "explain_mechanism",
        "synthesize",
        "apply_in_context",
        "calibrate_confidence",
    ]
    assert payload["subskills"]["localize"] == {
        "available": True,
        "independentReceiptsAvailable": True,
    }
    assert payload["subskills"]["synthesize"] == {
        "available": True,
        "independentReceiptsAvailable": False,
    }
    assert repo.exact_candidate_calls == 8
    assert repo.full_candidate_calls == 0

    sparse_cases = _cases()
    for case in sparse_cases[1:]:
        case["ptbxl_plus"]["fiducials"]["rois"] = [
            roi
            for roi in case["ptbxl_plus"]["fiducials"]["rois"]
            if not (roi.get("concept") == "qrs_complex" and roi.get("lead") == "V1")
        ]
    sparse_client = _client_for_repo(tmp_path, CountingExactRepo(sparse_cases))
    sparse = sparse_client.get(
        "/training/campaigns/availability",
        params={"conceptId": "right_bundle_branch_block"},
    ).json()
    assert sparse["subskills"]["localize"] == {
        "available": True,
        "independentReceiptsAvailable": False,
    }


def test_training_pool_cache_is_bounded_and_lru(tmp_path, monkeypatch):
    concepts = ["normal_ecg", "sinus_rhythm", "right_bundle_branch_block"]
    repo = CountingIndexedRepo(concepts)
    monkeypatch.setattr(training_routes_module, "TRAINING_POOL_CACHE_MAX_ENTRIES", 2)
    client = _client_for_repo(tmp_path, repo)

    for concept in concepts:
        response = client.get(
            "/training/campaigns/pool",
            params={"conceptId": concept, "subskill": "recognize"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["eligibleDistinct"] == 1
    assert repo.training_candidate_calls == 3

    # The first key was evicted; rebuilding it is the fourth repository scan.
    rebuilt = client.get(
        "/training/campaigns/pool",
        params={"conceptId": concepts[0], "subskill": "recognize"},
    )
    assert rebuilt.status_code == 200
    assert repo.training_candidate_calls == 4

    # The most recently used pre-existing key remains cached.
    cached = client.get(
        "/training/campaigns/pool",
        params={"conceptId": concepts[2], "subskill": "recognize"},
    )
    assert cached.status_code == 200
    assert repo.training_candidate_calls == 4


def test_pool_cap_unique_plan_pending_resume_and_never_synthetic(tmp_path):
    client, _, campaigns = _client(tmp_path)
    pool = client.get(
        "/training/campaigns/pool",
        params={"conceptId": "right_bundle_branch_block", "subskill": "recognize"},
    ).json()
    assert pool["eligibleDistinct"] == 8
    assert sum(pool["roleCounts"].values()) == pool["eligibleDistinct"]
    assert pool["roleCounts"]["target"] > 0
    assert pool["allowedLengths"] == [5, 10, 20, 25, 50, 100, 500, 1000, 5000]
    assert pool["source"] == "audited_waveform_only"
    synthesis = client.get(
        "/training/campaigns/pool",
        params={"conceptId": "right_bundle_branch_block", "subskill": "synthesize"},
    ).json()
    assert synthesis["eligibleDistinct"] == 8
    assert synthesis["independentReceiptsAvailable"] is False
    application = client.get(
        "/training/campaigns/pool",
        params={"conceptId": "right_bundle_branch_block", "subskill": "apply_in_context"},
    ).json()
    assert application["eligibleDistinct"] == 8
    assert application["independentReceiptsAvailable"] is False
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
    assert {
        "caseFocus", "phase", "role", "selectionReason", "targetPresent",
    }.isdisjoint(started["current"]["slot"])

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


@pytest.mark.parametrize(
    ("requested_length", "expected_length"),
    [(5, 5), (20, 8)],
)
def test_learner_scale_campaign_lengths_are_accepted(
    tmp_path, requested_length, expected_length
):
    client, _, campaigns = _client(tmp_path)
    response = client.post(
        "/training/campaigns",
        headers={"Authorization": f"learner-length-{requested_length}"},
        json={
            "conceptId": "right_bundle_branch_block",
            "subskill": "recognize",
            "length": requested_length,
        },
    )

    assert response.status_code == 200, response.text
    campaign = response.json()["campaign"]
    assert campaign["requestedLength"] == requested_length
    assert campaign["length"] == expected_length
    slots = campaigns.all_slots(campaign["campaignId"])
    assert len(slots) == expected_length
    assert len({slot["caseId"] for slot in slots}) == expected_length


def test_pending_slot_hides_answer_bearing_metadata_until_feedback(tmp_path):
    private_projection = {
        "position": 0,
        "phase": "mimic",
        "role": "mimic",
        "caseId": "canonical-case-id",
        "caseFocus": "left_bundle_branch_block",
        "targetPresent": False,
        "selectionReason": "contrast_after_target_success",
        "status": "served",
    }
    assert _public_pending_slot(private_projection) == {
        "position": 0,
        "caseId": "canonical-case-id",
        "status": "served",
    }

    client, _, campaigns = _client(tmp_path)
    started = client.post(
        "/training/campaigns",
        headers={"Authorization": "pending-redaction"},
        json={
            "conceptId": "right_bundle_branch_block",
            "subskill": "recognize",
            "length": 5,
        },
    ).json()
    campaign_id = started["campaign"]["campaignId"]
    case_ref = started["current"]["case"]["caseId"]
    case_id = _pending_canonical(campaigns, campaign_id)
    private_slot = campaigns.get_slot_for_case(campaign_id, case_id)
    assert private_slot
    answer_bearing_keys = {
        "caseFocus", "phase", "role", "selectionReason", "targetPresent",
    }
    assert answer_bearing_keys.isdisjoint(started["current"]["slot"])

    submitted = client.post(
        f"/training/campaigns/{campaign_id}/submit",
        headers={"Authorization": "pending-redaction"},
        json={
            "caseId": case_ref,
            "selectedAnswer": (
                "present" if private_slot["targetPresent"] else "absent"
            ),
            "confidence": 4,
        },
    )

    assert submitted.status_code == 200, submitted.text
    feedback = submitted.json()["current"]
    assert feedback["kind"] == "feedback"
    assert feedback["slot"]["phase"] == private_slot["phase"]
    assert feedback["slot"]["caseFocus"] == private_slot["caseFocus"]
    assert feedback["slot"]["targetPresent"] == private_slot["targetPresent"]
    assert feedback["slot"]["selectionReason"] == private_slot["selectionReason"]


def test_public_campaign_metadata_does_not_expose_the_private_roster_recipe():
    campaign = {
        "campaignId": "tc_scale",
        "length": 5000,
        "phases": ["target", "mimic", "negative", "transfer"] * 1250,
        "phaseCounts": {"target": 1250, "mimic": 1250, "negative": 1250, "transfer": 1250},
        "rosterPolicy": {"plannedLength": 5000, "reusedByRole": {"target": 12}},
    }

    public = _public_campaign(campaign)

    assert {"phases", "phaseCounts", "rosterPolicy"}.isdisjoint(public)
    assert public == {"campaignId": "tc_scale", "length": 5000}
    assert len(campaign["phases"]) == 5000


def test_five_item_trace_plan_is_balanced_unpredictable_and_has_target_transfer():
    pool = _role_pool(target=8, mimic=8, negative=8, prefix="five-plan")
    first = _build_plan(
        pool,
        5,
        reserve_transfer_roles={"target"},
        rng=random.Random(17),
    )
    repeated = _build_plan(
        pool,
        5,
        reserve_transfer_roles={"target"},
        rng=random.Random(17),
    )
    alternate = _build_plan(
        pool,
        5,
        reserve_transfer_roles={"target"},
        rng=random.Random(29),
    )

    assert first == repeated
    assert [(row["caseId"], row["phase"]) for row in first] != [
        (row["caseId"], row["phase"]) for row in alternate
    ]
    assert len(first) == len({row["caseId"] for row in first}) == 5
    transfers = [row for row in first if row["phase"] == "transfer"]
    assert len(transfers) >= 1
    assert any(row["targetPresent"] and row["role"] == "target" for row in transfers)
    instructional = Counter(
        row["phase"] for row in first if row["phase"] != "transfer"
    )
    assert max(instructional.values()) - min(instructional.values()) <= 1
    for row in first:
        assert {
            "caseFocus", "phase", "role", "selectionReason", "targetPresent",
        }.isdisjoint(_public_pending_slot(row))


def test_legacy_duplicate_current_campaigns_are_repaired_before_unique_index(tmp_path):
    db = tmp_path / "legacy-training-duplicates.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.executescript(
            """
            CREATE TABLE training_campaigns (
                campaign_id TEXT PRIMARY KEY,
                learner_id TEXT NOT NULL,
                concept_id TEXT NOT NULL,
                subskill TEXT NOT NULL,
                requested_length INTEGER NOT NULL,
                length INTEGER NOT NULL,
                pool_count INTEGER NOT NULL,
                phases_json TEXT NOT NULL,
                phase_counts_json TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                pending_case_id TEXT,
                feedback_case_id TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                context_key TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                abandoned_at TEXT
            );
            """
        )
        conn.executemany(
            """INSERT INTO training_campaigns (
                campaign_id, learner_id, concept_id, subskill, requested_length,
                length, pool_count, phases_json, phase_counts_json, position,
                pending_case_id, feedback_case_id, status, context_key,
                created_at, updated_at, abandoned_at
            ) VALUES (?, ?, 'right_bundle_branch_block', 'recognize', 10, 1, 1,
                      '["target"]', '{"target":1,"mimic":0,"negative":0,"transfer":0}',
                      0, ?, NULL, 'active', '', ?, ?, NULL)""",
            [
                (
                    "tc_legacy_old",
                    "legacy-owner",
                    "legacy-old-case",
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:00:00+00:00",
                ),
                (
                    "tc_legacy_new",
                    "legacy-owner",
                    "legacy-new-case",
                    "2026-02-01T00:00:00+00:00",
                    "2026-02-01T00:00:00+00:00",
                ),
                (
                    "tc_other_owner",
                    "other-owner",
                    "other-case",
                    "2026-01-15T00:00:00+00:00",
                    "2026-01-15T00:00:00+00:00",
                ),
            ],
        )

    campaigns = TrainingCampaignStore(db)
    assert campaigns.get_active("legacy-owner")["campaignId"] == "tc_legacy_new"
    assert campaigns.get_active("other-owner")["campaignId"] == "tc_other_owner"
    with campaigns.connect() as conn:
        repaired = conn.execute(
            "SELECT status, pending_case_id, feedback_case_id, abandoned_at "
            "FROM training_campaigns WHERE campaign_id = 'tc_legacy_old'"
        ).fetchone()
        index = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'index' "
            "AND name = 'uq_training_campaign_current_learner'"
        ).fetchone()
    assert tuple(repaired[:3]) == ("abandoned", None, None)
    assert repaired["abandoned_at"]
    assert index and "WHERE status = 'active' OR feedback_case_id IS NOT NULL" in index["sql"]

    with pytest.raises(sqlite3.IntegrityError):
        with campaigns.connect() as conn:
            conn.execute(
                """INSERT INTO training_campaigns (
                    campaign_id, learner_id, concept_id, subskill, requested_length,
                    length, pool_count, phases_json, phase_counts_json, position,
                    pending_case_id, status, context_key, created_at, updated_at
                ) VALUES ('tc_illegal_duplicate', 'legacy-owner',
                          'right_bundle_branch_block', 'recognize', 10, 1, 1,
                          '["target"]',
                          '{"target":1,"mimic":0,"negative":0,"transfer":0}',
                          0, 'illegal-case', 'active', '',
                          '2026-03-01T00:00:00+00:00',
                          '2026-03-01T00:00:00+00:00')"""
            )


def test_concurrent_same_owner_starts_commit_one_campaign_and_return_resume_id(tmp_path):
    client, learning, campaigns = _client(tmp_path)
    barrier = threading.Barrier(2)

    def start_campaign():
        barrier.wait(timeout=5)
        return client.post(
            "/training/campaigns",
            headers={"Authorization": "race-owner"},
            json={
                "conceptId": "right_bundle_branch_block",
                "subskill": "recognize",
                "length": 10,
            },
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: start_campaign(), range(2)))

    assert sorted(response.status_code for response in responses) == [200, 409]
    created = next(response.json() for response in responses if response.status_code == 200)
    conflict = next(response.json() for response in responses if response.status_code == 409)
    campaign_id = created["campaign"]["campaignId"]
    assert conflict["detail"] == {
        "code": "active_training_campaign",
        "campaignId": campaign_id,
    }
    assert created["current"]["kind"] == "pending"

    with learning.connect() as conn:
        current_count = conn.execute(
            "SELECT COUNT(*) FROM training_campaigns WHERE learner_id = 'race-owner' "
            "AND (status = 'active' OR feedback_case_id IS NOT NULL)"
        ).fetchone()[0]
        campaign_count = conn.execute(
            "SELECT COUNT(*) FROM training_campaigns WHERE learner_id = 'race-owner'"
        ).fetchone()[0]
        slot_state = conn.execute(
            "SELECT COUNT(*) total, SUM(status = 'pending') pending "
            "FROM training_campaign_slots WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()
    assert current_count == campaign_count == 1
    assert slot_state["total"] == 8
    assert slot_state["pending"] == 1
    assert campaigns.get_active("race-owner")["campaignId"] == campaign_id


def test_concurrent_starts_are_isolated_per_owner(tmp_path):
    client, learning, _ = _client(tmp_path)
    barrier = threading.Barrier(2)

    def start_campaign(owner: str):
        barrier.wait(timeout=5)
        return client.post(
            "/training/campaigns",
            headers={"Authorization": owner},
            json={
                "conceptId": "right_bundle_branch_block",
                "subskill": "recognize",
                "length": 10,
            },
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(start_campaign, ("owner-one", "owner-two")))

    assert [response.status_code for response in responses] == [200, 200]
    campaign_ids = {response.json()["campaign"]["campaignId"] for response in responses}
    assert len(campaign_ids) == 2
    with learning.connect() as conn:
        rows = conn.execute(
            "SELECT learner_id, COUNT(*) total FROM training_campaigns "
            "WHERE status = 'active' GROUP BY learner_id ORDER BY learner_id"
        ).fetchall()
    assert [(row["learner_id"], row["total"]) for row in rows] == [
        ("owner-one", 1),
        ("owner-two", 1),
    ]


def test_recent_independent_ecgs_are_excluded_deterministically_and_owner_scoped(tmp_path):
    db = tmp_path / "recent-depth.sqlite3"
    learning = LearningStore(db)
    campaigns = TrainingCampaignStore(db, learning.connect)
    pool = _role_pool(target=12, mimic=9, negative=9, prefix="depth")
    canonical = _build_plan(pool, 10)
    recent = [
        next(slot["caseId"] for slot in canonical if slot["role"] == role)
        for role in ("target", "mimic", "negative")
    ]
    _seed_recent_independent_training_events(learning, "owner-recent-a", recent)
    _seed_recent_independent_training_events(learning, "owner-recent-c", recent)

    first = campaigns.start_or_return_campaign(
        "owner-recent-a", "right_bundle_branch_block", "discriminate",
        10, len(pool), canonical, pool,
    )["campaign"]
    control = campaigns.start_or_return_campaign(
        "owner-control", "right_bundle_branch_block", "discriminate",
        10, len(pool), canonical, pool,
    )["campaign"]
    repeated = campaigns.start_or_return_campaign(
        "owner-recent-c", "right_bundle_branch_block", "discriminate",
        10, len(pool), canonical, pool,
    )["campaign"]

    first_ids = [slot["caseId"] for slot in campaigns.all_slots(first["campaignId"])]
    control_ids = [slot["caseId"] for slot in campaigns.all_slots(control["campaignId"])]
    repeated_ids = [slot["caseId"] for slot in campaigns.all_slots(repeated["campaignId"])]
    assert set(first_ids).isdisjoint(recent)
    assert control_ids == [slot["caseId"] for slot in canonical]
    assert repeated_ids == first_ids
    assert first_ids != control_ids
    assert first["phaseCounts"] == control["phaseCounts"] == repeated["phaseCounts"]
    assert first["rosterPolicy"]["eligibleRecentOverlapCount"] == len(recent)
    assert first["rosterPolicy"]["excludedRecentCount"] == len(recent)
    assert first["rosterPolicy"]["reusedRecentCount"] == 0
    assert first["rosterPolicy"]["reuseUnavoidable"] is False
    assert control["rosterPolicy"]["eligibleRecentOverlapCount"] == 0


def test_live_cross_mode_exposure_is_hard_excluded_with_same_role_replacement(tmp_path):
    db = tmp_path / "live-exposure-depth.sqlite3"
    learning = LearningStore(db)
    campaigns = TrainingCampaignStore(db, learning.connect)
    owner = "cross-mode-owner"
    pool = _role_pool(target=12, mimic=9, negative=9, prefix="cross-mode")
    canonical = _build_plan(pool, 10)
    exposed_case_id = canonical[0]["caseId"]
    guided_case_id = canonical[1]["caseId"]
    now = datetime.now(UTC)
    with learning.connect() as conn:
        create_lease(
            conn,
            lease_id="cross-mode-rapid-lease",
            owner_id=owner,
            mode="rapid",
            session_id="cross-mode-rapid-round",
            ecg_ids=(exposed_case_id,),
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )
        record_guided_packet_exposure(
            conn,
            owner_id=owner,
            lesson_id="training-cross-mode",
            ecg_id=guided_case_id,
            occurred_at=now,
        )

    campaign = campaigns.start_or_return_campaign(
        owner,
        "right_bundle_branch_block",
        "discriminate",
        10,
        len(pool),
        canonical,
        pool,
    )["campaign"]
    slots = campaigns.all_slots(campaign["campaignId"])
    pool_roles = {entry["caseId"]: entry["role"] for entry in pool}

    assert len(slots) == len({slot["caseId"] for slot in slots}) == 10
    assert {exposed_case_id, guided_case_id}.isdisjoint(
        {slot["caseId"] for slot in slots}
    )
    assert Counter(slot["phase"] for slot in slots) == Counter(
        slot["phase"] for slot in canonical
    )
    assert Counter(pool_roles[slot["caseId"]] for slot in slots) == Counter(
        slot["role"] for slot in canonical
    )
    assert campaign["rosterPolicy"]["liveOwnerExposureCount"] == 2
    assert campaign["rosterPolicy"]["eligibleLiveExposureOverlapCount"] == 2
    assert campaign["rosterPolicy"]["liveExposureHardExcluded"] == 2


def test_training_start_fails_closed_when_live_exposure_exhausts_exact_role_depth(
    tmp_path,
):
    client, learning, _ = _client(tmp_path)
    owner = "cross-mode-shallow"
    now = datetime.now(UTC)
    with learning.connect() as conn:
        create_lease(
            conn,
            lease_id="shallow-rapid-lease",
            owner_id=owner,
            mode="rapid",
            session_id="shallow-rapid-round",
            ecg_ids=("7000",),
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )

    response = client.post(
        "/training/campaigns",
        headers={"Authorization": owner},
        json={
            "conceptId": "right_bundle_branch_block",
            "subskill": "recognize",
            "length": 10,
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "training_live_exposure_conflict"
    with learning.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM training_campaigns WHERE learner_id = ?",
            (owner,),
        ).fetchone()[0] == 0


def test_recent_reuse_fallback_preserves_length_roles_and_phase_composition(tmp_path):
    db = tmp_path / "recent-fallback.sqlite3"
    learning = LearningStore(db)
    campaigns = TrainingCampaignStore(db, learning.connect)
    # Both target ECGs are required by this canonical balanced recipe. The pool
    # has eleven fresh ECGs overall, but no spare fresh target ECG, so the
    # recent target must be reused instead of corrupting contrast composition.
    pool = _role_pool(target=2, mimic=5, negative=5, prefix="fallback")
    canonical = _build_plan(pool, 10, rng=random.Random(37))
    recent_case_id = next(slot["caseId"] for slot in canonical if slot["role"] == "target")
    _seed_recent_independent_training_events(learning, "fallback-owner", [recent_case_id])

    campaign = campaigns.start_or_return_campaign(
        "fallback-owner", "right_bundle_branch_block", "discriminate",
        10, len(pool), canonical, pool,
    )["campaign"]
    slots = campaigns.all_slots(campaign["campaignId"])
    pool_roles = {entry["caseId"]: entry["role"] for entry in pool}

    assert len(slots) == len({slot["caseId"] for slot in slots}) == 10
    assert Counter(slot["phase"] for slot in slots) == Counter(
        slot["phase"] for slot in canonical
    )
    assert Counter(pool_roles[slot["caseId"]] for slot in slots) == Counter(
        slot["role"] for slot in canonical
    )
    assert recent_case_id in {slot["caseId"] for slot in slots}
    reused = [
        slot for slot in slots
        if slot["selectionReason"] == "recent_independent_reuse_unavoidable"
    ]
    assert [slot["caseId"] for slot in reused] == [recent_case_id]
    assert {
        "caseFocus", "phase", "role", "selectionReason", "targetPresent",
    }.isdisjoint(_public_pending_slot(reused[0]))
    policy = campaign["rosterPolicy"]
    assert policy["freshEligibleCount"] == 11
    assert policy["plannedLength"] == policy["requestedLength"] == 10
    assert policy["requestedLengthSatisfied"] is True
    assert policy["reusedRecentCount"] == 1
    assert policy["reusedByRole"] == {"target": 1, "mimic": 0, "negative": 0}
    assert policy["reuseUnavoidable"] is True
    assert policy["reuseReason"] == "composition_preserving_role_depth_exhausted"


def test_5000_case_start_excludes_recent_history_without_shrinking_or_recomposing(tmp_path):
    db = tmp_path / "recent-scale.sqlite3"
    learning = LearningStore(db)
    campaigns = TrainingCampaignStore(db, learning.connect)
    pool = _role_pool(target=2000, mimic=2000, negative=2000, prefix="scale-depth")
    canonical = _build_plan(pool, 5000, rng=random.Random(41))
    recent: list[str] = []
    for role, count in (("target", 300), ("mimic", 100), ("negative", 100)):
        recent.extend([
            slot["caseId"]
            for slot in canonical
            if slot["role"] == role
        ][:count])
    assert len(recent) == 500
    _seed_recent_independent_training_events(learning, "scale-history-owner", recent)

    campaign = campaigns.start_or_return_campaign(
        "scale-history-owner", "right_bundle_branch_block", "discriminate",
        5000, len(pool), canonical, pool,
    )["campaign"]
    slots = campaigns.all_slots(campaign["campaignId"])
    selected_ids = [slot["caseId"] for slot in slots]
    pool_roles = {entry["caseId"]: entry["role"] for entry in pool}

    assert len(slots) == len(set(selected_ids)) == 5000
    assert set(selected_ids).isdisjoint(recent)
    assert Counter(slot["phase"] for slot in slots) == Counter(
        slot["phase"] for slot in canonical
    )
    assert Counter(pool_roles[case_id] for case_id in selected_ids) == Counter(
        slot["role"] for slot in canonical
    )
    assert slots[0]["status"] == "pending"
    policy = campaign["rosterPolicy"]
    assert policy["plannedLength"] == policy["requestedLength"] == 5000
    assert policy["requestedLengthSatisfied"] is True
    assert policy["eligibleRecentOverlapCount"] == 500
    assert policy["excludedRecentCount"] == 500
    assert policy["reusedRecentCount"] == 0
    assert policy["reuseUnavoidable"] is False


def test_5000_case_roster_adapts_with_indexed_lookup_and_preserves_every_unique_case(tmp_path):
    db = tmp_path / "scale.sqlite3"
    learning = LearningStore(db)
    campaigns = TrainingCampaignStore(db, learning.connect)
    learning.ensure_profile("scale-learner")
    plan = [
        {
            "caseId": f"scale-{index:04d}",
            "caseFocus": "right_bundle_branch_block" if index % 3 == 0 else "normal_ecg",
            "targetPresent": index % 3 == 0,
            "phase": "target" if index % 3 == 0 else "mimic" if index % 3 == 1 else "transfer",
        }
        for index in range(5000)
    ]
    campaign = campaigns.create_campaign(
        "scale-learner", "right_bundle_branch_block", "recognize", 5000, 5000, plan
    )
    pending = campaigns.claim_next(campaign["campaignId"])
    assert pending and pending["pendingCaseId"] == "scale-0000"
    reservation = campaigns.claim_answer_submission(
        campaign_id=campaign["campaignId"],
        case_id="scale-0000",
        learner_id="scale-learner",
    )
    assert reservation["status"] == "claimed"

    recorded = campaigns.finalize_answer(
        learning_store=learning,
        campaign_id=campaign["campaignId"],
        case_id="scale-0000",
        learner_id="scale-learner",
        lease_id=reservation["leaseId"],
        submission_key=reservation["submissionKey"],
        response={},
        grade={},
        tutor=None,
        receipt_event={
            "eventKey": f"train:{campaign['campaignId']}:0:scale-0000:recognize",
            "_serverVerifiedScoring": True,
            "moduleId": "train",
            "sceneId": "right_bundle_branch_block:target",
            "interactionId": "scale-0000:recognize",
            "concept": "right_bundle_branch_block",
            "subskills": ["recognize"],
            "score": 0.0,
            "correct": False,
            "attempts": 1,
            "assistance": "independent",
            "hintsUsed": 0,
            "confidence": 3,
            "evidenceLevel": "guided",
            "trainingPhase": "target",
            "evidenceSource": "response",
            "caseId": "scale-0000",
            "caseProvenance": "real_eligible",
            "caseEligible": True,
            "misconceptions": [],
            "_retentionVerified": False,
            "_retentionMorphologyKey": None,
        },
        summary={},
        confidence=3,
        hints_used=0,
        adaptation_preference="target",
        adaptation_reason="target_recheck_after_miss",
    )
    assert recorded["status"] == "recorded"
    assert recorded["adaptedNext"]["caseId"] == "scale-0003"
    assert recorded["adaptedNext"]["selectionReason"] == "target_recheck_after_miss"
    with campaigns.connect() as conn:
        counts = conn.execute(
            "SELECT COUNT(*) total, COUNT(DISTINCT case_id) unique_cases, "
            "SUM(CASE WHEN case_id GLOB '__training_swap__*' THEN 1 ELSE 0 END) temporary "
            "FROM training_campaign_slots WHERE campaign_id = ?",
            (campaign["campaignId"],),
        ).fetchone()
        indexes = {
            row["name"]
            for row in conn.execute("PRAGMA index_list(training_campaign_slots)").fetchall()
        }
    assert counts["total"] == counts["unique_cases"] == 5000
    assert counts["temporary"] == 0
    assert "idx_training_slot_adaptive" in indexes


def test_committed_miss_reorders_only_unseen_real_roster_for_target_recheck(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        training_routes_module.secrets, "SystemRandom", lambda: random.Random(1)
    )
    client, _, campaigns = _client(tmp_path)
    started = client.post(
        "/training/campaigns",
        headers={"Authorization": "adaptive-miss"},
        json={"conceptId": "right_bundle_branch_block", "subskill": "recognize", "length": 10},
    ).json()
    campaign_id = started["campaign"]["campaignId"]
    first_case_ref = started["current"]["case"]["caseId"]
    first_case_id = _pending_canonical(campaigns, campaign_id)
    first_slot = campaigns.get_slot_for_case(campaign_id, first_case_id)
    assert first_slot and first_slot["targetPresent"] is True
    roster_before = {slot["caseId"] for slot in campaigns.all_slots(campaign_id)}

    submitted = client.post(
        f"/training/campaigns/{campaign_id}/submit",
        headers={"Authorization": "adaptive-miss"},
        json={
            "caseId": first_case_ref,
            "selectedAnswer": "absent",
            "confidence": 4,
        },
    )
    assert submitted.status_code == 200, submitted.text

    slots_after = campaigns.all_slots(campaign_id)
    assert {slot["caseId"] for slot in slots_after} == roster_before
    assert len(roster_before) == len(slots_after)
    assert all(not slot["caseId"].startswith("fixture") for slot in slots_after)
    next_private = slots_after[1]
    assert next_private["targetPresent"] is True
    assert next_private["selectionReason"] == "target_recheck_after_miss"

    advanced = client.post(
        f"/training/campaigns/{campaign_id}/next",
        headers={"Authorization": "adaptive-miss"},
    ).json()
    assert advanced["current"]["case"]["caseId"] != first_case_ref
    assert {
        "caseFocus", "phase", "role", "selectionReason", "targetPresent",
    }.isdisjoint(advanced["current"]["slot"])


def test_committed_target_success_selects_contrast_without_changing_unique_roster(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        training_routes_module.secrets, "SystemRandom", lambda: random.Random(1)
    )
    client, _, campaigns = _client(tmp_path)
    started = client.post(
        "/training/campaigns",
        headers={"Authorization": "adaptive-success"},
        json={"conceptId": "right_bundle_branch_block", "subskill": "recognize", "length": 10},
    ).json()
    campaign_id = started["campaign"]["campaignId"]
    first_case_ref = started["current"]["case"]["caseId"]
    first_case_id = _pending_canonical(campaigns, campaign_id)
    first_slot = campaigns.get_slot_for_case(campaign_id, first_case_id)
    assert first_slot and first_slot["targetPresent"] is True
    roster_before = {slot["caseId"] for slot in campaigns.all_slots(campaign_id)}

    response = client.post(
        f"/training/campaigns/{campaign_id}/submit",
        headers={"Authorization": "adaptive-success"},
        json={
            "caseId": first_case_ref,
            "selectedAnswer": "present",
            "confidence": 4,
        },
    )
    assert response.status_code == 200, response.text

    slots_after = campaigns.all_slots(campaign_id)
    assert {slot["caseId"] for slot in slots_after} == roster_before
    assert len({slot["caseId"] for slot in slots_after}) == len(slots_after)
    assert slots_after[1]["targetPresent"] is False
    assert slots_after[1]["selectionReason"] == "contrast_after_target_success"


def test_training_finalization_rolls_back_every_receipt_and_advance_boundary(tmp_path):
    client, learning, campaigns = _client(tmp_path)
    learner = "atomic-training"
    campaign_id, pending = _reach_transfer(
        client, campaigns, learner=learner, subskill="discriminate"
    )
    case_ref = pending["current"]["case"]["caseId"]
    case_id = _pending_canonical(campaigns, campaign_id)
    slot = campaigns.get_slot_for_case(campaign_id, case_id)
    assert slot and slot["phase"] == "transfer"
    contract = build_subskill_task(
        case_id=case_id,
        case_concept="right_bundle_branch_block",
        subskill="discriminate",
        case_focus=slot["caseFocus"],
        contrast_family=_contrast_family("right_bundle_branch_block"),
        variant=int(slot["position"]),
    )
    assert contract and contract.correct_answer
    body = {
        "caseId": case_ref,
        "selectedAnswer": "present" if slot["targetPresent"] else "absent",
        "confidence": 4,
        "subskillTaskAnswer": contract.correct_answer,
        "receiptConcept": "right_bundle_branch_block",
    }
    baseline = _training_atomic_snapshot(
        learning, campaign_id, learner, case_id
    )
    roster_before = {row[2] for row in baseline["slots"]}
    checkpoints: list[str] = []

    def fail_after_adaptation(label: str) -> None:
        checkpoints.append(label)
        if label == "after_adaptation":
            raise RuntimeError("injected:after_adaptation")

    setattr(campaigns, "_training_finalization_failure_hook", fail_after_adaptation)
    try:
        with pytest.raises(RuntimeError, match="injected:after_adaptation"):
            client.post(
                f"/training/campaigns/{campaign_id}/submit",
                headers={"Authorization": learner},
                json=body,
            )
    finally:
        delattr(campaigns, "_training_finalization_failure_hook")
    assert checkpoints == [
        "after_attempt",
        "after_answer",
        "after_receipt",
        "after_learner_event",
        "after_lease_submitted",
        "after_receipt_persisted",
        "after_slot_answered",
        "after_campaign_advance",
        "after_adaptation",
    ]
    assert _training_atomic_snapshot(learning, campaign_id, learner, case_id) == baseline

    for checkpoint in checkpoints[:-1]:
        def fail_at_boundary(label: str, *, target: str = checkpoint) -> None:
            if label == target:
                raise RuntimeError(f"injected:{target}")

        setattr(campaigns, "_training_finalization_failure_hook", fail_at_boundary)
        try:
            with pytest.raises(RuntimeError, match=f"injected:{checkpoint}"):
                client.post(
                    f"/training/campaigns/{campaign_id}/submit",
                    headers={"Authorization": learner},
                    json=body,
                )
        finally:
            delattr(campaigns, "_training_finalization_failure_hook")
        assert _training_atomic_snapshot(learning, campaign_id, learner, case_id) == baseline

    committed = client.post(
        f"/training/campaigns/{campaign_id}/submit",
        headers={"Authorization": learner},
        json=body,
    )
    assert committed.status_code == 200, committed.text
    committed_body = committed.json()
    assert committed_body["replay"] is False
    assert committed_body["answer"]["integrityStatus"] == "atomic_v2"
    assert committed_body["answer"]["receipt"]["effectiveEvidenceLevel"] == "independent_transfer"
    durable = _training_atomic_snapshot(learning, campaign_id, learner, case_id)
    assert len(durable["answers"]) == durable["attempts"] == durable["events"] == durable["retention"] == 1
    assert durable["answers"] == ["atomic_v2"]
    assert durable["campaign"][0] == baseline["campaign"][0] + 1
    assert durable["campaign"][1] is None
    assert durable["campaign"][2] == case_id
    assert {row[2] for row in durable["slots"]} == roster_before
    assert len({row[2] for row in durable["slots"]}) == len(durable["slots"])

    replay = client.post(
        f"/training/campaigns/{campaign_id}/submit",
        headers={"Authorization": learner},
        json={**body, "selectedAnswer": "absent" if body["selectedAnswer"] == "present" else "present", "confidence": 1},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["replay"] is True
    assert replay.json()["answer"] == committed_body["answer"]
    assert _training_atomic_snapshot(learning, campaign_id, learner, case_id) == durable


def test_concurrent_training_submissions_commit_one_answer_and_one_evidence_event(tmp_path):
    client, learning, campaigns = _client(tmp_path)
    learner = "concurrent-training"
    started = client.post(
        "/training/campaigns",
        headers={"Authorization": learner},
        json={"conceptId": "right_bundle_branch_block", "subskill": "recognize", "length": 10},
    ).json()
    campaign_id = started["campaign"]["campaignId"]
    case_ref = started["current"]["case"]["caseId"]
    case_id = _pending_canonical(campaigns, campaign_id)
    slot = campaigns.get_slot_for_case(campaign_id, case_id)
    body = {
        "caseId": case_ref,
        "selectedAnswer": "present" if slot["targetPresent"] else "absent",
        "confidence": 4,
    }
    barrier = threading.Barrier(2)

    def submit_once():
        barrier.wait()
        response = client.post(
            f"/training/campaigns/{campaign_id}/submit",
            headers={"Authorization": learner},
            json=body,
        )
        return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: submit_once(), range(2)))

    assert [status for status, _ in results] == [200, 200]
    payloads = [payload for _, payload in results]
    assert sorted(payload["replay"] for payload in payloads) == [False, True]
    assert len({payload["answer"]["answerId"] for payload in payloads}) == 1
    assert all(payload["answer"]["integrityStatus"] == "atomic_v2" for payload in payloads)
    snapshot = _training_atomic_snapshot(learning, campaign_id, learner, case_id)
    assert snapshot["answers"] == ["atomic_v2"]
    assert snapshot["attempts"] == snapshot["events"] == 1
    assert snapshot["retention"] == 0
    assert snapshot["campaign"][0] == 1
    assert snapshot["campaign"][1] is None
    assert snapshot["campaign"][2] == case_id
    assert [row[1] for row in snapshot["leases"]] == ["submitted"]
    assert [row[3] for row in snapshot["ledgerEvents"]].count("item_presented") == 1
    assert [row[3] for row in snapshot["ledgerEvents"]].count("answer_committed") == 1
    assert len(snapshot["competencyRows"]) == 1
    assert snapshot["competencyRows"][0][1:] == (
        "right_bundle_branch_block:recognize",
        1.0,
    )


def test_pending_ecg_and_lease_are_exposed_in_one_owner_bound_generation(tmp_path):
    client, learning, campaigns = _client(tmp_path)
    started = client.post(
        "/training/campaigns",
        headers={"Authorization": "lease-owner"},
        json={
            "conceptId": "right_bundle_branch_block",
            "subskill": "recognize",
            "length": 10,
        },
    )
    assert started.status_code == 200, started.text
    payload = started.json()
    campaign_id = payload["campaign"]["campaignId"]
    case_id = _pending_canonical(campaigns, campaign_id)

    with learning.connect() as conn:
        lease = conn.execute(
            "SELECT lease_id, owner_id, mode, session_id, state, integrity_status "
            "FROM assessment_leases WHERE session_id = ?",
            (campaign_id,),
        ).fetchone()
        protected = conn.execute(
            "SELECT ecg_id FROM assessment_lease_cases WHERE lease_id = ?",
            (lease["lease_id"],),
        ).fetchall()
        events = conn.execute(
            "SELECT event_type, ecg_id, score FROM learner_events "
            "WHERE session_id = ? ORDER BY created_at",
            (campaign_id,),
        ).fetchall()

    assert tuple(lease[1:]) == (
        "lease-owner",
        "training",
        campaign_id,
        "active",
        "atomic_v2",
    )
    assert [row["ecg_id"] for row in protected] == [case_id]
    assert [tuple(row) for row in events] == [("item_presented", case_id, None)]
    assert campaigns.is_case_pending(case_id) is True
    assert campaigns.is_case_pending_for_learner(case_id, "lease-owner") is True
    assert campaigns.is_case_pending_for_learner(case_id, "another-owner") is False


def test_grading_failure_releases_exact_claim_and_retry_is_not_trapped(
    tmp_path, monkeypatch
):
    client, learning, _ = _client(tmp_path)
    learner = "grading-recovery"
    started = client.post(
        "/training/campaigns",
        headers={"Authorization": learner},
        json={
            "conceptId": "right_bundle_branch_block",
            "subskill": "recognize",
            "length": 10,
        },
    ).json()
    campaign_id = started["campaign"]["campaignId"]
    case_id = started["current"]["case"]["caseId"]
    observed_states: list[str] = []
    original_grade_attempt = training_routes_module.grade_attempt

    def fail_after_claim(case, attempt):
        with learning.connect() as conn:
            state = conn.execute(
                "SELECT state FROM assessment_leases WHERE owner_id = ? "
                "AND mode = 'training' AND session_id = ?",
                (learner, campaign_id),
            ).fetchone()["state"]
        observed_states.append(str(state))
        raise RuntimeError("recoverable grading failure")

    monkeypatch.setattr(training_routes_module, "grade_attempt", fail_after_claim)
    with pytest.raises(RuntimeError, match="recoverable grading failure"):
        client.post(
            f"/training/campaigns/{campaign_id}/submit",
            headers={"Authorization": learner},
            json={"caseId": case_id, "selectedAnswer": "present", "confidence": 4},
        )
    assert observed_states == ["submitting"]

    with learning.connect() as conn:
        lease = conn.execute(
            "SELECT state, submission_key_hash, claimed_at, terminal_at "
            "FROM assessment_leases WHERE owner_id = ? AND session_id = ?",
            (learner, campaign_id),
        ).fetchone()
        answer_count = conn.execute(
            "SELECT COUNT(*) FROM training_campaign_answers WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()[0]
        committed_count = conn.execute(
            "SELECT COUNT(*) FROM learner_events WHERE session_id = ? "
            "AND event_type = 'answer_committed'",
            (campaign_id,),
        ).fetchone()[0]
    assert tuple(lease) == ("active", None, None, None)
    assert answer_count == committed_count == 0

    monkeypatch.setattr(
        training_routes_module,
        "grade_attempt",
        original_grade_attempt,
    )
    retry = client.post(
        f"/training/campaigns/{campaign_id}/submit",
        headers={"Authorization": learner},
        json={"caseId": case_id, "selectedAnswer": "present", "confidence": 4},
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["replay"] is False


def test_expired_untimed_lease_rotates_once_under_concurrent_resume(
    tmp_path, monkeypatch
):
    client, learning, _ = _client(tmp_path)
    learner = "expiry-race"
    started = client.post(
        "/training/campaigns",
        headers={"Authorization": learner},
        json={
            "conceptId": "right_bundle_branch_block",
            "subskill": "recognize",
            "length": 10,
        },
    ).json()
    campaign_id = started["campaign"]["campaignId"]
    case_id = started["current"]["case"]["caseId"]
    with learning.connect() as conn:
        old_lease = conn.execute(
            "SELECT lease_id, expires_at FROM assessment_leases "
            "WHERE session_id = ? AND state = 'active'",
            (campaign_id,),
        ).fetchone()
    future = (
        training_store_module._utc(str(old_lease["expires_at"]))
        + timedelta(seconds=1)
    ).isoformat()
    monkeypatch.setattr(training_store_module, "_now", lambda: future)
    barrier = threading.Barrier(2)

    def resume_once():
        barrier.wait(timeout=5)
        return client.get(
            "/training/campaigns/active",
            headers={"Authorization": learner},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: resume_once(), range(2)))
    assert [response.status_code for response in responses] == [200, 200]
    assert {
        response.json()["current"]["case"]["caseId"] for response in responses
    } == {case_id}

    with learning.connect() as conn:
        leases = conn.execute(
            "SELECT lease_id, state FROM assessment_leases WHERE session_id = ? "
            "ORDER BY created_at, lease_id",
            (campaign_id,),
        ).fetchall()
        event_types = [
            row["event_type"]
            for row in conn.execute(
                "SELECT event_type FROM learner_events WHERE session_id = ? "
                "ORDER BY created_at, event_id",
                (campaign_id,),
            ).fetchall()
        ]
    assert len(leases) == 2
    assert {row["state"] for row in leases} == {"expired", "active"}
    assert next(row for row in leases if row["state"] == "expired")["lease_id"] == old_lease["lease_id"]
    assert event_types.count("item_expired") == 1
    assert event_types.count("item_presented") == 2

    assert client.get(
        "/training/campaigns/active",
        headers={"Authorization": learner},
    ).status_code == 200
    with learning.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM learner_events WHERE session_id = ? "
            "AND event_type = 'item_expired'",
            (campaign_id,),
        ).fetchone()[0] == 1


def test_abandon_terminalizes_pending_item_once_and_owner_cannot_be_spoofed(tmp_path):
    client, learning, campaigns = _client(tmp_path)
    learner = "abandon-owner"
    started = client.post(
        "/training/campaigns",
        headers={"Authorization": learner},
        json={
            "conceptId": "right_bundle_branch_block",
            "subskill": "recognize",
            "length": 10,
        },
    ).json()
    campaign_id = started["campaign"]["campaignId"]
    case_id = started["current"]["case"]["caseId"]
    assert campaigns.claim_answer_submission(
        campaign_id=campaign_id,
        case_id=case_id,
        learner_id="spoofed-owner",
    )["status"] == "missing"
    assert client.post(
        f"/training/campaigns/{campaign_id}/abandon",
        headers={"Authorization": "spoofed-owner"},
    ).status_code == 404

    first = client.post(
        f"/training/campaigns/{campaign_id}/abandon",
        headers={"Authorization": learner},
    )
    second = client.post(
        f"/training/campaigns/{campaign_id}/abandon",
        headers={"Authorization": learner},
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["campaign"]["status"] == "abandoned"
    with learning.connect() as conn:
        lease_states = [
            row["state"]
            for row in conn.execute(
                "SELECT state FROM assessment_leases WHERE session_id = ?",
                (campaign_id,),
            ).fetchall()
        ]
        abandoned_events = conn.execute(
            "SELECT event_type, score FROM learner_events WHERE session_id = ? "
            "AND event_type = 'item_abandoned'",
            (campaign_id,),
        ).fetchall()
    assert lease_states == ["abandoned"]
    assert [tuple(row) for row in abandoned_events] == [("item_abandoned", None)]
    assert campaigns.is_case_pending(case_id) is False


def test_abandon_wins_safely_after_claim_without_partial_answer(
    tmp_path, monkeypatch
):
    client, learning, _ = _client(tmp_path)
    learner = "submit-abandon-race"
    started = client.post(
        "/training/campaigns",
        headers={"Authorization": learner},
        json={
            "conceptId": "right_bundle_branch_block",
            "subskill": "recognize",
            "length": 10,
        },
    ).json()
    campaign_id = started["campaign"]["campaignId"]
    case_id = started["current"]["case"]["caseId"]
    grading_started = threading.Event()
    grading_may_finish = threading.Event()
    original_grade_attempt = training_routes_module.grade_attempt

    def delayed_grade(case, attempt):
        grading_started.set()
        if not grading_may_finish.wait(timeout=10):
            raise RuntimeError("test grading barrier timed out")
        return original_grade_attempt(case, attempt)

    monkeypatch.setattr(training_routes_module, "grade_attempt", delayed_grade)

    def submit_once():
        return client.post(
            f"/training/campaigns/{campaign_id}/submit",
            headers={"Authorization": learner},
            json={"caseId": case_id, "selectedAnswer": "present", "confidence": 4},
        )

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(submit_once)
        try:
            assert grading_started.wait(timeout=10)
            abandoned = client.post(
                f"/training/campaigns/{campaign_id}/abandon",
                headers={"Authorization": learner},
            )
            assert abandoned.status_code == 200, abandoned.text
        finally:
            grading_may_finish.set()
        submitted = future.result(timeout=10)

    assert submitted.status_code == 409
    assert submitted.json()["detail"]["code"] == "training_assessment_changed"
    with learning.connect() as conn:
        campaign = conn.execute(
            "SELECT status, pending_case_id, feedback_case_id FROM training_campaigns "
            "WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()
        lease = conn.execute(
            "SELECT state FROM assessment_leases WHERE session_id = ?",
            (campaign_id,),
        ).fetchone()
        answer_count = conn.execute(
            "SELECT COUNT(*) FROM training_campaign_answers WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()[0]
        committed_count = conn.execute(
            "SELECT COUNT(*) FROM learner_events WHERE session_id = ? "
            "AND event_type = 'answer_committed'",
            (campaign_id,),
        ).fetchone()[0]
        abandoned_count = conn.execute(
            "SELECT COUNT(*) FROM learner_events WHERE session_id = ? "
            "AND event_type = 'item_abandoned'",
            (campaign_id,),
        ).fetchone()[0]
    assert tuple(campaign) == ("abandoned", None, None)
    assert lease["state"] == "abandoned"
    assert answer_count == committed_count == 0
    assert abandoned_count == 1


def test_structured_task_variants_are_varied_but_reproducible():
    arguments = {
        "case_id": "7000",
        "case_concept": "right_bundle_branch_block",
        "subskill": "discriminate",
        "case_focus": "right_bundle_branch_block",
        "contrast_family": _contrast_family("right_bundle_branch_block"),
    }
    first = build_subskill_task(**arguments, variant=0)
    first_again = build_subskill_task(**arguments, variant=0)
    second = build_subskill_task(**arguments, variant=1)
    assert first and first_again and second
    assert first.public == first_again.public
    assert first.correct_answer == first_again.correct_answer
    assert first.public["variant"] == 0
    assert second.public["variant"] == 1
    assert first.public["prompt"] != second.public["prompt"]

    def correct_label(contract):
        return next(
            option["label"] for option in contract.public["options"]
            if option["id"] == contract.correct_answer
        )

    assert correct_label(first) == correct_label(second) == "Right bundle branch block"


def test_classification_contract_is_versioned_stable_and_answer_free():
    first = build_training_classification_contract(
        "right_bundle_branch_block", 0
    )
    repeated = build_training_classification_contract(
        "right_bundle_branch_block", 0
    )
    alternate = build_training_classification_contract(
        "right_bundle_branch_block", 1
    )
    qtc = build_training_classification_contract("qtc_prolongation", 2)

    assert first == repeated
    assert first["version"] == "focused-classification-v1"
    assert [option["id"] for option in first["options"]] == ["present", "absent"]
    assert [option["id"] for option in alternate["options"]] == ["absent", "present"]
    assert first["prompt"] != alternate["prompt"]
    assert qtc["presentLabel"] == "QTc ≥480 ms"
    assert qtc["absentLabel"] == "QTc <480 ms"
    encoded = json.dumps(first, sort_keys=True).casefold()
    assert "correctanswer" not in encoded
    assert "expectedanswer" not in encoded
    assert "targetpresent" not in encoded


def test_packet_grounded_fill_in_and_matching_contracts_are_deterministic_and_key_safe():
    packet = _cases()[0]
    common = {
        "case_id": packet["case_id"],
        "case_concept": "right_bundle_branch_block",
        "case_focus": "right_bundle_branch_block",
        "contrast_family": _contrast_family("right_bundle_branch_block"),
        "case_packet": packet,
    }

    measurement = build_subskill_task(**common, subskill="measure", variant=0)
    measurement_again = build_subskill_task(**common, subskill="measure", variant=0)
    measurement_variant = build_subskill_task(**common, subskill="measure", variant=1)
    assert measurement and measurement_again and measurement_variant
    assert measurement.public == measurement_again.public
    assert measurement.public["kind"] == "numeric_fill_in"
    assert measurement.public["prompt"] != measurement_variant.public["prompt"]
    assert measurement.expected_value == 92.0
    assert measurement.tolerance == 20.0
    assert measurement.grounding == {"packetFeature": "qrs_ms"}
    measurement_public = json.dumps(measurement.public, sort_keys=True)
    assert "expectedValue" not in measurement_public
    assert "tolerance" not in measurement.public
    assert "packetFeature" not in measurement_public
    assert "qrs_ms" not in measurement_public
    assert "92.0" not in measurement_public

    exact = grade_subskill_task(measurement, numeric_value=92.0)
    near = grade_subskill_task(measurement, numeric_value=111.0)
    outside = grade_subskill_task(measurement, numeric_value=113.0)
    invalid = grade_subskill_task(measurement, numeric_value=999.0)
    assert exact == {
        "kind": "numeric_fill_in", "complete": True, "correct": True,
        "score": 1.0, "submittedValue": 92.0, "expectedValue": 92.0,
        "tolerance": 20.0, "unit": "ms", "absoluteError": 0.0,
    }
    assert near["correct"] is True
    assert outside["correct"] is False and outside["score"] == 0.5
    assert invalid["complete"] is False and invalid["correct"] is False

    unsupported_measurement = build_subskill_task(
        **{**common, "case_concept": "left_axis_deviation"},
        subskill="measure",
        variant=0,
    )
    assert unsupported_measurement is None

    qtc_packet = deepcopy(packet)
    qtc_packet["ptbxl_plus"]["fiducials"]["rois"].append({
        "concept": "qt_segment",
        "lead": "II",
        "label": "QT interval",
        "timeStartSec": 0.50,
        "timeEndSec": 0.88,
        "ampMinMv": -0.5,
        "ampMaxMv": 1.0,
    })
    qtc_measurement = build_subskill_task(
        **{
            **common,
            "case_concept": "qtc_prolongation",
            "case_focus": "qtc_prolongation",
            "contrast_family": _contrast_family("qtc_prolongation"),
            "case_packet": qtc_packet,
        },
        subskill="measure",
        variant=0,
    )
    assert qtc_measurement is not None
    assert qtc_measurement.public["responseLabel"] == "QTc"
    assert qtc_measurement.expected_value == 416.0
    assert qtc_measurement.grounding == {"packetFeature": "qtc_ms"}
    assert qtc_measurement.evidence_source == "packet_measurement:qtc_ms"
    qtc_trace_valid, qtc_trace_native = _evidence_valid(
        qtc_packet,
        "qtc_prolongation",
        "measure",
        {
            "mode": "caliper",
            "lead": "II",
            "timeStartSec": 0.50,
            "timeEndSec": 0.88,
            "valueMs": 380,
        },
        "",
    )
    assert qtc_trace_native is True
    assert qtc_trace_valid is True
    qtc_as_caliper_valid, _ = _evidence_valid(
        qtc_packet,
        "qtc_prolongation",
        "measure",
        {
            "mode": "caliper",
            "lead": "II",
            "timeStartSec": 0.50,
            "timeEndSec": 0.916,
            "valueMs": 416,
        },
        "",
    )
    assert qtc_as_caliper_valid is False
    qtc_packet["supported_objectives"].extend(
        ["qt_interval", "qtc_prolongation"]
    )
    assert _expected_answer(qtc_packet, "qt_interval", "measure") is None
    assert _expected_answer(qtc_packet, "qtc_prolongation", "recognize") == "absent"
    qtc_packet["ptbxl_plus"]["measurements"]["qtc_ms"] = 500.0
    assert _expected_answer(qtc_packet, "qt_interval", "measure") is None
    assert _expected_answer(qtc_packet, "qtc_prolongation", "recognize") == "present"
    assert TrainingPoolResolver._pair_is_supported("qt_interval", "measure") is False
    assert TrainingPoolResolver._pair_is_supported("qt_interval", "recognize") is False
    assert TrainingPoolResolver._pair_is_supported(
        "qtc_prolongation", "recognize"
    ) is True

    direct_qt_measurement = build_subskill_task(
        **{
            **common,
            "case_concept": "qt_interval",
            "case_focus": "qtc_prolongation",
            "contrast_family": _contrast_family("qtc_prolongation"),
            "case_packet": qtc_packet,
        },
        subskill="measure",
        variant=0,
    )
    assert direct_qt_measurement is not None
    assert direct_qt_measurement.public["responseLabel"] == "QT interval"
    assert direct_qt_measurement.expected_value == 380.0
    assert direct_qt_measurement.grounding == {"packetFeature": "qt_ms"}
    assert direct_qt_measurement.evidence_source == "packet_measurement:qt_ms"

    synthesis = build_subskill_task(**common, subskill="synthesize", variant=1)
    synthesis_again = build_subskill_task(**common, subskill="synthesize", variant=1)
    assert synthesis and synthesis_again
    assert synthesis.public == synthesis_again.public
    assert synthesis.public["kind"] == "single_choice"
    assert synthesis.correct_matches is None
    assert synthesis.public["frameworkVersion"] == (
        "focused-systematic-interpretation-v1"
    )
    assert [row["key"] for row in synthesis.public["frameworkSteps"]] == list(
        SYSTEMATIC_INTERPRETATION
    )

    application_matching = build_subskill_task(
        **common, subskill="apply_in_context", variant=1
    )
    assert application_matching is not None
    assert application_matching.public["kind"] == "matching"
    assert {choice["label"] for choice in application_matching.public["choices"]} == {
        "ECG finding to integrate",
        "Context required before a pathway",
        "Bounded clinical application",
    }
    application_public = json.dumps(
        application_matching.public, sort_keys=True
    ).casefold()
    assert "qrs duration, morphology, and lead distribution" in application_public
    assert "select an appropriate pathway" in application_public
    correct_matching = grade_subskill_task(
        application_matching, matches=application_matching.correct_matches,
    )
    ordered_rows = list(application_matching.correct_matches)
    ordered_choices = [
        application_matching.correct_matches[row] for row in ordered_rows
    ]
    rotated = {
        row: ordered_choices[(index + 1) % len(ordered_choices)]
        for index, row in enumerate(ordered_rows)
    }
    wrong_matching = grade_subskill_task(application_matching, matches=rotated)
    duplicate_matching = grade_subskill_task(
        application_matching,
        matches={row: ordered_choices[0] for row in ordered_rows},
    )
    assert correct_matching["complete"] is True
    assert correct_matching["correct"] is True
    assert correct_matching["score"] == 1.0
    assert wrong_matching["complete"] is True
    assert wrong_matching["correct"] is False
    assert wrong_matching["score"] == 0.0
    assert duplicate_matching["complete"] is False
    assert duplicate_matching["correct"] is False

    ungrounded_packet = deepcopy(packet)
    ungrounded_packet["supported_objectives"] = ["normal_ecg"]
    blinded_negative = build_subskill_task(
        **{**common, "case_packet": ungrounded_packet},
        subskill="synthesize",
        variant=1,
    )
    assert blinded_negative and blinded_negative.public["kind"] == "single_choice"
    assert blinded_negative.public == synthesis.public
    negative_public = json.dumps(blinded_negative.public, sort_keys=True).casefold()
    assert "right bundle branch block" not in negative_public


def test_mechanism_distractors_stay_in_the_same_electrical_domain_and_vary():
    rbbb_labels_by_variant = []
    for variant in range(3):
        contract = build_subskill_task(
            case_id="ptbxl:mechanism-rbbb",
            case_concept="right_bundle_branch_block",
            subskill="explain_mechanism",
            case_focus="right_bundle_branch_block",
            contrast_family=_contrast_family("right_bundle_branch_block"),
            variant=variant,
        )
        assert contract is not None
        labels = {option["label"] for option in contract.public["options"]}
        rbbb_labels_by_variant.append(labels)
        assert MECHANISM_EXPLANATIONS["right_bundle_branch_block"] in labels
        assert labels <= {
            MECHANISM_EXPLANATIONS[concept]
            for concept in {
                "right_bundle_branch_block", "left_bundle_branch_block",
                "incomplete_right_bundle_branch_block", "qrs_duration",
                "nonspecific_intraventricular_conduction_delay",
                "left_anterior_fascicular_block", "left_posterior_fascicular_block",
                "wolff_parkinson_white", "paced_rhythm", "wide_complex_tachycardia",
            }
        }
    assert len({frozenset(labels) for labels in rbbb_labels_by_variant}) > 1

    qtc = build_subskill_task(
        case_id="ptbxl:mechanism-qtc",
        case_concept="qtc_prolongation",
        subskill="explain_mechanism",
        case_focus="qtc_prolongation",
        contrast_family=_contrast_family("qtc_prolongation"),
        variant=0,
    )
    assert qtc is not None
    qtc_labels = {option["label"] for option in qtc.public["options"]}
    assert MECHANISM_EXPLANATIONS["qt_interval"] in qtc_labels
    assert MECHANISM_EXPLANATIONS["electrolyte_drug_pattern"] in qtc_labels


def test_measurement_evidence_requires_bounded_recomputed_roi_geometry():
    packet = _cases()[0]
    valid = {
        "mode": "caliper",
        "lead": "V1",
        "timeStartSec": 0.320,
        "timeEndSec": 0.412,
        "valueMs": 92,
    }
    assert _evidence_valid(
        packet, "right_bundle_branch_block", "measure", valid, ""
    ) == (True, True)

    forged_rows = [
        {"mode": "caliper", "lead": "V1", "valueMs": 92},
        {
            "mode": "caliper", "lead": "V1",
            "timeStartSec": 0.30, "timeEndSec": 0.44, "valueMs": 92,
        },
        {
            "mode": "caliper", "lead": "V1",
            "timeStartSec": 0.412, "timeEndSec": 0.320, "valueMs": 92,
        },
        {
            "mode": "caliper", "lead": "V1",
            "timeStartSec": 9.95, "timeEndSec": 10.042, "valueMs": 92,
        },
        {
            "mode": "caliper", "lead": "V1",
            "timeStartSec": 0.80, "timeEndSec": 0.892, "valueMs": 92,
        },
    ]
    for forged in forged_rows:
        assert _evidence_valid(
            packet, "right_bundle_branch_block", "measure", forged, ""
        ) == (False, True)

    rate_packet = deepcopy(packet)
    rate_packet["ptbxl_plus"]["fiducials"]["rois"].extend([
        {
            "concept": "qrs_complex", "lead": "II", "label": "QRS",
            "timeStartSec": 1.00, "timeEndSec": 1.10,
            "ampMinMv": -0.5, "ampMaxMv": 1.0,
        },
        {
            "concept": "qrs_complex", "lead": "II", "label": "QRS",
            "timeStartSec": 1.833, "timeEndSec": 1.933,
            "ampMinMv": -0.5, "ampMaxMv": 1.0,
        },
    ])
    assert _evidence_valid(
        rate_packet,
        "rate",
        "measure",
        {
            "mode": "caliper", "lead": "II",
            "timeStartSec": 1.05, "timeEndSec": 1.883, "valueMs": 833,
        },
        "",
    ) == (True, True)
    assert _evidence_valid(
        rate_packet,
        "rate",
        "measure",
        {
            "mode": "caliper", "lead": "II",
            "timeStartSec": 3.00, "timeEndSec": 3.833, "valueMs": 833,
        },
        "",
    ) == (False, True)


def test_numeric_fill_in_is_server_graded_postcommit_and_replays_atomically(tmp_path):
    client, _, campaigns = _client(tmp_path)
    learner = "numeric-fill-in"
    started = client.post(
        "/training/campaigns",
        headers={"Authorization": learner},
        json={
            "conceptId": "right_bundle_branch_block",
            "subskill": "measure",
            "length": 10,
        },
    ).json()
    campaign_id = started["campaign"]["campaignId"]
    case_ref = started["current"]["case"]["caseId"]
    case_id = _pending_canonical(campaigns, campaign_id)
    slot = campaigns.get_slot_for_case(campaign_id, case_id)
    packet = next(case for case in _cases() if case["case_id"] == case_id)
    task = started["current"]["task"]
    question_snapshot = started["current"]["questionSnapshot"]
    assert task["kind"] == "numeric_fill_in"
    assert question_snapshot == {
        "version": "focused-question-v1",
        "classification": build_training_classification_contract(
            "right_bundle_branch_block", int(slot["position"])
        ),
        "task": task,
    }
    assert started["current"]["classification"] == (
        question_snapshot["classification"]
    )
    assert "expectedValue" not in task
    assert "tolerance" not in task
    assert "packetFeature" not in task
    expected = float(packet["ptbxl_plus"]["measurements"]["qrs_ms"])
    roster_before = {row["caseId"] for row in campaigns.all_slots(campaign_id)}
    body = {
        "caseId": case_ref,
        "selectedAnswer": "present" if slot["targetPresent"] else "absent",
        "confidence": 4,
        "viewerTaskEvidence": {
            "mode": "caliper",
            "lead": "V1",
            "timeStartSec": 0.320,
            "timeEndSec": 0.412,
            "valueMs": expected,
        },
        "subskillTaskValue": expected,
    }
    submitted = client.post(
        f"/training/campaigns/{campaign_id}/submit",
        headers={"Authorization": learner},
        json=body,
    )
    assert submitted.status_code == 200, submitted.text
    payload = submitted.json()
    assert payload["replay"] is False
    assert payload["answer"]["integrityStatus"] == "atomic_v2"
    assert payload["answer"]["response"]["subskillTaskValue"] == expected
    assert payload["answer"]["response"]["questionSnapshot"] == question_snapshot
    assert payload["current"]["questionSnapshot"] == question_snapshot
    assert payload["current"]["classification"] == question_snapshot["classification"]
    assert payload["current"]["task"] == question_snapshot["task"]
    task_result = payload["answer"]["grade"]["trainingSubskillTaskResult"]
    assert task_result["correct"] is True
    assert task_result["expectedValue"] == expected
    assert task_result["tolerance"] == 20.0
    assert payload["answer"]["grade"]["trainingEvidenceSource"] == (
        "trace_native+packet_measurement:qrs_ms"
    )
    assert {row["caseId"] for row in campaigns.all_slots(campaign_id)} == roster_before

    replay = client.post(
        f"/training/campaigns/{campaign_id}/submit",
        headers={"Authorization": learner},
        json={
            **body,
            "selectedAnswer": "absent" if body["selectedAnswer"] == "present" else "present",
            "subskillTaskValue": task["minValue"],
        },
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["replay"] is True
    assert replay.json()["answer"] == payload["answer"]
    assert {row["caseId"] for row in campaigns.all_slots(campaign_id)} == roster_before


def test_qt_measurement_handoff_keeps_qtc_classification_and_credits_raw_qt(
    tmp_path, monkeypatch
):
    original_build_plan = training_routes_module._build_plan

    def transfer_first(*args, **kwargs):
        plan = original_build_plan(*args, **kwargs)
        transfer_index = next(
            index for index, row in enumerate(plan) if row["phase"] == "transfer"
        )
        plan[0]["phase"], plan[transfer_index]["phase"] = (
            plan[transfer_index]["phase"],
            plan[0]["phase"],
        )
        return plan

    monkeypatch.setattr(training_routes_module, "_build_plan", transfer_first)
    cases = _qt_cases()
    client, learning, campaigns = _client(tmp_path, cases)

    direct = client.post(
        "/training/campaigns",
        headers={"Authorization": "qt-direct-unavailable"},
        json={
            "conceptId": "qt_interval",
            "subskill": "measure",
            "length": 5,
        },
    )
    assert direct.status_code == 409

    learner = "qt-proxy-measurement"
    started_response = client.post(
        "/training/campaigns",
        headers={"Authorization": learner},
        json={
            "conceptId": "qtc_prolongation",
            "subskill": "measure",
            "length": 5,
            "contextKey": "receiptConcept=qt_interval&returnTo=%2Flearn%2Frepolarization-safety",
        },
    )
    assert started_response.status_code == 200, started_response.text
    started = started_response.json()
    campaign_id = started["campaign"]["campaignId"]
    case_id = _pending_canonical(campaigns, campaign_id)
    slot = campaigns.get_slot_for_case(campaign_id, case_id)
    packet = next(case for case in cases if case["case_id"] == case_id)
    assert slot and slot["phase"] == "transfer"

    classification = started["current"]["classification"]
    task = started["current"]["task"]
    assert classification["presentLabel"] == "QTc ≥480 ms"
    assert classification["absentLabel"] == "QTc <480 ms"
    assert task["kind"] == "numeric_fill_in"
    assert task["responseLabel"] == "QT interval"
    assert "expectedValue" not in task
    assert "qtc_ms" not in json.dumps(task, sort_keys=True)
    assert started["current"]["questionSnapshot"] == {
        "version": "focused-question-v1",
        "classification": classification,
        "task": task,
    }

    qt_ms = float(packet["ptbxl_plus"]["measurements"]["qt_ms"])
    expected_classification = (
        "present"
        if float(packet["ptbxl_plus"]["measurements"]["qtc_ms"]) >= 480
        else "absent"
    )
    submitted = client.post(
        f"/training/campaigns/{campaign_id}/submit",
        headers={"Authorization": learner},
        json={
            "caseId": started["current"]["case"]["caseId"],
            "selectedAnswer": expected_classification,
            "viewerTaskEvidence": {
                "mode": "caliper",
                "lead": "II",
                "timeStartSec": 0.50,
                "timeEndSec": 0.88,
                "valueMs": qt_ms,
            },
            "subskillTaskValue": qt_ms,
            "receiptConcept": "qt_interval",
        },
    )
    assert submitted.status_code == 200, submitted.text
    answer = submitted.json()["answer"]
    task_result = answer["grade"]["trainingSubskillTaskResult"]
    assert answer["summary"]["classificationCorrect"] is True
    assert answer["summary"]["correct"] is True
    assert answer["response"]["questionSnapshot"]["classification"] == classification
    assert answer["response"]["questionSnapshot"]["task"] == task
    assert task_result["expectedValue"] == qt_ms
    assert task_result["correct"] is True
    assert answer["grade"]["trainingEvidenceSource"] == (
        "trace_native+packet_measurement:qt_ms"
    )
    assert answer["receipt"]["effectiveEvidenceLevel"] == "independent_transfer"
    profile_row = next(
        row
        for row in learning.get_profile(learner)["subskillMastery"]
        if row["concept"] == "qt_interval" and row["subskill"] == "measure"
    )
    assert profile_row["independentAttempts"] == 1
    assert profile_row["distinctSuccessfulEcgs"] == 1


def test_numeric_measurement_transfer_advances_independent_mastery_and_retention(tmp_path):
    cases = _cases()
    for case in cases:
        if case["source"] == "fixture":
            continue
        if "qrs_duration" not in case["supported_objectives"]:
            case["supported_objectives"].append("qrs_duration")
        case["ptbxl_plus"]["measurements"]["qrs_ms"] = 140.0
        case["concept_confidence"]["qrs_duration"] = {
            "tier": "A", "score": 0.95, "evidence": [], "warnings": [],
        }
    client, learning, campaigns = _client(tmp_path, cases)
    learner = "numeric-transfer"
    started_response = client.post(
        "/training/campaigns",
        headers={"Authorization": learner},
        json={"conceptId": "qrs_duration", "subskill": "measure", "length": 10},
    )
    assert started_response.status_code == 200, started_response.text
    current = started_response.json()
    campaign_id = current["campaign"]["campaignId"]

    while True:
        case_id = _pending_canonical(campaigns, campaign_id)
        slot = campaigns.get_slot_for_case(campaign_id, case_id)
        assert slot
        if slot["phase"] == "transfer":
            break
        submitted = client.post(
            f"/training/campaigns/{campaign_id}/submit",
            headers={"Authorization": learner},
            json={
                "caseId": current["current"]["case"]["caseId"],
                "selectedAnswer": "present" if slot["targetPresent"] else "absent",
                "confidence": 3,
            },
        )
        assert submitted.status_code == 200, submitted.text
        current = client.post(
            f"/training/campaigns/{campaign_id}/next",
            headers={"Authorization": learner},
        ).json()

    canonical_case_id = _pending_canonical(campaigns, campaign_id)
    packet = next(case for case in cases if case["case_id"] == canonical_case_id)
    expected = float(packet["ptbxl_plus"]["measurements"]["qrs_ms"])
    response = client.post(
        f"/training/campaigns/{campaign_id}/submit",
        headers={"Authorization": learner},
        json={
            "caseId": current["current"]["case"]["caseId"],
            "selectedAnswer": "present",
            "confidence": 4,
            "viewerTaskEvidence": {
                "mode": "caliper",
                "lead": "V1",
                "timeStartSec": 0.30,
                "timeEndSec": 0.44,
                "valueMs": expected,
            },
            "subskillTaskValue": expected,
            "receiptConcept": "qrs_duration",
        },
    )
    assert response.status_code == 200, response.text
    answer = response.json()["answer"]
    assert answer["grade"]["trainingEvidenceSource"] == (
        "trace_native+packet_measurement:qrs_ms"
    )
    assert answer["receipt"]["effectiveEvidenceLevel"] == "independent_transfer"
    receipt = answer["receipt"]["receipts"][0]
    assert receipt["retentionEligible"] is True
    assert receipt["distinctSuccessfulEcgs"] == 1
    row = next(
        item for item in learning.get_profile(learner)["subskillMastery"]
        if item["concept"] == "qrs_duration" and item["subskill"] == "measure"
    )
    assert row["independentAttempts"] == 1
    assert row["distinctEligibleEcgs"] == 1
    assert row["nextDueAt"] is not None


def test_synthesis_framework_is_consistent_and_durable_postcommit(tmp_path):
    client, _, campaigns = _client(tmp_path)
    learner = "grounded-matching"
    started = client.post(
        "/training/campaigns",
        headers={"Authorization": learner},
        json={
            "conceptId": "right_bundle_branch_block",
            "subskill": "synthesize",
            "length": 10,
        },
    ).json()
    campaign_id = started["campaign"]["campaignId"]
    roster_before = {row["caseId"] for row in campaigns.all_slots(campaign_id)}

    first_case_ref = started["current"]["case"]["caseId"]
    first_case_id = _pending_canonical(campaigns, campaign_id)
    first_slot = campaigns.get_slot_for_case(campaign_id, first_case_id)
    first_packet = next(case for case in _cases() if case["case_id"] == first_case_id)
    first_contract = build_subskill_task(
        case_id=first_case_id,
        case_concept="right_bundle_branch_block",
        subskill="synthesize",
        case_focus=first_slot["caseFocus"],
        contrast_family=_contrast_family("right_bundle_branch_block"),
        variant=int(first_slot["position"]),
        case_packet=first_packet,
    )
    assert first_contract and first_contract.public["kind"] == "single_choice"
    assert first_contract.public["frameworkVersion"] == (
        "focused-systematic-interpretation-v1"
    )
    assert [row["key"] for row in first_contract.public["frameworkSteps"]] == list(
        SYSTEMATIC_INTERPRETATION
    )
    assert "correctAnswer" not in json.dumps(first_contract.public)
    first_submit = client.post(
        f"/training/campaigns/{campaign_id}/submit",
        headers={"Authorization": learner},
        json={
            "caseId": first_case_ref,
            "selectedAnswer": "present" if first_slot["targetPresent"] else "absent",
            "confidence": 4,
            "subskillTaskAnswer": first_contract.correct_answer,
            "structuredInterpretation": SYSTEMATIC_INTERPRETATION,
        },
    )
    assert first_submit.status_code == 200, first_submit.text
    pending = client.post(
        f"/training/campaigns/{campaign_id}/next",
        headers={"Authorization": learner},
    ).json()
    case_ref = pending["current"]["case"]["caseId"]
    case_id = _pending_canonical(campaigns, campaign_id)
    slot = campaigns.get_slot_for_case(campaign_id, case_id)
    packet = next(case for case in _cases() if case["case_id"] == case_id)
    task = pending["current"]["task"]
    assert task["kind"] == "single_choice"
    assert task["frameworkVersion"] == "focused-systematic-interpretation-v1"
    assert [row["key"] for row in task["frameworkSteps"]] == list(
        SYSTEMATIC_INTERPRETATION
    )
    assert "caseFocus" not in pending["current"]["slot"]
    public_text = json.dumps(task, sort_keys=True).casefold()
    assert "right bundle branch block" not in public_text
    assert "left bundle branch block" not in public_text
    assert "correctchoice" not in public_text
    assert "supportedobjective" not in public_text

    contract = build_subskill_task(
        case_id=case_id,
        case_concept="right_bundle_branch_block",
        subskill="synthesize",
        case_focus=slot["caseFocus"],
        contrast_family=_contrast_family("right_bundle_branch_block"),
        variant=int(slot["position"]),
        case_packet=packet,
    )
    assert contract and contract.public == task and contract.correct_answer
    body = {
        "caseId": case_ref,
        "selectedAnswer": "present" if slot["targetPresent"] else "absent",
        "confidence": 4,
        "subskillTaskAnswer": contract.correct_answer,
        "structuredInterpretation": SYSTEMATIC_INTERPRETATION,
    }
    submitted = client.post(
        f"/training/campaigns/{campaign_id}/submit",
        headers={"Authorization": learner},
        json=body,
    )
    assert submitted.status_code == 200, submitted.text
    payload = submitted.json()
    result = payload["answer"]["grade"]["trainingSubskillTaskResult"]
    assert payload["replay"] is False
    assert payload["answer"]["integrityStatus"] == "atomic_v2"
    assert payload["answer"]["response"]["subskillTaskAnswer"] == (
        contract.correct_answer
    )
    assert payload["answer"]["response"]["structuredInterpretation"] == (
        SYSTEMATIC_INTERPRETATION
    )
    assert payload["answer"]["response"]["questionSnapshot"]["task"][
        "frameworkVersion"
    ] == "focused-systematic-interpretation-v1"
    assert result["kind"] == "single_choice"
    assert result["complete"] is True and result["correct"] is True
    assert result["systematicInterpretationComplete"] is True
    assert result["systematicInterpretation"] == SYSTEMATIC_INTERPRETATION
    assert [row["key"] for row in result["reviewedFramework"]] == list(
        SYSTEMATIC_INTERPRETATION
    )
    assert all(set(row) == {"key", "label", "review", "grounded"} for row in result["reviewedFramework"])
    assert any(row["grounded"] for row in result["reviewedFramework"])
    assert any(not row["grounded"] for row in result["reviewedFramework"])
    assert all(
        row["review"].startswith("Reviewed ECG data:")
        if row["grounded"]
        else row["review"].startswith(
            "This ECG record does not independently verify this domain"
        )
        for row in result["reviewedFramework"]
    )
    assert {row["caseId"] for row in campaigns.all_slots(campaign_id)} == roster_before

    replay = client.post(
        f"/training/campaigns/{campaign_id}/submit",
        headers={"Authorization": learner},
        json={**body, "subskillTaskAnswer": ""},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["replay"] is True
    assert replay.json()["answer"] == payload["answer"]
    assert {row["caseId"] for row in campaigns.all_slots(campaign_id)} == roster_before


def test_measurement_without_numeric_ground_truth_is_not_advertised_or_started(tmp_path):
    cases = _cases()
    for index, case in enumerate(cases):
        if case["source"] == "fixture":
            continue
        supported = ["left_axis_deviation"] if index < 3 else ["axis_normal"]
        case["supported_objectives"] = supported
        case["concept_confidence"] = {
            concept: {"tier": "A", "score": 0.95, "evidence": [], "warnings": []}
            for concept in supported
        }
    learner = "measurement-without-ground-truth"
    client, learning, _ = _client(tmp_path, cases)
    pool = client.get(
        "/training/campaigns/pool",
        headers={"Authorization": learner},
        params={"conceptId": "left_axis_deviation", "subskill": "measure"},
    )
    assert pool.status_code == 200, pool.text
    assert pool.json()["eligibleDistinct"] == 0
    assert pool.json()["independentReceiptsAvailable"] is False

    started = client.post(
        "/training/campaigns",
        headers={"Authorization": learner},
        json={"conceptId": "left_axis_deviation", "subskill": "measure", "length": 10},
    )
    assert started.status_code == 409, started.text
    assert started.json()["detail"] == (
        "No eligible distinct audited waveform ECGs support this competency"
    )

    with learning.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM learner_profiles WHERE learner_id = ?", (learner,)
        ).fetchone()["n"] == 0
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM attempts WHERE learner_id = ?", (learner,)
        ).fetchone()["n"] == 0
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM subskill_mastery WHERE learner_id = ?", (learner,)
        ).fetchone()["n"] == 0


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
    canonical_case_id = _pending_canonical(campaigns, campaign_id)
    private_slot = campaigns.get_slot_for_case(campaign_id, canonical_case_id)
    assert private_slot is not None

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
        "selectedAnswer": "present" if private_slot["targetPresent"] else "absent",
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
    assert first_body["summary"]["classificationCorrect"] == 1
    assert first_body["summary"]["fullTaskCorrect"] == 1

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
    case_ref = pending["current"]["case"]["caseId"]
    case_id = _pending_canonical(campaigns, campaign_id)
    slot = campaigns.get_slot_for_case(campaign_id, case_id)
    contract = build_subskill_task(
        case_id=case_id,
        case_concept="right_bundle_branch_block",
        subskill="discriminate",
        case_focus=slot["caseFocus"],
        contrast_family=_contrast_family("right_bundle_branch_block"),
        variant=int(slot["position"]),
    )
    response = client.post(
        f"/training/campaigns/{campaign_id}/submit",
        headers={"Authorization": "discriminator"},
        json={
            "caseId": case_ref,
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
    case_ref = pending["current"]["case"]["caseId"]
    case_id = _pending_canonical(campaigns, campaign_id)
    slot = campaigns.get_slot_for_case(campaign_id, case_id)
    contract = build_subskill_task(
        case_id=case_id,
        case_concept="right_bundle_branch_block",
        subskill="explain_mechanism",
        case_focus=slot["caseFocus"],
        contrast_family=_contrast_family("right_bundle_branch_block"),
        variant=int(slot["position"]),
    )
    wrong = next(
        option["id"] for option in pending["current"]["task"]["options"]
        if option["id"] != contract.correct_answer
    )
    response = client.post(
        f"/training/campaigns/{campaign_id}/submit",
        headers={"Authorization": "mechanism"},
        json={
            "caseId": case_ref,
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


def test_mechanism_is_scored_separately_from_a_wrong_pattern_decision(tmp_path):
    client, learning, campaigns = _client(tmp_path)
    campaign_id, pending = _reach_transfer(
        client, campaigns, learner="mechanism-separate-axis", subskill="explain_mechanism"
    )
    case_ref = pending["current"]["case"]["caseId"]
    case_id = _pending_canonical(campaigns, campaign_id)
    slot = campaigns.get_slot_for_case(campaign_id, case_id)
    contract = build_subskill_task(
        case_id=case_id,
        case_concept="right_bundle_branch_block",
        subskill="explain_mechanism",
        case_focus=slot["caseFocus"],
        contrast_family=_contrast_family("right_bundle_branch_block"),
        variant=int(slot["position"]),
    )
    response = client.post(
        f"/training/campaigns/{campaign_id}/submit",
        headers={"Authorization": "mechanism-separate-axis"},
        json={
            "caseId": case_ref,
            "selectedAnswer": "absent" if slot["targetPresent"] else "present",
            "confidence": 4,
            "subskillTaskAnswer": contract.correct_answer,
            "receiptConcept": "right_bundle_branch_block",
        },
    )
    assert response.status_code == 200, response.text
    answer = response.json()["answer"]
    assert answer["summary"]["classificationCorrect"] is False
    assert answer["summary"]["correct"] is True
    assert answer["grade"]["trainingSubskillEvidenceCorrect"] is True
    assert "target_status_error:right_bundle_branch_block" in answer["summary"]["misconceptions"]
    row = next(
        item for item in learning.get_profile("mechanism-separate-axis")["subskillMastery"]
        if item["concept"] == "right_bundle_branch_block"
        and item["subskill"] == "explain_mechanism"
    )
    assert row["independentAttempts"] == 1
    assert row["correct"] >= 1


def test_synthesis_requires_all_eight_bounded_interpretation_steps(tmp_path):
    client, _, campaigns = _client(tmp_path)
    learner = "synthesis-systematic-required"
    started = client.post(
        "/training/campaigns",
        headers={"Authorization": learner},
        json={
            "conceptId": "right_bundle_branch_block",
            "subskill": "synthesize",
            "length": 10,
        },
    ).json()
    campaign_id = started["campaign"]["campaignId"]
    case_ref = started["current"]["case"]["caseId"]
    case_id = _pending_canonical(campaigns, campaign_id)
    slot = campaigns.get_slot_for_case(campaign_id, case_id)
    contract = build_subskill_task(
        case_id=case_id,
        case_concept="right_bundle_branch_block",
        subskill="synthesize",
        case_focus=slot["caseFocus"],
        contrast_family=_contrast_family("right_bundle_branch_block"),
        variant=int(slot["position"]),
    )
    base = {
        "caseId": case_ref,
        "selectedAnswer": "present" if slot["targetPresent"] else "absent",
        "subskillTaskAnswer": contract.correct_answer,
    }

    missing = client.post(
        f"/training/campaigns/{campaign_id}/submit",
        headers={"Authorization": learner},
        json=base,
    )
    assert missing.status_code == 422, missing.text
    assert missing.json()["detail"] == {
        "code": "training_systematic_interpretation_required",
        "message": (
            "Complete all eight interpretation steps and provide a final "
            "synthesis of at least 12 characters before checking this task."
        ),
        "missingFields": list(SYSTEMATIC_INTERPRETATION),
    }
    assert campaigns.get_answer(campaign_id, case_id) is None
    assert campaigns.get_campaign(campaign_id)["pendingCaseId"] == case_id

    short_synthesis = client.post(
        f"/training/campaigns/{campaign_id}/submit",
        headers={"Authorization": learner},
        json={
            **base,
            "structuredInterpretation": {
                **SYSTEMATIC_INTERPRETATION,
                "synthesis": "too short",
            },
        },
    )
    assert short_synthesis.status_code == 422, short_synthesis.text
    assert short_synthesis.json()["detail"]["missingFields"] == ["synthesis"]
    assert campaigns.get_answer(campaign_id, case_id) is None


def test_synthesis_requires_the_server_owned_choice_not_a_long_nonsense_note(tmp_path):
    client, _, campaigns = _client(tmp_path)
    started = client.post(
        "/training/campaigns",
        headers={"Authorization": "synthesis-nonsense"},
        json={
            "conceptId": "right_bundle_branch_block",
            "subskill": "synthesize",
            "length": 10,
        },
    ).json()
    campaign_id = started["campaign"]["campaignId"]
    case_ref = started["current"]["case"]["caseId"]
    case_id = _pending_canonical(campaigns, campaign_id)
    slot = campaigns.get_slot_for_case(campaign_id, case_id)
    contract = build_subskill_task(
        case_id=case_id,
        case_concept="right_bundle_branch_block",
        subskill="synthesize",
        case_focus=slot["caseFocus"],
        contrast_family=_contrast_family("right_bundle_branch_block"),
        variant=int(slot["position"]),
    )
    wrong = next(
        option["id"] for option in started["current"]["task"]["options"]
        if option["id"] != contract.correct_answer
    )
    response = client.post(
        f"/training/campaigns/{campaign_id}/submit",
        headers={"Authorization": "synthesis-nonsense"},
        json={
            "caseId": case_ref,
            "selectedAnswer": "present" if slot["targetPresent"] else "absent",
            "confidence": 4,
            "evidenceNote": "Nonsense filler is deliberately longer than twenty characters and must never be graded semantically.",
            "subskillTaskAnswer": wrong,
            "structuredInterpretation": SYSTEMATIC_INTERPRETATION,
        },
    )
    assert response.status_code == 200, response.text
    answer = response.json()["answer"]
    assert answer["summary"]["classificationCorrect"] is True
    assert answer["summary"]["correct"] is False
    assert answer["grade"]["trainingSubskillEvidenceCorrect"] is False
    assert answer["grade"]["trainingEvidenceSource"] == "curated_synthesis_task"


def test_structured_synthesis_transfer_remains_formative(tmp_path):
    client, learning, campaigns = _client(tmp_path)
    campaign_id, pending = _reach_transfer(
        client, campaigns, learner="synthesis-transfer", subskill="synthesize"
    )
    case_ref = pending["current"]["case"]["caseId"]
    case_id = _pending_canonical(campaigns, campaign_id)
    slot = campaigns.get_slot_for_case(campaign_id, case_id)
    case_packet = next(case for case in _cases() if case["case_id"] == case_id)
    contract = build_subskill_task(
        case_id=case_id,
        case_concept="right_bundle_branch_block",
        subskill="synthesize",
        case_focus=slot["caseFocus"],
        contrast_family=_contrast_family("right_bundle_branch_block"),
        variant=int(slot["position"]),
        case_packet=case_packet,
    )
    task_response = (
        {"subskillTaskMatches": contract.correct_matches}
        if contract.public["kind"] == "matching"
        else {"subskillTaskAnswer": contract.correct_answer}
    )
    response = client.post(
        f"/training/campaigns/{campaign_id}/submit",
        headers={"Authorization": "synthesis-transfer"},
        json={
            "caseId": case_ref,
            "selectedAnswer": "present" if slot["targetPresent"] else "absent",
            "confidence": 4,
            "structuredInterpretation": SYSTEMATIC_INTERPRETATION,
            **task_response,
        },
    )
    assert response.status_code == 200, response.text
    answer = response.json()["answer"]
    assert answer["summary"]["correct"] is True
    assert answer["receipt"]["requestedEvidenceLevel"] == "guided"
    assert answer["receipt"]["effectiveEvidenceLevel"] == "guided"
    row = next(
        item for item in learning.get_profile("synthesis-transfer")["subskillMastery"]
        if item["concept"] == "right_bundle_branch_block"
        and item["subskill"] == "synthesize"
    )
    assert row["attempts"] >= 1
    assert row["independentAttempts"] == 0
    assert row["distinctSuccessfulEcgs"] == 0


def test_apply_in_context_uses_a_formative_structured_boundary_task(tmp_path):
    client, learning, campaigns = _client(tmp_path)
    started = client.post(
        "/training/campaigns",
        headers={"Authorization": "context-boundary"},
        json={
            "conceptId": "right_bundle_branch_block",
            "subskill": "apply_in_context",
            "length": 10,
        },
    ).json()
    campaign_id = started["campaign"]["campaignId"]
    case_ref = started["current"]["case"]["caseId"]
    case_id = _pending_canonical(campaigns, campaign_id)
    slot = campaigns.get_slot_for_case(campaign_id, case_id)
    contract = build_subskill_task(
        case_id=case_id,
        case_concept="right_bundle_branch_block",
        subskill="apply_in_context",
        case_focus=slot["caseFocus"],
        contrast_family=_contrast_family("right_bundle_branch_block"),
        variant=int(slot["position"]),
    )
    response = client.post(
        f"/training/campaigns/{campaign_id}/submit",
        headers={"Authorization": "context-boundary"},
        json={
            "caseId": case_ref,
            "selectedAnswer": "present" if slot["targetPresent"] else "absent",
            "confidence": 4,
            "subskillTaskAnswer": contract.correct_answer,
        },
    )
    assert response.status_code == 200, response.text
    answer = response.json()["answer"]
    assert answer["summary"]["correct"] is True
    assert answer["grade"]["trainingEvidenceSource"] == "curated_context_boundary_task"
    assert answer["receipt"]["effectiveEvidenceLevel"] == "guided"
    row = next(
        item for item in learning.get_profile("context-boundary")["subskillMastery"]
        if item["concept"] == "right_bundle_branch_block"
        and item["subskill"] == "apply_in_context"
    )
    assert row["attempts"] == 1
    assert row["independentAttempts"] == 0


def test_confidence_transfer_records_calibration_separately_from_recognition(tmp_path):
    client, learning, campaigns = _client(tmp_path)
    campaign_id, pending = _reach_transfer(
        client, campaigns, learner="calibrator", subskill="calibrate_confidence"
    )
    case_ref = pending["current"]["case"]["caseId"]
    case_id = _pending_canonical(campaigns, campaign_id)
    slot = campaigns.get_slot_for_case(campaign_id, case_id)
    # A deliberately low-confidence miss is a calibrated confidence outcome,
    # while the separate classificationCorrect flag remains false.
    response = client.post(
        f"/training/campaigns/{campaign_id}/submit",
        headers={"Authorization": "calibrator"},
        json={
            "caseId": case_ref,
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


def test_non_calibration_training_does_not_invent_confidence(tmp_path):
    client, learning, campaigns = _client(tmp_path)
    learner = "no-hidden-confidence"
    started = client.post(
        "/training/campaigns",
        headers={"Authorization": learner},
        json={
            "conceptId": "right_bundle_branch_block",
            "subskill": "recognize",
            "length": 5,
        },
    ).json()
    campaign_id = started["campaign"]["campaignId"]
    canonical_id = _pending_canonical(campaigns, campaign_id)
    slot = campaigns.get_slot_for_case(campaign_id, canonical_id)
    assert slot

    submitted = client.post(
        f"/training/campaigns/{campaign_id}/submit",
        headers={"Authorization": learner},
        json={
            "caseId": started["current"]["case"]["caseId"],
            "selectedAnswer": "present" if slot["targetPresent"] else "absent",
            # Even an old client value is ignored outside calibration work.
            "confidence": 5,
        },
    )
    assert submitted.status_code == 200, submitted.text
    answer = submitted.json()["answer"]
    assert answer["response"]["confidence"] is None
    assert answer["summary"]["confidence"] is None
    with learning.connect() as conn:
        attempt = conn.execute(
            "SELECT confidence FROM attempts WHERE learner_id = ? ORDER BY id DESC LIMIT 1",
            (learner,),
        ).fetchone()
        event = conn.execute(
            "SELECT confidence FROM guided_learning_events WHERE learner_id = ? "
            "AND module_id = 'train' ORDER BY id DESC LIMIT 1",
            (learner,),
        ).fetchone()
    # The immutable attempts table uses 0 as its established omitted sentinel;
    # guided receipts are nullable and retain a real null.
    assert attempt["confidence"] == 0
    assert event["confidence"] is None


def test_completed_campaign_is_immutable_and_new_start_preserves_history(tmp_path):
    cases = _cases()
    for index, source in enumerate(
        [case for case in cases if case["source"] != "fixture"]
    ):
        duplicate = deepcopy(source)
        duplicate["case_id"] = str(8000 + index)
        duplicate["display_id"] = f"PTB-XL {8000 + index}"
        cases.append(duplicate)
    client, learning, campaigns = _client(tmp_path, cases)
    learner = "completed-history-owner"
    current = client.post(
        "/training/campaigns",
        headers={"Authorization": learner},
        json={
            "conceptId": "right_bundle_branch_block",
            "subskill": "recognize",
            "length": 5,
        },
    ).json()
    campaign_id = current["campaign"]["campaignId"]

    while current["campaign"]["status"] != "complete":
        canonical_id = _pending_canonical(campaigns, campaign_id)
        slot = campaigns.get_slot_for_case(campaign_id, canonical_id)
        assert slot
        submitted = client.post(
            f"/training/campaigns/{campaign_id}/submit",
            headers={"Authorization": learner},
            json={
                "caseId": current["current"]["case"]["caseId"],
                "selectedAnswer": "present" if slot["targetPresent"] else "absent",
            },
        )
        assert submitted.status_code == 200, submitted.text
        current = submitted.json()
        if current["campaign"]["status"] != "complete":
            current = client.post(
                f"/training/campaigns/{campaign_id}/next",
                headers={"Authorization": learner},
            ).json()

    abandoned = client.post(
        f"/training/campaigns/{campaign_id}/abandon",
        headers={"Authorization": learner},
    )
    assert abandoned.status_code == 200, abandoned.text
    assert abandoned.json()["campaign"]["status"] == "complete"

    replacement = client.post(
        "/training/campaigns",
        headers={"Authorization": learner},
        json={
            "conceptId": "right_bundle_branch_block",
            "subskill": "recognize",
            "length": 5,
            "replaceActive": True,
        },
    )
    assert replacement.status_code == 200, replacement.text
    assert replacement.json()["campaign"]["campaignId"] != campaign_id

    preserved = campaigns.get_campaign(campaign_id)
    assert preserved and preserved["status"] == "complete"
    assert preserved["feedbackCaseId"] is None
    with learning.connect() as conn:
        saved = conn.execute(
            "SELECT status, COUNT(*) AS answer_count FROM training_campaigns "
            "JOIN training_campaign_answers USING (campaign_id) "
            "WHERE training_campaigns.campaign_id = ? GROUP BY status",
            (campaign_id,),
        ).fetchone()
    assert tuple(saved) == ("complete", 5)
