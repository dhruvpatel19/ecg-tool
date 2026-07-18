from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Concept:
    id: str
    label: str
    group: str
    min_student_facing_cases: int = 1
    high_yield: bool = True


CONCEPTS: list[Concept] = [
    Concept("normal_ecg", "Normal ECG", "foundations"),
    Concept("rate", "Rate", "foundations"),
    Concept("sinus_rhythm", "Sinus rhythm", "rhythm"),
    Concept("atrial_fibrillation", "Atrial fibrillation", "rhythm"),
    Concept("atrial_flutter", "Atrial flutter", "rhythm"),
    Concept("supraventricular_tachycardia", "Supraventricular tachycardia", "rhythm"),
    Concept("wide_complex_tachycardia", "Wide-complex tachycardia", "rhythm"),
    Concept("ventricular_tachycardia", "Ventricular tachycardia", "rhythm"),
    Concept(
        "polymorphic_ventricular_tachycardia",
        "Polymorphic ventricular tachycardia",
        "rhythm",
    ),
    Concept("ventricular_flutter", "Ventricular flutter", "rhythm"),
    Concept("ventricular_fibrillation", "Ventricular fibrillation", "rhythm"),
    Concept("bradycardia", "Bradycardia", "rhythm"),
    Concept("av_block_first_degree", "First-degree AV block", "intervals"),
    Concept("av_block_second_degree_mobitz_i", "Mobitz I AV block", "intervals"),
    Concept("av_block_second_degree_mobitz_ii", "Mobitz II AV block", "intervals"),
    Concept("av_block_third_degree", "Third-degree AV block", "intervals"),
    Concept("axis_normal", "Normal axis", "axis"),
    Concept("left_axis_deviation", "Left axis deviation", "axis"),
    Concept("right_axis_deviation", "Right axis deviation", "axis"),
    Concept("qrs_duration", "QRS duration", "conduction"),
    Concept("right_bundle_branch_block", "Right bundle branch block", "conduction"),
    Concept("left_bundle_branch_block", "Left bundle branch block", "conduction"),
    Concept("incomplete_right_bundle_branch_block", "Incomplete right bundle branch block", "conduction"),
    Concept(
        "nonspecific_intraventricular_conduction_delay",
        "Nonspecific intraventricular conduction delay",
        "conduction",
    ),
    Concept("left_anterior_fascicular_block", "Left anterior fascicular block", "conduction"),
    Concept("left_posterior_fascicular_block", "Left posterior fascicular block", "conduction"),
    Concept("wolff_parkinson_white", "Wolff-Parkinson-White (pre-excitation)", "conduction"),
    Concept("paced_rhythm", "Paced rhythm", "rhythm"),
    Concept("premature_ventricular_complex", "Premature ventricular complex (PVC)", "rhythm"),
    Concept("premature_atrial_complex", "Premature atrial complex (PAC)", "rhythm"),
    Concept("r_wave_progression", "R-wave progression", "morphology"),
    Concept("left_ventricular_hypertrophy", "Left ventricular hypertrophy", "hypertrophy"),
    Concept("right_ventricular_hypertrophy", "Right ventricular hypertrophy", "hypertrophy"),
    Concept("atrial_enlargement", "Atrial enlargement", "hypertrophy"),
    Concept("st_elevation", "ST elevation", "st_t_mi"),
    Concept("st_depression", "ST depression", "st_t_mi"),
    Concept("t_wave_inversion", "T-wave inversion", "st_t_mi"),
    Concept("nonspecific_st_t_change", "Nonspecific ST-T change", "st_t_mi"),
    Concept("myocardial_infarction", "Myocardial infarction", "st_t_mi"),
    Concept("anterior_mi", "Anterior MI", "st_t_mi"),
    Concept("inferior_mi", "Inferior MI", "st_t_mi"),
    Concept("lateral_mi", "Lateral MI", "st_t_mi"),
    Concept("septal_mi", "Septal MI", "st_t_mi"),
    Concept("posterior_mi", "Posterior MI", "st_t_mi"),
    Concept("myocardial_ischemia", "Myocardial ischemia (ST-T)", "st_t_mi"),
    Concept("pathologic_q_waves", "Pathologic Q waves", "st_t_mi"),
    Concept("qt_interval", "QT interval", "intervals"),
    Concept("qtc_prolongation", "QTc prolongation", "intervals"),
    Concept("electrolyte_drug_pattern", "Electrolyte/drug pattern", "st_t_mi"),
    Concept("pericarditis_pattern", "Pericarditis pattern", "st_t_mi"),
]


