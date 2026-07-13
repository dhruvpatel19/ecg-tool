import { test, expect } from "@playwright/test";
import { randomUsername } from "./helpers";

test.describe("auth", () => {
  test("register a new user, see the logged-in state, then logout", async ({ page }) => {
    const username = randomUsername();
    const password = "Sup3r-Secret-Pw!";

    await page.goto("/login");
    await expect(page.locator("#auth-claim-progress")).toHaveCount(0);

    // Switch to the Register tab.
    await page.getByRole("button", { name: "Register" }).click();

    await page.locator("#auth-username").fill(username);
    await page.locator("#auth-display").fill("E2E Tester");
    await page.locator("#auth-password").fill(password);

    await page.getByRole("button", { name: "Create account" }).click();

    // On success we are redirected to the rebuilt dashboard and the nav shows the account.
    await expect(page.getByRole("heading", { name: "Build a read you can trust." })).toBeVisible({ timeout: 30_000 });

    const logout = page.getByRole("button", { name: "Sign out" });
    await expect(logout).toBeVisible();
    // The display name (or username) is shown in the nav account block.
    await expect(page.locator(".nav-account-name")).toContainText("E2E Tester");

    // The reusable credential is an HttpOnly cookie and is never persisted in
    // browser-readable storage.
    const token = await page.evaluate(() => window.localStorage.getItem("ecg_token"));
    expect(token).toBeNull();
    const sessionCookie = (await page.context().cookies()).find((cookie) => cookie.name === "ecg_session");
    expect(sessionCookie, "expected the backend session cookie after register").toBeTruthy();
    expect(sessionCookie?.httpOnly).toBe(true);
    expect(sessionCookie?.sameSite).toBe("Lax");

    // A full reload hydrates the account through GET /auth/me and the cookie.
    await page.reload();
    await expect(page.locator(".nav-account-name")).toContainText("E2E Tester");
    await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();

    // Sign out returns to demo mode (Sign in link reappears).
    await logout.click();
    await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible();
    const clearedCookies = (await page.context().cookies()).filter((cookie) => cookie.name === "ecg_session");
    expect(clearedCookies).toHaveLength(0);
  });

  test("guest work is offered explicitly, off by default, and claimed once", async ({ page }) => {
    const username = randomUsername("guest_claim");
    const password = "Sup3r-Secret-Pw!";
    const pathwayId = `claim-e2e-${Date.now()}`;

    const seeded = await page.request.post("/api/backend/learners/demo/pathway-progress", {
      data: {
        learnerId: "demo",
        source: "server",
        merge: true,
        items: [{
          pathwayId,
          moduleId: "claim-module",
          sceneId: "claim-scene",
          status: "complete",
          activeInteractionIndex: 2,
          completedActionIds: ["claim-action"],
          state: { source: "guest-e2e" },
        }],
      },
    });
    expect(seeded.ok()).toBe(true);
    const originalGuest = (await page.context().cookies()).find((cookie) => cookie.name === "ecg_guest");
    expect(originalGuest, "expected a guest owner cookie before account creation").toBeTruthy();

    await page.goto("/login");
    const claim = page.getByLabel("Save this browser’s guest work to my account");
    await expect(claim).toBeVisible();
    await expect(claim).not.toBeChecked();
    await expect(page.getByText(/1 saved learning records include/)).toBeVisible();

    await page.getByRole("button", { name: "Register" }).click();
    await expect(claim).not.toBeChecked();
    await claim.check();
    await page.locator("#auth-username").fill(username);
    await page.locator("#auth-display").fill("Guest Claim Learner");
    await page.locator("#auth-password").fill(password);
    await page.getByRole("button", { name: "Create account" }).click();

    await expect(page.getByRole("heading", { name: "Build a read you can trust." })).toBeVisible({ timeout: 30_000 });
    const cookies = await page.context().cookies();
    const rotatedGuest = cookies.find((cookie) => cookie.name === "ecg_guest");
    expect(rotatedGuest?.value).toBeTruthy();
    expect(rotatedGuest?.value).not.toBe(originalGuest?.value);
    expect(rotatedGuest?.httpOnly).toBe(true);

    const accountProgressResponse = await page.request.get(
      `/api/backend/learners/demo/pathway-progress?pathwayId=${encodeURIComponent(pathwayId)}`,
    );
    expect(accountProgressResponse.ok()).toBe(true);
    const accountProgress = await accountProgressResponse.json() as {
      items: Array<{ pathwayId: string; status: string; state: Record<string, unknown> }>;
    };
    expect(accountProgress.items).toEqual(expect.arrayContaining([
      expect.objectContaining({
        pathwayId,
        status: "complete",
        state: expect.objectContaining({ source: "guest-e2e" }),
      }),
    ]));

    const freshGuestSummary = await (await page.request.get("/api/backend/auth/guest-progress")).json() as {
      hasProgress: boolean;
      totalActivities: number;
    };
    expect(freshGuestSummary).toMatchObject({ hasProgress: false, totalActivities: 0 });
  });

  test("switching accounts remounts private UI and cannot restore another learner's Rapid draft", async ({ page }) => {
    const password = "Sup3r-Secret-Pw!";
    const register = async (username: string, displayName: string) => {
      await page.goto("/login");
      await page.getByRole("button", { name: "Register" }).click();
      await page.locator("#auth-username").fill(username);
      await page.locator("#auth-display").fill(displayName);
      await page.locator("#auth-password").fill(password);
      await page.getByRole("button", { name: "Create account" }).click();
      await expect(page.locator(".nav-account-name")).toContainText(displayName);
    };

    await register(randomUsername("owner_a"), "Learner A");
    const learnerA = await page.evaluate(async () => {
      const response = await fetch("/api/backend/auth/me");
      return (await response.json()) as { user: { userId: string } };
    });
    await page.goto("/profile");
    await expect(page.getByRole("heading", { name: "Learner A progress" })).toBeVisible();

    // Seed a valid completed-round snapshot under A's server identity. B must
    // never read it, even in the same tab and browser storage partition.
    await page.evaluate((ownerKey) => {
      sessionStorage.setItem(`ecg-tool:rapid-round:v2:${ownerKey}`, JSON.stringify({
        version: 2,
        ownerKey,
        context: "",
        view: "complete",
        paceId: "ward",
        sessionLength: 5,
        caseIndex: 1,
        caseSummary: null,
        packet: null,
        sweep: { rate: "", rhythm: "", axis: "", intervals: "", conduction: "", st_t: "", chambers: "", synthesis: "" },
        selectedConcepts: [],
        confidence: 3,
        grade: null,
        caseCoach: null,
        aiViewerActions: [],
        traceEvidence: null,
        traceReceipt: "",
        handoffReceipt: "",
        results: [{ caseId: "private-a", displayId: "PRIVATE A", score: 1, timedOut: false, responseMs: 1000, correctObjectives: [], missedObjectives: [], overcalledObjectives: [], misconceptions: [], revealedDiagnosis: "" }],
        startedAtEpochMs: null,
        deadlineAtEpochMs: null,
      }));
    }, learnerA.user.userId);

    await page.getByRole("button", { name: "Sign out" }).click();
    await register(randomUsername("owner_b"), "Learner B");
    await page.goto("/rapid");

    await expect(page.getByRole("heading", { name: "Rapid ECG rounds" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Start ward read" })).toBeVisible();
    await expect(page.getByText("PRIVATE A")).toHaveCount(0);
    await page.goto("/profile");
    await expect(page.getByRole("heading", { name: "Learner B progress" })).toBeVisible();
    await expect(page.getByText("Learner A progress")).toHaveCount(0);
  });
});
