from __future__ import annotations

from collections import Counter
import json

from app.clinical import shift
from app.clinical.clinical_grading import grade_clinical_answer
from app.clinical.constants import clock_for
from app.clinical.provenance import assert_longitudinal_pair_provenance
from app.clinical.real_items import (
    AUTHENTIC_LONGITUDINAL_PRIOR_BY_CURRENT,
    LONGITUDINAL_APPLICATION_OBJECTIVES_BY_CURRENT,
)
from app.main import clinical_item_store, clinical_packet
from app.clinical.schemas import ClinicalAnswer


EXPECTED_EPISODES = {
    "948": {
        "prior": "942",
        "item_id": "ptb-948-serial-rhythm-medication-safety",
        "lane": "ed",
    },
    "17769": {
        "prior": "17763",
        "item_id": "ptb-17769-serial-heart-failure-myocardial-injury",
        "lane": "ward",
    },
    "5003": {
        "prior": "4942",
        "item_id": "ptb-5003-serial-bifascicular-syncope",
        "lane": "clinic",
    },
}


def _episode(current_ecg_id: str):
    return next(
        item
        for item in clinical_item_store.list_for_serving(status="harness_pass")
        if item.ecg_id == current_ecg_id
    )


def _session(*, step_answers: list[int] | None = None) -> dict:
    return {
        "learnerId": "demo",
        "sessionId": "cs_longitudinal_transport_test",
        "contextRevealed": True,
        "position": 0,
        "length": 1,
        "tier": "learn",
        "stepAnswers": step_answers or [],
        "firstLook": {"firstLookFinding": "rate_or_rhythm"},
    }


def test_release_bank_contains_three_reserved_longitudinal_pairs() -> None:
    items = clinical_item_store.list_for_serving(status="harness_pass")
    all_waveform_ids = [
        str(ecg_id)
        for item in items
        for ecg_id in (item.ecg_id, item.prior_ecg_id)
        if ecg_id
    ]

    assert AUTHENTIC_LONGITUDINAL_PRIOR_BY_CURRENT == {
        current: episode["prior"] for current, episode in EXPECTED_EPISODES.items()
    }
    assert len(items) == 103
    assert len(all_waveform_ids) == len(set(all_waveform_ids)) == 106
    assert {item.ecg_id for item in items if item.prior_ecg_id} == set(EXPECTED_EPISODES)
    assert not set(AUTHENTIC_LONGITUDINAL_PRIOR_BY_CURRENT.values()) & {
        item.ecg_id for item in items
    }


def test_all_twenty_served_stepwise_cases_have_exact_stage_competencies() -> None:
    stepwise = [
        item
        for item in clinical_item_store.list_for_serving(status="harness_pass")
        if item.question_type == "stepwise"
    ]
    compact_expected = {
        "chb-stepwise": (
            (("rate", "measure"),),
            (("av_block_third_degree", "discriminate"),),
        ),
        "af-ward-stepwise": (
            (("rate", "measure"),),
            (("atrial_fibrillation", "discriminate"),),
        ),
        "svt-ed-stepwise": (
            (("rate", "measure"),),
            (("supraventricular_tachycardia", "discriminate"),),
        ),
        "brady-ed-stepwise": (
            (("rate", "measure"),),
            (("sinus_rhythm", "discriminate"),),
        ),
    }
    longitudinal_expected = {
        "948": (
            (("sinus_rhythm", "synthesize"),),
            (("qt_interval", "apply_in_context"),),
            (("qt_interval", "apply_in_context"),),
        ),
        "17769": (
            (
                ("sinus_rhythm", "synthesize"),
                ("nonspecific_st_t_change", "discriminate"),
            ),
            (("myocardial_ischemia", "apply_in_context"),),
            (("myocardial_ischemia", "apply_in_context"),),
        ),
        "5003": (
            (
                ("right_bundle_branch_block", "synthesize"),
                ("left_anterior_fascicular_block", "synthesize"),
                ("qrs_duration", "discriminate"),
            ),
            (
                ("right_bundle_branch_block", "apply_in_context"),
                ("left_anterior_fascicular_block", "apply_in_context"),
            ),
            (
                ("right_bundle_branch_block", "apply_in_context"),
                ("left_anterior_fascicular_block", "apply_in_context"),
            ),
        ),
    }

    assert len(stepwise) == 20
    assert sum(item.prior_ecg_id is None for item in stepwise) == 17
    assert sum(item.prior_ecg_id is not None for item in stepwise) == 3
    for item in stepwise:
        actual = tuple(
            tuple(
                (competency.objective_id, competency.subskill)
                for competency in step.competencies
            )
            for step in item.steps
        )
        if item.prior_ecg_id:
            expected = longitudinal_expected[item.ecg_id]
        else:
            family = next(
                family
                for family in compact_expected
                if family in item.item_id
            )
            expected = compact_expected[family]
        assert actual == expected, item.item_id
        assert all(step.stage_kind and step.stage_title for step in item.steps), item.item_id


