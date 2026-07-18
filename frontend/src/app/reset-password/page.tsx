"use client";

import { ArrowLeft, CheckCircle2, KeyRound, ShieldCheck, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Suspense, useLayoutEffect, useRef, useState } from "react";
import { ApiError, api } from "@/lib/api";
import {
  emailedLinkProof,
  PENDING_PASSWORD_RESET_PROOF_KEY,
  storedPasswordResetProof,
} from "@/lib/routeAccess";
import styles from "../forgot-password/recovery.module.css";

type ResetErrors = {
  newPassword?: string;
  confirmation?: string;
  recoveryUsername?: string;
  recoveryDisplayName?: string;
  form?: string;
};

type RecoveredIdentity = {
  username: string;
  displayName: string | null;
};

const TERMINAL_PASSWORD_RESET_CODES = new Set([
  "challenge_attempts_exhausted",
  "challenge_expired",
  "challenge_invalid",
  "challenge_stale",
  "challenge_used",
]);

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<RecoveryLoading />}>
      <ResetPasswordScreen />
    </Suspense>
  );
}

function RecoveryLoading() {
  return (
    <div className={styles.recoveryPage}>
      <section className={styles.contextPanel} aria-labelledby="reset-loading-title">
        <div>
          <span className={styles.contextIcon} aria-hidden="true"><KeyRound size={22} /></span>
          <p className={styles.eyebrow}>Account recovery</p>
          <h1 id="reset-loading-title">Choose a new password.</h1>
        </div>
      </section>
      <section className={styles.formCard} aria-label="Loading password reset">
        <p>Checking your reset link…</p>
      </section>
    </div>
  );
}

