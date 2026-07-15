import { test, expect } from "@playwright/test";
import { collectConsoleErrors } from "./helpers";

const profileFixture = {
  learnerId: "demo",
  displayName: "Demo learner",
  attemptCount: 7,
  mastery: [],
  subskillMastery: [
    {
      concept: "atrial_fibrillation",
      subskill: "recognize",
      independentMastery: 0.62,
      independentAttempts: 3,
      attempts: 4,
      isDue: true,
    },
    {
      concept: "axis_normal",
      subskill: "discriminate",
      independentMastery: 0,
      independentAttempts: 0,
      attempts: 2,
      isDue: false,
    },
  ],
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
    independentAttempts: 3,
    dueCompetencies: 1,
    overdueCompetencies: 0,
    highConfidenceMisses: 0,
    eligibleConcepts: 12,
    baselineNeeded: false,
  },
  primary: {
    objectiveId: "axis_normal",
    label: "Normal axis",
    domain: "axis",
    caseConcept: "axis_normal",
    eligibleDistinct: 20,
    subskill: "discriminate",
    state: "developing",
    attempts: 2,
    independentAttempts: 1,
    independentMastery: 0.5,
    highConfidenceWrong: 0,
    isDue: true,
    dueState: "due",
    overdueDays: 0,
    nextDueAt: "2026-07-14T10:00:00Z",
    stabilityDays: 2,
    distinctSuccessfulEcgs: 1,
    distinctModes: 1,
    lapses: 0,
    reason: "The saved scheduler marked axis discrimination as due for retrieval.",
  },
  priorities: [],
  stages: [
    {
      order: 1,
      mode: "train",
      title: "Compare normal and deviated axes",
      purpose: "Discriminate axis patterns on a fresh set of real ECGs.",
      href: "/train?concept=axis_normal&subskill=discriminate",
      suggestedLength: 4,
      receiptConcept: "axis_normal",
      receiptSubskill: "discriminate",
      evidenceKind: "independent_transfer",
    },
  ],
  integration: null,
  clinicalApplication: null,
  explanation: "The verified scheduler selected the next executable practice stage.",
};

const noResumeFixture = {
  version: "learning-resume-v1",
  generatedAt: "2026-07-14T12:00:00Z",
  primary: null,
  additional: [],
};

const resumeFixture = {
  version: "learning-resume-v1",
  generatedAt: "2026-07-14T12:00:00Z",
  primary: {
    mode: "rapid",
    phase: "deadline",
    completed: 1,
    total: 5,
    updatedAt: "2026-07-14T09:00:00Z",
    destination: { kind: "rapid" },
  },
  additional: [
    {
      mode: "clinical",
      phase: "feedback",
      completed: 2,
      total: 5,
      updatedAt: "2026-07-14T11:00:00Z",
      destination: { kind: "clinical" },
    },
    {
      mode: "training",
      phase: "in_progress",
      completed: 3,
      total: 10,
      updatedAt: "2026-07-14T10:00:00Z",
      destination: { kind: "training" },
    },
    {
      mode: "guided",
      phase: "in_progress",
      completed: 1,
      total: 15,
      updatedAt: "2026-07-14T08:00:00Z",
      destination: { kind: "guided", moduleId: "leads-vectors", sceneId: "M02.S2" },
    },
  ],
};

