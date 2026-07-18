import { expect, test } from "@playwright/test";
import { collectConsoleErrors, registerVerifiedE2ELearner } from "./helpers";

test.beforeEach(async ({ page }) => {
  await registerVerifiedE2ELearner(page, { prefix: "adaptive" });
});

test("evidence-backed Guided remediation stays formative and preserves the independent check", async ({ page }) => {
  await page.route("**/api/backend/learning/resume", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        version: "learning-resume-v1",
        generatedAt: "2026-07-14T12:00:00Z",
        primary: null,
        additional: [],
      }),
    });
  });
  await page.route("**/api/backend/adaptive/plan", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        learnerId: "learner-guided-remediation",
        coachContext: { contextId: "apc1.mock", version: "adaptive-plan-coach-v1", expiresAt: "2099-01-01T00:00:00Z" },
        generatedAt: "2026-07-14T12:00:00Z",
        plannerKind: "verified_competency_scheduler",
        generativeTutorUsed: false,
        basis: {
          independentAttempts: 3,
          dueCompetencies: 0,
          overdueCompetencies: 0,
          highConfidenceMisses: 0,
          eligibleConcepts: 1,
          baselineNeeded: false,
        },
        primary: {
          objectiveId: "right_bundle_branch_block",
          label: "Right bundle branch block",
          domain: "conduction",
          caseConcept: "right_bundle_branch_block",
          eligibleDistinct: 25,
          subskill: "discriminate",
          state: "building",
          attempts: 4,
          independentAttempts: 3,
          independentMastery: 0.31,
          highConfidenceWrong: 0,
          isDue: false,
          dueState: "scheduled",
          overdueDays: 0,
          nextDueAt: null,
          stabilityDays: 1,
          distinctSuccessfulEcgs: 1,
          distinctModes: 1,
          lapses: 1,
          reason: "Recent independent checks support a concept repair.",
        },
        priorities: [],
        stages: [{
          order: 1,
          stageKind: "remediation",
          status: "current",
          mode: "train",
          title: "Build RBBB discrimination",
          purpose: "Complete the exact task, then clear an unannounced transfer ECG.",
          href: "/train?concept=right_bundle_branch_block&receiptConcept=right_bundle_branch_block&subskill=discriminate&suggestedLength=25&returnTo=%2Fhome%3Fpanel%3Dplan",
          suggestedLength: 25,
          receiptConcept: "right_bundle_branch_block",
          receiptSubskill: "discriminate",
          evidenceKind: "independent_transfer",
        }],
        guidedRemediation: {
          mode: "guided",
          title: "Rebuild Right bundle branch block before the next check",
          purpose: "Work through the authored paired-lead scene, then return for the blinded ECG check. This lesson is supportive practice and does not count as independent mastery evidence.",
          href: "/learn/ventricular-conduction?scene=m05-s2",
          moduleId: "ventricular-conduction",
          sceneId: "m05-s2",
          concept: "right_bundle_branch_block",
          evidenceKind: "formative_guided",
          updatesIndependentMastery: false,
          beforeStageOrder: 1,
          reason: "Unassisted performance is 31% after 3 checks, which supports a short concept repair.",
        },
        integration: null,
        clinicalApplication: null,
        integrationReadiness: { unlocked: false, reason: "Complete consolidation first." },
        explanation: "Evidence-backed repair followed by an independent check.",
      }),
    });
  });

  await page.goto("/home?panel=plan");
  const planPanel = page.locator("#home-panel-plan");
  const action = planPanel.getByTestId("recommended-action");
  await expect(action).toHaveText(/Start guided review/);
  await expect(action).toHaveAttribute("href", "/learn/ventricular-conduction?scene=m05-s2");
  await expect(planPanel.getByText("Guided review", { exact: true })).toBeVisible();
  await expect(planPanel.getByText(/Review Right bundle branch block with support/i)).toBeVisible();
  await expect(planPanel.getByText(/independent mastery evidence/i)).toHaveCount(0);

  const after = planPanel.getByText("What comes after this", { exact: true }).locator("xpath=ancestor::details");
  await after.locator("summary").click();
  await expect(after.locator('a[href*="receiptConcept=right_bundle_branch_block"]')).toBeVisible();

  await page.goto("/home");
  await expect(page.getByRole("heading", { name: "Review Right bundle branch block with guidance" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Start guided review/ })).toHaveAttribute(
    "href",
    "/learn/ventricular-conduction?scene=m05-s2",
  );
  await expect(page.getByText(/source-contracted|server records|receipt route/i)).toHaveCount(0);
});

