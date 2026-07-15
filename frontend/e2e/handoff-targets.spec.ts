import { expect, test } from "@playwright/test";
import { guidedHandoffHref, resolveHandoffTarget } from "../src/lib/learning/handoffTargets";
import { NATIVE_PRODUCTION_MODULES } from "../src/lib/learning/modules";
import { competencyPracticeHref } from "../src/lib/competencyRoutes";
import {
  campaignMatchesTrainingLaunch,
  parseTrainingLaunchIntent,
  trainingFeedbackHeading,
  trainingMasteryPresentation,
} from "../src/lib/learning/trainingLogic";
import type { LearnerProfile } from "../src/lib/types";

test("Training feedback names target-present and contrast decisions without leaking phase", () => {
  expect(trainingFeedbackHeading({ correct: true, expectedAnswer: "present", measurementRehearsal: false })).toBe("Pattern recognized");
  expect(trainingFeedbackHeading({ correct: true, expectedAnswer: "absent", measurementRehearsal: false })).toBe("Contrast distinguished");
  expect(trainingFeedbackHeading({ correct: true, expectedAnswer: null, measurementRehearsal: false })).toBe("Decision supported");
  expect(trainingFeedbackHeading({ correct: false, expectedAnswer: "present", measurementRehearsal: false })).toBe("Re-check the discriminator");
});

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

test("every Guided to Rapid handoff launches an explicit exact receipt while preserving its source objective", () => {
  const rapidHandoffs = NATIVE_PRODUCTION_MODULES.flatMap((module) => module.scenes.flatMap((scene) => (
    scene.handoffs
      .filter((handoff) => handoff.mode === "rapid")
      .map((handoff) => ({ module, scene, handoff }))
  )));
  expect(rapidHandoffs.length).toBeGreaterThan(0);

  for (const { module, scene, handoff } of rapidHandoffs) {
    if (!handoff.destination) throw new Error(`${module.id}:${scene.id} has no executable Rapid destination`);
    const href = guidedHandoffHref(handoff, { moduleId: module.id, sceneId: scene.id });
    const url = new URL(href, "https://example.test");
    expect(url.pathname).toBe("/rapid");
    expect(url.searchParams.get("sourceObjective")).toBe(handoff.concept);
    expect(url.searchParams.get("focus")).toBe(handoff.destination.focus);
    expect(url.searchParams.get("receiptConcept")).toBe(
      handoff.destination.receiptConcept ?? handoff.destination.focus,
    );
    expect(url.searchParams.get("subskill")).toBe(handoff.destination.subskill);
    expect(handoff.destination.subskill).toBe("recognize");
    expect(url.searchParams.get("returnTo")).toBe(`/learn/${module.id}?scene=${scene.id}`);
  }
});

test("every Guided Clinical handoff names a lane with a real exact application surface", () => {
  const supported = new Set([
    "clinic:normal_ecg",
    "clinic:bradycardia",
    "clinic:qtc_prolongation",
    "ward:atrial_fibrillation",
    "ward:left_ventricular_hypertrophy",
    "ed:bradycardia",
    "ed:supraventricular_tachycardia",
  ]);
  const clinicalHandoffs = NATIVE_PRODUCTION_MODULES.flatMap((module) => module.scenes.flatMap((scene) => (
    scene.handoffs
      .filter((handoff) => handoff.mode === "clinical")
      .map((handoff) => ({ module, scene, handoff }))
  )));
  expect(clinicalHandoffs.length).toBeGreaterThan(0);

  for (const { module, scene, handoff } of clinicalHandoffs) {
    if (!handoff.destination?.lane) throw new Error(`${module.id}:${scene.id} has no executable Clinical lane`);
    const url = new URL(guidedHandoffHref(handoff, { moduleId: module.id, sceneId: scene.id }), "https://example.test");
    expect(url.pathname).toBe("/practice");
    expect(url.searchParams.get("sourceObjective")).toBe(handoff.concept);
    expect(url.searchParams.get("focus")).toBe(handoff.destination.focus);
    expect(url.searchParams.get("subskill")).toBe("apply_in_context");
    expect(url.searchParams.get("lane")).toBe(handoff.destination.lane);
    expect(supported.has(`${handoff.destination.lane}:${handoff.destination.focus}`)).toBe(true);
    expect(handoff.supportLevel).not.toBe("independent");
  }
});

