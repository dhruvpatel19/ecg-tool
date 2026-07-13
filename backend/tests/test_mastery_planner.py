from __future__ import annotations

from datetime import UTC, datetime

from app.mastery_planner import build_mastery_plan
from app.objectives import ObjectiveDefinition


def _definition(
    objective_id: str,
    concept: str,
    *subskills: str,
    ceiling: str = "eligible_real_case",
) -> ObjectiveDefinition:
    return ObjectiveDefinition(
        id=objective_id,
        label=objective_id.replace("_", " ").title(),
        domain="test",
        case_concepts=(concept,),
        allowed_subskills=tuple(subskills),
        task_templates={subskill: ("classification",) for subskill in subskills},
        evidence_ceiling=ceiling,
    )


def test_unassessed_plan_starts_with_baseline_and_never_displays_a_mastery_prior() -> None:
    plan = build_mastery_plan(
        {"subskillMastery": []},
        {"normal_ecg": 100, "atrial_fibrillation": 20},
        definitions=[
            _definition("normal_ecg", "normal_ecg", "recognize"),
            _definition("atrial_fibrillation", "atrial_fibrillation", "recognize"),
        ],
        clinical_concepts=set(),
        as_of=datetime(2026, 7, 12, tzinfo=UTC),
    )
    assert plan["basis"]["baselineNeeded"] is True
    assert plan["basis"]["independentAttempts"] == 0
    assert plan["primary"]["independentMastery"] == 0.0
    assert plan["primary"]["reason"].endswith("has not yet been observed; begin with an eligible real ECG.")
    assert plan["stages"][0]["mode"] == "rapid"
    assert "highest-priority exact receipt task" in plan["explanation"]
    assert plan["stages"][0]["receiptConcept"] == "normal_ecg"
    assert plan["stages"][0]["receiptSubskill"] == "recognize"
    assert plan["stages"][0]["stageKind"] == "baseline"
    assert plan["integration"] is None
    assert plan["integrationReadiness"]["unlocked"] is False
    assert plan["basis"]["minimumDistinctEcgsForDurable"] == 3


def test_due_and_high_confidence_evidence_drive_plan_before_unseen_cells() -> None:
    profile = {
        "subskillMastery": [
            {
                "concept": "atrial_fibrillation",
                "subskill": "recognize",
                "attempts": 5,
                "independentAttempts": 4,
                "independentMastery": 0.72,
                "highConfidenceWrong": 1,
                "isDue": True,
                "dueState": "overdue",
                "overdueDays": 3.5,
                "distinctSuccessfulEcgs": 3,
                "distinctModes": 2,
            }
        ]
    }
    plan = build_mastery_plan(
        profile,
        {"normal_ecg": 100, "atrial_fibrillation": 20},
        definitions=[
            _definition("normal_ecg", "normal_ecg", "recognize"),
            _definition("atrial_fibrillation", "atrial_fibrillation", "recognize"),
        ],
        clinical_concepts={"atrial_fibrillation"},
    )
    assert plan["primary"]["caseConcept"] == "atrial_fibrillation"
    assert plan["basis"]["dueCompetencies"] == 1
    assert plan["basis"]["overdueCompetencies"] == 1
    assert plan["basis"]["highConfidenceMisses"] == 1
    assert [stage["mode"] for stage in plan["stages"]] == ["rapid"]
    assert "subskill=recognize" in plan["stages"][0]["href"]


def test_unavailable_or_nonexistent_source_contracts_never_enter_plan() -> None:
    plan = build_mastery_plan(
        {"subskillMastery": []},
        {"wide_complex_tachycardia": 10, "normal_ecg": 3},
        definitions=[
            _definition(
                "wide_complex_tachycardia",
                "wide_complex_tachycardia",
                "recognize",
                ceiling="formative_or_simulation",
            ),
            _definition("normal_ecg", "normal_ecg", "recognize"),
            _definition("missing", "atrial_fibrillation", "recognize"),
        ],
        clinical_concepts=set(),
    )
    assert {row["caseConcept"] for row in plan["priorities"]} == {"normal_ecg"}
    assert all("wide_complex_tachycardia" not in stage["href"] for stage in plan["stages"])