function ResetPasswordScreen() {
  const router = useRouter();
  const [proof, setProof] = useState<{ challengeId: string; token: string } | null>(null);
  const challengeId = proof?.challengeId ?? "";
  const token = proof?.token ?? "";
  const hasResetProof = Boolean(proof && challengeId && token);
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [recoveryUsername, setRecoveryUsername] = useState("");
  const [recoveryDisplayName, setRecoveryDisplayName] = useState("");
  const [recoveredIdentity, setRecoveredIdentity] = useState<RecoveredIdentity | null>(null);
  const [errors, setErrors] = useState<ResetErrors>({});
  const [busy, setBusy] = useState(false);
  const [invalidLink, setInvalidLink] = useState(false);
  const passwordRef = useRef<HTMLInputElement>(null);
  const confirmationRef = useRef<HTMLInputElement>(null);
  const recoveryUsernameRef = useRef<HTMLInputElement>(null);
  const recoveryDisplayNameRef = useRef<HTMLInputElement>(null);
  const passwordsMatch = newPassword.length >= 10 && newPassword === confirmation;
  const proofCaptured = useRef(false);

  function clearStoredProof() {
    setProof({ challengeId: "", token: "" });
    try {
      window.sessionStorage.removeItem(PENDING_PASSWORD_RESET_PROOF_KEY);
    } catch {
      // React state still drops the one-time proof on every terminal outcome.
    }
  }

  useLayoutEffect(() => {
    if (proofCaptured.current || typeof window === "undefined") return;
    proofCaptured.current = true;
    const hasUrlProofMaterial = Boolean(window.location.search || window.location.hash);
    const fromUrl = emailedLinkProof(window.location.search, window.location.hash);
    let captured = fromUrl.challengeId && fromUrl.token ? fromUrl : null;
    try {
      if (captured) {
        window.sessionStorage.setItem(
          PENDING_PASSWORD_RESET_PROOF_KEY,
          JSON.stringify({ ...captured, savedAt: Date.now() }),
        );
      } else if (!hasUrlProofMaterial) {
        const raw = window.sessionStorage.getItem(PENDING_PASSWORD_RESET_PROOF_KEY);
        captured = storedPasswordResetProof(raw);
        if (raw && !captured) {
          window.sessionStorage.removeItem(PENDING_PASSWORD_RESET_PROOF_KEY);
        }
      } else {
        // A partial or malformed emailed-link handoff must fail closed instead
        // of silently reviving an older proof from this tab.
        window.sessionStorage.removeItem(PENDING_PASSWORD_RESET_PROOF_KEY);
      }
    } catch {
      // A blocked tab store cannot prevent a fresh URL proof from remaining in
      // memory; an URL-less reload simply falls back to the incomplete state.
    } finally {
      if (hasUrlProofMaterial) {
        window.history.replaceState(window.history.state, "", "/reset-password");
      }
      setProof(captured ?? { challengeId: "", token: "" });
    }
  }, []);

  function focusPassword() {
    window.requestAnimationFrame(() => passwordRef.current?.focus());
  }

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !hasResetProof) return;

    if (newPassword.length < 10) {
      setErrors({ newPassword: "Use at least 10 characters for your new password." });
      passwordRef.current?.focus();
      return;
    }
    if (newPassword.length > 256) {
      setErrors({ newPassword: "Use 256 characters or fewer." });
      passwordRef.current?.focus();
      return;
    }
    if (!confirmation) {
      setErrors({ confirmation: "Enter your new password again." });
      confirmationRef.current?.focus();
      return;
    }
    if (newPassword !== confirmation) {
      setErrors({ confirmation: "The passwords do not match. Enter the same password again." });
      confirmationRef.current?.focus();
      return;
    }

    const normalizedRecoveryUsername = recoveryUsername.trim();
    if (normalizedRecoveryUsername && !/^[A-Za-z0-9_.-]{3,32}$/.test(normalizedRecoveryUsername)) {
      setErrors({ recoveryUsername: "Use 3–32 letters, numbers, dots, dashes, or underscores." });
      recoveryUsernameRef.current?.focus();
      return;
    }
    if (["admin", "demo", "guest"].includes(normalizedRecoveryUsername.toLowerCase())) {
      setErrors({ recoveryUsername: "Choose a different username." });
      recoveryUsernameRef.current?.focus();
      return;
    }

    setErrors({});
    setBusy(true);
    try {
      const result = await api.confirmPasswordReset({
        challengeId,
        token,
        newPassword,
        recoveryUsername: normalizedRecoveryUsername || undefined,
        recoveryDisplayName: recoveryDisplayName.trim() || undefined,
      });
      clearStoredProof();
      setNewPassword("");
      setConfirmation("");
      setRecoveryUsername("");
      setRecoveryDisplayName("");
      if (result.identityRecovered && result.username) {
        setRecoveredIdentity({ username: result.username, displayName: result.displayName ?? null });
      } else {
        router.replace("/login?passwordReset=1");
      }
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === "password_too_short") {
        setErrors({ newPassword: "Use at least 10 characters for your new password." });
        focusPassword();
      } else if (caught instanceof ApiError && caught.code === "password_too_long") {
        setErrors({ newPassword: "Use 256 characters or fewer." });
        focusPassword();
      } else if (caught instanceof ApiError && caught.code === "password_too_common") {
        setErrors({ newPassword: "Choose a less common passphrase that is not easy to guess." });
        focusPassword();
      } else if (caught instanceof ApiError && caught.code === "invalid_username") {
        setErrors({ recoveryUsername: "Use 3–32 letters, numbers, dots, dashes, or underscores." });
        window.requestAnimationFrame(() => recoveryUsernameRef.current?.focus());
      } else if (caught instanceof ApiError && ["username_taken", "recovery_identity_unavailable"].includes(caught.code ?? "")) {
        setErrors({ recoveryUsername: "That username is already in use. Choose another." });
        window.requestAnimationFrame(() => recoveryUsernameRef.current?.focus());
      } else if (caught instanceof ApiError && caught.code === "display_name_too_long") {
        setErrors({ recoveryDisplayName: "Use 80 characters or fewer for the name shown in TRACE." });
        window.requestAnimationFrame(() => recoveryDisplayNameRef.current?.focus());
      } else if (caught instanceof ApiError && caught.code?.startsWith("challenge_")) {
        if (TERMINAL_PASSWORD_RESET_CODES.has(caught.code)) {
          clearStoredProof();
        }
        setErrors({});
        setInvalidLink(true);
      } else {
        setErrors({ form: "Your password could not be reset right now. Wait a moment and try again." });
      }
    } finally {
      setBusy(false);
    }
  }

  if (!proof) return <RecoveryLoading />;

  return (
    <div className={styles.recoveryPage}>
      <section className={styles.contextPanel} aria-labelledby="reset-page-title">
        <div>
          <span className={styles.contextIcon} aria-hidden="true"><KeyRound size={22} /></span>
          <p className={styles.eyebrow}>Account recovery</p>
          <h1 id="reset-page-title">Choose a new password.</h1>
          <p className={styles.contextCopy}>
            A strong passphrase protects your private learning record and keeps your progress available across devices.
          </p>
        </div>
        <p className={styles.privacyNote}>
          <ShieldCheck size={16} aria-hidden="true" />
          Resetting your password signs out other sessions that may still be using the old password.
        </p>
      </section>

      <section className={styles.formCard} aria-labelledby="reset-password-title">
        {recoveredIdentity ? (
          <div className={styles.stateBlock} role="status" aria-live="polite">
            <span className={styles.stateIcon} aria-hidden="true"><CheckCircle2 size={23} /></span>
            <h2 id="reset-password-title">Your account is yours again</h2>
            <p>
              Your password was updated. Sign in with
              {recoveredIdentity.displayName ? ` ${recoveredIdentity.displayName}’s` : " your"} username below.
            </p>
            <div className={styles.recoveredIdentity} aria-label="Recovered sign-in identity">
              <span>Username</span>
              <strong>{recoveredIdentity.username}</strong>
            </div>
            <div className={styles.stateActions}>
              <Link className={styles.primaryLink} href="/login?passwordReset=1">Continue to sign in</Link>
            </div>
          </div>
        ) : !hasResetProof || invalidLink ? (
          <div className={styles.stateBlock} role="alert">
            <span className={styles.stateIcon} aria-hidden="true"><TriangleAlert size={23} /></span>
            <h2 id="reset-password-title">
              {invalidLink ? "This reset link is no longer valid" : "This reset link is incomplete"}
            </h2>
            <p>
              {invalidLink
                ? "This link may be invalid, expired, or has already been used. Request a new link and open the most recent email from TRACE."
                : "Request a new link from the password-recovery page, then open the most recent email from TRACE."}
            </p>
            <div className={styles.stateActions}>
              <Link className={styles.primaryLink} href="/forgot-password">Request a new link</Link>
              <Link className={styles.secondaryLink} href="/login">Return to sign in</Link>
            </div>
          </div>
        ) : (
          <>
            <header className={styles.formHeader}>
              <h2 id="reset-password-title">Set your new password</h2>
              <p>Use 10–256 characters and avoid common or repeated passwords.</p>
            </header>

            <form className={styles.form} onSubmit={onSubmit} noValidate>
              <div className={styles.field}>
                <label htmlFor="reset-new-password">New password</label>
                <input
                  ref={passwordRef}
                  id="reset-new-password"
                  name="newPassword"
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={10}
                  maxLength={256}
                  aria-invalid={errors.newPassword ? "true" : undefined}
                  aria-describedby={errors.newPassword ? "reset-new-password-error" : "reset-new-password-hint"}
                  value={newPassword}
                  onChange={(event) => {
                    setNewPassword(event.target.value);
                    if (errors.newPassword || errors.form) setErrors({});
                  }}
                />
                {errors.newPassword ? (
                  <p className={styles.fieldError} id="reset-new-password-error" role="alert">{errors.newPassword}</p>
                ) : (
                  <p className={styles.fieldHint} id="reset-new-password-hint">A longer passphrase is easier to remember and harder to guess.</p>
                )}
              </div>

              <div className={styles.field}>
                <label htmlFor="reset-password-confirmation">Confirm new password</label>
                <input
                  ref={confirmationRef}
                  id="reset-password-confirmation"
                  name="passwordConfirmation"
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={10}
                  maxLength={256}
                  className={passwordsMatch ? styles.matchingInput : undefined}
                  aria-invalid={errors.confirmation ? "true" : undefined}
                  aria-describedby={errors.confirmation
                    ? "reset-password-confirmation-error"
                    : passwordsMatch
                      ? "reset-password-confirmation-match"
                      : undefined}
                  value={confirmation}
                  onChange={(event) => {
                    setConfirmation(event.target.value);
                    if (errors.confirmation || errors.form) setErrors({});
                  }}
                />
                {errors.confirmation ? (
                  <p className={styles.fieldError} id="reset-password-confirmation-error" role="alert">{errors.confirmation}</p>
                ) : passwordsMatch ? (
                  <p className={styles.fieldSuccess} id="reset-password-confirmation-match" role="status">
                    <CheckCircle2 size={14} aria-hidden="true" /> Passwords match
                  </p>
                ) : null}
              </div>

              <details className={styles.identityRecovery}>
                <summary>Don’t recognize the account details?</summary>
                <div className={styles.identityRecoveryBody}>
                  <p>
                    You can choose a new username before signing in.
                  </p>
                  <div className={styles.field}>
                    <label htmlFor="reset-recovery-username">Your username <span>(optional)</span></label>
                    <input
                      ref={recoveryUsernameRef}
                      id="reset-recovery-username"
                      name="recoveryUsername"
                      type="text"
                      autoComplete="username"
                      minLength={3}
                      maxLength={32}
                      spellCheck={false}
                      aria-invalid={errors.recoveryUsername ? "true" : undefined}
                      aria-describedby={errors.recoveryUsername ? "reset-recovery-username-error" : "reset-recovery-username-hint"}
                      value={recoveryUsername}
                      onChange={(event) => {
                        setRecoveryUsername(event.target.value);
                        if (errors.recoveryUsername || errors.form) setErrors({});
                      }}
                    />
                    {errors.recoveryUsername ? (
                      <p className={styles.fieldError} id="reset-recovery-username-error" role="alert">{errors.recoveryUsername}</p>
                    ) : (
                      <p className={styles.fieldHint} id="reset-recovery-username-hint">Use 3–32 letters, numbers, dots, dashes, or underscores.</p>
                    )}
                  </div>
                  <div className={styles.field}>
                    <label htmlFor="reset-recovery-display-name">Name shown in TRACE <span>(optional)</span></label>
                    <input
                      ref={recoveryDisplayNameRef}
                      id="reset-recovery-display-name"
                      name="recoveryDisplayName"
                      type="text"
                      autoComplete="name"
                      maxLength={80}
                      aria-invalid={errors.recoveryDisplayName ? "true" : undefined}
                      aria-describedby={errors.recoveryDisplayName ? "reset-recovery-display-name-error" : undefined}
                      value={recoveryDisplayName}
                      onChange={(event) => {
                        setRecoveryDisplayName(event.target.value);
                        if (errors.recoveryDisplayName || errors.form) setErrors({});
                      }}
                    />
                    {errors.recoveryDisplayName ? (
                      <p className={styles.fieldError} id="reset-recovery-display-name-error" role="alert">{errors.recoveryDisplayName}</p>
                    ) : null}
                  </div>
                  <p className={styles.identityBoundary}>Verified accounts keep their existing username and profile name.</p>
                </div>
              </details>

              {errors.form ? <p className={styles.formError} role="alert">{errors.form}</p> : null}

              <button className={styles.submitButton} type="submit" disabled={busy}>
                <KeyRound size={17} aria-hidden="true" />
                {busy ? "Updating password…" : "Update password"}
              </button>
            </form>

            <Link className={styles.backLink} href="/login">
              <ArrowLeft size={15} aria-hidden="true" />
              Back to sign in
            </Link>
          </>
        )}
      </section>
    </div>
  );
}
