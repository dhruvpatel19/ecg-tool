import { expect, test } from "@playwright/test";
import { collectConsoleErrors, registerVerifiedE2ELearner } from "./helpers";

const profileFixture = {
  learnerId: "demo",
  displayName: "Demo learner",
  attemptCount: 4,
  mastery: [],
  subskillMastery: [],
  recentAttempts: [],
  misconceptions: [],
  weakObjectives: [],
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
  independentReceipt: { mode: "rapid", caseConcept: "sinus_rhythm", receiptConcept: "sinus_rhythm", subskill: "recognize" },
  evidenceUncertainty: null,
};

const competenciesFixture = {
  learnerId: "demo",
  registryVersion: "coherence-test",
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
  coachContext: { contextId: "apc1.profile-test", version: "adaptive-plan-coach-v1", expiresAt: "2099-01-01T00:00:00Z" },
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
    href: "/rapid?focus=sinus_rhythm&subskill=recognize&suggestedLength=5",
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

test.describe("My learning", () => {
  test.beforeEach(async ({ page }) => {
    await registerVerifiedE2ELearner(page, { prefix: "my_learning" });
  });

  test("consolidates the legacy study plan and keeps one stable navigation destination", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/review");

    await expect(page).toHaveURL(/\/profile\?tab=plan$/);
    await expect(page.getByRole("heading", { name: /’s learning$/ })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Study plan" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByTestId("recommended-action")).toBeVisible({ timeout: 30_000 });

    const learningLink = page.getByRole("navigation", { name: "Primary navigation" }).getByRole("link", { name: "My learning" });
    await expect(learningLink).toHaveAttribute("href", "/profile");
    await expect(learningLink).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("link", { name: "Progress and insights" })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Study plan" })).toHaveCount(0);
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("supports deep-linked tabs, keyboard movement, and browser history", async ({ page }) => {
    await page.goto("/profile?tab=competencies");
    const competencyTab = page.getByRole("tab", { name: "Competency map" });
    await expect(competencyTab).toHaveAttribute("aria-selected", "true");

    await competencyTab.focus();
    await page.keyboard.press("ArrowRight");
    await expect(page).toHaveURL(/\/profile\?tab=activity$/);
    await expect(page.getByRole("tab", { name: "Activity" })).toBeFocused();

    await page.getByRole("tab", { name: "Overview" }).click();
    await expect(page).toHaveURL(/\/profile\?tab=overview$/);
    await page.goBack();
    await expect(page).toHaveURL(/\/profile\?tab=activity$/);
    await expect(page.getByRole("tab", { name: "Activity" })).toHaveAttribute("aria-selected", "true");
    await page.goForward();
    await expect(page).toHaveURL(/\/profile\?tab=overview$/);
  });

  test("offers an honest baseline destination when the planner has no runnable stage", async ({ page }) => {
    await page.route("**/api/backend/learners/demo", (route) => route.fulfill({
      json: {
        learnerId: "demo",
        displayName: "Demo learner",
        attemptCount: 0,
        mastery: [],
        subskillMastery: [],
        recentAttempts: [],
        misconceptions: [],
        weakObjectives: [],
      },
    }));
    await page.route("**/api/backend/learners/demo/competencies", (route) => route.fulfill({
      json: { learnerId: "demo", registryVersion: "test", objectives: [] },
    }));
    await page.route("**/api/backend/adaptive/plan", (route) => route.fulfill({
      json: {
        learnerId: "demo",
        generatedAt: "2026-07-14T12:00:00Z",
        plannerKind: "verified_competency_scheduler",
        generativeTutorUsed: false,
        basis: {
          independentAttempts: 0,
          dueCompetencies: 0,
          overdueCompetencies: 0,
          highConfidenceMisses: 0,
          eligibleConcepts: 0,
          baselineNeeded: true,
        },
        primary: null,
        priorities: [],
        stages: [],
        integration: null,
        clinicalApplication: null,
        explanation: "A baseline is needed before a personalized plan can be scheduled.",
      },
    }));

    await page.goto("/profile?tab=overview");
    const baselineHref = "/rapid?pace=untimed&suggestedLength=10&returnTo=%2Fprofile%3Ftab%3Doverview";
    await expect(page.getByText("Baseline · not yet personalized", { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Start baseline" })).toHaveAttribute("href", baselineHref);
    await expect(page.locator("a.button.primary")).toHaveCount(1);
    await expect(page.getByRole("link", { name: "Start a baseline" })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Practice next" })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Open this step" })).toHaveCount(0);
    await expect(page.locator('a[href="/profile?tab=plan"]')).toHaveCount(0);

    await page.getByRole("tab", { name: "Study plan" }).click();
    await expect(page.getByTestId("recommended-action")).toHaveText(/Start baseline/);
    await expect(page.getByTestId("recommended-action")).toHaveAttribute(
      "href",
      "/rapid?pace=untimed&suggestedLength=10&returnTo=%2Fprofile%3Ftab%3Dplan",
    );
    await expect(page.getByText("General practice · not personalized", { exact: true })).toHaveCount(0);
  });

  test("keeps loaded evidence usable when the personalized planner fails", async ({ page }) => {
    await page.route("**/api/backend/learners/demo", (route) => route.fulfill({ json: profileFixture }));
    await page.route("**/api/backend/learners/demo/competencies", (route) => route.fulfill({ json: competenciesFixture }));
    await page.route("**/api/backend/adaptive/plan", (route) => route.fulfill({ status: 503, body: "planner unavailable" }));

    await page.goto("/profile?tab=overview");

    await expect(page.getByText(/personalized study plan could not be loaded/i)).toBeVisible();
    await expect(page.getByText("General practice · not personalized", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Personalized step unavailable" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Start general practice" })).toHaveAttribute(
      "href",
      "/rapid?pace=untimed&suggestedLength=5&returnTo=%2Fprofile%3Ftab%3Doverview",
    );
    await expect(page.getByLabel("Progress summary")).toContainText("72%");
    await expect(page.getByText("Establish an independent baseline", { exact: true })).toHaveCount(0);
    await expect(page.locator("a.button.primary")).toHaveCount(1);

    await page.getByRole("tab", { name: "Study plan" }).click();
    await expect(page.getByRole("tabpanel", { name: "Study plan" }).getByRole("alert")).toContainText("couldn’t load your study plan");
  });

  test("does not turn a failed competency request into zero or not-started evidence", async ({ page }) => {
    await page.route("**/api/backend/learners/demo", (route) => route.fulfill({ json: profileFixture }));
    await page.route("**/api/backend/learners/demo/competencies", (route) => route.fulfill({ status: 503, body: "competencies unavailable" }));
    await page.route("**/api/backend/adaptive/plan", (route) => route.fulfill({ json: runnablePlanFixture }));

    await page.goto("/profile?tab=overview");

    await expect(page.getByText(/competency detail could not be loaded/i)).toBeVisible();
    const metrics = page.getByLabel("Progress summary");
    await expect(metrics.locator("strong")).toHaveText(["—", "—", "—", "—"]);
    await expect(page.getByText("Competency detail is temporarily unavailable. Retry to restore this queue.", { exact: true })).toBeVisible();
    await expect(page.getByText("Review timing is temporarily unavailable.", { exact: true })).toBeVisible();

    await page.getByRole("tab", { name: "Competency map" }).click();
    await expect(page.getByText("No zero scores or “not started” states have been inferred from the failed request.", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: /Not started/ })).toHaveCount(0);
    const retry = page.getByRole("button", { name: "Retry competency detail" });
    await expect(retry).toBeVisible();
    expect((await retry.boundingBox())?.height).toBeGreaterThanOrEqual(44);
  });

  test("labels planner evidence as objective checks rather than ECGs or sessions", async ({ page }) => {
    await page.route("**/api/backend/adaptive/plan", async (route) => {
      const response = await route.fetch();
      const plan = await response.json();
      await route.fulfill({ response, json: {
        ...plan,
        // The planner counts exact competency observations. Keep the legacy
        // compatibility alias synchronized so this remains a valid response.
        basis: {
          ...plan.basis,
          independentCompetencyObservations: 3,
          independentAttempts: 3,
          independentAttemptUnit: "competency_observation",
        },
      } });
    });
    await page.goto("/profile?tab=plan");
    await page.getByText("Why this recommendation", { exact: true }).click();
    await expect(page.getByText(/3 objective checks recorded/)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/scored checks completed/)).toHaveCount(0);
  });

  test("puts started and due competencies before unseen skills and labels eligibility honestly", async ({ page }) => {
    const competencyCell = (state: "unseen" | "acquiring" | "developing", overrides: Record<string, unknown> = {}) => ({
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
      independentReceipt: { mode: "rapid", caseConcept: "normal_ecg", receiptConcept: "normal_ecg", subskill: "recognize" },
      evidenceUncertainty: null,
      ...overrides,
    });
    const unseen = Array.from({ length: 11 }, (_, index) => ({
      objectiveId: `unseen_${String(index + 1).padStart(2, "0")}`,
      label: `Unseen ${String(index + 1).padStart(2, "0")}`,
      domain: index === 0 ? "st_t_mi" : "rhythm",
      caseConcepts: ["normal_ecg"],
      evidenceCeiling: "eligible_real_case",
      subskills: [competencyCell("unseen")],
    }));
    await page.route("**/api/backend/learners/demo/competencies", (route) => route.fulfill({
      json: {
        learnerId: "demo",
        registryVersion: "sort-test",
        objectives: [
          ...unseen,
          {
            objectiveId: "started_but_weak",
            label: "Started but weak",
            domain: "rhythm",
            caseConcepts: ["sinus_rhythm"],
            evidenceCeiling: "eligible_real_case",
            subskills: [competencyCell("acquiring", { attempts: 2, independentAttempts: 1, independentMastery: 0.2 })],
          },
          {
            objectiveId: "due_skill",
            label: "Due skill",
            domain: "rhythm",
            caseConcepts: ["sinus_rhythm"],
            evidenceCeiling: "eligible_real_case",
            subskills: [competencyCell("developing", { attempts: 3, independentAttempts: 2, independentMastery: 0.45, isDue: true, dueState: "due" })],
          },
          {
            objectiveId: "formative_composite",
            label: "ZZ formative composite",
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
      },
    }));

    await page.goto("/profile?tab=competencies");
    const rows = page.locator("details.profile-objective");
    await expect(rows).toHaveCount(10);
    await expect(page.getByLabel("Filter by domain").locator('option[value="st_t_mi"]')).toHaveText("ST–T / infarction");
    const visibleLabels = await rows.locator("summary > span:first-child > strong").allTextContents();
    expect(visibleLabels.slice(0, 2)).toEqual(["Due skill", "Started but weak"]);
    await expect(rows.filter({ hasText: "Unseen 01" })).toContainText("Real-ECG check available");
    await expect(rows.filter({ hasText: "Unseen 01" })).not.toContainText("Checked on real ECGs");

    await page.getByRole("button", { name: "Show all 14" }).click();
    await expect(rows.filter({ hasText: "Formative Composite" })).toContainText("Formative practice only");
    await expect(rows.filter({ hasText: "Formative Composite" })).not.toContainText("Real-ECG check available");

    await page.getByRole("button", { name: /Not started/ }).click();
    const unseenLabels = await rows.locator("summary > span:first-child > strong").allTextContents();
    expect(unseenLabels[0]).toBe("Unseen 01");
    await expect(rows.filter({ hasText: "Started but weak" })).toHaveCount(0);

    await page.getByRole("button", { name: /Not started/ }).click();
    await page.getByLabel("Search competencies").fill("Started but weak");
    await expect(rows).toHaveCount(1);
    await expect(rows).toContainText("Started but weak");
  });

  test("keeps all five sections usable at 320px and 390px", async ({ page }) => {
    for (const width of [320, 390]) {
      await page.setViewportSize({ width, height: 844 });
      await page.goto("/profile?tab=plan");
      const recommendedAction = page.getByTestId("recommended-action");
      await expect(recommendedAction).toBeVisible({ timeout: 30_000 });
      const actionBox = await recommendedAction.boundingBox();
      expect(actionBox?.height).toBeGreaterThanOrEqual(44);
      expect(actionBox?.x).toBeGreaterThanOrEqual(0);
      expect((actionBox?.x ?? 0) + (actionBox?.width ?? 0)).toBeLessThanOrEqual(width);

      for (const label of ["Overview", "Study plan", "Competency map", "Activity", "Preferences"]) {
        const tab = page.getByRole("tab", { name: label });
        await tab.scrollIntoViewIfNeeded();
        await expect(tab).toBeVisible();
        expect((await tab.boundingBox())?.height).toBeGreaterThanOrEqual(44);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
    }
  });

  test("paginates and filters answer-key-free cross-mode activity without duplicates", async ({ page }) => {
    const requests: string[] = [];
    const activity = Array.from({ length: 23 }, (_, index) => ({
      id: `evt_${String(index).padStart(3, "0")}`,
      mode: index % 4 === 0 ? "guided" : index % 4 === 1 ? "training" : index % 4 === 2 ? "rapid" : "clinical",
      kind: index % 4 === 0 ? "guided_task" : "ecg_attempt",
      occurredAt: `2026-07-${String(13 - Math.floor(index / 4)).padStart(2, "0")}T12:00:00Z`,
      objectiveId: index % 4 === 0 ? "axis_normal" : "right_bundle_branch_block",
      subskill: index % 4 === 0 ? "localize" : "discriminate",
      testedCompetencies: index === 2 ? [
        { objectiveId: "sinus_rhythm", subskill: "recognize", evidence: "independent" },
        { objectiveId: "axis_normal", subskill: "recognize", evidence: "independent" },
        { objectiveId: "nonspecific_st_t_change", subskill: "recognize", evidence: "independent" },
      ] : [],
      score: index === 22 ? null : index % 3 === 0 ? 0.5 : 0.9,
      confidence: 4,
      assistance: index % 4 === 0 ? "assisted" : "unassisted",
      evidence: index === 22 ? "legacy_unverified" : index % 4 === 0 || index % 4 === 3 ? "formative" : "independent",
      reviewRecommended: index !== 22 && index % 3 === 0,
    }));
    await page.route("**/api/backend/learning/activity?*", async (route) => {
      const url = new URL(route.request().url());
      requests.push(url.search);
      const mode = url.searchParams.get("mode");
      const cursor = url.searchParams.get("cursor");
      const filtered = mode === "all" ? activity : activity.filter((item) => item.mode === mode);
      const pageItems = cursor ? filtered.slice(20) : filtered.slice(0, 20);
      await route.fulfill({
        json: {
          version: "learning-activity-v1",
          items: pageItems,
          nextCursor: !cursor && filtered.length > 20 ? "opaque-next" : null,
          hasMore: !cursor && filtered.length > 20,
        },
      });
    });

    await page.goto("/profile?tab=activity");
    await expect(page.getByTestId("activity-item")).toHaveCount(20, { timeout: 30_000 });
    await expect(page.getByText("Rapid ECG · 3 skills checked", { exact: true })).toBeVisible();
    await expect(page.getByText(/Sinus rhythm.*Normal axis.*Nonspecific ST-T change/i)).toBeVisible();
    await page.getByRole("button", { name: "Load more activity" }).click();
    await expect(page.getByTestId("activity-item")).toHaveCount(23);
    const ids = await page.getByTestId("activity-item").evaluateAll((nodes) => nodes.map((node) => node.textContent));
    expect(ids).toHaveLength(23);
    await expect(page.getByText("Legacy record · not used for mastery", { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: /review result/i })).toHaveCount(0);

    await page.getByRole("button", { name: "Guided", exact: true }).click();
    await expect(page.getByTestId("activity-item")).toHaveCount(6);
    expect(requests.at(-1)).toContain("mode=guided");
    expect(requests.at(-1)).not.toContain("cursor=");
  });

  test("preserves loaded activity when a later page fails and permits retry", async ({ page }) => {
    let loadMoreAttempts = 0;
    const items = Array.from({ length: 20 }, (_, index) => ({
      id: `evt_keep_${index}`,
      mode: "rapid",
      kind: "ecg_attempt",
      occurredAt: "2026-07-13T12:00:00Z",
      objectiveId: "sinus_rhythm",
      subskill: "recognize",
      score: 0.8,
      confidence: 3,
      assistance: "unassisted",
      evidence: "independent",
      reviewRecommended: false,
    }));
    await page.route("**/api/backend/learning/activity?*", async (route) => {
      const url = new URL(route.request().url());
      if (url.searchParams.has("cursor")) {
        loadMoreAttempts += 1;
        if (loadMoreAttempts === 1) {
          await route.fulfill({ status: 503, body: "unavailable" });
          return;
        }
        await route.fulfill({ json: { version: "learning-activity-v1", items: [], nextCursor: null, hasMore: false } });
        return;
      }
      await route.fulfill({ json: { version: "learning-activity-v1", items, nextCursor: "retry-cursor", hasMore: true } });
    });

    await page.goto("/profile?tab=activity");
    await expect(page.getByTestId("activity-item")).toHaveCount(20, { timeout: 30_000 });
    const loadMore = page.getByRole("button", { name: "Load more activity" });
    await loadMore.click();
    await expect(page.getByRole("tabpanel", { name: "Activity" }).getByRole("alert")).toContainText("items already shown are still available");
    await expect(page.getByTestId("activity-item")).toHaveCount(20);
    await loadMore.click();
    await expect(loadMore).toHaveCount(0);
    await expect(page.getByTestId("activity-item")).toHaveCount(20);
  });
});
