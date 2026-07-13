"use client";

import { Fragment, createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { api } from "./api";
import type { User } from "./types";

type AuthContextValue = {
  user: User | null;
  /** True while GET /auth/me hydrates the HttpOnly cookie session. */
  loading: boolean;
  /** Stable owner key for learner-scoped browser state. Never use a display name here. */
  identityKey: string;
  /** Changes whenever the effective browser identity changes, forcing private UI state to remount. */
  authEpoch: number;
  login: (username: string, password: string, claimGuestProgress?: boolean) => Promise<User>;
  register: (username: string, password: string, displayName?: string, claimGuestProgress?: boolean) => Promise<User>;
  logout: () => Promise<void>;
  logoutAll: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [verificationError, setVerificationError] = useState<string | null>(null);
  const [verificationAttempt, setVerificationAttempt] = useState(0);
  const [authEpoch, setAuthEpoch] = useState(0);
  const identityRef = useRef("guest");

  const transitionIdentity = useCallback((nextUser: User | null) => {
    const nextIdentity = nextUser?.userId ?? "guest";
    if (identityRef.current !== nextIdentity) {
      identityRef.current = nextIdentity;
      setAuthEpoch((value) => value + 1);
    }
    setUser(nextUser);
  }, []);

  // The credential is HttpOnly, so the only safe hydration check is /auth/me.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setVerificationError(null);
    api
      .me()
      .then((res) => {
        if (cancelled) return;
        if (res.authenticated && res.user) {
          transitionIdentity(res.user);
        } else {
          transitionIdentity(null);
        }
      })
      .catch(() => {
        if (cancelled) return;
        // A transport failure does not prove the HttpOnly session is absent.
        // Keep all stateful pages unmounted until identity can be verified.
        setVerificationError("Your private session could not be verified. No learner data has been opened.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [transitionIdentity, verificationAttempt]);

  const login = useCallback(
    async (username: string, password: string, claimGuestProgress = false) => {
      const res = await api.login({ username, password, claimGuestProgress });
      if (res.guestClaim && typeof window !== "undefined") {
        window.sessionStorage.removeItem("ecg-tool:rapid-round:v2:guest");
      }
      transitionIdentity(res.user);
      return res.user;
    },
    [transitionIdentity],
  );

  const register = useCallback(
    async (username: string, password: string, displayName?: string, claimGuestProgress = false) => {
      const res = await api.register({ username, password, displayName, claimGuestProgress });
      if (res.guestClaim && typeof window !== "undefined") {
        window.sessionStorage.removeItem("ecg-tool:rapid-round:v2:guest");
      }
      transitionIdentity(res.user);
      return res.user;
    },
    [transitionIdentity],
  );

  const logout = useCallback(async () => {
    // Do not present a guest UI while the HttpOnly cookie may still authorize
    // requests as the prior student. A failed server revocation leaves the
    // current identity mounted and lets the caller surface a retry.
    await api.logout();
    transitionIdentity(null);
  }, [transitionIdentity]);

  const logoutAll = useCallback(async () => {
    await api.logoutAll();
    transitionIdentity(null);
  }, [transitionIdentity]);

  const identityKey = user?.userId ?? "guest";

  const value = useMemo<AuthContextValue>(
    () => ({ user, loading, identityKey, authEpoch, login, register, logout, logoutAll }),
    [user, loading, identityKey, authEpoch, login, register, logout, logoutAll],
  );

  // Hydrate the HttpOnly account/guest identity before mounting stateful pages.
  // This prevents concurrent first-load API calls from racing the initial
  // per-browser guest cookie and prevents a brief guest-data flash on refresh.
  if (loading || verificationError) {
    return (
      <AuthContext.Provider value={value}>
        <div className="auth-session-loader" role="status" aria-live="polite">
          <span className="status-orb" aria-hidden="true" />
          <strong>{verificationError ?? "Opening your learning workspace…"}</strong>
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
      <Fragment key={`${identityKey}:${authEpoch}`}>{children}</Fragment>
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
