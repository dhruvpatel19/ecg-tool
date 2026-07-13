"""Ten-module guided curriculum backed by the source-traceable product storyboard.

Foundations previews the complete descriptive read. Later modules spiral back to
the same observations for mechanism, pathology discrimination, clinical meaning,
and transfer. The grouping intentionally teaches axis before fascicular block,
ventricular conduction before wide-complex reasoning, and repolarization before
ischemia. Existing /tutorials endpoints remain compatible case selectors.
"""

from __future__ import annotations

from typing import Any

from .ontology import CONCEPT_BY_ID, concept_label
from .tutorials import TUTORIALS

_LESSON_BY_ID = {lesson["id"]: lesson for lesson in TUTORIALS}

# Modules ARE the systematic read: finishing the curriculum in order is learning the
# method. Each module builds on the last; lessons auto-gate by reliable-case availability.
MODULES: list[dict[str, Any]] = [
    {
        "id": "foundations",
        "title": "Foundations of the ECG Read",
        "overview": "Calibration, the 12-lead layout and territories, rate, and basic rhythm — the scaffolding every interpretation hangs on.",
        # The standalone 13-scene module previews leads/rate/rhythm itself; the
        # backend lesson selector remains orientation-only so later pathology
        # modules own each native case lesson exactly once.
        "lessonIds": ["orientation"],
        "prerequisites": [],
    },
    {
        "id": "leads-vectors",
        "title": "Leads, Vectors, Axis & the Normal 12-Lead",
        "overview": "Electrodes versus leads, vector projection, contiguous territories, full frontal axis, R-wave progression, and placement/normal-variant checks.",
        "lessonIds": ["lead-territories", "axis"],
        "prerequisites": ["foundations"],
    },
    {
        "id": "rhythm-ectopy",
        "title": "Rate, Sinus Rhythm, Pauses & Ectopy",
        "overview": "A repeatable rhythm ladder: rate, regularity, sinus source, premature atrial/ventricular beats, escape beats, pauses, patterns, and artifact.",
        "lessonIds": ["rate", "rhythm-basics", "ectopy"],
        "prerequisites": ["foundations"],
    },
    {
        "id": "av-brady",
        "title": "AV Conduction & Bradyarrhythmias",
        "overview": "PR behavior, first- and second-degree patterns, honest 2:1 uncertainty, AV dissociation, escape rhythms, and perfusion-aware bradycardia reasoning.",
        "lessonIds": ["pr-av-block"],
        "prerequisites": ["rhythm-ectopy"],
    },
    {
        "id": "ventricular-conduction",
        "title": "Ventricular Activation, Conduction, Pre-excitation & Pacing",
        "overview": "QRS duration versus morphology, BBB/fascicular mechanisms, pre-excitation, pacing, and secondary ST-T change.",
        "lessonIds": ["qrs-conduction", "bundle-branch-blocks", "fascicular-preexcitation", "paced"],
        "prerequisites": ["leads-vectors", "av-brady"],
    },
    {
        "id": "tachyarrhythmias",
        "title": "Tachyarrhythmias: Narrow, Wide, Regular & Irregular",
        "overview": "Stability first, then mechanism, regularity, width, atrial activity, AF/flutter/SVT, and data-gated wide-complex safety reasoning.",
        "lessonIds": ["af-flutter", "svt"],
        "prerequisites": ["rhythm-ectopy", "ventricular-conduction"],
    },
    {
        "id": "chambers-voltage",
        "title": "Chambers, Voltage & R-Wave Progression",
        "overview": "Atrial morphology, ventricular voltage and axis, LVH/RVH evidence, normal and poor R-wave progression, strain patterns, and false-positive discipline.",
        "lessonIds": ["hypertrophy"],
        "prerequisites": ["leads-vectors", "ventricular-conduction"],
    },
    {
        "id": "repolarization-safety",
        "title": "Repolarization, QT, Electrolytes & Drugs",
        "overview": "ST-T description, baseline/J point, manual QT/QTc, rate correction, wide-QRS confounding, and cautious medication/electrolyte safety links.",
        "lessonIds": ["qt-qtc"],
        "prerequisites": ["ventricular-conduction"],
    },
    {
        "id": "ischemia-infarction",
        "title": "Ischemia, Infarction, Territories & Mimics",
        "overview": "Contiguous and reciprocal patterns, established infarction/localization, common mimics, serial reasoning, and an explicit acute-data boundary.",
        "lessonIds": ["ischemia-st-t", "mi-localization"],
        "prerequisites": ["leads-vectors", "ventricular-conduction", "chambers-voltage", "repolarization-safety"],
    },
    {
        "id": "integration-transfer",
        "title": "Integrated Interpretation & Clinical Transfer",
        "overview": "Prioritized complete reads, machine disagreement, communication, medication safety, clinic/ward/ED transfer, and exact remediation loops.",
        "lessonIds": ["integrated-interpretation"],
        "prerequisites": ["rhythm-ectopy", "av-brady", "ventricular-conduction", "tachyarrhythmias", "chambers-voltage", "repolarization-safety", "ischemia-infarction"],
    },
]


def _lesson_objectives(lesson: dict[str, Any]) -> list[str]:
    return [o for o in lesson.get("objectives", []) if o in CONCEPT_BY_ID]


def _availability(repo: Any, objectives: list[str]) -> int:
    if not objectives:
        return 0
    if hasattr(repo, "group_reliable_count"):
        return repo.group_reliable_count(objectives)
    return 0


def curriculum_view(repo: Any, mastery: dict[str, float] | None = None) -> dict[str, Any]:
    mastery = mastery or {}
    modules_out: list[dict[str, Any]] = []
    for order, module in enumerate(MODULES):
        lessons_out = []
        module_objectives: set[str] = set()
        for lesson_id in module["lessonIds"]:
            lesson = _LESSON_BY_ID.get(lesson_id)
            if not lesson:
                continue
            objectives = _lesson_objectives(lesson)
            module_objectives.update(objectives)
            reliable = _availability(repo, objectives)
            avg_mastery = (
                round(sum(mastery.get(o, 0.25) for o in objectives) / len(objectives), 3) if objectives else 0.0
            )
            lessons_out.append(
                {
                    "id": lesson_id,
                    "title": lesson["title"],
                    "objectives": [{"id": o, "label": concept_label(o)} for o in objectives],
                    "reliableCaseCount": reliable,
                    "available": reliable >= 1,
                    "mastery": avg_mastery,
                }
            )
        module_reliable = _availability(repo, sorted(module_objectives))
        avg = (
            round(sum(mastery.get(o, 0.25) for o in module_objectives) / len(module_objectives), 3)
            if module_objectives
            else 0.0
        )
        modules_out.append(
            {
                "id": module["id"],
                "title": module["title"],
                "overview": module["overview"],
                "order": order,
                "prerequisites": module["prerequisites"],
                "lessons": lessons_out,
                "reliableCaseCount": module_reliable,
                "available": module_reliable >= 1,
                "mastery": avg,
            }
        )
    return {"modules": modules_out}
