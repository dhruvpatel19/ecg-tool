import { safeLearningReturn } from "./learningReturn";
import type { LearningSubskill } from "./interactionTypes";

export const RAPID_SESSION_LENGTHS = [5, 10, 25, 50, 100, 500, 1000, 5000] as const;
export const RAPID_PACES = ["untimed", "ward", "emergency"] as const;
export type RapidPace = (typeof RAPID_PACES)[number];

type RapidReceiptSummaryInput = {
  concept: string;
  subskill: string;
  accepted: boolean;
  correct?: boolean;
};

type RapidClinicalHandoffResult = {
  missedObjectives: string[];
  correctObjectives: string[];
};

export type RapidClinicalDestination = {
  lane: "clinic" | "ward" | "ed";
};

function frequencyRank(values: string[]): string[] {
  const counts = new Map<string, number>();
  values.forEach((value) => counts.set(value, (counts.get(value) ?? 0) + 1));
  return [...counts]
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .map(([value]) => value);
}

/** Carry a server-graded Rapid finding into Clinical's actual launch fields. */
export function rapidClinicalHandoffHref(
  results: RapidClinicalHandoffResult[],
  destinations: ReadonlyMap<string, RapidClinicalDestination>,
): string | null {
  // A frequent strength must never outrank a less frequent miss. Clinical is
  // the transfer step after Rapid, so remediation is chosen from misses first;
  // a correctly identified finding is only a fallback when no missed finding
  // has an eligible authored application case.
  const missedTarget = frequencyRank(
    results.flatMap((result) => result.missedObjectives),
  ).find((concept) => destinations.has(concept));
  const target = missedTarget ?? frequencyRank(
    results.flatMap((result) => result.correctObjectives),
  ).find((concept) => destinations.has(concept));
  if (!target) return null;
  const destination = destinations.get(target);
  if (!destination) return null;
  const params = new URLSearchParams({
    focus: target,
    subskill: "apply_in_context",
    lane: destination.lane,
    returnTo: "/rapid",
  });
  return `/practice?${params.toString()}`;
}

export function rapidReceiptSummary(
  receipts: RapidReceiptSummaryInput[],
  label: (concept: string) => string = (concept) => concept.replaceAll("_", " "),
): string {
  const accepted = receipts.filter((receipt) => receipt.accepted);
  const positive = accepted.filter((receipt) => receipt.correct !== false);
  const lapses = accepted.filter((receipt) => receipt.correct === false);
  const recognized = positive.filter((receipt) => receipt.subskill === "recognize");
  const localized = positive.some((receipt) => receipt.subskill === "localize" && receipt.concept === "qrs_complex");
  const synthesized = positive.filter((receipt) => receipt.subskill === "synthesize");
  const missedRecognition = lapses.filter((receipt) => receipt.subskill === "recognize");
  const missedSynthesis = lapses.filter((receipt) => receipt.subskill === "synthesize");
  const positiveParts: string[] = [];
  const reviewParts: string[] = [];
  if (recognized.length) positiveParts.push(`recognized ${recognized.map((item) => label(item.concept)).join(", ")}`);
  if (localized) positiveParts.push("QRS localization verified on the trace");
  if (synthesized.length) positiveParts.push(`full-read synthesis verified for ${synthesized.map((item) => label(item.concept)).join(", ")}`);
  if (missedRecognition.length) reviewParts.push(`review needed for ${missedRecognition.map((item) => label(item.concept)).join(", ")}`);
  if (missedSynthesis.length) reviewParts.push(`full-read synthesis needs review for ${missedSynthesis.map((item) => label(item.concept)).join(", ")}`);
  if (positiveParts.length && reviewParts.length) {
    return `Learning record saved: ${[...positiveParts, ...reviewParts].join(" · ")}.`;
  }
  if (positiveParts.length) {
    return `Progress saved: ${positiveParts.join(" · ")}.`;
  }
  if (reviewParts.length) {
    return `Attempt saved: ${reviewParts.join(" · ")}. No positive evidence was earned.`;
  }
  return "Attempt saved. Your progress is unchanged because the required finding, trace mark, or complete interpretation was not finished yet.";
}

