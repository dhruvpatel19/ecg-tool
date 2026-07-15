import type { Page } from "@playwright/test";

export function isOpaqueEcgCapability(value: unknown): value is string {
  return typeof value === "string" && /^ec_[A-Za-z0-9_-]{12,}$/.test(value);
}

/**
 * Subscribe to console + page errors and return a growing array of error strings.
 * Filters out benign noise (favicon 404s, React DevTools hint, HMR chatter) so a
 * non-empty result is a real regression.
 */
export function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  const ignore = [
    /favicon/i,
    /Download the React DevTools/i,
    /\[Fast Refresh\]/i,
    /websocket/i,
  ];
  const keep = (text: string) => !ignore.some((re) => re.test(text));

  page.on("console", (message) => {
    if (message.type() === "error") {
      const text = message.text();
      if (keep(text)) errors.push(text);
    }
  });
  page.on("pageerror", (error) => {
    const text = error.message;
    if (keep(text)) errors.push(text);
  });
  return errors;
}

/** A username unlikely to collide across runs, for the auth registration test. */
export function randomUsername(prefix = "e2e"): string {
  const suffix = `${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
  const safePrefix = prefix
    .replace(/[^A-Za-z0-9_.-]/g, "_")
    .slice(0, Math.max(3, 32 - suffix.length - 1));
  return `${safePrefix}_${suffix}`;
}

export type VerifiedE2ELearner = {
  username: string;
  password: string;
  user: {
    userId: string;
    username: string;
    displayName: string | null;
    accountStatus: "verified";
    emailMasked: string;
    emailVerified: true;
    emailTwoFactorEnabled: false;
  };
};

type VerifiedLearnerOptions = {
  prefix?: string;
  username?: string;
  password?: string;
  displayName?: string;
};

async function presentVerifiedOwner(page: Page, payload: {
  userId: string;
  username: string;
  displayName?: string | null;
}): Promise<VerifiedE2ELearner["user"]> {
  const user: VerifiedE2ELearner["user"] = {
    userId: payload.userId,
    username: payload.username,
    displayName: payload.displayName ?? null,
    accountStatus: "verified",
    emailMasked: "e***@example.test",
    emailVerified: true,
    emailTwoFactorEnabled: false,
  };
  // Mode suites exercise owner isolation and durable learning APIs, not email
  // delivery. The backend test fixture supplies the real HttpOnly owner cookie;
  // this route prevents the product's legacy-email upgrade screen from hiding
  // the mode under test. Email registration/verification has its own E2E suite.
  await page.route("**/api/backend/auth/me", (route) => route.fulfill({
    json: { authenticated: true, user },
  }));
  return user;
}

/**
 * Create a durable owner for a real-backend mode test.
 *
 * The backend must run with APP_ENV=test, whose internal registration branch
 * intentionally avoids external email delivery. Deployed registration remains
 * verification-required and is covered separately by email-auth.spec.ts.
 */
export async function registerVerifiedE2ELearner(
  page: Page,
  options: VerifiedLearnerOptions = {},
): Promise<VerifiedE2ELearner> {
  const username = options.username ?? randomUsername(options.prefix ?? "verified_e2e");
  const password = options.password ?? "Sup3r-Secret-Pw!";
  const response = await page.request.post("/api/backend/auth/register", {
    data: { username, password, displayName: options.displayName },
  });
  if (!response.ok()) {
    throw new Error(
      `Verified E2E owner setup failed (${response.status()}). `
      + `Run the isolated browser backend with APP_ENV=test. ${await response.text()}`,
    );
  }
  const body = await response.json() as {
    user?: { userId?: string; username?: string; displayName?: string | null };
  };
  if (!body.user?.userId || !body.user.username) {
    throw new Error("Verified E2E owner setup returned no authenticated user.");
  }
  const user = await presentVerifiedOwner(page, {
    userId: body.user.userId,
    username: body.user.username,
    displayName: body.user.displayName,
  });
  return { username, password, user };
}

/** Restore an existing test owner and refresh the UI's verified-owner view. */
export async function signInVerifiedE2ELearner(
  page: Page,
  credentials: Pick<VerifiedE2ELearner, "username" | "password">,
): Promise<VerifiedE2ELearner> {
  const response = await page.request.post("/api/backend/auth/login", {
    data: { identifier: credentials.username, password: credentials.password },
  });
  if (!response.ok()) {
    throw new Error(`Verified E2E owner sign-in failed (${response.status()}). ${await response.text()}`);
  }
  const body = await response.json() as {
    user?: { userId?: string; username?: string; displayName?: string | null };
  };
  if (!body.user?.userId || !body.user.username) {
    throw new Error("Verified E2E owner sign-in returned no authenticated user.");
  }
  const user = await presentVerifiedOwner(page, {
    userId: body.user.userId,
    username: body.user.username,
    displayName: body.user.displayName,
  });
  return { ...credentials, user };
}

/** Choose a trace point from raw waveform samples without consulting answer ROIs. */
export async function strongestWaveformPoint(
  page: Page,
  ecgRef: string,
  lead: string,
  startSec = 0,
  endSec = 10,
  scope?:
    | { mode: "training"; sessionId: string }
    | { mode: "rapid"; sessionId: string }
    | { mode: "clinical"; sessionId: string },
): Promise<{ lead: string; timeSec: number; amplitudeMv: number }> {
  const encodedRef = encodeURIComponent(ecgRef);
  const path = scope?.mode === "training"
    ? `/api/backend/training/campaigns/${encodeURIComponent(scope.sessionId)}/waveform/${encodedRef}`
    : scope?.mode === "rapid"
      ? `/api/backend/rapid/rounds/${encodeURIComponent(scope.sessionId)}/waveform/${encodedRef}`
      : scope?.mode === "clinical"
        ? `/api/backend/clinical/shift/${encodeURIComponent(scope.sessionId)}/waveform/${encodedRef}`
        : `/api/backend/cases/${encodedRef}/waveform`;
  const response = await page.request.get(
    `${path}?leads=${encodeURIComponent(lead)}&start=${startSec}&end=${endSec}&maxPoints=5000`,
  );
  if (!response.ok()) throw new Error(`Waveform request failed for the scoped ECG capability (${response.status()}).`);
  const waveform = await response.json() as {
    leads?: Array<{ lead: string; points: Array<{ timeSec: number; amplitudeMv: number }> }>;
  };
  const points = waveform.leads?.find((candidate) => candidate.lead === lead)?.points ?? [];
  if (!points.length) throw new Error(`No ${lead} waveform samples were returned for the requested ECG capability.`);
  const point = points.reduce((strongest, candidate) => (
    Math.abs(candidate.amplitudeMv) > Math.abs(strongest.amplitudeMv) ? candidate : strongest
  ));
  return { lead, ...point };
}
