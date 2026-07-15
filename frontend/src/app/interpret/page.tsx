import { redirect } from "next/navigation";
import { safeLearningReturn } from "@/lib/learning/learningReturn";
import { RAPID_SESSION_LENGTHS } from "@/lib/learning/rapidLogic";

type LegacySearchParams = Promise<Record<string, string | string[] | undefined>>;

const LEARNING_SUBSKILLS = new Set([
  "recognize",
  "localize",
  "measure",
  "discriminate",
  "explain_mechanism",
  "synthesize",
  "apply_in_context",
  "calibrate_confidence",
]);

function first(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

export default async function LegacyInterpretPage({ searchParams }: { searchParams: LegacySearchParams }) {
  const params = await searchParams;
  const focus = first(params.focus) || first(params.concept) || "";
  const requestedSubskill = first(params.subskill) || "";
  const receiptConcept = first(params.receiptConcept) || "";
  const returnTo = safeLearningReturn(first(params.returnTo), ["lesson", "study_plan"]);
  const requestedLength = first(params.suggestedLength) || "";
  const suggestedLength = /^\d+$/.test(requestedLength) && RAPID_SESSION_LENGTHS.includes(
    Number(requestedLength) as (typeof RAPID_SESSION_LENGTHS)[number],
  ) ? requestedLength : "";
  const target = new URLSearchParams();

  if (focus) {
    target.set("focus", focus);
    target.set("receiptConcept", receiptConcept || focus);
    target.set("subskill", LEARNING_SUBSKILLS.has(requestedSubskill) ? requestedSubskill : "synthesize");
  }
  if (suggestedLength) target.set("suggestedLength", suggestedLength);
  if (returnTo) target.set("returnTo", returnTo);

  redirect(target.size ? `/rapid?${target.toString()}` : "/rapid");
}
