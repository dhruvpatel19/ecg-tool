"""Versioned competency vocabulary for future learning-mode contracts.

This module is intentionally additive.  The production evidence registry in
``objectives.py`` remains the authority for which objective/subskill pairs can
write mastery today.  This vocabulary gives new task manifests and learner UI
one explicit hierarchy without changing stored identifiers, receipts, or API
payloads.

The three axes below are deliberately independent:

* a topic describes *what* ECG knowledge is being assessed;
* a skill describes the observable learner job;
* Bloom cognitive demand and response format describe task construction.

For example, ``recognize`` can be assessed at an ``apply`` or ``analyze``
demand with either a concise typed response or a single-choice item.  Neither
the Bloom level nor the response widget becomes a mastery skill.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal, Mapping


COMPETENCY_TAXONOMY_VERSION = "2026.07.17"

SkillLifecycle = Literal["current", "planned"]
BloomDemandId = Literal["remember", "understand", "apply", "analyze", "evaluate", "create"]


@dataclass(frozen=True)
class SkillDefinition:
    id: str
    label: str
    description: str
    lifecycle: SkillLifecycle = "current"

    def as_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "lifecycle": self.lifecycle,
        }


@dataclass(frozen=True)
class BloomDemandDefinition:
    id: BloomDemandId
    label: str
    description: str
    order: int

    def as_dict(self) -> dict[str, str | int]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "order": self.order,
        }


@dataclass(frozen=True)
class UmbrellaDefinition:
    id: str
    label: str
    description: str
    order: int

    def as_dict(self) -> dict[str, str | int]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "order": self.order,
        }


@dataclass(frozen=True)
class TopicDefinition:
    id: str
    label: str
    umbrella_id: str
    skill_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "umbrellaId": self.umbrella_id,
            "skillIds": list(self.skill_ids),
        }


CURRENT_EVIDENCE_SKILL_IDS = (
    "recognize",
    "localize",
    "measure",
    "discriminate",
    "explain_mechanism",
    "synthesize",
    "apply_in_context",
    "calibrate_confidence",
)

PLANNED_SKILL_IDS = ("compare_change",)
COMPETENCY_SKILL_IDS = (
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


COMPETENCY_SKILLS: Mapping[str, SkillDefinition] = MappingProxyType({
    "recognize": SkillDefinition(
        id="recognize",
        label="Recognize and name",
        description="Name the ECG finding at the specificity supported by the tracing.",
    ),
    "localize": SkillDefinition(
        id="localize",
        label="Locate the evidence",
        description="Locate the leads, beats, intervals, or regions that support a conclusion.",
    ),
    "measure": SkillDefinition(
        id="measure",
        label="Measure accurately",
        description="Measure ECG values with the correct boundaries, units, and method.",
    ),
    "discriminate": SkillDefinition(
        id="discriminate",
        label="Distinguish alternatives",
        description="Separate a target finding from close mimics using decisive evidence.",
    ),
    "explain_mechanism": SkillDefinition(
        id="explain_mechanism",
        label="Explain the mechanism",
        description="Connect the surface ECG pattern to its electrical mechanism.",
    ),
    "synthesize": SkillDefinition(
        id="synthesize",
        label="Complete an interpretation",
        description="Integrate findings into a prioritized, evidence-limited ECG interpretation.",
    ),
    "compare_change": SkillDefinition(
        id="compare_change",
        label="Compare and describe change",
        description="Compare governed prior or serial ECGs and characterize meaningful change.",
        lifecycle="planned",
    ),
    "apply_in_context": SkillDefinition(
        id="apply_in_context",
        label="Apply in clinical context",
        description="Use ECG evidence with supplied clinical information without exceeding either source.",
    ),
    "calibrate_confidence": SkillDefinition(
        id="calibrate_confidence",
        label="Calibrate certainty",
        description="Match certainty and claim strength to the quality and limits of the evidence.",
    ),
})


BLOOM_COGNITIVE_DEMANDS: Mapping[BloomDemandId, BloomDemandDefinition] = MappingProxyType({
    "remember": BloomDemandDefinition(
        id="remember",
        label="Remember",
        description="Retrieve a fact, definition, threshold, or association.",
        order=1,
    ),
    "understand": BloomDemandDefinition(
        id="understand",
        label="Understand",
        description="Explain, classify, summarize, or interpret supplied information.",
        order=2,
    ),
    "apply": BloomDemandDefinition(
        id="apply",
        label="Apply",
        description="Use a method or rule on an unfamiliar ECG example.",
        order=3,
    ),
    "analyze": BloomDemandDefinition(
        id="analyze",
        label="Analyze",
        description="Differentiate features, relationships, and competing explanations.",
        order=4,
    ),
    "evaluate": BloomDemandDefinition(
        id="evaluate",
        label="Evaluate",
        description="Judge an interpretation or action against ECG evidence and constraints.",
        order=5,
    ),
    "create": BloomDemandDefinition(
        id="create",
        label="Create",
        description="Produce a coherent interpretation, comparison, or clinical synthesis.",
        order=6,
    ),
})


TASK_RESPONSE_FORMATS = (
    "single_choice",
    "multiple_select",
    "fill_blank",
    "short_answer",
    "numeric_entry",
    "roi_selection",
    "lead_selection",
    "matching",
    "structured_interpretation",
    "paired_comparison",
    "clinical_decision",
)


@dataclass(frozen=True)
class TaskLearningMetadata:
    """Independent task-construction axes; this class does not authorize evidence."""

    topic_id: str
    skill_id: str
    cognitive_demand: BloomDemandId
    response_format: str

    def __post_init__(self) -> None:
        if self.topic_id not in COMPETENCY_TOPICS:
            raise ValueError(f"Unknown competency topic: {self.topic_id}")
        if self.skill_id not in COMPETENCY_SKILLS:
            raise ValueError(f"Unknown competency skill: {self.skill_id}")
        if self.cognitive_demand not in BLOOM_COGNITIVE_DEMANDS:
            raise ValueError(f"Unknown Bloom cognitive demand: {self.cognitive_demand}")
        if self.response_format not in TASK_RESPONSE_FORMATS:
            raise ValueError(f"Unknown task response format: {self.response_format}")

    def as_dict(self) -> dict[str, str]:
        return {
            "topicId": self.topic_id,
            "skillId": self.skill_id,
            "cognitiveDemand": self.cognitive_demand,
            "responseFormat": self.response_format,
        }


COMPETENCY_UMBRELLAS: tuple[UmbrellaDefinition, ...] = (
    UmbrellaDefinition(
        id="acquisition_signal",
        label="ECG acquisition and signal",
        description="Determine whether the tracing and lead setup can support interpretation.",
        order=1,
    ),
    UmbrellaDefinition(
        id="systematic_foundations",
        label="Systematic ECG foundations",
        description="Build the measurement and description framework used in every interpretation.",
        order=2,
    ),
    UmbrellaDefinition(
        id="rhythm_ectopy",
        label="Rhythm and ectopy",
        description="Interpret rhythm origin, regularity, atrial activity, ectopy, and escape activity.",
        order=3,
    ),
    UmbrellaDefinition(
        id="av_conduction_bradyarrhythmia",
        label="AV conduction and bradyarrhythmias",
        description="Analyze atrioventricular timing, conduction, and dissociation.",
        order=4,
    ),
    UmbrellaDefinition(
        id="ventricular_conduction_preexcitation_pacing",
        label="Ventricular conduction, pre-excitation and pacing",
        description="Interpret ventricular activation pathways and device-mediated activation.",
        order=5,
    ),
    UmbrellaDefinition(
        id="chamber_forces",
        label="Chamber force patterns",
        description="Interpret electrical force patterns without equating them with structural diagnosis.",
        order=6,
    ),
    UmbrellaDefinition(
        id="repolarization_qt_safety",
        label="Repolarization and QT safety",
        description="Interpret ST-T patterns, QT context, and important confounders.",
        order=7,
    ),
    UmbrellaDefinition(
        id="ischemia_infarction",
        label="Ischemia and infarction patterns",
        description="Analyze distribution, reciprocal evidence, territory, and change over time.",
        order=8,
    ),
    UmbrellaDefinition(
        id="integrated_interpretation_transfer",
        label="Integrated interpretation and clinical transfer",
        description="Synthesize ECG evidence, comparison, uncertainty, and supplied clinical context.",
        order=9,
    ),
)


_PATTERN_SKILLS = COMPETENCY_SKILL_IDS
_SIGNAL_SKILLS = (
    "recognize",
    "localize",
    "measure",
    "discriminate",
    "explain_mechanism",
    "synthesize",
    "compare_change",
    "calibrate_confidence",
)
_EVIDENCE_LIMIT_SKILLS = (
    "discriminate",
    "explain_mechanism",
    "synthesize",
    "compare_change",
    "apply_in_context",
    "calibrate_confidence",
)
_TRANSFER_SKILLS = (
    "discriminate",
    "synthesize",
    "compare_change",
    "apply_in_context",
    "calibrate_confidence",
)


COMPETENCY_TOPIC_DEFINITIONS: tuple[TopicDefinition, ...] = (
        TopicDefinition("calibration_and_signal_quality", "Calibration and signal quality", "acquisition_signal", _SIGNAL_SKILLS),
        TopicDefinition("artifact", "Artifact", "acquisition_signal", _SIGNAL_SKILLS),
        TopicDefinition("lead_placement_and_reversal", "Lead placement and reversal", "acquisition_signal", _SIGNAL_SKILLS),
        TopicDefinition("waveform_components", "Waveform components", "systematic_foundations", _PATTERN_SKILLS),
        TopicDefinition("rate", "Rate", "systematic_foundations", _PATTERN_SKILLS),
        TopicDefinition("rhythm_source_and_regularity", "Rhythm source and regularity", "systematic_foundations", _PATTERN_SKILLS),
        TopicDefinition("frontal_axis", "Frontal axis", "systematic_foundations", _PATTERN_SKILLS),
        TopicDefinition("intervals_and_duration", "Intervals and duration", "systematic_foundations", _PATTERN_SKILLS),
        TopicDefinition("normal_variants", "Normal ECG and normal variants", "systematic_foundations", _PATTERN_SKILLS),
        TopicDefinition("sinus_rhythms", "Sinus rhythms", "rhythm_ectopy", _PATTERN_SKILLS),
        TopicDefinition("atrial_fibrillation", "Atrial fibrillation", "rhythm_ectopy", _PATTERN_SKILLS),
        TopicDefinition("atrial_flutter", "Atrial flutter", "rhythm_ectopy", _PATTERN_SKILLS),
        TopicDefinition("regular_narrow_complex_tachycardia", "Regular narrow-complex tachycardia", "rhythm_ectopy", _PATTERN_SKILLS),
        TopicDefinition("ectopy", "Atrial and ventricular ectopy", "rhythm_ectopy", _PATTERN_SKILLS),
        TopicDefinition("escape_rhythms", "Escape rhythms", "rhythm_ectopy", _PATTERN_SKILLS),
        TopicDefinition("wide_complex_rhythms", "Wide-complex rhythms", "rhythm_ectopy", _PATTERN_SKILLS),
        TopicDefinition("first_degree_av_block", "First-degree AV block", "av_conduction_bradyarrhythmia", _PATTERN_SKILLS),
        TopicDefinition("mobitz_i", "Second-degree AV block: Mobitz I", "av_conduction_bradyarrhythmia", _PATTERN_SKILLS),
        TopicDefinition("second_degree_av_block_indeterminate", "Second-degree AV block: indeterminate or 2:1", "av_conduction_bradyarrhythmia", _PATTERN_SKILLS),
        TopicDefinition("mobitz_ii", "Second-degree AV block: Mobitz II", "av_conduction_bradyarrhythmia", _PATTERN_SKILLS),
        TopicDefinition("complete_av_block", "Complete AV block", "av_conduction_bradyarrhythmia", _PATTERN_SKILLS),
        TopicDefinition("atrioventricular_relationship", "Atrioventricular relationships", "av_conduction_bradyarrhythmia", _PATTERN_SKILLS),
        TopicDefinition("qrs_width_and_ivcd", "QRS width and intraventricular conduction delay", "ventricular_conduction_preexcitation_pacing", _PATTERN_SKILLS),
        TopicDefinition("right_bundle_branch_block", "Right bundle branch block", "ventricular_conduction_preexcitation_pacing", _PATTERN_SKILLS),
        TopicDefinition("left_bundle_branch_block", "Left bundle branch block", "ventricular_conduction_preexcitation_pacing", _PATTERN_SKILLS),
        TopicDefinition("fascicular_block", "Fascicular block", "ventricular_conduction_preexcitation_pacing", _PATTERN_SKILLS),
        TopicDefinition("ventricular_preexcitation", "Ventricular pre-excitation", "ventricular_conduction_preexcitation_pacing", _PATTERN_SKILLS),
        TopicDefinition("paced_rhythms", "Paced rhythms", "ventricular_conduction_preexcitation_pacing", _PATTERN_SKILLS),
        TopicDefinition("atrial_enlargement_pattern", "Atrial enlargement patterns", "chamber_forces", _PATTERN_SKILLS),
        TopicDefinition("left_ventricular_hypertrophy_pattern", "Left ventricular hypertrophy patterns", "chamber_forces", _PATTERN_SKILLS),
        TopicDefinition("right_ventricular_hypertrophy_pattern", "Right ventricular hypertrophy patterns", "chamber_forces", _PATTERN_SKILLS),
        TopicDefinition("structural_inference_limits", "Limits of structural inference", "chamber_forces", _EVIDENCE_LIMIT_SKILLS),
        TopicDefinition("primary_secondary_st_t_change", "Primary and secondary ST-T change", "repolarization_qt_safety", _PATTERN_SKILLS),
        TopicDefinition("st_elevation", "ST elevation", "repolarization_qt_safety", _PATTERN_SKILLS),
        TopicDefinition("st_depression", "ST depression", "repolarization_qt_safety", _PATTERN_SKILLS),
        TopicDefinition("t_wave_abnormality", "T-wave abnormalities", "repolarization_qt_safety", _PATTERN_SKILLS),
        TopicDefinition("nonspecific_st_t_change", "Nonspecific ST-T change", "repolarization_qt_safety", _PATTERN_SKILLS),
        TopicDefinition("qt_qtc", "QT and QTc", "repolarization_qt_safety", _PATTERN_SKILLS),
        TopicDefinition("drug_electrolyte_patterns", "Drug and electrolyte patterns", "repolarization_qt_safety", _PATTERN_SKILLS),
        TopicDefinition("pericarditis_pattern", "Pericarditis-pattern ECG changes", "repolarization_qt_safety", _PATTERN_SKILLS),
        TopicDefinition("ischemic_distribution", "ECG patterns of ischemia", "ischemia_infarction", _PATTERN_SKILLS),
        TopicDefinition("reciprocal_contiguous_leads", "Contiguous and reciprocal lead relationships", "ischemia_infarction", _PATTERN_SKILLS),
        TopicDefinition("established_infarction_patterns", "Established infarction patterns", "ischemia_infarction", _PATTERN_SKILLS),
        TopicDefinition("infarct_territories", "Infarction territories", "ischemia_infarction", _PATTERN_SKILLS),
        TopicDefinition("posterior_involvement", "Posterior involvement", "ischemia_infarction", _PATTERN_SKILLS),
        TopicDefinition("right_ventricular_involvement", "Right ventricular involvement", "ischemia_infarction", _PATTERN_SKILLS),
        TopicDefinition("systematic_interpretation", "Systematic complete interpretation", "integrated_interpretation_transfer", _PATTERN_SKILLS),
        TopicDefinition("machine_read_audit", "Machine interpretation audit", "integrated_interpretation_transfer", _PATTERN_SKILLS),
        TopicDefinition("evidence_limits_and_uncertainty", "Evidence limits and uncertainty", "integrated_interpretation_transfer", _EVIDENCE_LIMIT_SKILLS),
        TopicDefinition("clinical_stability", "Clinical stability assessment", "integrated_interpretation_transfer", _TRANSFER_SKILLS),
        TopicDefinition("immediate_action_and_data_needs", "Immediate action and additional data needs", "integrated_interpretation_transfer", _TRANSFER_SKILLS),
)

COMPETENCY_TOPICS: Mapping[str, TopicDefinition] = MappingProxyType({
    topic.id: topic for topic in COMPETENCY_TOPIC_DEFINITIONS
})


def competency_taxonomy_snapshot() -> dict[str, Any]:
    """Return a deterministic projection for future contracts and tooling."""

    topics_by_umbrella: dict[str, list[dict[str, Any]]] = {
        umbrella.id: [] for umbrella in COMPETENCY_UMBRELLAS
    }
    for topic in COMPETENCY_TOPICS.values():
        topics_by_umbrella[topic.umbrella_id].append(topic.as_dict())

    return {
        "version": COMPETENCY_TAXONOMY_VERSION,
        "skills": [COMPETENCY_SKILLS[skill_id].as_dict() for skill_id in COMPETENCY_SKILL_IDS],
        "bloomCognitiveDemands": [
            definition.as_dict()
            for definition in sorted(BLOOM_COGNITIVE_DEMANDS.values(), key=lambda item: item.order)
        ],
        "responseFormats": list(TASK_RESPONSE_FORMATS),
        "umbrellas": [
            {
                **umbrella.as_dict(),
                "topics": topics_by_umbrella[umbrella.id],
            }
            for umbrella in sorted(COMPETENCY_UMBRELLAS, key=lambda item: item.order)
        ],
    }


def _validate_registry() -> None:
    skill_ids = tuple(COMPETENCY_SKILLS)
    if skill_ids != COMPETENCY_SKILL_IDS:
        raise ValueError("Competency skill order and registry keys must match")
    if set(CURRENT_EVIDENCE_SKILL_IDS) & set(PLANNED_SKILL_IDS):
        raise ValueError("Current and planned competency skills must be disjoint")
    if set(CURRENT_EVIDENCE_SKILL_IDS) | set(PLANNED_SKILL_IDS) != set(COMPETENCY_SKILL_IDS):
        raise ValueError("Every competency skill must have an explicit lifecycle")
    if COMPETENCY_SKILLS["compare_change"].lifecycle != "planned":
        raise ValueError("Comparison must remain planned until governed paired ECG evidence exists")

    umbrella_ids = {umbrella.id for umbrella in COMPETENCY_UMBRELLAS}
    if len(umbrella_ids) != len(COMPETENCY_UMBRELLAS):
        raise ValueError("Competency umbrella identifiers must be unique")
    if len(COMPETENCY_TOPICS) != len(COMPETENCY_TOPIC_DEFINITIONS):
        raise ValueError("Competency topic identifiers must be unique")
    for umbrella_id in umbrella_ids:
        if not any(topic.umbrella_id == umbrella_id for topic in COMPETENCY_TOPICS.values()):
            raise ValueError(f"Competency umbrella has no topics: {umbrella_id}")
    for topic in COMPETENCY_TOPICS.values():
        if topic.umbrella_id not in umbrella_ids:
            raise ValueError(f"Unknown umbrella for competency topic {topic.id}: {topic.umbrella_id}")
        if not topic.skill_ids:
            raise ValueError(f"Competency topic has no applicable skills: {topic.id}")
        unknown_skills = set(topic.skill_ids) - set(COMPETENCY_SKILL_IDS)
        if unknown_skills:
            raise ValueError(f"Unknown skills for competency topic {topic.id}: {sorted(unknown_skills)}")


_validate_registry()