test.describe("dashboard", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/backend/auth/me", (route) => route.fulfill({
      json: {
        authenticated: true,
        user: {
          userId: "u_dashboard_test",
          username: "dashboard_test",
          displayName: "Dashboard learner",
          accountStatus: "verified",
          emailVerified: true,
        },
      },
    }));
    await page.route("**/api/backend/learning/resume", (route) => route.fulfill({ json: noResumeFixture }));
  });

  test("presents the four-mode product and routes into each mode", async ({ page }) => {
    const errors = collectConsoleErrors(page);

    await page.goto("/dashboard");

    await expect(page.getByRole("heading", { name: "Build a read you can trust." })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Choose the kind of work you need." })).toBeVisible();

    const modeLinks = [
      { name: /Open guided learning/, href: "/learn" },
      { name: /Open focused practice/, href: "/train" },
      { name: /Start rapid practice/, href: "/rapid" },
      { name: /Open clinical cases/, href: "/practice" },
    ];
    for (const mode of modeLinks) {
      await expect(page.getByRole("link", { name: mode.name })).toHaveAttribute("href", mode.href);
    }

    const primary = page.getByRole("navigation", { name: "Primary navigation" });
    await expect(primary.getByRole("link", { name: /Guided learning/ })).toBeVisible();
    await expect(primary.getByRole("link", { name: /Focused practice/ })).toBeVisible();
    await expect(primary.getByRole("link", { name: /Rapid practice/ })).toBeVisible();
    await expect(primary.getByRole("link", { name: /Clinical cases/ })).toBeVisible();

    await page.getByRole("link", { name: /Open focused practice/ }).click();
    await expect(page).toHaveURL(/\/train(?:\?|$)/);
    await expect(page.getByRole("heading", { name: "Train one visual skill until it sticks" })).toBeVisible({ timeout: 30_000 });

    // Give late async logs a moment to flush, then assert a clean console.
    await page.waitForTimeout(500);
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("uses the server-owned primary runnable stage and rationale", async ({ page }) => {
    await page.route("**/api/backend/learners/demo", (route) => route.fulfill({ json: profileFixture }));
    await page.route("**/api/backend/adaptive/plan", (route) => route.fulfill({ json: adaptivePlanFixture }));

    await page.goto("/dashboard");

    await expect(page.getByRole("heading", { name: adaptivePlanFixture.stages[0].title })).toBeVisible();
    await expect(page.getByText(adaptivePlanFixture.stages[0].purpose, { exact: true })).toBeVisible();
    await expect(page.getByText(`Why now: ${adaptivePlanFixture.primary.reason}`, { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Start recommended practice" })).toHaveAttribute(
      "href",
      adaptivePlanFixture.stages[0].href,
    );
    await expect(page.getByText(/Strengthen atrial fibrillation/i)).toHaveCount(0);
  });

  test("continues the authoritative cross-mode session before showing the adaptive next step", async ({ page }) => {
    await page.unroute("**/api/backend/learning/resume");
    await page.route("**/api/backend/learning/resume", (route) => route.fulfill({ json: resumeFixture }));
    await page.route("**/api/backend/learners/demo", (route) => route.fulfill({ json: profileFixture }));
    await page.route("**/api/backend/adaptive/plan", (route) => route.fulfill({ json: adaptivePlanFixture }));

    await page.goto("/dashboard");

    await expect(page.getByRole("heading", { name: "Continue Rapid practice" })).toBeVisible();
    await expect(page.getByText("Timed ECG needs attention", { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Continue Rapid practice" })).toHaveAttribute("href", "/rapid");
    await expect(page.getByRole("link", { name: /After you finish.*Compare normal and deviated axes/ })).toHaveAttribute(
      "href",
      adaptivePlanFixture.stages[0].href,
    );

    const other = page.getByText("Other open sessions", { exact: true }).locator("..").locator("..");
    await expect(other.getByRole("link", { name: "Continue Clinical cases" })).toHaveAttribute("href", "/practice");
    await expect(other.getByRole("link", { name: "Continue Focused practice" })).toHaveAttribute("href", "/train");
    await expect(other.getByRole("link", { name: "Continue Guided learning" })).toHaveAttribute(
      "href",
      "/learn/leads-vectors?scene=M02.S2",
    );
    await expect(page.getByRole("link", { name: "Continue Foundations" })).toHaveCount(0);
    await expect(page.getByText("Foundations · The systematic sweep", { exact: true })).toHaveCount(0);
  });

  test("keeps the follow-on recommendation readable at 320px", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 780 });
    await page.unroute("**/api/backend/learning/resume");
    await page.route("**/api/backend/learning/resume", (route) => route.fulfill({ json: resumeFixture }));
    await page.route("**/api/backend/learners/demo", (route) => route.fulfill({ json: profileFixture }));
    await page.route("**/api/backend/adaptive/plan", (route) => route.fulfill({ json: adaptivePlanFixture }));

    await page.goto("/dashboard");
    const followOn = page.getByRole("link", { name: /After you finish.*Compare normal and deviated axes/ });
    await expect(followOn).toBeVisible();
    const geometry = await followOn.evaluate((link) => {
      const title = link.querySelector("strong") as HTMLElement;
      const linkRect = link.getBoundingClientRect();
      return {
        linkWidth: linkRect.width,
        titleWidth: title.getBoundingClientRect().width,
        titleScrollWidth: title.scrollWidth,
        whiteSpace: getComputedStyle(title).whiteSpace,
        documentOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      };
    });
    expect(geometry.linkWidth).toBeGreaterThan(170);
    expect(geometry.titleWidth).toBeGreaterThan(150);
    expect(geometry.titleScrollWidth).toBeLessThanOrEqual(geometry.titleWidth + 1);
    expect(geometry.whiteSpace).not.toBe("nowrap");
    expect(geometry.documentOverflow).toBeLessThanOrEqual(1);
  });

  test("rejects an unallowlisted resume destination instead of navigating stored data", async ({ page }) => {
    await page.unroute("**/api/backend/learning/resume");
    await page.route("**/api/backend/learning/resume", (route) => route.fulfill({
      json: {
        version: "learning-resume-v1",
        generatedAt: "2026-07-14T12:00:00Z",
        primary: {
          mode: "guided",
          phase: "in_progress",
          completed: 1,
          total: 15,
          updatedAt: "2026-07-14T11:00:00Z",
          destination: { kind: "guided", moduleId: "https:evil.example", sceneId: "redirect" },
        },
        additional: [{
          mode: "training",
          phase: "in_progress",
          completed: 1,
          total: 10,
          updatedAt: "2026-07-14T10:00:00Z",
          destination: { kind: "training", href: "https://evil.example" },
        }],
      },
    }));
    await page.route("**/api/backend/learners/demo", (route) => route.fulfill({ json: profileFixture }));
    await page.route("**/api/backend/adaptive/plan", (route) => route.fulfill({ json: adaptivePlanFixture }));

    await page.goto("/dashboard");

    await expect(page.getByRole("heading", { name: adaptivePlanFixture.stages[0].title })).toBeVisible();
    await expect(page.getByRole("link", { name: "Start recommended practice" })).toHaveAttribute(
      "href",
      adaptivePlanFixture.stages[0].href,
    );
    await expect(page.locator('a[href*="evil.example"]')).toHaveCount(0);
    await expect(page.getByText("Other open sessions", { exact: true })).toHaveCount(0);
  });

  test("shows a clearly unpersonalized fallback when the adaptive plan is unavailable", async ({ page }) => {
    await page.route("**/api/backend/learners/demo", (route) => route.fulfill({ json: profileFixture }));
    await page.route("**/api/backend/adaptive/plan", (route) => route.fulfill({ status: 503, body: "unavailable" }));

    await page.goto("/dashboard");

    await expect(page.getByText("General practice · not personalized", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Try an untimed rapid ECG." })).toBeVisible();
    await expect(
      page.getByText("This is a general practice option, not a recommendation based on your progress.", { exact: true }),
    ).toBeVisible();
    await expect(page.getByRole("link", { name: "Start general practice" })).toHaveAttribute(
      "href",
      "/rapid?pace=untimed&suggestedLength=5",
    );
    await expect(page.locator("a.button.primary")).toHaveCount(1);
  });

  test("labels a valid empty-history plan as a baseline rather than a planner failure", async ({ page }) => {
    await page.route("**/api/backend/learners/demo", (route) => route.fulfill({ json: profileFixture }));
    await page.route("**/api/backend/adaptive/plan", (route) => route.fulfill({
      json: {
        ...adaptivePlanFixture,
        basis: { ...adaptivePlanFixture.basis, baselineNeeded: true, independentAttempts: 0 },
        primary: null,
        stages: [],
        guidedRemediation: null,
        explanation: "An independent baseline is needed.",
      },
    }));

    await page.goto("/dashboard");

    await expect(page.getByText("Baseline · not yet personalized", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Start with an untimed baseline." })).toBeVisible();
    await expect(page.getByRole("link", { name: "Start baseline" })).toHaveAttribute(
      "href",
      "/rapid?pace=untimed&suggestedLength=10",
    );
    await expect(page.getByText(/temporarily unavailable/i)).toHaveCount(0);
  });

  test("does not expose a recommendation destination while the adaptive plan is loading", async ({ page }) => {
    let releasePlan!: () => void;
    const planGate = new Promise<void>((resolve) => { releasePlan = resolve; });
    await page.route("**/api/backend/learners/demo", (route) => route.fulfill({ json: profileFixture }));
    await page.route("**/api/backend/adaptive/plan", async (route) => {
      await planGate;
      await route.fulfill({ json: adaptivePlanFixture });
    });

    await page.goto("/dashboard");
    const loadingAction = page.getByRole("button", { name: "Preparing next step" });
    await expect(loadingAction).toBeDisabled();
    await expect(page.getByRole("link", { name: /Start recommended practice|Start general practice/ })).toHaveCount(0);

    releasePlan();
    await expect(loadingAction).toHaveCount(0, { timeout: 30_000 });
    await expect(page.getByRole("link", { name: "Start recommended practice" })).toBeVisible();
  });

  test("uses honest names for the progress evidence available on the dashboard", async ({ page }) => {
    await page.route("**/api/backend/learners/demo", (route) => route.fulfill({ json: profileFixture }));
    await page.route("**/api/backend/adaptive/plan", (route) => route.fulfill({ json: adaptivePlanFixture }));

    await page.goto("/dashboard");

    const snapshot = page.getByLabel("Learning snapshot");
    await expect(snapshot.locator("div").filter({ hasText: "Independent estimate" })).toContainText("62%");
    await expect(snapshot.locator("div").filter({ hasText: "Independent skills" })).toContainText("1");
    await expect(snapshot.locator("div").filter({ hasText: "Skills due" })).toContainText("1");
    await expect(page.getByText("Recorded attempts", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("link", { name: /View progress/ })).toHaveCount(1);
    await expect(page.getByText("Completed reads", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Confidence rechecks", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Progress follows you across every mode.", { exact: true })).toHaveCount(0);
  });

  test("keeps authenticated phone navigation readable without collisions", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 700 });
    await page.goto("/dashboard");
    await expect(page.getByRole("link", { name: "Account security" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();

    const geometry = await page.evaluate(() => {
      const elements = [...document.querySelectorAll<HTMLElement>(
        ".side-nav .brand, .side-nav .nav-link, .side-nav .nav-account-action",
      )].filter((element) => {
        const rect = element.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
      });
      const rects = elements.map((element) => {
        const rect = element.getBoundingClientRect();
        return { label: element.getAttribute("aria-label") ?? element.textContent?.trim() ?? "", left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom };
      });
      const collisions: string[] = [];
      for (let left = 0; left < rects.length; left += 1) {
        for (let right = left + 1; right < rects.length; right += 1) {
          const a = rects[left];
          const b = rects[right];
          if (a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top) {
            collisions.push(`${a.label} / ${b.label}`);
          }
        }
      }
      return {
        documentFits: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
        allInsideViewport: rects.every((rect) => rect.left >= 0 && rect.right <= window.innerWidth),
        collisions,
      };
    });
    expect(geometry).toEqual({ documentFits: true, allInsideViewport: true, collisions: [] });
  });
});
