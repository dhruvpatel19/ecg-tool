import { expect, test, type Page } from "@playwright/test";

const verifiedUser = {
  userId: "u_email_auth",
  username: "ecg_student",
  displayName: "ECG Student",
  accountStatus: "verified",
  emailMasked: "s***@example.edu",
  emailVerified: true,
};

const accountResolutionPassword = ["Attempt", "passphrase", "2026"].join("-");

async function mockAccountBasics(page: Page) {
  await page.route("**/api/backend/auth/sessions", (route) => route.fulfill({ json: { sessions: [] } }));
  await page.route("**/api/backend/auth/guest-progress", (route) => route.fulfill({
    json: { hasProgress: false, claimable: false, totalActivities: 0, attempts: 0, guidedInteractions: 0, competencyReceipts: 0, lessonScenes: 0, tutorThreads: 0, reviewSessions: 0, rapidRounds: 0, clinicalSessions: 0, trainingCampaigns: 0, competencies: 0, learningPreferences: 0, lastActivityAt: null },
  }));
}

test.describe("verified email authentication", () => {
  test("novice registration is compact, accessible, and creates no session before a six-digit verification", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 780 });
    await page.route("**/api/backend/auth/me", (route) => route.fulfill({ json: { authenticated: false, user: null } }));
    await mockAccountBasics(page);
    let registerBody: unknown;
    let verificationBody: unknown;
    await page.route("**/api/backend/auth/register", async (route) => {
      registerBody = route.request().postDataJSON();
      await route.fulfill({ json: { verificationRequired: true, challengeId: "verify_registration", maskedEmail: "s***@example.edu", expiresAt: "2030-01-01T00:00:00Z", guestClaimPendingVerification: false, deliveryFailed: false, retryAfterSeconds: 60 } });
    });
    await page.route("**/api/backend/auth/email/verify/confirm", async (route) => {
      verificationBody = route.request().postDataJSON();
      await route.fulfill({ json: { user: verifiedUser, accountStatus: "verified", guestClaim: null } });
    });

    await page.goto("/login?mode=register&next=%2Faccount");
    await expect(page.getByRole("heading", { level: 2, name: "Create your account" })).toBeVisible();
    await expect(page.getByLabel("Display name (optional)")).toHaveCount(0);
    await expect(page.getByText("PTB-XL case 3 · CC BY 4.0")).toHaveCount(1);
    await expect(page.getByRole("link", { name: "Terms" })).toHaveAttribute("href", "/terms");
    await expect(page.getByRole("link", { name: "Privacy Notice" })).toHaveAttribute("href", "/privacy");
    await page.getByLabel("Email", { exact: true }).fill("student@example.edu");
    await page.getByLabel("Password", { exact: true }).fill("Safe-passphrase-2026");
    await page.getByLabel("Confirm password").fill("Safe-passphrase-2026");
    await page.getByRole("button", { name: "Create account", exact: true }).click();

    const code = page.getByLabel("Six-digit verification code");
    await expect(page.getByRole("heading", { level: 1, name: "Verify your email" })).toBeVisible();
    await expect(code).toHaveAttribute("inputmode", "numeric");
    await expect(code).toHaveAttribute("autocomplete", "one-time-code");
    await expect(code).toHaveAttribute("maxlength", "6");
    await expect(page.locator("#auth-password")).toHaveCount(0);
    await code.fill("123456");
    await page.locator("#auth-verification-password").fill("Safe-passphrase-2026");
    await page.getByRole("button", { name: "Verify email" }).click();
    await expect(page).toHaveURL(/\/account$/);
    expect(registerBody).toEqual({ password: "Safe-passphrase-2026", email: "student@example.edu" });
    expect(verificationBody).toEqual({ challengeId: "verify_registration", token: "123456", password: "Safe-passphrase-2026" });
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  });

  test("an owner-proved existing email never creates a session and offers sign-in or recovery", async ({ page }) => {
    await page.route("**/api/backend/auth/me", (route) => route.fulfill({ json: { authenticated: false, user: null } }));
    let resendBody: unknown;
    let confirmBody: unknown;
    await page.route("**/api/backend/auth/register", (route) => route.fulfill({
      json: {
        verificationRequired: true,
        challengeId: "registration_resolution",
        maskedEmail: "o***@example.edu",
        expiresAt: "2030-01-01T00:00:00Z",
        deliveryFailed: false,
        retryAfterSeconds: 0,
      },
    }));
    await page.route("**/api/backend/auth/email/verify/resend", async (route) => {
      resendBody = route.request().postDataJSON();
      await route.fulfill({ json: { ok: true, message: "PRIVATE purpose", deliveryFailed: false, retryAfterSeconds: 60 } });
    });
    await page.route("**/api/backend/auth/email/verify/confirm", async (route) => {
      confirmBody = route.request().postDataJSON();
      await route.fulfill({
        json: {
          accountResolutionRequired: true,
          suggestedAction: "sign_in_or_reset_password",
          message: "PRIVATE existing membership detail",
        },
      });
    });

    await page.goto("/login?mode=register&next=%2Faccount");
    await expect(page.locator('[data-route-accessibility-ready="true"]')).toHaveText("Sign in loaded");
    await page.getByLabel("Email", { exact: true }).fill("owner@example.edu");
    await page.getByLabel("Password", { exact: true }).fill(accountResolutionPassword);
    await page.getByLabel("Confirm password").fill(accountResolutionPassword);
    await page.getByRole("button", { name: "Create account", exact: true }).click();

    await expect(page.getByText(/sent a six-digit verification code/i)).toBeVisible();
    await expect(page.getByText(/account was created/i)).toHaveCount(0);
    await page.getByRole("button", { name: "Resend email" }).click();
    await page.getByLabel("Six-digit verification code").fill("135790");
    await page.locator("#auth-verification-password").fill(accountResolutionPassword);
    const confirmationResponse = page.waitForResponse((response) => (
      response.url().includes("/api/backend/auth/email/verify/confirm")
      && response.request().method() === "POST"
    ));
    await page.getByRole("button", { name: "Verify email" }).click();
    await confirmationResponse;

    await expect(page).toHaveURL(/\/login(?:\?|$)/);
    await expect(page.getByRole("heading", { level: 1, name: "This email already has a TRACE account" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Continue with the account you already have" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Reset password" })).toHaveAttribute("href", "/forgot-password");
    await expect(page.locator(".side-nav")).toHaveCount(0);
    await expect(page.getByText(/PRIVATE existing|PRIVATE purpose/i)).toHaveCount(0);
    expect(resendBody).toEqual({ challengeId: "registration_resolution" });
    expect(confirmBody).toEqual({ challengeId: "registration_resolution", token: "135790", password: accountResolutionPassword });
  });

  test("generic registration failure guides recovery without exposing backend detail", async ({ page }) => {
    await page.route("**/api/backend/auth/me", (route) => route.fulfill({ json: { authenticated: false, user: null } }));
    await page.route("**/api/backend/auth/register", (route) => route.fulfill({
      status: 400,
      json: { detail: { code: "registration_unavailable", message: "PRIVATE membership collision" } },
    }));

    await page.goto("/login?mode=register");
    await page.getByLabel("Email", { exact: true }).fill("possible@example.edu");
    await page.getByLabel("Password", { exact: true }).fill(accountResolutionPassword);
    await page.getByLabel("Confirm password").fill(accountResolutionPassword);
    await page.getByRole("button", { name: "Create account", exact: true }).click();

    await expect(page.getByText(/We couldn’t create an account with those details/i)).toBeVisible();
    const options = page.getByLabel("Existing account options");
    await expect(options.getByRole("button", { name: "Sign in instead" })).toBeVisible();
    await expect(options.getByRole("link", { name: "Reset password" })).toHaveAttribute("href", "/forgot-password");
    await expect(page.getByText("PRIVATE membership collision")).toHaveCount(0);
  });

  test("an owner-proved unfinished account leads with password recovery", async ({ page }) => {
    await page.route("**/api/backend/auth/me", (route) => route.fulfill({ json: { authenticated: false, user: null } }));
    await page.route("**/api/backend/auth/register", (route) => route.fulfill({
      json: {
        verificationRequired: true,
        challengeId: "pending_registration_resolution",
        maskedEmail: "p***@example.edu",
        expiresAt: "2030-01-01T00:00:00Z",
        deliveryFailed: false,
        retryAfterSeconds: 60,
      },
    }));
    await page.route("**/api/backend/auth/email/verify/confirm", (route) => route.fulfill({
      json: {
        accountResolutionRequired: true,
        suggestedAction: "reset_password",
        message: "PRIVATE pending membership detail",
      },
    }));

    await page.goto("/login?mode=register");
    await page.getByLabel("Email", { exact: true }).fill("pending@example.edu");
    await page.getByLabel("Password", { exact: true }).fill(accountResolutionPassword);
    await page.getByLabel("Confirm password").fill(accountResolutionPassword);
    await page.getByRole("button", { name: "Create account", exact: true }).click();
    await page.getByLabel("Six-digit verification code").fill("975310");
    await page.locator("#auth-verification-password").fill(accountResolutionPassword);
    await page.getByRole("button", { name: "Verify email" }).click();

    await expect(page.getByRole("heading", { name: "Finish recovering this account" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Reset password" })).toHaveAttribute("href", "/forgot-password");
    await expect(page.getByRole("button", { name: "Back to sign in" })).toBeVisible();
    await expect(page.getByText(/PRIVATE pending/i)).toHaveCount(0);
    await expect(page.locator(".side-nav")).toHaveCount(0);
  });

  test("returning login accepts email and signs in without a second email challenge", async ({ page }) => {
    await page.route("**/api/backend/auth/me", (route) => route.fulfill({ json: { authenticated: false, user: null } }));
    await mockAccountBasics(page);
    let loginBody: unknown;
    await page.route("**/api/backend/auth/login", async (route) => {
      loginBody = route.request().postDataJSON();
      await route.fulfill({ json: { user: verifiedUser, guestClaim: null } });
    });

    await page.goto("/login?next=%2Faccount");
    await expect(page.getByRole("heading", { level: 1, name: "Sign in" })).toBeVisible();
    await page.getByLabel("Email", { exact: true }).fill("student@example.edu");
    await page.locator("#auth-password").fill("Safe-passphrase-2026");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page).toHaveURL(/\/account$/);
    expect(loginBody).toEqual({ identifier: "student@example.edu", password: "Safe-passphrase-2026" });
  });

  test("verification links scrub proof and wait for an explicit password-confirmed action", async ({ page }) => {
    await page.route("**/api/backend/auth/me", (route) => route.fulfill({ json: { authenticated: false, user: null } }));
    await mockAccountBasics(page);
    let browserUrlAtRequest = "";
    let requestUrl = "";
    let requestBody: unknown;
    let confirmRequests = 0;
    const observedNetwork: Array<{ url: string; referer: string }> = [];
    page.on("request", (request) => observedNetwork.push({
      url: request.url(),
      referer: request.headers().referer ?? "",
    }));
    await page.route("**/api/backend/auth/email/verify/confirm", async (route) => {
      confirmRequests += 1;
      browserUrlAtRequest = page.url();
      requestUrl = route.request().url();
      requestBody = route.request().postDataJSON();
      await route.fulfill({ json: { user: verifiedUser, accountStatus: "verified", guestClaim: null } });
    });
    await page.goto("/verify-email?challengeId=verify_link&next=%2Faccount#token=123456");
    await expect(page).toHaveURL(/\/verify-email$/);
    await expect(page.getByRole("heading", { name: "Confirm your email" })).toBeVisible();
    expect(confirmRequests).toBe(0);
    await page.getByLabel("Current password").fill("Safe-passphrase-2026");
    await page.getByRole("button", { name: "Verify email" }).click();
    await expect(page).toHaveURL(/\/account$/);
    expect(browserUrlAtRequest).toMatch(/\/verify-email$/);
    expect(browserUrlAtRequest).not.toContain("123456");
    expect(new URL(requestUrl).search).toBe("");
    expect(requestBody).toEqual({ challengeId: "verify_link", token: "123456", password: "Safe-passphrase-2026" });
    expect(observedNetwork.every((request) => !request.url.includes("123456") && !request.referer.includes("123456"))).toBe(true);
  });

  test("signed-out email-change links survive sign-in without exposing proof", async ({ page }) => {
    let authenticated = false;
    await page.route("**/api/backend/auth/me", (route) => route.fulfill({ json: authenticated ? { authenticated: true, user: verifiedUser } : { authenticated: false, user: null } }));
    await mockAccountBasics(page);
    await page.route("**/api/backend/auth/login", async (route) => {
      authenticated = true;
      await route.fulfill({ json: { user: verifiedUser, guestClaim: null, twoFactorRequired: false } });
    });
    let changeBody: unknown;
    let browserUrlAtRequest = "";
    const observedNetwork: Array<{ url: string; referer: string }> = [];
    page.on("request", (request) => observedNetwork.push({
      url: request.url(),
      referer: request.headers().referer ?? "",
    }));
    await page.route("**/api/backend/auth/email/change/confirm", async (route) => {
      browserUrlAtRequest = page.url();
      changeBody = route.request().postDataJSON();
      await route.fulfill({ json: { ok: true, user: { ...verifiedUser, emailMasked: "n***@example.edu" } } });
    });

    await page.goto("/account/email-change?challengeId=change_link#token=private-change-token");
    await expect(page).toHaveURL((url) => url.pathname === "/login" && url.searchParams.get("next") === "/account/email-change" && !url.href.includes("private-change-token"));
    await page.getByLabel("Email", { exact: true }).fill("student@example.edu");
    await page.locator("#auth-password").fill("Safe-passphrase-2026");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Verify the new address" })).toBeVisible();
    await page.getByRole("button", { name: "Confirm new email" }).click();
    await expect(page.getByRole("heading", { name: "Email updated" })).toBeVisible();
    expect(browserUrlAtRequest).toMatch(/\/account\/email-change$/);
    expect(browserUrlAtRequest).not.toContain("private-change-token");
    expect(changeBody).toEqual({ challengeId: "change_link", token: "private-change-token" });
    expect(observedNetwork.every((request) => !request.url.includes("private-change-token") && !request.referer.includes("private-change-token"))).toBe(true);
  });

  test("pending registration can replace an unreachable email without creating a session", async ({ page }) => {
    await page.route("**/api/backend/auth/me", (route) => route.fulfill({ json: { authenticated: false, user: null } }));
    let replacementBody: unknown;
    let resendBody: unknown;
    await page.route("**/api/backend/auth/register", (route) => route.fulfill({
      json: {
        verificationRequired: true,
        challengeId: "old_registration_challenge",
        maskedEmail: "w***@example.edu",
        expiresAt: "2030-01-01T00:00:00Z",
        deliveryFailed: false,
        retryAfterSeconds: 0,
      },
    }));
    await page.route("**/api/backend/auth/email/unverified/replace", async (route) => {
      replacementBody = route.request().postDataJSON();
      await route.fulfill({
        json: {
          verificationRequired: true,
          challengeId: "replacement_registration_challenge",
          maskedEmail: "r***@example.edu",
          expiresAt: "2030-01-01T00:00:00Z",
          deliveryFailed: true,
          retryAfterSeconds: 0,
        },
      });
    });
    await page.route("**/api/backend/auth/email/verify/resend", async (route) => {
      resendBody = route.request().postDataJSON();
      await route.fulfill({ json: { ok: true, message: "PRIVATE delivery detail", deliveryFailed: false, retryAfterSeconds: 60 } });
    });

    await page.goto("/login?mode=register&next=%2Faccount");
    await page.getByLabel("Email", { exact: true }).fill("wrong@example.edu");
    await page.getByLabel("Password", { exact: true }).fill("Safe-passphrase-2026");
    await page.getByLabel("Confirm password").fill("Safe-passphrase-2026");
    await page.getByRole("button", { name: "Create account", exact: true }).click();
    await page.getByRole("button", { name: "Use a different email" }).click();

    await expect(page.getByRole("heading", { name: "Use a different email" })).toBeVisible();
    await page.getByLabel("Replacement email").fill("reachable@example.edu");
    await page.getByLabel("Registration password").fill("Safe-passphrase-2026");
    await page.getByRole("button", { name: "Update email and send code" }).click();

    await expect(page.getByText(/address was updated, but the verification email could not be sent/i)).toBeVisible();
    await expect(page.locator(".side-nav")).toHaveCount(0);
    await expect(page).toHaveURL(/\/login/);
    await page.getByRole("button", { name: "Resend email" }).click();
    await expect(page.getByText("PRIVATE delivery detail")).toHaveCount(0);
    expect(replacementBody).toEqual({
      challengeId: "old_registration_challenge",
      currentPassword: "Safe-passphrase-2026",
      newEmail: "reachable@example.edu",
    });
    expect(resendBody).toEqual({ challengeId: "replacement_registration_challenge" });
  });

  test("authenticated legacy account can replace a pending email with current-password proof", async ({ page }) => {
    const pendingUser = {
      ...verifiedUser,
      accountStatus: "email_verification_required",
      emailMasked: "w***@example.edu",
      emailVerified: false,
    };
    await page.route("**/api/backend/auth/me", (route) => route.fulfill({ json: { authenticated: true, user: pendingUser } }));
    await mockAccountBasics(page);
    let replacementBody: unknown;
    let resendBody: unknown;
    await page.route("**/api/backend/auth/email/unverified/replace", async (route) => {
      replacementBody = route.request().postDataJSON();
      await route.fulfill({
        json: {
          verificationRequired: true,
          challengeId: "legacy_replacement_challenge",
          maskedEmail: "n***@example.edu",
          expiresAt: "2030-01-01T00:00:00Z",
          deliveryFailed: true,
          retryAfterSeconds: 0,
        },
      });
    });
    await page.route("**/api/backend/auth/email/verify/resend", async (route) => {
      resendBody = route.request().postDataJSON();
      await route.fulfill({ json: { ok: true, message: "PRIVATE resend detail", deliveryFailed: false, retryAfterSeconds: 60 } });
    });
    await page.route("**/api/backend/auth/email/verify/confirm", (route) => route.fulfill({
      json: { user: verifiedUser, accountStatus: "verified", guestClaim: null },
    }));

    await page.goto("/account");
    await expect(page.getByText(/wrong or unreachable/i)).toBeVisible();
    await page.getByLabel("Replacement email address").fill("new-address@example.edu");
    await page.locator("#account-email-password").fill("Safe-passphrase-2026");
    await page.getByRole("button", { name: "Replace email and send code" }).click();
    await expect(page.getByText(/code expires after a short time/i)).toBeVisible();
    await expect(page.getByRole("button", { name: "Not now" })).toBeVisible();
    await page.getByRole("button", { name: "Resend email" }).click();
    await expect(page.getByText("PRIVATE resend detail")).toHaveCount(0);

    expect(replacementBody).toEqual({ currentPassword: "Safe-passphrase-2026", newEmail: "new-address@example.edu" });
    expect(resendBody).toEqual({ challengeId: "legacy_replacement_challenge" });
  });

  test("email-change proof survives reload and transient failure, then clears only after success", async ({ page }) => {
    await page.route("**/api/backend/auth/me", (route) => route.fulfill({ json: { authenticated: true, user: verifiedUser } }));
    let confirmCalls = 0;
    await page.route("**/api/backend/auth/email/change/confirm", async (route) => {
      confirmCalls += 1;
      if (confirmCalls === 1) {
        await route.fulfill({ status: 503, json: { detail: { code: "email_service_unavailable", message: "PRIVATE outage detail" } } });
      } else {
        await route.fulfill({ json: { ok: true, user: { ...verifiedUser, emailMasked: "n***@example.edu" } } });
      }
    });

    await page.goto("/account/email-change?challengeId=durable_change#token=durable-private-token");
    await page.getByRole("button", { name: "Confirm new email" }).click();
    await expect(page.getByText(/email change could not be confirmed right now/i)).toBeVisible();
    await expect(page.getByText("PRIVATE outage detail")).toHaveCount(0);
    expect(await page.evaluate(() => sessionStorage.getItem("trace:pending-email-change-proof:v1"))).toContain("durable-private-token");

    await page.goto("/privacy");
    await expect(page.getByRole("heading", { name: "Your learning record should help you—not surprise you." })).toBeVisible();
    await page.goto("/account/email-change");
    await expect(page.getByRole("heading", { name: "Verify the new address" })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("heading", { name: "Verify the new address" })).toBeVisible();
    await page.getByRole("button", { name: "Confirm new email" }).click();
    await expect(page.getByRole("heading", { name: "Email updated" })).toBeVisible();
    expect(await page.evaluate(() => sessionStorage.getItem("trace:pending-email-change-proof:v1"))).toBeNull();
    expect(confirmCalls).toBe(2);
  });

  test("retryable incorrect email-change proof remains available for another attempt", async ({ page }) => {
    await page.route("**/api/backend/auth/me", (route) => route.fulfill({ json: { authenticated: true, user: verifiedUser } }));
    await page.route("**/api/backend/auth/email/change/confirm", (route) => route.fulfill({
      status: 400,
      json: { detail: { code: "challenge_incorrect", message: "PRIVATE attempt detail" } },
    }));

    await page.goto("/account/email-change?challengeId=retryable_change#token=retryable-private-token");
    await page.getByRole("button", { name: "Confirm new email" }).click();
    await expect(page.getByText(/confirmation wasn’t accepted/i)).toBeVisible();
    await expect(page.getByText("PRIVATE attempt detail")).toHaveCount(0);
    expect(await page.evaluate(() => sessionStorage.getItem("trace:pending-email-change-proof:v1"))).toContain("retryable-private-token");
    await page.reload();
    await expect(page.getByRole("heading", { name: "Verify the new address" })).toBeVisible();
  });

  test("terminal email-change rejection removes the stored proof", async ({ page }) => {
    await page.route("**/api/backend/auth/me", (route) => route.fulfill({ json: { authenticated: true, user: verifiedUser } }));
    await page.route("**/api/backend/auth/email/change/confirm", (route) => route.fulfill({
      status: 400,
      json: { detail: { code: "challenge_expired", message: "PRIVATE expiry detail" } },
    }));

    await page.goto("/account/email-change?challengeId=expired_change#token=expired-private-token");
    await page.getByRole("button", { name: "Confirm new email" }).click();
    await expect(page.getByText(/invalid, expired, or has already been used/i)).toBeVisible();
    await expect(page.getByText("PRIVATE expiry detail")).toHaveCount(0);
    expect(await page.evaluate(() => sessionStorage.getItem("trace:pending-email-change-proof:v1"))).toBeNull();
    await page.reload();
    await expect(page.getByRole("heading", { name: "This confirmation link is incomplete" })).toBeVisible();
  });

  test("closing an email-change panel does not claim the emailed link was revoked", async ({ page }) => {
    await page.route("**/api/backend/auth/me", (route) => route.fulfill({ json: { authenticated: true, user: verifiedUser } }));
    await mockAccountBasics(page);
    await page.route("**/api/backend/auth/email/change/request", (route) => route.fulfill({
      json: { emailChangeVerificationRequired: true, challengeId: "pending_change_link", maskedEmail: "n***@example.edu", expiresAt: "2030-01-01T00:00:00Z", deliveryFailed: false, retryAfterSeconds: 60 },
    }));

    await page.goto("/account");
    await page.getByRole("button", { name: "Change verified email…" }).click();
    await page.getByLabel("New email address").fill("new@example.edu");
    await page.locator("#account-email-password").fill("Safe-passphrase-2026");
    await page.getByRole("button", { name: "Verify new email" }).click();
    await expect(page.getByText(/link expires after a short time/i)).toBeVisible();
    await expect(page.getByRole("button", { name: "Close panel" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Cancel change" })).toHaveCount(0);
  });

  test("account security stays focused on verified email and recovery", async ({ page }) => {
    await page.route("**/api/backend/auth/me", (route) => route.fulfill({ json: { authenticated: true, user: verifiedUser } }));
    await mockAccountBasics(page);

    await page.goto("/account");
    await expect(page.getByText("Your verified email is used for sign-in and account recovery.")).toBeVisible();
    await expect(page.getByText(/two-step verification/i)).toHaveCount(0);
    await expect(page.getByRole("button", { name: /enable with email code/i })).toHaveCount(0);
  });

  test("earlier beta learning stays invisible unless claimable and clears retired caches after attach", async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem("foundations_state_v1:guest", "legacy");
      localStorage.setItem("trace-production-curriculum-v1", "legacy");
      localStorage.setItem("trace:guest-learning-preferences", "saved");
      sessionStorage.setItem("ecg-tool:rapid-round:v2:guest", "legacy");
    });
    await page.route("**/api/backend/auth/me", (route) => route.fulfill({ json: { authenticated: true, user: verifiedUser } }));
    await page.route("**/api/backend/auth/sessions", (route) => route.fulfill({ json: { sessions: [] } }));
    await page.route("**/api/backend/auth/guest-progress", (route) => route.fulfill({ json: { hasProgress: true, claimable: true, totalActivities: 12, attempts: 4, guidedInteractions: 3, competencyReceipts: 2, lessonScenes: 3, tutorThreads: 0, reviewSessions: 0, rapidRounds: 2, clinicalSessions: 0, trainingCampaigns: 0, competencies: 2, learningPreferences: 1, lastActivityAt: "2026-07-01T00:00:00Z" } }));
    await page.route("**/api/backend/auth/guest-progress/claim", (route) => route.fulfill({ json: { ok: true, guestClaim: { claimed: true, replay: false, claimedAt: "2026-07-14T00:00:00Z", guestProgress: { hasProgress: true, claimable: true, totalActivities: 12 } } } }));

    await page.goto("/account");
    await expect(page.getByRole("heading", { name: "Earlier browser learning found" })).toBeVisible();
    await page.getByRole("button", { name: "Attach to my account" }).click();
    await expect(page.getByText("Earlier learning was attached to this account.")).toBeVisible();
    expect(await page.evaluate(() => ({
      foundations: localStorage.getItem("foundations_state_v1:guest"),
      production: localStorage.getItem("trace-production-curriculum-v1"),
      preferences: localStorage.getItem("trace:guest-learning-preferences"),
      rapid: sessionStorage.getItem("ecg-tool:rapid-round:v2:guest"),
    }))).toEqual({ foundations: null, production: null, preferences: null, rapid: null });
  });
});
