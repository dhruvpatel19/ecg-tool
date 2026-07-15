"use client";

import { ArrowLeft, Check, KeyRound, Mail, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import { api } from "@/lib/api";
import styles from "./recovery.module.css";

const GENERIC_CONFIRMATION =
  "If an account exists for that email, we’ll send a password-reset link. Check your inbox and spam folder.";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [emailError, setEmailError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;

    const normalizedEmail = email.trim();
    setEmailError(null);
    setFormError(null);

    if (!normalizedEmail) {
      setEmailError("Enter the email address linked to your account.");
      emailRef.current?.focus();
      return;
    }
    if (emailRef.current?.validity.typeMismatch) {
      setEmailError("Enter a valid email address.");
      emailRef.current.focus();
      return;
    }

    setBusy(true);
    try {
      await api.requestPasswordReset({ email: normalizedEmail });
      setSubmitted(true);
    } catch {
      setFormError("Recovery could not be started right now. Wait a moment and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.recoveryPage}>
      <section className={styles.contextPanel} aria-labelledby="recovery-page-title">
        <div>
          <span className={styles.contextIcon} aria-hidden="true"><KeyRound size={22} /></span>
          <p className={styles.eyebrow}>Account recovery</p>
          <h1 id="recovery-page-title">Get back to your ECG learning.</h1>
          <p className={styles.contextCopy}>
            Request a secure reset link, choose a new password, and continue from your saved learning record.
          </p>
        </div>
        <p className={styles.privacyNote}>
          <ShieldCheck size={16} aria-hidden="true" />
          For your security, reset links expire after a short time.
        </p>
      </section>

      <section className={styles.formCard} aria-labelledby="forgot-password-title">
        {submitted ? (
          <div className={styles.stateBlock} role="status" aria-live="polite">
            <span className={styles.stateIcon} aria-hidden="true"><Check size={23} /></span>
            <h2 id="forgot-password-title">Check your inbox</h2>
            <p>{GENERIC_CONFIRMATION}</p>
            <div className={styles.stateActions}>
              <Link className={styles.primaryLink} href="/login">Return to sign in</Link>
              <button
                className={styles.secondaryLink}
                type="button"
                onClick={() => {
                  setSubmitted(false);
                  window.requestAnimationFrame(() => emailRef.current?.focus());
                }}
              >
                Try another address
              </button>
            </div>
          </div>
        ) : (
          <>
            <header className={styles.formHeader}>
              <h2 id="forgot-password-title">Reset your password</h2>
              <p>Enter the email address connected to your TRACE account.</p>
            </header>

            <form className={styles.form} onSubmit={onSubmit} noValidate>
              <div className={styles.field}>
                <label htmlFor="recovery-email">Email address</label>
                <input
                  ref={emailRef}
                  id="recovery-email"
                  name="email"
                  type="email"
                  inputMode="email"
                  autoComplete="email"
                  required
                  maxLength={254}
                  aria-invalid={emailError ? "true" : undefined}
                  aria-describedby={emailError ? "recovery-email-error" : "recovery-email-hint"}
                  value={email}
                  onChange={(event) => {
                    setEmail(event.target.value);
                    if (emailError) setEmailError(null);
                  }}
                />
                {emailError ? (
                  <p className={styles.fieldError} id="recovery-email-error" role="alert">{emailError}</p>
                ) : (
                  <p className={styles.fieldHint} id="recovery-email-hint">We’ll only use this address for account recovery.</p>
                )}
              </div>

              {formError ? <p className={styles.formError} role="alert">{formError}</p> : null}

              <button className={styles.submitButton} type="submit" disabled={busy}>
                <Mail size={17} aria-hidden="true" />
                {busy ? "Requesting link…" : "Send reset link"}
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
