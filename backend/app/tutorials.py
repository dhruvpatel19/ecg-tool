from __future__ import annotations

from typing import Any


# Lessons follow the systematic-read spine and are grounded ONLY in concepts the
# curation actually supports on PTB-XL (chronic/resting). caseConcept names a
# well-covered concept so a representative case exists. Acute STEMI and VT have no
# lesson here — PTB-XL lacks them; they arrive with supplementary datasets. Every
# lesson is auto-gated by reliable-case availability in curriculum.py.
TUTORIALS: list[dict[str, Any]] = [
    # --- Foundations ---
    {
        "id": "orientation",
        "title": "ECG Orientation & Calibration",
        "objectives": ["rate", "normal_ecg"],
        "caseConcept": "normal_ecg",
        "steps": [
            "Confirm calibration, paper speed, time, amplitude, and the 12-lead layout.",
            "Use lead II to connect grid boxes with seconds and millivolts.",
            "Estimate one R-R interval before naming the rate.",
        ],
    },
    {
        "id": "lead-territories",
        "title": "Lead Layout & Territories",
        "objectives": ["normal_ecg"],
        "caseConcept": "normal_ecg",
        "steps": [
            "Separate the six limb leads from the six precordial leads.",
            "Group the contiguous territories: inferior (II, III, aVF), septal (V1-V2), anterior (V3-V4), lateral (I, aVL, V5-V6).",
            "Practice naming which leads 'look at' each region — the map you'll reuse for every localization.",
        ],
    },
    {"id": "rate", "title": "Rate", "objectives": ["rate"], "caseConcept": "normal_ecg", "steps": ["Estimate rate from R-R spacing.", "Compare with grounded rate evidence when available."]},
    {"id": "rhythm-basics", "title": "Rhythm: Sinus, Brady, and Regularity", "objectives": ["sinus_rhythm", "bradycardia"], "caseConcept": "sinus_rhythm", "steps": ["Confirm an upright P before every QRS in lead II.", "Assess regularity, then rate (brady vs normal).", "Name sinus rhythm only when P-QRS relationship is consistent."]},
    # --- Rhythm & ectopy ---
    {"id": "af-flutter", "title": "Atrial Fibrillation & Flutter", "objectives": ["atrial_fibrillation", "atrial_flutter"], "caseConcept": "atrial_fibrillation", "steps": ["Look for absent organized P waves vs sawtooth flutter waves.", "Assess the irregularly-irregular rhythm of AF.", "Estimate the ventricular response rate."]},
    {"id": "svt", "title": "Supraventricular Tachycardia", "objectives": ["supraventricular_tachycardia"], "caseConcept": "supraventricular_tachycardia", "steps": ["Confirm a narrow-complex tachycardia.", "Assess regularity and look for retrograde or hidden P waves.", "Separate SVT from sinus tachycardia by onset and rate."]},
    {"id": "ectopy", "title": "Ectopy: PVCs & PACs", "objectives": ["premature_ventricular_complex", "premature_atrial_complex"], "caseConcept": "premature_ventricular_complex", "steps": ["Spot the early beat and judge whether it is wide (ventricular) or narrow (atrial).", "Look for a compensatory pause and the preceding P wave.", "Describe patterns (isolated, bigeminy) without over-calling."]},
    {"id": "paced", "title": "Paced Rhythm", "objectives": ["paced_rhythm"], "caseConcept": "paced_rhythm", "steps": ["Find the pacing spikes and which chamber they precede.", "Confirm capture (spike followed by the expected complex).", "Recognize the paced QRS morphology so it is not mistaken for a bundle block."]},
    # --- Intervals & AV conduction ---
    {"id": "pr-av-block", "title": "PR Interval & AV Block", "objectives": ["av_block_first_degree", "av_block_second_degree_mobitz_ii", "av_block_third_degree"], "caseConcept": "av_block_first_degree", "steps": ["Measure PR from P onset to QRS onset.", "Decide first-degree (long but constant) vs higher-grade block.", "Name a specific block only with the conduction evidence to support it."]},
    {"id": "qt-qtc", "title": "QT/QTc, Drug & Electrolyte Patterns", "objectives": ["qt_interval", "qtc_prolongation", "electrolyte_drug_pattern"], "caseConcept": "qtc_prolongation", "steps": ["Measure QT in a clear lead and use the rate-corrected QTc.", "Recognize prolongation and common drug/electrolyte contributors.", "Interpret QTc only when correction is available."]},
    # --- QRS & conduction ---
    {"id": "qrs-conduction", "title": "QRS Duration and Conduction", "objectives": ["qrs_duration"], "caseConcept": "right_bundle_branch_block", "steps": ["Measure QRS width.", "Separate duration from morphology."]},
    {"id": "bundle-branch-blocks", "title": "Bundle Branch Blocks", "objectives": ["right_bundle_branch_block", "left_bundle_branch_block", "incomplete_right_bundle_branch_block"], "caseConcept": "right_bundle_branch_block", "steps": ["Use V1 and V6 as anchor leads.", "Separate complete from incomplete by QRS width.", "Avoid over-specific claims without morphology support."]},
    {"id": "fascicular-preexcitation", "title": "Fascicular Blocks & Pre-excitation", "objectives": ["left_anterior_fascicular_block", "left_posterior_fascicular_block", "wolff_parkinson_white"], "caseConcept": "left_anterior_fascicular_block", "steps": ["Tie a fascicular block to its axis shift (LAFB -> left axis; LPFB -> right axis).", "For pre-excitation, look for a short PR with a delta wave.", "Keep claims anchored to axis and PR evidence."]},
    # --- Axis & chambers ---
    {"id": "axis", "title": "Axis", "objectives": ["axis_normal", "left_axis_deviation", "right_axis_deviation"], "caseConcept": "axis_normal", "steps": ["Use limb leads for frontal plane axis.", "Compare with grounded axis measurement if present."]},
    {"id": "hypertrophy", "title": "Chamber Enlargement and Hypertrophy", "objectives": ["left_ventricular_hypertrophy", "right_ventricular_hypertrophy", "atrial_enlargement"], "caseConcept": "left_ventricular_hypertrophy", "steps": ["Apply voltage criteria for ventricular hypertrophy.", "Check P-wave morphology for atrial enlargement.", "Treat single-criterion voltage cautiously."]},
    # --- Ischemia & infarction (established / chronic — PTB-XL's strength) ---
    {"id": "ischemia-st-t", "title": "Ischemic ST-T Changes", "objectives": ["myocardial_ischemia", "st_depression", "t_wave_inversion", "nonspecific_st_t_change"], "caseConcept": "myocardial_ischemia", "steps": ["Find the J point and ST segment, then the T wave.", "Recognize ischemic ST depression and T-wave inversion.", "Separate true ischemic patterns from nonspecific ST-T change."]},
    {"id": "mi-localization", "title": "Established MI & Localization", "objectives": ["myocardial_infarction", "anterior_mi", "inferior_mi", "lateral_mi", "septal_mi", "pathologic_q_waves"], "caseConcept": "anterior_mi", "steps": ["Recognize an old/established infarct by pathologic Q waves and lost R waves.", "Localize by the contiguous lead territory.", "State the territory, not just 'MI'."]},
    # --- Integration ---
    {"id": "integrated-interpretation", "title": "Integrated Clerkship ECG Interpretation", "objectives": ["rate", "sinus_rhythm", "axis_normal", "qrs_duration", "myocardial_infarction"], "caseConcept": None, "steps": ["Work through rate, rhythm, axis, intervals, QRS, ST-T, and synthesis.", "Lead with the most reliable findings and explicitly name uncertainty."]},
]


