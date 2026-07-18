import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";
import { collectConsoleErrors } from "./helpers";

function localDateKey(offset = 0) {
  const date = new Date();
  date.setHours(12, 0, 0, 0);
  date.setDate(date.getDate() + offset);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

const planFixture = {
  learnerId: "demo",
  coachContext: { contextId: "apc1.calendar", version: "adaptive-plan-coach-v1", expiresAt: "2099-01-01T00:00:00Z" },
  generatedAt: "2026-07-16T12:00:00Z",
  plannerKind: "verified_competency_scheduler",
  generativeTutorUsed: false,
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
  priorities: [],
  stages: [],
  guidedRemediation: null,
  integration: null,
  clinicalApplication: null,
  calendarAction: {
    version: "calendar-plan-action-v1",
    actionKey: "calendar-action-af-baseline",
    relationship: "starting_check",
    title: "Check atrial fibrillation · independent recognition",
    mode: "rapid",
    objectiveId: "atrial_fibrillation",
    objectiveLabel: "Atrial fibrillation",
    subskill: "recognize",
    caseConcept: "atrial_fibrillation",
    launchHref: "/rapid?focus=atrial_fibrillation&receiptConcept=atrial_fibrillation&subskill=recognize&suggestedLength=5&pace=untimed&returnTo=%2Fhome%3Fpanel%3Dplan",
    suggestedDurationMinutes: 30,
  },
  explanation: "A starting check is needed.",
};

type CalendarItem = {
  itemId: string;
  source: "manual" | "retention_review" | "study_plan";
  title: string;
  notes: string;
  scheduledDate: string;
  startMinute: number | null;
  durationMinutes: number | null;
  status: "scheduled" | "completed";
  completionSource: "manual" | "verified_practice" | null;
  completedAt: string | null;
  competency: null | {
    objectiveId: string;
    objectiveLabel: string;
    subskill: string;
    caseConcept: string;
    mode: "train" | "rapid";
    sourceDueAt: string;
    currentDueAt: string | null;
    sourceCurrent: boolean;
    launchHref: string | null;
  };
  activity: null | {
    kind: "manual_mode" | "retention_review" | "study_plan";
    mode: "guided" | "train" | "rapid" | "clinical";
    objectiveId: string | null;
    objectiveLabel: string | null;
    subskill: string | null;
    caseConcept: string | null;
    sourceCurrent: boolean | null;
    launchHref: string | null;
  };
  revision: number;
  createdAt: string;
  updatedAt: string;
};

async function routeCalendarHome(page: Page, options: { reviewCount?: number; failCalendar?: boolean } = {}) {
  const today = localDateKey();
  const reviewCount = options.reviewCount ?? 1;
  let calendarRequests = 0;
  let sequence = 0;
  let settings = { timeZone: "America/New_York", weekStartsOn: 1 as 0 | 1, saved: true, updatedAt: "2026-07-16T12:00:00Z" };
  let items: CalendarItem[] = [];
  const mutationBodies: Array<{ method: string; path: string; body: Record<string, unknown> | null }> = [];
  const failedResponses: string[] = [];
  page.on("response", (response) => {
    if (response.status() >= 400) failedResponses.push(`${response.status()} ${response.url()}`);
  });

  await page.route("**/api/backend/auth/me", (route) => route.fulfill({
    json: { authenticated: true, user: { userId: "u_calendar", username: "calendar", displayName: "Calendar Learner", accountStatus: "verified", emailVerified: true } },
  }));
  await page.route("**/api/backend/adaptive/plan", (route) => route.fulfill({ json: planFixture }));
  await page.route("**/api/backend/learning/resume", (route) => route.fulfill({ json: { version: "learning-resume-v1", generatedAt: "2026-07-16T12:00:00Z", primary: null, additional: [] } }));
  await page.route("**/api/backend/learning/preferences", (route) => route.fulfill({ json: {
    trainingStage: "not_set",
    primaryGoal: "build_fundamentals",
    defaultSessionLength: 10,
    rapidPace: "untimed",
    guidanceLevel: "balanced",
    reduceMotion: false,
    largeControls: false,
    updatedAt: null,
  } }));
  await page.route("**/api/backend/learners/demo/competencies", (route) => route.fulfill({ json: {
    learnerId: "demo",
    registryVersion: "calendar-test",
    calendarProjection: { timeZone: "America/New_York", today, reviewDays: [] },
    objectives: [],
  } }));
  await page.route("**/api/backend/learning/sessions?*", (route) => route.fulfill({ json: { version: "learning-sessions-v1", items: [], hasMore: false, nextOffset: null, totalSavedItems: 0 } }));
  await page.route("**/api/backend/tutor/threads?*", (route) => route.fulfill({ json: { threads: [] } }));

  await page.route("**/api/backend/learning/calendar**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api\/backend/, "");
    const method = request.method();
    const body = method === "GET" || method === "DELETE" ? null : request.postDataJSON() as Record<string, unknown>;
    if (method !== "GET") mutationBodies.push({ method, path, body });

    if (method === "GET" && path === "/learning/calendar") {
      calendarRequests += 1;
      if (options.failCalendar) return route.fulfill({ status: 503, json: { detail: "temporarily unavailable" } });
      const startDate = url.searchParams.get("startDate")!;
      const endDate = url.searchParams.get("endDate")!;
      return route.fulfill({
        json: {
          version: "study-calendar-v1",
          generatedAt: "2026-07-16T12:00:00Z",
          range: { startDate, endDate },
          settings,
          today,
          items: items.filter((item) => item.scheduledDate >= startDate && item.scheduledDate <= endDate),
          reviewDays: today >= startDate && today <= endDate ? [{
            date: today,
            total: reviewCount,
            overdue: reviewCount,
            items: [
              ["atrial_fibrillation", "Atrial fibrillation", "discriminate"],
              ["anterior_mi", "Anterior MI", "recognize"],
              ["qt_interval", "QT Interval", "measure"],
              ["sinus_rhythm", "Sinus rhythm", "recognize"],
              ["premature_ventricular_complex", "Premature ventricular complex", "discriminate"],
            ].slice(0, reviewCount).map(([objectiveId, objectiveLabel, subskill], index) => ({
              key: `${objectiveId}:${subskill}`,
              objectiveId,
              objectiveLabel,
              subskill,
              nextDueAt: `${today}T10:00:00Z`,
              dueState: "overdue",
              overdueDays: 2,
              plannedFor: items.find((item) => item.competency?.objectiveId === objectiveId)?.scheduledDate ?? null,
              scheduledItemId: items.find((item) => item.competency?.objectiveId === objectiveId)?.itemId ?? null,
              launchHref: `/train?concept=${objectiveId}&subskill=${subskill}`,
              planPriority: index + 1,
            })),
          }] : [],
        },
      });
    }

    if (method === "PUT" && path === "/learning/calendar/settings") {
      settings = { ...settings, timeZone: String(body!.timeZone), weekStartsOn: Number(body!.weekStartsOn) as 0 | 1, updatedAt: new Date().toISOString() };
      return route.fulfill({ json: settings });
    }

    if (method === "POST" && path === "/learning/calendar/items") {
      sequence += 1;
      const now = new Date().toISOString();
      const item: CalendarItem = {
        itemId: `manual-${sequence}`,
        source: "manual",
        title: String(body!.title),
        notes: String(body!.notes ?? ""),
        scheduledDate: String(body!.scheduledDate),
        startMinute: body!.startMinute === null || body!.startMinute === undefined ? null : Number(body!.startMinute),
        durationMinutes: body!.durationMinutes === null || body!.durationMinutes === undefined ? null : Number(body!.durationMinutes),
        status: "scheduled",
        completionSource: null,
        completedAt: null,
        competency: null,
        activity: body!.mode ? {
          kind: "manual_mode",
          mode: String(body!.mode) as "guided" | "train" | "rapid" | "clinical",
          objectiveId: null,
          objectiveLabel: null,
          subskill: null,
          caseConcept: null,
          sourceCurrent: null,
          launchHref: body!.mode === "guided" ? "/learn" : `/${String(body!.mode)}`,
        } : null,
        revision: 1,
        createdAt: now,
        updatedAt: now,
      };
      items.push(item);
      return route.fulfill({ status: 201, json: item });
    }

    if (method === "POST" && path === "/learning/calendar/items/from-competency") {
      sequence += 1;
      const now = new Date().toISOString();
      const item: CalendarItem = {
        itemId: `review-${sequence}`,
        source: "retention_review",
        title: "Review atrial fibrillation discrimination",
        notes: String(body!.notes ?? ""),
        scheduledDate: String(body!.scheduledDate),
        startMinute: body!.startMinute === null || body!.startMinute === undefined ? null : Number(body!.startMinute),
        durationMinutes: body!.durationMinutes === null || body!.durationMinutes === undefined ? null : Number(body!.durationMinutes),
        status: "scheduled",
        completionSource: null,
        completedAt: null,
        competency: {
          objectiveId: "atrial_fibrillation",
          objectiveLabel: "Atrial fibrillation",
          subskill: "discriminate",
          caseConcept: "atrial_fibrillation",
          mode: "train",
          sourceDueAt: String(body!.expectedNextDueAt),
          currentDueAt: String(body!.expectedNextDueAt),
          sourceCurrent: true,
          launchHref: "/train?concept=atrial_fibrillation&subskill=discriminate",
        },
        activity: {
          kind: "retention_review",
          mode: "train",
          objectiveId: "atrial_fibrillation",
          objectiveLabel: "Atrial fibrillation",
          subskill: "discriminate",
          caseConcept: "atrial_fibrillation",
          sourceCurrent: true,
          launchHref: "/train?concept=atrial_fibrillation&subskill=discriminate",
        },
        revision: 1,
        createdAt: now,
        updatedAt: now,
      };
      items.push(item);
      return route.fulfill({ status: 201, json: item });
    }

    if (method === "POST" && path === "/learning/calendar/items/from-plan") {
      sequence += 1;
      const now = new Date().toISOString();
      const launchHref = `/rapid?focus=atrial_fibrillation&receiptConcept=atrial_fibrillation&subskill=recognize&suggestedLength=5&pace=untimed&returnTo=${encodeURIComponent(`/home?panel=calendar&date=${String(body!.scheduledDate)}`)}`;
      const item: CalendarItem = {
        itemId: `plan-${sequence}`,
        source: "study_plan",
        title: planFixture.calendarAction.title,
        notes: String(body!.notes ?? ""),
        scheduledDate: String(body!.scheduledDate),
        startMinute: body!.startMinute === null || body!.startMinute === undefined ? null : Number(body!.startMinute),
        durationMinutes: body!.durationMinutes === null || body!.durationMinutes === undefined ? 30 : Number(body!.durationMinutes),
        status: "scheduled",
        completionSource: null,
        completedAt: null,
        competency: null,
        activity: {
          kind: "study_plan",
          mode: "rapid",
          objectiveId: "atrial_fibrillation",
          objectiveLabel: "Atrial fibrillation",
          subskill: "recognize",
          caseConcept: "atrial_fibrillation",
          sourceCurrent: true,
          launchHref,
        },
        revision: 1,
        createdAt: now,
        updatedAt: now,
      };
      items.push(item);
      return route.fulfill({ status: 201, json: item });
    }

    const itemId = path.match(/^\/learning\/calendar\/items\/([^/]+)/)?.[1];
    const index = items.findIndex((item) => item.itemId === itemId);
    if (!itemId || index < 0) return route.fulfill({ status: 404, json: { detail: "not found" } });
    const existing = items[index];

    if (method === "PATCH") {
      const updated: CalendarItem = {
        ...existing,
        title: body!.title === undefined ? existing.title : String(body!.title),
        notes: body!.notes === undefined ? existing.notes : String(body!.notes),
        scheduledDate: body!.scheduledDate === undefined ? existing.scheduledDate : String(body!.scheduledDate),
        startMinute: body!.startMinute === undefined ? existing.startMinute : body!.startMinute === null ? null : Number(body!.startMinute),
        durationMinutes: body!.durationMinutes === undefined ? existing.durationMinutes : body!.durationMinutes === null ? null : Number(body!.durationMinutes),
        revision: existing.revision + 1,
        updatedAt: new Date().toISOString(),
      };
      items[index] = updated;
      return route.fulfill({ json: updated });
    }

    if (path.endsWith("/completion") && method === "PUT") {
      const updated = { ...existing, status: "completed" as const, completionSource: "manual" as const, completedAt: new Date().toISOString(), revision: existing.revision + 1 };
      items[index] = updated;
      return route.fulfill({ json: updated });
    }

    if (path.endsWith("/completion") && method === "DELETE") {
      const updated = { ...existing, status: "scheduled" as const, completionSource: null, completedAt: null, revision: existing.revision + 1 };
      items[index] = updated;
      return route.fulfill({ json: updated });
    }

    if (method === "DELETE") {
      items = items.filter((item) => item.itemId !== itemId);
      return route.fulfill({ json: { deleted: true, itemId } });
    }

    return route.fulfill({ status: 405, json: { detail: "unsupported" } });
  });

  return {
    get calendarRequests() { return calendarRequests; },
    get mutationBodies() { return mutationBodies; },
    get failedResponses() { return failedResponses; },
  };
}

