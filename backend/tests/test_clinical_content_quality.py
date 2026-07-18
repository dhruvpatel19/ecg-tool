"""Focused item-writing safeguards for the real Clinical case bank."""

from __future__ import annotations

from app.clinical.real_items import (
    REAL_AUTHORED_ITEMS,
    _rate_distractor_values,
    authored_content_quality_failures,
)


EXPECTED_OPTION_CONTRACT = {
    "ptb-8911-chb-stepwise": [
        ("chb_bedside", "ideal", None, ("bedside_now", "pacing_pads", "call_help")),
        ("chb_ready", "ideal", None, ("twelve_lead", "tcp_ready")),
        ("chb_atropine", "acceptable", None, ("atropine", "pacing_pads", "call_help")),
        ("chb_later", "under_triage", None, ()),
        ("chb_home", "unsafe", None, ()),
    ],
    "ptb-1919-svt-action": [
        ("svt_vagal", "ideal", None, ("vagal_maneuver", "adenosine", "continuous_monitoring")),
        ("svt_shock", "over_triage_safe", None, ()),
        ("svt_af", "under_triage", None, ()),
        ("svt_wait", "unsafe", None, ()),
    ],
    "ptb-3-normal-triage": [
        ("normal_routine", "ideal", "routine", ()),
        ("normal_workup", "over_triage_safe", "workup", ()),
        ("normal_emergency", "unsafe", "act", ()),
    ],
    "ptb-28-qtc-medication": [
        ("qtc_verify", "ideal", None, ("hold_qt_drugs", "check_electrolytes")),
        ("qtc_mag", "over_triage_safe", None, ()),
        ("qtc_ignore", "unsafe", None, ()),
    ],
    "ptb-2-brady-clinic-triage": [
        ("brady_review", "ideal", "workup", ()),
        ("brady_ignore", "under_triage", "routine", ()),
        ("brady_emergency", "over_triage_safe", "act", ()),
    ],
    "ptb-330-af-ward-stepwise": [
        ("af_assess", "ideal", None, ("anticoagulation_assessment",)),
        ("af_more_blocker", "unsafe", None, ()),
        ("af_shock", "over_triage_safe", None, ()),
    ],
    "ptb-307-slow-af-medication": [
        ("slow_af_review", "ideal", None, ("anticoagulation_assessment",)),
        ("slow_af_block", "unsafe", None, ()),
        ("slow_af_ignore", "under_triage", None, ()),
    ],
    "ptb-299-lvh-context-mcq": [
        ("lvh_correlate", "ideal", None, ()),
        ("lvh_emergency", "unsafe", None, ()),
        ("lvh_normal", "under_triage", None, ()),
    ],
    "ptb-1173-svt-ed-stepwise": [
        ("svt_step_vagal", "ideal", None, ("vagal_maneuver", "adenosine", "continuous_monitoring")),
        ("svt_step_shock", "over_triage_safe", None, ()),
        ("svt_step_home", "unsafe", None, ()),
    ],
    "ptb-3267-svt-ed-triage": [
        ("svt_triage_treat", "ideal", "workup", ("vagal_maneuver", "adenosine", "continuous_monitoring")),
        ("svt_triage_shock", "over_triage_safe", "act", ()),
        ("svt_triage_routine", "unsafe", "routine", ()),
    ],
    "ptb-567-af-rvr-ed-triage": [
        ("af_triage_assess", "ideal", "workup", ("rate_control", "anticoagulation_assessment")),
        ("af_triage_shock", "over_triage_safe", "act", ()),
        ("af_triage_home", "unsafe", "routine", ()),
    ],
    "ptb-959-chb-ed-triage": [
        ("chb_triage_act", "ideal", "act", ("bedside_now", "pacing_pads", "call_help")),
        ("chb_triage_labs", "under_triage", "workup", ()),
        ("chb_triage_home", "unsafe", "routine", ()),
    ],
    "ptb-12-brady-ed-stepwise": [
        ("brady_step_assess", "ideal", None, ("bedside_now", "continuous_monitoring")),
        ("brady_step_pace", "over_triage_safe", None, ()),
        ("brady_step_home", "unsafe", None, ()),
    ],
}


def _option_contract(item):
    return [
        (
            option.id,
            option.answer_class,
            option.value,
            tuple(option.required_safety_tokens),
        )
        for option in item.options
    ]


def test_all_thirteen_selectable_templates_pass_the_authored_quality_gate() -> None:
    selectable = [item for item in REAL_AUTHORED_ITEMS if item.options]

    assert len(selectable) == 13
    assert {item.item_id for item in selectable} == set(EXPECTED_OPTION_CONTRACT)
    assert authored_content_quality_failures(selectable) == []


def test_reauthoring_preserves_answer_classes_values_and_safety_tokens() -> None:
    by_id = {item.item_id: item for item in REAL_AUTHORED_ITEMS}

    assert {
        item_id: _option_contract(by_id[item_id])
        for item_id in EXPECTED_OPTION_CONTRACT
    } == EXPECTED_OPTION_CONTRACT


def test_quality_gate_rejects_obvious_or_nonparallel_distractors() -> None:
    item = next(
        candidate.model_copy(deep=True)
        for candidate in REAL_AUTHORED_ITEMS
        if candidate.item_id == "ptb-1919-svt-action"
    )
    item.options[-1].text = "Ignore the rhythm."

    failures = authored_content_quality_failures([item])

    assert any("fragment-like" in failure for failure in failures)
    assert any("gives away its weakness" in failure for failure in failures)


def test_quality_gate_rejects_diagnosis_revealed_in_the_vignette() -> None:
    item = next(
        candidate.model_copy(deep=True)
        for candidate in REAL_AUTHORED_ITEMS
        if candidate.item_id == "ptb-567-af-rvr-ed-triage"
    )
    item.stem = "The ECG shows atrial fibrillation during an emergency assessment."

    failures = authored_content_quality_failures([item])

    assert any("names the ECG answer" in failure for failure in failures)


def test_quality_gate_rejects_unmapped_or_unattributed_stepwise_stages() -> None:
    item = next(
        candidate.model_copy(deep=True)
        for candidate in REAL_AUTHORED_ITEMS
        if candidate.item_id == "ptb-1173-svt-ed-stepwise"
    )
    # A malformed future stepwise item must not bypass stage validation merely
    # because its integrated-decision options are also absent.
    item.options = []
    item.steps[0].competencies = []
    item.steps[1].stage_title = None

    failures = authored_content_quality_failures([item])

    assert any(
        "step-1: every served stepwise stage requires exact competency mappings"
        in failure
        for failure in failures
    )
    assert any(
        "step-2: every served stepwise stage requires explicit stage kind and title"
        in failure
        for failure in failures
    )


def test_stepwise_rate_distractors_are_distinct_and_clinically_adjacent() -> None:
    for measured_rate in (38, 47, 63, 165):
        distractors = _rate_distractor_values(measured_rate, 2)

        assert len(distractors) == len(set(distractors)) == 2
        assert measured_rate not in distractors
        assert all(20 <= value <= 240 for value in distractors)
        assert min(abs(value - measured_rate) for value in distractors) <= 30
