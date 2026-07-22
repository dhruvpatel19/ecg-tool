import { expect, test } from "@playwright/test";
import type { PathwayProgressItem } from "../src/lib/api";
import { registerVerifiedE2ELearner } from "./helpers";

type MigrationResponse = {
  learnerId: string;
  migrationVersion: "foundations-native-v2";
  result: "not_needed" | "migrated" | "replay" | "source_conflict";
  resumeSceneId: string;
  items: PathwayProgressItem[];
  legacyPracticePreserved: boolean;
};

let userId = "";
let migration: MigrationResponse;
let progressItems: PathwayProgressItem[] = [];
let savedProgressBodies: Array<Record<string, unknown>> = [];

function interactionEvidence(interactionId: string, kind = "sequence") {
  return {
    interactionId,
    kind,
    correct: true,
    partial: false,
    score: 1,
    attempts: 1,
    assistance: "independent",
    hintsUsed: 0,
    response: [],
    misconceptions: [],
    feedbackBranch: "correct",
  };
}

function progressItem(
  sceneId: string,
  status: PathwayProgressItem["status"],
  activeInteractionIndex = 0,
  evidence: Record<string, ReturnType<typeof interactionEvidence>> = {},
  teachingComplete = false,
): PathwayProgressItem {
  return {
    pathwayId: "production-curriculum",
    moduleId: "foundations",
    sceneId,
    status,
    activeInteractionIndex,
    completedActionIds: Object.keys(evidence),
    state: {
      status,
      activeInteractionIndex,
      revealedMechanismCount: 1,
      teachingStep: teachingComplete ? 2 : 0,
      teachingVisitedSteps: teachingComplete ? [0, 1, 2] : [0],
      teachingComplete,
      evidence,
      equivalentRetryCount: 0,
      assistedInteractionIds: [],
    },
    createdAt: "2026-07-19T12:00:00.000Z",
    updatedAt: "2026-07-19T12:00:00.000Z",
  };
}

