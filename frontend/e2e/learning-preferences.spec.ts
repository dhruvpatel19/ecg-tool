import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const defaults = {
  trainingStage: "not_set",
  primaryGoal: "build_fundamentals",
  defaultSessionLength: 10,
  rapidPace: "untimed",
  guidanceLevel: "balanced",
  reduceMotion: false,
  largeControls: false,
  updatedAt: null as string | null,
};

test.describe("learning preferences", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/backend/auth/me", (route) => route.fulfill({
      json: {
        authenticated: true,
        user: {
          userId: "u_preferences",
          username: "preferences",
          displayName: "Preference Learner",
          accountStatus: "verified",
          emailVerified: true,
        },
      },
    }));
    await page.route("**/api/backend/auth/sessions", (route) => route.fulfill({ json: { sessions: [] } }));
    await page.route("**/api/backend/auth/guest-progress", (route) => route.fulfill({ json: { hasProgress: false, claimable: false } }));
  });

  test("persists strict choices and applies display preferences to the app shell", async ({ page }) => {
    let stored = { ...defaults };
    const writes: Array<Record<string, unknown>> = [];
    await page.route("**/api/backend/learning/preferences", async (route) => {
      if (route.request().method() === "PUT") {
        const update = route.request().postDataJSON() as Record<string, unknown>;
        writes.push(update);
        stored = { ...stored, ...update, updatedAt: "2026-07-14T13:00:00Z" };
      }
      await route.fulfill({ json: stored });
    });

    await page.goto("/account#learning-preferences");
    await expect(page.getByRole("heading", { name: "Shape your learning workspace" })).toBeVisible();
    await page.getByLabel("Where are you in training?").selectOption("core_clerkship");
    await page.getByLabel("What are you working toward?").selectOption("clinical_reading");
    await page.getByRole("radio", { name: "25 ECGs" }).press("Space");
    await page.getByRole("radio", { name: /Ward pace/ }).press("Space");
    await page.getByRole("radio", { name: /Step by step/ }).press("Space");
    await page.getByRole("checkbox", { name: /Reduce motion/ }).check();
    await page.getByRole("checkbox", { name: /Larger controls/ }).check();
    await page.getByRole("button", { name: "Save preferences" }).click();

    await expect(page.getByText("Preferences saved.")).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("data-reduce-motion", "true");
    await expect(page.locator("html")).toHaveAttribute("data-large-controls", "true");
    expect(writes).toEqual([{
      trainingStage: "core_clerkship",
      primaryGoal: "clinical_reading",
      defaultSessionLength: 25,
      rapidPace: "ward",
      guidanceLevel: "step_by_step",
      reduceMotion: true,
      largeControls: true,
    }]);

    // The client bridge reapplies saved presentation choices outside Account,
    // then the URL-addressable Account section hydrates the same record again.
    await page.goto("/");
    await expect(page.locator("html")).toHaveAttribute("data-reduce-motion", "true");
    await expect(page.locator("html")).toHaveAttribute("data-large-controls", "true");
    await page.goto("/account#learning-preferences");
    await expect(page.getByLabel("Where are you in training?")).toHaveValue("core_clerkship");
    await expect(page.getByLabel("What are you working toward?")).toHaveValue("clinical_reading");
    await expect(page.getByRole("radio", { name: "25 ECGs" })).toBeChecked();
    await expect(page.getByRole("checkbox", { name: /Larger controls/ })).toBeChecked();
    await expect(page.locator("html")).toHaveAttribute("data-large-controls", "true");
  });

  test("lives in Account with named groups and passes WCAG A/AA", async ({ page }) => {
    await page.route("**/api/backend/learning/preferences", (route) => route.fulfill({ json: defaults }));
    await page.goto("/account#learning-preferences");
    await expect(page).toHaveURL(/\/account#learning-preferences$/);
    await expect(page.getByText("Preferences are private to your account and follow you across devices.")).toBeVisible();
    await expect(page.getByRole("group", { name: "About your learning" })).toBeVisible();
    await expect(page.getByRole("group", { name: "Practice defaults" })).toBeVisible();
    await expect(page.getByRole("group", { name: "Guided lesson support" })).toBeVisible();
    await expect(page.getByRole("group", { name: "Display and interaction" })).toBeVisible();

    await expect(page.getByRole("tab", { name: "Preferences" })).toHaveCount(0);

    const axe = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(axe.violations.map((violation) => ({
      id: violation.id,
      targets: violation.nodes.map((node) => node.target),
    }))).toEqual([]);
  });

  test("keeps large controls usable without horizontal overflow at 320px", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 780 });
    await page.route("**/api/backend/learning/preferences", (route) => route.fulfill({
      json: { ...defaults, largeControls: true },
    }));
    await page.goto("/account#learning-preferences");
    await expect(page.locator("html")).toHaveAttribute("data-large-controls", "true");
    await expect(page.getByRole("button", { name: "Save preferences" })).toBeVisible();

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);

    const shortControls = await page.locator("button:visible, select:visible, label:has(input[type=checkbox]):visible").evaluateAll((controls) => (
      controls
        .map((control) => ({
          label: control.getAttribute("aria-label") || control.textContent || control.getAttribute("id") || control.tagName,
          height: control.getBoundingClientRect().height,
        }))
        .filter((control) => control.height < 47.5)
    ));
    expect(shortControls).toEqual([]);
  });

  test("coalesces the shell and active mode preference read", async ({ page }) => {
    let reads = 0;
    await page.route("**/api/backend/learning/preferences", async (route) => {
      if (route.request().method() === "GET") reads += 1;
      await new Promise((resolve) => setTimeout(resolve, 75));
      await route.fulfill({ json: { ...defaults, defaultSessionLength: 25 } });
    });

    await page.goto("/train");
    await expect(page.getByRole("heading", { name: "Train one visual skill until it sticks" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByLabel("Requested unique ECGs")).toHaveValue("25");
    expect(reads).toBe(1);
  });

  test("prefills only untouched Clinical length and preserves explicit or learner choices", async ({ page }) => {
    await page.route("**/api/backend/learning/preferences", (route) => route.fulfill({
      json: { ...defaults, defaultSessionLength: 25 },
    }));
    await page.route("**/api/backend/clinical/shift/active", (route) => route.fulfill({
      json: { session: null, state: "picker", current: null, grade: null, report: null },
    }));
    await page.route("**/api/backend/clinical/bank/coverage", (route) => route.fulfill({
      json: { coverage: {}, servingStatus: "harness_pass" },
    }));

    await page.goto("/practice");
    await expect(page.getByRole("button", { name: "10 patient cases" })).toHaveAttribute("aria-pressed", "true");
    await page.getByRole("button", { name: "5 patient cases" }).click();
    await expect(page.getByRole("button", { name: "5 patient cases" })).toHaveAttribute("aria-pressed", "true");

    await page.goto("/practice?length=5");
    await expect(page.getByRole("button", { name: "5 patient cases" })).toHaveAttribute("aria-pressed", "true");
  });
});
