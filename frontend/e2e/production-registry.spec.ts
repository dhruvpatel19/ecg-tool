import { expect, test } from "@playwright/test";
import { collectConsoleErrors } from "./helpers";

test.describe("production curriculum registry", () => {
  test("Foundations remains an explicitly hosted module", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/learn/foundations");

    await expect(page.getByText("Module 1 of 10 · guided")).toBeVisible();
    await expect(page.locator('iframe[title="Foundations — Reading an ECG"]')).toHaveAttribute("src", "/foundations/index.html?owner=guest");
    expect(errors).toEqual([]);
  });

  test("native modules use the validated runtime and canonical boundary navigation", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/learn/leads-vectors?scene=M02.S1");

    await expect(page.locator(".production-module")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("Module 2 of 10 · Production guided pathway")).toBeVisible();
    await expect(page.locator('.guided-module-footer a[href="/learn/foundations"]')).toBeVisible();
    await expect(page.locator('.guided-module-footer a[href="/learn/rhythm-ectopy"]')).toBeVisible();

    await page.goto("/learn/integration-transfer");
    await expect(page.locator(".production-module")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("Module 10 of 10 · Production guided pathway")).toBeVisible();
    await expect(page.locator('.guided-module-footer a[href="/learn/ischemia-infarction"]')).toBeVisible();
    await expect(page.locator('.guided-module-footer a[href="/rapid"]')).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("curriculum hub shows real scene counts and keeps pathway completion separate from competency", async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("trace-production-curriculum-v1", JSON.stringify({
        "leads-vectors": {
          "M02.S0": { status: "complete", activeInteractionIndex: 0, revealedMechanismCount: 1, evidence: {}, equivalentRetryCount: 0 },
        },
      }));
    });
    await page.goto("/learn");

    await expect(page.getByText("118 interactive scenes")).toBeVisible({ timeout: 30_000 });
    const card = page.locator(".curriculum-module").filter({ hasText: "Leads, Vectors, Axis" });
    await card.locator(".curriculum-module-summary").click();
    await expect(card).toContainText("1/15 scenes complete");
    await expect(card).toContainText("15 interactive scenes · real-trace workspace");
    await expect(card).toContainText(/pathway · \d+% competency evidence/);
  });
});
