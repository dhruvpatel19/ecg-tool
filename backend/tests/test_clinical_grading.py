"""Tests for the Clinical Decisions per-type grader (answer-class + axes + caps)."""

from __future__ import annotations

from app.clinical.clinical_grading import grade_clinical_answer
from app.clinical.schemas import (
    ClinicalAnswer,
    ClinicalCaseItem,
    ClinicalClick,
    DisplaySpec,
    EvidenceClaim,
    EvidenceManifest,
    FillInTask,
    MatchingChoice,
    MatchingRow,
    MatchingTask,
    Option,
    StemChips,
)
from app.clinical.seed_items import SEED_PACKETS, packet_for
from app.clinical.seed_items import CASE_C, CASE_T, CASE_W
from app.clinical.fixture_items import AF_MCQ
from app.fixtures import build_fixture_cases


def _ans(**kw):
    return ClinicalAnswer(**kw)


def test_ideal_option_high_credit_and_correct():
    grade = grade_clinical_answer(
        CASE_W, packet_for(CASE_W), _ans(selected_option_id="w1", step_answers=[0, 0], confidence=4)
    )
    assert grade["answerClass"] == "ideal"
    assert grade["score"] == 1.0
    assert grade["correctObjectives"]  # preserved for feedback/reporting
    assert grade["masteryDelta"] == {}  # formative bank never mutates mastery


def test_confidence_upside_cap_lowers_correct_credit():
    high = grade_clinical_answer(CASE_W, packet_for(CASE_W), _ans(selected_option_id="w1", step_answers=[0, 0], confidence=5))
    low = grade_clinical_answer(CASE_W, packet_for(CASE_W), _ans(selected_option_id="w1", step_answers=[0, 0], confidence=1))
    assert high["score"] > low["score"]
    assert low["score"] >= 0.6  # still correct, just capped


def test_omitted_confidence_preserves_base_credit_without_calibration() -> None:
    packet = next(
        case for case in build_fixture_cases() if case["case_id"] == AF_MCQ.ecg_id
    )

    grade = grade_clinical_answer(
        AF_MCQ,
        packet,
        _ans(selected_option_id="af_rate"),
    )

    assert grade["score"] == 1.0
    assert grade["answerClass"] == "ideal"
    assert grade["calibrationEvent"] == {}


def test_high_confidence_wrong_zeroed_and_flagged():
    grade = grade_clinical_answer(CASE_W, packet_for(CASE_W), _ans(selected_option_id="w4", confidence=5))
    assert grade["score"] == 0.0
    assert grade["calibrationEvent"]["highConfidenceWrong"] is True
    assert grade["missedObjectives"]


def test_atropine_only_capped_for_complete_block():
    """An ideal/acceptable option lacking the required safety action is capped (§16B5)."""
    item = ClinicalCaseItem(
        item_id="t-atropine-only",
        ecg_id="seed-chb-001",
        situation="ward",
        question_type="mcq",
        acuity_tier="high",
        stem="Symptomatic bradycardia on telemetry.",
        chips=StemChips(age=70, setting="ward", symptom="dizziness"),
        prompt="Next step?",
        options=[Option(id="a", text="Give IV atropine and reassess in 30 minutes.", answer_class="acceptable")],
        evidence_manifest=EvidenceManifest(
            ecg_supports=[EvidenceClaim(objective_id="av_block_third_degree", source_type="curated_label")],
            action_rationale="Pacing readiness is the safe move.",
        ),
        display_spec=DisplaySpec(mode="twelve_lead", tested_scope="full_12_lead"),
    )
    grade = grade_clinical_answer(item, SEED_PACKETS["seed-chb-001"], _ans(selected_option_id="a", confidence=3))
    assert "missing_required_safety_action" in grade["safetyFlags"]
    assert grade["score"] <= 0.3


def test_triage_ideal_act_now():
    grade = grade_clinical_answer(CASE_T, packet_for(CASE_T), _ans(selected_option_id="t_act", confidence=4))
    assert grade["score"] == 1.0
    assert grade["answerClass"] == "ideal"


