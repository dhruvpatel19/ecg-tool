import { expect, test } from "@playwright/test";
import { collectConsoleErrors, registerVerifiedE2ELearner } from "./helpers";
import { NATIVE_PRODUCTION_MODULES } from "../src/lib/learning/modules";
import { buildModuleTeachingLesson, moduleSceneHasTeaching, resolveTutorTemplate } from "../src/lib/learning/modulePedagogy";

const LATER_MODULES = NATIVE_PRODUCTION_MODULES.filter((module) => module.id !== "foundations");

test.describe("native module teaching studios", () => {
  test.beforeEach(async ({ page }) => {
    await registerVerifiedE2ELearner(page, { prefix: "module_teaching" });
  });

  test("every later module exposes an authored visual model before its ECG task", async ({ page }, testInfo) => {
    test.slow();
    const errors = collectConsoleErrors(page);

    for (const module of LATER_MODULES) {
      const scene = module.scenes.find((candidate) => moduleSceneHasTeaching(module.id, candidate));
      expect(scene, `${module.id} needs at least one teaching scene`).toBeDefined();
      await page.goto(`/learn/${module.id}?scene=${encodeURIComponent(scene!.id)}`);

      await expect(page.locator("#production-scene-title")).toHaveText(scene!.copy.title, { timeout: 30_000 });
      await expect(page.getByText("The module owns", { exact: true })).toBeVisible();
      await expect(page.getByText("Luna adds", { exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: "Pause motion" })).toBeVisible();
      await expect(page.getByText("Pause and predict", { exact: true })).toBeVisible();
      await expect(page.locator("#production-active-interaction")).toHaveCount(0);
      await expect(page.locator('[data-guided-region="ecg"]')).toBeVisible();

      const lesson = buildModuleTeachingLesson(module, scene!);
      const ideaButtons = page.getByRole("navigation", { name: "Lesson ideas" }).getByRole("button");
      await expect(ideaButtons).toHaveCount(lesson.beats.length);
      if (module.id === "leads-vectors") {
        await page.screenshot({ path: testInfo.outputPath("module-teaching-desktop.png"), fullPage: true });
      }
      for (let index = 0; index < lesson.beats.length; index += 1) {
        await ideaButtons.nth(index).click();
      }
      await page.getByRole("button", { name: "Start the ECG task" }).click();
      await expect(page.getByText("Model explored", { exact: true })).toBeVisible();
      await expect(page.locator("#production-active-interaction")).toHaveCount(1);
    }

    expect(errors).toEqual([]);
  });

  test("the upgraded studio remains readable without page overflow on a phone", async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/learn/ischemia-infarction?scene=m09-s1");
    await expect(page.getByText("The module owns", { exact: true })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("button", { name: "Pause motion" })).toBeVisible();
    const [teachingBox, ecgBox] = await Promise.all([
      page.getByRole("region", { name: "Build the territory-evidence map" }).boundingBox(),
      page.locator('[data-guided-region="ecg"]').boundingBox(),
    ]);
    expect(teachingBox).not.toBeNull();
    expect(ecgBox).not.toBeNull();
    expect(ecgBox!.y).toBeLessThan(teachingBox!.y);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    await page.screenshot({ path: testInfo.outputPath("module-teaching-mobile.png"), fullPage: true });
  });

  test("Luna replaces the lesson rail without covering the ECG", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/learn/ventricular-conduction?scene=m05-s1");
    const ecg = page.locator('[data-guided-region="ecg"]');
    const rail = page.getByRole("complementary", { name: "Authored model beside the ECG" });
    await expect(ecg).toBeVisible({ timeout: 30_000 });
    const launcher = rail.getByRole("button", { name: /Ask Luna about this step/i });
    await launcher.click();
    const tutor = rail.getByRole("dialog", { name: /Luna tutor/i });
    await expect(tutor).toBeVisible();
    await expect(ecg).toBeVisible();
    await expect(page.locator(".learning-tutor-backdrop")).toHaveCount(0);
    await expect(tutor.getByRole("button", { name: "Return" })).toBeFocused();
    await tutor.getByRole("button", { name: "Return" }).click();
    await expect(launcher).toBeFocused();
    await expect(rail.getByRole("navigation", { name: "Lesson ideas" })).toBeVisible();
  });

  test("Foundations adds motion, prediction, and an explicit authored-versus-AI boundary", async ({ page }, testInfo) => {
    await page.goto("/learn/foundations?scene=S1");
    await expect(page.getByRole("heading", { name: "Build the idea before you use it" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("button", { name: "Pause motion" })).toBeVisible();
    await expect(page.getByText("The module owns", { exact: true })).toBeVisible();
    await expect(page.getByText("Luna adds", { exact: true })).toBeVisible();
    await expect(page.getByText("Pause and predict", { exact: true })).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath("foundations-teaching-desktop.png"), fullPage: true });
  });
});

test("all native scenes expose objective, Bloom, prerequisite, evidence-ceiling, and claim-limit contracts", () => {
  for (const module of NATIVE_PRODUCTION_MODULES) {
    for (const [index, scene] of module.scenes.entries()) {
      expect(scene.learningContract, `${module.id}/${scene.id}`).toBeDefined();
      expect(scene.learningContract!.objectiveId.length).toBeGreaterThan(0);
      expect(scene.learningContract!.bloom.length).toBeGreaterThan(0);
      expect(["none", "guided", "independent_immediate_candidate"]).toContain(scene.learningContract!.evidenceCeiling);
      if (moduleSceneHasTeaching(module.id, scene)) {
        expect(scene.learningContract!.evidenceCeiling, `${module.id}/${scene.id} teaches immediately before practice`).toBe("guided");
      }
      if (module.id !== "foundations" && index > 0) {
        expect(scene.learningContract!.prerequisiteSceneIds).toContain(module.scenes[index - 1]!.id);
      }
      if (module.id !== "foundations" && scene.caseContract?.forbiddenClaims.length) {
        expect(scene.learningContract!.criticalRules).toEqual(scene.caseContract.forbiddenClaims);
      }
      for (const template of [scene.copy.openingTutorMessage, scene.tutor.tangentBridge, scene.tutor.returnPrompt]) {
        expect(resolveTutorTemplate(template, { actionNumber: 1, leads: ["II"] }), `${module.id}/${scene.id}`).not.toMatch(/\[[^\]]+\]/);
      }
    }
  }
});
