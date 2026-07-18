const APP_ORIGIN = "https://trace.invalid";
export const PENDING_EMAIL_CHANGE_PROOF_KEY = "trace:pending-email-change-proof:v1";
export const PENDING_PASSWORD_RESET_PROOF_KEY = "trace:pending-password-reset-proof:v1";
export const PASSWORD_RESET_PROOF_TTL_MS = 30 * 60 * 1_000;

export type EmailedLinkProof = {
  challengeId: string;
  token: string;
};

const PUBLIC_PATHS = new Set([
  "/",
  "/login",
  "/verify-email",
  "/forgot-password",
  "/reset-password",
  "/account/email-change",
  "/privacy",
  "/terms",
  "/accessibility",
  "/data-sources",
]);

/**
 * Read an emailed challenge from the browser URL. New links keep the secret in
 * the fragment so it is never included in an HTTP request or Referer header;
 * the query fallback supports links issued before that hardening shipped.
 */
export function emailedLinkProof(search: string, hash: string): EmailedLinkProof {
  const query = new URLSearchParams(search);
  const fragment = new URLSearchParams(hash.startsWith("#") ? hash.slice(1) : hash);
  return {
    challengeId: query.get("challengeId")?.trim() ?? "",
    token: fragment.get("token")?.trim() || query.get("token")?.trim() || "",
  };
}

/**
 * Recover a password-reset handoff after the proof has been scrubbed from the
 * address bar. The same-tab copy is bounded to 30 minutes after the learner
 * opens the link; the backend remains authoritative for issuance expiry.
 * Malformed, incomplete, or future-dated values fail closed.
 */
export function storedPasswordResetProof(
  raw: string | null,
  now = Date.now(),
): EmailedLinkProof | null {
  if (!raw) return null;
  try {
    const saved = JSON.parse(raw) as {
      challengeId?: unknown;
      token?: unknown;
      savedAt?: unknown;
    };
    if (
      typeof saved.challengeId !== "string"
      || typeof saved.token !== "string"
      || typeof saved.savedAt !== "number"
      || !Number.isFinite(saved.savedAt)
    ) {
      return null;
    }
    const age = now - saved.savedAt;
    const challengeId = saved.challengeId.trim();
    const token = saved.token.trim();
    if (
      age < 0
      || age >= PASSWORD_RESET_PROOF_TTL_MS
      || !challengeId
      || !token
    ) {
      return null;
    }
    return { challengeId, token };
  } catch {
    return null;
  }
}

/** Public pages must remain usable before (or without) a session check. */
export function isPublicEntryPath(pathname: string): boolean {
  return PUBLIC_PATHS.has(pathname);
}

/**
 * Resolve a post-auth destination against a fixed app origin. This rejects
 * absolute, protocol-relative, and backslash-authority URLs while preserving
 * an internal path's query and fragment.
 */
export function safeAppPath(requested: string | null | undefined, fallback = "/"): string {
  if (!requested) return fallback;
  try {
    const resolved = new URL(requested, `${APP_ORIGIN}/`);
    if (resolved.origin !== APP_ORIGIN || !resolved.pathname.startsWith("/")) return fallback;
    return `${resolved.pathname}${resolved.search}${resolved.hash}`;
  } catch {
    return fallback;
  }
}

/** Sign-in entry point for a specific private workspace. */
export function signInPath(next?: string | null): string {
  const destination = safeAppPath(next, "/home");
  const search = new URLSearchParams();
  if (destination !== "/home") search.set("next", destination);
  const query = search.toString();
  return query ? `/login?${query}` : "/login";
}

/** Explicit account-creation entry point used by public product CTAs. */
export function registrationPath(next?: string | null): string {
  const destination = safeAppPath(next, "/home");
  const search = new URLSearchParams({ mode: "register" });
  if (destination !== "/home") search.set("next", destination);
  return `/login?${search.toString()}`;
}
