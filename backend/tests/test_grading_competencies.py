from __future__ import annotations

from app.grading import grade_attempt, grade_click_answer, grade_region_answer
from app.schemas import AttemptRequest


def _case(*objectives: str) -> dict:
    return {
        "case_id": "grading-fixture",
        "concept_confidence": {
            objective: {"tier": "A", "score": 0.9} for objective in objectives
        },
        "teaching_points": [],
        "ptbxl": {"report": "fixture report"},
        "ptbxl_plus": {"features": {"heart_rate": 72.0}, "fiducials": {"rois": []}},
    }


def test_numeric_rate_is_recognized_as_a_structured_rate_answer() -> None:
    grade = grade_attempt(
        _case("rate"),
        AttemptRequest(
            caseId="grading-fixture",
            structuredAnswer={"rate": "72"},
            freeTextAnswer="",
        ),
    )
    assert grade["score"] == 1.0
    assert grade["correctObjectives"] == ["rate"]


def test_wrong_numeric_rate_does_not_receive_mastery_credit() -> None:
    grade = grade_attempt(
        _case("rate"),
        AttemptRequest(
            caseId="grading-fixture",
            mode="concept_practice",
            focusObjective="rate",
            structuredAnswer={"rate": "299"},
            confidence=5,
        ),
    )
    assert grade["score"] == 0.0
    assert grade["correctObjectives"] == []
    assert grade["masteryDelta"]["rate"] < 0


def test_unrelated_matching_number_in_free_text_cannot_rescue_wrong_rate_field() -> None:
    grade = grade_attempt(
        _case("rate"),
        AttemptRequest(
            caseId="grading-fixture",
            structuredAnswer={"rate": "299 bpm", "conduction": "QRS duration 64 ms"},
            freeTextAnswer="QRS duration 64 ms",
            confidence=5,
        ),
    )

    assert grade["score"] == 0.0
    assert grade["correctObjectives"] == []


def test_av_block_vocabulary_is_gradable() -> None:
    grade = grade_attempt(
        _case("av_block_second_degree_mobitz_i"),
        AttemptRequest(
            caseId="grading-fixture",
            structuredAnswer={"intervals": "Mobitz I (Wenckebach)"},
        ),
    )
    assert grade["score"] == 1.0


def test_concept_training_grades_only_the_selected_focus() -> None:
    grade = grade_attempt(
        _case("right_bundle_branch_block", "qrs_duration", "sinus_rhythm", "rate"),
        AttemptRequest(
            caseId="grading-fixture",
            mode="concept_practice",
            focusObjective="right_bundle_branch_block",
            structuredAnswer={"selectedConcepts": ["right_bundle_branch_block"]},
        ),
    )
    assert grade["score"] == 1.0
    assert grade["missedObjectives"] == []
    assert grade["correctObjectives"] == ["right_bundle_branch_block"]


def test_quick_look_grades_one_dominant_finding_without_penalizing_incidental_labels() -> None:
    grade = grade_attempt(
        _case("right_bundle_branch_block", "qrs_duration", "sinus_rhythm", "qt_interval", "rate"),
        AttemptRequest(
            caseId="grading-fixture",
            mode="rapid_practice",
            assessmentScope="dominant_finding",
            structuredAnswer={"selectedConcepts": ["right_bundle_branch_block"]},
            confidence=5,
        ),
    )

    assert grade["score"] == 1.0
    assert grade["missedObjectives"] == []
    assert grade["correctObjectives"] == ["right_bundle_branch_block"]
    assert grade["masteryDelta"] == {"right_bundle_branch_block": 0.08}
    assert "high-confidence wrong answer" not in grade["misconceptions"]


def test_click_grading_accepts_homologous_visible_beats() -> None:
    case = _case("rate")
    case["ptbxl_plus"]["features"]["heart_rate"] = 60.0
    case["ptbxl_plus"]["fiducials"]["rois"] = [
        {
            "lead": "II",
            "concept": "qrs_complex",
            "label": "QRS complex",
            "timeStartSec": 4.80,
            "timeEndSec": 4.90,
            "ampMinMv": -0.4,
            "ampMaxMv": 1.2,
        }
    ]

    result = grade_click_answer(case, "II", 1.84, 0.7, "qrs_complex")

    assert result["correct"] is True


def test_click_grading_rejects_a_point_far_from_the_waveform() -> None:
    case = _case("rate")
    case["ptbxl_plus"]["features"]["heart_rate"] = 60.0
    case["ptbxl_plus"]["fiducials"]["rois"] = [
        {
            "lead": "II", "concept": "qrs_complex", "label": "QRS complex",
            "timeStartSec": 4.80, "timeEndSec": 4.90, "ampMinMv": -0.4, "ampMaxMv": 1.2,
        }
    ]

    result = grade_click_answer(case, "II", 1.84, 2.0, "qrs_complex")

    assert result["correct"] is False
    assert "far from the waveform" in result["feedback"]


def test_irregular_rhythm_does_not_project_one_fiducial_by_average_rate() -> None:
    case = _case("atrial_fibrillation")
    case["supported_objectives"] = ["atrial_fibrillation"]
    case["ptbxl_plus"]["features"]["heart_rate"] = 120.0
    case["ptbxl_plus"]["fiducials"]["rois"] = [
        {
            "lead": "II", "concept": "qrs_complex", "label": "QRS complex",
            "timeStartSec": 4.80, "timeEndSec": 4.90, "ampMinMv": -0.4, "ampMaxMv": 1.2,
        }
    ]

    result = grade_click_answer(case, "II", 2.84, 0.7, "qrs_complex")

    assert result["correct"] is False
    assert result["noTarget"] is True
    assert "not scored" in result["feedback"]


def test_region_grading_requires_coverage_and_localization() -> None:
    case = _case("st_elevation")
    case["ptbxl_plus"]["fiducials"]["rois"] = [
        {
            "lead": "II", "concept": "st_segment", "label": "ST segment",
            "timeStartSec": 4.90, "timeEndSec": 5.10, "ampMinMv": -0.1, "ampMaxMv": 0.3,
        }
    ]

    tight = grade_region_answer(case, "II", 4.88, 5.12, -0.15, 0.35, "st_segment")
    broad = grade_region_answer(case, "II", 0.0, 10.0, -2.5, 2.5, "st_segment")

    assert tight["correct"] is True
    assert tight["targetCoverage"] >= 0.9
    assert broad["correct"] is False
    assert "too broad" in broad["feedback"]


def test_region_grading_returns_neutral_when_concept_has_no_roi() -> None:
    case = _case("st_elevation")
    case["ptbxl_plus"]["fiducials"]["rois"] = [
        {
            "lead": "II", "concept": "qrs_complex", "label": "QRS complex",
            "timeStartSec": 4.80, "timeEndSec": 4.90, "ampMinMv": -0.4, "ampMaxMv": 1.2,
        }
    ]

    result = grade_region_answer(case, "II", 4.8, 4.9, -0.4, 1.2, "st_segment")

    assert result["correct"] is False
    assert result["noTarget"] is True