def test_each_longitudinal_pair_is_same_patient_time_ordered_and_validated() -> None:
    for current_id, expected in EXPECTED_EPISODES.items():
        item = _episode(current_id)
        current = clinical_packet(current_id)
        prior = clinical_packet(expected["prior"])
        assert current is not None and prior is not None

        assert item.item_id == expected["item_id"]
        assert item.prior_ecg_id == expected["prior"]
        assert item.situation == expected["lane"]
        assert current["record_identity"]["patientId"] == prior["record_identity"]["patientId"]
        assert assert_longitudinal_pair_provenance(
            current,
            prior,
            current_ecg_id=current_id,
            prior_ecg_id=expected["prior"],
        ) == (current, prior)
        assert current["signal_quality"]["status"] == "acceptable"
        assert prior["signal_quality"]["status"] == "acceptable"
        assert current["signal_quality"]["human_validated"] is True
        assert prior["signal_quality"]["human_validated"] is True


def test_episode_stages_are_complete_and_source_labelled() -> None:
    keyed_positions: list[int] = []
    for current_id in EXPECTED_EPISODES:
        item = _episode(current_id)

        assert item.question_type == "stepwise"
        assert item.display_spec.mode == "stacked_twelve_lead"
        assert [step.stage_kind for step in item.steps] == ["ecg", "reassessment", "handoff"]
        assert len(item.steps) == 3
        assert all(step.stage_title and step.elapsed_label and step.clinical_update for step in item.steps)
        assert {point.source for point in item.steps[0].data_points} == {"source_metadata"}
        assert {
            point.source
            for step in item.steps[1:]
            for point in step.data_points
        } == {"authored_simulation"}
        assert all(sum(option.correct for option in step.options) == 1 for step in item.steps)
        assert item.application_objectives == list(
            LONGITUDINAL_APPLICATION_OBJECTIVES_BY_CURRENT[current_id]
        )
        assert all(step.competencies for step in item.steps)
        assert all(
            option.rationale
            for step in item.steps
            for option in step.options
        )
        assert len(item.options) == 3
        assert [option.id for option in item.options] == [
            "episode-plan-a",
            "episode-plan-b",
            "episode-plan-c",
        ]
        assert sum(option.answer_class == "ideal" for option in item.options) == 1
        keyed_positions.extend(
            next(index for index, option in enumerate(step.options) if option.correct)
            for step in item.steps
        )
        keyed_positions.append(
            next(index for index, option in enumerate(item.options) if option.answer_class == "ideal")
        )

    # Correct placement is deliberately balanced so authored order cannot
    # become an accidental answer key across the three episodes.
    assert Counter(keyed_positions) == {0: 4, 1: 4, 2: 4}


