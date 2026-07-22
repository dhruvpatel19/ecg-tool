import { expect, test } from "@playwright/test";
import { gradeInteraction } from "../src/lib/learning/gradeInteraction";
import {
  evidenceRevealsSolution,
  interactionEvidenceResolved,
  UNSUCCESSFUL_ATTEMPTS_BEFORE_SOLUTION,
} from "../src/lib/learning/interactionTypes";
import { M01_FOUNDATIONS_MODULE } from "../src/lib/learning/modules";
import { registerVerifiedE2ELearner } from "./helpers";

test("the third unsuccessful grade preserves the miss and closes only as guided support", () => {
  const interaction = M01_FOUNDATIONS_MODULE.scenes
    .find((scene) => scene.id === "S0")!
    .interactions.find((item) => item.id === "m01-s0-sweep");
  if (!interaction || interaction.kind !== "sequence") throw new Error("Missing Foundations sweep interaction");

  const wrongOrder = [...interaction.correctOrder].reverse();
  const first = gradeInteraction(interaction, wrongOrder, 1);
  const second = gradeInteraction(interaction, wrongOrder, 2);
  const third = gradeInteraction(interaction, wrongOrder, UNSUCCESSFUL_ATTEMPTS_BEFORE_SOLUTION);

  expect(first).toMatchObject({ correct: false, solutionRevealed: false });
  expect(second).toMatchObject({ correct: false, solutionRevealed: false });
  expect(evidenceRevealsSolution(first)).toBe(false);
  expect(evidenceRevealsSolution(second)).toBe(false);

  expect(third).toMatchObject({
    correct: false,
    attempts: 3,
    assistance: "scaffolded",
    hintsUsed: 1,
    solutionRevealed: true,
  });
  expect(third.score).toBeLessThan(1);
  expect(evidenceRevealsSolution(third)).toBe(true);
  expect(interactionEvidenceResolved(third)).toBe(true);
});

test("Foundations reveals each worked answer after three misses and then permits progression", async ({ page }) => {
  const account = await registerVerifiedE2ELearner(page, {
    prefix: "foundations_three_attempts",
    displayName: "Three Attempt Learner",
  });
  const learnerId = account.user.userId;
  const guidedBodies: Array<Record<string, unknown>> = [];

  await page.route(`**/api/backend/learners/${learnerId}/foundations-native-migration`, (route) => route.fulfill({
    json: {
      learnerId,
      migrationVersion: "foundations-native-v2",
      result: "not_needed",
      resumeSceneId: "S0",
      items: [],
      legacyPracticePreserved: false,
    },
  }));
  await page.route(`**/api/backend/learners/${learnerId}/pathway-progress**`, (route) => route.fulfill({
    json: { learnerId, items: [] },
  }));
  await page.route("**/api/backend/learning-events/guided", (route) => {
    guidedBodies.push(route.request().postDataJSON() as Record<string, unknown>);
    return route.fulfill({
      status: 200,
      json: {
        eventId: guidedBodies.length,
        requestedEvidenceLevel: "guided",
        effectiveEvidenceLevel: "guided",
        receipts: [],
      },
    });
  });

  await page.goto("/learn/foundations?scene=S0");
  const check = page.getByRole("button", { name: "Check order" });

  await expect(check).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "A reliable ECG read, every time" })).toBeVisible();
  await expect(page.getByText("1 of 7 checkpoints explored", { exact: true })).toBeVisible();
  for (let step = 1; step < 7; step += 1) {
    await page.getByRole("button", { name: "Next checkpoint", exact: true }).click();
  }
  await expect.poll(() => guidedBodies.length).toBe(0);
  await expect(check).toHaveCount(0);
  await page.getByRole("button", { name: "Try the first check", exact: true }).click();
  await expect(check).toBeVisible();

  await check.click();
  await expect(page.getByLabel("Worked solution")).toHaveCount(0);
  await check.click();
  await expect(page.getByLabel("Worked solution")).toHaveCount(0);
  await check.click();

  const firstSolution = page.getByLabel("Worked solution");
  await expect(firstSolution).toBeVisible();
  await expect(firstSolution.getByText("1. Calibration & quality", { exact: true })).toBeVisible();
  await expect(firstSolution.getByText("7. Synthesis", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Check order" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Continue" })).toBeVisible();
  await expect.poll(() => guidedBodies.length).toBe(3);
  expect(guidedBodies[2]).toMatchObject({
    interactionId: "m01-s0-sweep",
    correct: false,
    attempts: 3,
    assistance: "scaffolded",
    hintsUsed: 1,
    evidenceLevel: "guided",
  });

  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: "Which habits make an ECG interpretation reliable?" })).toBeVisible();
  await page.getByRole("button", { name: "If one lead is noisy, treat every part of the ECG as uninterpretable." }).click();

  const secondCheck = page.getByRole("button", { name: "Check answer" });
  await secondCheck.click();
  await expect(page.getByLabel("Worked solution")).toHaveCount(0);
  await secondCheck.click();
  await expect(page.getByLabel("Worked solution")).toHaveCount(0);
  await secondCheck.click();

  await expect(page.getByLabel("Worked solution")).toBeVisible();
  await expect.poll(() => guidedBodies.length).toBe(6);
  expect(guidedBodies[5]).toMatchObject({
    interactionId: "m01-s0-scope",
    correct: false,
    attempts: 3,
    assistance: "scaffolded",
    evidenceLevel: "guided",
  });
  await expect(page.getByLabel("Completion and transfer")).toBeVisible();
  await expect(page.getByRole("button", { name: /Next scene/ })).toBeEnabled();
});
