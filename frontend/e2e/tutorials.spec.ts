import { expect, test, type Page } from "@playwright/test";
import { registerVerifiedE2ELearner } from "./helpers";

async function navigateLegacy(page: Page, source: string, expectedPath: string) {
  await page.goto(source, { waitUntil: "domcontentloaded" });
  await expect.poll(() => new URL(page.url()).pathname).toBe(expectedPath);
  return new URL(page.url());
}

test.describe("legacy learner route compatibility", () => {
  test.beforeEach(async ({ page }) => {
    await registerVerifiedE2ELearner(page, { prefix: "legacy_routes" });
  });

  test("saved tutorial lessons land in their canonical Guided modules", async ({ page }) => {
    await navigateLegacy(page, "/tutorials?lesson=qt-qtc", "/learn/repolarization-safety");
    await navigateLegacy(page, "/tutorials?lesson=axis", "/learn/leads-vectors");
    await navigateLegacy(page, "/tutorials?lesson=retired-lesson", "/learn");
  });

  test("Interpret hands focused work to Rapid and preserves receipt context", async ({ page }) => {
    const target = await navigateLegacy(
      page,
      "/interpret?concept=atrial_fibrillation&returnTo=%2Freview",
      "/rapid",
    );
    expect(Object.fromEntries(target.searchParams)).toEqual({
      focus: "atrial_fibrillation",
      receiptConcept: "atrial_fibrillation",
      subskill: "synthesize",
      returnTo: "/review",
    });
  });

  test("Interpret preserves explicit canonical learning context", async ({ page }) => {
    const target = await navigateLegacy(
      page,
      "/interpret?focus=qtc_prolongation&receiptConcept=drug_safety&subskill=apply_in_context&returnTo=%2Flearn%2Frepolarization-safety%3Fscene%3D4",
      "/rapid",
    );
    expect(target.searchParams.get("focus")).toBe("qtc_prolongation");
    expect(target.searchParams.get("receiptConcept")).toBe("drug_safety");
    expect(target.searchParams.get("subskill")).toBe("apply_in_context");
    expect(target.searchParams.get("returnTo")).toBe("/learn/repolarization-safety?scene=4");
  });

  test("Concepts hands focused work to Training and preserves supported filters", async ({ page }) => {
    const target = await navigateLegacy(
      page,
      "/concepts?concept=qtc_prolongation&subskill=measure&returnTo=%2Freview",
      "/train",
    );
    expect(Object.fromEntries(target.searchParams)).toEqual({
      concept: "qtc_prolongation",
      subskill: "measure",
      returnTo: "/review",
    });
  });

  test("unsafe and legacy return targets are dropped to prevent redirect loops", async ({ page }) => {
    const interpretTarget = await navigateLegacy(
      page,
      "/interpret?concept=sinus_rhythm&returnTo=%2Finterpret%3Fconcept%3Dsinus_rhythm",
      "/rapid",
    );
    expect(interpretTarget.searchParams.has("returnTo")).toBe(false);

    const conceptsTarget = await navigateLegacy(
      page,
      "/concepts?focus=axis&subskill=synthesize&returnTo=https%3A%2F%2Fexample.com",
      "/train",
    );
    expect(conceptsTarget.searchParams.get("concept")).toBe("axis");
    expect(conceptsTarget.searchParams.has("subskill")).toBe(false);
    expect(conceptsTarget.searchParams.has("returnTo")).toBe(false);
  });

  test("a legacy navigation adds no extra history entry", async ({ page }) => {
    await page.goto("/dashboard");
    await page.goto("/tutorials?lesson=axis", { waitUntil: "domcontentloaded" });
    await expect(page).toHaveURL(/\/learn\/leads-vectors(?:[?#]|$)/);

    await page.goBack({ waitUntil: "domcontentloaded" });
    await expect(page).toHaveURL(/\/dashboard(?:[?#]|$)/);
  });
});
