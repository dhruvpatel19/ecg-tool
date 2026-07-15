"use client";

import { Fragment, createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { api, type AuthAttemptResponse, type EmailVerificationConfirmationResponse, type GuestClaimReceipt } from "./api";
import { clearGuestLearningPreferencesMarker } from "./learningPreferences";
import { emailedLinkProof, isPublicEntryPath, PENDING_EMAIL_CHANGE_PROOF_KEY, signInPath } from "./routeAccess";
import type { User } from "./types";

type AuthContextValue = {
  user: User | null;
  /** True while GET /auth/me hydrates the HttpOnly cookie session. */
  loading: boolean;
  /** Stable owner key for learner-scoped browser state. Never use a display name here. */
  identityKey: string;
  /** Changes whenever the effective browser identity changes, forcing private UI state to remount. */
  authEpoch: number;
  login: (identifier: string, password: string) => Promise<AuthAttemptResponse>;
  register: (email: string, password: string, displayName?: string) => Promise<AuthAttemptResponse>;
  confirmEmailVerification: (challengeId: string, token: string, password: string) => Promise<EmailVerificationConfirmationResponse>;
  refreshUser: () => Promise<User | null>;
  logout: () => Promise<void>;
  logoutAll: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

/** Remove browser-readable state owned by one authenticated learner only. */
export function clearAuthenticatedBrowserState(userId: string): boolean {
  if (typeof window === "undefined") return true;
  const authenticatedOwner = userId.startsWith("u_");
  const localKeys = [
    ...(authenticatedOwner
      ? [`foundations_state_v1:${userId}`, `found_best:${userId}`]
      : []),
    // Retired Guided clients used unscoped keys. They must not survive an
    // identity transition and appear under the next learner.
    "trace-production-curriculum-v1",
    "trace-guided-scene-progress-v3",
  ];
  const sessionKeys = authenticatedOwner ? [`ecg-tool:rapid-round:v2:${userId}`] : [];
  let cleared = true;
  for (const [readStorage, keys] of [
    [() => window.localStorage, localKeys],
    [() => window.sessionStorage, sessionKeys],
  ] as const) {
    let storage: Storage;
    try {
      storage = readStorage();
    } catch {
      cleared = false;
      continue;
    }
    for (const key of keys) {
      try {
        storage.removeItem(key);
      } catch {
        cleared = false;
      }
    }
  }
  return cleared;
}

/** Remove browser caches from the retired anonymous beta after server attach/discard. */
export function clearEarlierBrowserLearningState(): boolean {
  if (typeof window === "undefined") return true;
  let cleared = true;
  const localKeys = [
    "foundations_state_v1:guest",
    "found_best:guest",
    "foundations_state_v1",
    "found_best",
    "trace-production-curriculum-v1",
    "trace-guided-scene-progress-v3",
    "trace:guest-learning-preferences",
  ];
  const sessionKeys = ["ecg-tool:rapid-round:v2:guest"];
  for (const [readStorage, keys] of [
    [() => window.localStorage, localKeys],
    [() => window.sessionStorage, sessionKeys],
  ] as const) {
    try {
      const storage = readStorage();
      keys.forEach((key) => storage.removeItem(key));
    } catch {
      cleared = false;
    }
  }
  return cleared;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const publicEntry = isPublicEntryPath(pathname);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [verificationError, setVerificationError] = useState<string | null>(null);
  const [verificationAttempt, setVerificationAttempt] = useState(0);
  const [authEpoch, setAuthEpoch] = useState(0);
  const identityRef = useRef("guest");
  const explicitSessionRevisionRef = useRef(0);

  // Email-change confirmation is a public proof handoff until the HttpOnly
  // session is known. Capture the fragment secret and erase the entire proof
  // URL during layout, before the passive /auth/me hydration request can run.
  useLayoutEffect(() => {
    if (pathname !== "/account/email-change" || typeof window === "undefined") return;
    const proof = emailedLinkProof(window.location.search, window.location.hash);
    if (proof.challengeId && proof.token) {
      try {
        window.sessionStorage.setItem(
          PENDING_EMAIL_CHANGE_PROOF_KEY,
          JSON.stringify({ ...proof, savedAt: Date.now() }),
        );
      } catch {
        // The mounted confirmation page retains the proof in memory. Never
        // fall back to putting the secret into a sign-in query string.
      }
    }
    if (window.location.search || window.location.hash) {
      window.history.replaceState(window.history.state, "", "/account/email-change");
    }
  }, [pathname]);

  const transitionIdentity = useCallback((nextUser: User | null) => {
    const nextIdentity = nextUser?.userId ?? "guest";
    if (identityRef.current !== nextIdentity) {
      identityRef.current = nextIdentity;
      setAuthEpoch((value) => value + 1);
    }
    setUser(nextUser);
  }, []);

  const acceptAuthenticatedUser = useCallback((nextUser: User, guestClaim?: GuestClaimReceipt | null) => {
    if (guestClaim && typeof window !== "undefined") {
      clearEarlierBrowserLearningState();
      clearGuestLearningPreferencesMarker();
    }
    if (identityRef.current !== nextUser.userId) {
      clearAuthenticatedBrowserState(identityRef.current);
    }
    explicitSessionRevisionRef.current += 1;
    setVerificationError(null);
    setLoading(false);
    transitionIdentity(nextUser);
  }, [transitionIdentity]);

  // The credential is HttpOnly, so the only safe hydration check is /auth/me.
  useEffect(() => {
    let cancelled = false;
    const sessionRevision = explicitSessionRevisionRef.current;
    setLoading(true);
    setVerificationError(null);
    api
      .me()
      .then((res) => {
        if (cancelled || explicitSessionRevisionRef.current !== sessionRevision) return;
        if (res.authenticated && res.user) {
          transitionIdentity(res.user);
        } else {
          transitionIdentity(null);
        }
      })
      .catch(() => {
        if (cancelled || explicitSessionRevisionRef.current !== sessionRevision) return;
        // A transport failure does not prove the HttpOnly session is absent.
        // Keep all stateful pages unmounted until identity can be verified.
        setVerificationError("Your private session could not be verified. No learner data has been opened.");
      })
      .finally(() => {
        if (!cancelled && explicitSessionRevisionRef.current === sessionRevision) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [transitionIdentity, verificationAttempt]);

  useEffect(() => {
    if (loading || verificationError || user) return;
    if (pathname === "/account/email-change") {
      router.replace(signInPath("/account/email-change"));
      return;
    }
    if (publicEntry) return;
    const requested = typeof window === "undefined"
      ? pathname
      : `${window.location.pathname}${window.location.search}${window.location.hash}`;
    router.replace(signInPath(requested));
  }, [loading, pathname, publicEntry, router, user, verificationError]);

  const accountSetupRedirect = Boolean(
    user?.accountStatus
    && user.accountStatus !== "verified"
    && !["/account", "/account/email-change", "/login", "/verify-email", "/forgot-password", "/reset-password"].includes(pathname),
  );

  useEffect(() => {
    if (accountSetupRedirect) router.replace("/account?setup=email");
  }, [accountSetupRedirect, router]);

  const login = useCallback(
    async (identifier: string, password: string) => {
      const res = await api.login({ identifier, password });
      if ("user" in res) acceptAuthenticatedUser(res.user, res.guestClaim);
      return res;
    },
    [acceptAuthenticatedUser],
  );

  const register = useCallback(
    async (email: string, password: string, displayName?: string) => {
      const res = await api.register({ password, email, displayName });
      if ("user" in res) acceptAuthenticatedUser(res.user, res.guestClaim);
      return res;
    },
    [acceptAuthenticatedUser],
  );

  const confirmEmailVerification = useCallback(async (challengeId: string, token: string, password: string) => {
    const res = await api.confirmEmailVerification({ challengeId, token, password });
    if ("accountResolutionRequired" in res) return res;
    acceptAuthenticatedUser(res.user, res.guestClaim);
    return res;
  }, [acceptAuthenticatedUser]);

  const refreshUser = useCallback(async () => {
    const res = await api.me();
    if (res.authenticated && res.user) {
      acceptAuthenticatedUser(res.user);
      return res.user;
    }
    // An authoritative signed-out response means the HttpOnly session was
    // revoked, expired, or deleted elsewhere. Evict the prior owner and every
    // browser-readable private draft before the private route guard reruns.
    clearAuthenticatedBrowserState(identityRef.current);
    explicitSessionRevisionRef.current += 1;
    setVerificationError(null);
    setLoading(false);
    transitionIdentity(null);
    return null;
  }, [acceptAuthenticatedUser, transitionIdentity]);

  const logout = useCallback(async () => {
    // Do not present a signed-out UI while the HttpOnly cookie may still authorize
    // requests as the prior student. A failed server revocation leaves the
    // current identity mounted and lets the caller surface a retry.
    await api.logout();
    clearAuthenticatedBrowserState(identityRef.current);
    explicitSessionRevisionRef.current += 1;
    setVerificationError(null);
    setLoading(false);
    transitionIdentity(null);
  }, [transitionIdentity]);

  const logoutAll = useCallback(async () => {
    await api.logoutAll();
    clearAuthenticatedBrowserState(identityRef.current);
    explicitSessionRevisionRef.current += 1;
    setVerificationError(null);
    setLoading(false);
    transitionIdentity(null);
  }, [transitionIdentity]);

  const identityKey = user?.userId ?? "guest";

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      identityKey,
      authEpoch,
      login,
      register,
      confirmEmailVerification,
      refreshUser,
      logout,
      logoutAll,
    }),
    [
      user,
      loading,
      identityKey,
      authEpoch,
      login,
      register,
      confirmEmailVerification,
      refreshUser,
      logout,
      logoutAll,
    ],
  );

  // Hydrate the HttpOnly account identity before mounting stateful pages. This
  // prevents concurrent first-load API calls and a prior learner-data flash.
  if (accountSetupRedirect || (!publicEntry && (loading || verificationError || !user))) {
    return (
      <AuthContext.Provider value={value}>
        <div className="auth-session-loader" role="status" aria-live="polite">
          <span className="status-orb" aria-hidden="true" />
          <strong>{verificationError ?? (loading ? "Opening your learning workspace…" : "Taking you to account setup…")}</strong>
          {verificationError ? (
            <button className="button subtle small" type="button" onClick={() => setVerificationAttempt((value) => value + 1)}>
              Retry session check
            </button>
          ) : null}
        </div>
      </AuthContext.Provider>
    );
  }

  // Pages and tutor components hold sensitive learner state in React memory. A
  // keyed boundary guarantees that logout/login cannot leave the prior learner's
  // profile, drafts, answers, or conversation mounted in the same tab.
  return (
    <AuthContext.Provider value={value}>
      {verificationError ? (
        <div className="public-session-warning" role="alert">
          <span>{verificationError}</span>
          <button className="button subtle small" type="button" onClick={() => setVerificationAttempt((value) => value + 1)}>
            Retry session check
          </button>
        </div>
      ) : null}
      <Fragment key={`${identityKey}:${authEpoch}`}>{children}</Fragment>
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
