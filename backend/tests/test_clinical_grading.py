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
    assert grade["correctObjectives"]  # mastery credited


def test_confidence_upside_cap_lowers_correct_credit():
    high = grade_clinical_answer(CASE_W, packet_for(CASE_W), _ans(selected_option_id="w1", step_answers=[0, 0], confidence=5))
    low = grade_clinical_answer(CASE_W, packet_for(CASE_W), _ans(selected_option_id="w1", step_answers=[0, 0], confidence=1))
    assert high["score"] > low["score"]
    assert low["score"] >= 0.6  # still correct, just capped


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
    assert all(delta <= 0 for delta in grade["masteryDelta"].values())
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
