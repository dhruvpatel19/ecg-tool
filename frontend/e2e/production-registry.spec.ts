import { expect, test } from "@playwright/test";
import { collectConsoleErrors, registerVerifiedE2ELearner } from "./helpers";
import {
  M01_FOUNDATIONS_MODULE,
  NATIVE_PRODUCTION_MODULES,
} from "../src/lib/learning/modules";
import { M01_SCENE_MANIFESTS } from "../src/lib/learning/modules/m01Foundations";
import {
  M01_CASE_ALLOCATION_SUMMARY,
  validateM01CaseAllocations,
} from "../src/lib/learning/modules/m01FoundationsCases";
import { gradeInteraction } from "../src/lib/learning/gradeInteraction";
import { MODULES } from "../src/lib/modules";

let userId = "";

test("Foundations is a complete 13-scene native curriculum with multimodal actions", () => {
  const expectedSceneIds = Array.from({ length: 13 }, (_, index) => `S${index}`);
  const sceneIds = M01_FOUNDATIONS_MODULE.scenes.map((scene) => scene.id);
  const interactionIds = M01_FOUNDATIONS_MODULE.scenes.flatMap((scene) => scene.interactions.map((interaction) => interaction.id));
  const kinds = new Set(M01_FOUNDATIONS_MODULE.scenes.flatMap((scene) => scene.interactions.map((interaction) => interaction.kind)));

  expect(sceneIds).toEqual(expectedSceneIds);
  expect(new Set(sceneIds).size).toBe(13);
  expect(new Set(M01_FOUNDATIONS_MODULE.scenes.map((scene) => scene.partId)).size).toBe(4);
  expect(new Set(interactionIds).size).toBe(interactionIds.length);
  expect(kinds.size).toBeGreaterThanOrEqual(10);
  expect([...kinds]).toEqual(expect.arrayContaining([
    "waveform_lab",
    "model_explore",
    "clinical_stage",
    "vector_lab",
    "numeric_entry",
    "pairing",
    "categorize",
    "free_response",
    "lead_select",
  ]));
  expect(M01_FOUNDATIONS_MODULE.scenes.flatMap((scene) => scene.interactions).filter((interaction) => interaction.kind === "waveform_lab").length).toBeGreaterThanOrEqual(8);
});

test("Foundations manifests are unique, topological, and preserve evidence ceilings", () => {
  const ids = M01_SCENE_MANIFESTS.map((manifest) => manifest.sceneId);
  expect(ids).toEqual(Array.from({ length: 13 }, (_, index) => `S${index}`));
  expect(new Set(ids).size).toBe(ids.length);

  for (const [index, manifest] of M01_SCENE_MANIFESTS.entries()) {
    const scene = M01_FOUNDATIONS_MODULE.scenes[index];
    expect(scene.id).toBe(manifest.sceneId);
    expect(scene.learningContract).toMatchObject({
      objectiveId: manifest.objectiveId,
      bloom: manifest.bloom,
      prerequisiteSceneIds: manifest.prerequisites,
      evidenceCeiling: manifest.evidenceCeiling,
      criticalRules: manifest.criticalRules,
    });
    expect(manifest.requiredActions.length).toBeGreaterThan(0);
    for (const prerequisite of manifest.prerequisites) {
      expect(ids.indexOf(prerequisite as (typeof ids)[number])).toBeLessThan(index);
    }
  }

  const capstone = M01_FOUNDATIONS_MODULE.scenes.at(-1)!;
  expect(capstone.id).toBe("S12");
  expect(capstone.learningContract?.evidenceCeiling).toBe("independent_immediate_candidate");
  expect(capstone.completionRule.requireIndependentAttempt).toBe(false);
  expect(capstone.caseContract).toMatchObject({
    allowedUses: ["worked_example"],
    fallback: "contrast_only",
  });
});

