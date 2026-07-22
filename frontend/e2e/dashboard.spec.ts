import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { collectConsoleErrors } from "./helpers";

const dashboardToday = new Date().toLocaleDateString("en-CA", { timeZone: "America/New_York" });

async function expectNoWcagViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(results.violations.map((violation) => ({
    id: violation.id,
    targets: violation.nodes.map((node) => node.target.join(" ")),
  })), JSON.stringify(results.violations, null, 2)).toEqual([]);
}

const profileFixture = {
  learnerId: "demo",
  displayName: "Alex Student",
  attemptCount: 7,
  mastery: [],
  subskillMastery: [],
  recentAttempts: [],
  misconceptions: [],
  weakObjectives: [],
};

const adaptivePlanFixture = {
  learnerId: "demo",
  coachContext: {
    contextId: "apc1.dashboard-test",
    version: "adaptive-plan-coach-v1",
    expiresAt: "2099-01-01T00:00:00Z",
  },
  generatedAt: "2026-07-14T12:00:00Z",
  plannerKind: "verified_competency_scheduler",
  generativeTutorUsed: false,
  basis: {
    independentCompetencyObservations: 6,
    independentAttempts: 6,
    independentAttemptUnit: "competency_observation",
    dueCompetencies: 1,
    overdueCompetencies: 1,
    highConfidenceMisses: 1,
    eligibleConcepts: 12,
    baselineNeeded: false,
  },
  primary: {
    objectiveId: "atrial_fibrillation",
    label: "Atrial fibrillation",
    domain: "rhythm",
    caseConcept: "atrial_fibrillation",
    eligibleDistinct: 20,
    subskill: "discriminate",
    state: "developing",
    attempts: 3,
    independentAttempts: 2,
    independentMastery: 0.58,
    highConfidenceWrong: 1,
    isDue: true,
    dueState: "overdue",
    overdueDays: 2,
    nextDueAt: "2026-07-14T10:00:00Z",
    stabilityDays: 2,
    distinctSuccessfulEcgs: 1,
    distinctModes: 1,
    lapses: 1,
    reason: "A confident miss and due retrieval check make this the most useful next skill.",
  },
  priorities: [{
    objectiveId: "atrial_fibrillation",
    label: "Atrial fibrillation",
    domain: "rhythm",
    caseConcept: "atrial_fibrillation",
    eligibleDistinct: 20,
    subskill: "discriminate",
    state: "developing",
    attempts: 3,
    independentAttempts: 2,
    independentMastery: 0.58,
    highConfidenceWrong: 1,
    isDue: true,
    dueState: "overdue",
    overdueDays: 2,
    nextDueAt: "2026-07-14T10:00:00Z",
    stabilityDays: 2,
    distinctSuccessfulEcgs: 1,
    distinctModes: 1,
    lapses: 1,
    reason: "A confident miss and due retrieval check make this the most useful next skill.",
  }],
  stages: [{
    order: 1,
    mode: "train",
    title: "Separate atrial fibrillation from close rhythm mimics",
    purpose: "Compare the rhythm on fresh ECGs and make the decisive trace evidence explicit.",
    href: "/train?concept=atrial_fibrillation&subskill=discriminate&returnTo=%2Fhome%3Fpanel%3Dplan",
    suggestedLength: 5,
    receiptConcept: "atrial_fibrillation",
    receiptSubskill: "discriminate",
    evidenceKind: "independent_transfer",
  }],
  guidedRemediation: null,
  integration: null,
  clinicalApplication: null,
  explanation: "The verified scheduler selected the next executable practice stage.",
};

