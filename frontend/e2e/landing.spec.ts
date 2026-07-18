import { expect, test } from "@playwright/test";
import { collectConsoleErrors } from "./helpers";

test.describe("public landing page", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/backend/auth/me", (route) => route.fulfill({
      json: { authenticated: false, user: null },
    }));
  });

  test("introduces the product before showing any learner dashboard", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    const privateDashboardRequests: string[] = [];
    page.on("request", (request) => {
      if (/\/(learners\/demo|adaptive\/plan|learning\/resume)(?:\?|$)/.test(new URL(request.url()).pathname)) {
        privateDashboardRequests.push(request.url());
      }
    });

    await page.goto("/");
    await expect(page.locator('[data-route-accessibility-ready="true"]')).toHaveText("ECG learning home loaded");

    await expect(page.getByRole("heading", { name: "Read ECGs with a method you can trust." })).toBeVisible();
    await expect(page).toHaveTitle("TRACE · ECG learning for medical students");
    const productSummary = page.locator("#main-content").getByText(/Learn the framework, strengthen specific findings/i);
    await expect(productSummary).toHaveCount(1);
    await expect(productSummary).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Website navigation" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Create account", exact: true })).toHaveAttribute("href", "/login?mode=register");
    await expect(page.getByRole("link", { name: "Create your account", exact: true }).first()).toHaveAttribute("href", "/login?mode=register");
    await expect(page.getByRole("link", { name: "Sign in", exact: true }).first()).toHaveAttribute("href", "/login");
    await expect(page.getByRole("link", { name: /guest/i })).toHaveCount(0);
    await expect(page.getByText(/continue as guest|explore as a guest/i)).toHaveCount(0);
    await expect(page.locator(".side-nav")).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Build a read you can trust." })).toHaveCount(0);
    expect(privateDashboardRequests).toEqual([]);

    const body = (await page.locator("body").innerText()).toLowerCase();
    for (const implementationPhrase of [
      "backend",
      "corpus",
      "registry version",
      "provider",
      "evidence gate",
      "grounded demo tutor",
      "server-synced",
    ]) {
      expect(body).not.toContain(implementationPhrase);
    }
    expect(errors, `Unexpected console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("explains all four connected learning modes with direct destinations", async ({ page }) => {
    await page.goto("/");

    const modes = [
      ["Guided learning", "/login?mode=register&next=%2Flearn"],
      ["Focused practice", "/login?mode=register&next=%2Ftrain"],
      ["Rapid practice", "/login?mode=register&next=%2Frapid"],
      ["Clinical cases", "/login?mode=register&next=%2Fpractice"],
    ] as const;
    for (const [title, href] of modes) {
      const modeLink = page.getByRole("heading", { name: title, exact: true }).locator("../..");
      await expect(modeLink).toContainText(title);
      await expect(modeLink).toHaveAttribute("href", href);
    }
    await expect(page.getByRole("heading", { name: "The tracing stays at the center of the work." })).toBeVisible();
    await expect(page.getByLabel("Example of an adaptive learning recommendation")).toContainText("Adaptive learning coach");
    await expect(page.getByRole("img", { name: /deidentified PTB-XL ECG/i })).toBeVisible();
  });

  test("keeps the public entry and account action usable at 320 pixels", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 780 });
    await page.goto("/");

    await expect(page.getByRole("link", { name: "TRACE ECG learning home" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Create account", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Create your account", exact: true }).first()).toBeVisible();

    const geometry = await page.evaluate(() => ({
      overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      createHeight: document.querySelector<HTMLElement>('a[href="/login?mode=register"]')?.getBoundingClientRect().height ?? 0,
    }));
    expect(geometry.overflow).toBeLessThanOrEqual(1);
    expect(geometry.createHeight).toBeGreaterThanOrEqual(44);
  });
});
