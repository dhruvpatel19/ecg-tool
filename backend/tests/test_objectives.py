from __future__ import annotations

import re
from pathlib import Path

from app.objectives import (
    GUIDED_OBJECTIVE_IDS,
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


def test_every_objective_has_a_mapping_or_explicit_unavailable_reason() -> None:
    for objective in OBJECTIVES.values():
        assert objective.case_concepts or objective.unavailable_reason
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
