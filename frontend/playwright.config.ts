import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright E2E config for the ECG learning platform frontend.
 *
 * These tests drive the REAL app against a REAL backend. They are not run as part
 * of `npm run build`/`typecheck` — they need a live backend.
 *
 * How to run (from frontend/):
 *   1. Start the backend so it listens on http://127.0.0.1:8000
 *      (see backend/** for how to start it).
 *   2. Install browsers once:   npx playwright install
 *   3. Run the suite:           npm run e2e
 *      (or interactively:        npm run e2e:ui)
 *
 * The `webServer` block below boots the Next.js dev server for you and points its
 * same-origin proxy (/api/backend/*) at the backend via ECG_BACKEND_API_BASE.
 * Override the backend URL with E2E_BACKEND_BASE, or the app URL with E2E_BASE_URL.
 */

// Use localhost (not 127.0.0.1): Next.js dev treats a 127.0.0.1 page origin as a
// cross-origin dev request and blocks some resources, which broke the e2e run.
const BACKEND_BASE = process.env.E2E_BACKEND_BASE ?? "http://localhost:8000";
const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:3100";
const PORT = new URL(BASE_URL).port || "3100";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? "list" : [["list"], ["html", { open: "never" }]],
  timeout: 60_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    actionTimeout: 15_000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  // Boot the dev server with the proxy wired to the backend. Reuse a server that is
  // already running locally so you can keep `npm run dev` open while iterating.
  webServer: {
    // Invoke through npm so the project-local Next binary resolves on Windows
    // as well as Linux CI. Calling `next` directly only worked when an older
    // server already happened to be listening on the test port.
    command: `npx next dev --port ${PORT}`,
    url: BASE_URL,
    timeout: 120_000,
    reuseExistingServer: !process.env.CI,
    env: {
      ECG_BACKEND_API_BASE: BACKEND_BASE,
      // Never let an E2E dev server replace the production `.next` directory
      // used by a concurrently running local demo (`next start`).
      NEXT_DIST_DIR: `.next-e2e-${PORT}`,
    },
  },
});
