import { test, expect } from "@playwright/test";

test.describe("auth", () => {
  test("keeps phone sign-in and account-creation controls touch-sized", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 780 });
    await page.goto("/login");
    const signInControls = [
      page.getByRole("tab", { name: "Sign in" }),
      page.getByRole("tab", { name: "Register" }),
      page.locator("#auth-email-signin"),
      page.locator("#auth-password"),
      page.getByRole("button", { name: "Sign in" }),
    ];
    for (const control of signInControls) {
      const box = await control.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.height).toBeGreaterThanOrEqual(44);
    }
    await page.getByRole("tab", { name: "Register" }).click();
    for (const control of [
      page.locator("#auth-email"),
      page.locator("#auth-password-confirm"),
      page.getByRole("button", { name: "Create account" }),
    ]) {
      const box = await control.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.height).toBeGreaterThanOrEqual(44);
    }
    await expect(page.getByText(/continue as guest|guest work/i)).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  });

  test("offers a positively identified earlier beta record only inside a verified account", async ({ page }) => {
    let claimCalls = 0;
    await page.route("**/api/backend/auth/me", (route) => route.fulfill({
      json: {
        authenticated: true,
        user: {
          userId: "u_beta_migration",
          username: "beta_migration",
          displayName: "Beta Learner",
          accountStatus: "verified",
          emailVerified: true,
        },
      },
    }));
    await page.route("**/api/backend/auth/sessions", (route) => route.fulfill({ json: { sessions: [] } }));
    await page.route("**/api/backend/auth/guest-progress", (route) => {
      return route.fulfill({
        json: {
          hasProgress: true,
          claimable: true,
          totalActivities: 17,
          attempts: 3,
          guidedInteractions: 4,
          competencyReceipts: 2,
          lessonScenes: 2,
          tutorThreads: 1,
          reviewSessions: 1,
          rapidRounds: 2,
          clinicalSessions: 1,
          trainingCampaigns: 1,
          competencies: 2,
          lastActivityAt: "2026-07-14T12:00:00+00:00",
        },
      });
    });
    await page.route("**/api/backend/auth/guest-progress/claim", (route) => {
      claimCalls += 1;
      return route.fulfill({
        json: {
          ok: true,
          guestClaim: {
            claimed: true,
            rotatedGuestId: true,
            guestProgress: { hasProgress: false, claimable: false, totalActivities: 0 },
          },
        },
      });
    });

    await page.goto("/account");
    await expect(page.getByRole("heading", { name: "Earlier browser learning found" })).toBeVisible();
    await expect(page.getByText(/An earlier beta version saved practice in this browser/i)).toBeVisible();
    await expect(page.getByText(/17 saved learning activities/i)).toBeVisible();
    expect(claimCalls).toBe(0);

    await page.getByRole("button", { name: "Attach to my account" }).click();
    await expect.poll(() => claimCalls).toBe(1);
    await expect(page.getByText("Earlier learning was attached to this account.")).toBeVisible();
  });

  test("lists sessions honestly, revokes one other session, and confirms sign out everywhere", async ({ page }) => {
    const currentSessionId = `ses_${"a".repeat(64)}`;
    const otherSessionId = `ses_${"b".repeat(64)}`;
    let sessions = [
      {
        sessionId: currentSessionId,
        createdAt: "2026-07-14T12:00:00+00:00",
        expiresAt: "2026-08-13T12:00:00+00:00",
        current: true,
      },
      {
        sessionId: otherSessionId,
        createdAt: "2026-07-13T09:30:00+00:00",
        expiresAt: "2026-08-12T09:30:00+00:00",
        current: false,
      },
    ];
    const revokedIds: string[] = [];
    let logoutAllCalls = 0;

    await page.route("**/api/backend/auth/me", (route) => route.fulfill({
      json: {
        authenticated: true,
        user: { userId: "u_session_ui", username: "session_ui", displayName: "Session Learner" },
      },
    }));
    await page.route("**/api/backend/auth/sessions", (route) => route.fulfill({ json: { sessions } }));
    await page.route("**/api/backend/auth/sessions/*", (route) => {
      const sessionId = decodeURIComponent(new URL(route.request().url()).pathname.split("/").at(-1) ?? "");
      revokedIds.push(sessionId);
      sessions = sessions.filter((session) => session.sessionId !== sessionId);
      return route.fulfill({ json: { ok: true, revokedSessionId: sessionId } });
    });
    await page.route("**/api/backend/auth/logout-all", (route) => {
      logoutAllCalls += 1;
      return route.fulfill({ json: { ok: true, revokedSessions: sessions.length } });
    });

    await page.goto("/account");
    await expect(page.getByRole("heading", { name: "Signed-in sessions" })).toBeVisible();
    const list = page.getByRole("list", { name: "Active sessions" });
    await expect(list.getByRole("listitem")).toHaveCount(2);
    await expect(list.getByText("This session", { exact: true })).toBeVisible();
    const otherRow = list.getByRole("listitem").filter({ hasText: "Other session" });
    await expect(otherRow).toContainText("Started");
    await expect(otherRow).toContainText("Expires");
    await expect(page.getByText(/Windows|macOS|Chrome|Safari|location:/i)).toHaveCount(0);

    await otherRow.getByRole("button", { name: /Sign out other session started/ }).click();
    await expect(page.getByText("Other session signed out.")).toBeVisible();
    await expect(page.getByText("1 active session", { exact: true })).toBeVisible();
    expect(revokedIds).toEqual([otherSessionId]);

    await page.getByRole("button", { name: "Sign out everywhere…" }).click();
    const confirmation = page.getByRole("group", { name: "Confirm sign out everywhere" });
    await expect(confirmation).toBeVisible();
    expect(logoutAllCalls).toBe(0);
    await confirmation.getByRole("button", { name: "Cancel" }).click();
    await expect(confirmation).toHaveCount(0);
    expect(logoutAllCalls).toBe(0);

    await page.getByRole("button", { name: "Sign out everywhere…" }).click();
    await page.getByRole("button", { name: "Confirm sign out everywhere" }).click();
    await expect.poll(() => logoutAllCalls).toBe(1);
    await expect(page.locator("main").getByRole("heading", { name: "Sign in" })).toBeVisible();
  });

  test("progress export requires an accessible password confirmation and supports a clean retry", async ({ page }) => {
    let authorizationCalls = 0;
    let exportCalls = 0;

    await page.route("**/api/backend/auth/me", (route) => route.fulfill({
      json: {
        authenticated: true,
        user: { userId: "u_export_ui", username: "export_ui", displayName: "Export Learner" },
      },
    }));
    await page.route("**/api/backend/auth/sessions", (route) => route.fulfill({ json: { sessions: [] } }));
    await page.route("**/api/backend/auth/export/authorize", async (route) => {
      authorizationCalls += 1;
      const body = route.request().postDataJSON() as { currentPassword: string };
      if (authorizationCalls === 1) {
        expect(body.currentPassword).toBe("wrong-password");
        return route.fulfill({
          status: 400,
          json: { detail: { field: "currentPassword", code: "invalid_current_password", message: "Current password is incorrect." } },
        });
      }
      expect(body.currentPassword).toBe("correct-password");
      return route.fulfill({ json: { ok: true, expiresAt: "2026-07-14T12:05:00+00:00" } });
    });
    await page.route("**/api/backend/auth/export", (route) => {
      exportCalls += 1;
      expect(route.request().method()).toBe("POST");
      return route.fulfill({
        json: {
          schemaVersion: "ecg-student-progress-v2",
          exportedAt: "2026-07-14T12:00:00+00:00",
          assessmentPrivacy: { pendingAndFutureAnswerContractsOmitted: true, note: "Protected" },
          account: { userId: "u_export_ui", username: "export_ui", displayName: "Export Learner", createdAt: "2026-07-01T00:00:00+00:00" },
          recordCounts: {},
          records: {},
        },
      });
    });

    await page.goto("/account");
    await page.getByRole("button", { name: "Download progress…" }).click();
    const form = page.getByRole("form", { name: "Confirm password to export" });
    await expect(form).toBeVisible();
    await expect(form.getByText(/one-time approval.*expires after five minutes/i)).toBeVisible();
    expect(exportCalls).toBe(0);

    const password = form.getByLabel("Current password", { exact: true });
    await password.fill("wrong-password");
    await form.getByRole("button", { name: "Confirm and download" }).click();
    await expect(form.getByRole("alert")).toContainText("That password is incorrect");
    await expect(password).toHaveValue("");
    await expect(password).toBeFocused();
    expect(exportCalls).toBe(0);

    await password.fill("correct-password");
    const downloadPromise = page.waitForEvent("download");
    await form.getByRole("button", { name: "Confirm and download" }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe("ecg-progress-export_ui.json");
    await expect(page.getByText("Your progress export is ready.")).toBeVisible();
    expect(authorizationCalls).toBe(2);
    expect(exportCalls).toBe(1);

    const browserReadableExportState = await page.evaluate(() => ({
      local: Object.keys(localStorage).filter((key) => key.toLowerCase().includes("export")),
      session: Object.keys(sessionStorage).filter((key) => key.toLowerCase().includes("export")),
    }));
    expect(browserReadableExportState).toEqual({ local: [], session: [] });
  });

});