def test_episode_transport_reveals_only_the_active_patient_stage() -> None:
    item = _episode("948")
    correct = [
        next(index for index, option in enumerate(step.options) if option.correct)
        for step in item.steps
    ]

    blind = shift._serve_payload(
        item,
        clinical_packet,
        {**_session(), "contextRevealed": False},
    )["item"]
    blind_json = json.dumps(blind)
    assert "stepwise_state" not in blind
    assert "3.3 mmol/L" not in blind_json
    assert "4.1 mmol/L" not in blind_json

    first = shift._serve_payload(item, clinical_packet, _session())["item"]
    first_json = json.dumps(first)
    assert first["comparison_provenance"] == "same_patient_time_ordered_real_ecgs"
    assert first["stepwise_state"]["active"]["stage_title"] == "Compare the two ECGs"
    assert first["stepwise_state"]["committed"] == []
    assert "3.3 mmol/L" not in first_json
    assert "4.1 mmol/L" not in first_json
    assert "competencies" not in first_json
    assert "rationale" not in first_json
    assert "competency_scores" not in first_json

    second = shift._serve_payload(
        item, clinical_packet, _session(step_answers=correct[:1])
    )["item"]
    second_json = json.dumps(second)
    committed = second["stepwise_state"]["committed"][0]
    assert committed["stage_title"] == "Compare the two ECGs"
    assert committed["data_points"][0]["source"] == "source_metadata"
    assert second["stepwise_state"]["active"]["stage_title"] == "Reassess modifiable risk"
    assert "3.3 mmol/L" in second_json
    assert "4.1 mmol/L" not in second_json

    third = shift._serve_payload(
        item, clinical_packet, _session(step_answers=correct[:2])
    )["item"]
    third_json = json.dumps(third)
    assert third["stepwise_state"]["active"]["stage_title"] == "Build the disposition handoff"
    assert "3.3 mmol/L" in third_json
    assert "4.1 mmol/L" in third_json

    integrated = shift._serve_payload(
        item, clinical_packet, _session(step_answers=correct)
    )["item"]
    assert integrated["stepwise_state"]["active"] is None
    assert integrated["stepwise_state"]["finalChoicesRevealed"] is True
    assert integrated["options"]


def test_on_shift_clock_accounts_for_each_episode_stage() -> None:
    item = _episode("948")
    base_orient, base_decide = clock_for(item.situation, item.question_type)
    clock = shift.clock_spec(item, "shift")

    assert clock["orientSec"] == base_orient
    assert clock["decideSec"] == base_decide + len(item.steps) * shift.STEPWISE_STAGE_SECONDS

    compact = next(
        candidate
        for candidate in clinical_item_store.list_for_serving(status="harness_pass")
        if candidate.question_type == "stepwise" and candidate.prior_ecg_id is None
    )
    compact_orient, compact_decide = clock_for(compact.situation, compact.question_type)
    assert shift.clock_spec(compact, "shift") == {
        "untimed": False,
        "orientSec": compact_orient,
        "decideSec": compact_decide,
    }


def test_longitudinal_grade_keeps_stage_and_final_action_evidence_separate() -> None:
    item = _episode("948")
    packet = clinical_packet(item.ecg_id)
    assert packet is not None
    correct_steps = [
        next(index for index, option in enumerate(step.options) if option.correct)
        for step in item.steps
    ]
    ideal = next(option for option in item.options if option.answer_class == "ideal")
    unsafe = next(option for option in item.options if option.answer_class == "unsafe")

    unsafe_plan = grade_clinical_answer(
        item,
        packet,
        ClinicalAnswer(
            selectedOptionId=unsafe.id,
            stepAnswers=correct_steps,
        ),
    )
    assert unsafe_plan["stepResults"] == [True, True, True]
    assert unsafe_plan["correctObjectives"] == ["sinus_rhythm"]
    assert unsafe_plan["missedObjectives"] == ["qt_interval"]
    assert len(unsafe_plan["stepFeedback"]) == 3
    assert all(row["supportedAnswer"] and row["explanation"] for row in unsafe_plan["stepFeedback"])

    wrong_first = [*correct_steps]
    wrong_first[0] = next(
        index for index, option in enumerate(item.steps[0].options) if not option.correct
    )
    stage_miss = grade_clinical_answer(
        item,
        packet,
        ClinicalAnswer(
            selectedOptionId=ideal.id,
            stepAnswers=wrong_first,
        ),
    )
    assert stage_miss["missedObjectives"] == ["sinus_rhythm"]
    assert stage_miss["correctObjectives"] == ["qt_interval"]