test("study plan leads with one executable action while preserving the verified plan contract", async ({ page }) => {
  const errors = collectConsoleErrors(page);
  const planResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname.endsWith("/api/backend/adaptive/plan")
      && response.request().method() === "GET";
  });
  await page.goto("/review");

  await expect(page).toHaveURL(/\/home\?panel=plan$/);
  await expect(page.getByRole("tab", { name: "My plan" })).toHaveAttribute("aria-selected", "true");
  const recommendedAction = page.getByTestId("recommended-action");
  await expect(recommendedAction).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("#home-panel-plan").getByText("Your next step", { exact: true })).toBeVisible();
  await expect(page.locator("#home-panel-plan").getByRole("button", { name: "Plan with Luna" })).toBeVisible();
  const currentNav = page.getByRole("navigation", { name: "Primary navigation" }).getByRole("link", { name: "Dashboard" });
  await expect(currentNav).toHaveAttribute("href", "/home");
  await expect(currentNav).toHaveAttribute("aria-current", "page");
  await expect(page.getByText("Coming soon")).toHaveCount(0);
  await expect(page.getByRole("dialog", { name: "Plan with Luna" })).toHaveCount(0);
  await expect(page.getByRole("textbox", { name: "Message Luna" })).toHaveCount(0);

  // Secondary planning detail is available without competing with the action.
  const disclosures = page.locator("details");
  expect(await disclosures.count()).toBeGreaterThanOrEqual(1);
  for (const disclosure of await disclosures.all()) await expect(disclosure).not.toHaveAttribute("open", "");

  const learnerFacingText = await page.locator("main").innerText();
  expect(learnerFacingText).not.toMatch(/verified concept|receipt-grounded|server grader|independent transfer|eligible ECGs|review ceiling/i);

  const response = await planResponse;
  expect(response.ok(), `Adaptive plan request returned ${response.status()}.`).toBeTruthy();
  const plan = await response.json() as {
    plannerKind: string;
    generativeTutorUsed: boolean;
    coachContext: { contextId: string; version: string; expiresAt: string };
    basis: { baselineNeeded: boolean };
    stages: Array<{ mode: string; href: string; receiptConcept: string; receiptSubskill: string; evidenceKind: string }>;
    clinicalApplication: null | { href: string; concept: string; subskill: string; evidenceKind: string };
  };
  expect(plan.plannerKind).toBe("verified_competency_scheduler");
  expect(plan.generativeTutorUsed).toBe(false);
  expect(plan.coachContext.contextId).toMatch(/^apc1\./);
  expect(plan.coachContext.version).toBe("adaptive-plan-coach-v1");
  expect(Date.parse(plan.coachContext.expiresAt)).toBeGreaterThan(Date.now());
  expect(plan.stages.length).toBeGreaterThan(0);
  for (const stage of plan.stages) {
    expect(["train", "rapid"]).toContain(stage.mode);
    expect(stage.href).toContain(`receiptConcept=${encodeURIComponent(stage.receiptConcept)}`);
    expect(stage.href).toContain(`subskill=${encodeURIComponent(stage.receiptSubskill)}`);
    expect(stage.evidenceKind).toBe("independent_transfer");
  }
  if (plan.clinicalApplication) {
    expect(plan.clinicalApplication.href).toContain(`focus=${encodeURIComponent(plan.clinicalApplication.concept)}`);
    expect(plan.clinicalApplication.href).toContain("subskill=apply_in_context");
    expect(plan.clinicalApplication.subskill).toBe("apply_in_context");
    expect(plan.clinicalApplication.evidenceKind).toBe("formative_application");
    if (plan.basis.baselineNeeded) {
      await expect(page.getByText("Apply it in a patient case", { exact: true })).toHaveCount(0);
    } else {
      await expect(page.getByText("Apply it in a patient case", { exact: true })).toBeVisible();
    }
  }
  await expect(recommendedAction).toHaveAttribute("href", plan.stages[0].href);
  expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
});

test("loading state does not render an empty or invented recommendation", async ({ page }) => {
  let releasePlan!: () => void;
  const planGate = new Promise<void>((resolve) => { releasePlan = resolve; });
  await page.route("**/api/backend/adaptive/plan", async (route) => {
    await planGate;
    await route.continue();
  });

  await page.goto("/review");
  const loading = page.getByRole("status", { name: "Loading your next practice step" });
  await expect(loading).toBeVisible();
  await expect(loading).toContainText("Finding your best next step");
  await expect(page.getByTestId("recommended-action")).toHaveCount(0);
  await expect(page.getByText(/No eligible target|Establish your baseline/i)).toHaveCount(0);

  releasePlan();
  await expect(loading).toHaveCount(0, { timeout: 30_000 });
  await expect(page.getByTestId("recommended-action")).toBeVisible();
});

