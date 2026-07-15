import { expect, test } from "@playwright/test";
import { registerVerifiedE2ELearner } from "./helpers";

let userId = "";

test.describe("Foundations progress contract", () => {
  test.beforeEach(async ({ page }) => {
    const account = await registerVerifiedE2ELearner(page, {
      prefix: "foundations_progress",
      displayName: "Foundation Learner",
    });
    userId = account.user.userId;
  });

  test("the host and embedded module agree after refresh and ignore unknown scene receipts", async ({ page }) => {
    await page.route(`**/api/backend/learners/${userId}/pathway-progress**`, (route) => route.fulfill({
      json: {
        learnerId: userId,
        items: [{
          pathwayId: "foundations-curriculum",
          moduleId: "foundations",
          sceneId: "foundations-progress",
          status: "attempted",
          activeInteractionIndex: 2,
          completedActionIds: ["S0", "S1", "UNKNOWN_SCENE"],
          state: {
            completedScenes: 1,
            totalScenes: 13,
            foundationState: {
              completed: ["S0", "S1", "UNKNOWN_SCENE"],
              skipped: ["S0", "S3", "ALSO_UNKNOWN"],
              current: 2,
              bestAccuracy: 80,
              nv: {},
              testedOut: {},
            },
          },
        }],
      },
    }));

    await page.goto("/learn/foundations");
    const moduleFrame = page.frameLocator('iframe[title="Foundations of the ECG Read"]');

    await expect(page.getByText("1/13 scenes", { exact: true })).toBeVisible();
    await expect(moduleFrame.locator("#progPct")).toHaveText("8% · 2 review");
    await expect(moduleFrame.locator("#partRail")).toContainText("1/4 · 2 later");

    await page.reload();
    await expect(page.getByText("1/13 scenes", { exact: true })).toBeVisible();
    await expect(moduleFrame.locator("#progPct")).toHaveText("8% · 2 review");
  });

  test("authenticated progress replaces stale account cache with the server-owned snapshot", async ({ page }) => {
    const progressItem = {
      pathwayId: "foundations-curriculum",
      moduleId: "foundations",
      sceneId: "foundations-progress",
      status: "attempted",
      activeInteractionIndex: 3,
      completedActionIds: ["S0", "S1", "S2"],
      state: {
        completedScenes: 3,
        totalScenes: 13,
        bestAccuracy: 70,
        foundationState: {
          completed: ["S0", "S1", "S2", "NOT_A_SCENE"],
          skipped: [],
          current: 3,
          bestAccuracy: 70,
          nv: {},
          testedOut: {},
        },
      },
    };

    await page.addInitScript((key) => {
      if (window.top !== window) return;
      window.localStorage.setItem(key, JSON.stringify({
        completed: { S0: true }, current: 1, nv: {}, skipped: {}, testedOut: {},
      }));
    }, `foundations_state_v1:${userId}`);
    await page.route(`**/api/backend/learners/${userId}/pathway-progress**`, async (route) => {
      await route.fulfill({ json: { learnerId: userId, items: [progressItem] } });
    });

    await page.goto("/learn/foundations");

    const moduleFrame = page.frameLocator('iframe[title="Foundations of the ECG Read"]');
    await expect(page.getByText("3/13 scenes", { exact: true })).toBeVisible();
    await expect(moduleFrame.locator("#progPct")).toHaveText("23%");

    await page.reload();
    await expect(page.getByText("3/13 scenes", { exact: true })).toBeVisible();
    await expect(moduleFrame.locator("#progPct")).toHaveText("23%");
  });

  test("the embedded lesson follows the page scroll and keeps a predictable keyboard boundary", async ({ page }) => {
    await page.route(`**/api/backend/learners/${userId}/pathway-progress**`, (route) => route.fulfill({
      json: { learnerId: userId, items: [] },
    }));
    for (const viewport of [
      { width: 320, height: 720 },
      { width: 390, height: 844 },
      { width: 1024, height: 768 },
      { width: 1440, height: 900 },
    ]) {
      await page.setViewportSize(viewport);
      await page.goto("/learn/foundations");
      const moduleFrame = page.frameLocator('iframe[title="Foundations of the ECG Read"]');
      await expect(moduleFrame.locator("#sceneScroll")).toBeVisible();

      await expect.poll(async () => moduleFrame.locator("html").evaluate(() => ({
        seamlessStyle: Boolean(document.getElementById("trace-foundations-seamless-embed")),
        frameScrolls: document.documentElement.scrollHeight > window.innerHeight + 1,
        bodyOverflowY: getComputedStyle(document.body).overflowY,
        sceneScrolls: document.querySelector<HTMLElement>("#sceneScroll")!.scrollHeight
          > document.querySelector<HTMLElement>("#sceneScroll")!.clientHeight + 1,
        sceneOverflowY: getComputedStyle(document.querySelector<HTMLElement>("#sceneScroll")!).overflowY,
        tutorScrolls: document.querySelector<HTMLElement>("#tutorStream")!.scrollHeight
          > document.querySelector<HTMLElement>("#tutorStream")!.clientHeight + 1,
        tutorOverflowY: getComputedStyle(document.querySelector<HTMLElement>("#tutorStream")!).overflowY,
      }))).toEqual({
        seamlessStyle: true,
        frameScrolls: false,
        bodyOverflowY: "hidden",
        sceneScrolls: false,
        sceneOverflowY: "visible",
        tutorScrolls: false,
        tutorOverflowY: "visible",
      });

      expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
      const frameBox = await page.locator('iframe[title="Foundations of the ECG Read"]').boundingBox();
      expect(frameBox).not.toBeNull();
      expect(frameBox!.width).toBeLessThanOrEqual(viewport.width);
    }

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/learn/foundations");
    const moduleFrame = page.frameLocator('iframe[title="Foundations of the ECG Read"]');
    await expect(moduleFrame.locator("#nvBtn")).toBeVisible();
    const modulesLink = page.getByRole("link", { name: "Modules" });
    await modulesLink.focus();
    await page.keyboard.press("Tab");
    await expect(moduleFrame.locator("#nvBtn")).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    await expect(modulesLink).toBeFocused();
  });
});
