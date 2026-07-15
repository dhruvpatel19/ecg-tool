"""Deterministic task contracts for independently assessable ECG subskills.

The language model never grades these tasks.  Each contract is generated from
the server-owned campaign slot, an audited ECG label, and a reviewed knowledge
key.  Public contracts omit the answer key; submit-time grading regenerates the
same contract from durable state.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from typing import Any

from .ontology import CONCEPT_BY_ID, PRACTICE_GROUPS, concept_label


STRUCTURED_CHOICE_SUBSKILLS = frozenset(
    {"discriminate", "explain_mechanism", "synthesize", "apply_in_context"}
)


@dataclass(frozen=True)
class SubskillTaskContract:
    public: dict[str, Any]
    correct_answer: str | None
    evidence_source: str
    independently_assessable: bool
    correct_matches: dict[str, str] | None = None
    expected_value: float | None = None
    tolerance: float | None = None
    grounding: dict[str, Any] | None = None


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


# Mechanism distractors should be plausible misconceptions from the same
# electrical domain, not an arbitrary tour through unrelated ECG categories.
# These families supplement the public practice taxonomy where a small group
# (for example QT/QTc or ectopy) would otherwise provide only one distractor.
_MECHANISM_NEIGHBOR_FAMILIES = (
    frozenset({
        "normal_ecg", "rate", "sinus_rhythm", "bradycardia",
        "atrial_fibrillation", "atrial_flutter", "supraventricular_tachycardia",
        "wide_complex_tachycardia", "premature_atrial_complex",
        "premature_ventricular_complex", "paced_rhythm",
    }),
    frozenset({
        "av_block_first_degree", "av_block_second_degree_mobitz_i",
        "av_block_second_degree_mobitz_ii", "av_block_third_degree",
        "wolff_parkinson_white",
    }),
    frozenset({
        "qrs_duration", "right_bundle_branch_block", "left_bundle_branch_block",
        "incomplete_right_bundle_branch_block",
        "nonspecific_intraventricular_conduction_delay",
        "left_anterior_fascicular_block", "left_posterior_fascicular_block",
        "wolff_parkinson_white", "paced_rhythm", "wide_complex_tachycardia",
    }),
    frozenset({
        "axis_normal", "left_axis_deviation", "right_axis_deviation",
        "left_anterior_fascicular_block", "left_posterior_fascicular_block",
    }),
    frozenset({
        "r_wave_progression", "left_ventricular_hypertrophy",
        "right_ventricular_hypertrophy", "atrial_enlargement",
        "left_bundle_branch_block", "right_bundle_branch_block",
    }),
    frozenset({
        "st_elevation", "st_depression", "t_wave_inversion",
        "nonspecific_st_t_change", "myocardial_ischemia", "pathologic_q_waves",
        "pericarditis_pattern", "electrolyte_drug_pattern", "qtc_prolongation",
    }),
    frozenset({
        "myocardial_infarction", "anterior_mi", "inferior_mi", "lateral_mi",
        "septal_mi", "posterior_mi", "pathologic_q_waves", "myocardial_ischemia",
    }),
    frozenset({
        "qt_interval", "qtc_prolongation", "electrolyte_drug_pattern",
        "nonspecific_st_t_change", "t_wave_inversion",
    }),
)


def _mechanism_distractors(
    case_concept: str,
    *,
    contrast_family: set[str],
    variant_index: int,
) -> list[str]:
    """Return three deterministic, electrically adjacent misconception keys."""

    taxonomy_families = tuple(
        frozenset(str(item) for item in group.get("concepts", []))
        for group in PRACTICE_GROUPS
    )
    target_families = [
        family
        for family in (*taxonomy_families, *_MECHANISM_NEIGHBOR_FAMILIES)
        if case_concept in family
    ]

    def score(candidate: str) -> int:
        # The active target/mimic family is the strongest signal; shared
        # electrical taxonomies then rank close mechanisms above generic ones.
        return (4 if candidate in contrast_family else 0) + sum(
            1 for family in target_families if candidate in family
        )

    ranked = sorted(
        (
            candidate
            for candidate in MECHANISM_EXPLANATIONS
            if candidate != case_concept
        ),
        key=lambda candidate: (-score(candidate), concept_label(candidate).casefold()),
    )
    close = [candidate for candidate in ranked if score(candidate) > 0]
    if len(close) >= 3:
        offset = variant_index % len(close)
        return [close[(offset + index) % len(close)] for index in range(3)]
    return (close + [candidate for candidate in ranked if candidate not in close])[:3]


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
    if subskill == "synthesize":
        # Selecting a reviewed synthesis is useful deliberate practice, but it
        # is not the same construct as producing a complete ECG synthesis.
        # Independent synthesis is assessed by Rapid's full structured sweep.
        return False
    # Training can rehearse the information boundary for clinical application,
    # but a resting ECG without a patient vignette cannot independently prove
    # apply-in-context competence. Clinical Decisions owns that evidence lane.
    if subskill == "apply_in_context":
        return False
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


def _stable_order(case_id: str, task_key: str, rows: list[tuple[str, Any]]) -> list[tuple[str, Any]]:
    return sorted(
        rows,
        key=lambda row: hashlib.sha256(
            f"{case_id}:{task_key}:{row[0]}".encode("utf-8")
        ).digest(),
    )


def _packet_features(packet: dict[str, Any]) -> dict[str, Any]:
    plus = packet.get("ptbxl_plus") or {}
    return {**(plus.get("features") or {}), **(plus.get("measurements") or {})}


def _numeric_measurement_task(
    *, case_id: str, concept: str, variant_index: int, packet: dict[str, Any]
) -> SubskillTaskContract | None:
    if concept == "rate":
        spec = ("heart_rate", "Ventricular rate", "bpm", 20.0, 250.0, 1.0, 5.0)
    elif "qt" in concept:
        spec = ("qt_ms", "QT interval", "ms", 150.0, 900.0, 5.0, 35.0)
    elif "av_block" in concept or concept.startswith("pr_"):
        spec = ("pr_ms", "PR interval", "ms", 60.0, 500.0, 5.0, 20.0)
    elif any(token in concept for token in ("qrs", "bundle", "conduction")):
        spec = ("qrs_ms", "QRS duration", "ms", 40.0, 300.0, 5.0, 20.0)
    else:
        return None
    feature, label, unit, minimum, maximum, step, tolerance = spec
    value = _packet_features(packet).get(feature)
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return None
    expected = float(value)
    if not minimum <= expected <= maximum:
        return None
    prompts = (
        f"Measure and enter the {label.lower()} from this ECG.",
        f"What is the best trace-based estimate of the {label.lower()}?",
        f"Use the ECG grid to calculate the {label.lower()}, then enter one value.",
    )
    return SubskillTaskContract(
        public={
            "kind": "numeric_fill_in",
            "subskill": "measure",
            "variant": variant_index,
            "prompt": prompts[variant_index],
            "responseLabel": label,
            "unit": unit,
            "minValue": minimum,
            "maxValue": maximum,
            "step": step,
            "required": True,
            "gradingBoundary": (
                "The server compares this value with the exact packet measurement. "
                "The expected value and tolerance remain hidden until commitment."
            ),
        },
        correct_answer=None,
        evidence_source=f"packet_measurement:{feature}",
        independently_assessable=True,
        expected_value=expected,
        tolerance=tolerance,
        grounding={"packetFeature": feature},
    )


def _grounded_matching_task(
    *,
    case_id: str,
    case_focus: str,
    subskill: str,
    variant_index: int,
    packet: dict[str, Any],
) -> SubskillTaskContract | None:
    supported = {str(value) for value in (packet.get("supported_objectives") or [])}
    waveform = packet.get("waveform") or {}
    leads = [str(lead) for lead in (waveform.get("leads") or []) if str(lead).strip()]
    if case_focus not in supported or not leads:
        return None

    lead_index = int(hashlib.sha256(f"{case_id}:{variant_index}:lead".encode()).hexdigest(), 16) % len(leads)
    lead = leads[lead_index]
    boundary_clauses = (
        "Patient symptoms, bedside stability, cause, and treatment",
        "Acuity, symptom attribution, and a management pathway",
        "Timing, clinical cause, and the next patient-care action",
    )
    source_labels = {
        "finding": "Audited label field",
        "waveform": "Waveform acquisition fact",
        "unsupported": "Not established by this ECG packet",
    }
    ordered_choices = _stable_order(
        case_id,
        f"{subskill}:matching:v{variant_index}:choices",
        list(source_labels.items()),
    )
    choices: list[dict[str, str]] = []
    choice_id_by_source: dict[str, str] = {}
    for index, (source, label) in enumerate(ordered_choices, start=1):
        choice_id = f"choice_{index}"
        choices.append({"id": choice_id, "label": label})
        choice_id_by_source[source] = choice_id

    source_rows = [
        # Keep the pre-commit statement deliberately generic. Naming the
        # reviewed finding here would disclose whether the target is present
        # before the learner commits the paired classification response.
        ("finding", "The packet's reviewed ECG finding label"),
        ("waveform", f"Recorded waveform: {len(leads)} lead{'s' if len(leads) != 1 else ''}, including {lead}"),
        ("unsupported", boundary_clauses[variant_index]),
    ]
    ordered_rows = _stable_order(
        case_id,
        f"{subskill}:matching:v{variant_index}:rows",
        source_rows,
    )
    rows: list[dict[str, str]] = []
    correct_matches: dict[str, str] = {}
    for index, (source, clause) in enumerate(ordered_rows, start=1):
        row_id = f"statement_{index}"
        rows.append({"id": row_id, "clause": clause})
        correct_matches[row_id] = choice_id_by_source[source]

    prompts = (
        "Match each statement to the strongest source this ECG packet can support.",
        "Sort the finding, acquisition fact, and clinical boundary by evidence source.",
        "Map each statement to what comes from the ECG label, waveform, or neither.",
    )
    return SubskillTaskContract(
        public={
            "kind": "matching",
            "subskill": subskill,
            "variant": variant_index,
            "prompt": prompts[variant_index],
            "choices": choices,
            "rows": rows,
            "required": True,
            "gradingBoundary": (
                "Every key is regenerated from this packet's audited objective and waveform lead set. "
                "Correct mappings remain server-only until commitment."
            ),
        },
        correct_answer=None,
        evidence_source="packet_label_waveform_boundary_matching",
        independently_assessable=False,
        correct_matches=correct_matches,
        grounding={
            "supportedObjective": case_focus,
            "waveformLead": lead,
            "waveformLeadCount": len(leads),
            "unsupportedBoundary": "no_patient_context",
        },
    )


def grade_subskill_task(
    contract: SubskillTaskContract,
    *,
    answer: str = "",
    matches: dict[str, str] | None = None,
    numeric_value: float | None = None,
) -> dict[str, Any]:
    """Deterministically grade one server-authored task and expose keys only postcommit."""

    kind = str(contract.public.get("kind") or "")
    if kind == "single_choice":
        complete = bool(answer)
        correct = bool(complete and answer == contract.correct_answer)
        return {
            "kind": kind,
            "complete": complete,
            "correct": correct,
            "score": 1.0 if correct else 0.0,
            "submittedAnswer": answer or None,
            "correctAnswer": contract.correct_answer,
        }
    if kind == "matching":
        submitted = matches or {}
        expected = contract.correct_matches or {}
        public_choice_ids = {
            str(choice.get("id")) for choice in (contract.public.get("choices") or [])
        }
        complete = (
            set(submitted) == set(expected)
            and all(choice_id in public_choice_ids for choice_id in submitted.values())
            and len(set(submitted.values())) == len(expected)
        )
        row_results = [
            {
                "rowId": row_id,
                "submittedChoiceId": submitted.get(row_id),
                "correctChoiceId": correct_choice,
                "correct": bool(complete and submitted.get(row_id) == correct_choice),
            }
            for row_id, correct_choice in expected.items()
        ]
        score = (
            sum(1 for result in row_results if result["correct"]) / len(row_results)
            if row_results else 0.0
        )
        return {
            "kind": kind,
            "complete": complete,
            "correct": bool(row_results) and all(result["correct"] for result in row_results),
            "score": round(score, 4),
            "rows": row_results,
        }
    if kind == "numeric_fill_in":
        minimum = float(contract.public["minValue"])
        maximum = float(contract.public["maxValue"])
        complete = bool(
            isinstance(numeric_value, (int, float))
            and math.isfinite(float(numeric_value))
            and minimum <= float(numeric_value) <= maximum
        )
        expected = contract.expected_value
        tolerance = contract.tolerance
        error = (
            abs(float(numeric_value) - expected)
            if complete and expected is not None else None
        )
        correct = bool(error is not None and tolerance is not None and error <= tolerance)
        score = 1.0 if correct else (
            0.5 if error is not None and tolerance is not None and error <= 2 * tolerance else 0.0
        )
        return {
            "kind": kind,
            "complete": complete,
            "correct": correct,
            "score": score,
            "submittedValue": numeric_value,
            "expectedValue": expected,
            "tolerance": tolerance,
            "unit": contract.public.get("unit"),
            "absoluteError": round(error, 4) if error is not None else None,
        }
    return {"kind": kind, "complete": True, "correct": False, "score": 0.0}


def _application_information(concept: str) -> str:
    """Reviewed information set needed before a resting ECG becomes a decision.

    These are deliberately information-gathering boundaries, not treatment
    recommendations. They let Training assess whether a learner keeps waveform
    evidence separate from symptoms, perfusion, timing, and governed actions.
    """

    value = concept.casefold()
    if any(token in value for token in ("qt", "repolar", "electrolyte", "drug")):
        return "manual QT/QTc and QRS verification, medicines and interactions, electrolytes, symptoms, and a valid prior ECG"
    if any(token in value for token in ("st_", "ischemia", "infar", "_mi", "q_wave")):
        return "symptom timing, bedside stability, serial ECGs or a valid prior, and the appropriate non-ECG clinical data"
    if any(token in value for token in ("rhythm", "fibrillation", "flutter", "tachy", "brady", "block", "ectop", "paced")):
        return "pulse, blood pressure and perfusion, symptoms, medicines, rhythm history, and any valid rhythm-stream evidence"
    if any(token in value for token in ("bundle", "conduction", "qrs", "axis", "hypertrophy", "enlargement")):
        return "symptoms, bedside stability, medicines, a valid prior ECG, and any relevant structural or device records"
    return "symptoms, vital signs and perfusion, medicines, a valid prior ECG, and the relevant non-ECG clinical data"


def build_subskill_task(
    *,
    case_id: str,
    case_concept: str,
    subskill: str,
    case_focus: str,
    contrast_family: set[str],
    variant: int = 0,
    case_packet: dict[str, Any] | None = None,
) -> SubskillTaskContract | None:
    variant_index = max(0, int(variant)) % 3
    if subskill == "measure" and case_packet is not None:
        return _numeric_measurement_task(
            case_id=case_id,
            concept=case_concept,
            variant_index=variant_index,
            packet=case_packet,
        )
    if (
        subskill in {"synthesize", "apply_in_context"}
        and variant_index == 1
        and case_packet is not None
    ):
        grounded_matching = _grounded_matching_task(
            case_id=case_id,
            case_focus=case_focus,
            subskill=subskill,
            variant_index=variant_index,
            packet=case_packet,
        )
        if grounded_matching is not None:
            return grounded_matching
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
            f"discriminate:v{variant_index}",
            [(concept, concept_label(concept)) for concept in choices],
            case_focus,
        )
        prompts = (
            "Which reviewed ECG pattern best accounts for this tracing in the target-versus-mimic set?",
            "Select the audited pattern that best separates this tracing from the target and its nearby look-alikes.",
            "In this comparison set, which reviewed finding is actually supported by the waveform?",
        )
        return SubskillTaskContract(
            public={
                "kind": "single_choice",
                "subskill": subskill,
                "variant": variant_index,
                "prompt": prompts[variant_index],
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
        distractors = _mechanism_distractors(
            case_concept,
            contrast_family=contrast_family,
            variant_index=variant_index,
        )
        rows = [(case_concept, correct)] + [
            (concept, MECHANISM_EXPLANATIONS[concept]) for concept in distractors
        ]
        options, correct_answer = _opaque_choices(
            case_id, f"explain_mechanism:v{variant_index}", rows, case_concept
        )
        prompts = (
            f"Which causal chain best explains the electrical basis of {concept_label(case_concept)}?",
            f"Which reviewed electrical sequence produces {concept_label(case_concept)}?",
            f"Choose the mechanism statement that stays specific to {concept_label(case_concept)} without adding clinical claims.",
        )
        return SubskillTaskContract(
            public={
                "kind": "single_choice",
                "subskill": subskill,
                "variant": variant_index,
                "prompt": prompts[variant_index],
                "options": options,
                "required": True,
                "gradingBoundary": "This reviewed knowledge key explains the ECG construct only; it does not infer symptoms, acuity, etiology, or treatment.",
            },
            correct_answer=correct_answer,
            evidence_source="curated_mechanism_task",
            independently_assessable=True,
        )

    if subskill == "synthesize":
        rows = [
            (
                "bounded_synthesis",
                "Prioritize the finding supported by the waveform, cite the relevant ECG evidence, and state that this resting tracing does not by itself establish symptoms, cause, acuity, or treatment.",
            ),
            (
                "acute_overclaim",
                "Call the tracing acute and unstable, then choose immediate treatment from the ECG alone.",
            ),
            (
                "false_exclusion",
                "Use this one resting tracing to exclude clinically important disease whenever the campaign target is not supported.",
            ),
            (
                "unprioritized_dump",
                "Repeat every available machine label without identifying the finding best supported by the waveform or its evidence limits.",
            ),
        ]
        options, correct_answer = _opaque_choices(
            case_id, f"synthesize:v{variant_index}", rows, "bounded_synthesis"
        )
        prompts = (
            "Which one-line synthesis is strongest while staying inside the resting ECG's evidence boundary?",
            "Which summary prioritizes the supported ECG finding without claiming clinical facts the tracing cannot establish?",
            "Choose the best evidence-bounded takeaway from this ECG.",
        )
        return SubskillTaskContract(
            public={
                "kind": "single_choice",
                "subskill": subskill,
                "variant": variant_index,
                "prompt": prompts[variant_index],
                "options": options,
                "required": True,
                "gradingBoundary": "The server checks a reviewed evidence-limited synthesis key. A long note alone cannot earn this competency receipt.",
            },
            correct_answer=correct_answer,
            evidence_source="curated_synthesis_task",
            independently_assessable=False,
        )

    if subskill == "apply_in_context":
        information = _application_information(case_concept)
        rows = [
            (
                "bounded_application",
                f"Keep the waveform-supported ECG finding separate from the diagnosis, then obtain {information} before choosing a reviewed clinical pathway.",
            ),
            (
                "symptom_causality",
                "Treat the waveform-supported finding as proof that the patient's symptoms are caused by this ECG pattern.",
            ),
            (
                "timing_inference",
                "Use the resting tracing to date onset and infer dynamic change without serial or prior evidence.",
            ),
            (
                "management_from_trace",
                "Choose a medication, procedure, disposition, or resuscitation action from the waveform without first checking bedside context or an approved pathway.",
            ),
        ]
        options, correct_answer = _opaque_choices(
            case_id, f"apply_in_context:v{variant_index}", rows, "bounded_application"
        )
        prompts = (
            "Which next-step statement uses the ECG appropriately in clinical context?",
            "Before a clinical decision, which statement correctly combines this ECG finding with the missing context?",
            "Which response respects what the ECG shows and identifies what must still be checked?",
        )
        return SubskillTaskContract(
            public={
                "kind": "single_choice",
                "subskill": subskill,
                "variant": variant_index,
                "prompt": prompts[variant_index],
                "options": options,
                "required": True,
                "gradingBoundary": "This is a formative source-boundary task. Independent clinical application requires a governed vignette in Clinical Decisions.",
            },
            correct_answer=correct_answer,
            evidence_source="curated_context_boundary_task",
            independently_assessable=False,
        )

    if subskill == "calibrate_confidence":
        prompts = (
            "Commit confidence before feedback. Calibration is scored against whether your blinded target decision is correct.",
            "Before the answer is revealed, rate how likely your blinded ECG decision is to be correct.",
            "Lock in both your target decision and certainty; feedback will score their calibration together.",
        )
        return SubskillTaskContract(
            public={
                "kind": "confidence_commit",
                "subskill": subskill,
                "variant": variant_index,
                "prompt": prompts[variant_index],
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
