import { expect, test } from "@playwright/test";

test("verified mastery coach is actionable and not a coming-soon shell", async ({ page }) => {
  await page.goto("/review");
  await expect(page.getByRole("heading", { name: "Your next evidence plan" })).toBeVisible();
  await expect(page.getByText("Coming soon")).toHaveCount(0);
  await expect(page.getByText("Executable evidence path")).toBeVisible();
  await expect(page.locator(".mastery-stage").first()).toBeVisible();
  expect(await page.locator(".mastery-stage").count()).toBeGreaterThanOrEqual(1);
  await expect(page.getByRole("link", { name: /Open (train|rapid)/ }).first()).toBeVisible();

  const response = await page.request.get("/api/backend/adaptive/plan");
  expect(response.ok()).toBeTruthy();
  const plan = await response.json() as {
    plannerKind: string;
    generativeTutorUsed: boolean;
    stages: Array<{ mode: string; href: string; receiptConcept: string; receiptSubskill: string; evidenceKind: string }>;
  };
  expect(plan.plannerKind).toBe("verified_competency_scheduler");
  expect(plan.generativeTutorUsed).toBe(false);
  expect(plan.stages.length).toBeGreaterThan(0);
  for (const stage of plan.stages) {
    expect(["train", "rapid"]).toContain(stage.mode);
    expect(stage.href).toContain(`receiptConcept=${encodeURIComponent(stage.receiptConcept)}`);
    expect(stage.href).toContain(`subskill=${encodeURIComponent(stage.receiptSubskill)}`);
    expect(stage.evidenceKind).toBe("independent_transfer");
  }
});

test("mastery coach remains readable without horizontal overflow on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/review");
  await expect(page.getByRole("heading", { name: "Your next evidence plan" })).toBeVisible();
  await expect(page.locator(".mastery-stage").first()).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
