import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

async function expectNoWcagViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const summary = results.violations.map((violation) => ({
    id: violation.id,
    impact: violation.impact,
    help: violation.help,
    targets: violation.nodes.map((node) => node.target.join(" ")),
  }));

  expect(summary, JSON.stringify(summary, null, 2)).toEqual([]);
}

test.describe("public entry accessibility", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/backend/auth/me", (route) => route.fulfill({
      json: { authenticated: false, user: null },
    }));
  });

  for (const surface of [
    { name: "landing", path: "/", readyHeading: "Read ECGs with a method you can trust." },
    { name: "sign in", path: "/login", readyHeading: "Sign in" },
    { name: "registration", path: "/login?mode=register", readyHeading: "Create your account" },
  ] as const) {
    test(`${surface.name} has no detectable WCAG A/AA violations`, async ({ page }) => {
      await page.goto(surface.path);
      await expect(page.getByRole("heading", { name: surface.readyHeading, exact: typeof surface.readyHeading === "string" })).toBeVisible();
      await expect(page.getByRole("main")).toBeVisible();
      await expectNoWcagViolations(page);
    });
  }

  test("the public shell exposes a working skip link and clear landmarks", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Read ECGs with a method you can trust." })).toBeVisible();
    await expect(page).toHaveTitle("TRACE · ECG learning for medical students");

    await page.keyboard.press("Tab");
    const skipLink = page.getByRole("link", { name: "Skip to main content" });
    await expect(skipLink).toBeFocused();
    await expect(skipLink).toHaveAttribute("href", "#main-content");
    await page.keyboard.press("Enter");
    await expect(page.getByRole("main")).toBeFocused();

    await expect(page.getByRole("banner")).toHaveCount(1);
    await expect(page.getByRole("navigation", { name: "Website navigation" })).toHaveCount(1);
    await expect(page.getByRole("contentinfo")).toHaveCount(1);
  });

  test("authentication tabs support keyboard selection and keep form labels explicit", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "Sign in", exact: true })).toBeVisible();

    const signInTab = page.getByRole("tab", { name: "Sign in" });
    const registerTab = page.getByRole("tab", { name: "Register" });
    await signInTab.focus();
    await page.keyboard.press("ArrowRight");
    await expect(registerTab).toBeFocused();
    await expect(registerTab).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("heading", { name: "Create your account" })).toBeVisible();

    await expect(page.getByRole("textbox", { name: "Email" })).toHaveAttribute("autocomplete", "email");
    await expect(page.getByRole("textbox", { name: "Display name (optional)" })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Terms" })).toHaveAttribute("href", "/terms");
    await expect(page.getByRole("link", { name: "Privacy Notice" })).toHaveAttribute("href", "/privacy");
    await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("autocomplete", "new-password");
    await expect(page.getByLabel("Confirm password")).toHaveAttribute("autocomplete", "new-password");
    await expect(page.getByRole("tabpanel")).toHaveAttribute("aria-labelledby", "auth-tab-register");

    await page.keyboard.press("ArrowLeft");
    await expect(signInTab).toBeFocused();
    await expect(signInTab).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("heading", { name: "Sign in", exact: true })).toBeVisible();
  });

  test("landing and registration remain violation-free at 320 pixels", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 780 });

    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Read ECGs with a method you can trust." })).toBeVisible();
    await expectNoWcagViolations(page);

    await page.goto("/login?mode=register");
    await expect(page.getByRole("heading", { name: "Create your account" })).toBeVisible();
    await expectNoWcagViolations(page);
  });
});
