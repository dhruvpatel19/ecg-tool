import { expect, test } from "@playwright/test";
import {
  learningReturnLabel,
  parseLearningReturn,
  safeLearningReturn,
} from "../src/lib/learning/learningReturn";
import { parseRapidLaunchIntent, rapidClinicalHandoffHref, rapidDebriefPracticeHref, rapidReceiptSummary } from "../src/lib/learning/rapidLogic";
import { parseTrainingLaunchIntent } from "../src/lib/learning/trainingLogic";

test("learning returns accept only explicit internal destinations and label the study plan", () => {
  expect(parseLearningReturn("/home?panel=plan", ["lesson", "study_plan"])).toEqual({
    href: "/home?panel=plan",
    surface: "study_plan",
    label: "Return to study plan",
  });
  // Retain the old deep link while bookmarks and in-flight sessions migrate.
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
  expect(parseLearningReturn("/home?panel=calendar&date=2026-07-16", ["calendar"])).toEqual({
    href: "/home?panel=calendar&date=2026-07-16",
    surface: "calendar",
    label: "Return to calendar",
  });
  expect(parseLearningReturn("/home?panel=calendar&date=2026-07-16", ["study_plan"])).toBeNull();
  expect(parseLearningReturn("/home/review/lsr1_rapid_test", ["session_review"])).toEqual({
    href: "/home/review/lsr1_rapid_test",
    surface: "session_review",
    label: "Return to session review",
  });
  expect(parseLearningReturn("/home/review/../account", ["session_review"])).toBeNull();
  expect(parseLearningReturn("/home/review/lsr1_rapid_test?next=%2Faccount", ["session_review"])).toBeNull();

  for (const unsafe of [
    "https://evil.test/steal",
    "//evil.test/steal",
    "/\\evil.test/steal",
    "/learn/../profile?tab=plan",
    "/profile?tab=plan&returnTo=%2F%2Fevil.test",
    "/home?panel=plan&returnTo=%2F%2Fevil.test",
    "/home?panel=calendar",
    "/home?panel=calendar&date=2026-02-29",
    "/home?panel=calendar&date=2026-02-30",
    "/home?panel=calendar&date=2026-7-16",
    "/home?panel=calendar&date=0000-07-16",
    "/home?date=2026-07-16&panel=calendar",
    "/home?panel=calendar&date=2026-07-16&next=%2F%2Fevil.test",
    "/home?panel=calendar&date=2026-07-16&date=2026-07-17",
    "/review?next=%2F%2Fevil.test",
    "/learn/rhythm-ectopy?returnTo=%2F%2Fevil.test",
  ]) {
    expect(parseLearningReturn(unsafe)).toBeNull();
  }
});

test("Rapid debriefs keep emergency recognition in Emergency Rapid and send other skills to exact Training receipts", () => {
  expect(rapidDebriefPracticeHref({
    objectiveId: "ventricular_fibrillation",
    subskill: "recognize",
  })).toBe(
    "/rapid?focus=ventricular_fibrillation&receiptConcept=ventricular_fibrillation&subskill=recognize&practiceMode=emergency",
  );
  expect(rapidDebriefPracticeHref({
    objectiveId: "atrial_fibrillation",
    subskill: "discriminate",
  })).toBe(
    "/train?concept=atrial_fibrillation&receiptConcept=atrial_fibrillation&subskill=discriminate&returnTo=%2Frapid",
  );
});

test("Training and Rapid preserve the exact calendar date in their encoded return contract", () => {
  const calendarReturn = "/home?panel=calendar&date=2026-07-16";
  const trainingParams = new URLSearchParams({
    concept: "atrial_fibrillation",
    receiptConcept: "atrial_fibrillation",
    subskill: "recognize",
    returnTo: calendarReturn,
  });
  const trainingLaunchHref = `/train?${trainingParams.toString()}`;
  expect(trainingLaunchHref).toContain(
    "returnTo=%2Fhome%3Fpanel%3Dcalendar%26date%3D2026-07-16",
  );
  expect(parseTrainingLaunchIntent(trainingLaunchHref.slice("/train".length)).returnTo).toBe(calendarReturn);

  const rapidParams = new URLSearchParams({
    focus: "atrial_fibrillation",
    receiptConcept: "atrial_fibrillation",
    subskill: "recognize",
    returnTo: calendarReturn,
  });
  const rapidLaunchHref = `/rapid?${rapidParams.toString()}`;
  expect(rapidLaunchHref).toContain(
    "returnTo=%2Fhome%3Fpanel%3Dcalendar%26date%3D2026-07-16",
  );
  expect(parseRapidLaunchIntent(rapidLaunchHref.slice("/rapid".length)).returnTo).toBe(calendarReturn);
  expect(learningReturnLabel(calendarReturn, ["calendar"])).toBe("Return to calendar");
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
    "?concept=right_bundle_branch_block&receiptConcept=right_bundle_branch_block&subskill=discriminate&suggestedLength=25&returnTo=%2Fhome%3Fpanel%3Dplan",
  )).toMatchObject({
    suggestedLength: 25,
    returnTo: "/home?panel=plan",
  });
  expect(parseTrainingLaunchIntent("?suggestedLength=11").suggestedLength).toBeNull();
  expect(parseTrainingLaunchIntent("?suggestedLength=25.0").suggestedLength).toBeNull();

  expect(parseRapidLaunchIntent(
    "?focus=atrial_fibrillation&receiptConcept=atrial_fibrillation&subskill=recognize&suggestedLength=10&returnTo=%2Fhome%3Fpanel%3Dplan",
  )).toEqual({
    focus: "atrial_fibrillation",
    secondaryConcept: "",
    secondaryConceptInvalid: false,
    receiptConcept: "atrial_fibrillation",
    subskill: "recognize",
    returnTo: "/home?panel=plan",
    suggestedLength: 10,
    pace: null,
    requestedPace: null,
    practiceMode: null,
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
  expect(parseRapidLaunchIntent("?practiceMode=emergency").practiceMode).toBe("emergency");
  expect(parseRapidLaunchIntent("?practiceMode=unsafe").practiceMode).toBeNull();
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
