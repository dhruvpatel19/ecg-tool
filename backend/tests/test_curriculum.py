"""Structural integrity of the tutorial/module taxonomy (no corpus needed).

Guards the rebuilt lesson spine: every objective is a real concept, no lesson teaches
a PTB-XL-absent concept, and click-tasks/modules stay consistent with the lesson list.
"""

from __future__ import annotations

from app.curriculum import MODULES
from app.ontology import CONCEPT_BY_ID
from app.tutorials import CLICK_TASKS, TUTORIALS

_LESSON_IDS = {lesson["id"] for lesson in TUTORIALS}

# Concepts PTB-XL cannot support as student-facing (0 reliable cases); they belong to
# supplementary datasets / a 'coming soon' state, never to a lesson's objectives.
_PTBXL_ABSENT = {"wide_complex_tachycardia", "pericarditis_pattern", "r_wave_progression"}


def test_every_lesson_objective_and_case_concept_is_known() -> None:
    for lesson in TUTORIALS:
        assert lesson["objectives"], f"{lesson['id']}: no objectives"
        for objective in lesson["objectives"]:
            assert objective in CONCEPT_BY_ID, f"{lesson['id']}: unknown objective {objective}"
        case_concept = lesson.get("caseConcept")
        assert case_concept is None or case_concept in CONCEPT_BY_ID, f"{lesson['id']}: unknown caseConcept {case_concept}"


def test_no_lesson_teaches_a_ptbxl_absent_concept() -> None:
    for lesson in TUTORIALS:
        leak = _PTBXL_ABSENT & set(lesson["objectives"])
        assert not leak, f"{lesson['id']} teaches PTB-XL-absent concept(s): {leak}"


def test_click_tasks_reference_real_lessons() -> None:
    for lesson_id in CLICK_TASKS:
        assert lesson_id in _LESSON_IDS, f"click task references unknown lesson {lesson_id}"


def test_modules_cover_every_lesson_exactly_once_with_valid_prereqs() -> None:
    assert len(MODULES) == 10, "the source-audited guided-learning spine has ten dependency-driven modules"
    module_lessons = [lid for module in MODULES for lid in module["lessonIds"]]
    for lid in module_lessons:
        assert lid in _LESSON_IDS, f"module references unknown lesson {lid}"
    assert set(module_lessons) == _LESSON_IDS, "every lesson must belong to a module"
    assert len(module_lessons) == len(set(module_lessons)), "a lesson appears in more than one module"
    module_ids = {module["id"] for module in MODULES}
    module_order = {module["id"]: order for order, module in enumerate(MODULES)}
    for order, module in enumerate(MODULES):
        for prereq in module["prerequisites"]:
            assert prereq in module_ids, f"{module['id']}: unknown prerequisite {prereq}"
            assert module_order[prereq] < order, f"{module['id']}: prerequisite must come first"
