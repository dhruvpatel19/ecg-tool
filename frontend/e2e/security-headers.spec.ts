import { expect, test } from "@playwright/test";
import { registerVerifiedE2ELearner } from "./helpers";

test("student pages enforce a nonce-based same-origin content policy", async ({ page, request }) => {
  const response = await request.get("/login");
  expect(response.ok()).toBeTruthy();

  const headers = response.headers();
  const csp = headers["content-security-policy"] ?? "";
  expect(csp).toContain("default-src 'self'");
  expect(csp).toMatch(/script-src 'self' 'nonce-[0-9a-f-]+'/);
  expect(csp).not.toContain("script-src 'self' 'unsafe-inline'");
  expect(csp).toContain("frame-ancestors 'none'");
  expect(csp).toContain("object-src 'none'");
  expect(csp).toContain("base-uri 'self'");
  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(headers["x-frame-options"]).toBe("DENY");
  expect(headers["referrer-policy"]).toBe("no-referrer");
  expect(headers["permissions-policy"]).toContain("camera=()");
  const nonce = csp.match(/script-src 'self' 'nonce-([0-9a-f-]+)'/)?.[1];
  expect(nonce).toBeTruthy();
  expect(await response.text()).toContain(`nonce="${nonce}"`);

  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await page.getByRole("tab", { name: "Register" }).click();
  await expect(page.getByRole("heading", { name: "Create your account" })).toBeVisible();
});

test("the foundations lesson alone may be framed by its same-origin host", async ({ page }) => {
  const anonymousHtml = await page.request.get("/foundations/index.html");
  const anonymousCases = await page.request.get("/foundations/data/cases.json");
  const anonymousScript = await page.request.get("/foundations/scenes.js");
  expect(anonymousHtml.status()).toBe(401);
  expect(anonymousCases.status()).toBe(401);
  expect(anonymousScript.status()).toBe(401);

  await registerVerifiedE2ELearner(page, { prefix: "security_headers" });
  const response = await page.request.get("/foundations/index.html");
  expect(response.ok(), await response.text()).toBeTruthy();

  const headers = response.headers();
  expect(headers["content-security-policy"]).toContain("frame-ancestors 'self'");
  expect(headers["x-frame-options"]).toBe("SAMEORIGIN");
  expect(headers["cache-control"]).toBe("private, no-store");
  expect(headers.vary).toContain("Cookie");

  const cases = await page.request.get("/foundations/data/cases.json");
  expect(cases.ok(), await cases.text()).toBeTruthy();
  expect(cases.headers()["cache-control"]).toBe("private, no-store");

  await page.goto("/foundations/index.html");
  await expect(page.getByRole("heading", { name: "Open Foundations from TRACE" })).toBeVisible();
  await expect(page.getByText("No guest learning state was opened.", { exact: false })).toBeVisible();
  expect(await page.evaluate(() => ({
    state: localStorage.getItem("foundations_state_v1:guest"),
    best: localStorage.getItem("found_best:guest"),
  }))).toEqual({ state: null, best: null });

  await page.goto("/learn/foundations");
  const lesson = page.frameLocator('iframe[title="Foundations of the ECG Read"]');
  await expect(lesson.locator("#tutorInput")).toBeVisible();
  await expect(lesson.locator("#tutorInput")).toHaveAttribute("maxlength", "4000");
  await expect(lesson.locator("#tutorPrivacy")).toContainText("Do not enter patient names");
});

test("the backend proxy rejects cross-site state changes before forwarding", async ({ request }) => {
  const response = await request.post("/api/backend/auth/logout", {
    headers: {
      Origin: "https://attacker.invalid",
      "Sec-Fetch-Site": "cross-site",
    },
  });
  expect(response.status()).toBe(403);
  await expect(response.json()).resolves.toMatchObject({ code: "cross_site_request_rejected" });
});

test("the backend proxy accepts the public next-start origin for same-origin mutations", async ({ request }) => {
  const baseUrl = process.env.E2E_BASE_URL ?? "http://localhost:3100";
  const response = await request.post("/api/backend/auth/logout", {
    headers: {
      Origin: new URL(baseUrl).origin,
      "Sec-Fetch-Site": "same-origin",
    },
  });

  expect(response.status()).toBe(200);
  await expect(response.json()).resolves.toMatchObject({ ok: true });
});

test("public backend probes stay minimal and never create learner identity", async ({ request }) => {
  const response = await request.get("/api/backend/health");
  expect(response.ok()).toBeTruthy();
  expect(await response.json()).toEqual({ ok: true });
  const headers = response.headers();
  expect(headers["set-cookie"]).toBeUndefined();
  expect(headers.server?.toLowerCase() ?? "").not.toContain("uvicorn");
  expect(headers["cache-control"]).toBe("no-store");
});