const competenciesFixture = {
  learnerId: "demo",
  registryVersion: "v-test",
  calendarProjection: {
    timeZone: "America/New_York",
    today: dashboardToday,
    reviewDays: [{ date: dashboardToday, total: 1 }],
  },
  objectives: [
    {
      objectiveId: "atrial_fibrillation",
      label: "Atrial fibrillation",
      domain: "rhythm",
      caseConcepts: ["atrial_fibrillation"],
      evidenceCeiling: "eligible_real_case",
      subskills: [{
        subskill: "discriminate",
        state: "developing",
        formativeScore: 0.7,
        independentMastery: 0.58,
        attempts: 3,
        independentAttempts: 2,
        highConfidenceWrong: 1,
        lastPracticedAt: "2026-07-14T10:00:00Z",
        lastIndependentAt: "2026-07-14T10:00:00Z",
        lastIndependentCorrect: false,
        nextDueAt: "2026-07-14T10:00:00Z",
        dueState: "overdue",
        isDue: true,
        overdueDays: 2,
        daysUntilDue: null,
        stabilityDays: 2,
        lapses: 1,
        spacedRetrievals: 1,
        distinctEligibleEcgs: 20,
        distinctSuccessfulEcgs: 1,
        distinctModes: 1,
        distinctMorphologies: 1,
        independentEvidenceAvailable: true,
        independentReceipt: { mode: "train", caseConcept: "atrial_fibrillation", receiptConcept: "atrial_fibrillation", subskill: "discriminate" },
        evidenceUncertainty: null,
      }],
    },
    {
      objectiveId: "axis_normal",
      label: "Normal axis",
      domain: "axis",
      caseConcepts: ["axis_normal"],
      evidenceCeiling: "eligible_real_case",
      subskills: [{
        subskill: "recognize",
        state: "durable",
        formativeScore: 1,
        independentMastery: 0.91,
        attempts: 5,
        independentAttempts: 4,
        highConfidenceWrong: 0,
        lastPracticedAt: "2026-07-12T10:00:00Z",
        lastIndependentAt: "2026-07-12T10:00:00Z",
        lastIndependentCorrect: true,
        nextDueAt: "2099-07-20T10:00:00Z",
        dueState: "scheduled",
        isDue: false,
        overdueDays: 0,
        daysUntilDue: 5,
        stabilityDays: 18,
        lapses: 0,
        spacedRetrievals: 3,
        distinctEligibleEcgs: 20,
        distinctSuccessfulEcgs: 4,
        distinctModes: 2,
        distinctMorphologies: 3,
        independentEvidenceAvailable: true,
        independentReceipt: { mode: "rapid", caseConcept: "axis_normal", receiptConcept: "axis_normal", subskill: "recognize" },
        evidenceUncertainty: null,
      }],
    },
  ],
};

const activityFixture = {
  version: "learning-activity-v1",
  nextCursor: null,
  hasMore: false,
  items: [
    {
      id: "evt_recent_1",
      mode: "rapid",
      kind: "ecg_attempt",
      occurredAt: "2026-07-15T12:00:00Z",
      objectiveId: "atrial_fibrillation",
      subskill: "recognize",
      testedCompetencies: [
        { objectiveId: "atrial_fibrillation", subskill: "recognize", evidence: "independent" },
        { objectiveId: "axis_normal", subskill: "recognize", evidence: "independent" },
      ],
      score: 0.72,
      confidence: 5,
      assistance: "unassisted",
      evidence: "independent",
      reviewRecommended: true,
      review: { sessionRef: "lsr1_rapid_partial", attemptIndex: 1, sessionStatus: "abandoned" },
    },
    {
      id: "evt_recent_2",
      mode: "guided",
      kind: "guided_task",
      occurredAt: "2026-07-14T12:00:00Z",
      objectiveId: "axis_normal",
      subskill: "recognize",
      testedCompetencies: [{ objectiveId: "axis_normal", subskill: "recognize", evidence: "formative" }],
      score: 0.9,
      confidence: 3,
      assistance: "assisted",
      evidence: "formative",
      reviewRecommended: false,
      review: null,
      lesson: { moduleId: "foundations", sceneId: "S9" },
    },
  ],
};

