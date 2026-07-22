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
SYSTEMATIC_INTERPRETATION_VERSION = "focused-systematic-interpretation-v1"
SYSTEMATIC_INTERPRETATION_KEYS = (
    "rate",
    "rhythm",
    "axis",
    "intervals",
    "conduction",
    "st_t",
    "hypertrophy",
    "synthesis",
)
SYSTEMATIC_INTERPRETATION_STEPS = (
    {
        "key": "rate",
        "label": "Rate",
        "prompt": "Estimate the atrial and ventricular rates when each can be determined.",
        "placeholder": "For example: ventricular rate about 72 bpm",
    },
    {
        "key": "rhythm",
        "label": "Rhythm",
        "prompt": "Describe regularity, atrial activity, and the atrioventricular relationship.",
        "placeholder": "Name the rhythm and cite the defining relationship",
    },
    {
        "key": "axis",
        "label": "Axis",
        "prompt": "Classify the frontal QRS axis and cite the limb-lead polarity used.",
        "placeholder": "For example: normal axis; QRS positive in I and aVF",
    },
    {
        "key": "intervals",
        "label": "P waves & PR / intervals",
        "prompt": "Assess P-wave morphology and the PR interval before moving to the QRS.",
        "placeholder": "Describe P waves and report the PR interval when measurable",
    },
    {
        "key": "conduction",
        "label": "QRS & conduction",
        "prompt": "Measure QRS duration, then describe conduction and morphology.",
        "placeholder": "Report QRS width and any supported conduction pattern",
    },
    {
        "key": "st_t",
        "label": "ST-T & QT",
        "prompt": "Review ST segments, T waves, QT/QTc, and their lead distribution.",
        "placeholder": "Describe repolarization and report QT/QTc when available",
    },
    {
        "key": "hypertrophy",
        "label": "Chambers & R-wave progression",
        "prompt": "Check chamber patterns, voltage, and precordial R-wave progression.",
        "placeholder": "State supported findings or that none are identified",
    },
    {
        "key": "synthesis",
        "label": "Final synthesis",
        "prompt": "Prioritize the principal ECG conclusion and its decisive evidence without adding unsupported clinical claims.",
        "placeholder": "One evidence-bounded final interpretation",
    },
)
_RHYTHM_REVIEW_OBJECTIVES = frozenset(
    {
        "sinus_rhythm",
        "atrial_fibrillation",
        "atrial_flutter",
        "supraventricular_tachycardia",
        "wide_complex_tachycardia",
        "bradycardia",
        "av_block_first_degree",
        "av_block_second_degree_mobitz_i",
        "av_block_second_degree_mobitz_ii",
        "av_block_third_degree",
        "paced_rhythm",
        "premature_ventricular_complex",
        "premature_atrial_complex",
    }
)
_AXIS_REVIEW_OBJECTIVES = frozenset(
    {"axis_normal", "left_axis_deviation", "right_axis_deviation"}
)
_CONDUCTION_REVIEW_OBJECTIVES = frozenset(
    {
        "qrs_duration",
        "right_bundle_branch_block",
        "left_bundle_branch_block",
        "incomplete_right_bundle_branch_block",
        "nonspecific_intraventricular_conduction_delay",
        "left_anterior_fascicular_block",
        "left_posterior_fascicular_block",
        "wolff_parkinson_white",
        "paced_rhythm",
    }
)
_REPOLARIZATION_REVIEW_OBJECTIVES = frozenset(
    {
        "st_elevation",
        "st_depression",
        "t_wave_inversion",
        "nonspecific_st_t_change",
        "myocardial_infarction",
        "anterior_mi",
        "inferior_mi",
        "lateral_mi",
        "septal_mi",
        "posterior_mi",
        "myocardial_ischemia",
        "pathologic_q_waves",
        "qtc_prolongation",
        "electrolyte_drug_pattern",
        "pericarditis_pattern",
    }
)
_CHAMBER_REVIEW_OBJECTIVES = frozenset(
    {
        "r_wave_progression",
        "left_ventricular_hypertrophy",
        "right_ventricular_hypertrophy",
        "atrial_enlargement",
    }
)


