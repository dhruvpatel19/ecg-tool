import type { CrossModeHandoff } from "@/lib/learning/interactionTypes";

export type HandoffTargetResolution = {
  requestedConcept: string;
  caseConcept: string;
  exact: boolean;
  rationale: string;
};

type GuidedHandoffRouteContext = {
  moduleId: string;
  sceneId: string;
};

/** Build an authored cross-mode launch whose destination is actually runnable. */
export function guidedHandoffHref(
  handoff: CrossModeHandoff,
  context: GuidedHandoffRouteContext,
): string {
  const sourceObjective = handoff.concept.trim();
  if (!sourceObjective) {
    throw new Error(`Guided ${handoff.mode} handoff requires a source objective.`);
  }
  if (!context.moduleId.trim() || !context.sceneId.trim()) {
    throw new Error("Guided handoff requires a module and scene context.");
  }

  if (handoff.mode !== "train" && !handoff.destination) {
    throw new Error(`Guided ${handoff.mode} handoff requires an executable destination contract.`);
  }
  const destination = handoff.destination;
  const focus = (destination?.focus ?? sourceObjective).trim();
  const destinationSubskill = destination?.subskill ?? handoff.subskill;
  if (!focus) throw new Error(`Guided ${handoff.mode} handoff requires a destination focus.`);

  const params = new URLSearchParams({
    focus,
    sourceObjective,
    subskill: destinationSubskill,
    support: handoff.supportLevel,
    origin: `${context.moduleId}:${context.sceneId}`,
    returnTo: `/learn/${context.moduleId}?scene=${context.sceneId}`,
  });
  if (handoff.mode === "rapid") {
    params.set("receiptConcept", (destination?.receiptConcept ?? focus).trim());
    if (destination?.secondaryConcept) params.set("secondaryConcept", destination.secondaryConcept);
    if (destination?.suggestedLength) params.set("suggestedLength", String(destination.suggestedLength));
    if (destination?.pace) params.set("pace", destination.pace);
  }
  if (handoff.mode === "clinical") {
    if (!destination?.lane) throw new Error("Guided Clinical handoff requires a compatible lane.");
    params.set("lane", destination.lane);
    if (destination.length) params.set("length", String(destination.length));
  }

  const pathname = handoff.mode === "train"
    ? "/train"
    : handoff.mode === "rapid"
      ? "/rapid"
      : "/practice";
  return `${pathname}?${params.toString()}`;
}

type AliasRule = { pattern: RegExp; candidates: string[]; rationale: string };

// Storyboard competencies are often narrower than corpus diagnostic labels. A
// transfer may use a broader case family only when the relationship is explicit
// and the destination interaction still tests the requested subskill. If no
// validated family is available, callers must fail closed rather than substitute
// an unrelated case and misattribute its evidence.
const ALIAS_RULES: AliasRule[] = [
  { pattern: /lead_(territor|anatomy|placement|projection)|frontal_lead_map|precordial_placement|r_wave_progression/, candidates: ["normal_ecg"], rationale: "a complete normal 12-lead provides every named lead without disclosing a pathology" },
  { pattern: /^axis$|axis_/, candidates: ["axis_normal", "left_axis_deviation", "right_axis_deviation"], rationale: "the axis family supplies grounded QRS polarity contrasts" },
  { pattern: /pr_qrs_boundaries|pr_sequence/, candidates: ["av_block_first_degree"], rationale: "a first-degree AV-block case supplies a measurable PR interval and QRS boundary" },
  { pattern: /av_block_2_to_1|mobitz_ii_vs_blocked_pac|av_conduction|av_relationship/, candidates: ["av_block_second_degree_mobitz_ii", "av_block_first_degree"], rationale: "the vetted AV-block family is the closest eligible conduction contrast" },
  { pattern: /syncope_bradycardia|bradycardia_with_pulse|brady_context|escape_rhythm|pause_escape/, candidates: ["bradycardia"], rationale: "the available bradycardia family can support rate/rhythm evidence without inventing an event rhythm" },
  { pattern: /ectopy|premature/, candidates: ["premature_ventricular_complex", "premature_atrial_complex"], rationale: "the PVC/PAC family supplies real premature-beat contrasts" },
  { pattern: /rhythm_basics|rhythm_regularities/, candidates: ["sinus_rhythm"], rationale: "sinus-rhythm cases support the basic rhythm ladder" },
  { pattern: /qrs_width_morphology|ventricular_conduction|ivcd|bundle_activation|machine_audit_conduction/, candidates: ["qrs_duration", "right_bundle_branch_block", "left_bundle_branch_block"], rationale: "the vetted wide-QRS family supplies measurable duration and paired morphology" },
  { pattern: /integrated_wide_qrs_device|wide_complex|device/, candidates: ["right_bundle_branch_block", "qrs_duration"], rationale: "the current bank supports wide-QRS/conduction transfer but not device-management claims" },
  { pattern: /tachycardia_with_pulse|palpitations_tachycardia|tachyarrhythmia|tachycardia_matrix|irregular_narrow/, candidates: ["atrial_fibrillation", "supraventricular_tachycardia", "atrial_flutter"], rationale: "the vetted tachyarrhythmia family supports rhythm discrimination" },
  { pattern: /sinus_vs_svt|svt_atrial_timing/, candidates: ["supraventricular_tachycardia"], rationale: "the SVT family supports the requested narrow-tachycardia contrast" },
  { pattern: /chamber|voltage|poor_r_wave|lvh_chronic/, candidates: ["left_ventricular_hypertrophy", "right_ventricular_hypertrophy", "atrial_enlargement"], rationale: "the vetted chamber/voltage family supplies the relevant morphology" },
  { pattern: /repolarization|st_t_morphology|primary_secondary|secondary_repolarization|nonischemic_st_t|st_depression_t_inversion/, candidates: ["nonspecific_st_t_change", "st_depression", "t_wave_inversion"], rationale: "the vetted ST–T family supports descriptive recovery-pattern work" },
  { pattern: /medication_qt|integrated_medication_qt|wide_qrs_qt|qtc|qt_/, candidates: ["qtc_prolongation", "qt_interval"], rationale: "the QT/QTc family supplies measured interval evidence; medication action remains separately governed" },
  { pattern: /chest_pain|ischemia|contiguous_reciprocal|inferior_right_sided|anterior_lateral/, candidates: ["myocardial_ischemia", "anterior_mi", "inferior_mi"], rationale: "the ischemia/infarction family supports lead geography without creating acute timing" },
  { pattern: /infarct|posterior_mi|pathologic_q|mi$/, candidates: ["myocardial_infarction", "pathologic_q_waves", "anterior_mi"], rationale: "the established-infarction family supports chronic pattern evidence without acute timing" },
  { pattern: /interpretation_framework|prioritized_ecg|integrated_interpretation|integrated_capstone|machine_read_audit/, candidates: ["normal_ecg"], rationale: "a complete normal 12-lead supports the grounded whole-ECG framework without inventing a pathology" },
];

export function resolveHandoffTarget(requestedConcept: string, availableConcepts: Iterable<string>): HandoffTargetResolution | null {
  if (!requestedConcept) return null;
  const available = new Set(availableConcepts);
  if (available.has(requestedConcept)) {
    return { requestedConcept, caseConcept: requestedConcept, exact: true, rationale: "exact grounded concept match" };
  }
  const rule = ALIAS_RULES.find((candidate) => candidate.pattern.test(requestedConcept));
  const caseConcept = rule?.candidates.find((candidate) => available.has(candidate));
  if (!rule || !caseConcept) return null;
  return { requestedConcept, caseConcept, exact: false, rationale: rule.rationale };
}
