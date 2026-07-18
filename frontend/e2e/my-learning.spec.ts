import { expect, test, type Locator, type Page } from "@playwright/test";
import { collectConsoleErrors } from "./helpers";

const calendarTodayFixture = (() => {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
})();

const calendarProjectionFixture = {
  timeZone: "America/New_York",
  today: calendarTodayFixture,
  reviewDays: [{ date: calendarTodayFixture, total: 1 }],
};

const profileFixture = {
  learnerId: "demo",
  displayName: "Demo Learner",
  attemptCount: 4,
  mastery: [],
  subskillMastery: [],
  recentAttempts: [],
  misconceptions: [],
  weakObjectives: [],
};

const preferencesFixture = {
  trainingStage: "not_set",
  primaryGoal: "build_fundamentals",
  defaultSessionLength: 10,
  rapidPace: "untimed",
  guidanceLevel: "balanced",
  reduceMotion: false,
  largeControls: false,
  updatedAt: null,
};

const competencyCellFixture = {
  subskill: "recognize",
  state: "developing",
  formativeScore: 0.8,
  independentMastery: 0.72,
  attempts: 4,
  independentAttempts: 3,
  highConfidenceWrong: 1,
  lastPracticedAt: "2026-07-13T12:00:00Z",
  lastIndependentAt: "2026-07-13T12:00:00Z",
  lastIndependentCorrect: true,
  nextDueAt: "2026-07-14T12:00:00Z",
  dueState: "due",
  isDue: true,
  overdueDays: 0,
  daysUntilDue: 0,
  stabilityDays: 3,
  lapses: 0,
  spacedRetrievals: 1,
  distinctEligibleEcgs: 20,
  distinctSuccessfulEcgs: 2,
  distinctModes: 1,
  distinctMorphologies: 2,
  independentEvidenceAvailable: true,
  independentReceipt: {
    mode: "rapid",
    caseConcept: "sinus_rhythm",
    receiptConcept: "sinus_rhythm",
    subskill: "recognize",
  },
  evidenceUncertainty: null,
};

const competenciesFixture = {
  learnerId: "demo",
  registryVersion: "my-learning-test",
  calendarProjection: calendarProjectionFixture,
  objectives: [{
    objectiveId: "sinus_rhythm",
    label: "Sinus rhythm",
    domain: "rhythm",
    caseConcepts: ["sinus_rhythm"],
    evidenceCeiling: "eligible_real_case",
    subskills: [competencyCellFixture],
  }],
};

const runnablePlanFixture = {
  learnerId: "demo",
  coachContext: {
    contextId: "apc1.my-learning-test",
    version: "adaptive-plan-coach-v1",
    expiresAt: "2099-01-01T00:00:00Z",
  },
  generatedAt: "2026-07-14T12:00:00Z",
  plannerKind: "verified_competency_scheduler",
  generativeTutorUsed: false,
  basis: {
    independentCompetencyObservations: 3,
    independentAttempts: 3,
    independentAttemptUnit: "competency_observation",
    dueCompetencies: 1,
    overdueCompetencies: 0,
    highConfidenceMisses: 1,
    eligibleConcepts: 20,
    baselineNeeded: false,
  },
  primary: {
    objectiveId: "sinus_rhythm",
    label: "Sinus rhythm",
    domain: "rhythm",
    caseConcept: "sinus_rhythm",
    eligibleDistinct: 20,
    subskill: "recognize",
    state: "developing",
    attempts: 4,
    independentAttempts: 3,
    independentMastery: 0.72,
    highConfidenceWrong: 1,
    isDue: true,
    dueState: "due",
    overdueDays: 0,
    nextDueAt: "2026-07-14T12:00:00Z",
    stabilityDays: 3,
    distinctSuccessfulEcgs: 2,
    distinctModes: 1,
    lapses: 0,
    reason: "A fresh retrieval check is due.",
  },
  priorities: [],
  stages: [{
    order: 1,
    mode: "rapid",
    title: "Recheck sinus rhythm",
    purpose: "Identify sinus rhythm on a fresh real ECG.",
    href: "/rapid?focus=sinus_rhythm&subskill=recognize&returnTo=%2Fhome%3Fpanel%3Dplan",
    suggestedLength: 5,
    receiptConcept: "sinus_rhythm",
    receiptSubskill: "recognize",
    evidenceKind: "independent_transfer",
  }],
  guidedRemediation: null,
  integration: null,
  clinicalApplication: null,
  explanation: "The verified scheduler selected a due retrieval check.",
};

