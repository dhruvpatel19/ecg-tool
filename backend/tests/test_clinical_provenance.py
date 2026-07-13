"""Learner Clinical serving is real-ECG-only and fails closed at both gates."""

from __future__ import annotations

from collections import Counter
import re

import pytest
from fastapi.testclient import TestClient

from app.clinical import shift
from app.clinical.fixture_items import FIXTURE_ITEMS, FIXTURE_PACKETS
from app.clinical.provenance import (
    LEARNER_CLINICAL_SOURCES,
    assert_learner_item_provenance,
    assert_serving_bank_provenance,
)
from app.clinical.harness import run_harness
from app.clinical.real_items import (
    APPLICATION_OBJECTIVES_BY_SCENARIO,
    AUTHORED_VARIANTS_BY_SCENARIO,
    CLINICAL_FAMILY_BY_SCENARIO,
    MINIMUM_CLINICAL_BANK_SIZE,
    REAL_ECGS_BY_SCENARIO,
    _OLD_NEUTRAL_CLONE_MARKERS,
    normalized_scenario_signature,
)
from app.clinical.seed_items import CASE_T as SYNTHETIC_WCT_TEMPLATE
from app.main import app, clinical_item_store, clinical_packet
from app.objectives import (
    CLINICAL_APPLICATION_CONCEPTS,
    CLINICAL_LOCALIZATION_CONCEPTS,
    OBJECTIVES,
)
from app.ontology import CONCEPT_BY_ID

client = TestClient(app)


def test_every_serving_item_resolves_to_an_allowed_real_packet() -> None:
    served = list(clinical_item_store.list_for_serving(status="harness_pass"))
    assert len(served) >= MINIMUM_CLINICAL_BANK_SIZE
    assert len({item.ecg_id for item in served}) == len(served)
    assert len({item.item_id for item in served}) == len(served)
    assert len({ecg_id for ids in REAL_ECGS_BY_SCENARIO.values() for ecg_id in ids}) == sum(
        len(ids) for ids in REAL_ECGS_BY_SCENARIO.values()
    )
    question_types = {item.question_type for item in served}
    assert {"click", "spoterror", "triage", "stepwise", "mcq"} <= question_types
    for item in served:
        packet = assert_learner_item_provenance(item, clinical_packet)
        assert packet["source"] in LEARNER_CLINICAL_SOURCES
        assert packet["source"] == "ptbxl"
        assert packet["case_id"] == item.ecg_id
        assert not item.ecg_id.startswith(("seed-", "fixture-"))
        assert item.question_type != "oldnew"
        assert "wide_complex_tachycardia" not in {
            claim.objective_id for claim in item.evidence_manifest.ecg_supports
        }


def test_interaction_mix_is_balanced_and_trace_native() -> None:
    served = list(clinical_item_store.list_for_serving(status="harness_pass"))
    counts = Counter(item.question_type for item in served)
    assert max(counts.values()) / len(served) <= 0.5
    trace_native = sum(counts[kind] for kind in ("click", "spoterror", "stepwise"))
    assert trace_native / len(served) >= 0.30


def test_hundred_case_bank_preserves_lane_and_interaction_diversity() -> None:
    served = list(clinical_item_store.list_for_serving(status="harness_pass"))
    lanes = Counter(item.situation for item in served)
    types = Counter(item.question_type for item in served)

    assert set(lanes) == {"clinic", "ward", "ed"}
    assert min(lanes.values()) >= 30
    assert max(lanes.values()) - min(lanes.values()) <= 1
    assert {"click", "spoterror", "triage", "stepwise", "mcq"} <= set(types)
    assert max(types.values()) / len(served) <= 0.25


def test_hundred_real_ecgs_have_hundred_genuinely_distinct_authored_signatures() -> None:
    served = list(clinical_item_store.list_for_serving(status="harness_pass"))
    signatures = {normalized_scenario_signature(item) for item in served}

    assert len(served) >= MINIMUM_CLINICAL_BANK_SIZE
    assert len({item.ecg_id for item in served}) == len(served)
    assert len(signatures) == len(served)
    assert len(signatures) >= MINIMUM_CLINICAL_BANK_SIZE
    assert set(AUTHORED_VARIANTS_BY_SCENARIO) == set(REAL_ECGS_BY_SCENARIO)
    assert all(
        len(AUTHORED_VARIANTS_BY_SCENARIO[scenario_id]) == len(ecg_ids)
        for scenario_id, ecg_ids in REAL_ECGS_BY_SCENARIO.items()
    )
    for item in served:
        text = f"{item.stem} {item.prompt}".casefold()
        assert not any(marker in text for marker in _OLD_NEUTRAL_CLONE_MARKERS)


def test_authored_bank_has_declared_clinical_family_breadth_and_all_items_repass_harness() -> None:
    served = list(clinical_item_store.list_for_serving(status="harness_pass"))
    family_ids = set(CLINICAL_FAMILY_BY_SCENARIO.values())
    assert {
        "chest_discomfort_claim_boundary",
        "qt_drug_safety",
        "syncope_brady",
        "palpitations_rhythm",
        "conduction",
        "normal_mimic",
        "machine_audit",
        "chamber_voltage",
    } <= family_ids
    assert set(CLINICAL_FAMILY_BY_SCENARIO) == set(REAL_ECGS_BY_SCENARIO)
    for item in served:
        packet = assert_learner_item_provenance(item, clinical_packet)
        report = run_harness(item, packet, None)
        assert report.passed, f"{item.item_id}: {report.failing_checks()}"