def _systematic_framework_public() -> dict[str, Any]:
    return {
        "frameworkVersion": SYSTEMATIC_INTERPRETATION_VERSION,
        "frameworkSteps": [dict(step) for step in SYSTEMATIC_INTERPRETATION_STEPS],
    }


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


def _measurement_review(
    values: dict[str, Any], fields: tuple[tuple[str, str, str], ...]
) -> list[str]:
    review: list[str] = []
    for key, label, unit in fields:
        value = values.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        numeric = float(value)
        if not math.isfinite(numeric):
            continue
        review.append(f"{label} {numeric:g}{unit}")
    return review


def _objective_review(
    supported: list[str], allowed: frozenset[str]
) -> list[str]:
    return [concept_label(value) for value in supported if value in allowed]


def reviewed_systematic_framework(packet: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Build a postcommit guide from reviewed labels and packet measurements only."""

    packet = packet if isinstance(packet, dict) else {}
    values = _packet_features(packet)
    supported = list(
        dict.fromkeys(
            str(value)
            for value in (packet.get("supported_objectives") or [])
            if str(value) in CONCEPT_BY_ID
        )
    )
    evidence: dict[str, list[str]] = {
        "rate": _measurement_review(values, (("heart_rate", "Ventricular rate", " bpm"),)),
        "rhythm": _objective_review(supported, _RHYTHM_REVIEW_OBJECTIVES),
        "axis": [
            *_measurement_review(values, (("axis_deg", "Frontal QRS axis", "°"),)),
            *_objective_review(supported, _AXIS_REVIEW_OBJECTIVES),
        ],
        "intervals": _measurement_review(values, (("pr_ms", "PR", " ms"),)),
        "conduction": [
            *_measurement_review(values, (("qrs_ms", "QRS", " ms"),)),
            *_objective_review(supported, _CONDUCTION_REVIEW_OBJECTIVES),
        ],
        "st_t": [
            *_measurement_review(
                values,
                (("qt_ms", "QT", " ms"), ("qtc_ms", "QTc", " ms")),
            ),
            *_objective_review(supported, _REPOLARIZATION_REVIEW_OBJECTIVES),
        ],
        "hypertrophy": _objective_review(supported, _CHAMBER_REVIEW_OBJECTIVES),
        "synthesis": [concept_label(value) for value in supported[:8]],
    }
    rows: list[dict[str, Any]] = []
    for step in SYSTEMATIC_INTERPRETATION_STEPS:
        key = str(step["key"])
        grounded_items = list(dict.fromkeys(evidence.get(key) or []))
        rows.append(
            {
                "key": key,
                "label": str(step["label"]),
                "review": (
                    "Reviewed ECG data: " + "; ".join(grounded_items) + "."
                    if grounded_items
                    else "This ECG record does not independently verify this domain; do not infer it from missing data."
                ),
                "grounded": bool(grounded_items),
            }
        )
    return rows


def _systematic_interpretation_result(
    contract: SubskillTaskContract,
    result: dict[str, Any],
    *,
    systematic_interpretation: dict[str, str] | None,
    case_packet: dict[str, Any] | None,
) -> dict[str, Any]:
    if contract.public.get("subskill") != "synthesize":
        return result
    interpretation = {
        key: (
            str((systematic_interpretation or {}).get(key) or "").strip()[:2_000]
        )
        for key in SYSTEMATIC_INTERPRETATION_KEYS
    }
    complete = all(interpretation.values()) and len(interpretation["synthesis"]) >= 12
    return {
        **result,
        "systematicInterpretationComplete": complete,
        "systematicInterpretation": interpretation,
        "reviewedFramework": reviewed_systematic_framework(case_packet),
    }


def _numeric_measurement_task(
    *, case_id: str, concept: str, variant_index: int, packet: dict[str, Any]
) -> SubskillTaskContract | None:
    if concept == "rate":
        spec = ("heart_rate", "Ventricular rate", "bpm", 20.0, 250.0, 1.0, 5.0)
    elif concept == "qtc_prolongation":
        # The typed response assesses the corrected QT value. The paired trace
        # caliper remains a raw QT interval because QTc is calculated rather
        # than a directly selectable waveform span.
        spec = ("qtc_ms", "QTc", "ms", 150.0, 900.0, 5.0, 35.0)
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
                "Your value is checked against the reviewed ECG measurement. "
                "The expected value and accepted range remain hidden until you check your answer."
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
    case_concept: str,
    case_focus: str,
    subskill: str,
    variant_index: int,
    packet: dict[str, Any],
) -> SubskillTaskContract | None:
    waveform = packet.get("waveform") or {}
    leads = [str(lead) for lead in (waveform.get("leads") or []) if str(lead).strip()]
    if not leads:
        return None

    value = case_concept.casefold()
    preferred = (
        ["V1", "V6"]
        if any(token in value for token in ("bundle", "qrs", "conduction", "fascicular", "wolff"))
        else ["II", "V1"]
        if any(token in value for token in ("rhythm", "fibrillation", "flutter", "tachy", "brady", "block", "ectop"))
        else ["II", "V5"]
        if "qt" in value
        else ["II", "III", "aVF"]
        if "inferior" in value
        else ["V2", "V3", "V4"]
        if any(token in value for token in ("st_", "ischemia", "infar", "_mi", "t_wave"))
        else leads[:2]
    )
    evidence_leads = [lead for lead in preferred if lead in leads][:2] or leads[:2]
    lead_phrase = " and ".join(evidence_leads)
    evidence_domain = _synthesis_evidence(case_concept)

    if subskill == "synthesize":
        role_labels = {
            "evidence": "Waveform evidence to cite",
            "interpretation": "Prioritized ECG conclusion",
            "limit": "Clinical limit to state",
        }
        source_rows = [
            (
                "evidence",
                f"Verify {evidence_domain} on this tracing, including leads {lead_phrase}.",
            ),
            (
                "interpretation",
                "Decide whether that evidence supports the selected topic and lead with that conclusion.",
            ),
            (
                "limit",
                "Keep symptoms, acuity, cause, timing, and treatment outside the ECG-only conclusion.",
            ),
        ]
        prompt = "Match each part of this ECG synthesis to the role it should play."
        boundary = (
            "Use the available ECG leads and the reviewed evidence for the selected topic; "
            "the answer remains hidden until you check your work."
        )
    else:
        information = _application_information(case_concept)
        role_labels = {
            "evidence": "ECG finding to integrate",
            "context": "Context required before a pathway",
            "application": "Bounded clinical application",
        }
        source_rows = [
            (
                "evidence",
                f"First verify {evidence_domain} on this tracing, including leads {lead_phrase}.",
            ),
            ("context", f"Then obtain {information}."),
            (
                "application",
                "Only after integration, select an appropriate pathway without making the ECG prove cause or stability.",
            ),
        ]
        prompt = "Match each item to its role in applying this ECG finding safely."
        boundary = (
            "This checks the evidence-to-context sequence. Full patient-management "
            "decisions are practiced in Clinical Cases."
        )

    ordered_choices = _stable_order(
        case_id,
        f"{subskill}:matching:v{variant_index}:choices",
        list(role_labels.items()),
    )
    choices: list[dict[str, str]] = []
    choice_id_by_role: dict[str, str] = {}
    for index, (role, label) in enumerate(ordered_choices, start=1):
        choice_id = f"choice_{index}"
        choices.append({"id": choice_id, "label": label})
        choice_id_by_role[role] = choice_id

    ordered_rows = _stable_order(
        case_id,
        f"{subskill}:matching:v{variant_index}:rows",
        source_rows,
    )
    rows: list[dict[str, str]] = []
    correct_matches: dict[str, str] = {}
    for index, (role, clause) in enumerate(ordered_rows, start=1):
        row_id = f"statement_{index}"
        rows.append({"id": row_id, "clause": clause})
        correct_matches[row_id] = choice_id_by_role[role]

    return SubskillTaskContract(
        public={
            "kind": "matching",
            "subskill": subskill,
            "variant": variant_index,
            "prompt": prompt,
            "choices": choices,
            "rows": rows,
            "required": True,
            "gradingBoundary": boundary,
            **(_systematic_framework_public() if subskill == "synthesize" else {}),
        },
        correct_answer=None,
        evidence_source=f"packet_grounded_{subskill}_role_matching",
        independently_assessable=False,
        correct_matches=correct_matches,
        grounding={
            "supportedObjective": case_focus,
            "caseConcept": case_concept,
            "evidenceDomain": evidence_domain,
            "waveformLeads": evidence_leads,
            "waveformLeadCount": len(leads),
            "roleSequence": "evidence_interpretation_context",
        },
    )


def grade_subskill_task(
    contract: SubskillTaskContract,
    *,
    answer: str = "",
    matches: dict[str, str] | None = None,
    numeric_value: float | None = None,
    systematic_interpretation: dict[str, str] | None = None,
    case_packet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Deterministically grade one server-authored task and expose keys only postcommit."""

    kind = str(contract.public.get("kind") or "")
    if kind == "single_choice":
        complete = bool(answer)
        correct = bool(complete and answer == contract.correct_answer)
        return _systematic_interpretation_result(
            contract,
            {
                "kind": kind,
                "complete": complete,
                "correct": correct,
                "score": 1.0 if correct else 0.0,
                "submittedAnswer": answer or None,
                "correctAnswer": contract.correct_answer,
            },
            systematic_interpretation=systematic_interpretation,
            case_packet=case_packet,
        )
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
        return _systematic_interpretation_result(
            contract,
            {
                "kind": kind,
                "complete": complete,
                "correct": bool(row_results)
                and all(result["correct"] for result in row_results),
                "score": round(score, 4),
                "rows": row_results,
            },
            systematic_interpretation=systematic_interpretation,
            case_packet=case_packet,
        )
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
    if any(token in value for token in ("bundle", "conduction", "qrs", "axis", "hypertrophy", "enlargement", "fascicular", "wolff")):
        return "symptoms, bedside stability, medicines, a valid prior ECG, and any relevant structural or device records"
    if any(token in value for token in ("rhythm", "fibrillation", "flutter", "tachy", "brady", "block", "ectop", "paced")):
        return "pulse, blood pressure and perfusion, symptoms, medicines, rhythm history, and any valid rhythm-stream evidence"
    return "symptoms, vital signs and perfusion, medicines, a valid prior ECG, and the relevant non-ECG clinical data"


def _synthesis_evidence(concept: str) -> str:
    """Name the reviewed ECG evidence domain without disclosing the case label.

    Focused Practice already tells the learner which campaign target they are
    testing.  These phrases make the synthesis task relevant to that target
    while avoiding use of the hidden case-focus label as an answer cue.
    """

    value = concept.casefold()
    if any(token in value for token in ("bundle", "conduction", "qrs", "fascicular", "preexc", "wolff")):
        return "QRS duration, morphology, and lead distribution"
    if any(
        token in value
        for token in (
            "rhythm",
            "fibrillation",
            "flutter",
            "tachy",
            "brady",
            "block",
            "ectop",
            "premature",
            "paced",
        )
    ):
        return "rate, regularity, atrial activity, and atrioventricular relationship"
    if any(token in value for token in ("st_", "ischemia", "infar", "_mi", "q_wave", "t_wave", "repolar")):
        return "ST-T morphology, anatomic lead distribution, and reciprocal features"
    if any(token in value for token in ("qt", "electrolyte", "drug")):
        return "verified intervals, rate correction, and repolarization morphology"
    if any(token in value for token in ("axis", "hypertrophy", "enlargement", "progression")):
        return "lead polarity, voltage, morphology, and vector distribution"
    return "rate, rhythm, intervals, axis, morphology, and repolarization"


def _synthesis_rows(concept: str, variant_index: int) -> list[tuple[str, str]]:
    """Build homogeneous synthesis choices around common interpretation errors."""

    evidence = _synthesis_evidence(concept)
    bounded = (
        f"Prioritize whether the selected topic is supported, justify that conclusion with the most discriminating {evidence}, and keep acuity, cause, and patient impact as separate clinical questions.",
        f"Lead with whether the selected topic is supported, connect that conclusion to the strongest {evidence}, and state which timing, etiologic, or clinical-significance questions remain unresolved.",
        f"Give the selected-topic conclusion first, cite the decisive {evidence}, and distinguish the ECG interpretation from claims about onset, cause, symptoms, or management.",
    )
    single_feature = (
        f"Prioritize the selected topic when its most familiar feature appears, cite that feature, and use the remaining {evidence} as confirmation rather than as discriminating evidence.",
        f"Lead with the selected-topic conclusion from the strongest single feature, use the remaining {evidence} as supporting context, and defer competing patterns to the detailed review.",
        f"Give the selected-topic conclusion first when one characteristic feature is present, then list other compatible {evidence} without weighing discordant findings.",
    )
    etiologic_extension = (
        f"Prioritize whether the selected topic is supported, justify it with the relevant {evidence}, and add the clinical cause most compatible with that morphology while flagging the attribution for confirmation.",
        f"Lead with the selected-topic conclusion, connect it to the strongest {evidence}, and rank the likely etiology from the pattern distribution while reserving final confirmation for clinical context.",
        f"Give the selected-topic conclusion first, cite the decisive {evidence}, and translate the pattern into the most likely underlying diagnosis while noting that correlation is still needed.",
    )
    inventory_first = (
        "Report rate, rhythm, intervals, axis, morphology, and repolarization in sequence, give the selected topic the same weight as each observation, and leave the overall priority for later context.",
        "Summarize every available ECG feature in acquisition order, avoid ranking the selected topic above the other observations, and let the clinical team decide which finding matters most.",
        "List all measured and machine-reported features before mentioning the selected topic, preserve equal emphasis across the list, and postpone a prioritized conclusion until more context arrives.",
    )
    return [
        ("bounded_synthesis", bounded[variant_index]),
        ("single_feature_priority", single_feature[variant_index]),
        ("etiologic_extension", etiologic_extension[variant_index]),
        ("unprioritized_inventory", inventory_first[variant_index]),
    ]


def _application_information_sets(concept: str) -> tuple[str, str, str, str]:
    """Return one complete and three plausible-but-incomplete context sets."""

    value = concept.casefold()
    complete = _application_information(concept)
    if any(token in value for token in ("qt", "repolar", "electrolyte", "drug")):
        return (
            complete,
            "medicines and interactions, electrolytes, symptoms, and a valid prior ECG",
            "manual QT/QTc and QRS verification, medicines, symptoms, and current electrolytes",
            "manual QT/QTc verification, symptoms, medicines, and a valid prior ECG",
        )
    if any(token in value for token in ("st_", "ischemia", "infar", "_mi", "q_wave")):
        return (
            complete,
            "symptom timing, serial ECGs or a valid prior, and the appropriate non-ECG clinical data",
            "symptom timing, bedside stability, and the appropriate non-ECG clinical data",
            "bedside stability, symptom timing, and serial ECGs or a valid prior",
        )
    if any(token in value for token in ("bundle", "conduction", "qrs", "axis", "hypertrophy", "enlargement", "fascicular", "wolff")):
        return (
            complete,
            "symptoms, medicines, a valid prior ECG, and relevant structural or device records",
            "symptoms, bedside stability, medicines, and relevant structural or device records",
            "symptoms, bedside stability, a valid prior ECG, and relevant structural or device records",
        )
    if any(token in value for token in ("rhythm", "fibrillation", "flutter", "tachy", "brady", "block", "ectop", "paced")):
        return (
            complete,
            "pulse, symptoms, medicines, rhythm history, and any valid rhythm-stream evidence",
            "pulse, blood pressure and perfusion, symptoms, medicines, and rhythm history",
            "pulse, blood pressure and perfusion, symptoms, rhythm history, and rhythm-stream evidence",
        )
    return (
        complete,
        "symptoms, medicines, a valid prior ECG, and the relevant non-ECG clinical data",
        "symptoms, vital signs and perfusion, medicines, and the relevant non-ECG clinical data",
        "symptoms, vital signs and perfusion, a valid prior ECG, and the relevant non-ECG clinical data",
    )


def _application_rows(concept: str, variant_index: int) -> list[tuple[str, str]]:
    """Build near-neighbor clinical-boundary choices without treatment advice."""

    complete, causal_set, timing_set, pathway_set = _application_information_sets(concept)
    bounded = (
        f"Keep the selected topic as a waveform finding; integrate {complete}, then use that combined picture to select an appropriate clinical pathway.",
        f"Document the selected topic as an ECG interpretation; pair it with {complete}, and only then map the finding to an appropriate clinical pathway.",
        f"Separate the waveform-supported topic from the clinical diagnosis; bring in {complete} before deciding which clinical pathway fits.",
    )
    causal_shortcut = (
        f"Use the selected topic as the provisional explanation for the presentation; integrate {causal_set} to decide how strongly that explanation should guide the pathway.",
        f"Document the selected topic as the leading clinical explanation; pair it with {causal_set}, then refine that attribution as the pathway develops.",
        f"Connect the waveform-supported target to the likely clinical diagnosis; bring in {causal_set} before deciding how confidently that diagnosis should guide the pathway.",
    )
    timing_shortcut = (
        f"Keep the selected topic as a waveform finding; integrate {timing_set}, and let pattern prominence guide a provisional estimate of onset until comparison data are available.",
        f"Document the selected topic as an ECG interpretation; pair it with {timing_set}, then use morphology severity to estimate whether the finding is recent.",
        f"Separate the target from the final diagnosis; bring in {timing_set}, and use the degree of abnormality to provisionally place the finding in time.",
    )
    pathway_shortcut = (
        f"Keep the selected topic as a waveform finding; integrate {pathway_set}, select the best-fitting pathway, and add further context if the initial course remains unclear.",
        f"Document the selected topic as an ECG interpretation; pair it with {pathway_set}, then choose a pathway and use later information to refine the choice.",
        f"Separate the target from the clinical diagnosis; bring in {pathway_set}, decide which pathway fits best, and use subsequent context to adjust that decision.",
    )
    return [
        ("bounded_application", bounded[variant_index]),
        ("causal_attribution", causal_shortcut[variant_index]),
        ("timing_from_morphology", timing_shortcut[variant_index]),
        ("incomplete_context", pathway_shortcut[variant_index]),
    ]


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
        subskill == "apply_in_context"
        and variant_index == 1
        and case_packet is not None
    ):
        grounded_matching = _grounded_matching_task(
            case_id=case_id,
            case_concept=case_concept,
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
            "Which reviewed ECG pattern best accounts for this tracing among the target and its close look-alikes?",
            "Select the reviewed pattern that best separates this tracing from the target and its nearby look-alikes.",
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
                "gradingBoundary": "Your answer is checked against reviewed ECG evidence; no AI grades this question.",
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
                "gradingBoundary": "This question focuses on the electrical mechanism; it does not infer symptoms, acuity, cause, or treatment.",
            },
            correct_answer=correct_answer,
            evidence_source="curated_mechanism_task",
            independently_assessable=True,
        )

    if subskill == "synthesize":
        rows = _synthesis_rows(case_concept, variant_index)
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
                "gradingBoundary": "Your choice is checked against a reviewed, evidence-limited synthesis. The complete interpretation sequence matters—not note length alone.",
                **_systematic_framework_public(),
            },
            correct_answer=correct_answer,
            evidence_source="curated_synthesis_task",
            independently_assessable=False,
        )

    if subskill == "apply_in_context":
        rows = _application_rows(case_concept, variant_index)
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
                "gradingBoundary": "This practices the information needed to use an ECG safely. Full management decisions are assessed in Clinical Cases.",
            },
            correct_answer=correct_answer,
            evidence_source="curated_context_boundary_task",
            independently_assessable=False,
        )

    if subskill == "calibrate_confidence":
        prompts = (
            "Choose your confidence before feedback. Calibration is compared with whether your first ECG decision is correct.",
            "Before the answer is revealed, rate how likely your first ECG decision is to be correct.",
            "Choose both your topic decision and certainty; feedback will review how well they align.",
        )
        return SubskillTaskContract(
            public={
                "kind": "confidence_commit",
                "subskill": subskill,
                "variant": variant_index,
                "prompt": prompts[variant_index],
                "options": [],
                "required": True,
                "gradingBoundary": "This answer adds one calibration check; reliable calibration requires repeated, varied ECGs.",
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