const baselinePlanFixture = {
  ...runnablePlanFixture,
  basis: {
    independentCompetencyObservations: 0,
    independentAttempts: 0,
    independentAttemptUnit: "competency_observation",
    dueCompetencies: 0,
    overdueCompetencies: 0,
    highConfidenceMisses: 0,
    eligibleConcepts: 0,
    baselineNeeded: true,
  },
  primary: null,
  // The planner may offer an executable cold-start route before it has any
  // learner evidence. The presenter must still label the action honestly.
  stages: runnablePlanFixture.stages,
  explanation: "A starting check is needed before a personalized plan can be scheduled.",
};

const emptyResumeFixture = {
  version: "learning-resume-v1",
  generatedAt: "2026-07-15T12:00:00Z",
  primary: null,
  additional: [],
};

const emptyActivityFixture = {
  version: "learning-activity-v1",
  items: [],
  nextCursor: null,
  hasMore: false,
};

const emptySessionsFixture = {
  version: "learning-sessions-v1",
  hasMore: false,
  nextOffset: null,
  totalSavedItems: 0,
  items: [],
};

async function routeCanonicalLearning(page: Page) {
  await page.route("**/api/backend/auth/me", (route) => route.fulfill({
    json: {
      authenticated: true,
      user: {
        userId: "u_my_learning",
        username: "demo",
        displayName: "Demo Learner",
        accountStatus: "verified",
        emailVerified: true,
      },
    },
  }));
  await page.route("**/api/backend/learners/demo", (route) => route.fulfill({ json: profileFixture }));
  await page.route("**/api/backend/learners/demo/competencies", (route) => route.fulfill({ json: competenciesFixture }));
  await page.route("**/api/backend/adaptive/plan", (route) => route.fulfill({ json: runnablePlanFixture }));
  await page.route("**/api/backend/learning/resume", (route) => route.fulfill({ json: emptyResumeFixture }));
  await page.route("**/api/backend/learning/activity?*", (route) => route.fulfill({ json: emptyActivityFixture }));
  await page.route("**/api/backend/learning/sessions?*", (route) => route.fulfill({ json: emptySessionsFixture }));
  await page.route("**/api/backend/learning/preferences", (route) => route.fulfill({ json: preferencesFixture }));
  await page.route("**/api/backend/auth/sessions", (route) => route.fulfill({ json: { sessions: [] } }));
  await page.route("**/api/backend/auth/guest-progress", (route) => route.fulfill({
    json: { hasProgress: false, claimable: false },
  }));
}

async function expectTouchTarget(locator: Locator) {
  await expect(locator).toBeVisible();
  const box = await locator.boundingBox();
  expect(box, "Expected a rendered touch target").not.toBeNull();
  expect(box!.height).toBeGreaterThanOrEqual(44);
}

async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
}

function competencyCell(
  state: "unseen" | "acquiring" | "developing" | "consolidating" | "durable",
  overrides: Record<string, unknown> = {},
) {
  return {
    subskill: "recognize",
    state,
    formativeScore: 0,
    independentMastery: 0,
    attempts: 0,
    independentAttempts: 0,
    highConfidenceWrong: 0,
    lastPracticedAt: null,
    lastIndependentAt: null,
    lastIndependentCorrect: null,
    nextDueAt: null,
    dueState: state === "unseen" ? "unseen" : "scheduled",
    isDue: false,
    overdueDays: 0,
    daysUntilDue: null,
    stabilityDays: 0,
    lapses: 0,
    spacedRetrievals: 0,
    distinctEligibleEcgs: 20,
    distinctSuccessfulEcgs: 0,
    distinctModes: 0,
    distinctMorphologies: 0,
    independentEvidenceAvailable: true,
    independentReceipt: {
      mode: "rapid",
      caseConcept: "sinus_rhythm",
      receiptConcept: "sinus_rhythm",
      subskill: "recognize",
    },
    evidenceUncertainty: null,
    ...overrides,
  };
}