PRACTICE_GROUPS = [
    {
        "id": "normal_ecg",
        "label": "Normal ECG",
        "concepts": ["normal_ecg", "rate", "sinus_rhythm", "axis_normal"],
    },
    {
        "id": "mi_infarction",
        "label": "MI and infarction",
        "concepts": ["myocardial_infarction", "anterior_mi", "inferior_mi", "lateral_mi", "septal_mi", "posterior_mi"],
    },
    {
        "id": "st_t_changes",
        "label": "ST-T changes & ischemia",
        "concepts": [
            "st_depression",
            "t_wave_inversion",
            "myocardial_ischemia",
            "nonspecific_st_t_change",
            "pathologic_q_waves",
            "st_elevation",
            "electrolyte_drug_pattern",
        ],
    },
    {
        "id": "conduction_disturbance",
        "label": "Conduction disturbance",
        "concepts": [
            "qrs_duration",
            "right_bundle_branch_block",
            "left_bundle_branch_block",
            "incomplete_right_bundle_branch_block",
            "left_anterior_fascicular_block",
            "left_posterior_fascicular_block",
            "nonspecific_intraventricular_conduction_delay",
            "wolff_parkinson_white",
            "paced_rhythm",
        ],
    },
    {
        "id": "bundle_branch_block",
        "label": "Bundle branch block",
        "concepts": ["right_bundle_branch_block", "left_bundle_branch_block", "qrs_duration"],
    },
    {
        "id": "fascicular_preexcitation",
        "label": "Fascicular blocks & pre-excitation",
        "concepts": ["left_anterior_fascicular_block", "left_posterior_fascicular_block", "wolff_parkinson_white"],
    },
    {
        "id": "ectopy",
        "label": "Ectopy (PVC / PAC)",
        "concepts": ["premature_ventricular_complex", "premature_atrial_complex"],
    },
    {
        "id": "axis",
        "label": "Axis",
        "concepts": ["axis_normal", "left_axis_deviation", "right_axis_deviation"],
    },
    {
        "id": "hypertrophy",
        "label": "Hypertrophy/chamber enlargement",
        "concepts": ["left_ventricular_hypertrophy", "right_ventricular_hypertrophy", "atrial_enlargement"],
    },
    {
        "id": "bradyarrhythmias",
        "label": "Bradyarrhythmias",
        "concepts": [
            "bradycardia",
            "av_block_first_degree",
            "av_block_second_degree_mobitz_i",
            "av_block_second_degree_mobitz_ii",
            "av_block_third_degree",
        ],
    },
    {
        "id": "tachyarrhythmias",
        "label": "Tachyarrhythmias",
        "concepts": [
            "atrial_fibrillation",
            "atrial_flutter",
            "supraventricular_tachycardia",
            "wide_complex_tachycardia",
            "ventricular_tachycardia",
            "polymorphic_ventricular_tachycardia",
            "ventricular_flutter",
            "ventricular_fibrillation",
        ],
    },
    {"id": "af_flutter", "label": "AF/flutter", "concepts": ["atrial_fibrillation", "atrial_flutter"]},
    {
        "id": "av_block",
        "label": "AV block",
        "concepts": [
            "av_block_first_degree",
            "av_block_second_degree_mobitz_i",
            "av_block_second_degree_mobitz_ii",
            "av_block_third_degree",
        ],
    },
    {"id": "qt_qtc", "label": "QT/QTc", "concepts": ["qt_interval", "qtc_prolongation"]},
]


CONCEPT_BY_ID = {concept.id: concept for concept in CONCEPTS}
DEFAULT_MASTERY = {concept.id: 0.25 for concept in CONCEPTS}


def concept_label(concept_id: str) -> str:
    concept = CONCEPT_BY_ID.get(concept_id)
    return concept.label if concept else concept_id.replace("_", " ").title()