const sessionsFixture = {
  version: "learning-sessions-v1",
  hasMore: false,
  nextOffset: null,
  totalSavedItems: 0,
  items: [
    {
      sessionRef: "lsr1_rapid_test",
      mode: "rapid",
      status: "complete",
      attempted: 5,
      total: 5,
      score: 0.8,
      correctCount: null,
      flaggedCount: 0,
      focusCompetencies: [{ objectiveId: "atrial_fibrillation", subskill: "discriminate", mappingSource: "session_focus" }],
      startedAt: "2026-07-15T11:00:00Z",
      completedAt: "2026-07-15T12:00:00Z",
      reviewAvailable: true,
    },
    {
      sessionRef: "lsr1_clinical_test",
      mode: "clinical",
      status: "complete",
      attempted: 3,
      total: 3,
      score: 0.67,
      correctCount: 2,
      flaggedCount: 0,
      focusCompetencies: [{ objectiveId: "axis_normal", subskill: "recognize", mappingSource: "session_focus" }],
      startedAt: "2026-07-14T11:00:00Z",
      completedAt: "2026-07-14T12:00:00Z",
      reviewAvailable: true,
    },
    {
      sessionRef: "lsr1_rapid_partial",
      mode: "rapid",
      status: "abandoned",
      attempted: 2,
      total: 5,
      score: 0.7,
      correctCount: null,
      flaggedCount: 0,
      focusCompetencies: [{ objectiveId: "atrial_fibrillation", subskill: "recognize", mappingSource: "session_focus" }],
      startedAt: "2026-07-13T11:00:00Z",
      completedAt: "2026-07-13T12:00:00Z",
      reviewAvailable: true,
    },
  ],
};

const sessionReviewFixture = {
  version: "learning-session-review-v1",
  session: sessionsFixture.items[0],
  attempts: [
    {
      index: 1,
      score: 0.8,
      competencies: [{ objectiveId: "atrial_fibrillation", subskill: "discriminate", score: 0.8, mappingSource: "committed_event" }],
      confidence: 2,
      assistance: { hintsUsed: 1 },
      flagged: false,
    },
    {
      index: 2,
      score: null,
      competencies: [{ objectiveId: "atrial_fibrillation", subskill: "discriminate", score: null, mappingSource: "session_focus" }],
      confidence: null,
      assistance: null,
      flagged: false,
    },
  ],
};

const clinicalSessionReviewFixture = {
  version: "learning-session-review-v1",
  session: sessionsFixture.items[1],
  attempts: [
    {
      index: 1,
      score: 0.75,
      competencies: [{ objectiveId: "axis_normal", subskill: "apply_in_context", score: 0.75, mappingSource: "committed_event" }],
      // A legacy shared-attempt value must not reappear in the current
      // Clinical review UI.
      confidence: null,
      assistance: { hintsUsed: 0 },
      flagged: false,
    },
  ],
};

const partialRapidReviewFixture = {
  version: "learning-session-review-v1",
  session: sessionsFixture.items[2],
  attempts: [
    {
      index: 1,
      score: 0.8,
      competencies: [{ objectiveId: "atrial_fibrillation", subskill: "recognize", score: 0.8, mappingSource: "committed_event" }],
      confidence: 4,
      assistance: { hintsUsed: 0 },
      flagged: false,
    },
    {
      index: 2,
      score: 0.6,
      competencies: [{ objectiveId: "atrial_fibrillation", subskill: "recognize", score: 0.6, mappingSource: "committed_event" }],
      confidence: 3,
      assistance: { hintsUsed: 0 },
      flagged: false,
    },
  ],
};

const noResumeFixture = { version: "learning-resume-v1", generatedAt: "2026-07-15T12:00:00Z", primary: null, additional: [] };

