import { expect, test, type Page, type Route } from "@playwright/test";

const signedOut = { authenticated: false, user: null };

async function mockSignedOut(page: Page) {
  await page.route("**/api/backend/auth/me", (route) => route.fulfill({ json: signedOut }));
}

async function waitForSignInHydration(page: Page) {
  const password = page.locator("#auth-password");
  const toggle = page.getByRole("button", { name: "Show password" });
  await expect(async () => {
    await toggle.click();
    await expect(password).toHaveAttribute("type", "text", { timeout: 750 });
  }).toPass({ timeout: 15_000 });
  await page.getByRole("button", { name: "Hide password" }).click();
  await expect(password).toHaveAttribute("type", "password");
}

test.describe("account-required route boundary", () => {
  test("keeps the landing and sign-in pages usable while session verification is pending", async ({ page }) => {
    const guestRequests: string[] = [];
    page.on("request", (request) => {
      if (request.url().includes("/auth/guest-progress")) guestRequests.push(request.url());
    });

    for (const entry of [
      { path: "/", heading: "Read ECGs with a method you can trust." },
      { path: "/login?mode=register", heading: "Create your account" },
    ] as const) {
      let releaseSessionCheck = () => {};
      const gate = new Promise<void>((resolve) => { releaseSessionCheck = resolve; });
      let sessionChecks = 0;
      const handler = async (route: Route) => {
        sessionChecks += 1;
        await gate;
        await route.fulfill({ json: signedOut });
      };
      await page.route("**/api/backend/auth/me", handler);

      await page.goto(entry.path, { waitUntil: "domcontentloaded" });
      await expect.poll(() => sessionChecks).toBe(1);
      await expect(page.getByRole("heading", { name: entry.heading })).toBeVisible({ timeout: 2_000 });
      if (entry.path.startsWith("/login")) {
        const createAccount = page.getByRole("button", { name: "Create account", exact: true });
        const credentialForm = createAccount.locator("xpath=ancestor::form");
        await expect(credentialForm).toHaveAttribute("method", "post");
        await expect(credentialForm).toHaveAttribute("action", "/login");
        await expect(createAccount).toBeEnabled();
      }

      releaseSessionCheck();
      await expect.poll(() => sessionChecks).toBe(1);
      await page.unroute("**/api/backend/auth/me", handler);
    }

    expect(guestRequests).toEqual([]);
  });

  test("redirects every private student area to sign in without mounting it", async ({ page }) => {
    await mockSignedOut(page);
    const unexpectedPrivateRequests: string[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.pathname.startsWith("/api/backend/") && url.pathname !== "/api/backend/auth/me") {
        unexpectedPrivateRequests.push(url.pathname);
      }
    });

    const destinations = [
      { requested: "/learn", next: "/learn" },
      { requested: "/learn/foundations", next: "/learn/foundations" },
      { requested: "/train?concept=atrial_fibrillation", next: "/train?concept=atrial_fibrillation" },
      { requested: "/rapid", next: "/rapid" },
      { requested: "/practice", next: "/practice" },
      // The default destination is intentionally omitted from the query.
      { requested: "/home", next: null },
      { requested: "/home/review/lsr1_boundary_test", next: "/home/review/lsr1_boundary_test" },
      // The legacy profile shell is guarded before its page-level redirect.
      { requested: "/profile?tab=plan", next: "/profile?tab=plan" },
      { requested: "/account", next: "/account" },
      { requested: "/review", next: "/home?panel=plan" },
    ];

    for (const destination of destinations) {
      await page.goto(destination.requested);
      await expect.poll(() => {
        const url = new URL(page.url());
        return {
          pathname: url.pathname,
          mode: url.searchParams.get("mode"),
          next: url.searchParams.get("next"),
        };
      }).toEqual({ pathname: "/login", mode: null, next: destination.next });
      await expect(page.getByRole("heading", { name: "Sign in", exact: true })).toBeVisible();
      await expect(page.locator(".side-nav")).toHaveCount(0);
      await expect(page.getByText(/continue as guest|guest learner/i)).toHaveCount(0);
    }

    expect(unexpectedPrivateRequests).toEqual([]);
  });

  test("does not release the embedded Foundations application or PTB bundle directly", async ({ page }) => {
    await mockSignedOut(page);

    for (const path of [
      "/foundations",
      "/foundations/index.html",
      "/foundations/scenes.js",
      "/foundations/data/cases.json",
    ]) {
      const response = await page.request.get(path, { maxRedirects: 0 });
      expect(response.status(), path).toBe(401);
      await expect(response.json()).resolves.toMatchObject({ code: "authentication_required" });
      expect(response.headers()["cache-control"]).toBe("private, no-store");
    }
  });

  test("public mode cards carry an encoded private destination into registration", async ({ page }) => {
    await mockSignedOut(page);
    await page.goto("/");

    const guidedLink = page.getByRole("link", { name: "Create an account to start guided learning" });
    await expect(guidedLink).toHaveAttribute("href", "/login?mode=register&next=%2Flearn");
    await guidedLink.click();

    await expect(page).toHaveURL((url) => (
      url.pathname === "/login"
      && url.searchParams.get("mode") === "register"
      && url.searchParams.get("next") === "/learn"
    ));
    await expect(page.getByRole("tab", { name: "Register" })).toHaveAttribute("aria-selected", "true");
  });

  test("sanitizes a hostile post-auth destination and exposes no guest entry", async ({ page }) => {
    await mockSignedOut(page);
    await page.route("**/api/backend/auth/login", (route) => route.fulfill({
      json: {
        user: { userId: "u_boundary", username: "boundary", displayName: "Boundary Learner" },
        guestClaim: null,
      },
    }));

    const hostile = encodeURIComponent("/\\\\attacker.example/private");
    await page.goto(`/login?next=${hostile}`);
    await expect(page.getByText(/continue as guest|guest work|guest learner/i)).toHaveCount(0);
    await waitForSignInHydration(page);
    await page.locator("#auth-email-signin").fill("boundary@example.test");
    await page.locator("#auth-password").fill("correct horse battery staple");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();

    await expect(page).toHaveURL((url) => url.pathname === "/home" && url.hostname === "localhost");
  });

  test("an explicit sign-in wins over a slower stale session check", async ({ page }) => {
    let releaseSessionCheck = () => {};
    const gate = new Promise<void>((resolve) => { releaseSessionCheck = resolve; });
    await page.route("**/api/backend/auth/me", async (route) => {
      await gate;
      await route.fulfill({ json: signedOut });
    });
    await page.route("**/api/backend/auth/login", (route) => route.fulfill({
      json: {
        user: { userId: "u_slow_check", username: "slow_check", displayName: "Verified Learner" },
        guestClaim: null,
      },
    }));

    await page.goto("/login?next=%2Fprofile", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeEnabled();
    await waitForSignInHydration(page);
    await page.locator("#auth-email-signin").fill("slow-check@example.test");
    await page.locator("#auth-password").fill("correct horse battery staple");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();

    await expect(page).toHaveURL((url) => url.pathname === "/home");
    await expect(page.locator(".nav-account-name")).toContainText("Verified Learner");
    releaseSessionCheck();
    await page.waitForTimeout(100);
    await expect(page).toHaveURL((url) => url.pathname === "/home");
    await expect(page.locator(".nav-account-name")).toContainText("Verified Learner");
  });
});
