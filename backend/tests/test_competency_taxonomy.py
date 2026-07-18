from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.competency_taxonomy import (
    BLOOM_COGNITIVE_DEMANDS,
    COMPETENCY_SKILL_IDS,
    COMPETENCY_SKILLS,
    COMPETENCY_TAXONOMY_VERSION,
    COMPETENCY_TOPICS,
    COMPETENCY_UMBRELLAS,
    CURRENT_EVIDENCE_SKILL_IDS,
    PLANNED_SKILL_IDS,
    TASK_RESPONSE_FORMATS,
    TaskLearningMetadata,
    competency_taxonomy_snapshot,
)
from app.objectives import SUBSKILLS


def test_versioned_skill_registry_preserves_current_evidence_ids() -> None:
    assert CURRENT_EVIDENCE_SKILL_IDS == SUBSKILLS
    assert PLANNED_SKILL_IDS == ("compare_change",)
    assert COMPETENCY_SKILL_IDS == (
        "recognize",
        "localize",
        "measure",
        "discriminate",
        "explain_mechanism",
        "synthesize",
        "compare_change",
        "apply_in_context",
        "calibrate_confidence",
    )
    assert COMPETENCY_SKILLS["compare_change"].lifecycle == "planned"
    assert "identify" not in COMPETENCY_SKILLS


def test_skill_registry_uses_one_canonical_learner_vocabulary() -> None:
    assert {skill_id: definition.label for skill_id, definition in COMPETENCY_SKILLS.items()} == {
        "recognize": "Recognize and name",
        "localize": "Locate the evidence",
        "measure": "Measure accurately",
        "discriminate": "Distinguish alternatives",
        "explain_mechanism": "Explain the mechanism",
        "synthesize": "Complete an interpretation",
        "compare_change": "Compare and describe change",
        "apply_in_context": "Apply in clinical context",
        "calibrate_confidence": "Calibrate certainty",
    }


def test_taxonomy_has_explicit_clinical_umbrellas_topics_and_skill_links() -> None:
    assert len(COMPETENCY_UMBRELLAS) == 9
    assert len(COMPETENCY_TOPICS) >= 45
    umbrella_ids = {definition.id for definition in COMPETENCY_UMBRELLAS}

    for topic in COMPETENCY_TOPICS.values():
        assert topic.umbrella_id in umbrella_ids
        assert topic.skill_ids
        assert set(topic.skill_ids) <= set(COMPETENCY_SKILL_IDS)

    assert COMPETENCY_TOPICS["mobitz_i"].umbrella_id == "av_conduction_bradyarrhythmia"
    assert COMPETENCY_TOPICS["mobitz_ii"].umbrella_id == "av_conduction_bradyarrhythmia"
    assert COMPETENCY_TOPICS["second_degree_av_block_indeterminate"].id != "mobitz_ii"
    assert COMPETENCY_TOPICS["structural_inference_limits"].umbrella_id == "chamber_forces"
    assert "compare_change" in COMPETENCY_TOPICS["ischemic_distribution"].skill_ids


def test_bloom_demand_and_response_format_are_not_mastery_skills() -> None:
    assert set(BLOOM_COGNITIVE_DEMANDS).isdisjoint(COMPETENCY_SKILLS)
    assert set(TASK_RESPONSE_FORMATS).isdisjoint(COMPETENCY_SKILLS)

    concise = TaskLearningMetadata(
        topic_id="atrial_fibrillation",
        skill_id="recognize",
        cognitive_demand="apply",
        response_format="short_answer",
    )
    analytical = TaskLearningMetadata(
        topic_id="atrial_fibrillation",
        skill_id="recognize",
        cognitive_demand="analyze",
        response_format="single_choice",
    )

    assert concise.skill_id == analytical.skill_id
    assert concise.cognitive_demand != analytical.cognitive_demand
    assert concise.response_format != analytical.response_format
    assert concise.as_dict() == {
        "topicId": "atrial_fibrillation",
        "skillId": "recognize",
        "cognitiveDemand": "apply",
        "responseFormat": "short_answer",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("topic_id", "unknown_topic"),
        ("skill_id", "identify"),
        ("cognitive_demand", "hard"),
        ("response_format", "giant_dropdown"),
    ),
)
def test_task_learning_metadata_fails_closed_for_unknown_axis_values(field: str, value: str) -> None:
    values = {
        "topic_id": "atrial_fibrillation",
        "skill_id": "recognize",
        "cognitive_demand": "apply",
        "response_format": "short_answer",
    }
    values[field] = value
    with pytest.raises(ValueError):
        TaskLearningMetadata(**values)  # type: ignore[arg-type]


def test_snapshot_is_versioned_and_keeps_bloom_metadata_separate() -> None:
    snapshot = competency_taxonomy_snapshot()
    assert snapshot["version"] == COMPETENCY_TAXONOMY_VERSION
    assert [item["id"] for item in snapshot["skills"]] == list(COMPETENCY_SKILL_IDS)
    assert [item["id"] for item in snapshot["bloomCognitiveDemands"]] == [
        "remember",
        "understand",
        "apply",
        "analyze",
        "evaluate",
        "create",
    ]
    assert sum(len(umbrella["topics"]) for umbrella in snapshot["umbrellas"]) == len(COMPETENCY_TOPICS)


def test_frontend_skill_labels_match_the_backend_contract() -> None:
    source_path = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "src"
        / "lib"
        / "learning"
        / "skillLabels.ts"
    )
    source = source_path.read_text(encoding="utf-8")
    version_match = re.search(r'COMPETENCY_TAXONOMY_VERSION = "([^"]+)"', source)
    assert version_match and version_match.group(1) == COMPETENCY_TAXONOMY_VERSION

    label_block = source.split("COMPETENCY_SKILL_LABELS = {", 1)[1].split("} as const", 1)[0]
    frontend_labels = dict(re.findall(r'^\s{2}([a-z_]+): "([^"]+)",?$', label_block, re.MULTILINE))
    assert frontend_labels == {
        skill_id: COMPETENCY_SKILLS[skill_id].label for skill_id in COMPETENCY_SKILL_IDS
    }