test("Luna sends only the opaque plan context and traps keyboard focus", async ({ page }) => {
  let tutorBody: Record<string, unknown> | null = null;
  await page.route("**/api/backend/tutor/message", async (route) => {
    tutorBody = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        threadId: "th_adaptive_e2e",
        tutorMessage: "This recommendation comes from your current saved practice history.",
        feedback: "",
        viewerActions: [],
        objectiveUpdates: [],
        misconceptions: [],
        uncertaintyWarnings: [],
        citedEvidence: [],
        onLessonTopic: true,
      }),
    });
  });

  await page.goto("/review");
  await expect(page.getByTestId("recommended-action")).toBeVisible({ timeout: 30_000 });
  const coachTrigger = page.locator("#home-panel-plan").getByRole("button", { name: "Plan with Luna" });
  await coachTrigger.focus();
  await page.keyboard.press("Enter");

  const dialog = page.getByRole("dialog", { name: "Plan with Luna" });
  const close = page.getByRole("button", { name: "Close Luna" });
  await expect(dialog).toBeVisible();
  await expect(close).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);

  const composer = page.getByRole("textbox", { name: "Message Luna" });
  await composer.fill("Why is this first?");
  await page.getByRole("button", { name: "Send" }).click();
  await expect.poll(() => tutorBody).not.toBeNull();

  const body = tutorBody as unknown as {
    adaptiveContext?: { contextId?: string; version?: string; expiresAt?: string };
    viewerState?: Record<string, unknown>;
    lessonId?: string;
  };
  expect(body.adaptiveContext?.contextId).toMatch(/^apc1\./);
  expect(body.adaptiveContext?.version).toBe("adaptive-plan-coach-v1");
  expect(body.lessonId).toBe("adaptive-mastery-plan");
  expect(body.viewerState).toEqual({ activity: "adaptive_mastery_plan", surface: "learning-home" });
  expect(body.viewerState).not.toHaveProperty("primary");
  expect(body.viewerState).not.toHaveProperty("priorities");
  expect(body.viewerState).not.toHaveProperty("prescribedStages");
  expect(body.viewerState).not.toHaveProperty("explanation");

  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(coachTrigger).toBeFocused();
});

test("plan disclosures work from the keyboard and the mobile action stays in view without overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/review");
  const action = page.getByTestId("recommended-action");
  await expect(action).toBeVisible({ timeout: 30_000 });

  // The learner name and translated copy can legitimately make the plan card
  // start below the first mobile viewport. Verify the action after bringing it
  // into view instead of coupling the layout contract to one generated name.
  await action.scrollIntoViewIfNeeded();
  const actionBox = await action.boundingBox();
  const viewportHeight = await page.evaluate(() => window.innerHeight);
  expect(actionBox).not.toBeNull();
  expect(actionBox!.y).toBeGreaterThanOrEqual(0);
  // Allow one device-pixel of Chromium subpixel rounding at the viewport edge.
  expect(actionBox!.y + actionBox!.height).toBeLessThanOrEqual(viewportHeight + 1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);

  const firstDisclosure = page.locator("#home-panel-plan details").first();
  const firstSummary = firstDisclosure.locator("summary");
  await firstSummary.focus();
  await page.keyboard.press("Enter");
  await expect(firstDisclosure).toHaveAttribute("open", "");
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);

  const coachTrigger = page.locator("#home-panel-plan").getByRole("button", { name: "Plan with Luna" });
  await coachTrigger.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Plan with Luna" });
  await expect(dialog).toBeVisible();
  const viewportWidth = await page.evaluate(() => window.innerWidth);
  // Visibility can be reported while the short slide-in transition is still
  // translating the drawer beyond the viewport edge. Assert its settled box.
  await expect.poll(async () => {
    const box = await dialog.boundingBox();
    return box ? box.x + box.width : Number.POSITIVE_INFINITY;
  }).toBeLessThanOrEqual(viewportWidth + 1);
  const dialogBox = await dialog.boundingBox();
  expect(dialogBox).not.toBeNull();
  expect(dialogBox!.x).toBeGreaterThanOrEqual(0);
  expect(dialogBox!.x + dialogBox!.width).toBeLessThanOrEqual(viewportWidth + 1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
});
