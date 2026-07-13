"use client";

import { ArrowRight, Brain, CheckCircle2, LogIn, ShieldCheck, UserPlus } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { GuestProgressSummary } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="page"><div className="panel pad">Loading sign-in...</div></div>}>
      <LoginScreen />
    </Suspense>
  );
}

function LoginScreen() {
  const { login, register } = useAuth();
  const router = useRouter();
  const search = useSearchParams();
  const requestedNext = search.get("next") || "/";
  // Keep post-auth navigation inside the application; protocol-relative and
  // absolute destinations must never turn the sign-in page into an open redirect.
  const next = requestedNext.startsWith("/") && !requestedNext.startsWith("//") ? requestedNext : "/";

  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [guestProgress, setGuestProgress] = useState<GuestProgressSummary | null>(null);
  const [claimGuestProgress, setClaimGuestProgress] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.guestProgress()
      .then((summary) => {
        if (!cancelled) setGuestProgress(summary);
      })
      .catch(() => {
        // If the browser's guest work cannot be verified, do not offer a claim.
        if (!cancelled) setGuestProgress(null);
      });
    return () => { cancelled = true; };
  }, []);

  const canClaimGuestProgress = Boolean(guestProgress?.hasProgress && guestProgress.claimable);
  const modeSessions = guestProgress
    ? guestProgress.reviewSessions + guestProgress.rapidRounds + guestProgress.clinicalSessions + guestProgress.trainingCampaigns
    : 0;

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    setError(null);
    if (!username.trim() || !password) {
      setError("Enter a username and password.");
      return;
    }
    if (mode === "register" && password.length < 10) {
      setError("Password must be at least 10 characters.");
      return;
    }
    setBusy(true);
    try {
      const shouldClaim = canClaimGuestProgress && claimGuestProgress;
      if (mode === "register") {
        await register(username.trim(), password, displayName.trim() || undefined, shouldClaim);
      } else {
        await login(username.trim(), password, shouldClaim);
      }
      router.push(next);
    } catch (err) {
      // Surface a friendly message for the common 400/401 cases.
      const raw = err instanceof Error ? err.message : "Could not sign you in.";
      if (raw.startsWith("401")) setError("Incorrect username or password.");
      else if (raw.includes("password_too_short")) setError("Password must be at least 10 characters.");
      else if (raw.includes("username_taken")) setError("That username is already taken.");
      else if (raw.includes("invalid_username")) setError("Use 3–32 letters, digits, underscores, periods, or hyphens for your username.");
      else if (raw.startsWith("409") || raw.includes("guest_progress_already_claimed")) {
        setError("This browser’s guest work was already claimed by another account. Uncheck the transfer option to continue without merging it.");
      }
      else if (raw.startsWith("429")) setError("Too many account attempts. Please wait a few minutes and try again.");
      else if (raw.startsWith("400")) setError("Check the highlighted account details and try again.");
      else setError(raw);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page auth-page">
      <section className="panel pad auth-card">
        <div className="auth-brand">
          <span className="brand-mark">
            <Brain size={20} aria-hidden="true" />
          </span>
          <div>
            <p className="eyebrow" style={{ margin: 0 }}>ECG Tutor V1</p>
            <h1 style={{ fontSize: "1.6rem", margin: "2px 0 0" }}>{mode === "login" ? "Sign in" : "Create your account"}</h1>
          </div>
        </div>
        <p className="muted" style={{ marginTop: 4 }}>
          {mode === "login"
            ? "Sign in to keep your mastery, attempts, and tutor threads across sessions."
            : "Register to save your progress. Your username scopes your personal learner profile."}
        </p>

        <div className="segmented" aria-label="Authentication mode" style={{ marginTop: 8 }}>
          <button type="button" className={mode === "login" ? "active" : ""} onClick={() => { setMode("login"); setError(null); setClaimGuestProgress(false); }}>
            Sign in
          </button>
          <button type="button" className={mode === "register" ? "active" : ""} onClick={() => { setMode("register"); setError(null); setClaimGuestProgress(false); }}>
            Register
          </button>
        </div>

        {error ? <div className="warning" id="auth-error" role="alert" style={{ marginTop: 14 }}>{error}</div> : null}

        <form className="form-grid practice-form" style={{ marginTop: 14 }} onSubmit={onSubmit} noValidate>
          <div className="field full">
            <label htmlFor="auth-username">Username</label>
            <input
              id="auth-username"
              name="username"
              autoComplete="username"
              maxLength={64}
              aria-describedby={error ? "auth-error" : undefined}
              value={username}
              onChange={(event) => setUsername(event.target.value)}
            />
          </div>
          {mode === "register" ? (
            <div className="field full">
              <label htmlFor="auth-display">Display name (optional)</label>
              <input
                id="auth-display"
                name="displayName"
                maxLength={80}
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
              />
            </div>
          ) : null}
          <div className="field full">
            <label htmlFor="auth-password">Password</label>
            <input
              id="auth-password"
              name="password"
              type="password"
              minLength={mode === "register" ? 10 : undefined}
              maxLength={256}
              autoComplete={mode === "register" ? "new-password" : "current-password"}
              aria-describedby={error ? "auth-error" : undefined}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>
          {canClaimGuestProgress && guestProgress ? (
            <label className="auth-claim-panel" htmlFor="auth-claim-progress">
              <input
                id="auth-claim-progress"
                type="checkbox"
                checked={claimGuestProgress}
                onChange={(event) => setClaimGuestProgress(event.target.checked)}
              />
              <span className="auth-claim-copy">
                <span className="auth-claim-heading">
                  <CheckCircle2 size={17} aria-hidden="true" />
                  Save this browser’s guest work to my account
                </span>
                <span className="auth-claim-summary">
                  {guestProgress.totalActivities} saved learning records include {guestProgress.attempts} scored attempts, {guestProgress.lessonScenes} lesson scenes, {modeSessions} practice sessions, and {guestProgress.tutorThreads} tutor threads.
                </span>
                <span className="auth-claim-note">
                  Optional and off by default. Your account history is kept, guest evidence is merged once, and this guest work cannot later be claimed by a different account.
                </span>
              </span>
            </label>
          ) : null}
          <button className="button primary" type="submit" disabled={busy} style={{ marginTop: 4 }}>
            {mode === "login" ? <LogIn size={17} aria-hidden="true" /> : <UserPlus size={17} aria-hidden="true" />}
            {busy ? "Please wait..." : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>

        <div className="auth-guest">
          <ShieldCheck size={15} aria-hidden="true" />
          <span className="muted">No account needed to explore. </span>
          <Link className="auth-guest-link" href={next}>
            Continue as guest
            <ArrowRight size={14} aria-hidden="true" />
          </Link>
        </div>
      </section>
    </div>
  );
}
