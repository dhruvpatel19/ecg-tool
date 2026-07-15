const APP_ORIGIN = "https://trace.invalid";
export const PENDING_EMAIL_CHANGE_PROOF_KEY = "trace:pending-email-change-proof:v1";

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
export function emailedLinkProof(search: string, hash: string): { challengeId: string; token: string } {
  const query = new URLSearchParams(search);
  const fragment = new URLSearchParams(hash.startsWith("#") ? hash.slice(1) : hash);
  return {
    challengeId: query.get("challengeId")?.trim() ?? "",
    token: fragment.get("token")?.trim() || query.get("token")?.trim() || "",
  };
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
  const destination = safeAppPath(next, "/dashboard");
  const search = new URLSearchParams();
  if (destination !== "/dashboard") search.set("next", destination);
  const query = search.toString();
  return query ? `/login?${query}` : "/login";
}

/** Explicit account-creation entry point used by public product CTAs. */
export function registrationPath(next?: string | null): string {
  const destination = safeAppPath(next, "/dashboard");
  const search = new URLSearchParams({ mode: "register" });
  if (destination !== "/dashboard") search.set("next", destination);
  return `/login?${search.toString()}`;
}
