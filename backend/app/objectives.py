"""Versioned educational-objective registry shared by all learning modes.

Case concepts describe what the corpus can support. Educational objectives are
narrower learner jobs emitted by the production guided curriculum. Keeping the
two identifiers separate prevents a normal tracing used for lead mapping from
masquerading as pathology-recognition evidence.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from .ingest.dangerous_arrhythmia import SOURCE_FS as DANGEROUS_ARRHYTHMIA_FS
from .ingest.source_contract import KNOWN_SOURCES
from .ontology import CONCEPTS, CONCEPT_BY_ID
from .source_policy import packet_allows_learning_evidence

REGISTRY_VERSION = "2026.07.19"

SUBSKILLS = (
    "recognize",
    "localize",
    "measure",
    "discriminate",
    "explain_mechanism",
    "synthesize",
    "apply_in_context",
    "calibrate_confidence",
)

TASKS_BY_SUBSKILL: dict[str, tuple[str, ...]] = {
    "recognize": ("classification", "feature_bundle", "normal_or_abnormal", "fill_blank"),
    "localize": ("lead_selection", "point", "region", "bounding_box", "territory_map"),
    "measure": ("caliper", "numeric_entry", "boundary_selection", "formula"),
    "discriminate": ("target_mimic_compare", "paired_ecg", "matching", "feature_sort"),
    "explain_mechanism": ("mechanism_sequence", "matching", "fill_blank", "short_explanation"),
    "synthesize": ("structured_sweep", "prioritize", "evidence_limited_synthesis"),
    "apply_in_context": ("clinical_decision", "information_needed", "stepwise_branch"),
    "calibrate_confidence": ("confidence_commit", "claim_ceiling", "not_assessable"),
}


# Every objective currently emitted from a production guided handoff. A test
# compares this set with the TypeScript module registry so drift fails loudly.
GUIDED_OBJECTIVE_IDS = (
    "anterior_lateral_localization", "artifact", "atrial_enlargement", "atrial_fibrillation",
    "atrial_flutter", "av_block_2_to_1", "av_block_first_degree",
    "av_block_second_degree_mobitz_i", "av_block_third_degree", "av_conduction_mixed",
    "av_relationship", "axis", "brady_context", "bradycardia", "bradycardia_with_pulse",
    "bundle_activation", "chamber_chronic_context", "chamber_pattern_mixed",
    "chamber_voltage_projection", "chest_pain_ecg_transfer", "contiguous_reciprocal_st_pattern",
    "ectopy", "ectopy_timing", "electrolyte_drug_pattern", "escape_rhythm",
    "frontal_lead_map", "inferior_right_sided_extension", "integrated_capstone",
    "integrated_chest_pain", "integrated_interpretation", "integrated_medication_qt",
    "integrated_wide_qrs_device", "interpretation_framework_mapping",
    "irregular_narrow_tachycardia", "ischemia_claim_layers", "ischemia_mimic_discrimination",
    "ivcd_claim_strength", "lead_anatomy", "lead_placement", "lead_projection", "lead_territories",
    "left_anterior_fascicular_block", "left_bundle_branch_block", "left_ventricular_hypertrophy",
    "lvh_chronic_context", "machine_audit_conduction", "machine_read_audit", "medication_qt_review",
    "mobitz_ii_vs_blocked_pac", "nonischemic_st_t_comparison", "normal_ecg", "paced_rhythm",
    "palpitations_tachycardia_transfer", "pathologic_q_waves", "pause_escape",
    "polymorphic_artifact", "poor_r_wave_progression", "posterior_mi", "pr_qrs_boundaries",
    "pr_sequence", "precordial_placement", "preexcited_atrial_fibrillation",
    "primary_secondary_repolarization", "prioritized_ecg_synthesis", "qrs_duration",
    "qrs_width_morphology", "qt_interval", "qtc_prolongation", "r_wave_progression",
    "rate", "repolarization_boundaries", "repolarization_qt_mixed",
    "resuscitation_source_boundary", "rhythm_basics", "rhythm_regularities",
    "right_bundle_branch_block", "right_ventricular_hypertrophy", "secondary_repolarization",
    "serial_ecg_comparison", "sinus_rhythm", "sinus_vs_svt",
    "st_depression_t_inversion_differential", "st_t_morphology", "svt_atrial_timing",
    "syncope_bradycardia_transfer", "tachyarrhythmia_mixed", "tachycardia_matrix",
    "tachycardia_with_pulse", "ventricular_conduction_mixed", "wide_complex_tachycardia",
    "wide_qrs_qt_confound", "wolff_parkinson_white",
    "foundations_waveform_landmarks", "foundations_calibration",
    "foundations_signal_quality", "foundations_rate",
    "foundations_atrial_source", "foundations_pr_qrs",
    "foundations_recovery", "foundations_twelve_lead_navigation",
    "foundations_axis", "foundations_systematic_sweep",
)

# These objectives were emitted by earlier Guided curricula but are no longer
# executable handoffs: both require a governed prior/current ECG pair, which the
# installed corpus does not currently provide. Keep them in the registry so
# previously stored learning records remain interpretable without advertising a
# destination that cannot truthfully assess the requested skill.
RETIRED_GUIDED_OBJECTIVE_IDS = frozenset({
    "ecg_comparison",
    "integrated_prior_comparison",
})

# Neutral waveform targets can produce valid trace-native evidence without
# asserting a diagnosis. They are registered separately from pathology concepts
# and Guided handoff objectives so stored evidence is never invisible.
NEUTRAL_WAVEFORM_OBJECTIVES = frozenset({"qrs_complex"})

# These trace-native foundations appeared in earlier Guided curricula and have
# valid student evidence in existing learning records. They remain canonical so
# a registry update can never silently orphan earned work.
LEGACY_FOUNDATIONAL_OBJECTIVE_IDS = frozenset({
    "ecg_grid_calibration",
    "pr_interval",
    "waveform_components",
})

# Additive objective ids for the rebuilt native Foundations module. They are
# deliberately distinct from historical concepts: old lesson completion can be
# displayed as prior guided practice, but it cannot be silently promoted into a
# new objective's independent or retained evidence.
FOUNDATIONS_OBJECTIVE_IDS = frozenset({
    "foundations_waveform_landmarks",
    "foundations_calibration",
    "foundations_signal_quality",
    "foundations_rate",
    "foundations_atrial_source",
    "foundations_pr_qrs",
    "foundations_recovery",
    "foundations_twelve_lead_navigation",
    "foundations_axis",
    "foundations_systematic_sweep",
})

FOUNDATIONAL_OBJECTIVE_IDS = (
    LEGACY_FOUNDATIONAL_OBJECTIVE_IDS | FOUNDATIONS_OBJECTIVE_IDS
)

_FOUNDATIONAL_SUBSKILLS: dict[str, tuple[str, ...]] = {
    "ecg_grid_calibration": ("measure", "explain_mechanism", "calibrate_confidence"),
    "pr_interval": ("localize", "measure", "explain_mechanism", "calibrate_confidence"),
    "waveform_components": ("recognize", "localize", "discriminate", "explain_mechanism", "calibrate_confidence"),
    "foundations_waveform_landmarks": ("localize", "discriminate", "explain_mechanism"),
    "foundations_calibration": ("localize", "measure", "discriminate", "explain_mechanism", "calibrate_confidence"),
    "foundations_signal_quality": ("localize", "discriminate", "calibrate_confidence"),
    "foundations_rate": ("localize", "measure", "discriminate", "explain_mechanism"),
    "foundations_atrial_source": ("localize", "discriminate", "explain_mechanism", "calibrate_confidence"),
    "foundations_pr_qrs": ("localize", "measure", "discriminate", "calibrate_confidence"),
    "foundations_recovery": ("localize", "measure", "discriminate", "explain_mechanism", "synthesize", "calibrate_confidence"),
    "foundations_twelve_lead_navigation": (
        "recognize",
        "localize",
        "discriminate",
        "explain_mechanism",
        "synthesize",
        "calibrate_confidence",
    ),
    "foundations_axis": ("localize", "discriminate", "explain_mechanism", "calibrate_confidence"),
    "foundations_systematic_sweep": ("localize", "measure", "discriminate", "explain_mechanism", "synthesize", "calibrate_confidence"),
}

# Case-family aliases describe where a future server grader could obtain a
# suitable representation. They do not themselves unlock grading; every v2
# Foundations objective remains formative until its reviewed manifest and
# server-owned scorer are connected below.
_FOUNDATIONS_CASE_MAPPINGS: dict[str, tuple[tuple[str, ...], str]] = {
    "foundations_waveform_landmarks": (("normal_ecg",), "waveform_fundamentals"),
    "foundations_calibration": (("normal_ecg",), "waveform_fundamentals"),
    "foundations_signal_quality": (("normal_ecg",), "signal_quality"),
    "foundations_rate": (("rate",), "foundations"),
    "foundations_atrial_source": (("sinus_rhythm",), "rhythm"),
    "foundations_pr_qrs": (
        ("normal_ecg", "av_block_first_degree", "qrs_duration"),
        "intervals",
    ),
    "foundations_recovery": (("normal_ecg", "qtc_prolongation"), "repolarization"),
    "foundations_twelve_lead_navigation": (("normal_ecg",), "lead_vectors"),
    "foundations_axis": (
        ("axis_normal", "left_axis_deviation", "right_axis_deviation"),
        "axis",
    ),
    "foundations_systematic_sweep": (("normal_ecg",), "integration"),
}

# Explicit compatibility additions are preferable to silently remapping
# historical evidence onto a different clinical skill. Each pair remains a
# truthful task on an eligible waveform and is now part of the versioned
# registry contract.
_SUBSKILL_ADDITIONS: dict[str, frozenset[str]] = {
    "ectopy": frozenset({"apply_in_context"}),
    "ischemia_mimic_discrimination": frozenset({"localize"}),
    "normal_ecg": frozenset({"localize"}),
    "qrs_duration": frozenset({"localize"}),
    "resuscitation_source_boundary": frozenset({"synthesize"}),
    "tachyarrhythmia_mixed": frozenset({"localize", "measure"}),
}


@dataclass(frozen=True)
class ObjectiveDefinition:
    id: str
    label: str
    domain: str
    case_concepts: tuple[str, ...]
    allowed_subskills: tuple[str, ...]
    task_templates: dict[str, tuple[str, ...]]
    evidence_ceiling: str = "eligible_real_case"
    unavailable_reason: str | None = None
    version: str = REGISTRY_VERSION

    def as_api(self) -> dict[str, Any]:
        value = asdict(self)
        value["caseConcepts"] = list(value.pop("case_concepts"))
        value["allowedSubskills"] = list(value.pop("allowed_subskills"))
        value["taskTemplates"] = {key: list(items) for key, items in value.pop("task_templates").items()}
        value["evidenceCeiling"] = value.pop("evidence_ceiling")
        value["unavailableReason"] = value.pop("unavailable_reason")
        return value


Alias = tuple[re.Pattern[str], tuple[str, ...], str]

_ALIASES: tuple[Alias, ...] = (
    (re.compile(r"lead_(territor|anatomy|placement|projection)|frontal_lead_map|precordial_placement|r_wave_progression"), ("normal_ecg",), "lead_vectors"),
    (re.compile(r"^axis$|axis_"), ("axis_normal", "left_axis_deviation", "right_axis_deviation"), "axis"),
    (re.compile(r"pr_qrs_boundaries|pr_sequence"), ("av_block_first_degree",), "av_conduction"),
    (re.compile(r"av_block_2_to_1|mobitz_ii_vs_blocked_pac|av_conduction|av_relationship"), ("av_block_second_degree_mobitz_ii", "av_block_first_degree"), "av_conduction"),
    (re.compile(r"syncope_bradycardia|bradycardia_with_pulse|brady_context|escape_rhythm|pause_escape"), ("bradycardia",), "rhythm"),
    (re.compile(r"ectopy|premature"), ("premature_ventricular_complex", "premature_atrial_complex"), "rhythm"),
    (re.compile(r"rhythm_basics|rhythm_regularities"), ("sinus_rhythm",), "rhythm"),
    (re.compile(r"qrs_width_morphology|ventricular_conduction|ivcd|bundle_activation|machine_audit_conduction"), ("qrs_duration", "right_bundle_branch_block", "left_bundle_branch_block"), "conduction"),
    (re.compile(r"integrated_wide_qrs_device|wide_complex|device"), ("right_bundle_branch_block", "qrs_duration"), "conduction"),
    (re.compile(r"tachycardia_with_pulse|palpitations_tachycardia|tachyarrhythmia|tachycardia_matrix|irregular_narrow"), ("atrial_fibrillation", "supraventricular_tachycardia", "atrial_flutter"), "tachyarrhythmia"),
    (re.compile(r"sinus_vs_svt|svt_atrial_timing"), ("supraventricular_tachycardia",), "tachyarrhythmia"),
    (re.compile(r"chamber|voltage|poor_r_wave|lvh_chronic"), ("left_ventricular_hypertrophy", "right_ventricular_hypertrophy", "atrial_enlargement"), "chambers"),
    (re.compile(r"repolarization|st_t_morphology|primary_secondary|secondary_repolarization|nonischemic_st_t|st_depression_t_inversion"), ("nonspecific_st_t_change", "st_depression", "t_wave_inversion"), "repolarization"),
    (re.compile(r"medication_qt|integrated_medication_qt|wide_qrs_qt|qtc|qt_"), ("qtc_prolongation", "qt_interval"), "qt_safety"),
    (re.compile(r"chest_pain|ischemia|contiguous_reciprocal|inferior_right_sided|anterior_lateral"), ("myocardial_ischemia", "anterior_mi", "inferior_mi"), "ischemia"),
    (re.compile(r"infarct|posterior_mi|pathologic_q|mi$"), ("myocardial_infarction", "pathologic_q_waves", "anterior_mi"), "infarction"),
    (re.compile(r"interpretation_framework|prioritized_ecg|integrated_interpretation|integrated_capstone|machine_read_audit"), ("normal_ecg",), "integration"),
    (re.compile(r"integrated_prior_comparison|ecg_comparison|serial_ecg_comparison"), ("normal_ecg",), "comparison"),
    (re.compile(r"artifact|polymorphic_artifact"), ("normal_ecg",), "signal_quality"),
)

_FORMATIVE_ONLY = {
    "artifact": "Artifact-specific scored geometry is not available in the current corpus.",
    "polymorphic_artifact": "A resting ECG cannot establish a transient polymorphic rhythm; use a reviewed simulation.",
    "ecg_comparison": "A valid paired prior/current source is required for comparison mastery.",
    "serial_ecg_comparison": "True serial ECG pairs are not connected.",
    "integrated_prior_comparison": "True paired prior/current ECGs are not connected.",
    "resuscitation_source_boundary": "Source selection is teachable, but ACLS mastery requires a reviewed rhythm stream and algorithm.",
    "preexcited_atrial_fibrillation": "Both AF and pre-excitation evidence must coexist in a reviewed rhythm stream.",
    "r_wave_progression": "No reliable Tier A/B R-wave-progression case is available in the active corpus.",
    "poor_r_wave_progression": "No reliable Tier A/B poor-R-wave-progression case is connected; a normal tracing may teach lead order but cannot prove pathology recognition.",
    "pericarditis_pattern": "No reliable Tier A/B pericarditis-pattern case is available in the active corpus.",
    **{
        objective_id: (
            "Native Foundations practice is formative until its reviewed case manifest "
            "and server-owned analytic grader are connected."
        )
        for objective_id in FOUNDATIONS_OBJECTIVE_IDS
    },
}

# Canonical concepts for which the automated-screened Clinical bank contains an
# explicit downstream decision objective.  Keep this intentionally small and in
# lock-step with real_items.APPLICATION_OBJECTIVES_BY_SCENARIO: incidental ECG
# findings and trace-only click/audit cases must not gain a *Clinical action
# receipt*.  Training may expose a formative ``apply_in_context`` information-
# boundary task for any mapped ECG objective, but it cannot issue independent
# application evidence without a governed vignette and action policy.
CLINICAL_APPLICATION_CONCEPTS = frozenset({
    "atrial_fibrillation",
    "av_block_third_degree",
    "bradycardia",
    "left_anterior_fascicular_block",
    "left_ventricular_hypertrophy",
    "myocardial_ischemia",
    "normal_ecg",
    "qt_interval",
    "qtc_prolongation",
    "right_bundle_branch_block",
    "supraventricular_tachycardia",
})

# Clinical click and spot-the-error items validate these concepts against a
# packet-grounded ROI.  No other Clinical concept receives localization merely
# because it appears in a vignette or machine statement.
CLINICAL_LOCALIZATION_CONCEPTS = frozenset({
    "av_block_first_degree",
    "left_ventricular_hypertrophy",
    "qtc_prolongation",
    "right_bundle_branch_block",
    "st_depression",
})

# Unlike simulation-only objectives, these rhythm families become independently
# assessable only when an audited expert rhythm-stream source is present in the
# active immutable release. The registry has no permanent hard lock, while
# runtime availability still fails closed until a qualifying packet exists.
DYNAMIC_SOURCE_UNAVAILABLE: dict[str, str] = {
    "wide_complex_tachycardia": (
        "No audited, learner-eligible expert wide-complex tachycardia rhythm-stream packet is connected."
    ),
    "ventricular_tachycardia": (
        "No audited, learner-eligible expert ventricular-tachycardia rhythm fragment is connected."
    ),
    "polymorphic_ventricular_tachycardia": (
        "No audited, learner-eligible expert polymorphic-ventricular-tachycardia rhythm fragment is connected."
    ),
    "ventricular_flutter": (
        "No audited, learner-eligible expert ventricular-flutter rhythm fragment is connected."
    ),
    "ventricular_fibrillation": (
        "No audited, learner-eligible expert ventricular-fibrillation rhythm fragment is connected."
    ),
}

_SURFACE_12_LEADS = {"I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"}


class ObjectiveRepository(Protocol):
    def candidates(self, concept_id: str | None = None) -> list[dict[str, Any]]: ...
    def rapid_rhythm_candidates(self, concept_id: str | None = None) -> list[dict[str, Any]]: ...
    def get_case(self, case_id: str) -> dict[str, Any] | None: ...


@dataclass(frozen=True)
class ObjectiveRuntimeAvailability:
    evidence_ceiling: str
    unavailable_reason: str | None
    eligible_case_ids: tuple[str, ...] = ()
    eligible_subskills: tuple[str, ...] = ()

    @property
    def independent_evidence_available(self) -> bool:
        return self.unavailable_reason is None


def audited_source_packet_supports_objective(packet: dict[str, Any] | None, objective_id: str) -> bool:
    """Fail-closed audit for objectives unlocked by a specialist source packet.

    This is intentionally stricter than checking ``supported_objectives``.  A
    forged Tier-B row, a research-only source, a mismatched license/version, or
    a rhythm label without its expert episode/window provenance cannot remove a
    mastery ceiling.
    """

    if objective_id not in DYNAMIC_SOURCE_UNAVAILABLE or not isinstance(packet, dict):
        return False
    if not packet_allows_learning_evidence(packet, "rapid", objective_id, "recognize").allowed:
        return False
    source = str(packet.get("source") or "")
    descriptor = KNOWN_SOURCES.get(source)
    if not descriptor or descriptor.access != "open":
        return False
    label_authority_text = descriptor.label_authority.casefold()
    if (
        "rhythm_stream" not in descriptor.educational_uses
        or not any(marker in label_authority_text for marker in ("expert", "reviewed"))
    ):
        return False

    case_id = str(packet.get("case_id") or "")
    identity = packet.get("record_identity") or {}
    provenance = packet.get("source_provenance") or {}
    if not isinstance(identity, dict) or not isinstance(provenance, dict):
        return False
    source_record_id = str(identity.get("sourceRecordId") or "")
    patient_id = str(identity.get("patientId") or "")
    if (
        not source_record_id
        or (descriptor.patient_ids_available and not patient_id)
        or case_id != f"{source}:{source_record_id}"
    ):
        return False
    if (
        identity.get("sourceId") != source
        or str(identity.get("sourceVersion") or "") != descriptor.version
        or str(identity.get("licenseId") or "") != descriptor.license_id
    ):
        return False
    if (
        provenance.get("sourceId") != source
        or str(provenance.get("sourceVersion") or "") != descriptor.version
        or str(provenance.get("licenseId") or "") != descriptor.license_id
        or str(provenance.get("patientId") or "") != patient_id
        or str(provenance.get("labelAuthority") or "") != descriptor.label_authority
    ):
        return False

    eligibility = packet.get("educational_eligibility") or {}
    if not isinstance(eligibility, dict):
        return False
    eligible_modes = {str(value) for value in eligibility.get("eligibleModes") or []}
    eligible_subskills = eligibility.get("eligibleSubskills") or {}
    if not isinstance(eligible_subskills, dict):
        return False
    objective_subskills = {str(value) for value in eligible_subskills.get(objective_id) or []}
    if (
        eligibility.get("educationalUse") != "rhythm_stream"
        or not ({"training", "rapid"} & eligible_modes)
        or not ({"recognize", "discriminate"} & objective_subskills)
        or eligibility.get("clinicalCaseEligible") is not False
        or eligibility.get("clinicalManagementEligible") is not False
    ):
        return False
    if source == "ecg-fragment-dangerous-arrhythmia" and (
        eligibility.get("masteryEvidenceEligible") is not True
        or eligibility.get("shockabilityClassificationEligible") is not False
        or eligibility.get("treatmentOrActionSequenceEligible") is not False
        or eligibility.get("actionQuestionsFormativeOnly") is not True
    ):
        return False

    source_labels = packet.get("source_labels") or {}
    if not isinstance(source_labels, dict):
        return False
    rhythm_label = source_labels.get("rhythm") or {}
    if not isinstance(rhythm_label, dict):
        return False
    canonical_rhythm = str(
        rhythm_label.get("canonicalConceptId")
        or rhythm_label.get("canonicalRhythmId")
        or ""
    )
    label_authority = str(
        rhythm_label.get("authority")
        or rhythm_label.get("labelAuthority")
        or ""
    )
    if (
        canonical_rhythm != objective_id
        or label_authority != descriptor.label_authority
        or not str(rhythm_label.get("rhythmCode") or "")
    ):
        return False
    concept_confidence = packet.get("concept_confidence") or {}
    if not isinstance(concept_confidence, dict):
        return False
    confidence = concept_confidence.get(objective_id) or {}
    if not isinstance(confidence, dict):
        return False
    try:
        confidence_score = float(confidence.get("score") or 0)
    except (TypeError, ValueError):
        return False
    signal_quality = packet.get("signal_quality") or {}
    if not isinstance(signal_quality, dict):
        return False
    supported = packet.get("supported_objectives") or []
    if not isinstance(supported, (list, tuple, set)):
        return False
    if (
        objective_id not in supported
        or confidence.get("tier") not in {"A", "B"}
        or confidence_score < 0.58
        or signal_quality.get("status") != "acceptable"
    ):
        return False

    waveform = packet.get("waveform") or {}
    if not isinstance(waveform, dict):
        return False
    try:
        sampling_frequency = int(waveform.get("sampling_frequency") or 0)
        duration_sec = float(waveform.get("duration_sec") or 0)
        leads = set(waveform.get("leads") or [])
        window_start = int(provenance["windowStartSample"])
        window_end = int(provenance["windowEndSample"])
        if source == "leipzig-heart-center":
            episode_start = int(provenance["episodeStartSample"])
            episode_end = int(provenance["episodeEndSample"])
            waveform_ok = (
                sampling_frequency == 100
                and duration_sec == 10.0
                and leads == _SURFACE_12_LEADS
            )
            source_fs = int(provenance.get("sourceSamplingFrequency") or 0)
            episode_ok = (
                source_fs > 0
                and episode_start <= window_start < window_end <= episode_end
                and window_end - window_start == round(10.0 * source_fs)
            )
        elif source == "ecg-fragment-dangerous-arrhythmia":
            waveform_ok = (
                sampling_frequency == DANGEROUS_ARRHYTHMIA_FS
                and duration_sec == 2.0
                and leads == {"MLII"}
                and waveform.get("isSingleModifiedLimbLeadII") is True
            )
            episode_ok = (
                window_start == 0
                and window_end == round(duration_sec * sampling_frequency)
            )
        else:
            return False
    except (KeyError, TypeError, ValueError):
        return False
    fingerprint = str(packet.get("signal_fingerprint") or "")
    return bool(
        waveform_ok
        and episode_ok
        and re.fullmatch(r"[0-9a-f]{64}", fingerprint)
    )


def audited_source_evidence(
    repo: ObjectiveRepository | None, objective_id: str
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if repo is None or objective_id not in DYNAMIC_SOURCE_UNAVAILABLE:
        return (), ()
    case_ids: list[str] = []
    subskills: set[str] = set()
    candidates: list[dict[str, Any]] = []
    try:
        candidates.extend(repo.candidates(objective_id))
    except Exception:
        pass
    specialist_provider = getattr(repo, "rapid_rhythm_candidates", None)
    if callable(specialist_provider):
        try:
            candidates.extend(specialist_provider(objective_id))
        except Exception:
            pass
    for candidate in candidates:
        case_id = str(candidate.get("case_id") or "")
        if not case_id:
            continue
        try:
            packet = repo.get_case(case_id)
        except Exception:
            continue
        if audited_source_packet_supports_objective(packet, objective_id):
            case_ids.append(case_id)
            eligibility = packet.get("educational_eligibility") or {}
            source_subskills = eligibility.get("eligibleSubskills") or {}
            if isinstance(source_subskills, dict):
                values = source_subskills.get(objective_id) or []
                if isinstance(values, (list, tuple, set)):
                    subskills.update(str(value) for value in values)
    return (
        tuple(dict.fromkeys(case_ids)),
        tuple(subskill for subskill in SUBSKILLS if subskill in subskills),
    )


def audited_source_case_ids(repo: ObjectiveRepository | None, objective_id: str) -> tuple[str, ...]:
    return audited_source_evidence(repo, objective_id)[0]


def objective_runtime_availability(
    definition: ObjectiveDefinition,
    repo: ObjectiveRepository | None = None,
) -> ObjectiveRuntimeAvailability:
    """Resolve static ceilings plus source-dependent runtime unlocks."""

    if definition.unavailable_reason:
        return ObjectiveRuntimeAvailability(definition.evidence_ceiling, definition.unavailable_reason)
    dynamic_reason = DYNAMIC_SOURCE_UNAVAILABLE.get(definition.id)
    if dynamic_reason:
        eligible_ids, eligible_subskills = audited_source_evidence(repo, definition.id)
        if not eligible_ids:
            return ObjectiveRuntimeAvailability("formative_or_simulation", dynamic_reason)
        return ObjectiveRuntimeAvailability(
            "eligible_real_case", None, eligible_ids, eligible_subskills
        )
    return ObjectiveRuntimeAvailability(
        definition.evidence_ceiling,
        None,
        eligible_subskills=definition.allowed_subskills,
    )


def _label(objective_id: str) -> str:
    overrides = {
        "av_block_2_to_1": "2:1 AV block",
        "foundations_waveform_landmarks": "Waveform landmarks",
        "foundations_calibration": "Calibration and measurement",
        "foundations_signal_quality": "Task-specific signal quality",
        "foundations_rate": "Ventricular rate",
        "foundations_atrial_source": "Atrial source and P–QRS relationship",
        "foundations_pr_qrs": "PR and QRS measurement",
        "foundations_recovery": "Recovery landmarks",
        "foundations_twelve_lead_navigation": "Twelve-lead navigation",
        "foundations_axis": "Frontal QRS axis",
        "foundations_systematic_sweep": "Systematic descriptive sweep",
        "qtc_prolongation": "QTc prolongation",
        "qrs_duration": "QRS duration",
        "st_t_morphology": "ST–T morphology",
        "pr_qrs_boundaries": "PR and QRS boundaries",
        "wide_qrs_qt_confound": "Wide-QRS QT confound",
        "ivcd_claim_strength": "IVCD claim strength",
    }
    if objective_id in overrides:
        return overrides[objective_id]
    acronyms = {
        "av": "AV",
        "ecg": "ECG",
        "ivcd": "IVCD",
        "ii": "II",
        "iii": "III",
        "lvh": "LVH",
        "mi": "MI",
        "pac": "PAC",
        "pr": "PR",
        "qrs": "QRS",
        "qt": "QT",
        "qtc": "QTc",
        "rvh": "RVH",
        "st": "ST",
        "svt": "SVT",
        "wpw": "WPW",
    }
    return " ".join(
        acronyms.get(token, token.title()) for token in objective_id.split("_")
    )


def _case_mapping(objective_id: str) -> tuple[tuple[str, ...], str]:
    if objective_id in _FOUNDATIONS_CASE_MAPPINGS:
        return _FOUNDATIONS_CASE_MAPPINGS[objective_id]
    if objective_id == "qrs_complex":
        # Normal ECG is the inventory anchor only; localization itself is
        # diagnosis-neutral and may be observed on any eligible tracing.
        return ("normal_ecg",), "waveform_fundamentals"
    if objective_id in {"ecg_grid_calibration", "waveform_components"}:
        return ("normal_ecg",), "waveform_fundamentals"
    if objective_id == "pr_interval":
        return ("normal_ecg", "av_block_first_degree"), "av_conduction"
    if objective_id == "qt_interval":
        # The corpus authors a QTc case family, while the M08 measurement
        # objective assesses the learner's raw QT caliper placement and value.
        # Training owns the narrow measurement-only receipt proxy; keeping the
        # mapping here lets Guided/Planner discover that executable handoff
        # without pretending a raw QT value is itself a binary diagnosis.
        return ("qtc_prolongation",), "intervals"
    if objective_id == "preexcited_atrial_fibrillation":
        # This remains formative until a reviewed rhythm stream contains both
        # pre-excitation and AF evidence, but it belongs in the tachyarrhythmia
        # curriculum rather than leaking an internal "unmapped" bucket.
        return ("atrial_fibrillation", "wolff_parkinson_white"), "tachyarrhythmia"
    if objective_id == "resuscitation_source_boundary":
        # Source-selection reasoning integrates rhythm recognition with the
        # limits of a resting 12-lead. It cannot earn resuscitation mastery
        # without the governed stream described by its explicit ceiling.
        return ("wide_complex_tachycardia", "bradycardia"), "integration"
    if objective_id in CONCEPT_BY_ID:
        concept = CONCEPT_BY_ID[objective_id]
        return (objective_id,), concept.group
    for pattern, candidates, domain in _ALIASES:
        if pattern.search(objective_id):
            return tuple(candidate for candidate in candidates if candidate in CONCEPT_BY_ID), domain
    return (), "unmapped"


def _subskills(objective_id: str, domain: str) -> tuple[str, ...]:
    if objective_id in _FOUNDATIONAL_SUBSKILLS:
        return _FOUNDATIONAL_SUBSKILLS[objective_id]
    if objective_id == "qrs_complex":
        return ("localize",)
    selected = {"recognize", "discriminate", "explain_mechanism", "calibrate_confidence"}
    if re.search(r"lead|territor|locali|placement|wave|morphology|segment|artifact|progression", objective_id):
        selected.add("localize")
    if objective_id in CLINICAL_LOCALIZATION_CONCEPTS:
        selected.add("localize")
    if re.search(r"rate|interval|boundar|qrs|qt|voltage|axis|pr_|bundle|conduction", objective_id):
        selected.add("measure")
    # A canonical packet concept can support an exact, server-graded synthesis
    # task in Training/Rapid. Application remains formative in Training; an
    # independent application receipt still requires a reviewed Clinical item.
    if objective_id in CONCEPT_BY_ID:
        selected.update({"synthesize", "apply_in_context"})
    # Curriculum objectives that explicitly name an integrative construct may
    # expose that construct. Mode-specific assessment matrices still decide
    # whether a particular case/task can issue independent evidence; a case
    # alias alone is never sufficient.
    if re.search(r"mixed|integrated|synthesis|framework|audit|comparison|transfer|claim", objective_id):
        selected.add("synthesize")
    if re.search(r"context|clinical|chest_pain|medication|syncope|palpitations|with_pulse|resuscitation", objective_id):
        selected.add("apply_in_context")
    if objective_id in CLINICAL_APPLICATION_CONCEPTS:
        selected.add("apply_in_context")
    selected.update(_SUBSKILL_ADDITIONS.get(objective_id, ()))
    # Stable ordering is part of the API contract.
    return tuple(item for item in SUBSKILLS if item in selected)


def build_registry() -> dict[str, ObjectiveDefinition]:
    objective_ids = (
        set(GUIDED_OBJECTIVE_IDS)
        | set(RETIRED_GUIDED_OBJECTIVE_IDS)
        | {concept.id for concept in CONCEPTS}
        | set(NEUTRAL_WAVEFORM_OBJECTIVES)
        | set(FOUNDATIONAL_OBJECTIVE_IDS)
    )
    result: dict[str, ObjectiveDefinition] = {}
    for objective_id in sorted(objective_ids):
        case_concepts, domain = _case_mapping(objective_id)
        allowed = _subskills(objective_id, domain)
        reason = _FORMATIVE_ONLY.get(objective_id)
        if not case_concepts and not reason:
            reason = "No explicit confidence-curated case-family mapping exists."
        result[objective_id] = ObjectiveDefinition(
            id=objective_id,
            label=_label(objective_id),
            domain=domain,
            case_concepts=case_concepts,
            allowed_subskills=allowed,
            task_templates={subskill: TASKS_BY_SUBSKILL[subskill] for subskill in allowed},
            evidence_ceiling="formative_or_simulation" if reason else "eligible_real_case",
            unavailable_reason=reason,
        )
    return result


OBJECTIVES = build_registry()


def objective_definition(objective_id: str) -> ObjectiveDefinition | None:
    return OBJECTIVES.get(objective_id)


def validate_objective_subskill(objective_id: str, subskill: str) -> bool:
    objective = objective_definition(objective_id)
    return bool(objective and subskill in objective.allowed_subskills)
