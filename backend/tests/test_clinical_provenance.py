"""Learner Clinical serving is real-ECG-only and fails closed at both gates."""

from __future__ import annotations

from collections import Counter
import re
import uuid

import pytest
from fastapi.testclient import TestClient

from app.clinical import shift
from app.clinical.fixture_items import FIXTURE_ITEMS, FIXTURE_PACKETS
from app.clinical.provenance import (
    LEARNER_CLINICAL_SOURCES,
    assert_longitudinal_pair_provenance,
    assert_learner_item_provenance,
    assert_serving_bank_provenance,
)
from app.clinical.harness import run_harness
from app.clinical.real_items import (
    APPLICATION_OBJECTIVES_BY_SCENARIO,
    AUTHORED_VARIANTS_BY_SCENARIO,
    CLINICAL_FAMILY_BY_SCENARIO,
    MATCHING_ORDINALS_BY_SCENARIO,
    MINIMUM_CLINICAL_BANK_SIZE,
    LONGITUDINAL_APPLICATION_OBJECTIVES_BY_CURRENT,
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
from app.subskill_tasks import training_independent_receipt_available

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
    assert {"click", "spoterror", "fillin", "matching", "triage", "stepwise", "mcq"} <= question_types
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
    trace_native = sum(counts[kind] for kind in ("click", "spoterror", "fillin", "stepwise"))
    assert trace_native / len(served) >= 0.30


def test_hundred_case_bank_preserves_lane_and_interaction_diversity() -> None:
    served = list(clinical_item_store.list_for_serving(status="harness_pass"))
    lanes = Counter(item.situation for item in served)
    types = Counter(item.question_type for item in served)

    assert set(lanes) == {"clinic", "ward", "ed"}
    assert min(lanes.values()) >= 30
    assert max(lanes.values()) - min(lanes.values()) <= 1
    assert {"click", "spoterror", "fillin", "matching", "triage", "stepwise", "mcq"} <= set(types)
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


def test_matching_bank_uses_twelve_distinct_real_ecgs_with_varied_accessible_order() -> None:
    served = list(clinical_item_store.list_for_serving(status="harness_pass"))
    matching = [item for item in served if item.question_type == "matching"]

    assert sum(len(ordinals) for ordinals in MATCHING_ORDINALS_BY_SCENARIO.values()) == 12
    assert len(matching) == 12
    assert Counter(item.situation for item in matching) == {"clinic": 4, "ward": 4, "ed": 4}
    assert len({item.ecg_id for item in matching}) == 12
    assert len({tuple(choice.id for choice in item.matching_task.choices) for item in matching}) >= 3
    assert len({tuple(row.source_type for row in item.matching_task.rows) for item in matching}) >= 3
    for item in matching:
        assert item.application_objectives == []
        assert {row.id for row in item.matching_task.rows} == {"clause-a", "clause-b", "clause-c"}
        assert not item.options and not item.steps and not item.machine_read
        assert item.roi_target is None and item.fill_in_task is None
        packet = clinical_packet(item.ecg_id)
        report = run_harness(item, packet, None)
        assert report.passed, f"{item.item_id}: {report.failing_checks()}"


def test_matching_harness_rejects_a_key_or_reference_not_bound_to_packet_manifest() -> None:
    item = next(
        item.model_copy(deep=True)
        for item in clinical_item_store.list_for_serving(status="harness_pass")
        if item.question_type == "matching"
    )
    packet = clinical_packet(item.ecg_id)
    ecg_row = next(row for row in item.matching_task.rows if row.source_type == "ecg_support")
    ecg_row.correct_choice_id = "context"
    ecg_row.source_reference = "invented_objective"

    report = run_harness(item, packet, None)
    scoring = next(check for check in report.results if check.check == "scoring_schema")
    assert scoring.passed is False
    assert scoring.hard_stop is True
    assert any("key that disagrees" in message for message in scoring.messages)
    assert any("source_reference" in message for message in scoring.messages)


def test_clinical_application_receipts_are_limited_to_declared_canonical_cells() -> None:
    declared_application = {
        objective
        for objectives in APPLICATION_OBJECTIVES_BY_SCENARIO.values()
        for objective in objectives
    }
    declared_application.update(
        objective
        for objectives in LONGITUDINAL_APPLICATION_OBJECTIVES_BY_CURRENT.values()
        for objective in objectives
    )
    assert declared_application == set(CLINICAL_APPLICATION_CONCEPTS)

    # Every canonical ECG concept may rehearse the information boundary in
    # Training, but that resting-ECG exercise remains formative.  The registry
    # must not confuse broad practice availability with independently assessed
    # clinical application.
    formative_training_application = {
        concept
        for concept in CONCEPT_BY_ID
        if "apply_in_context" in OBJECTIVES[concept].allowed_subskills
    }
    assert formative_training_application == set(CONCEPT_BY_ID)
    assert all(
        not training_independent_receipt_available(concept, "apply_in_context")
        for concept in formative_training_application
    )

    served = list(clinical_item_store.list_for_serving(status="harness_pass"))
    served_application = {
        objective
        for item in served
        for objective in item.application_objectives
    }
    assert served_application == declared_application
    assert all(
        set(item.application_objectives)
        <= {claim.objective_id for claim in item.evidence_manifest.ecg_supports}
        for item in served
    )

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

    with TestClient(app) as lane_client:
        registration = lane_client.post(
            "/auth/register",
            json={
                "username": f"provenance_{lane}_{uuid.uuid4().hex[:8]}",
                "password": "-".join(("Clinical", "provenance", lane, "2026")),
            },
        )
        assert registration.status_code == 200, registration.text
        started = lane_client.post(
            "/clinical/shift/start",
            json={"lane": lane, "tier": "learn", "length": 50},
        )
        assert started.status_code == 200
        body = started.json()
        assert body["session"]["availableDistinctEcgs"] == len(distinct_ecgs)
        assert body["session"]["length"] == len(distinct_ecgs)
        assert body["next"]["item"]["situation"] == lane
        assert body["next"]["item"]["tracing_provenance"] == "real_deidentified_ecg"
        abandoned = lane_client.post(
            f"/clinical/shift/{body['session']['sessionId']}/abandon"
        )
        assert abandoned.status_code == 200, abandoned.text


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


def test_oldnew_rejects_a_self_pair_and_wct_remains_locked() -> None:
    oldnew = next(item for item in FIXTURE_ITEMS if item.question_type == "oldnew").model_copy(
        deep=True,
        update={
            "item_id": "ptb-longitudinal-unverified",
            "ecg_id": "195",
            "prior_ecg_id": "195",
            "validation_status": "harness_pass",
        },
    )
    with pytest.raises(RuntimeError, match="distinct records"):
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


def _longitudinal_packet(
    case_id: str,
    *,
    patient_id: str | None = "patient-1",
    recording_date: str = "2026-01-02 12:00:00",
    source: str = "ptbxl",
    source_version: str = "1.0.3",
    signal_status: str | None = "acceptable",
    human_validated: bool | None = True,
) -> dict:
    identity = {
        "sourceId": source,
        "sourceRecordId": case_id,
        "patientId": patient_id,
        "sourceVersion": source_version,
        "licenseId": "CC-BY-4.0",
    }
    provenance = {
        "sourceId": source,
        "sourceVersion": source_version,
        "licenseId": "CC-BY-4.0",
        "patientId": patient_id,
    }
    metadata: dict[str, object] = {"recording_date": recording_date}
    quality: dict[str, object] = {}
    if signal_status is not None:
        quality["status"] = signal_status
    if human_validated is not None:
        quality["human_validated"] = human_validated
        metadata["validated_by_human"] = human_validated
    return {
        "case_id": case_id,
        "source": source,
        "record_identity": identity,
        "source_provenance": provenance,
        "signal_quality": quality,
        "ptbxl": {"metadata": metadata},
    }


def test_authenticated_same_patient_pair_unlocks_oldnew_provenance() -> None:
    current = clinical_packet("948")
    prior = clinical_packet("942")
    assert current is not None and prior is not None

    resolved = assert_longitudinal_pair_provenance(
        current,
        prior,
        current_ecg_id="948",
        prior_ecg_id="942",
    )
    assert resolved == (current, prior)

    oldnew = next(item for item in FIXTURE_ITEMS if item.question_type == "oldnew").model_copy(
        deep=True,
        update={
            "item_id": "ptb-authenticated-longitudinal-948",
            "ecg_id": "948",
            "prior_ecg_id": "942",
            "validation_status": "harness_pass",
        },
    )
    resolved_item = assert_learner_item_provenance(oldnew, clinical_packet)
    assert resolved_item["case_id"] == "948"


@pytest.mark.parametrize(
    ("current_overrides", "prior_overrides", "message"),
    [
        ({"case_id": "prior"}, {}, "distinct records"),
        ({"patient_id": "patient-2"}, {}, "patient identity"),
        ({"source_version": "1.0.2"}, {}, "version is not approved"),
        ({"recording_date": "not-a-date"}, {}, "timestamp is invalid"),
        ({"recording_date": "2026-01-01 12:00:00"}, {}, "prior must precede"),
        ({"signal_status": "borderline"}, {}, "not acceptable"),
        ({"signal_status": None}, {}, "not acceptable"),
        ({"human_validated": False}, {}, "human signal validation"),
        ({"human_validated": None}, {}, "human signal validation"),
        ({"source": "prepared_bundle"}, {}, "unapproved source"),
    ],
)
def test_longitudinal_pair_provenance_fails_closed(
    current_overrides: dict,
    prior_overrides: dict,
    message: str,
) -> None:
    current_values = {
        "case_id": "current",
        "recording_date": "2026-01-02 12:00:00",
        **current_overrides,
    }
    prior_values = {
        "case_id": "prior",
        "recording_date": "2026-01-01 12:00:00",
        **prior_overrides,
    }
    with pytest.raises(RuntimeError, match=message):
        assert_longitudinal_pair_provenance(
            _longitudinal_packet(**current_values),
            _longitudinal_packet(**prior_values),
            current_ecg_id=str(current_values["case_id"]),
            prior_ecg_id=str(prior_values["case_id"]),
        )
