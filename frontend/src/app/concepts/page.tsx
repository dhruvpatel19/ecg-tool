import { redirect } from "next/navigation";
import { safeLearningReturn } from "@/lib/learning/learningReturn";
import { TRAINING_SESSION_LENGTHS } from "@/lib/learning/trainingLogic";

type LegacySearchParams = Promise<Record<string, string | string[] | undefined>>;

const TRAINING_SUBSKILLS = new Set([
  "recognize",
  "localize",
  "measure",
  "discriminate",
  "explain_mechanism",
  "calibrate_confidence",
]);

function first(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

export default async function LegacyConceptsPage({ searchParams }: { searchParams: LegacySearchParams }) {
  const params = await searchParams;
  const concept = first(params.focus) || first(params.concept) || "";
  const requestedSubskill = first(params.subskill) || "";
  const returnTo = safeLearningReturn(first(params.returnTo), ["lesson", "study_plan", "rapid", "clinical"]);
  const requestedLength = first(params.suggestedLength) || "";
  const suggestedLength = /^\d+$/.test(requestedLength) && TRAINING_SESSION_LENGTHS.includes(
    Number(requestedLength) as (typeof TRAINING_SESSION_LENGTHS)[number],
  ) ? requestedLength : "";
  const target = new URLSearchParams();

  if (concept) target.set("concept", concept);
  if (TRAINING_SUBSKILLS.has(requestedSubskill)) target.set("subskill", requestedSubskill);
  if (suggestedLength) target.set("suggestedLength", suggestedLength);
  if (returnTo) target.set("returnTo", returnTo);

  redirect(target.size ? `/train?${target.toString()}` : "/train");
}
