import { expect, test } from "@playwright/test";
import { collectConsoleErrors } from "./helpers";

test.describe("public password recovery", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/backend/auth/me", (route) => route.fulfill({
      json: { authenticated: false, user: null },
    }));
  });

  test("uses a generic, non-enumerating response after a recovery request", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    let requestBody: unknown;
    await page.route("**/api/backend/auth/password-reset/request", async (route) => {
      requestBody = route.request().postDataJSON();
      await route.fulfill({
        json: { ok: true, message: "PRIVATE: this account definitely exists" },
      });
    });

    const authHydrated = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/auth/me"));
    await page.goto("/forgot-password");
    await authHydrated;
    const email = page.getByRole("textbox", { name: "Email address" });
    await expect(email).toHaveAttribute("required", "");
    await expect(email).toHaveAttribute("autocomplete", "email");
    await email.fill("student@example.edu");
    await page.getByRole("button", { name: "Send reset link" }).click();

    await expect(page.getByRole("heading", { name: "Check your inbox" })).toBeVisible();
    await expect(page.getByText(/if an account exists for that email/i)).toBeVisible();
    await expect(page.getByText(/PRIVATE|definitely exists/i)).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Return to sign in" })).toHaveAttribute("href", "/login");
    expect(requestBody).toEqual({ email: "student@example.edu" });
    expect(errors).toEqual([]);
  });

  test("submits the reset proof only in the JSON body and completes the flow", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    const challengeId = "challenge_123456789";
    const token = "private-token-value";
    let requestUrl = "";
    let browserUrlAtRequest = "";
    let requestBody: unknown;
    const observedNetwork: Array<{ url: string; referer: string }> = [];
    page.on("request", (request) => observedNetwork.push({
      url: request.url(),
      referer: request.headers().referer ?? "",
    }));
    await page.route("**/api/backend/auth/password-reset/confirm", async (route) => {
      requestUrl = route.request().url();
      browserUrlAtRequest = page.url();
      requestBody = route.request().postDataJSON();
      await route.fulfill({ json: { ok: true } });
    });

    await page.goto(`/reset-password?challengeId=${challengeId}#token=${token}`);
    await expect(page).toHaveURL(/\/reset-password$/);
    const password = page.getByLabel("New password", { exact: true });
    const confirmation = page.getByLabel("Confirm new password");
    await expect(password).toHaveAttribute("required", "");
    await expect(password).toHaveAttribute("autocomplete", "new-password");
    await expect(confirmation).toHaveAttribute("autocomplete", "new-password");
    await password.fill("A-longer-passphrase-28");
    await confirmation.fill("A-longer-passphrase-28");
    await expect(page.getByText("Passwords match", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Update password" }).click();

    await expect(page).toHaveURL(/\/login\?passwordReset=1$/);
    await expect(page.getByText("Your password was updated. Sign in with your new password.")).toBeVisible();
    expect(new URL(requestUrl).search).toBe("");
    expect(requestUrl).not.toContain(challengeId);
    expect(requestUrl).not.toContain(token);
    expect(browserUrlAtRequest).not.toContain(challengeId);
    expect(browserUrlAtRequest).not.toContain(token);
    expect(requestBody).toEqual({ challengeId, token, newPassword: "A-longer-passphrase-28" });
    expect(observedNetwork.every((request) => !request.url.includes(token) && !request.referer.includes(token))).toBe(true);
    expect(errors).toEqual([]);
  });

  test("optionally reclaims an unrecognized unfinished account identity", async ({ page }) => {
    const challengeId = "challenge_reclaim_123";
    const token = "private-reclaim-token";
    const requestBodies: unknown[] = [];
    await page.route("**/api/backend/auth/password-reset/confirm", async (route) => {
      const requestBody = route.request().postDataJSON() as { recoveryUsername?: string };
      requestBodies.push(requestBody);
      if (requestBody.recoveryUsername === "already_used") {
        await route.fulfill({
          status: 409,
          json: { detail: { field: "recoveryUsername", code: "recovery_identity_unavailable", message: "private collision detail" } },
        });
        return;
      }
      await route.fulfill({
        json: {
          ok: true,
          identityRecovered: true,
          username: "actual_student",
          displayName: "Actual Student",
        },
      });
    });

    await page.goto(`/reset-password?challengeId=${challengeId}#token=${token}`);
    await expect(page.getByText("Don’t recognize the account details?")).toBeVisible();
    await expect(page.getByLabel("Your username (optional)")).toBeHidden();
    await page.getByText("Don’t recognize the account details?").click();
    const username = page.getByLabel("Your username (optional)");
    await expect(username).toBeVisible();
    await expect(page.getByText(/Verified accounts keep their existing username/i)).toBeVisible();

    await page.getByLabel("New password", { exact: true }).fill("A-longer-passphrase-28");
    await page.getByLabel("Confirm new password").fill("A-longer-passphrase-28");
    await username.fill("actual student");
    await page.getByRole("button", { name: "Update password" }).click();
    await expect(username).toBeFocused();
    await expect(page.getByText(/Use 3–32 letters, numbers/i)).toBeVisible();

    await username.fill("already_used");
    await page.getByLabel("Name shown in TRACE (optional)").fill("Actual Student");
    await page.getByRole("button", { name: "Update password" }).click();
    await expect(username).toBeFocused();
    await expect(page.getByText("That username is already in use. Choose another.")).toBeVisible();
    await expect(page.getByText("private collision detail")).toHaveCount(0);

    await username.fill("actual_student");
    await page.getByRole("button", { name: "Update password" }).click();

    await expect(page.getByRole("heading", { name: "Your account is yours again" })).toBeVisible();
    await expect(page.getByLabel("Recovered sign-in identity")).toContainText("actual_student");
    await expect(page.getByRole("link", { name: "Continue to sign in" })).toHaveAttribute("href", "/login?passwordReset=1");
    expect(requestBodies.at(-1)).toEqual({
      challengeId,
      token,
      newPassword: "A-longer-passphrase-28",
      recoveryUsername: "actual_student",
      recoveryDisplayName: "Actual Student",
    });
  });

  test("handles missing and rejected reset links without exposing raw errors", async ({ page }) => {
    let confirmRequests = 0;
    await page.route("**/api/backend/auth/password-reset/confirm", async (route) => {
      confirmRequests += 1;
      await route.fulfill({
        status: 400,
        json: {
          detail: {
            code: "challenge_expired",
            message: "RAW_INTERNAL_CHALLENGE_DETAIL",
          },
        },
      });
    });

    await page.goto("/reset-password");
    await expect(page.getByRole("heading", { name: "This reset link is incomplete" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Request a new link" })).toHaveAttribute("href", "/forgot-password");
    expect(confirmRequests).toBe(0);

    await page.goto("/reset-password?challengeId=expired_challenge&token=expired_token");
    await page.getByLabel("New password", { exact: true }).fill("A-longer-passphrase-28");
    await page.getByLabel("Confirm new password").fill("A-longer-passphrase-28");
    await page.getByRole("button", { name: "Update password" }).click();

    await expect(page.getByRole("alert").filter({ hasText: /invalid, expired, or has already been used/i })).toBeVisible();
    await expect(page.getByText("RAW_INTERNAL_CHALLENGE_DETAIL")).toHaveCount(0);
    expect(confirmRequests).toBe(1);
  });

  test("places focus on the field that needs correction", async ({ page }) => {
    await page.goto("/forgot-password");
    await page.getByRole("button", { name: "Send reset link" }).click();
    await expect(page.getByRole("textbox", { name: "Email address" })).toBeFocused();
    await expect(page.getByText("Enter the email address linked to your account.")).toBeVisible();

    await page.goto("/reset-password?challengeId=challenge_123456789#token=token_value");
    await page.getByLabel("New password", { exact: true }).fill("A-longer-passphrase-28");
    await page.getByLabel("Confirm new password").fill("A-different-passphrase-29");
    await page.getByRole("button", { name: "Update password" }).click();

    await expect(page.getByLabel("Confirm new password")).toBeFocused();
    await expect(page.getByText(/passwords do not match/i)).toBeVisible();
  });

  test("keeps both recovery forms usable on a 320px screen", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 760 });

    await page.goto("/forgot-password");
    for (const control of [
      page.getByRole("textbox", { name: "Email address" }),
      page.getByRole("button", { name: "Send reset link" }),
    ]) {
      const box = await control.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.height).toBeGreaterThanOrEqual(44);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);

    await page.goto("/reset-password?challengeId=challenge_123456789#token=token_value");
    for (const control of [
      page.getByLabel("New password", { exact: true }),
      page.getByLabel("Confirm new password"),
      page.getByRole("button", { name: "Update password" }),
    ]) {
      const box = await control.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.height).toBeGreaterThanOrEqual(44);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  });
});
