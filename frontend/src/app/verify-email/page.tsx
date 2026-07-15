"use client";

import { ArrowLeft, CheckCircle2, MailCheck, ShieldCheck, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Suspense, useLayoutEffect, useRef, useState } from "react";
import { ApiError, type AccountResolutionResponse } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { emailedLinkProof, safeAppPath } from "@/lib/routeAccess";
import styles from "../forgot-password/recovery.module.css";

type VerificationProof = {
  challengeId: string;
  token: string;
  next: string;
};

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<VerificationLoading />}>
      <VerifyEmailScreen />
    </Suspense>
  );
}

function VerificationLoading() {
  return (
    <div className={styles.recoveryPage}>
      <section className={styles.contextPanel} aria-labelledby="verify-loading-title">
        <div>
          <span className={styles.contextIcon} aria-hidden="true"><MailCheck size={22} /></span>
          <p className={styles.eyebrow}>Email verification</p>
          <h1 id="verify-loading-title">Secure your learning record.</h1>
        </div>
      </section>
      <section className={styles.formCard} aria-label="Loading email verification">
        <p>Checking your verification link…</p>
      </section>
    </div>
  );
}

function VerifyEmailScreen() {
  const router = useRouter();
  const { confirmEmailVerification } = useAuth();
  const [proof, setProof] = useState<VerificationProof | null>(null);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [accountResolution, setAccountResolution] = useState<AccountResolutionResponse | null>(null);
  const confirmationInFlight = useRef(false);
  const proofCaptured = useRef(false);
  const passwordRef = useRef<HTMLInputElement>(null);
  const completeProof = Boolean(proof?.challengeId && proof.token);

  useLayoutEffect(() => {
    if (proofCaptured.current || typeof window === "undefined") return;
    proofCaptured.current = true;
    const query = new URLSearchParams(window.location.search);
    const linkProof = emailedLinkProof(window.location.search, window.location.hash);
    const captured = {
      ...linkProof,
      next: safeAppPath(query.get("next"), "/dashboard"),
    };
    if (window.location.search || window.location.hash) {
      window.history.replaceState(window.history.state, "", "/verify-email");
    }
    setProof(captured);
  }, []);

  async function confirm(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!completeProof || !proof || confirmationInFlight.current) return;
    setError(null);
    setPasswordError(null);
    if (!password) {
      setPasswordError("Enter your password to continue.");
      passwordRef.current?.focus();
      return;
    }
    confirmationInFlight.current = true;
    setBusy(true);
    try {
      const result = await confirmEmailVerification(proof.challengeId, proof.token, password);
      setPassword("");
      if ("accountResolutionRequired" in result) {
        setAccountResolution(result);
        return;
      }
      router.replace(proof.next);
    } catch (caught) {
      const code = caught instanceof ApiError ? caught.code : null;
      setPassword("");
      if (code === "invalid_verification_credentials" || code === "invalid_credentials" || code === "invalid_current_password") {
        setPasswordError("That link or password wasn’t accepted. Check your email and try again.");
        window.requestAnimationFrame(() => passwordRef.current?.focus());
      } else if (code === "reauth_throttled") {
        setPasswordError("Too many verification attempts. Wait before trying again.");
        window.requestAnimationFrame(() => passwordRef.current?.focus());
      } else if (code === "challenge_attempts_exhausted") {
        setError("This verification link reached its attempt limit. Sign in to request a new message.");
      } else if (code === "challenge_stale") {
        setError("Your account changed after this link was sent. Sign in to start verification again.");
      } else {
        setError("This verification link is invalid, expired, or has already been used.");
      }
    } finally {
      confirmationInFlight.current = false;
      setBusy(false);
    }
  }

  if (!proof) return <VerificationLoading />;

  return (
    <div className={styles.recoveryPage}>
      <section className={styles.contextPanel} aria-labelledby="verify-page-title">
        <div>
          <span className={styles.contextIcon} aria-hidden="true"><MailCheck size={22} /></span>
          <p className={styles.eyebrow}>Email verification</p>
          <h1 id="verify-page-title">Verify your email.</h1>
          <p className={styles.contextCopy}>Confirm your email to save your progress and recover your account.</p>
        </div>
        <p className={styles.privacyNote}>
          <ShieldCheck size={16} aria-hidden="true" />
          For your security, verification links expire after a short time.
        </p>
      </section>

      <section className={styles.formCard} aria-labelledby="verify-email-title">
        {accountResolution ? (
          <div className={styles.stateBlock} role="status" aria-live="polite">
            <span className={styles.stateIcon} aria-hidden="true"><CheckCircle2 size={23} /></span>
            <h2 id="verify-email-title">This email already has a TRACE account</h2>
            <p>{accountResolution.suggestedAction === "reset_password"
              ? "Reset the password before signing in to this account."
              : "Sign in with the existing password, or reset it if you do not remember it."}</p>
            <div className={styles.stateActions}>
              {accountResolution.suggestedAction === "reset_password" ? (
                <>
                  <Link className={styles.primaryLink} href="/forgot-password">Reset password</Link>
                  <Link className={styles.secondaryLink} href="/login">Back to sign in</Link>
                </>
              ) : (
                <>
                  <Link className={styles.primaryLink} href="/login">Sign in</Link>
                  <Link className={styles.secondaryLink} href="/forgot-password">Reset password</Link>
                </>
              )}
            </div>
          </div>
        ) : !completeProof ? (
          <div className={styles.stateBlock} role="alert">
            <span className={styles.stateIcon} aria-hidden="true"><TriangleAlert size={23} /></span>
            <h2 id="verify-email-title">This verification link is incomplete</h2>
            <p>Sign in to request a fresh verification message, then open the most recent email from TRACE.</p>
            <div className={styles.stateActions}>
              <Link className={styles.primaryLink} href="/login">Return to sign in</Link>
            </div>
          </div>
        ) : (
          <div className={styles.stateBlock}>
            <span className={styles.stateIcon} aria-hidden="true"><CheckCircle2 size={23} /></span>
            <h2 id="verify-email-title">Confirm your email</h2>
            <p>Enter your password to finish verifying your email.</p>
            <form className={styles.form} onSubmit={confirm} noValidate>
              <div className={styles.field}>
                <label htmlFor="verify-email-password">Current password</label>
                <input
                  ref={passwordRef}
                  id="verify-email-password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => {
                    setPassword(event.target.value);
                    setPasswordError(null);
                    setError(null);
                  }}
                  aria-invalid={Boolean(passwordError)}
                  aria-describedby={passwordError ? "verify-email-password-error" : "verify-email-password-hint"}
                  required
                />
                <small className={styles.fieldHint} id="verify-email-password-hint">For your security, confirm your password.</small>
                {passwordError ? <small className={styles.fieldError} id="verify-email-password-error">{passwordError}</small> : null}
              </div>
              {error ? <p className={styles.formError} role="alert">{error}</p> : null}
              <button className={styles.submitButton} type="submit" disabled={busy}>
                <MailCheck size={17} aria-hidden="true" /> {busy ? "Verifying…" : "Verify email"}
              </button>
            </form>
            <Link className={styles.backLink} href="/login"><ArrowLeft size={15} aria-hidden="true" /> Return to sign in</Link>
          </div>
        )}
      </section>
    </div>
  );
}
