import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { registerVerifiedE2ELearner } from "./helpers";

const PUBLIC_ROUTES = [
  { name: "landing", path: "/" },
  { name: "sign in", path: "/login" },
] as const;

const PRIVATE_ROUTES = [
  { name: "dashboard", path: "/home" },
  { name: "Guided curriculum", path: "/learn" },
  { name: "Guided ECG workspace", path: "/learn/leads-vectors" },
  { name: "Foundations workspace", path: "/learn/foundations" },
  { name: "Focused Practice", path: "/train" },
  { name: "Rapid Practice", path: "/rapid" },
  { name: "Clinical Cases", path: "/practice" },
  { name: "progress", path: "/profile" },
  { name: "study plan", path: "/review" },
  { name: "account and privacy", path: "/account" },
] as const;

async function expectNoWcagViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const summary = results.violations.map((violation) => ({
    id: violation.id,
    impact: violation.impact,
    help: violation.help,
    targets: violation.nodes.map((node) => node.target.join(" ")),
  }));

  expect(summary, JSON.stringify(summary, null, 2)).toEqual([]);
}

test.describe("WCAG public entry", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/backend/auth/me", (route) => route.fulfill({ json: { authenticated: false, user: null } }));
  });

  for (const route of PUBLIC_ROUTES) {
    test(`${route.name} has no detectable A/AA violations`, async ({ page }) => {
      await page.goto(route.path);
      await expect(page.getByRole("main")).toBeVisible();
      await page.waitForTimeout(500);

      await expectNoWcagViolations(page);
    });
  }
});

test.describe("WCAG authenticated student shell", () => {
  test.beforeEach(async ({ page }) => {
    await registerVerifiedE2ELearner(page, { prefix: "a11y" });
  });

  for (const route of PRIVATE_ROUTES) {
    test(`${route.name} has no detectable A/AA violations`, async ({ page }) => {
      await page.goto(route.path);
      await expect(page.getByRole("main")).toBeVisible();
      await page.waitForTimeout(500);

      await expectNoWcagViolations(page);
    });
  }

  test("active Focused Practice workspace has no detectable A/AA violations", async ({ page }) => {
    await page.goto("/train?concept=right_bundle_branch_block");
    await page.getByRole("button", { name: "Start focused practice" }).click();
    await expect(page.getByRole("region", { name: "Focused training set" })).toBeVisible({ timeout: 30_000 });
    await expectNoWcagViolations(page);
  });

  test("active Rapid workspace has no detectable A/AA violations", async ({ page }) => {
    await page.goto("/rapid");
    await page.getByRole("button", { name: /No timer/ }).click();
    await page.getByRole("button", { name: "Start rapid set" }).click();
    await expect(page.getByRole("complementary", { name: "Rapid ECG response" })).toBeVisible({ timeout: 30_000 });
    await expectNoWcagViolations(page);
  });

  test("active Clinical workspace has no detectable A/AA violations", async ({ page }) => {
    await page.goto("/practice");
    await page.getByRole("button", { name: "Guided" }).click();
    await page.getByRole("button", { name: "Begin learning set" }).click();
    await expect(page.getByRole("heading", { name: "Record your initial ECG read" })).toBeVisible({ timeout: 30_000 });
    await expectNoWcagViolations(page);
  });
});
