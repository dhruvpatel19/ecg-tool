import { expect, test } from "@playwright/test";
import { collectConsoleErrors, registerVerifiedE2ELearner } from "./helpers";
import { MODULES } from "../src/lib/modules";

let userId = "";

test.describe("production curriculum registry", () => {
  test.beforeEach(async ({ page }) => {
    const account = await registerVerifiedE2ELearner(page, {
      prefix: "production_registry",
      displayName: "Registry Learner",
    });
    userId = account.user.userId;
    await page.route(`**/api/backend/learners/${userId}/pathway-progress**`, (route) => route.fulfill({
      json: { learnerId: userId, items: [] },
    }));
  });

  test("fallback hub metadata cannot drift from the backend curriculum", async ({ page }) => {
    const response = await page.request.get("/api/backend/curriculum?learnerId=demo");
    expect(response.ok(), await response.text()).toBe(true);
    const payload = await response.json() as {
      modules: Array<{ id: string; order: number; title: string; overview: string; prerequisites: string[] }>;
    };
    expect(payload.modules.map((module) => ({
      id: module.id,
      order: module.order,
      title: module.title,
      blurb: module.overview,
      prerequisites: module.prerequisites,
    }))).toEqual(MODULES.map((module) => ({
      id: module.id,
      order: module.order,
      title: module.title,
      blurb: module.blurb,
      prerequisites: module.prerequisites,
    })));
  });

  test("Foundations remains an explicitly hosted module", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/learn/foundations");

    await expect(page.getByText("Module 1 of 10 · guided")).toBeVisible();
    await expect(page.locator('iframe[title="Foundations of the ECG Read"]')).toHaveAttribute(
      "src",
      `/foundations/index.html?owner=${userId}`,
    );
    expect(errors).toEqual([]);
  });

  test("native modules use the validated runtime and canonical scene navigation", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/learn/leads-vectors?scene=M02.S1");

    await expect(page.locator(".production-module")).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(".production-module").getByText("Module 2/10", { exact: true }).first()).toBeVisible();
    await expect(page.locator('.production-module a[href="/learn"]').first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Previous scene" })).toBeEnabled();
    await expect(page.getByRole("button", { name: "Next scene" })).toBeVisible();

    await page.goto("/learn/integration-transfer");
    await expect(page.locator(".production-module")).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(".production-module").getByText("Module 10/10", { exact: true }).first()).toBeVisible();
    await expect(page.locator('.production-module a[href="/learn"]').first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Previous scene" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Next scene" })).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("curriculum hub shows real scene counts and keeps pathway completion separate from competency", async ({ page }) => {
    await page.route(`**/api/backend/learners/${userId}/pathway-progress**`, (route) => route.fulfill({
      json: {
        learnerId: userId,
        items: [{
          pathwayId: "production-curriculum",
          moduleId: "leads-vectors",
          sceneId: "M02.S0",
          status: "complete",
          activeInteractionIndex: 0,
          completedActionIds: [],
          state: {
            status: "complete",
            activeInteractionIndex: 0,
            revealedMechanismCount: 1,
            evidence: {},
            equivalentRetryCount: 0,
            assistedInteractionIds: [],
          },
          createdAt: "2026-07-14T12:00:00Z",
          updatedAt: "2026-07-14T12:00:00Z",
        }],
      },
    }));
    await page.goto("/learn");

    await expect(page.getByText("118 interactive scenes")).toBeVisible({ timeout: 30_000 });
    const card = page.locator(".curriculum-module").filter({ hasText: "Leads, Vectors, Axis" });
    await card.locator(".curriculum-module-summary").click();
    await expect(card).toContainText("1/15 scenes complete");
    await expect(card).toContainText("15 interactive scenes · real-trace workspace");
    await expect(card).toContainText(/\d+% pathway · not independently assessed/);
  });

  test("keeps the closed curriculum map concise on a phone", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 780 });
    await page.goto("/learn");
    await expect(page.getByRole("heading", { name: /Understand the trace/ })).toBeVisible();
    const overviewLines = await page.locator(".curriculum-module-summary .curriculum-title small").evaluateAll((nodes) => (
      nodes.map((node) => {
        const rect = node.getBoundingClientRect();
        const lineHeight = Number.parseFloat(getComputedStyle(node).lineHeight);
        return Math.ceil(rect.height / lineHeight);
      })
    ));
    expect(overviewLines).toHaveLength(10);
    expect(overviewLines.every((lines) => lines <= 2)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  });

  test("lesson chips deep-link to their authored scene and unavailable lessons are not links", async ({ page }) => {
    await page.route("**/api/backend/curriculum?**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          modules: [{
            id: "leads-vectors",
            title: "Leads, Vectors, Axis & the Normal 12-Lead",
            overview: "Learn the lead map and axis.",
            order: 1,
            prerequisites: ["foundations"],
            lessons: [
              { id: "lead-territories", title: "Lead Layout & Territories", objectives: [{ id: "normal_ecg", label: "Normal ECG" }], reliableCaseCount: 12, available: true, mastery: 0.25 },
              { id: "axis", title: "Axis", objectives: [{ id: "axis_normal", label: "Normal axis" }], reliableCaseCount: 8, available: true, mastery: 0.25 },
              { id: "advanced-placement", title: "Advanced placement", objectives: [], reliableCaseCount: 0, available: false, mastery: 0 },
            ],
            reliableCaseCount: 12,
            available: true,
            mastery: 0.25,
          }],
        }),
      });
    });

    await page.goto("/learn");
    const card = page.locator(".curriculum-module").filter({ hasText: "Leads, Vectors, Axis" });
    await card.locator(".curriculum-module-summary").click();

    await expect(card.getByRole("link", { name: /Lead Layout & Territories/ })).toHaveAttribute(
      "href",
      "/learn/leads-vectors?scene=M02.S0",
    );
    await expect(card.getByRole("link", { name: /Axis/ })).toHaveAttribute(
      "href",
      "/learn/leads-vectors?scene=M02.S10",
    );
    const unavailable = card.getByLabel("Advanced placement unavailable");
    await expect(unavailable).toBeVisible();
    await expect(unavailable).not.toHaveAttribute("href");
    expect(await unavailable.evaluate((element) => ({ tagName: element.tagName, tabIndex: (element as HTMLElement).tabIndex })))
      .toEqual({ tagName: "DIV", tabIndex: -1 });
    await expect(card.getByRole("link", { name: /Advanced placement/ })).toHaveCount(0);
  });
});