test.describe("in-app study calendar", () => {
  test("loads only when opened and supports keyboard date navigation", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    const state = await routeCalendarHome(page);
    await page.goto("/home");
    await expect(page.getByRole("heading", { name: "Welcome back, Calendar." })).toBeVisible();
    expect(state.calendarRequests).toBe(0);

    await page.getByRole("button", { name: "Open schedule" }).click();
    await expect(page).toHaveURL(/\/home\?panel=calendar&date=\d{4}-\d{2}-\d{2}$/);
    await expect(page.getByRole("heading", { name: "Plan your week" })).toBeVisible();
    await expect.poll(() => state.calendarRequests).toBeGreaterThan(0);

    const selected = page.locator('[data-calendar-day="true"][aria-pressed="true"]');
    await expect(selected).toHaveCount(1);
    await selected.focus();
    await page.keyboard.press("ArrowRight");
    await expect(page.locator('[data-calendar-day="true"][aria-pressed="true"]')).toBeFocused();
    const accessibility = await new AxeBuilder({ page })
      .include("#home-panel-calendar")
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(
      accessibility.violations.map((violation) => violation.id),
      JSON.stringify(accessibility.violations.map((violation) => ({
        id: violation.id,
        nodes: violation.nodes.map((node) => ({ target: node.target, summary: node.failureSummary })),
      })), null, 2),
    ).toEqual([]);
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}\nFailed responses:\n${state.failedResponses.join("\n")}`).toEqual([]);
  });

  test("does not present an empty calendar as truth when the calendar request fails", async ({ page }) => {
    await routeCalendarHome(page, { failCalendar: true });
    await page.goto("/home?panel=calendar");
    await expect(page.getByRole("alert").filter({ hasText: "Schedule unavailable" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Add study time" })).toBeDisabled();
    await expect(page.getByText("Nothing scheduled.", { exact: true })).toHaveCount(0);
    await expect(page.getByText("No suggested review for this day.", { exact: true })).toHaveCount(0);
  });

  test("adds, edits, reschedules, completes, reopens, and deletes a manual block", async ({ page }) => {
    const state = await routeCalendarHome(page);
    const tomorrow = localDateKey(1);
    await page.goto("/home?panel=calendar");
    await expect(page.getByRole("heading", { name: "Plan your week" })).toBeVisible();

    const addStudyBlock = page.getByRole("button", { name: "Add study time" });
    await addStudyBlock.click();
    await expect(page.getByLabel("Title")).toBeFocused();
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(addStudyBlock).toBeFocused();
    await addStudyBlock.click();
    await page.getByLabel("Title").fill("Focused rhythm review");
    await page.getByLabel("Notes optional").fill("Compare AF with flutter.");
    await page.getByLabel("Learning mode optional").selectOption("train");
    await page.getByLabel("Start optional").fill("18:30");
    await page.getByLabel("Minutes").fill("45");
    await page.getByRole("button", { name: "Add to schedule" }).click();
    await expect(page.getByText("Focused rhythm review", { exact: true })).toBeVisible();
    expect(state.mutationBodies.some((entry) => entry.method === "POST" && entry.path === "/learning/calendar/items" && entry.body?.startMinute === 1110 && entry.body?.mode === "train")).toBe(true);

    let card = page.getByText("Focused rhythm review", { exact: true }).locator("xpath=ancestor::article");
    await card.getByRole("button", { name: "Edit / reschedule" }).click();
    const editor = page.getByText("Edit study time", { exact: true }).locator("xpath=ancestor::form");
    await editor.getByLabel("Title").fill("Rhythm contrast review");
    await editor.getByRole("textbox", { name: "Date" }).fill(tomorrow);
    await editor.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByText("Rhythm contrast review", { exact: true })).toBeVisible();
    card = page.getByText("Rhythm contrast review", { exact: true }).locator("xpath=ancestor::article");

    await card.getByRole("button", { name: "Mark done" }).click();
    await expect(card.getByText("Done", { exact: true })).toBeVisible();
    await card.getByRole("button", { name: "Reopen" }).click();
    await expect(card.getByText("Scheduled", { exact: true })).toBeVisible();

    await card.getByRole("button", { name: "Delete" }).click();
    await card.getByRole("button", { name: "No" }).click();
    await expect(card.getByRole("button", { name: "Delete" })).toBeFocused();
    await card.getByRole("button", { name: "Delete" }).click();
    await card.getByRole("button", { name: "Yes" }).click();
    await expect(page.getByText("Rhythm contrast review", { exact: true })).toHaveCount(0);
    expect(state.mutationBodies.some((entry) => entry.method === "PATCH")).toBe(true);
    expect(state.mutationBodies.filter((entry) => entry.path.endsWith("/completion")).map((entry) => entry.method)).toEqual(["PUT", "DELETE"]);
  });

  test("turns a due competency into a bounded in-app review block", async ({ page }) => {
    const state = await routeCalendarHome(page);
    await page.goto("/home?panel=calendar");
    await expect(page.getByText("Atrial fibrillation", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Add 30 min" }).click();
    await expect(page.getByText("Review atrial fibrillation discrimination", { exact: true })).toBeVisible();
    await expect(page.getByText("How this schedule works", { exact: true })).toBeVisible();
    expect(state.mutationBodies.some((entry) => entry.path === "/learning/calendar/items/from-competency" && entry.body?.durationMinutes === 30)).toBe(true);
    const card = page.getByText("Review atrial fibrillation discrimination", { exact: true }).locator("xpath=ancestor::article");
    await card.getByRole("button", { name: "Mark done" }).click();
    await expect(card.getByText(/Marked done on your schedule/i)).toBeVisible();
  });

  test("keeps every due skill available while progressively revealing lower priorities", async ({ page }) => {
    await routeCalendarHome(page, { reviewCount: 5 });
    await page.goto("/home?panel=calendar");
    const reviews = page.getByRole("region", { name: "Suggested review" });
    await expect(reviews.getByText("Atrial fibrillation", { exact: true })).toBeVisible();
    await expect(reviews.getByText("QT Interval", { exact: true })).toBeVisible();
    await expect(reviews.getByText("Sinus rhythm", { exact: true })).toBeHidden();
    await reviews.getByText("Show 2 more due skills", { exact: true }).click();
    await expect(reviews.getByText("Sinus rhythm", { exact: true })).toBeVisible();
    await expect(reviews.getByText("Premature ventricular complex", { exact: true })).toBeVisible();
  });

  test("requires confirmation before scheduling the server-authored study plan step", async ({ page }) => {
    const state = await routeCalendarHome(page);
    await page.goto("/home?panel=plan");
    await page.getByRole("button", { name: "Add to my week" }).click();
    await expect(page).toHaveURL(/\/home\?panel=calendar&date=\d{4}-\d{2}-\d{2}$/);
    const editor = page.getByText("Add Luna's next step", { exact: true }).locator("xpath=ancestor::form");
    await expect(editor.getByText("Rapid practice · review before adding", { exact: true })).toBeVisible();
    await expect(page.getByText("Nothing scheduled.", { exact: true })).toBeVisible();
    expect(state.mutationBodies.some((entry) => entry.path === "/learning/calendar/items/from-plan")).toBe(false);
    await editor.getByRole("button", { name: "Confirm and add" }).click();
    const card = page.getByText(planFixture.calendarAction.title, { exact: true }).locator("xpath=ancestor::article");
    await expect(card.getByText(/Atrial fibrillation/)).toBeVisible();
    await expect(card.getByRole("link", { name: "Start rapid practice" })).toHaveAttribute("href", /returnTo=%2Fhome%3Fpanel%3Dcalendar%26date%3D\d{4}-\d{2}-\d{2}/);
    expect(state.mutationBodies.some((entry) => entry.path === "/learning/calendar/items/from-plan" && entry.body?.expectedActionKey === planFixture.calendarAction.actionKey)).toBe(true);
  });

  test("hands a coach conversation into the same confirm-before-save calendar flow", async ({ page }) => {
    const state = await routeCalendarHome(page);
    await page.goto("/home");
    const coachCard = page.getByRole("heading", { name: "Talk through your next step" }).locator("xpath=ancestor::aside");
    await coachCard.getByRole("button", { name: "Ask Luna about your plan" }).click();
    const coach = page.getByRole("dialog", { name: "Plan with Luna" });
    await expect(coach.getByText("Add this step to your week", { exact: true })).toBeVisible();
    await coach.getByRole("button", { name: "Choose a time" }).click();
    await expect(page).toHaveURL(/\/home\?panel=calendar&date=\d{4}-\d{2}-\d{2}$/);
    await expect(page.getByText("Add Luna's next step", { exact: true })).toBeVisible();
    expect(state.mutationBodies.some((entry) => entry.path === "/learning/calendar/items/from-plan")).toBe(false);
  });

  test("uses the compact date strip without horizontal page overflow on mobile", async ({ page }) => {
    await routeCalendarHome(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/home?panel=calendar");
    const tabs = page.getByRole("tablist", { name: "Learning dashboard sections" });
    await expect(tabs.getByRole("tab")).toHaveText(["Home", "History", "Progress", "Schedule", "My plan"]);
    const tabLayout = await tabs.evaluate((element) => {
      const bounds = element.getBoundingClientRect();
      const buttons = Array.from(element.querySelectorAll("button"));
      return {
        overflow: element.scrollWidth - element.clientWidth,
        allContained: buttons.every((button) => {
          const rect = button.getBoundingClientRect();
          return rect.left >= bounds.left - 1 && rect.right <= bounds.right + 1;
        }),
      };
    });
    expect(tabLayout).toEqual({ overflow: 0, allContained: true });

    const primaryNavigation = page.getByRole("navigation", { name: "Primary navigation" });
    const shellLayout = await primaryNavigation.evaluate((element) => {
      const bounds = element.getBoundingClientRect();
      const links = Array.from(element.querySelectorAll("a"));
      return {
        overflow: element.scrollWidth - element.clientWidth,
        allContained: links.every((link) => {
          const rect = link.getBoundingClientRect();
          return rect.left >= bounds.left - 1 && rect.right <= bounds.right + 1;
        }),
      };
    });
    expect(shellLayout).toEqual({ overflow: 0, allContained: true });
    await expect(page.getByRole("heading", { name: "Welcome back, Calendar." })).toBeVisible();
    await expect(page.getByRole("button", { name: "Plan with Luna" })).toBeVisible();
    await expect(page.getByLabel("Selected week")).toBeVisible();
    await expect(page.getByLabel(/calendar$/)).toBeHidden();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    const addButton = page.getByRole("button", { name: "Add study time" });
    const box = await addButton.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.height).toBeGreaterThanOrEqual(44);
  });
});
