import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Locator, type Page } from "@playwright/test";
import type { PathwayProgressItem } from "../src/lib/api";
import { collectConsoleErrors, registerVerifiedE2ELearner } from "./helpers";

let owner = "";
let progressItems: PathwayProgressItem[] = [];

function completedEvidence(interactionId: string, kind: string) {
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

function attemptedScene(
  sceneId: string,
  activeInteractionIndex: number,
  evidence: Record<string, ReturnType<typeof completedEvidence>>,
): PathwayProgressItem {
  return {
    pathwayId: "production-curriculum",
    moduleId: "foundations",
    sceneId,
    status: "attempted",
    activeInteractionIndex,
    completedActionIds: Object.keys(evidence),
    state: {
      status: "attempted",
      activeInteractionIndex,
      revealedMechanismCount: 1,
      teachingStep: 2,
      teachingVisitedSteps: [0, 1, 2],
      teachingComplete: true,
      evidence,
      equivalentRetryCount: 0,
      assistedInteractionIds: [],
    },
  };
}

async function setRangeWithKeyboard(slider: Locator, edge: "Home" | "End", key: "ArrowRight" | "ArrowLeft", presses: number) {
  await slider.focus();
  await slider.press(edge);
  for (let index = 0; index < presses; index += 1) await slider.press(key);
}

async function expectNoAxeViolations(page: Page) {
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(result.violations.map((violation) => ({
    id: violation.id,
    impact: violation.impact,
    targets: violation.nodes.map((node) => node.target),
  }))).toEqual([]);
}

test.describe("native Foundations accessibility and tutor boundaries", () => {
  test.beforeEach(async ({ page }) => {
    const account = await registerVerifiedE2ELearner(page, {
      prefix: "foundations_accessibility",
      displayName: "Foundation Learner",
    });
    owner = account.user.userId;
    progressItems = [];
    await page.route(`**/api/backend/learners/${owner}/foundations-native-migration`, (route) => route.fulfill({
      json: {
        learnerId: owner,
        migrationVersion: "foundations-native-v2",
        result: "not_needed",
        resumeSceneId: "S0",
        items: [],
        legacyPracticePreserved: false,
      },
    }));
    await page.route(`**/api/backend/learners/${owner}/pathway-progress**`, (route) => route.fulfill({
      json: { learnerId: owner, items: progressItems },
    }));
  });

  test("the authored ECG lab has a complete keyboard path and records only guided simulation evidence", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    const guidedBodies: Array<Record<string, unknown>> = [];
    progressItems = [attemptedScene("S1", 1, {
      "m01-s1-cycle": completedEvidence("m01-s1-cycle", "model_explore"),
    })];
    await page.route("**/api/backend/learning-events/guided", (route) => {
      guidedBodies.push(route.request().postDataJSON() as Record<string, unknown>);
      return route.fulfill({
        status: 200,
        json: {
          eventId: 1,
          requestedEvidenceLevel: "guided",
          effectiveEvidenceLevel: "guided",
          receipts: [],
        },
      });
    });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/learn/foundations?scene=S1");

    await expect(page.locator('iframe[title*="Foundations"]')).toHaveCount(0);
    await expect(page.getByRole("img", { name: /II practice ECG waveform/ })).toBeVisible();
    await expect(page.getByText(/Practice waveform:.*not a patient ECG/)).toBeVisible();
    const smallGrid = page.locator('pattern[id="small-grid-m01-s1-landmarks"]');
    await expect(smallGrid).toHaveAttribute("width", "36");
    await expect(smallGrid).toHaveAttribute("height", "36");
    const cursor = page.getByRole("slider", { name: "Keyboard cursor" });
    const target = page.getByRole("combobox", { name: "Target to mark" });
    const place = page.getByRole("button", { name: "Place target" });

    await setRangeWithKeyboard(cursor, "Home", "ArrowRight", 24);
    await expect(target).toHaveValue("p");
    await place.press("Enter");
    await expect(target).toHaveValue("qrs");

    await setRangeWithKeyboard(cursor, "Home", "ArrowRight", 43);
    await place.press("Enter");
    await expect(target).toHaveValue("t");

    await setRangeWithKeyboard(cursor, "End", "ArrowLeft", 29);
    await place.press("Enter");
    await page.getByRole("button", { name: "Check placement" }).press("Enter");

    await expect(page.getByText("That’s it", { exact: true })).toBeVisible();
    await expect.poll(() => guidedBodies.length).toBe(1);
    expect(guidedBodies[0]).toMatchObject({
      moduleId: "foundations",
      sceneId: "S1",
      interactionId: "m01-s1-landmarks",
      concept: "foundations_waveform_landmarks",
      subskills: ["localize"],
      evidenceLevel: "guided",
      caseId: null,
      caseProvenance: "authored_simulation",
      caseEligible: false,
    });
    await expectNoAxeViolations(page);
    expect(errors).toEqual([]);
  });

  test("an authored action beside a contrast ECG never inherits that patient's provenance", async ({ page }) => {
    const guidedBodies: Array<Record<string, unknown>> = [];
    progressItems = [attemptedScene("S5", 0, {})];
    await page.route("**/api/backend/learning-events/guided", (route) => {
      guidedBodies.push(route.request().postDataJSON() as Record<string, unknown>);
      return route.fulfill({
        status: 200,
        json: {
          eventId: 8,
          requestedEvidenceLevel: "guided",
          effectiveEvidenceLevel: "guided",
          receipts: [],
        },
      });
    });

    await page.goto("/learn/foundations?scene=S5");
    const cursor = page.getByRole("slider", { name: "Keyboard cursor" });
    const place = page.getByRole("button", { name: "Place target" });
    await setRangeWithKeyboard(cursor, "Home", "ArrowRight", 25);
    await place.press("Enter");
    await setRangeWithKeyboard(cursor, "Home", "ArrowRight", 44);
    await place.press("Enter");
    await page.getByRole("button", { name: "Check placement" }).press("Enter");

    await expect.poll(() => guidedBodies.length).toBe(1);
    expect(guidedBodies[0]).toMatchObject({
      moduleId: "foundations",
      sceneId: "S5",
      interactionId: "m01-s5-p-qrs",
      caseId: null,
      guidedContext: null,
      caseProvenance: "authored_simulation",
      caseEligible: false,
      evidenceLevel: "guided",
    });
  });

  test("the integrated transfer keeps Luna silent and exposes the claim ceiling before an attempt", async ({ page }) => {
    await page.goto("/learn/foundations?scene=S12");

    await expect(page.getByRole("heading", { name: "Two complete ECG reads" })).toBeVisible();
    await expect(page.getByText(/brings every Foundations skill together/)).toBeVisible();
    await expect(page.getByLabel("Completion and transfer")).toHaveCount(0);
    await expect(page.getByRole("progressbar", { name: "Lesson 13 of 13" })).toBeVisible();

    await page.getByRole("button", { name: "Ask Luna" }).click();
    const drawer = page.getByRole("dialog", { name: "Foundations tutor" });
    await expect(drawer).toBeVisible();
    const chat = drawer.getByLabel("Conversational tutor chat");
    await expect(chat.getByText("Conversational tutor is silent.")).toBeVisible();
    await expect(chat.locator(".tutor-chat-header button")).toHaveAttribute("aria-expanded", "false");
    await expect(chat.getByRole("textbox")).toHaveCount(0);

    await drawer.getByRole("button", { name: "Close tutor" }).click();
    await expect(page.getByText(/guided evidence|evidence ceiling|mastery receipt/i)).toHaveCount(0);
  });

  test("the 13-scene map and tutor drawer trap focus and restore it on a phone", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.setViewportSize({ width: 320, height: 780 });
    await page.goto("/learn/foundations?scene=S0");

    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
    const sceneMapTrigger = page.getByRole("button", { name: "Contents" });
    await sceneMapTrigger.focus();
    await sceneMapTrigger.press("Enter");
    const sceneMap = page.getByRole("dialog", { name: "Foundations of ECG Interpretation" });
    await expect(sceneMap).toBeVisible();
    await expect(sceneMap.getByRole("navigation", { name: "Module scenes" }).getByRole("button")).toHaveCount(13);
    await expect(sceneMap.getByRole("button", { name: "Close" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(sceneMapTrigger).toBeFocused();

    const tutorTrigger = page.getByRole("button", { name: "Ask Luna" });
    await tutorTrigger.press("Enter");
    const tutorDrawer = page.getByRole("dialog", { name: "Foundations tutor" });
    await expect(tutorDrawer.getByRole("button", { name: "Close tutor" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(tutorTrigger).toBeFocused();
    expect(errors).toEqual([]);
  });
});
