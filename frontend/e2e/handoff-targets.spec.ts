import { expect, test } from "@playwright/test";
import { resolveHandoffTarget } from "../src/lib/learning/handoffTargets";
import { competencyPracticeHref } from "../src/lib/competencyRoutes";

test("Guided handoffs mirror the six eligible backend alias families", () => {
  const available = ["normal_ecg", "nonspecific_st_t_change", "st_depression", "t_wave_inversion"];
  const expected: Record<string, string> = {
    st_depression_t_inversion_differential: "nonspecific_st_t_change",
    interpretation_framework_mapping: "normal_ecg",
    integrated_interpretation: "normal_ecg",
    prioritized_ecg_synthesis: "normal_ecg",
    machine_read_audit: "normal_ecg",
    integrated_capstone: "normal_ecg",
  };

  for (const [requested, caseConcept] of Object.entries(expected)) {
    expect(resolveHandoffTarget(requested, available)).toMatchObject({
      requestedConcept: requested,
      caseConcept,
      exact: false,
    });
  }
});

test("supported direct findings resolve exactly without proxying", () => {
  const supported = ["paced_rhythm", "electrolyte_drug_pattern", "posterior_mi"];
  for (const concept of supported) {
    expect(resolveHandoffTarget(concept, supported)).toEqual({
      requestedConcept: concept,
      caseConcept: concept,
      exact: true,
      rationale: "exact grounded concept match",
    });
  }
});

test("competency CTAs fail closed and preserve the exact receipt contract", () => {
  expect(competencyPracticeHref(null)).toBeNull();
  expect(competencyPracticeHref({
    mode: "rapid",
    caseConcept: "normal_ecg",
    receiptConcept: "integrated_interpretation",
    subskill: "synthesize",
  })).toBe("/rapid?receiptConcept=integrated_interpretation&subskill=synthesize&returnTo=%2Fprofile&focus=normal_ecg");
  expect(competencyPracticeHref({
    mode: "train",
    caseConcept: "right_bundle_branch_block",
    receiptConcept: "right_bundle_branch_block",
    subskill: "discriminate",
  })).toBe("/train?receiptConcept=right_bundle_branch_block&subskill=discriminate&returnTo=%2Fprofile&concept=right_bundle_branch_block");
});