test("Guided handoffs reject a missing source or executable destination", () => {
  expect(() => guidedHandoffHref({
    mode: "rapid",
    label: "Broken handoff",
    concept: " ",
    subskill: "synthesize",
    supportLevel: "independent",
  }, { moduleId: "integration", sceneId: "capstone" })).toThrow(/source objective/i);

  expect(() => guidedHandoffHref({
    mode: "clinical",
    label: "Broken handoff",
    concept: "bradycardia_with_pulse",
    subskill: "apply_in_context",
    supportLevel: "faded",
  }, { moduleId: "conduction", sceneId: "context" })).toThrow(/executable destination/i);
});

test("Training launch intent preserves the authored case family, receipt, subskill, and profile return", () => {
  const intent = parseTrainingLaunchIntent(
    "?focus=left_bundle_branch_block&concept=right_bundle_branch_block&receiptConcept=integrated_interpretation&subskill=measure&returnTo=%2Fprofile",
  );
  expect(intent).toEqual({
    requestedCaseConcept: "right_bundle_branch_block",
    receiptConcept: "integrated_interpretation",
    subskill: "measure",
    returnTo: "/profile",
    suggestedLength: null,
    hasExplicitPreset: true,
    isHandoff: true,
  });
  expect(parseTrainingLaunchIntent("?concept=right_bundle_branch_block&returnTo=https%3A%2F%2Fevil.test").returnTo).toBe("");
});

test("an explicit Training handoff resumes only a campaign with the same full receipt contract", () => {
  const intent = parseTrainingLaunchIntent(
    "?concept=right_bundle_branch_block&receiptConcept=integrated_interpretation&subskill=measure&returnTo=%2Fprofile",
  );
  const matching = {
    conceptId: "right_bundle_branch_block",
    subskill: "measure",
    contextKey: "receiptConcept=integrated_interpretation&returnTo=%2Fprofile",
  };
  expect(campaignMatchesTrainingLaunch(matching, intent, "right_bundle_branch_block")).toBe(true);
  expect(campaignMatchesTrainingLaunch({ ...matching, subskill: "recognize" }, intent, "right_bundle_branch_block")).toBe(false);
  expect(campaignMatchesTrainingLaunch({ ...matching, conceptId: "left_bundle_branch_block" }, intent, "right_bundle_branch_block")).toBe(false);
  expect(campaignMatchesTrainingLaunch({ ...matching, contextKey: "receiptConcept=right_bundle_branch_block&returnTo=%2Fprofile" }, intent, "right_bundle_branch_block")).toBe(false);
});

test("Training mastery language separates unseen, formative practice, and demonstrated weakness", () => {
  const unseen = trainingMasteryPresentation({ subskillMastery: [] }, "right_bundle_branch_block", "recognize");
  expect(unseen).toMatchObject({ state: "unseen", label: "Not assessed yet", value: null, recommendationLabel: "unassessed skill" });

  const baseRow = {
    concept: "right_bundle_branch_block",
    subskill: "recognize",
    formativeScore: 0.8,
    independentMastery: 0.15,
    attempts: 3,
    independentAttempts: 0,
    correct: 2,
    highConfidenceWrong: 0,
    lastPracticedAt: null,
    lastIndependentAt: null,
    lastIndependentCorrect: null,
    nextDueAt: null,
    dueState: "unseen",
    isDue: false,
    overdueDays: 0,
    daysUntilDue: null,
    stabilityDays: 0,
    lapses: 0,
    spacedRetrievals: 0,
    distinctEligibleEcgs: 0,
    distinctSuccessfulEcgs: 0,
    distinctModes: 0,
    distinctMorphologies: 0,
    retentionUncertainty: null,
  } as LearnerProfile["subskillMastery"][number];
  const formative = trainingMasteryPresentation({ subskillMastery: [baseRow] }, "right_bundle_branch_block", "recognize");
  expect(formative).toMatchObject({ state: "formative", label: "Practiced · not independently checked", value: null });

  const assessed = trainingMasteryPresentation({
    subskillMastery: [{ ...baseRow, independentAttempts: 2, independentMastery: 0.2, dueState: "due", isDue: true }],
  }, "right_bundle_branch_block", "recognize");
  expect(assessed).toMatchObject({ state: "assessed", label: "Current mastery estimate · 20%", value: 0.2, recommendationLabel: "needs practice" });
});
