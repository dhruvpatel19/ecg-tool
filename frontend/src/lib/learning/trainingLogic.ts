import type { LearningSubskill } from "./interactionTypes";
import type { LearnerProfile, TrainingCampaign } from "../types";
import { safeLearningReturn } from "./learningReturn";

const TRAINING_SUBSKILLS = new Set<LearningSubskill>([
  "recognize",
  "localize",
  "measure",
  "discriminate",
  "explain_mechanism",
  "synthesize",
  "apply_in_context",
  "calibrate_confidence",
]);

/** API-compatible lengths. Focused Practice presents only 5/10/20 in the
 * learner setup; larger values remain accepted for durable legacy campaigns. */
export const TRAINING_SESSION_LENGTHS = [5, 10, 20, 25, 50, 100, 500, 1000, 5000] as const;
const TRAINING_RETURN_SURFACES = ["lesson", "study_plan", "profile", "calendar", "rapid", "clinical", "session_review"] as const;

export function trainingFeedbackHeading({
  correct,
  expectedAnswer,
  measurementRehearsal,
  subskillLabel,
}: {
  correct: boolean;
  expectedAnswer: "present" | "absent" | null;
  measurementRehearsal: boolean;
  subskillLabel?: string;
}) {
  if (measurementRehearsal) return "Measurement rehearsal saved";
  if (subskillLabel && !["Recognize the pattern", "Recognize and name"].includes(subskillLabel)) {
    return correct ? `${subskillLabel} met` : `${subskillLabel} needs review`;
  }
  if (!correct) return "Re-check the discriminator";
  if (expectedAnswer === "present") return "Pattern recognized";
  if (expectedAnswer === "absent") return "Contrast distinguished";
  return "Decision supported";
}

export type TrainingLaunchIntent = {
  requestedCaseConcept: string;
  receiptConcept: string;
  subskill: LearningSubskill | "";
  returnTo: string;
  suggestedLength: number | null;
  hasExplicitPreset: boolean;
  isHandoff: boolean;
};

export function safeTrainingReturn(value: string): string {
  return safeLearningReturn(value, TRAINING_RETURN_SURFACES);
}

export function parseTrainingLaunchIntent(search: string): TrainingLaunchIntent {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  const concept = (params.get("concept") ?? "").trim();
  const focus = (params.get("focus") ?? "").trim();
  const receipt = (params.get("receiptConcept") ?? "").trim();
  const requestedSubskill = (params.get("subskill") ?? "").trim() as LearningSubskill;
  const subskill = TRAINING_SUBSKILLS.has(requestedSubskill) ? requestedSubskill : "";
  const returnTo = safeTrainingReturn((params.get("returnTo") ?? "").trim());
  const requestedLength = params.get("suggestedLength") ?? "";
  const parsedLength = /^\d+$/.test(requestedLength) ? Number(requestedLength) : Number.NaN;
  const suggestedLength = TRAINING_SESSION_LENGTHS.includes(
    parsedLength as (typeof TRAINING_SESSION_LENGTHS)[number],
  ) ? parsedLength : null;
  return {
    // `concept` is an authored case-family target; `focus` is the older Rapid
    // and Guided spelling. A receipt can name a broader competency and must
    // never silently replace an explicitly supplied case family.
    requestedCaseConcept: concept || focus || receipt,
    receiptConcept: receipt || focus || concept,
    subskill,
    returnTo,
    suggestedLength,
    hasExplicitPreset: Boolean(concept || focus || receipt || subskill),
    isHandoff: Boolean(focus || receipt || returnTo),
  };
}

export function campaignMatchesTrainingLaunch(
  campaign: Pick<TrainingCampaign, "conceptId" | "subskill" | "contextKey">,
  intent: TrainingLaunchIntent,
  resolvedCaseConcept: string,
): boolean {
  if (!intent.hasExplicitPreset) return true;
  if (!resolvedCaseConcept || campaign.conceptId !== resolvedCaseConcept) return false;
  if (intent.subskill && campaign.subskill !== intent.subskill) return false;
  const context = new URLSearchParams(campaign.contextKey);
  const campaignReceipt = context.get("receiptConcept") || campaign.conceptId;
  if (intent.receiptConcept && campaignReceipt !== intent.receiptConcept) return false;
  const campaignReturn = safeTrainingReturn(context.get("returnTo") || "");
  return !intent.returnTo || campaignReturn === intent.returnTo;
}

export type TrainingMasteryPresentation = {
  state: "unseen" | "formative" | "assessed";
  label: string;
  detail: string;
  value: number | null;
  recommendationLabel: "unassessed skill" | "needs practice" | "scheduled review";
};

export function trainingMasteryPresentation(
  profile: Pick<LearnerProfile, "subskillMastery"> | null,
  concept: string,
  subskill: LearningSubskill,
): TrainingMasteryPresentation {
  const row = profile?.subskillMastery.find(
    (item) => item.concept === concept && item.subskill === subskill,
  );
  if (!row || row.attempts === 0) {
    return {
      state: "unseen",
      label: "Not assessed yet",
      detail: "No fresh mixed ECG check has been completed for this exact skill.",
      value: null,
      recommendationLabel: "unassessed skill",
    };
  }
  if (row.independentAttempts === 0) {
    return {
      state: "formative",
      label: "Practiced · not independently checked",
      detail: "Formative practice is saved, but it is not a mastery estimate until you complete a fresh mixed ECG check.",
      value: null,
      recommendationLabel: "unassessed skill",
    };
  }
  const needsPractice = row.independentMastery < 0.7
    || row.highConfidenceWrong > 0
    || row.isDue;
  return {
    state: "assessed",
    label: `Current mastery estimate · ${Math.round(row.independentMastery * 100)}%`,
    detail: `${row.independentAttempts} independent check${row.independentAttempts === 1 ? "" : "s"} recorded.`,
    value: row.independentMastery,
    recommendationLabel: needsPractice ? "needs practice" : "scheduled review",
  };
}
