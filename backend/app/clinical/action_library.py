"""Per-concept management-action library — the DETERMINISTIC safety layer of generation.

Each concept maps answer_class → canonical management actions. The generator selects an option
set from here (correct classes by construction), then the LLM only PARAPHRASES the actions and
writes a varied vignette — so safety/scoring is deterministic while wording/scenario vary.

EDUCATIONAL USE ONLY · authored from standard ACLS/AHA/guideline teaching, NOT individually
clinician-reviewed (matches the content-tables policy). Rotate `seed` for variety. Expand across
the ontology over time; concepts absent here fall back to the free-prompt generator.
"""

from __future__ import annotations

# concept → { answer_class: [canonical action INTENTS the LLM will paraphrase] }
CONCEPT_ACTIONS: dict[str, dict[str, list[str]]] = {
    "atrial_fibrillation": {
        "ideal": [
            "assess stroke risk (CHA2DS2-VASc) and bleeding risk and start anticoagulation if indicated; control the rate only if the ventricular response is fast or symptomatic",
        ],
        "acceptable": [
            "arrange cardiology follow-up and obtain baseline labs to plan an anticoagulation and rate-control strategy",
        ],
        "over_triage_safe": [
            "transfer urgently to the emergency department and activate an acute coronary pathway for the atrial fibrillation itself",
        ],
        "under_triage": [
            "document the atrial fibrillation and defer any stroke-risk assessment to a later visit",
        ],
        "unsafe": [
            "give a rate-controlling drug when the ventricular rate is already slow",
            "discharge the patient with no assessment of stroke risk or anticoagulation",
        ],
    },
    "atrial_flutter": {
        "ideal": ["confirm the rhythm, assess stroke risk and symptoms, and pursue rate control and anticoagulation assessment as for atrial fibrillation"],
        "acceptable": ["arrange cardiology review for a rate-control and anticoagulation plan"],
        "over_triage_safe": ["proceed straight to urgent electrical cardioversion in a stable, rate-controlled patient"],
        "under_triage": ["ignore the flutter and address only unrelated issues"],
        "unsafe": ["discharge without any anticoagulation assessment"],
    },
    "supraventricular_tachycardia": {
        "ideal": ["attempt vagal manoeuvres and, if unsuccessful, give adenosine with continuous monitoring"],
        "acceptable": ["place on a monitor and prepare adenosine while confirming the rhythm"],
        "over_triage_safe": ["proceed directly to sedation and synchronized cardioversion in a stable patient"],
        "under_triage": ["order routine outpatient labs and defer treatment of the ongoing tachycardia"],
        "unsafe": ["treat as atrial fibrillation with an intravenous calcium-channel blocker without confirming the rhythm"],
    },
    "bradycardia": {  # stable sinus bradycardia
        "ideal": ["assess symptoms and hemodynamic stability, review rate-slowing medications and reversible causes, and monitor or arrange follow-up as indicated"],
        "acceptable": ["obtain basic labs and observe on monitoring while evaluating for reversible causes"],
        "over_triage_safe": ["prepare transcutaneous pacing and escalate to intensive-care monitoring in a stable patient"],
        "under_triage": ["discharge with no evaluation because the rhythm is sinus"],
        "unsafe": ["give atropine or place a temporary pacemaker for stable, asymptomatic sinus bradycardia", "start an AV-nodal blocking drug"],
    },
    "av_block_first_degree": {
        "ideal": ["recognize isolated first-degree AV block as usually benign, review AV-nodal medications, and continue routine care"],
        "acceptable": ["note the finding and arrange routine follow-up"],
        "over_triage_safe": ["admit for continuous monitoring for the first-degree AV block alone"],
        "under_triage": [],
        "unsafe": ["admit for urgent pacemaker evaluation for isolated first-degree AV block", "attribute unrelated syncope to the first-degree block and escalate"],
    },
    "av_block_third_degree": {  # symptomatic complete heart block
        "ideal": ["apply transcutaneous pacing pads, check pulse and blood pressure at the bedside, and call cardiology for pacing"],
        "acceptable": ["give atropine while readying transcutaneous pacing and calling for help"],
        "over_triage_safe": [],
        "under_triage": ["continue routine monitoring and order morning labs"],
        "unsafe": ["reassure and discharge the patient", "give an AV-nodal blocking drug"],
    },
    "qtc_prolongation": {  # genuinely prolonged, regular rhythm
        "ideal": ["review and stop QT-prolonging medications and check and correct electrolytes (K, Mg, Ca), then reassess the QT"],
        "acceptable": ["arrange follow-up with telemetry while reviewing medications and electrolytes"],
        "over_triage_safe": ["transfer to the emergency department for immediate cardiology activation for the prolonged QT alone"],
        "under_triage": ["make no changes and recheck the ECG at a routine future visit"],
        "unsafe": ["start or continue a QT-prolonging antiarrhythmic drug", "give intravenous magnesium for torsades when no torsades has occurred"],
    },
    "left_ventricular_hypertrophy": {
        "ideal": ["correlate the LVH pattern with blood pressure and clinical context and arrange appropriate outpatient evaluation (e.g., echocardiography) and risk-factor management"],
        "acceptable": ["arrange routine outpatient follow-up and blood-pressure assessment"],
        "over_triage_safe": ["refer to the emergency department for the LVH pattern"],
        "under_triage": ["dismiss the tracing entirely with no follow-up"],
        "unsafe": ["start antihypertensive therapy on the ECG voltage alone without any blood-pressure data"],
    },
    "right_bundle_branch_block": {
        "ideal": ["recognize the RBBB pattern, compare with any prior ECG, and manage based on symptoms and context rather than the block alone"],
        "acceptable": ["note the conduction finding and arrange routine follow-up"],
        "over_triage_safe": ["admit for monitoring for an isolated RBBB"],
        "under_triage": [],
        "unsafe": ["treat the wide QRS as a life-threatening ventricular rhythm and give antiarrhythmics"],
    },
    "left_bundle_branch_block": {
        "ideal": ["compare with a prior ECG to judge whether the LBBB is old, and manage based on symptoms/context; recognize that LBBB limits ECG interpretation of ischemia"],
        "acceptable": ["arrange follow-up and obtain prior ECGs for comparison"],
        "over_triage_safe": ["activate the acute coronary pathway for a chronic LBBB with no acute symptoms"],
        "under_triage": ["ignore the LBBB and its implications for ischemia interpretation"],
        "unsafe": ["treat the wide QRS as ventricular tachycardia in a stable patient"],
    },
    "st_depression": {  # chronic, resting
        "ideal": ["interpret the ST depression in context, compare with a prior ECG, and evaluate for ischemia appropriately without assuming an acute event"],
        "acceptable": ["obtain a prior ECG for comparison and arrange appropriate outpatient ischemia evaluation"],
        "over_triage_safe": ["activate the cath lab for the resting ST depression with no symptoms"],
        "under_triage": ["call the ST depression normal and take no further action"],
        "unsafe": ["give antiplatelet/anticoagulant therapy for a presumed acute coronary syndrome based on the resting ECG alone"],
    },
    "normal_ecg": {
        "ideal": ["recognize the ECG as normal and continue routine care with no additional cardiac work-up"],
        "acceptable": ["document the normal ECG and address the presenting issue"],
        "over_triage_safe": ["order urgent cardiology evaluation despite a normal ECG and no symptoms"],
        "under_triage": [],
        "unsafe": ["start cardiac medication based on a normal ECG"],
    },
}