async function routeLearningHome(page: Page) {
  await page.route("**/api/backend/auth/me", (route) => route.fulfill({
    json: {
      authenticated: true,
      user: { userId: "u_dashboard", username: "alex", displayName: "Alex Student", accountStatus: "verified", emailVerified: true },
    },
  }));
  await page.route("**/api/backend/learners/demo", (route) => route.fulfill({ json: profileFixture }));
  await page.route("**/api/backend/learners/demo/competencies", (route) => route.fulfill({ json: competenciesFixture }));
  await page.route("**/api/backend/adaptive/plan", (route) => route.fulfill({ json: adaptivePlanFixture }));
  await page.route("**/api/backend/learning/resume", (route) => route.fulfill({ json: noResumeFixture }));
  await page.route("**/api/backend/learning/activity?*", (route) => route.fulfill({ json: activityFixture }));
  await page.route("**/api/backend/learners/u_dashboard/pathway-progress**", (route) => route.fulfill({ json: {
    learnerId: "u_dashboard",
    items: [
      {
        pathwayId: "production-curriculum",
        moduleId: "foundations",
        sceneId: "S0",
        status: "complete",
        activeInteractionIndex: 1,
        completedActionIds: ["s0-scope", "s0-route"],
        state: {},
        updatedAt: "2026-07-13T11:00:00Z",
      },
      {
        pathwayId: "production-curriculum",
        moduleId: "foundations",
        sceneId: "S1",
        status: "needs-review",
        activeInteractionIndex: 1,
        completedActionIds: ["s1-model"],
        state: {},
        updatedAt: "2026-07-14T11:00:00Z",
      },
    ],
  } }));
  await page.route("**/api/backend/learning/sessions?*", (route) => route.fulfill({ json: sessionsFixture }));
  await page.route("**/api/backend/learning/sessions/lsr1_rapid_test", (route) => route.fulfill({ json: sessionReviewFixture }));
  await page.route("**/api/backend/learning/sessions/lsr1_clinical_test", (route) => route.fulfill({ json: clinicalSessionReviewFixture }));
  await page.route("**/api/backend/learning/sessions/lsr1_rapid_partial", (route) => route.fulfill({ json: partialRapidReviewFixture }));
  await page.route("**/api/backend/learning/sessions/lsr1_rapid_test/attempts/1/flag", (route) => route.fulfill({ json: {
    sessionRef: "lsr1_rapid_test",
    attemptIndex: 1,
    flagged: route.request().method() === "PUT",
    flaggedCount: route.request().method() === "PUT" ? 1 : 0,
  } }));
  await page.route("**/api/backend/learning/preferences", (route) => route.fulfill({ json: {
    trainingStage: "not_set",
    primaryGoal: "build_fundamentals",
    defaultSessionLength: 5,
    rapidPace: "untimed",
    guidanceLevel: "balanced",
    reduceMotion: false,
    largeControls: false,
    updatedAt: null,
  } }));
  await page.route("**/api/backend/tutor/threads?*", (route) => route.fulfill({ json: { threads: [] } }));
}

