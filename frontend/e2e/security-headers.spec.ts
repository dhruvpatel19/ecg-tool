import { expect, test } from "@playwright/test";

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
  expect(headers["referrer-policy"]).toBe("strict-origin-when-cross-origin");
  expect(headers["permissions-policy"]).toContain("camera=()");
  const nonce = csp.match(/script-src 'self' 'nonce-([0-9a-f-]+)'/)?.[1];
  expect(nonce).toBeTruthy();
  expect(await response.text()).toContain(`nonce="${nonce}"`);

  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await page.getByRole("button", { name: "Register" }).click();
  await expect(page.getByRole("heading", { name: "Create your account" })).toBeVisible();
});

test("the foundations lesson alone may be framed by its same-origin host", async ({ page, request }) => {
  const response = await request.get("/foundations/index.html");
  expect(response.ok()).toBeTruthy();

  const headers = response.headers();
  expect(headers["content-security-policy"]).toContain("frame-ancestors 'self'");
  expect(headers["x-frame-options"]).toBe("SAMEORIGIN");

  await page.goto("/learn/foundations");
  const lesson = page.frameLocator('iframe[title="Foundations — Reading an ECG"]');
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

test("public backend probes stay minimal and never create learner identity", async ({ request }) => {
  const response = await request.get("/api/backend/health");
  expect(response.ok()).toBeTruthy();
  expect(await response.json()).toEqual({ ok: true });
  const headers = response.headers();
  expect(headers["set-cookie"]).toBeUndefined();
  expect(headers.server?.toLowerCase() ?? "").not.toContain("uvicorn");
  expect(headers["cache-control"]).toBe("no-store");
});