def test_runtime_audited_source_unlock_enters_adaptive_plan_without_changing_static_registry() -> None:
    wct = _definition(
        "wide_complex_tachycardia",
        "wide_complex_tachycardia",
        "recognize",
        ceiling="formative_or_simulation",
    )
    plan = build_mastery_plan(
        {"subskillMastery": []},
        {"wide_complex_tachycardia": 10},
        definitions=[wct],
        runtime_evidence={"wide_complex_tachycardia": "eligible_real_case"},
        runtime_subskills={"wide_complex_tachycardia": {"recognize"}},
        clinical_concepts=set(),
    )

    assert plan["primary"]["caseConcept"] == "wide_complex_tachycardia"
    assert plan["primary"]["subskill"] == "recognize"
    assert plan["stages"][0]["mode"] == "rapid"
    assert all(stage["mode"] != "clinical" for stage in plan["stages"])


def test_not_due_durable_skill_does_not_displace_an_unseen_eligible_skill() -> None:
    profile = {
        "subskillMastery": [{
            "concept": "normal_ecg",
            "subskill": "recognize",
            "attempts": 12,
            "independentAttempts": 8,
            "independentMastery": 0.95,
            "highConfidenceWrong": 0,
            "isDue": False,
            "dueState": "scheduled",
            "overdueDays": 0,
            "stabilityDays": 14,
            "spacedRetrievals": 4,
            "distinctEligibleEcgs": 6,
            "distinctSuccessfulEcgs": 6,
            "distinctModes": 3,
            "distinctMorphologies": 3,
            "lastIndependentCorrect": True,
        }]
    }
    plan = build_mastery_plan(
        profile,
        {"normal_ecg": 100, "atrial_fibrillation": 20},
        definitions=[
            _definition("normal_ecg", "normal_ecg", "recognize"),
            _definition("atrial_fibrillation", "atrial_fibrillation", "recognize"),
        ],
        clinical_concepts=set(),
    )
    assert plan["primary"]["caseConcept"] == "atrial_fibrillation"


def test_every_prescribed_subskill_links_to_a_mode_that_emits_that_exact_receipt() -> None:
    rows = [
        ("recognize", "rapid"),
        ("discriminate", "train"),
        ("explain_mechanism", "train"),
        ("calibrate_confidence", "train"),
    ]
    for subskill, expected_mode in rows:
        plan = build_mastery_plan(
            {"subskillMastery": []},
            {"atrial_fibrillation": 25},
            definitions=[
                _definition(
                    "atrial_fibrillation", "atrial_fibrillation", subskill
                )
            ],
            clinical_concepts={"atrial_fibrillation"},
        )
        assert plan["primary"]["subskill"] == subskill
        assert len(plan["stages"]) == 1
        stage = plan["stages"][0]
        assert stage["mode"] == expected_mode
        assert stage["receiptConcept"] == "atrial_fibrillation"
        assert stage["receiptSubskill"] == subskill
        assert f"subskill={subskill}" in stage["href"]

    synthesis = build_mastery_plan(
        {"subskillMastery": []},
        {"atrial_fibrillation": 25},
        definitions=[
            _definition(
                "tachyarrhythmia_mixed", "atrial_fibrillation", "synthesize"
            )
        ],
    )
    assert synthesis["stages"][0]["mode"] == "rapid"
    assert synthesis["stages"][0]["receiptConcept"] == "tachyarrhythmia_mixed"
    assert "receiptConcept=tachyarrhythmia_mixed" in synthesis["stages"][0]["href"]


def test_formative_only_application_is_not_advertised_as_a_mastery_path() -> None:
    plan = build_mastery_plan(
        {"subskillMastery": []},
        {"atrial_fibrillation": 25},
        definitions=[
            _definition(
                "atrial_fibrillation", "atrial_fibrillation", "apply_in_context"
            )
        ],
        clinical_concepts={"atrial_fibrillation"},
    )
    assert plan["primary"] is None
    assert plan["priorities"] == []
    assert plan["stages"] == []


def test_training_cells_without_a_trace_or_contrast_grader_do_not_enter_plan() -> None:
    plan = build_mastery_plan(
        {"subskillMastery": []},
        {"axis_normal": 50, "paced_rhythm": 10},
        definitions=[
            _definition("axis_normal", "axis_normal", "measure"),
            _definition("paced_rhythm", "paced_rhythm", "measure"),
        ],
    )
    assert plan["primary"] is None
    assert plan["stages"] == []


def test_sparse_family_cannot_be_advertised_as_a_durable_mastery_path() -> None:
    plan = build_mastery_plan(
        {"subskillMastery": []},
        {"av_block_second_degree_mobitz_i": 1},
        definitions=[
            _definition(
                "av_block_second_degree_mobitz_i",
                "av_block_second_degree_mobitz_i",
                "recognize",
            )
        ],
    )
    assert plan["primary"] is None
    assert plan["stages"] == []
