from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.mastery_planner import (
    _GUIDED_REMEDIATION_DESTINATIONS,
    _receipt_mode,
    build_mastery_plan,
)
from app.objectives import OBJECTIVES, ObjectiveDefinition


def _definition(
    objective_id: str,
    concept: str,
    *subskills: str,
    ceiling: str = "eligible_real_case",
    domain: str = "test",
) -> ObjectiveDefinition:
    return ObjectiveDefinition(
        id=objective_id,
        label=objective_id.replace("_", " ").title(),
        domain=domain,
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
    assert plan["basis"]["independentCompetencyObservations"] == 0
    assert plan["basis"]["independentAttemptUnit"] == "competency_observation"
    assert plan["primary"]["independentMastery"] == 0.0
    assert plan["primary"]["reason"].endswith("has not yet been checked; begin with a real ECG.")
    assert plan["stages"][0]["mode"] == "rapid"
    assert "establishes a focused starting point" in plan["explanation"]
    assert plan["stages"][0]["receiptConcept"] == "normal_ecg"
    assert plan["stages"][0]["receiptSubskill"] == "recognize"
    assert plan["stages"][0]["stageKind"] == "baseline"
    assert plan["stages"][0]["suggestedLength"] == 5
    assert plan["stages"][0]["suggestedPace"] == "untimed"
    baseline_query = parse_qs(urlparse(plan["stages"][0]["href"]).query)
    assert baseline_query["suggestedLength"] == ["5"]
    assert baseline_query["pace"] == ["untimed"]
    assert plan["integration"] is None
    assert plan["guidedRemediation"] is None
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
    assert plan["clinicalApplication"] == {
        "mode": "clinical",
        "title": "Apply Atrial Fibrillation in a patient-care decision",
        "purpose": plan["clinicalApplication"]["purpose"],
        "href": (
            "/practice?focus=atrial_fibrillation&subskill=apply_in_context"
            "&returnTo=%2Fhome%3Fpanel%3Dplan"
        ),
        "concept": "atrial_fibrillation",
        "subskill": "apply_in_context",
        "evidenceKind": "formative_application",
        "afterStageOrder": 1,
        "reason": plan["clinicalApplication"]["reason"],
    }
    assert all(stage["mode"] != "clinical" for stage in plan["stages"])
    assert plan["guidedRemediation"] == {
        "mode": "guided",
        "title": "Rebuild Atrial Fibrillation before the next check",
        "purpose": plan["guidedRemediation"]["purpose"],
        "href": "/learn/tachyarrhythmias?scene=m06-s5",
        "moduleId": "tachyarrhythmias",
        "sceneId": "m06-s5",
        "concept": "atrial_fibrillation",
        "evidenceKind": "formative_guided",
        "updatesIndependentMastery": False,
        "beforeStageOrder": 1,
        "reason": plan["guidedRemediation"]["reason"],
    }
    assert "does not count as independent mastery evidence" in plan["guidedRemediation"]["purpose"]


def test_failed_independent_check_reason_does_not_claim_success_across_zero_ecgs() -> None:
    profile = {
        "subskillMastery": [
            {
                "concept": "sinus_rhythm",
                "subskill": "recognize",
                "attempts": 1,
                "independentAttempts": 1,
                "independentMastery": 0.09,
                "highConfidenceWrong": 0,
                "isDue": False,
                "dueState": "scheduled",
                "overdueDays": 0,
                "distinctSuccessfulEcgs": 0,
                "distinctModes": 1,
            },
            {
                "concept": "axis_normal",
                "subskill": "recognize",
                "attempts": 2,
                "independentAttempts": 2,
                "independentMastery": 0.45,
                "highConfidenceWrong": 0,
                "isDue": False,
                "dueState": "scheduled",
                "overdueDays": 0,
                "distinctSuccessfulEcgs": 1,
                "distinctModes": 1,
            },
        ]
    }
    plan = build_mastery_plan(
        profile,
        {"sinus_rhythm": 100, "axis_normal": 100},
        definitions=[
            _definition("sinus_rhythm", "sinus_rhythm", "recognize"),
            _definition("axis_normal", "axis_normal", "recognize"),
        ],
        clinical_concepts=set(),
    )

    sinus = next(
        row for row in plan["priorities"] if row["caseConcept"] == "sinus_rhythm"
    )
    assert sinus["reason"] == (
        "After 1 independent check, the current mastery estimate for Sinus Rhythm · "
        "recognize is 9%; no successful ECG has been recorded yet."
    )
    assert "across 0" not in sinus["reason"]
    assert plan["basis"]["independentCompetencyObservations"] == 3
    assert plan["basis"]["independentAttempts"] == 3
    assert plan["basis"]["independentAttemptUnit"] == "competency_observation"


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
        query = parse_qs(urlparse(stage["href"]).query)
        expected_length = 25 if expected_mode == "train" else 5
        assert stage["suggestedLength"] == expected_length
        assert query["suggestedLength"] == [str(expected_length)]
        assert query["returnTo"] == ["/home?panel=plan"]

    exact_synthesis = build_mastery_plan(
        {"subskillMastery": []},
        {"atrial_fibrillation": 25},
        definitions=[
            _definition(
                "atrial_fibrillation", "atrial_fibrillation", "synthesize"
            )
        ],
    )
    assert exact_synthesis["primary"] is None
    assert exact_synthesis["stages"] == []

    reviewed_alias = build_mastery_plan(
        {"subskillMastery": []},
        {"normal_ecg": 25},
        definitions=[
            _definition(
                "integrated_interpretation", "normal_ecg", "synthesize"
            )
        ],
    )
    assert reviewed_alias["primary"] is None
    assert reviewed_alias["stages"] == []

    unreviewed_alias = build_mastery_plan(
        {"subskillMastery": []},
        {"atrial_fibrillation": 25},
        definitions=[
            _definition(
                "tachyarrhythmia_mixed", "atrial_fibrillation", "synthesize"
            )
        ],
    )
    assert unreviewed_alias["primary"] is None
    assert unreviewed_alias["stages"] == []


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
    assert plan["clinicalApplication"] is None


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


def test_guided_remediation_requires_observed_gap_and_preserves_independent_stage() -> None:
    plan = build_mastery_plan(
        {
            "subskillMastery": [{
                "concept": "right_bundle_branch_block",
                "subskill": "discriminate",
                "attempts": 4,
                "independentAttempts": 3,
                "independentMastery": 0.31,
                "highConfidenceWrong": 0,
                "isDue": False,
                "dueState": "scheduled",
                "overdueDays": 0,
                "distinctSuccessfulEcgs": 1,
                "distinctModes": 1,
                "lapses": 1,
            }],
        },
        {"right_bundle_branch_block": 25},
        definitions=[
            _definition(
                "right_bundle_branch_block",
                "right_bundle_branch_block",
                "discriminate",
                domain="conduction",
            )
        ],
    )

    guided = plan["guidedRemediation"]
    assert guided["href"] == "/learn/ventricular-conduction?scene=m05-s2"
    assert guided["evidenceKind"] == "formative_guided"
    assert guided["updatesIndependentMastery"] is False
    assert guided["beforeStageOrder"] == 1
    assert plan["stages"][0]["mode"] == "train"
    assert plan["stages"][0]["evidenceKind"] == "independent_transfer"
    assert plan["stages"][0]["receiptConcept"] == "right_bundle_branch_block"


def test_cross_concept_integration_is_not_advertised_without_synthesis_grading() -> None:
    profile = {
        "subskillMastery": [
            {
                "concept": "normal_ecg",
                "subskill": "recognize",
                "attempts": 5,
                "independentAttempts": 4,
                "independentMastery": 0.68,
                "highConfidenceWrong": 0,
                "isDue": False,
                "dueState": "scheduled",
                "overdueDays": 0,
                "distinctSuccessfulEcgs": 4,
                "distinctModes": 2,
            },
            {
                "concept": "atrial_fibrillation",
                "subskill": "recognize",
                "attempts": 4,
                "independentAttempts": 3,
                "independentMastery": 0.82,
                "highConfidenceWrong": 0,
                "isDue": False,
                "dueState": "scheduled",
                "overdueDays": 0,
                "distinctSuccessfulEcgs": 3,
                "distinctModes": 2,
            },
        ]
    }
    plan = build_mastery_plan(
        profile,
        {"normal_ecg": 100, "atrial_fibrillation": 25},
        definitions=[
            _definition(
                "normal_ecg", "normal_ecg", "recognize", "synthesize", domain="framework"
            ),
            _definition(
                "atrial_fibrillation", "atrial_fibrillation", "recognize", domain="rhythm"
            ),
        ],
    )

    assert plan["integrationReadiness"]["unlocked"] is False
    assert "deterministic per-domain grading" in plan["integrationReadiness"]["reason"]
    assert plan["guidedRemediation"] is None
    assert plan["integration"] is None


def test_saved_session_preferences_shape_runnable_stages_without_weakening_receipts() -> None:
    training = build_mastery_plan(
        {"subskillMastery": []},
        {"atrial_fibrillation": 25},
        definitions=[
            _definition(
                "atrial_fibrillation",
                "atrial_fibrillation",
                "discriminate",
            )
        ],
        preferences={
            "trainingStage": "core_clerkship",
            "primaryGoal": "clinical_reading",
            "defaultSessionLength": 5,
            "rapidPace": "emergency",
            "guidanceLevel": "minimal",
        },
    )
    training_stage = training["stages"][0]
    assert training_stage["suggestedLength"] == 10
    assert parse_qs(urlparse(training_stage["href"]).query)["suggestedLength"] == ["10"]
    assert training_stage["receiptSubskill"] == "discriminate"
    assert training["preferenceContext"]["primaryGoal"] == "clinical_reading"

    baseline_recognition = build_mastery_plan(
        {"subskillMastery": []},
        {"atrial_fibrillation": 25},
        definitions=[
            _definition(
                "atrial_fibrillation",
                "atrial_fibrillation",
                "recognize",
            )
        ],
        preferences={
            "defaultSessionLength": 50,
            "rapidPace": "emergency",
        },
    )
    baseline_stage = baseline_recognition["stages"][0]
    assert baseline_stage["stageKind"] == "baseline"
    assert baseline_stage["suggestedLength"] == 5
    assert baseline_stage["suggestedPace"] == "untimed"
    baseline_query = parse_qs(urlparse(baseline_stage["href"]).query)
    assert baseline_query["suggestedLength"] == ["5"]
    assert baseline_query["pace"] == ["untimed"]

    established_recognition = build_mastery_plan(
        {
            "subskillMastery": [
                {
                    "concept": "atrial_fibrillation",
                    "subskill": "recognize",
                    "attempts": 1,
                    "independentAttempts": 1,
                    "independentMastery": 0.7,
                    "highConfidenceWrong": 0,
                    "isDue": False,
                    "dueState": "scheduled",
                    "overdueDays": 0,
                    "distinctSuccessfulEcgs": 1,
                    "distinctModes": 1,
                }
            ]
        },
        {"atrial_fibrillation": 25},
        definitions=[
            _definition(
                "atrial_fibrillation",
                "atrial_fibrillation",
                "recognize",
            )
        ],
        preferences={
            "defaultSessionLength": 50,
            "rapidPace": "emergency",
        },
    )
    established_stage = established_recognition["stages"][0]
    assert established_stage["stageKind"] == "consolidation"
    assert established_stage["suggestedLength"] == 50
    assert established_stage["suggestedPace"] == "emergency"
    established_query = parse_qs(urlparse(established_stage["href"]).query)
    assert established_query["suggestedLength"] == ["50"]
    assert established_query["pace"] == ["emergency"]

    synthesis = build_mastery_plan(
        {"subskillMastery": []},
        {"atrial_fibrillation": 25},
        definitions=[
            _definition(
                "atrial_fibrillation",
                "atrial_fibrillation",
                "synthesize",
            )
        ],
        preferences={
            "defaultSessionLength": 5,
            "rapidPace": "emergency",
        },
    )
    assert synthesis["primary"] is None
    assert synthesis["stages"] == []


def test_saved_goal_only_breaks_unseen_ties_and_never_displaces_due_evidence() -> None:
    definitions = [
        _definition("normal_ecg", "normal_ecg", "recognize"),
        _definition(
            "wide_complex_tachycardia",
            "wide_complex_tachycardia",
            "recognize",
        ),
    ]
    baseline = build_mastery_plan(
        {"subskillMastery": []},
        {"normal_ecg": 100, "wide_complex_tachycardia": 30},
        definitions=definitions,
        preferences={
            "trainingStage": "core_clerkship",
            "primaryGoal": "emergency_prioritization",
        },
    )
    assert baseline["primary"]["caseConcept"] == "wide_complex_tachycardia"
    assert "saved training stage and goal" in baseline["explanation"]

    due_profile = {
        "subskillMastery": [{
            "concept": "normal_ecg",
            "subskill": "recognize",
            "attempts": 4,
            "independentAttempts": 3,
            "independentMastery": 0.8,
            "highConfidenceWrong": 0,
            "isDue": True,
            "dueState": "overdue",
            "overdueDays": 2,
            "distinctSuccessfulEcgs": 3,
            "distinctModes": 1,
        }],
    }
    due = build_mastery_plan(
        due_profile,
        {"normal_ecg": 100, "wide_complex_tachycardia": 30},
        definitions=definitions,
        preferences={
            "trainingStage": "core_clerkship",
            "primaryGoal": "emergency_prioritization",
        },
    )
    assert due["primary"]["caseConcept"] == "normal_ecg"
    assert due["basis"]["overdueCompetencies"] == 1


def test_every_guided_remediation_destination_is_an_authored_routable_scene() -> None:
    module_files = {
        "leads-vectors": "m02LeadsVectors.ts",
        "rhythm-ectopy": "m03RhythmLogic.ts",
        "av-brady": "m04AvConduction.ts",
        "ventricular-conduction": "m05VentricularConduction.ts",
        "tachyarrhythmias": "m06Tachyarrhythmias.ts",
        "chambers-voltage": "m07ChambersVoltage.ts",
        "repolarization-safety": "m08Repolarization.ts",
        "ischemia-infarction": "m09Ischemia.ts",
    }
    modules_root = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "src"
        / "lib"
        / "learning"
        / "modules"
    )

    assert _GUIDED_REMEDIATION_DESTINATIONS
    independently_runnable_concepts = {
        case_concept
        for definition in OBJECTIVES.values()
        for case_concept in definition.case_concepts
        for subskill in definition.allowed_subskills
        if _receipt_mode(definition, case_concept, subskill)
    }
    assert independently_runnable_concepts <= set(_GUIDED_REMEDIATION_DESTINATIONS)
    for concept, (module_id, scene_id, scene_title) in _GUIDED_REMEDIATION_DESTINATIONS.items():
        source = (modules_root / module_files[module_id]).read_text(encoding="utf-8")
        assert f'id: "{module_id}"' in source, concept
        assert f'id: "{scene_id}"' in source, concept
        assert scene_title.strip(), concept
