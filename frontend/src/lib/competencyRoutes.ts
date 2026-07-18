import { RAPID_EMERGENCY_RHYTHM_CONCEPTS } from "./learning/rapidLogic";
import { safeLearningReturn } from "./learning/learningReturn";

type IndependentReceipt = {
  mode: "train" | "rapid";
  caseConcept: string;
  receiptConcept: string;
  subskill: string;
};

const COMPETENCY_RETURN_SURFACES = ["profile", "session_review"] as const;

export function competencyPracticeHref(
  receipt: IndependentReceipt | null,
  requestedReturn = "/home?panel=competencies",
): string | null {
  if (!receipt) return null;
  const returnTo = safeLearningReturn(requestedReturn, COMPETENCY_RETURN_SURFACES)
    || "/home?panel=competencies";
  const params = new URLSearchParams({
    receiptConcept: receipt.receiptConcept,
    subskill: receipt.subskill,
    returnTo,
  });
  if (receipt.mode === "train") {
    params.set("concept", receipt.caseConcept);
    return `/train?${params.toString()}`;
  }
  params.set("focus", receipt.caseConcept);
  if ((RAPID_EMERGENCY_RHYTHM_CONCEPTS as readonly string[]).includes(receipt.caseConcept)) {
    params.set("practiceMode", "emergency");
  }
  return `/rapid?${params.toString()}`;
}