const competencyMapFixture = {
  learnerId: "demo",
  registryVersion: "competency-panel-test",
  calendarProjection: calendarProjectionFixture,
  objectives: [
    {
      objectiveId: "unseen_skill",
      label: "Unseen skill",
      domain: "rhythm",
      caseConcepts: ["axis_normal"],
      evidenceCeiling: "eligible_real_case",
      subskills: [competencyCell("unseen", {
        independentReceipt: {
          mode: "rapid",
          caseConcept: "axis_normal",
          receiptConcept: "axis_normal",
          subskill: "recognize",
        },
      })],
    },
    {
      objectiveId: "started_but_weak",
      label: "Started but weak",
      domain: "rhythm",
      caseConcepts: ["atrial_fibrillation"],
      evidenceCeiling: "eligible_real_case",
      subskills: [competencyCell("acquiring", {
        subskill: "discriminate",
        attempts: 2,
        independentAttempts: 1,
        independentMastery: 0.2,
        lastPracticedAt: "2026-07-12T12:00:00Z",
        lastIndependentAt: "2026-07-12T12:00:00Z",
        independentReceipt: {
          mode: "train",
          caseConcept: "atrial_fibrillation",
          receiptConcept: "atrial_fibrillation",
          subskill: "discriminate",
        },
      })],
    },
    {
      objectiveId: "due_skill",
      label: "Due skill",
      domain: "rhythm",
      caseConcepts: ["sinus_rhythm"],
      evidenceCeiling: "eligible_real_case",
      subskills: [competencyCell("developing", {
        attempts: 3,
        independentAttempts: 2,
        independentMastery: 0.45,
        isDue: true,
        dueState: "due",
        nextDueAt: "2026-07-14T12:00:00Z",
        lastPracticedAt: "2026-07-13T12:00:00Z",
        lastIndependentAt: "2026-07-13T12:00:00Z",
      }), competencyCell("durable", {
        subskill: "calibrate_confidence",
        attempts: 4,
        independentAttempts: 3,
        independentMastery: 0.85,
        lastPracticedAt: "2026-07-13T12:00:00Z",
        lastIndependentAt: "2026-07-13T12:00:00Z",
      })],
    },
    {
      objectiveId: "formative_composite",
      label: "Formative composite",
      domain: "integration",
      caseConcepts: ["normal_ecg"],
      evidenceCeiling: "eligible_real_case",
      subskills: [competencyCell("unseen", {
        independentEvidenceAvailable: false,
        independentReceipt: null,
        evidenceUncertainty: "No independently scored route is implemented for this composite objective.",
      })],
    },
  ],
};

function activityFixture(index: number) {
  const mode = index % 4 === 0
    ? "guided"
    : index % 4 === 1
      ? "training"
      : index % 4 === 2
        ? "rapid"
        : "clinical";
  const evidence = index === 22
    ? "legacy_unverified"
    : index % 4 === 0 || index % 4 === 3
      ? "formative"
      : "independent";
  const objectiveId = index % 4 === 0 ? "axis_normal" : "right_bundle_branch_block";
  const subskill = index % 4 === 0 ? "localize" : "discriminate";
  return {
    id: `evt_${String(index).padStart(3, "0")}`,
    mode,
    kind: index % 4 === 0 ? "guided_task" : "ecg_attempt",
    occurredAt: `2026-07-${String(13 - Math.floor(index / 4)).padStart(2, "0")}T12:00:00Z`,
    objectiveId,
    subskill,
    testedCompetencies: index === 2
      ? [
          { objectiveId: "sinus_rhythm", subskill: "recognize", evidence: "independent" },
          { objectiveId: "axis_normal", subskill: "recognize", evidence: "independent" },
          { objectiveId: "nonspecific_st_t_change", subskill: "recognize", evidence: "independent" },
          { objectiveId: "sinus_rhythm", subskill: "recognize", evidence: "independent" },
        ]
      : index === 22
        ? []
        : [{
            objectiveId,
            subskill,
            evidence: evidence === "independent" ? "independent" : "formative",
          }],
    score: index === 22 ? null : index % 3 === 0 ? 0.5 : 0.9,
    confidence: 4,
    assistance: index % 4 === 0 ? "assisted" : "unassisted",
    evidence,
    reviewRecommended: index !== 22 && index % 3 === 0,
  };
}