test.describe("native Foundations progress contract", () => {
  test.beforeEach(async ({ page }) => {
    const account = await registerVerifiedE2ELearner(page, {
      prefix: "foundations_progress",
      displayName: "Foundation Learner",
    });
    userId = account.user.userId;
    progressItems = [];
    savedProgressBodies = [];
    migration = {
      learnerId: userId,
      migrationVersion: "foundations-native-v2",
      result: "not_needed",
      resumeSceneId: "S0",
      items: [],
      legacyPracticePreserved: false,
    };

    await page.route(`**/api/backend/learners/${userId}/foundations-native-migration`, (route) => route.fulfill({ json: migration }));
    await page.route(`**/api/backend/learners/${userId}/pathway-progress**`, (route) => {
      if (route.request().method() === "POST") {
        savedProgressBodies.push(route.request().postDataJSON() as Record<string, unknown>);
        return route.fulfill({ json: { learnerId: userId, items: progressItems } });
      }
      return route.fulfill({ json: { learnerId: userId, items: progressItems } });
    });
  });

  test("legacy history resumes in the native scene without being promoted to completion or mastery", async ({ page }) => {
    progressItems = [
      progressItem("S0", "viewed"),
      progressItem("S1", "attempted"),
      progressItem("S2", "skipped"),
      progressItem("S3", "attempted"),
      progressItem("S4", "needs-review"),
      progressItem("S5", "viewed"),
    ];
    migration = {
      ...migration,
      result: "migrated",
      resumeSceneId: "S5",
      items: progressItems,
      legacyPracticePreserved: true,
    };

    await page.goto("/learn/foundations");

    await expect(page).toHaveURL(/\/learn\/foundations\?scene=S5$/);
    await expect(page.getByRole("heading", { name: "Is there a sinus P-wave pattern?" })).toBeVisible();
    await expect(page.getByRole("progressbar", { name: "Lesson 6 of 13" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Build the idea before you use it" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Next scene" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Contents" })).toBeVisible();
    await expect(page.getByText(/Progress updated for/)).toHaveCount(0);
  });

  test("an allowlisted deep link wins over resume while an unknown scene fails closed", async ({ page }) => {
    migration = { ...migration, resumeSceneId: "S4" };

    await page.goto("/learn/foundations?scene=S9");
    await expect(page.getByRole("heading", { name: "Axis is the coarse QRS direction" })).toBeVisible();
    await expect(page).toHaveURL(/scene=S9$/);

    await page.goto("/learn/foundations?scene=NOT_A_FOUNDATION_SCENE");
    await expect(page.getByRole("heading", { name: "Regular first, then rate" })).toBeVisible();
    await expect(page).toHaveURL(/scene=S4$/);
  });

  test("server-owned native action state survives refresh and ignores the retired local cache", async ({ page }) => {
    progressItems = [progressItem("S1", "attempted", 1, {
      "m01-s1-cycle": interactionEvidence("m01-s1-cycle", "model_explore"),
    }, true)];
    migration = { ...migration, resumeSceneId: "S1", items: progressItems };
    await page.addInitScript((key) => {
      window.localStorage.setItem(key, JSON.stringify({
        completed: { S0: true, S1: true, S2: true, S3: true },
        current: 12,
        bestAccuracy: 100,
      }));
    }, `foundations_state_v1:${userId}`);

    await page.goto("/learn/foundations");
    await expect(page.getByText("2 of 3", { exact: true })).toBeVisible();
    await expect(page.getByRole("progressbar", { name: "Lesson 2 of 13" })).toBeVisible();

    await page.reload();
    await expect(page.getByText("2 of 3", { exact: true })).toBeVisible();
    await expect(page.getByRole("progressbar", { name: "Lesson 2 of 13" })).toBeVisible();
  });

  test("failed native guided evidence remains in the durable outbox and retries online", async ({ page }) => {
    progressItems = [progressItem("S0", "attempted", 1, {
      "m01-s0-sweep": interactionEvidence("m01-s0-sweep"),
    }, true)];
    migration = { ...migration, resumeSceneId: "S0", items: progressItems };
    const guidedBodies: Array<Record<string, unknown>> = [];
    let guidedAttempts = 0;
    await page.route("**/api/backend/learning-events/guided", async (route) => {
      guidedAttempts += 1;
      guidedBodies.push(route.request().postDataJSON() as Record<string, unknown>);
      if (guidedAttempts === 1) {
        return route.fulfill({ status: 503, json: { detail: "temporarily unavailable" } });
      }
      return route.fulfill({
        status: 200,
        json: {
          eventId: 99,
          requestedEvidenceLevel: "guided",
          effectiveEvidenceLevel: "guided",
          receipts: [],
        },
      });
    });

    await page.goto("/learn/foundations");
    await page.getByRole("button", { name: /Check calibration and signal quality/ }).click();
    await page.getByRole("button", { name: /Describe what the tracing supports/ }).click();
    await page.getByRole("button", { name: /not assessable/ }).click();
    await page.getByRole("button", { name: "Check answer" }).click();

    await expect(page.getByText(/queued on this device/)).toBeVisible();
    await expect.poll(() => guidedAttempts).toBe(1);
    await expect.poll(() => page.evaluate((key) => {
      const queued = JSON.parse(localStorage.getItem(key) ?? "[]") as unknown[];
      return queued.length;
    }, `trace-guided-evidence-outbox-v1:${userId}`)).toBe(1);
    expect(guidedBodies[0]).toMatchObject({
      moduleId: "foundations",
      sceneId: "S0",
      interactionId: "m01-s0-scope",
      evidenceLevel: "guided",
      caseProvenance: "authored_simulation",
      caseEligible: false,
    });

    await page.evaluate(() => window.dispatchEvent(new Event("online")));
    await expect.poll(() => guidedAttempts).toBe(2);
    await expect.poll(() => page.evaluate((key) => {
      const queued = JSON.parse(localStorage.getItem(key) ?? "[]") as unknown[];
      return queued.length;
    }, `trace-guided-evidence-outbox-v1:${userId}`)).toBe(0);
    await expect(page.getByText(/Practice saved/)).toBeVisible();
    expect(savedProgressBodies.length).toBeGreaterThan(0);
  });
});