test.describe("canonical learning dashboard", () => {
  test.beforeEach(async ({ page }) => routeLearningHome(page));

  test("redirects the retired Today route and presents one action-oriented home", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/home$/);
    const overview = page.locator("#home-panel-overview");
    await expect(page.getByRole("heading", { name: "Welcome back, Alex." })).toBeVisible();
    await expect(page.getByRole("heading", { name: adaptivePlanFixture.stages[0].title })).toBeVisible();
    await expect(overview.getByText(/ready for a quick review because it has been a while/i)).toBeHidden();
    await overview.locator("details").getByText("Why this next?", { exact: true }).click();
    await expect(overview.getByText(/ready for a quick review because it has been a while/i)).toBeVisible();

    const navigation = page.getByRole("navigation", { name: "Primary navigation" });
    await expect(navigation.getByRole("link", { name: "Dashboard" })).toHaveAttribute("href", "/home");
    await expect(navigation.getByRole("link", { name: "Today" })).toHaveCount(0);
    await expect(navigation.getByRole("link", { name: "My learning" })).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("returns an authenticated learner from an unknown route to the dashboard", async ({ page }) => {
    await page.goto("/not-a-real-learning-route");
    await expect(page.getByRole("heading", { name: "That learning route is not available." })).toBeVisible();
    await expect(page.getByRole("link", { name: "Return to dashboard" })).toHaveAttribute("href", "/home");
  });

  test("shows honest evidence counts, two reviewable sessions, and runnable skills", async ({ page }) => {
    await page.goto("/home");
    const summary = page.getByLabel("Learning progress summary");
    await expect(summary.getByText("Skills tested", { exact: true })).toBeVisible();
    await expect(summary.getByText("Staying strong", { exact: true })).toBeVisible();
    await expect(summary.getByText("Ready to review", { exact: true })).toBeVisible();
    await expect(page.getByText("Independent estimate", { exact: true })).toHaveCount(0);
    const foundations = page.getByTestId("foundations-status");
    await expect(foundations).toContainText("1/13");
    await expect(foundations.getByText("Evidence", { exact: true })).toBeVisible();
    await expect(foundations.getByText("3", { exact: true })).toBeVisible();
    await expect(foundations.getByText("Reviews", { exact: true })).toBeVisible();
    await expect(foundations.getByRole("link", { name: /Continue Foundations: One beat, one electrical story/ })).toHaveAttribute("href", "/learn/foundations?scene=S1");
    const recent = page.getByRole("heading", { name: "Your latest practice" }).locator("xpath=ancestor::section");
    await expect(recent).toBeVisible();
    await expect(recent.getByTestId("session-history").getByText("Rapid practice", { exact: true })).toBeVisible();
    await expect(recent.getByTestId("session-history").getByText("Clinical cases", { exact: true })).toBeVisible();
    await expect(recent.getByTestId("session-history").getByText("formative score", { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: /Review Rapid practice from/ })).toHaveAttribute("href", "/home/review/lsr1_rapid_test");
    await expect(page.getByRole("heading", { name: "Skills to revisit" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Practice Atrial fibrillation" })).toHaveAttribute("href", /returnTo=%2Fhome%3Fpanel%3Dcompetencies/);
    const week = page.getByRole("heading", { name: "Coming up this week" }).locator("xpath=ancestor::section");
    await expect(week).toBeVisible();
    await expect(week.getByText("1 suggested review", { exact: true })).toBeVisible();
  });

  test("prioritizes an unfinished session over the next recommendation", async ({ page }) => {
    await page.unroute("**/api/backend/learning/resume");
    await page.route("**/api/backend/learning/resume", (route) => route.fulfill({
      json: {
        version: "learning-resume-v1",
        generatedAt: "2026-07-15T12:00:00Z",
        primary: { mode: "rapid", phase: "deadline", completed: 1, total: 5, updatedAt: "2026-07-15T11:00:00Z", destination: { kind: "rapid" } },
        additional: [],
      },
    }));
    await page.goto("/home");
    await expect(page.getByRole("heading", { name: "Continue Rapid practice" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Continue Rapid practice" })).toHaveAttribute("href", "/rapid");
    await expect(page.getByRole("link", { name: /Up next.*Separate atrial fibrillation/ })).toBeVisible();
    await page.getByRole("tab", { name: "My plan" }).click();
    const studyPlan = page.getByRole("tabpanel", { name: "My plan" });
    await expect(studyPlan.getByRole("heading", { name: "Continue Rapid practice" })).toBeVisible();
    await expect(studyPlan.getByTestId("recommended-action")).toHaveAttribute("href", "/rapid");
    await expect(studyPlan.getByText("Why continue first", { exact: true })).toBeVisible();
  });

  test("keeps loaded sections useful when competency detail fails", async ({ page }) => {
    await page.unroute("**/api/backend/learners/demo/competencies");
    await page.route("**/api/backend/learners/demo/competencies", (route) => route.fulfill({ status: 503, body: "unavailable" }));
    await page.goto("/home");
    await expect(page.getByRole("heading", { name: adaptivePlanFixture.stages[0].title })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Your latest practice" })).toBeVisible();
    const warning = page.getByRole("status").filter({ hasText: "Everything that did load remains available." });
    await expect(warning).toContainText("Your progress details are temporarily unavailable.");
    const summary = page.getByLabel("Learning progress summary");
    await expect(summary.locator("article").nth(0).getByText("—", { exact: true })).toBeVisible();
    await expect(summary.locator("article").nth(1).getByText("—", { exact: true })).toBeVisible();
    await expect(summary.locator("article").nth(2).getByText("—", { exact: true })).toBeVisible();
    await expect(page.getByText("Your practice suggestions could not load.", { exact: true })).toBeVisible();
    const week = page.getByRole("heading", { name: "Coming up this week" }).locator("xpath=ancestor::section");
    await expect(week.getByText(/suggested reviews could not load/i)).toBeVisible();
    await expect(week.getByText("Open", { exact: true })).toHaveCount(0);
  });

  test("opens an answer-safe session review with fresh competency practice", async ({ page }) => {
    await page.goto("/home");
    await page.getByRole("link", { name: /Review Rapid practice from/ }).click();
    await expect(page).toHaveURL(/\/home\/review\/lsr1_rapid_test$/);
    await expect(page.getByRole("heading", { name: "Rapid practice" })).toBeVisible();
    await expect(page.getByText("Review only.", { exact: true })).toBeVisible();
    const sessionSummary = page.getByLabel("Session summary");
    await expect(sessionSummary.locator("article").filter({ hasText: "Questions scored" }).getByText("1/2", { exact: true })).toBeVisible();
    await expect(sessionSummary.locator("article").filter({ hasText: "Lower-confidence answers" }).getByText("1 of 1", { exact: true })).toBeVisible();
    await expect(sessionSummary.locator("article").filter({ hasText: "Questions with hints" }).getByText("1 of 1", { exact: true })).toBeVisible();
    await page.getByText("Question 1", { exact: true }).click();
    await expect(page.getByRole("link", { name: "Practice Atrial fibrillation: discriminate" })).toHaveAttribute("href", /returnTo=%2Fhome%2Freview%2Flsr1_rapid_test/);
    await page.getByRole("button", { name: "Save question", exact: true }).click();
    await expect(page.getByRole("button", { name: "Remove saved", exact: true })).toBeVisible();
    await expect(page.getByLabel("Session summary").locator("article").filter({ hasText: "Saved for review" }).getByText("1", { exact: true })).toBeVisible();
    await page.getByText("Question 2", { exact: true }).click();
    await expect(page.getByText(/Practiced in this session/)).toBeVisible();
    const secondItem = page.locator("details").filter({ hasText: "Question 2" });
    await expect(secondItem.getByRole("link", { name: "Practice Atrial fibrillation: discriminate" })).toBeVisible();
    await expect(page.getByText(/Support not recorded/)).toBeVisible();
    await expect(secondItem.getByRole("link", { name: /Review question & ECG/ })).toBeVisible();
    await expectNoWcagViolations(page);

    const savedOnlyToggle = page.getByRole("button", { name: /^Saved \(/ });
    await savedOnlyToggle.click();
    await page.getByRole("button", { name: "Remove saved", exact: true }).click();
    await expect(page.getByText("Question 1 removed from saved review.", { exact: true })).toHaveText(
      "Question 1 removed from saved review.",
    );
    await expect(savedOnlyToggle).toBeFocused();
    await expect(page.getByText("No questions from this session are saved yet.", { exact: true })).toBeVisible();
  });

  test("keeps Clinical review formative without reintroducing removed confidence measures", async ({ page }) => {
    await page.goto("/home/review/lsr1_clinical_test");
    await expect(page.getByRole("heading", { name: "Clinical cases" })).toBeVisible();
    await expect(page.getByText("Formative score", { exact: true })).toBeVisible();
    await expect(page.getByText(/Clinical case results are formative/)).toBeVisible();
    await expect(page.getByText("Lower-confidence answers", { exact: true })).toHaveCount(0);
    await page.getByText("Question 1", { exact: true }).click();
    await expect(page.getByText(/Confidence not recorded/)).toHaveCount(0);
    await expect(page.getByText("No hints", { exact: true })).toBeVisible();
  });

  test("labels an ended Rapid round as partial and exposes only submitted ECGs", async ({ page }) => {
    await page.goto("/home?panel=activity");
    const history = page.locator("#home-panel-activity").getByTestId("session-history");
    const partialRow = history.locator("article").filter({ hasText: "Partial Rapid round" });
    await expect(partialRow.getByText(/2 of 5 submitted · ended early/)).toBeVisible();
    await expect(partialRow.getByRole("link", { name: /Review Partial Rapid round from/ })).toHaveAttribute(
      "href",
      "/home/review/lsr1_rapid_partial",
    );

    const rapidActivity = page.getByTestId("activity-item").first();
    await rapidActivity.locator("summary").click();
    await expect(rapidActivity.getByText("Partial round", { exact: true })).toBeVisible();
    await expect(rapidActivity.getByRole("link", { name: "Review question & ECG" })).toHaveAttribute(
      "href",
      "/home/review/lsr1_rapid_partial/attempt/1",
    );

    await page.goto("/home/review/lsr1_rapid_partial");
    await expect(page.getByRole("heading", { name: "Partial Rapid round" })).toBeVisible();
    await expect(page.getByText("2 of 5 submitted", { exact: false })).toBeVisible();
    await expect(page.getByText(/Only submitted ECGs are shown; the unanswered ECG was discarded and was not scored/)).toBeVisible();
    await expect(page.getByRole("heading", { name: "Submitted ECGs" })).toBeVisible();
    await expect(page.getByText("Submitted ECG 1", { exact: true })).toBeVisible();
    await expect(page.getByText("Submitted ECG 2", { exact: true })).toBeVisible();
    await expect(page.getByText("Submitted ECG 3", { exact: true })).toHaveCount(0);
    await expectNoWcagViolations(page);
  });

  test("labels native Foundations history and reopens its exact scene", async ({ page }) => {
    await page.goto("/home?panel=activity");
    const foundationsActivity = page.getByTestId("activity-item").filter({ hasText: "Axis is the coarse QRS direction" });
    await expect(foundationsActivity.getByText("Foundations lesson", { exact: true })).toBeVisible();
    await foundationsActivity.locator("summary").click();
    await expect(foundationsActivity.getByRole("link", { name: "Reopen this scene" })).toHaveAttribute("href", "/learn/foundations?scene=S9");
  });

  test("retries competency routes without discarding loaded session evidence", async ({ page }) => {
    await page.unroute("**/api/backend/learners/demo/competencies");
    let competencyRequests = 0;
    await page.route("**/api/backend/learners/demo/competencies", (route) => {
      competencyRequests += 1;
      return route.fulfill({ status: 503, body: "unavailable" });
    });

    await page.goto("/home/review/lsr1_rapid_test");
    await expect(page.getByRole("heading", { name: "Rapid practice" })).toBeVisible();
    await page.getByText("Question 1", { exact: true }).click();
    await expect(page.getByRole("button", { name: "Retry finding practice for Atrial fibrillation" })).toBeVisible();

    await page.unroute("**/api/backend/learners/demo/competencies");
    await page.route("**/api/backend/learners/demo/competencies", (route) => {
      competencyRequests += 1;
      return route.fulfill({ json: competenciesFixture });
    });
    await page.getByRole("button", { name: "Retry finding practice for Atrial fibrillation" }).click();
    await expect(page.getByRole("heading", { name: "Rapid practice" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Practice Atrial fibrillation: discriminate" })).toBeVisible();
    expect(competencyRequests).toBeGreaterThanOrEqual(2);
  });

  test("filters completed sessions to the learner's saved-review queue", async ({ page }) => {
    await page.unroute("**/api/backend/learning/sessions?*");
    await page.route("**/api/backend/learning/sessions?*", (route) => {
      const url = new URL(route.request().url());
      const savedOnly = url.searchParams.get("savedOnly") === "true";
      const offset = Number(url.searchParams.get("offset") ?? 0);
      const flagged = sessionsFixture.items.slice(0, 2).map((item) => ({ ...item, flaggedCount: 1 }));
      if (!savedOnly) return route.fulfill({ json: { ...sessionsFixture, totalSavedItems: 2 } });
      return route.fulfill({ json: {
        ...sessionsFixture,
        totalSavedItems: 2,
        items: offset === 0 ? flagged.slice(0, 1) : flagged.slice(1),
        hasMore: offset === 0,
        nextOffset: offset === 0 ? 10 : null,
      } });
    });
    await page.goto("/home?panel=activity");
    await page.getByRole("button", { name: "Saved items (2)" }).click();
    const history = page.locator("#home-panel-activity").getByTestId("session-history");
    await expect(history.locator("article")).toHaveCount(1);
    await expect(history.getByText("Rapid practice", { exact: true })).toBeVisible();
    await expect(history.getByText("Clinical cases", { exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: "Load more saved sessions" }).click();
    await expect(history.locator("article")).toHaveCount(2);
    await expect(history.getByText("Clinical cases", { exact: true })).toBeVisible();
  });

  test("distinguishes an empty saved queue from an empty session history", async ({ page }) => {
    await page.goto("/home?panel=activity");
    await page.getByRole("button", { name: "Saved items (0)" }).click();
    await expect(page.getByText("No saved items yet.", { exact: true })).toBeVisible();
    await expect(page.getByText("No activity yet.", { exact: true })).toHaveCount(0);
  });

  test("uses one recommendation and one focus-trapped Luna with a selected draft", async ({ page }) => {
    await page.goto("/home");
    await page.getByRole("button", { name: "Why this next?" }).click();
    const dialog = page.getByRole("dialog", { name: "Plan with Luna" });
    const close = page.getByRole("button", { name: "Close Luna" });
    await expect(dialog).toBeVisible();
    await expect(close).toBeFocused();
    await expect(page.getByRole("textbox", { name: "Message Luna" })).toHaveValue("Why is this my next step?");
    await page.keyboard.press("Shift+Tab");
    expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);
    await expectNoWcagViolations(page);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("button", { name: "Why this next?" })).toBeFocused();

    await page.getByRole("tab", { name: "My plan" }).click();
    const planPanel = page.locator("#home-panel-plan");
    await expect(planPanel.getByRole("heading", { name: adaptivePlanFixture.stages[0].title })).toBeVisible();
    await expect(planPanel.getByRole("button", { name: "Plan with Luna" })).toHaveCount(1);
  });

  test("blocks Luna sends until saved history restoration finishes", async ({ page }) => {
    let releaseHistory!: () => void;
    const historyGate = new Promise<void>((resolve) => { releaseHistory = resolve; });
    await page.unroute("**/api/backend/tutor/threads?*");
    await page.route("**/api/backend/tutor/threads?*", async (route) => {
      await historyGate;
      await route.fulfill({ json: { threads: [] } });
    });

    await page.goto("/home");
    await page.getByRole("button", { name: "Why this next?" }).click();
    const composer = page.getByRole("textbox", { name: "Message Luna" });
    await expect(composer).toBeDisabled();
    await expect(page.getByRole("button", { name: "Send" })).toBeDisabled();
    releaseHistory();
    await expect(composer).toBeEnabled();
  });

  test("refreshes an expired Luna plan context without auto-sending the saved draft", async ({ page }) => {
    let planRequests = 0;
    let messageRequests = 0;
    await page.unroute("**/api/backend/adaptive/plan");
    await page.route("**/api/backend/adaptive/plan", (route) => {
      planRequests += 1;
      return route.fulfill({ json: {
        ...adaptivePlanFixture,
        coachContext: {
          ...adaptivePlanFixture.coachContext,
          contextId: `apc1.dashboard-refresh-${planRequests}`,
        },
      } });
    });
    await page.route("**/api/backend/tutor/message", (route) => {
      messageRequests += 1;
      return route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({ detail: { code: "adaptive_plan_context_expired", message: "Refresh the plan." } }),
      });
    });

    await page.goto("/home");
    const question = "Why is this my next step?";
    await page.getByRole("button", { name: "Why this next?" }).click();
    const composer = page.getByRole("textbox", { name: "Message Luna" });
    await expect(composer).toBeEnabled();
    await page.getByRole("button", { name: "Send" }).click();
    await expect.poll(() => planRequests).toBe(2);
    await expect(composer).toBeEnabled();
    await expect(composer).toHaveValue(question);
    expect(messageRequests).toBe(1);
  });

  test("activity and competency detail panels have no detectable A/AA violations and retain state", async ({ page }) => {
    await page.goto("/home?panel=activity");
    await expect(page.locator("#home-panel-activity")).toBeVisible();
    await expectNoWcagViolations(page);

    await page.getByRole("tab", { name: "Progress" }).click();
    const search = page.getByRole("searchbox", { name: "Search skills" });
    await search.fill("atrial");
    await expectNoWcagViolations(page);

    await page.getByRole("tab", { name: "History" }).click();
    await page.getByRole("tab", { name: "Progress" }).click();
    await expect(search).toHaveValue("atrial");
  });

  test("keeps the dashboard usable at 320px without horizontal overflow", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 760 });
    await page.goto("/home");
    await expect(page.getByRole("heading", { name: "Welcome back, Alex." })).toBeVisible();
    const geometry = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      scroll: document.documentElement.scrollWidth,
      primaryWidth: document.querySelector<HTMLElement>('a.button.primary')?.getBoundingClientRect().width ?? 0,
    }));
    expect(geometry.scroll).toBeLessThanOrEqual(geometry.viewport + 1);
    expect(geometry.primaryWidth).toBeGreaterThan(200);
  });
});