def test_click_periodic_match_correct_and_wrong():
    pkt = packet_for(CASE_C)
    right = grade_clinical_answer(CASE_C, pkt, _ans(click=ClinicalClick(lead="II", time_sec=2.5)))
    wrong = grade_clinical_answer(CASE_C, pkt, _ans(click=ClinicalClick(lead="V1", time_sec=2.5)))
    assert right["score"] == 1.0
    assert right["axisScores"]["concept_identification"] == 1.0
    assert wrong["score"] == 0.0


def test_numeric_fillin_grades_the_grounded_packet_measurement_with_tolerance() -> None:
    item = ClinicalCaseItem(
        item_id="numeric-qt",
        ecg_id="real-qt",
        situation="clinic",
        question_type="fillin",
        acuity_tier="moderate",
        stem="A QT interval requires manual verification.",
        prompt="Estimate QT in milliseconds.",
        fill_in_task=FillInTask(
            response_label="Estimated QT interval",
            unit="ms",
            objective_id="qtc_prolongation",
            expected_feature="qt_ms",
            tolerance=40,
            min_value=200,
            max_value=800,
            step=10,
        ),
        evidence_manifest=EvidenceManifest(
            ecg_supports=[EvidenceClaim(objective_id="qtc_prolongation")],
            action_rationale="Verify QT before applying a rate-correction formula.",
        ),
    )
    packet = {
        "supported_objectives": ["qtc_prolongation"],
        "ptbxl_plus": {"features": {"qt_ms": 508.0}, "fiducials": {"rois": []}},
    }

    correct = grade_clinical_answer(
        item, packet, _ans(fill_in_value=500, confidence=5)
    )
    near_miss = grade_clinical_answer(
        item, packet, _ans(fill_in_value=440, confidence=3)
    )
    wrong = grade_clinical_answer(
        item, packet, _ans(fill_in_value=350, confidence=5)
    )

    assert correct["score"] == 1.0
    assert correct["correctObjectives"] == ["qtc_prolongation"]
    assert correct["axisScores"] == {"measurement_accuracy": 1.0}
    assert "508 ms" in correct["feedback"]
    assert near_miss["score"] == 0.5
    assert near_miss["missedObjectives"] == ["qtc_prolongation"]
    assert wrong["score"] == 0.0
    assert wrong["calibrationEvent"]["highConfidenceWrong"] is True


def _matching_item() -> ClinicalCaseItem:
    return ClinicalCaseItem(
        item_id="matching-evidence-boundaries",
        ecg_id="real-lvh",
        situation="clinic",
        question_type="matching",
        acuity_tier="low",
        stem="A student reviews a tracing during an outpatient follow-up.",
        chips=StemChips(age=55, setting="outpatient follow-up", symptom="none"),
        prompt="Match each clause to its strongest evidence boundary.",
        matching_task=MatchingTask(
            choices=[
                MatchingChoice(id="context", label="Provided only by the authored vignette"),
                MatchingChoice(id="unsupported", label="Not established by this ECG or vignette"),
                MatchingChoice(id="ecg", label="Supported by this ECG packet"),
            ],
            rows=[
                MatchingRow(
                    id="context-row",
                    clause="Encounter setting: outpatient follow-up",
                    source_type="authored_context",
                    correct_choice_id="context",
                    source_reference="authored setting: outpatient follow-up",
                ),
                MatchingRow(
                    id="unsupported-row",
                    clause="Claim: acute hypertensive emergency",
                    source_type="unsupported_claim",
                    correct_choice_id="unsupported",
                    source_reference="acute hypertensive emergency",
                ),
                MatchingRow(
                    id="ecg-row",
                    clause="Left ventricular hypertrophy",
                    source_type="ecg_support",
                    correct_choice_id="ecg",
                    source_reference="left_ventricular_hypertrophy",
                    objective_id="left_ventricular_hypertrophy",
                ),
            ],
        ),
        evidence_manifest=EvidenceManifest(
            ecg_supports=[EvidenceClaim(objective_id="left_ventricular_hypertrophy")],
            stem_adds=["authored setting: outpatient follow-up"],
            forbidden_claims=["acute hypertensive emergency"],
            action_rationale="Separate ECG evidence from supplied context before acting.",
        ),
    )