FRAMEWORKS = [
    {
        "id": "clerkship",
        "title": "Standard Clerkship Framework",
        "steps": ["rate", "rhythm", "axis", "intervals", "conduction/QRS", "ST-T/ischemia", "hypertrophy/chambers", "final synthesis"],
    },
    {
        "id": "hearts",
        "title": "HEARTS Framework",
        "steps": [
            "H: Heart rate and rhythm",
            "E: Electrical axis",
            "A: Atria and intervals",
            "R: R-wave progression and QRS/conduction",
            "T: T waves and ST segments",
            "S: Synthesis",
        ],
    },
]


# Explicit, gradeable click tasks. Each references a REAL parsed-ROI concept
# (atrial_enlargement=P wave, av_block_first_degree=PR, qrs_duration=QRS,
# st_elevation=ST/J point, t_wave_inversion=T wave, qt_interval=QT) on a lead we
# actually parse fiducials for (II, V2, V5). Lessons without a single-ROI target
# (axis, hypertrophy, rhythm survey, etc.) have no click task and use structured submit.
# roiConcept values are NEUTRAL segment-location ids (p_wave, qrs_complex,
# st_segment, t_wave, pr_interval, qt_segment) — "find this part of the beat",
# which is a valid skill on any ECG (the finding is taught separately, grounded
# in labels/measurements).
CLICK_TASKS: dict[str, dict[str, Any]] = {
    "orientation": {"roiConcept": "qrs_complex", "leads": ["II"], "prompt": "Click the QRS complex in lead II."},
    "lead-territories": {"roiConcept": "qrs_complex", "leads": ["V2"], "prompt": "Click the QRS complex in V2 (anterior/septal territory)."},
    "rate": {"roiConcept": "qrs_complex", "leads": ["II"], "prompt": "Click an R wave (QRS) in lead II to anchor the rate."},
    "rhythm-basics": {"roiConcept": "p_wave", "leads": ["II"], "prompt": "Click a P wave in lead II."},
    "pr-av-block": {"roiConcept": "pr_interval", "leads": ["II"], "prompt": "Click within the PR interval in lead II."},
    "qrs-conduction": {"roiConcept": "qrs_complex", "leads": ["V2"], "prompt": "Click the QRS complex in V2 and judge its width."},
    "bundle-branch-blocks": {"roiConcept": "qrs_complex", "leads": ["V2"], "prompt": "Click the QRS complex in V2."},
    "ischemia-st-t": {"roiConcept": "st_segment", "leads": ["V2"], "prompt": "Click the ST segment (J point) in V2."},
    "mi-localization": {"roiConcept": "st_segment", "leads": ["V2"], "prompt": "Click the ST segment in V2."},
    "qt-qtc": {"roiConcept": "qt_segment", "leads": ["II"], "prompt": "Click within the QT interval in lead II."},
}


def _with_task(lesson: dict[str, Any]) -> dict[str, Any]:
    return {**lesson, "clickTask": CLICK_TASKS.get(lesson["id"])}


def list_tutorials() -> list[dict[str, Any]]:
    return [_with_task(lesson) for lesson in TUTORIALS]


def get_tutorial(lesson_id: str) -> dict[str, Any] | None:
    lesson = next((lesson for lesson in TUTORIALS if lesson["id"] == lesson_id), None)
    return _with_task(lesson) if lesson else None
