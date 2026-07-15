import { expect, test } from "@playwright/test";
import { collectConsoleErrors } from "./helpers";

test.describe("student-facing authentication", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/backend/auth/me", (route) => route.fulfill({
      json: { authenticated: false, user: null },
    }));
  });

  test("opens the registration intent directly from a public CTA", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto("/login?mode=register");

    await expect(page.getByRole("heading", { name: "See the tracing. Make the call. Learn from every read." })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Create your account" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Register" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("tab", { name: "Sign in" })).toHaveAttribute("aria-selected", "false");
    await expect(page.locator("#auth-password-confirm")).toBeVisible();
    await page.locator("#auth-password").fill("Safe-passphrase-2026");
    await page.locator("#auth-password-confirm").fill("Safe-passphrase-2026");
    await expect(page.getByText("Passwords match", { exact: true })).toBeVisible();
    await expect(page.getByRole("list", { name: "Four ECG learning modes" }).getByRole("listitem")).toHaveCount(4);
    await expect(page.getByText(/continue as guest|guest work/i)).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Create account", exact: true })).toBeEnabled();
    expect(errors).toEqual([]);
  });

  test("keeps the registration action and terms in the first 1280 by 720 viewport", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/login?mode=register");

    const createAccount = page.getByRole("button", { name: "Create account", exact: true });
    const terms = page.getByText("By creating an account", { exact: false });
    await expect(createAccount).toBeVisible();
    await expect(terms).toBeVisible();

    for (const control of [createAccount, page.locator("#auth-email"), page.locator("#auth-password"), page.locator("#auth-password-confirm")]) {
      const box = await control.boundingBox();
      expect(box, "expected the registration control to have visible geometry").not.toBeNull();
      expect(box!.height).toBeGreaterThanOrEqual(44);
      expect(box!.y + box!.height).toBeLessThanOrEqual(720);
    }
    const termsBox = await terms.boundingBox();
    expect(termsBox).not.toBeNull();
    expect(termsBox!.y + termsBox!.height).toBeLessThanOrEqual(720);
    const passwordBox = await page.locator("#auth-password").boundingBox();
    const confirmationBox = await page.locator("#auth-password-confirm").boundingBox();
    expect(passwordBox).not.toBeNull();
    expect(confirmationBox).not.toBeNull();
    expect(Math.abs(passwordBox!.y - confirmationBox!.y)).toBeLessThanOrEqual(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  });

  test("keeps the polished sign-in surface usable at 320px", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 780 });
    await page.goto("/login");

    await expect(page.getByRole("heading", { name: "Sign in", exact: true })).toBeVisible();
    for (const control of [
      page.getByRole("tab", { name: "Sign in" }),
      page.getByRole("tab", { name: "Register" }),
      page.locator("#auth-email-signin"),
      page.locator("#auth-password"),
      page.getByRole("button", { name: "Sign in", exact: true }),
    ]) {
      const box = await control.boundingBox();
      expect(box, "expected the control to have visible geometry").not.toBeNull();
      expect(box!.height).toBeGreaterThanOrEqual(44);
    }

    const overflow = await page.evaluate(() => (
      document.documentElement.scrollWidth - document.documentElement.clientWidth
    ));
    expect(overflow).toBeLessThanOrEqual(1);
    await expect(page.getByText(/continue as guest|guest work/i)).toHaveCount(0);
  });
});