def test_matching_grades_every_row_deterministically_without_pathology_receipt() -> None:
    item = _matching_item()
    packet = {"supported_objectives": ["left_ventricular_hypertrophy"]}
    correct = grade_clinical_answer(
        item,
        packet,
        _ans(
            matches={
                "context-row": "context",
                "unsupported-row": "unsupported",
                "ecg-row": "ecg",
            },
            confidence=5,
        ),
    )
    partial = grade_clinical_answer(
        item,
        packet,
        _ans(
            matches={
                "context-row": "ecg",
                "unsupported-row": "unsupported",
                "ecg-row": "context",
            },
            confidence=5,
        ),
    )
    duplicate = grade_clinical_answer(
        item,
        packet,
        _ans(
            matches={
                "context-row": "ecg",
                "unsupported-row": "ecg",
                "ecg-row": "ecg",
            },
            confidence=3,
        ),
    )

    assert correct["score"] == 1.0
    assert correct["matchingCorrect"] is True
    assert all(result["correct"] for result in correct["matchingResults"])
    assert correct["correctObjectives"] == []
    assert correct["missedObjectives"] == []
    assert correct["masteryDelta"] == {}
    assert correct["axisScores"] == {
        "authored_context_boundary": 1.0,
        "unsupported_claim_boundary": 1.0,
        "ecg_evidence": 1.0,
        "evidence_source_matching": 1.0,
    }
    assert partial["score"] == 0.333
    assert partial["matchingCorrect"] is False
    assert partial["calibrationEvent"]["highConfidenceWrong"] is True
    assert [result["correct"] for result in partial["matchingResults"]] == [False, True, False]
    assert duplicate["score"] == 0.0
    assert duplicate["calibrationEvent"]["matchingComplete"] is False


def test_matching_timeout_cannot_credit_prefilled_mapping() -> None:
    item = _matching_item()
    packet = {"supported_objectives": ["left_ventricular_hypertrophy"]}
    grade = grade_clinical_answer(
        item,
        packet,
        _ans(
            matches={
                "context-row": "context",
                "unsupported-row": "unsupported",
                "ecg-row": "ecg",
            },
            confidence=5,
            timed_out=True,
        ),
    )

    assert grade["timedOut"] is True
    assert grade["score"] == 0.0
    assert grade["matchingCorrect"] is False
    assert not any(result["correct"] for result in grade["matchingResults"])


def test_timeout_is_kind_but_scored_zero():
    grade = grade_clinical_answer(CASE_T, packet_for(CASE_T), _ans(timed_out=True, confidence=3))
    assert grade["timedOut"] is True
    assert grade["score"] == 0.0


def test_stepwise_timeout_cannot_regrade_prefilled_correct_steps() -> None:
    grade = grade_clinical_answer(
        CASE_W,
        packet_for(CASE_W),
        _ans(
            selected_option_id="w1",
            step_answers=[0, 0],
            confidence=5,
            timed_out=True,
        ),
    )
    assert grade["timedOut"] is True
    assert grade["score"] == 0.0
    assert grade["correctObjectives"] == []
    assert grade["masteryDelta"] == {}
    assert grade["stepResults"] == [False, False]
    assert grade["axisScores"]["ecg_sequence"] == 0.0


def test_stem_disclosure_does_not_inflate_ecg_mastery() -> None:
    packet = next(case for case in build_fixture_cases() if case["case_id"] == AF_MCQ.ecg_id)
    disclosed_item = AF_MCQ.model_copy(update={"stem": "Irregularly irregular pulse, rate ~118."})
    grade = grade_clinical_answer(disclosed_item, packet, _ans(selected_option_id="af_rate", confidence=4))

    assert grade["score"] > 0.8  # management choice can still be good
    assert grade["ecgRecognitionSuppressed"] is True
    assert set(grade["stemDisclosedObjectives"]) == {"atrial_fibrillation", "rate"}
    assert grade["masteryDelta"] == {}
    assert grade["correctObjectives"] == []


def test_common_rate_disclosure_phrasings_are_all_suppressed() -> None:
    packet = next(case for case in build_fixture_cases() if case["case_id"] == AF_MCQ.ecg_id)
    for stem in ("Pulse 118.", "HR 118.", "Tachycardic at 118.", "Ventricular rate 118 bpm."):
        item = AF_MCQ.model_copy(update={"stem": f"Irregularly irregular rhythm. {stem}"})
        grade = grade_clinical_answer(item, packet, _ans(selected_option_id="af_rate", confidence=4))
        assert "rate" in grade["stemDisclosedObjectives"], stem
        assert grade["masteryDelta"] == {}, stem