# Rotated clinical framings — WHY the ECG was obtained. Drives scenario variety.
CLINICAL_FRAMES: list[str] = [
    "a routine pre-operative clearance ECG",
    "a medication-review visit",
    "a telemetry finding on the ward",
    "an evaluation for nonspecific fatigue and mild exertional dyspnea",
    "an annual primary-care check-up",
    "a pre-participation screening ECG",
    "a daily inpatient ECG on the ward",
    "an ED visit for a non-cardiac complaint with an incidental ECG",
    "an outpatient cardiology follow-up",
    "a new-patient intake evaluation",
]


def _pick(items: list[str], seed: int) -> str:
    return items[seed % len(items)] if items else ""


def has_actions(concept: str) -> bool:
    return concept in CONCEPT_ACTIONS


def select_frame(seed: int) -> str:
    return CLINICAL_FRAMES[seed % len(CLINICAL_FRAMES)]


def select_options(concept: str, seed: int) -> list[tuple[str, str]]:
    """Return [(answer_class, action_intent)] — one ideal + rotated distractors. Classes are FIXED
    (correct by construction); the seed rotates which distractors/wordings appear for variety."""
    lib = CONCEPT_ACTIONS[concept]
    out: list[tuple[str, str]] = [("ideal", _pick(lib["ideal"], seed))]
    distractor_classes = [c for c in ("unsafe", "under_triage", "over_triage_safe", "acceptable") if lib.get(c)]
    chosen: list[str] = []
    if "unsafe" in distractor_classes:
        chosen.append("unsafe")  # always include a clearly-unsafe option
    rest = [c for c in distractor_classes if c != "unsafe"]
    if rest:
        r = seed % len(rest)
        rotated = rest[r:] + rest[:r]
        chosen.extend(rotated[:2])  # two rotated distractor classes → varies the option set
    for i, cls in enumerate(chosen):
        out.append((cls, _pick(lib[cls], seed + i + 1)))
    return out
