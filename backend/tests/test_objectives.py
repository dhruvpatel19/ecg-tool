from __future__ import annotations

import re
from pathlib import Path

from app.objectives import (
    FOUNDATIONAL_OBJECTIVE_IDS,
    FOUNDATIONS_OBJECTIVE_IDS,
    GUIDED_OBJECTIVE_IDS,
    LEGACY_FOUNDATIONAL_OBJECTIVE_IDS,
    NEUTRAL_WAVEFORM_OBJECTIVES,
    OBJECTIVES,
    SUBSKILLS,
    objective_runtime_availability,
    validate_objective_subskill,
)
from app.ontology import CONCEPTS


def _handoff_objectives() -> set[str]:
    module_root = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "learning" / "modules"
    pattern = re.compile(r'handoff\("[^"]+",\s*"[^"]+",\s*"([^"]+)"')
    found: set[str] = set()
    for path in module_root.glob("*.ts"):
        found.update(pattern.findall(path.read_text(encoding="utf-8")))
    return found


def test_registry_covers_every_case_concept_and_guided_handoff() -> None:
    assert {concept.id for concept in CONCEPTS} <= set(OBJECTIVES)
    assert _handoff_objectives() == set(GUIDED_OBJECTIVE_IDS)
    assert set(GUIDED_OBJECTIVE_IDS) <= set(OBJECTIVES)
    assert NEUTRAL_WAVEFORM_OBJECTIVES <= set(OBJECTIVES)
    assert FOUNDATIONAL_OBJECTIVE_IDS <= set(OBJECTIVES)


def test_neutral_qrs_localization_evidence_has_a_visible_registry_cell() -> None:
    objective = OBJECTIVES["qrs_complex"]
    assert objective.domain == "waveform_fundamentals"
    assert objective.allowed_subskills == ("localize",)
    assert objective.case_concepts == ("normal_ecg",)


def test_prior_registry_cells_remain_visible_and_semantically_valid() -> None:
    prior_pairs = {
        ("ecg_grid_calibration", "measure"),
        ("ectopy", "apply_in_context"),
        ("ischemia_mimic_discrimination", "localize"),
        ("normal_ecg", "localize"),
        ("pr_interval", "explain_mechanism"),
        ("pr_interval", "measure"),
        ("qrs_duration", "localize"),
        ("resuscitation_source_boundary", "synthesize"),
        ("tachyarrhythmia_mixed", "localize"),
        ("tachyarrhythmia_mixed", "measure"),
        ("waveform_components", "localize"),
    }
    assert all(validate_objective_subskill(objective, subskill) for objective, subskill in prior_pairs)


def test_native_foundations_objectives_are_additive_and_formative_until_server_graded() -> None:
    assert FOUNDATIONS_OBJECTIVE_IDS == {
        "foundations_waveform_landmarks",
        "foundations_calibration",
        "foundations_signal_quality",
        "foundations_rate",
        "foundations_atrial_source",
        "foundations_pr_qrs",
        "foundations_recovery",
        "foundations_twelve_lead_navigation",
        "foundations_axis",
        "foundations_systematic_sweep",
    }
    assert LEGACY_FOUNDATIONAL_OBJECTIVE_IDS == {
        "ecg_grid_calibration",
        "pr_interval",
        "waveform_components",
    }
    assert LEGACY_FOUNDATIONAL_OBJECTIVE_IDS.isdisjoint(FOUNDATIONS_OBJECTIVE_IDS)
    assert FOUNDATIONAL_OBJECTIVE_IDS == (
        LEGACY_FOUNDATIONAL_OBJECTIVE_IDS | FOUNDATIONS_OBJECTIVE_IDS
    )
    for objective_id in FOUNDATIONS_OBJECTIVE_IDS:
        objective = OBJECTIVES[objective_id]
        assert objective.case_concepts
        assert objective.allowed_subskills
        assert objective.evidence_ceiling == "formative_or_simulation"
        assert "server-owned analytic grader" in str(objective.unavailable_reason)


def test_every_objective_has_a_mapping_or_explicit_unavailable_reason() -> None:
    for objective in OBJECTIVES.values():
        assert objective.case_concepts or objective.unavailable_reason
        assert objective.domain != "unmapped"
        assert objective.allowed_subskills
        assert set(objective.allowed_subskills) <= set(SUBSKILLS)
        for subskill in objective.allowed_subskills:
            assert objective.task_templates[subskill]
            assert validate_objective_subskill(objective.id, subskill)


def test_source_boundaries_remain_formative() -> None:
    for objective_id in (
        "serial_ecg_comparison",
        "resuscitation_source_boundary",
        "preexcited_atrial_fibrillation",
    ):
        objective = OBJECTIVES[objective_id]
        assert objective.evidence_ceiling == "formative_or_simulation"
        assert objective.unavailable_reason


def test_source_boundary_objectives_live_in_student_facing_domains() -> None:
    assert OBJECTIVES["preexcited_atrial_fibrillation"].domain == "tachyarrhythmia"
    assert OBJECTIVES["resuscitation_source_boundary"].domain == "integration"


def test_wct_registry_is_runtime_locked_without_an_audited_rhythm_source() -> None:
    definition = OBJECTIVES["wide_complex_tachycardia"]
    assert definition.unavailable_reason is None
    availability = objective_runtime_availability(definition, None)
    assert availability.evidence_ceiling == "formative_or_simulation"
    assert availability.unavailable_reason
    assert availability.independent_evidence_available is False


def test_bundle_branch_objectives_expose_the_reviewed_qrs_measurement_subskill() -> None:
    assert "measure" in OBJECTIVES["right_bundle_branch_block"].allowed_subskills
    assert "measure" in OBJECTIVES["left_bundle_branch_block"].allowed_subskills


def test_qt_interval_objective_maps_to_the_authored_qtc_case_family() -> None:
    objective = OBJECTIVES["qt_interval"]
    assert objective.case_concepts == ("qtc_prolongation",)
    assert objective.domain == "intervals"
    assert "measure" in objective.allowed_subskills


def test_student_facing_objective_labels_preserve_clinical_acronyms() -> None:
    assert OBJECTIVES["normal_ecg"].label == "Normal ECG"
    assert OBJECTIVES["av_block_first_degree"].label == "AV Block First Degree"
    assert OBJECTIVES["st_depression"].label == "ST Depression"
    assert OBJECTIVES["qt_interval"].label == "QT Interval"