def test_clinical_competency_registry_exposes_only_declared_canonical_cells() -> None:
    declared_application = {
        objective
        for objectives in APPLICATION_OBJECTIVES_BY_SCENARIO.values()
        for objective in objectives
    }
    assert declared_application == set(CLINICAL_APPLICATION_CONCEPTS)
    exposed_application = {
        concept
        for concept in CONCEPT_BY_ID
        if "apply_in_context" in OBJECTIVES[concept].allowed_subskills
    }
    assert exposed_application == set(CLINICAL_APPLICATION_CONCEPTS)

    served = list(clinical_item_store.list_for_serving(status="harness_pass"))
    trace_localized = {
        item.roi_target.concept
        for item in served
        if item.question_type in {"click", "spoterror"} and item.roi_target is not None
    }
    assert trace_localized == set(CLINICAL_LOCALIZATION_CONCEPTS)
    assert all("localize" in OBJECTIVES[concept].allowed_subskills for concept in trace_localized)


def test_expanded_scenario_families_do_not_carry_exemplar_facts_to_other_ecgs() -> None:
    for item in clinical_item_store.list_for_serving(status="harness_pass"):
        packet = clinical_packet(item.ecg_id)
        assert packet is not None
        supported = set(packet.get("supported_objectives") or [])
        features = ((packet.get("ptbxl_plus") or {}).get("features") or {})

        truthful_machine_text = " ".join(
            line.text.casefold() for line in item.machine_read if not line.bad
        )
        if "sinus rhythm" in truthful_machine_text:
            assert "sinus_rhythm" in supported
        if "atrial fibrillation" in truthful_machine_text:
            assert "atrial_fibrillation" in supported

        objectives = {claim.objective_id for claim in item.evidence_manifest.ecg_supports}
        if "supraventricular_tachycardia" in objectives:
            assert float(features["qrs_ms"]) < 120
            assert "atrial_fibrillation" not in supported

        for step in item.steps:
            if "rate" not in step.prompt.casefold():
                continue
            correct = next(option for option in step.options if option.correct)
            displayed_rate = int(re.search(r"(\d+)\s*/min", correct.text).group(1))
            assert displayed_rate == round(float(features["heart_rate"]))


@pytest.mark.parametrize(
    ("lane", "required_objectives"),
    [
        ("clinic", {"normal_ecg", "bradycardia", "av_block_first_degree", "right_bundle_branch_block", "qtc_prolongation", "left_ventricular_hypertrophy"}),
        ("ward", {"atrial_fibrillation", "av_block_third_degree", "right_bundle_branch_block", "st_depression", "left_ventricular_hypertrophy"}),
        ("ed", {"supraventricular_tachycardia", "atrial_fibrillation", "av_block_third_degree", "bradycardia", "st_depression"}),
    ],
)
def test_each_lane_has_real_capacity_and_required_coverage(
    lane: str, required_objectives: set[str]
) -> None:
    items = clinical_item_store.list_for_serving(situation=lane, status="harness_pass")
    distinct_ecgs = {item.ecg_id for item in items}
    assert len(distinct_ecgs) >= 6
    objectives = {
        claim.objective_id
        for item in items
        for claim in item.evidence_manifest.ecg_supports
    }
    assert required_objectives <= objectives

    started = client.post(
        "/clinical/shift/start",
        json={"lane": lane, "tier": "learn", "length": 50},
    )
    assert started.status_code == 200
    body = started.json()
    assert body["session"]["availableDistinctEcgs"] == len(distinct_ecgs)
    assert body["session"]["length"] == len(distinct_ecgs)
    assert body["next"]["item"]["situation"] == lane
    assert body["next"]["item"]["tracing_provenance"] == "real_deidentified_ecg"


def test_startup_bank_assertion_rejects_harness_passed_fixture() -> None:
    synthetic = FIXTURE_ITEMS[0].model_copy(
        deep=True, update={"validation_status": "harness_pass"}
    )
    provider = lambda ecg_id: FIXTURE_PACKETS.get(ecg_id)
    with pytest.raises(RuntimeError, match="synthetic identifier"):
        assert_serving_bank_provenance([synthetic], provider)


def test_runtime_payload_assertion_rejects_fixture_even_if_injected() -> None:
    synthetic = FIXTURE_ITEMS[0].model_copy(
        deep=True, update={"validation_status": "harness_pass"}
    )
    session = {
        "contextRevealed": False,
        "position": 0,
        "length": 1,
        "tier": "learn",
    }
    provider = lambda ecg_id: FIXTURE_PACKETS.get(ecg_id)
    with pytest.raises(RuntimeError, match="synthetic identifier"):
        shift._serve_payload(synthetic, provider, session)


def test_oldnew_and_wct_remain_locked_without_authentic_sources() -> None:
    oldnew = next(item for item in FIXTURE_ITEMS if item.question_type == "oldnew").model_copy(
        deep=True,
        update={
            "item_id": "ptb-longitudinal-unverified",
            "ecg_id": "195",
            "prior_ecg_id": "195",
            "validation_status": "harness_pass",
        },
    )
    with pytest.raises(RuntimeError, match="old/new"):
        assert_learner_item_provenance(oldnew, clinical_packet)

    wct = SYNTHETIC_WCT_TEMPLATE.model_copy(
        deep=True,
        update={
            "item_id": "ptb-wct-unverified",
            "ecg_id": "1919",
            "validation_status": "harness_pass",
        },
    )
    with pytest.raises(RuntimeError, match="locked objective"):
        assert_learner_item_provenance(wct, clinical_packet)