def test_longitudinal_competency_receipts_are_exact_formative_cells() -> None:
    item = _episode("948")
    packet = clinical_packet(item.ecg_id)
    assert packet is not None
    correct_steps = [
        next(index for index, option in enumerate(step.options) if option.correct)
        for step in item.steps
    ]
    unsafe = next(option for option in item.options if option.answer_class == "unsafe")
    answer = ClinicalAnswer(selectedOptionId=unsafe.id, stepAnswers=correct_steps)
    grade = grade_clinical_answer(item, packet, answer)

    events = shift._clinical_competency_events(item, packet, grade, answer)
    by_cell = {(event["concept"], event["subskill"]): event for event in events}
    assert set(by_cell) == {
        ("sinus_rhythm", "synthesize"),
        ("qt_interval", "apply_in_context"),
    }
    assert by_cell[("sinus_rhythm", "synthesize")]["correct"] is True
    assert by_cell[("qt_interval", "apply_in_context")]["correct"] is False
    assert by_cell[("qt_interval", "apply_in_context")]["score"] == 2 / 3


def test_integrated_comparison_choice_preserves_analytic_partial_credit() -> None:
    item = _episode("17769")
    packet = clinical_packet(item.ecg_id)
    assert packet is not None
    correct_steps = [
        next(index for index, option in enumerate(step.options) if option.correct)
        for step in item.steps
    ]
    # This distractor correctly retains the persistent ST-T abnormality but
    # incorrectly says atrial fibrillation persists. Only the exact comparison
    # cell it demonstrates should receive credit.
    correct_steps[0] = 0
    ideal = next(option for option in item.options if option.answer_class == "ideal")
    grade = grade_clinical_answer(
        item,
        packet,
        ClinicalAnswer(selectedOptionId=ideal.id, stepAnswers=correct_steps),
    )

    outcomes = {
        (row["concept"], row["subskill"]): row
        for row in grade["competencyOutcomes"]
    }
    assert outcomes[("sinus_rhythm", "synthesize")]["correct"] is False
    assert outcomes[("nonspecific_st_t_change", "discriminate")]["correct"] is True
    assert outcomes[("myocardial_ischemia", "apply_in_context")]["correct"] is True
    assert grade["correctObjectives"] == [
        "nonspecific_st_t_change",
        "myocardial_ischemia",
    ]
    assert grade["missedObjectives"] == ["sinus_rhythm"]


def test_qt_risk_correction_keeps_exact_credit_despite_unrelated_af_error() -> None:
    item = _episode("948")
    packet = clinical_packet(item.ecg_id)
    assert packet is not None
    step_answers = [
        next(index for index, option in enumerate(step.options) if option.correct)
        for step in item.steps
    ]
    # This branch performs the complete electrolyte/QT-medication work but is
    # wrong only because it defers the separate episode-duration/stroke-risk
    # assessment. The exact QT cell must not inherit that unrelated error.
    step_answers[1] = 1
    ideal = next(option for option in item.options if option.answer_class == "ideal")
    answer = ClinicalAnswer(selectedOptionId=ideal.id, stepAnswers=step_answers)
    grade = grade_clinical_answer(
        item,
        packet,
        answer,
    )

    qt_outcomes = [
        row
        for row in grade["competencyOutcomes"]
        if row["concept"] == "qt_interval"
        and row["subskill"] == "apply_in_context"
    ]
    assert grade["stepResults"] == [True, False, True]
    assert [row["score"] for row in qt_outcomes] == [1.0, 1.0, 1.0]
    assert all(row["correct"] for row in qt_outcomes)
    assert grade["correctObjectives"] == ["sinus_rhythm", "qt_interval"]
    assert grade["missedObjectives"] == []
    events = shift._clinical_competency_events(item, packet, grade, answer)
    qt_event = next(
        event
        for event in events
        if event["concept"] == "qt_interval"
        and event["subskill"] == "apply_in_context"
    )
    assert qt_event["score"] == 1.0
    assert qt_event["correct"] is True
    assert qt_event["stageIndices"] == [1, 2]
