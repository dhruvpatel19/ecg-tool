import { expect, test } from "@playwright/test";
import {
  learningReturnLabel,
  parseLearningReturn,
  safeLearningReturn,
} from "../src/lib/learning/learningReturn";
import { parseRapidLaunchIntent, rapidClinicalHandoffHref, rapidReceiptSummary } from "../src/lib/learning/rapidLogic";
import { parseTrainingLaunchIntent } from "../src/lib/learning/trainingLogic";

test("learning returns accept only explicit internal destinations and label the study plan", () => {
  expect(parseLearningReturn("/profile?tab=plan", ["lesson", "study_plan"])).toEqual({
    href: "/profile?tab=plan",
    surface: "study_plan",
    label: "Return to study plan",
  });
  expect(parseLearningReturn("/review", ["lesson", "study_plan"])).toEqual({
    href: "/review",
    surface: "study_plan",
    label: "Return to study plan",
  });
  expect(safeLearningReturn("/learn/rhythm-ectopy?scene=M03.S14", ["lesson"])).toBe(
    "/learn/rhythm-ectopy?scene=M03.S14",
  );
  expect(learningReturnLabel("/learn/rhythm-ectopy?scene=M03.S14", ["lesson"])).toBe("Return to lesson");

  for (const unsafe of [
    "https://evil.test/steal",
    "//evil.test/steal",
    "/\\evil.test/steal",
    "/learn/../profile?tab=plan",
    "/profile?tab=plan&returnTo=%2F%2Fevil.test",
    "/review?next=%2F%2Fevil.test",
    "/learn/rhythm-ectopy?returnTo=%2F%2Fevil.test",
  ]) {
    expect(parseLearningReturn(unsafe)).toBeNull();
  }
});

test("Rapid completion carries the graded finding into Clinical and preserves a Rapid return", () => {
  expect(rapidClinicalHandoffHref([
    { missedObjectives: ["atrial_fibrillation"], correctObjectives: [] },
    { missedObjectives: [], correctObjectives: ["sinus_rhythm"] },
  ], new Map([
    ["atrial_fibrillation", { lane: "ward" as const }],
    ["sinus_rhythm", { lane: "clinic" as const }],
  ]))).toBe(
    "/practice?focus=atrial_fibrillation&subskill=apply_in_context&lane=ward&returnTo=%2Frapid",
  );
  expect(parseLearningReturn("/rapid", ["lesson", "study_plan", "rapid"])).toEqual({
    href: "/rapid",
    surface: "rapid",
    label: "Return to Rapid",
  });

  expect(rapidClinicalHandoffHref([
    { missedObjectives: ["atrial_fibrillation"], correctObjectives: ["sinus_rhythm"] },
    { missedObjectives: [], correctObjectives: ["sinus_rhythm"] },
    { missedObjectives: [], correctObjectives: ["sinus_rhythm"] },
  ], new Map([
    ["atrial_fibrillation", { lane: "ward" as const }],
    ["sinus_rhythm", { lane: "clinic" as const }],
  ]))).toContain("focus=atrial_fibrillation");

  expect(parseRapidLaunchIntent("?returnTo=%2Fpractice").returnTo).toBe("/practice");
  expect(learningReturnLabel("/practice", ["lesson", "study_plan", "clinical"])).toBe("Return to clinical cases");
});

test("Rapid receipt summary never describes accepted negative evidence as recognized", () => {
  const timeout = rapidReceiptSummary([
    { concept: "sinus_rhythm", subskill: "recognize", accepted: true, correct: false },
    { concept: "axis_normal", subskill: "recognize", accepted: true, correct: false },
    { concept: "nonspecific_st_t_change", subskill: "recognize", accepted: true, correct: false },
  ]);
  expect(timeout).toContain("review needed for sinus rhythm, axis normal, nonspecific st t change");
  expect(timeout).toContain("No positive evidence was earned");
  expect(timeout).not.toContain("Progress saved");
  expect(timeout).not.toMatch(/recognized/i);

  const mixed = rapidReceiptSummary([
    { concept: "sinus_rhythm", subskill: "recognize", accepted: true, correct: true },
    { concept: "axis_normal", subskill: "recognize", accepted: true, correct: false },
  ]);
  expect(mixed).toContain("recognized sinus rhythm");
  expect(mixed).toContain("review needed for axis normal");
});

test("adaptive launch parsers accept only mode-supported recommended lengths", () => {
  expect(parseTrainingLaunchIntent(
    "?concept=right_bundle_branch_block&receiptConcept=right_bundle_branch_block&subskill=discriminate&suggestedLength=25&returnTo=%2Fprofile%3Ftab%3Dplan",
  )).toMatchObject({
    suggestedLength: 25,
    returnTo: "/profile?tab=plan",
  });
  expect(parseTrainingLaunchIntent("?suggestedLength=11").suggestedLength).toBeNull();
  expect(parseTrainingLaunchIntent("?suggestedLength=25.0").suggestedLength).toBeNull();

  expect(parseRapidLaunchIntent(
    "?focus=atrial_fibrillation&receiptConcept=atrial_fibrillation&subskill=recognize&suggestedLength=10&returnTo=%2Fprofile%3Ftab%3Dplan",
  )).toEqual({
    focus: "atrial_fibrillation",
    secondaryConcept: "",
    secondaryConceptInvalid: false,
    receiptConcept: "atrial_fibrillation",
    subskill: "recognize",
    returnTo: "/profile?tab=plan",
    suggestedLength: 10,
    pace: null,
    requestedPace: null,
    paceAdjustedForCompleteRead: false,
    completeReadRequired: false,
  });
  expect(parseRapidLaunchIntent("?suggestedLength=5001").suggestedLength).toBeNull();
  expect(parseRapidLaunchIntent("?suggestedLength=10e0").suggestedLength).toBeNull();
  expect(parseRapidLaunchIntent("?pace=ward")).toMatchObject({
    pace: "ward",
    requestedPace: "ward",
    paceAdjustedForCompleteRead: false,
  });
  expect(parseRapidLaunchIntent("?pace=turbo").pace).toBeNull();
  expect(parseRapidLaunchIntent("?subskill=synthesize&pace=emergency")).toMatchObject({
    pace: "ward",
    requestedPace: "emergency",
    paceAdjustedForCompleteRead: true,
    completeReadRequired: true,
  });

  expect(parseRapidLaunchIntent(
    "?focus=normal_ecg&secondaryConcept=atrial_fibrillation&receiptConcept=integrated_interpretation&subskill=synthesize",
  )).toMatchObject({
    focus: "normal_ecg",
    secondaryConcept: "atrial_fibrillation",
    secondaryConceptInvalid: false,
  });
  for (const unsafe of [
    "?focus=normal_ecg&secondaryConcept=https%3A%2F%2Fevil.test",
    "?focus=normal_ecg&secondaryConcept=normal_ecg",
    "?focus=normal_ecg&secondaryConcept=atrial_fibrillation&secondaryConcept=rate",
  ]) {
    expect(parseRapidLaunchIntent(unsafe)).toMatchObject({
      secondaryConcept: "",
      secondaryConceptInvalid: true,
    });
  }
});