test.describe("canonical learning dashboard details", () => {
  test.beforeEach(async ({ page }) => {
    await routeCanonicalLearning(page);
  });

  test("redirects every legacy learning destination to its canonical surface", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    const redirects = [
      ["/review", "/home?panel=plan"],
      ["/profile", "/home"],
      ["/profile?tab=overview", "/home"],
      ["/profile?tab=plan", "/home?panel=plan"],
      ["/profile?tab=competencies", "/home?panel=competencies"],
      ["/profile?tab=activity", "/home?panel=activity"],
      ["/profile?tab=preferences", "/account#learning-preferences"],
    ] as const;

    for (const [legacy, canonical] of redirects) {
      await page.goto(legacy);
      await expect.poll(() => {
        const url = new URL(page.url());
        return `${url.pathname}${url.search}${url.hash}`;
      }).toBe(canonical);
    }

    const navigation = page.getByRole("navigation", { name: "Primary navigation" });
    await expect(navigation.getByRole("link", { name: "Dashboard" })).toHaveAttribute("href", "/home");
    await expect(navigation.getByRole("link", { name: "My learning" })).toHaveCount(0);
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("supports deep-linked panels, keyboard movement, and browser history", async ({ page }) => {
    await page.goto("/home?panel=activity");
    const tabs = page.getByRole("tablist", { name: "Learning dashboard sections" }).getByRole("tab");
    await expect(tabs).toHaveText(["Home", "History", "Progress", "Schedule", "My plan"]);

    const activityTab = page.getByRole("tab", { name: "History" });
    await expect(activityTab).toHaveAttribute("aria-selected", "true");
    await activityTab.focus();
    await page.keyboard.press("ArrowRight");
    await expect(page).toHaveURL(/\/home\?panel=competencies$/);
    const competenciesTab = page.getByRole("tab", { name: "Progress" });
    await expect(competenciesTab).toBeFocused();

    await page.keyboard.press("End");
    await expect(page).toHaveURL(/\/home\?panel=plan$/);
    const planTab = page.getByRole("tab", { name: "My plan" });
    await expect(planTab).toBeFocused();

    await page.keyboard.press("Home");
    await expect(page).toHaveURL(/\/home$/);
    await expect(page.getByRole("tab", { name: "Home" })).toBeFocused();

    await page.goBack();
    await expect(page).toHaveURL(/\/home\?panel=plan$/);
    await expect(planTab).toHaveAttribute("aria-selected", "true");
    await page.goBack();
    await expect(page).toHaveURL(/\/home\?panel=competencies$/);
    await expect(competenciesTab).toHaveAttribute("aria-selected", "true");
    await page.goForward();
    await expect(page).toHaveURL(/\/home\?panel=plan$/);
  });

  test("defers hidden activity and saved-session reads until the learner asks for them", async ({ page }) => {
    let activityRequests = 0;
    let sessionRequests = 0;
    let savedSessionRequests = 0;
    await page.unroute("**/api/backend/learning/activity?*");
    await page.route("**/api/backend/learning/activity?*", (route) => {
      activityRequests += 1;
      return route.fulfill({ json: emptyActivityFixture });
    });
    await page.unroute("**/api/backend/learning/sessions?*");
    await page.route("**/api/backend/learning/sessions?*", (route) => {
      const savedOnly = new URL(route.request().url()).searchParams.get("savedOnly") === "true";
      if (savedOnly) savedSessionRequests += 1;
      else sessionRequests += 1;
      return route.fulfill({ json: emptySessionsFixture });
    });

    await page.goto("/home");
    await expect(page.getByRole("heading", { name: runnablePlanFixture.stages[0].title })).toBeVisible();
    expect(activityRequests).toBe(0);
    expect(savedSessionRequests).toBe(0);
    // React's development Strict Mode may replay the effect once; production
    // performs one request. Neither path may preload the two hidden resources.
    expect(sessionRequests).toBeGreaterThan(0);
    expect(sessionRequests).toBeLessThanOrEqual(2);

    await page.getByRole("tab", { name: "History" }).click();
    await expect.poll(() => activityRequests).toBeGreaterThan(0);
    expect(activityRequests).toBeLessThanOrEqual(2);
    expect(savedSessionRequests).toBe(0);

    await page.getByRole("button", { name: "Saved items (0)" }).click();
    await expect.poll(() => savedSessionRequests).toBeGreaterThan(0);
    expect(savedSessionRequests).toBeLessThanOrEqual(2);
  });

  test("labels a cold-start route honestly even when the planner emits a runnable stage", async ({ page }) => {
    await page.unroute("**/api/backend/adaptive/plan");
    await page.route("**/api/backend/adaptive/plan", (route) => route.fulfill({ json: baselinePlanFixture }));
    await page.unroute("**/api/backend/learners/demo/competencies");
    await page.route("**/api/backend/learners/demo/competencies", (route) => route.fulfill({
      json: { learnerId: "demo", registryVersion: "baseline-test", calendarProjection: { ...calendarProjectionFixture, reviewDays: [] }, objectives: [] },
    }));

    await page.goto("/home");
    const overview = page.getByRole("tabpanel", { name: "Home" });
    await expect(overview.getByText("First step", { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Start 5-ECG check" })).toHaveAttribute(
      "href",
      baselinePlanFixture.stages[0].href,
    );
    await expect(page.getByText("Practice option", { exact: true })).toHaveCount(0);

    await page.getByRole("tab", { name: "My plan" }).click();
    const planPanel = page.getByRole("tabpanel", { name: "My plan" });
    await expect(planPanel.getByTestId("recommended-action")).toHaveText(/Start 5-ECG check/);
    await expect(planPanel.getByTestId("recommended-action")).toHaveAttribute(
      "href",
      baselinePlanFixture.stages[0].href,
    );
    await planPanel.locator("details").filter({ hasText: "Why this next?" }).first().locator("summary").click();
    await expect(planPanel.getByText(/0 skill checks/)).toBeVisible();
  });

  test("labels planner failure as general practice while keeping loaded evidence usable", async ({ page }) => {
    await page.unroute("**/api/backend/adaptive/plan");
    await page.route("**/api/backend/adaptive/plan", (route) => route.fulfill({
      status: 503,
      body: "planner unavailable",
    }));

    await page.goto("/home");
    await expect(page.getByText("Your tailored next step is temporarily unavailable.", { exact: false })).toBeVisible();
    await expect(page.getByText("Practice option", { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Start general practice" })).toHaveAttribute(
      "href",
      "/rapid?pace=untimed&suggestedLength=5&returnTo=%2Fhome",
    );

    const summary = page.getByLabel("Learning progress summary");
    await expect(summary.locator("article").nth(0).getByText("1", { exact: true })).toBeVisible();
    await expect(summary.locator("article").nth(1).getByText("0", { exact: true })).toBeVisible();
    await expect(summary.locator("article").nth(2).getByText("1", { exact: true })).toBeVisible();
    const recent = page.getByRole("heading", { name: "Your latest practice" }).locator("xpath=ancestor::section");
    await expect(recent.getByText("No activity yet.", { exact: true })).toBeVisible();

    await page.getByRole("tab", { name: "My plan" }).click();
    await expect(page.getByRole("tabpanel", { name: "My plan" }).getByRole("alert")).toContainText("Nothing was changed.");
  });

  test("does not infer zero or not-started evidence from a failed competency request", async ({ page }) => {
    await page.unroute("**/api/backend/learners/demo/competencies");
    await page.route("**/api/backend/learners/demo/competencies", (route) => route.fulfill({
      status: 503,
      body: "competencies unavailable",
    }));

    await page.goto("/home");
    const warning = page.getByRole("status").filter({ hasText: "Everything that did load remains available." });
    await expect(warning).toContainText("Your progress details are temporarily unavailable.");
    const summary = page.getByLabel("Learning progress summary");
    await expect(summary.locator("article strong")).toHaveText(["—", "—", "—"]);

    await page.getByRole("tab", { name: "Progress" }).click();
    const panel = page.getByRole("tabpanel", { name: "Progress" });
    await expect(panel.getByText(
      "Nothing below will be guessed while this information is unavailable.",
      { exact: true },
    )).toBeVisible();
    await expect(panel.getByRole("button", { name: /Not started/ })).toHaveCount(0);
    const retry = panel.getByRole("button", { name: "Try again" });
    await expectTouchTarget(retry);

    await page.unroute("**/api/backend/learners/demo/competencies");
    await page.route("**/api/backend/learners/demo/competencies", (route) => route.fulfill({
      json: competenciesFixture,
    }));
    await retry.click();
    await expect(panel.getByRole("heading", { name: "Your progress" })).toBeVisible();
    await expect(panel.getByRole("button", { name: /Not started/ })).toBeVisible();
  });

  test("sorts, searches, expands, and routes competency evidence without overstating eligibility", async ({ page }) => {
    await page.unroute("**/api/backend/learners/demo/competencies");
    await page.route("**/api/backend/learners/demo/competencies", (route) => route.fulfill({ json: competencyMapFixture }));

    await page.goto("/home?panel=competencies");
    const panel = page.getByRole("tabpanel", { name: "Progress" });
    await expect(panel.getByRole("heading", { name: "See what's strong and what to practice next" })).toBeVisible();

    const attention = panel
      .getByRole("heading", { name: "Practice next" })
      .locator("xpath=ancestor::section[1]");
    await expect(attention.locator("ol > li").nth(0)).toContainText("Due skill");
    await expect(attention.locator("ol > li").nth(1)).toContainText("Started but weak");

    const map = panel
      .getByRole("heading", { name: "Browse all skills" })
      .locator("xpath=ancestor::section[1]");
    const rhythmDomain = map.locator("details").filter({
      has: page.getByText("Rhythm", { exact: true }),
    }).first();
    await rhythmDomain.locator(":scope > summary").click();

    const dueObjective = rhythmDomain.locator("details").filter({
      has: page.getByText("Due skill", { exact: true }),
    }).first();
    const startedObjective = rhythmDomain.locator("details").filter({
      has: page.getByText("Started but weak", { exact: true }),
    }).first();
    const unseenObjective = rhythmDomain.locator("details").filter({
      has: page.getByText("Unseen skill", { exact: true }),
    }).first();
    const dueY = (await dueObjective.locator(":scope > summary").boundingBox())?.y ?? Number.POSITIVE_INFINITY;
    const startedY = (await startedObjective.locator(":scope > summary").boundingBox())?.y ?? Number.POSITIVE_INFINITY;
    const unseenY = (await unseenObjective.locator(":scope > summary").boundingBox())?.y ?? Number.POSITIVE_INFINITY;
    expect(dueY).toBeLessThan(startedY);
    expect(startedY).toBeLessThan(unseenY);
    await expect(dueObjective.locator(":scope > summary > span").first()).toHaveAttribute("data-state", "mixed");
    await expect(unseenObjective.locator(":scope > summary")).toContainText("Scored check available");

    await startedObjective.locator(":scope > summary").click();
    await expect(startedObjective.getByText(/Getting started after 1 scored ECG check across 20 different ECGs/)).toBeVisible();
    const evidenceDetails = startedObjective.locator("details").filter({
      has: page.getByText("Practice details", { exact: true }),
    }).first();
    await evidenceDetails.locator(":scope > summary").click();
    await expect(evidenceDetails.getByRole("list", { name: /Started but weak: Distinguish alternatives practice summary/ })).toBeVisible();
    await expect(startedObjective.getByRole("link", { name: "Practice this skill" })).toHaveAttribute(
      "href",
      "/train?receiptConcept=atrial_fibrillation&subskill=discriminate&returnTo=%2Fhome%3Fpanel%3Dcompetencies&concept=atrial_fibrillation",
    );

    await panel.getByRole("searchbox", { name: "Search skills" }).fill("Formative composite");
    await expect(map.getByRole("status")).toContainText("1 matching finding across 1 domain");
    const integrationDomain = map.locator("details").filter({
      has: page.getByText("Integration", { exact: true }),
    }).first();
    await integrationDomain.locator(":scope > summary").click();
    const compositeObjective = integrationDomain.locator("details").filter({
      has: page.getByText("Formative composite", { exact: true }),
    }).first();
    await expect(compositeObjective.locator(":scope > summary")).toContainText("Practice only so far");
    await expect(compositeObjective.locator(":scope > summary")).not.toContainText("Scored check available");
    await compositeObjective.locator(":scope > summary").click();
    await expect(compositeObjective.getByText("A scored ECG check isn't available for this skill yet.", { exact: true })).toBeVisible();
  });

  test("paginates, searches, and filters committed activity without answer replay", async ({ page }) => {
    const requests: string[] = [];
    const activity = Array.from({ length: 23 }, (_, index) => activityFixture(index));
    await page.unroute("**/api/backend/learning/activity?*");
    await page.route("**/api/backend/learning/activity?*", (route) => {
      const url = new URL(route.request().url());
      const mode = url.searchParams.get("mode") ?? "all";
      const limit = Number(url.searchParams.get("limit") ?? "20");
      const cursor = url.searchParams.get("cursor");
      const filtered = mode === "all" ? activity : activity.filter((item) => item.mode === mode);

      if (limit === 2) {
        return route.fulfill({
          json: { version: "learning-activity-v1", items: filtered.slice(0, 2), nextCursor: null, hasMore: false },
        });
      }

      requests.push(url.search);
      if (cursor) {
        return route.fulfill({
          json: {
            version: "learning-activity-v1",
            items: mode === "all" ? [filtered[19], ...filtered.slice(20)] : [],
            nextCursor: null,
            hasMore: false,
          },
        });
      }
      return route.fulfill({
        json: {
          version: "learning-activity-v1",
          items: filtered.slice(0, 20),
          nextCursor: filtered.length > 20 ? "opaque-next" : null,
          hasMore: filtered.length > 20,
        },
      });
    });

    await page.goto("/home?panel=activity");
    const panel = page.getByRole("tabpanel", { name: "History" });
    await expect(panel.getByLabel("How activity affects progress")).toBeVisible();
    await expect(page.getByTestId("activity-item")).toHaveCount(20);

    const grouped = panel.getByTestId("activity-item").filter({ hasText: "Sinus rhythm" });
    await expect(grouped.locator("summary").getByText("Sinus rhythm", { exact: true })).toBeVisible();
    await expect(grouped.getByText("Recognize and name · 2 more skills", { exact: false })).toBeVisible();
    await expect(grouped.getByText("Scored check", { exact: true })).toBeVisible();
    await grouped.locator("summary").click();
    await expect(grouped.getByText("What happened", { exact: true })).toBeVisible();
    await expect(grouped.getByText("Skills included in this activity.", { exact: true })).toBeVisible();
    await expect(grouped.getByRole("link", { name: "Practice Sinus rhythm: Recognize and name" })).toHaveAttribute(
      "href",
      "/rapid?receiptConcept=sinus_rhythm&subskill=recognize&returnTo=%2Fhome%3Fpanel%3Dactivity&focus=sinus_rhythm",
    );
    await expect(grouped.getByRole("link", { name: /review result/i })).toHaveCount(0);

    const clinicalActivity = panel.getByTestId("activity-item").filter({ hasText: "Clinical case" }).first();
    await expect(clinicalActivity.locator("summary").getByText("Formative practice", { exact: true })).toBeVisible();
    await expect(clinicalActivity.locator("summary").getByText(/Confidence/)).toHaveCount(0);
    await clinicalActivity.locator("summary").click();
    await expect(clinicalActivity.getByText("Confidence", { exact: true })).toHaveCount(0);

    await panel.getByRole("button", { name: "Load older activity" }).click();
    await expect(page.getByTestId("activity-item")).toHaveCount(23);

    await panel.getByLabel("Score").selectOption("unverified");
    await expect(page.getByTestId("activity-item")).toHaveCount(1);
    await expect(panel.getByTestId("activity-item").getByText("Older record", { exact: true })).toBeVisible();
    await panel.getByLabel("Score").selectOption("all");

    await panel.getByLabel("Follow-up").selectOption("recommended");
    await expect(page.getByTestId("activity-item")).toHaveCount(8);
    await panel.getByLabel("Follow-up").selectOption("all");

    await panel.getByRole("searchbox", { name: "Search recent history" }).fill("Nonspecific ST-T change");
    await expect(page.getByTestId("activity-item")).toHaveCount(1);
    await expect(panel.getByTestId("activity-item").locator("summary").getByText("Sinus rhythm", { exact: true })).toBeVisible();
    await panel.getByRole("button", { name: "Clear filters" }).click();
    await expect(page.getByTestId("activity-item")).toHaveCount(23);

    await panel.getByRole("button", { name: "Guided", exact: true }).click();
    await expect(page.getByTestId("activity-item")).toHaveCount(6);
    expect(requests.some((search) => (
      search.includes("mode=guided")
      && search.includes("limit=20")
      && !search.includes("cursor=")
    ))).toBe(true);
  });

  test("does not append stale pagination results after switching activity modes", async ({ page }) => {
    const initialItems = Array.from({ length: 20 }, (_, index) => ({
      id: `evt_initial_${index}`,
      mode: "rapid",
      kind: "ecg_attempt",
      occurredAt: "2026-07-13T12:00:00Z",
      objectiveId: "sinus_rhythm",
      subskill: "recognize",
      testedCompetencies: [{ objectiveId: "sinus_rhythm", subskill: "recognize", evidence: "independent" }],
      score: 0.8,
      confidence: 3,
      assistance: "unassisted",
      evidence: "independent",
      reviewRecommended: false,
    }));
    const guidedItem = {
      ...initialItems[0],
      id: "evt_guided_current",
      mode: "guided",
    };
    const staleItem = {
      ...initialItems[0],
      id: "evt_rapid_stale",
      objectiveId: "nonspecific_st_t_change",
      testedCompetencies: [{ objectiveId: "nonspecific_st_t_change", subskill: "recognize", evidence: "independent" }],
    };
    let notifyCursorRequested: () => void = () => undefined;
    const cursorRequested = new Promise<void>((resolve) => { notifyCursorRequested = resolve; });
    let releaseCursor: () => void = () => undefined;
    const cursorGate = new Promise<void>((resolve) => { releaseCursor = resolve; });

    await page.unroute("**/api/backend/learning/activity?*");
    await page.route("**/api/backend/learning/activity?*", async (route) => {
      const url = new URL(route.request().url());
      const mode = url.searchParams.get("mode") ?? "all";
      const limit = Number(url.searchParams.get("limit") ?? "20");
      if (limit === 2) {
        return route.fulfill({
          json: { version: "learning-activity-v1", items: initialItems.slice(0, 2), nextCursor: null, hasMore: false },
        });
      }
      if (url.searchParams.has("cursor")) {
        notifyCursorRequested();
        await cursorGate;
        return route.fulfill({
          json: { version: "learning-activity-v1", items: [staleItem], nextCursor: null, hasMore: false },
        });
      }
      if (mode === "guided") {
        return route.fulfill({
          json: { version: "learning-activity-v1", items: [guidedItem], nextCursor: null, hasMore: false },
        });
      }
      return route.fulfill({
        json: { version: "learning-activity-v1", items: initialItems, nextCursor: "stale-cursor", hasMore: true },
      });
    });

    await page.goto("/home?panel=activity");
    const panel = page.getByRole("tabpanel", { name: "History" });
    await expect(page.getByTestId("activity-item")).toHaveCount(20);
    const loadMore = panel.getByRole("button", { name: "Load older activity" });
    await loadMore.click();
    await cursorRequested;
    await expect(panel.getByRole("button", { name: "Loading more…" })).toBeDisabled();
    await expect(panel.locator('[aria-busy="true"]')).toHaveCount(1);
    const staleResponse = page.waitForResponse((response) => new URL(response.url()).searchParams.has("cursor"));

    await panel.getByRole("button", { name: "Guided", exact: true }).click();
    releaseCursor();
    await staleResponse;
    await page.waitForLoadState("networkidle");

    await expect(page.getByTestId("activity-item")).toHaveCount(1);
    await expect(page.getByTestId("activity-item")).toContainText("Guided lesson");
    await expect(page.getByText("Nonspecific ST-T change", { exact: true })).toHaveCount(0);
  });

  test("preserves loaded activity when a cursor request fails and permits retry", async ({ page }) => {
    let loadMoreAttempts = 0;
    const items = Array.from({ length: 20 }, (_, index) => ({
      id: `evt_keep_${index}`,
      mode: "rapid",
      kind: "ecg_attempt",
      occurredAt: "2026-07-13T12:00:00Z",
      objectiveId: "sinus_rhythm",
      subskill: "recognize",
      testedCompetencies: [{ objectiveId: "sinus_rhythm", subskill: "recognize", evidence: "independent" }],
      score: 0.8,
      confidence: 3,
      assistance: "unassisted",
      evidence: "independent",
      reviewRecommended: false,
    }));
    await page.unroute("**/api/backend/learning/activity?*");
    await page.route("**/api/backend/learning/activity?*", (route) => {
      const url = new URL(route.request().url());
      const limit = Number(url.searchParams.get("limit") ?? "20");
      if (limit === 2) {
        return route.fulfill({
          json: { version: "learning-activity-v1", items: items.slice(0, 2), nextCursor: null, hasMore: false },
        });
      }
      if (url.searchParams.has("cursor")) {
        loadMoreAttempts += 1;
        if (loadMoreAttempts === 1) return route.fulfill({ status: 503, body: "unavailable" });
        return route.fulfill({
          json: { version: "learning-activity-v1", items: [], nextCursor: null, hasMore: false },
        });
      }
      return route.fulfill({
        json: { version: "learning-activity-v1", items, nextCursor: "retry-cursor", hasMore: true },
      });
    });

    await page.goto("/home?panel=activity");
    const panel = page.getByRole("tabpanel", { name: "History" });
    await expect(page.getByTestId("activity-item")).toHaveCount(20);
    const loadMore = panel.getByRole("button", { name: "Load older activity" });
    await loadMore.click();
    await expect(panel.getByRole("alert")).toContainText("items already shown are still available");
    await expect(page.getByTestId("activity-item")).toHaveCount(20);

    await loadMore.click();
    await expect(loadMore).toHaveCount(0);
    await expect(page.getByTestId("activity-item")).toHaveCount(20);
    expect(loadMoreAttempts).toBe(2);
  });

  test("keeps preferences out of the dashboard and available in Account", async ({ page }) => {
    await page.goto("/home");
    await expect(page.getByRole("tab", { name: "Preferences" })).toHaveCount(0);
    await expect(page.getByRole("tablist", { name: "Learning dashboard sections" }).getByRole("tab")).toHaveCount(5);

    await page.goto("/account#learning-preferences");
    await expect(page).toHaveURL(/\/account#learning-preferences$/);
    await expect(page.getByRole("heading", { name: "Shape your learning workspace" })).toBeVisible();
    await expect(page.getByRole("group", { name: "About your learning" })).toBeVisible();
  });

  test("keeps canonical panels reachable with touch targets and no mobile overflow", async ({ page }) => {
    for (const width of [320, 390]) {
      await page.setViewportSize({ width, height: 844 });
      await page.goto("/home?panel=plan");

      const recommendedAction = page.getByTestId("recommended-action");
      await expectTouchTarget(recommendedAction);
      const actionBox = await recommendedAction.boundingBox();
      expect(actionBox!.x).toBeGreaterThanOrEqual(0);
      expect(actionBox!.x + actionBox!.width).toBeLessThanOrEqual(width + 1);

      for (const label of ["Home", "History", "Progress", "Schedule", "My plan"]) {
        const tab = page.getByRole("tab", { name: label });
        await tab.scrollIntoViewIfNeeded();
        await expectTouchTarget(tab);
      }
      await expectNoHorizontalOverflow(page);

      await page.getByRole("tab", { name: "History" }).click();
      const activityPanel = page.getByRole("tabpanel", { name: "History" });
      await expect(activityPanel.getByRole("searchbox", { name: "Search recent history" })).toHaveCount(0);
      await expectTouchTarget(activityPanel.getByRole("button", { name: "Saved items (0)" }));
      await expectNoHorizontalOverflow(page);

      await page.getByRole("tab", { name: "Progress" }).click();
      const competencyPanel = page.getByRole("tabpanel", { name: "Progress" });
      await expectTouchTarget(competencyPanel.getByRole("button", { name: /Not started/ }));
      const competencySearch = competencyPanel.getByRole("searchbox", { name: "Search skills" });
      const competencySearchTarget = competencySearch.locator("..");
      await expectTouchTarget(competencySearchTarget);
      await competencySearchTarget.click();
      await expect(competencySearch).toBeFocused();
      await expectNoHorizontalOverflow(page);

      await page.getByRole("tab", { name: "Home" }).click();
      await expectTouchTarget(page.getByRole("link", { name: "Start rapid practice" }));
      await expectNoHorizontalOverflow(page);
    }
  });
});
