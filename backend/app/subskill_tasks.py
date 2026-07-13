"""Deterministic task contracts for independently assessable ECG subskills.

The language model never grades these tasks.  Each contract is generated from
the server-owned campaign slot, an audited ECG label, and a reviewed knowledge
key.  Public contracts omit the answer key; submit-time grading regenerates the
same contract from durable state.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

from .ontology import CONCEPT_BY_ID, PRACTICE_GROUPS, concept_label


@dataclass(frozen=True)
class SubskillTaskContract:
    public: dict[str, Any]
    correct_answer: str | None
    evidence_source: str
    independently_assessable: bool


# Reviewed, bounded causal chains.  These describe the electrical mechanism
# that the named ECG construct represents; they do not infer symptoms, timing,
# etiology, treatment, or an acute clinical diagnosis from a resting tracing.
MECHANISM_EXPLANATIONS: dict[str, str] = {
    "normal_ecg": "Orderly atrial-to-ventricular activation produces expected rhythm, intervals, axis, and repolarization without a supported abnormal pattern.",
    "rate": "Ventricular rate is derived from cycle length: shorter R–R intervals produce a higher beats-per-minute estimate and longer intervals a lower one.",
    "sinus_rhythm": "Sinus-node activation produces a consistent atrial wave before each conducted QRS with a stable atrial-to-ventricular relationship.",
    "atrial_fibrillation": "Disorganized atrial activation removes consistent sinus P waves and variable AV-nodal conduction produces an irregular ventricular response.",
    "atrial_flutter": "A rapid organized atrial macro-reentry circuit produces repetitive atrial activity, with fixed or variable conduction through the AV node.",
    "supraventricular_tachycardia": "A rapid circuit or focus above the ventricles activates them through the His–Purkinje system, usually producing a narrow regular tachycardia.",
    "wide_complex_tachycardia": "Rapid ventricular activation, or supraventricular activation with aberrancy or pre-excitation, prolongs and alters the QRS during tachycardia.",
    "bradycardia": "Longer ventricular cycle lengths reduce the measured ventricular rate; the tracing must then be inspected for the rhythm producing those intervals.",
    "av_block_first_degree": "Atrial impulses conduct to the ventricles with a consistently prolonged AV conduction time, lengthening the PR interval without dropped QRS complexes.",
    "av_block_second_degree_mobitz_i": "Progressive AV-nodal conduction delay lengthens successive PR intervals until an atrial impulse fails to conduct.",
    "av_block_second_degree_mobitz_ii": "Intermittent failure below or within the His–Purkinje system drops a QRS without the progressive PR prolongation of Wenckebach.",
    "av_block_third_degree": "No atrial impulses conduct to the ventricles, so independent atrial and escape pacemakers produce AV dissociation.",
    "axis_normal": "The net frontal-plane ventricular depolarization vector points toward the normal lead-I and aVF quadrants, determining their QRS polarities.",
    "left_axis_deviation": "A leftward frontal-plane ventricular depolarization vector changes the net QRS polarity pattern across limb leads.",
    "right_axis_deviation": "A rightward frontal-plane ventricular depolarization vector changes the net QRS polarity pattern across limb leads.",
    "qrs_duration": "The QRS duration measures how long ventricular depolarization takes; slower or less coordinated activation widens the complex.",
    "right_bundle_branch_block": "Delayed right-ventricular activation after left-sided depolarization creates a widened QRS with characteristic right-precordial and lateral terminal forces.",
    "left_bundle_branch_block": "Delayed left-ventricular activation after right-sided depolarization creates a widened QRS with characteristic right-precordial and lateral morphology.",
    "incomplete_right_bundle_branch_block": "Partial right-sided conduction delay alters terminal right-ventricular forces while QRS duration remains below the complete-block threshold.",
    "nonspecific_intraventricular_conduction_delay": "Ventricular activation is prolonged without satisfying the reviewed morphology contract for a specific bundle-branch pattern.",
    "left_anterior_fascicular_block": "Delayed activation through the left anterior fascicle redirects initial and terminal frontal-plane forces, producing a characteristic leftward axis pattern.",
    "left_posterior_fascicular_block": "Delayed activation through the left posterior fascicle redirects frontal-plane forces toward a characteristic rightward axis pattern after alternatives are excluded.",
    "wolff_parkinson_white": "An accessory atrioventricular pathway pre-excites ventricular myocardium, shortening the PR interval and altering the initial QRS upstroke and width.",
    "paced_rhythm": "An electrical pacing stimulus activates atrial or ventricular myocardium; the chamber and capture pattern depend on what electrical event follows each spike.",
    "premature_ventricular_complex": "An early ventricular focus activates myocardium outside the usual His–Purkinje sequence, producing a premature wide complex with altered morphology.",
    "premature_atrial_complex": "An early atrial focus produces a premature atrial wave that may conduct with a narrow, aberrant, or occasionally blocked ventricular response.",
    "r_wave_progression": "Changing precordial lead orientation relative to ventricular depolarization shifts the balance from predominantly negative to predominantly positive QRS complexes.",
    "left_ventricular_hypertrophy": "Greater left-ventricular electrical forces can increase characteristic QRS voltages and alter repolarization, while the ECG remains an imperfect structural proxy.",
    "right_ventricular_hypertrophy": "Greater right-ventricular electrical forces can redirect precordial and frontal QRS vectors, while the ECG remains an imperfect structural proxy.",
    "atrial_enlargement": "Changed atrial activation mass or conduction alters P-wave duration and morphology; the ECG pattern is a proxy rather than direct chamber measurement.",
    "st_elevation": "A shifted ST segment reflects altered ventricular injury-current or repolarization vectors; the resting tracing alone does not establish acuity or cause.",
    "st_depression": "A downward ST displacement reflects altered ventricular repolarization or reciprocal vectors; morphology and context are required before assigning a cause.",
    "t_wave_inversion": "Reversal of the expected ventricular recovery vector changes T-wave polarity; multiple primary and secondary processes can produce the pattern.",
    "nonspecific_st_t_change": "Ventricular recovery differs from expected morphology without meeting a more specific reviewed repolarization pattern contract.",
    "myocardial_infarction": "Established myocardial injury or scar can alter depolarization and repolarization vectors, producing reviewed infarction-pattern labels without proving acute timing.",
    "anterior_mi": "Anterior myocardial injury or scar can redirect depolarization and recovery forces in anatomically related anterior precordial leads without proving acuity.",
    "inferior_mi": "Inferior myocardial injury or scar can redirect depolarization and recovery forces in leads II, III, and aVF without proving acuity.",
    "lateral_mi": "Lateral myocardial injury or scar can redirect depolarization and recovery forces in lateral limb and precordial leads without proving acuity.",
    "septal_mi": "Septal myocardial injury or scar can alter early depolarization forces in septal precordial leads without proving acuity.",
    "posterior_mi": "Posterior myocardial injury can produce reciprocal anterior forces; the pattern requires appropriate lead and clinical correlation and does not itself date the event.",
    "myocardial_ischemia": "Altered myocardial recovery can change ST segments and T waves, but the resting ECG pattern alone cannot establish the timing or clinical cause.",
    "pathologic_q_waves": "Loss or redirection of early depolarization forces can create abnormal Q waves, often reflecting established scar but not independently proving timing or etiology.",
    "qt_interval": "The QT interval spans ventricular depolarization through repolarization, so both activation duration and recovery time contribute to the measurement.",
    "qtc_prolongation": "Rate correction estimates ventricular recovery duration at a standardized heart rate; prolonged repolarization can reflect multiple acquired or inherited influences.",
    "electrolyte_drug_pattern": "Changes in ion-channel function alter depolarization or repolarization timing and morphology, but a tracing alone cannot identify a specific exposure.",
    "pericarditis_pattern": "Diffuse epicardial inflammation can redirect ST and PR vectors across multiple leads, but the ECG pattern alone cannot establish the clinical diagnosis.",
}


_MECHANISM_DISTRACTOR_ORDER = (
    "atrial_fibrillation",
    "right_bundle_branch_block",
    "qtc_prolongation",
    "left_ventricular_hypertrophy",
    "myocardial_infarction",
    "av_block_third_degree",
    "premature_ventricular_complex",
    "axis_normal",
)


def mechanism_task_available(concept: str) -> bool:
    return concept in MECHANISM_EXPLANATIONS


def discrimination_task_available(concept: str) -> bool:
    groups = [group for group in PRACTICE_GROUPS if concept in group.get("concepts", [])]
    selected = next(
        (group for group in groups if group.get("id") != "normal_ecg"),
        groups[0] if groups else None,
    )
    family = set(selected.get("concepts", [])) if selected else {concept}
    return len(family) >= 2


def training_independent_receipt_available(concept: str, subskill: str) -> bool:
    if subskill == "localize":
        return True
    if subskill == "measure":
        return bool(
            concept == "rate"
            or "qt" in concept
            or "av_block" in concept
            or concept.startswith("pr_")
            or any(token in concept for token in ("qrs", "bundle", "conduction"))
        )
    if subskill == "discriminate":
        return discrimination_task_available(concept)
    if subskill == "explain_mechanism":
        return mechanism_task_available(concept)
    return subskill == "calibrate_confidence"


def _opaque_choices(
    case_id: str,
    task_key: str,
    rows: list[tuple[str, str]],
    correct_key: str,
) -> tuple[list[dict[str, str]], str]:
    ordered = sorted(
        rows,
        key=lambda row: hashlib.sha256(
            f"{case_id}:{task_key}:{row[0]}".encode("utf-8")
        ).digest(),
    )
    options: list[dict[str, str]] = []
    correct_answer = ""
    for index, (key, label) in enumerate(ordered, start=1):
        option_id = f"choice_{index}"
        options.append({"id": option_id, "label": label})
        if key == correct_key:
            correct_answer = option_id
    return options, correct_answer


def build_subskill_task(
    *,
    case_id: str,
    case_concept: str,
    subskill: str,
    case_focus: str,
    contrast_family: set[str],
) -> SubskillTaskContract | None:
    if subskill == "discriminate":
        candidates = [case_focus, case_concept]
        candidates.extend(
            concept for concept in sorted(contrast_family)
            if concept not in candidates and concept in CONCEPT_BY_ID
        )
        choices = list(dict.fromkeys(candidates))[:4]
        if case_focus not in choices or len(choices) < 2:
            return None
        options, correct_answer = _opaque_choices(
            case_id,
            "discriminate",
            [(concept, concept_label(concept)) for concept in choices],
            case_focus,
        )
        return SubskillTaskContract(
            public={
                "kind": "single_choice",
                "subskill": subskill,
                "prompt": "Which reviewed ECG pattern best accounts for this tracing in the target-versus-mimic set?",
                "options": options,
                "required": True,
                "gradingBoundary": "The answer is checked against the audited packet label; no free-text inference or AI grading is used.",
            },
            correct_answer=correct_answer,
            evidence_source="labeled_contrast_task",
            independently_assessable=case_focus in contrast_family,
        )

    if subskill == "explain_mechanism":
        correct = MECHANISM_EXPLANATIONS.get(case_concept)
        if not correct:
            return None
        distractors = [
            concept for concept in _MECHANISM_DISTRACTOR_ORDER
            if concept != case_concept and concept in MECHANISM_EXPLANATIONS
        ][:3]
        rows = [(case_concept, correct)] + [
            (concept, MECHANISM_EXPLANATIONS[concept]) for concept in distractors
        ]
        options, correct_answer = _opaque_choices(
            case_id, "explain_mechanism", rows, case_concept
        )
        return SubskillTaskContract(
            public={
                "kind": "single_choice",
                "subskill": subskill,
                "prompt": f"Which causal chain best explains the electrical basis of {concept_label(case_concept)}?",
                "options": options,
                "required": True,
                "gradingBoundary": "This reviewed knowledge key explains the ECG construct only; it does not infer symptoms, acuity, etiology, or treatment.",
            },
            correct_answer=correct_answer,
            evidence_source="curated_mechanism_task",
            independently_assessable=True,
        )

    if subskill == "calibrate_confidence":
        return SubskillTaskContract(
            public={
                "kind": "confidence_commit",
                "subskill": subskill,
                "prompt": "Commit confidence before feedback. Calibration is scored against whether your blinded target decision is correct.",
                "options": [],
                "required": True,
                "gradingBoundary": "One receipt records a Brier-style calibration observation; durable calibration requires repeated, varied ECGs.",
            },
            correct_answer=None,
            evidence_source="confidence_commit",
            independently_assessable=True,
        )
    return None


def calibration_grade(confidence: int, classification_correct: bool) -> tuple[float, bool]:
    """Return a bounded one-trial calibration score and success threshold.

    Confidence is interpreted as the learner's probability that the committed
    answer is correct.  Low-confidence errors can therefore be calibrated even
    though they remain recognition errors; high-confidence misses are not.
    """
    probability = {1: 0.20, 2: 0.40, 3: 0.60, 4: 0.80, 5: 0.95}[confidence]
    outcome = 1.0 if classification_correct else 0.0
    score = max(0.0, min(1.0, 1.0 - (probability - outcome) ** 2))
    return score, score >= 0.84