test("Foundations publishes only a consistent answer-free case-allocation summary", () => {
  expect(validateM01CaseAllocations()).toEqual({
    valid: true,
    duplicateRoles: [],
    count: 24,
    roleCount: 5,
  });
  expect(M01_CASE_ALLOCATION_SUMMARY.reduce((total, item) => total + item.count, 0)).toBe(24);
  expect(Object.fromEntries(M01_CASE_ALLOCATION_SUMMARY.map((item) => [item.role, item.count]))).toEqual({
    modeled: 2,
    guided: 3,
    immediate_integration: 2,
    equivalent_retry: 4,
    component_contrast: 13,
  });

  for (const allocation of M01_CASE_ALLOCATION_SUMMARY) {
    expect(Object.keys(allocation)).not.toContain("caseId");
    expect(Object.values(allocation.representationCounts).reduce<number>(
      (total, value) => total + (value ?? 0),
      0,
    )).toBe(allocation.count);
    if (allocation.representationCounts.median_morphology_composite) {
      expect(allocation.evidenceCeiling).toMatch(/^(guided|contrast_only)$/);
    }
    if (allocation.role === "component_contrast") {
      expect(allocation.evidenceCeiling).toBe("contrast_only");
      expect(allocation.unavailableEvidence).toEqual(expect.arrayContaining(["beat_to_beat_rhythm", "cross_panel_timing"]));
    }
  }

  for (const scene of M01_FOUNDATIONS_MODULE.scenes.filter((item) => item.caseContract)) {
    expect(scene.caseContract!.fallback).toBe("contrast_only");
    expect(scene.caseContract!.allowedUses.every((use) => ["mechanism", "worked_example"].includes(use))).toBe(true);
    expect(scene.caseContract!.forbiddenClaims.length).toBeGreaterThanOrEqual(3);
    expect(scene.caseContract!.casePoolSlot).toMatch(/^foundations:S(?:[5-9]|1[0-2]):(?:component|modeled|guided|integration)$/);
    if (scene.caseContract!.retryCasePoolSlot) {
      expect(scene.caseContract!.retryCasePoolSlot).toBe("foundations:equivalent-retry");
    }
  }
});

test("Foundations capstones reject positive diagnostic or treatment claims while preserving explicit boundaries", () => {
  const freeResponse = M01_FOUNDATIONS_MODULE.scenes
    .find((scene) => scene.id === "S11")!
    .interactions.find((interaction) => interaction.id === "m01-s11-synthesis");
  if (!freeResponse || freeResponse.kind !== "free_response") throw new Error("Missing S11 synthesis interaction");

  const bounded = "Calibration and quality are readable. Ventricular rate is regular near 75 bpm. Axis is in the usual frontal quadrant. PR and QRS intervals are measured; QT is not assessable because the T wave end is limited. ST-T recovery is described relative to the baseline. I cannot diagnose ischemia or recommend treatment from this teaching tracing.";
  const boundedGrade = gradeInteraction(freeResponse, bounded, 1);
  expect(boundedGrade.correct).toBe(true);
  expect(boundedGrade.misconceptions).not.toContain("unsupported_diagnosis_urgency_or_treatment");

  const unsafe = `${bounded} This is a STEMI; start heparin. Overall the tracing is normal.`;
  const unsafeGrade = gradeInteraction(freeResponse, unsafe, 1);
  expect(unsafeGrade.correct).toBe(false);
  expect(unsafeGrade.score).toBeLessThanOrEqual(0.5);
  expect(unsafeGrade.misconceptions).toContain("unsupported_diagnosis_urgency_or_treatment");

  const unsafeNegationTricks = [
    "There is no doubt this is a STEMI; do not delay treatment.",
    "This is not only ischemia; it is STEMI.",
  ];
  for (const claim of unsafeNegationTricks) {
    const grade = gradeInteraction(freeResponse, `${bounded} ${claim}`, 1);
    expect(grade.correct, claim).toBe(false);
    expect(grade.score, claim).toBeLessThanOrEqual(0.5);
  }

  const contractionBoundary = bounded.replace(
    "I cannot diagnose ischemia or recommend treatment",
    "I can't diagnose ischemia or recommend treatment",
  );
  expect(gradeInteraction(freeResponse, contractionBoundary, 1).correct).toBe(true);
});