// Only exact, server-reviewed Rapid case concepts may be carried as the second
// concept in an adaptive integration launch. Guided aliases remain supported
// for the primary `focus`, but they cannot silently broaden this frozen roster.
export const RAPID_CASE_CONCEPTS = [
  "normal_ecg", "rate", "sinus_rhythm", "axis_normal", "left_axis_deviation", "right_axis_deviation",
  "premature_ventricular_complex", "premature_atrial_complex", "bradycardia", "av_block_first_degree",
  "av_block_second_degree_mobitz_ii", "av_block_third_degree", "atrial_fibrillation", "atrial_flutter",
  "supraventricular_tachycardia", "wide_complex_tachycardia", "qrs_duration", "right_bundle_branch_block", "left_bundle_branch_block",
  "left_anterior_fascicular_block", "left_posterior_fascicular_block", "wolff_parkinson_white",
  "paced_rhythm", "left_ventricular_hypertrophy", "right_ventricular_hypertrophy", "atrial_enlargement", "qt_interval",
  "qtc_prolongation", "nonspecific_st_t_change", "st_depression", "t_wave_inversion", "myocardial_ischemia",
  "electrolyte_drug_pattern", "myocardial_infarction", "anterior_mi", "inferior_mi", "lateral_mi", "septal_mi", "posterior_mi", "pathologic_q_waves",
] as const;

const RAPID_INTEGRATION_CONCEPTS = [
  ...RAPID_CASE_CONCEPTS,
  "av_block_second_degree_mobitz_i",
  "incomplete_right_bundle_branch_block",
  "nonspecific_intraventricular_conduction_delay",
  "pericarditis_pattern",
  "r_wave_progression",
  "st_elevation",
] as const;

const RAPID_INTEGRATION_CONCEPT_SET = new Set<string>(RAPID_INTEGRATION_CONCEPTS);

const RAPID_SUBSKILLS = new Set<LearningSubskill>([
  "recognize",
  "localize",
  "measure",
  "discriminate",
  "explain_mechanism",
  "synthesize",
  "apply_in_context",
  "calibrate_confidence",
]);

const RAPID_RETURN_SURFACES = ["lesson", "study_plan", "clinical"] as const;

export type RapidLaunchIntent = {
  focus: string;
  secondaryConcept: string;
  secondaryConceptInvalid: boolean;
  receiptConcept: string;
  subskill: LearningSubskill | "";
  returnTo: string;
  suggestedLength: number | null;
  pace: RapidPace | null;
  requestedPace: RapidPace | null;
  paceAdjustedForCompleteRead: boolean;
  completeReadRequired: boolean;
};

function allowlistedRapidLength(value: string | null): number | null {
  if (!value || !/^\d+$/.test(value)) return null;
  const length = Number(value);
  return RAPID_SESSION_LENGTHS.includes(length as (typeof RAPID_SESSION_LENGTHS)[number])
    ? length
    : null;
}

export function parseRapidLaunchIntent(search: string): RapidLaunchIntent {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  const focus = (params.get("focus") ?? "").trim();
  const secondaryValues = params.getAll("secondaryConcept").map((value) => value.trim());
  const secondaryConcept = secondaryValues.length === 1
    && RAPID_INTEGRATION_CONCEPT_SET.has(secondaryValues[0])
    && secondaryValues[0] !== focus
    ? secondaryValues[0]
    : "";
  const requestedSubskill = (params.get("subskill") ?? "").trim() as LearningSubskill;
  const subskill = RAPID_SUBSKILLS.has(requestedSubskill) ? requestedSubskill : "";
  const rawPace = (params.get("pace") ?? "").trim();
  const requestedPace = RAPID_PACES.includes(rawPace as RapidPace)
    ? rawPace as RapidPace
    : null;
  const completeReadRequired = subskill === "synthesize" || Boolean(secondaryConcept);
  const paceAdjustedForCompleteRead = requestedPace === "emergency" && completeReadRequired;
  return {
    focus,
    secondaryConcept,
    secondaryConceptInvalid: secondaryValues.length > 0 && !secondaryConcept,
    receiptConcept: (params.get("receiptConcept") ?? focus).trim(),
    subskill,
    returnTo: safeLearningReturn(params.get("returnTo"), RAPID_RETURN_SURFACES),
    suggestedLength: allowlistedRapidLength(params.get("suggestedLength")),
    pace: paceAdjustedForCompleteRead ? "ward" : requestedPace,
    requestedPace,
    paceAdjustedForCompleteRead,
    completeReadRequired,
  };
}