test("Foundations regular-rate marching requires consecutive ventricular events", () => {
  const march = M01_FOUNDATIONS_MODULE.scenes
    .find((scene) => scene.id === "S4")!
    .interactions.find((interaction) => interaction.id === "m01-s4-regular-marks");
  if (!march || march.kind !== "waveform_lab") throw new Error("Missing S4 authored marching interaction");

  expect(gradeInteraction(march, [450, 1250, 2050, 2850], 1).correct).toBe(true);
  const alternating = gradeInteraction(march, [450, 2050, 3650, 5250], 1);
  expect(alternating.correct).toBe(false);
  expect(alternating.partial).toBe(true);
});

test("Foundations modeled, guided, and integration reads use distinct evidence packets", () => {
  const firstClinicalStage = (sceneId: "S10" | "S11" | "S12") => {
    const interaction = M01_FOUNDATIONS_MODULE.scenes
      .find((scene) => scene.id === sceneId)!
      .interactions.find((item) => item.kind === "clinical_stage");
    if (!interaction || interaction.kind !== "clinical_stage") throw new Error(`Missing ${sceneId} clinical stage`);
    return interaction;
  };
  const modeled = firstClinicalStage("S10");
  const guided = firstClinicalStage("S11");
  const integration = firstClinicalStage("S12");
  const packetText = (interaction: typeof modeled) => interaction.stages.map((stage) => stage.revealCopy).join("\n");

  expect(packetText(guided)).not.toBe(packetText(modeled));
  expect(packetText(integration)).not.toBe(packetText(modeled));
  expect(packetText(integration)).not.toBe(packetText(guided));
  expect(packetText(guided)).toContain("PR 220 ms");
  expect(packetText(integration)).toContain("QRS onset-to-final-offset is 136 ms");
});

test.describe("production curriculum registry", () => {
  test.beforeEach(async ({ page }) => {
    const account = await registerVerifiedE2ELearner(page, {
      prefix: "production_registry",
      displayName: "Registry Learner",
    });
    userId = account.user.userId;
    await page.route(`**/api/backend/learners/${userId}/foundations-native-migration`, (route) => route.fulfill({
      json: {
        learnerId: userId,
        migrationVersion: "foundations-native-v2",
        result: "not_needed",
        resumeSceneId: "S0",
        items: [],
        legacyPracticePreserved: false,
      },
    }));
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

  test("Foundations uses the native runtime after its owner-bound migration", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/learn/foundations");

    await expect(page.locator(".production-module")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("heading", { name: "A reliable ECG read, every time" })).toBeVisible();
    await expect(page.getByRole("progressbar", { name: "Lesson 1 of 13" })).toBeVisible();
    await expect(page.locator('iframe[title="Foundations of ECG Interpretation"]')).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Next checkpoint" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Previous scene" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Next scene" })).toHaveCount(0);
    await expect(page).toHaveURL(/\/learn\/foundations\?scene=S0$/);
    expect(errors).toEqual([]);
  });

  test("native modules use the validated runtime and canonical scene navigation", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/learn/leads-vectors?scene=M02.S1");

    await expect(page.locator(".production-module")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("heading", { name: "Why does one beat look different twelve times?" })).toBeVisible();
    await expect(page.getByRole("progressbar", { name: "Lesson 2 of 15" })).toBeVisible();
    await expect(page.locator('.production-module a[href="/learn"]').first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Previous scene" })).toBeEnabled();
    await expect(page.getByRole("button", { name: "Next scene" })).toBeVisible();

    await page.goto("/learn/integration-transfer");
    await expect(page.locator(".production-module")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("heading", { name: "Two routes through the same ECG" })).toBeVisible();
    await expect(page.getByRole("progressbar", { name: "Lesson 1 of 12" })).toBeVisible();
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

    const sceneCount = NATIVE_PRODUCTION_MODULES.reduce((total, module) => total + module.scenes.length, 0);
    await expect(page.getByText(`${sceneCount} interactive scenes`)).toBeVisible({ timeout: 30_000 });
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
