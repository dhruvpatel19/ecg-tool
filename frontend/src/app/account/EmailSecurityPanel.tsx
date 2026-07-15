"use client";

import { Mail, ShieldCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import styles from "./account.module.css";

type PendingProof = {
  kind:
    | "email_verification"
    | "email_change"
    | "email_change_current_factor";
  challengeId: string;
  maskedEmail: string | null;
  expiresAt: string | null;
};

const DEFAULT_COOLDOWN = 60;

function safeAccountError(caught: unknown, fallback: string): string {
  if (!(caught instanceof ApiError)) return fallback;
  switch (caught.code) {
    case "invalid_email": return "Enter a valid email address.";
    case "email_unavailable": return "That email cannot be added to this account.";
    case "email_already_set": return "This account already has an email address.";
    case "invalid_current_password": return "The current password is incorrect.";
    case "invalid_credentials": return "The current password is incorrect.";
    case "invalid_verification_credentials": return "That code or password was not accepted. Check both and try again.";
    case "email_delivery_unavailable": return "Email delivery is temporarily unavailable. Please try again later.";
    case "current_email_factor_required": return "Confirm a fresh code sent to your current email before changing it.";
    case "challenge_incorrect": return "That code was not accepted. Check the email and try again.";
    case "challenge_expired": return "That code has expired. Request a new message.";
    case "challenge_used": return "That code was already used. Start the account step again.";
    case "challenge_attempts_exhausted": return "That challenge reached its attempt limit. Start the account step again.";
    case "challenge_stale": return "Your account changed after this message was sent. Start the account step again.";
    case "reauth_throttled": return "Too many password attempts. Wait before trying again.";
    case "unverified_email_change_unavailable": return "We couldn’t update the email. Check the address and password, then try again.";
    default: return fallback;
  }
}

export function EmailSecurityPanel() {
  const { user, confirmEmailVerification, refreshUser } = useAuth();
  const accountStatus = user?.accountStatus ?? "verified";
  const [email, setEmail] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [showEmailForm, setShowEmailForm] = useState(accountStatus !== "verified");
  const [pendingProof, setPendingProof] = useState<PendingProof | null>(null);
  const [proofCode, setProofCode] = useState("");
  const [proofPassword, setProofPassword] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [emailError, setEmailError] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [proofError, setProofError] = useState<string | null>(null);
  const [proofPasswordError, setProofPasswordError] = useState<string | null>(null);
  const [resendCooldown, setResendCooldown] = useState(0);

  const emailRef = useRef<HTMLInputElement>(null);
  const currentPasswordRef = useRef<HTMLInputElement>(null);
  const proofRef = useRef<HTMLInputElement>(null);
  const proofPasswordRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (accountStatus !== "verified") setShowEmailForm(true);
  }, [accountStatus]);

  useEffect(() => {
    if (resendCooldown <= 0) return;
    const timer = window.setTimeout(() => setResendCooldown((value) => Math.max(0, value - 1)), 1_000);
    return () => window.clearTimeout(timer);
  }, [resendCooldown]);

  if (!user) return null;

  function clearFeedback() {
    setError(null);
    setMessage(null);
    setEmailError(null);
    setPasswordError(null);
    setProofError(null);
    setProofPasswordError(null);
  }

  async function requestEmailAction(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    clearFeedback();
    if (!email.trim() || !emailRef.current?.validity.valid) {
      setEmailError("Enter a valid email address.");
      emailRef.current?.focus();
      return;
    }
    if (!currentPassword) {
      setPasswordError("Enter your current password.");
      currentPasswordRef.current?.focus();
      return;
    }

    setBusy("email-request");
    try {
      if (accountStatus === "email_upgrade_required") {
        const result = await api.requestEmailUpgrade({ email: email.trim(), currentPassword });
        setPendingProof({ kind: "email_verification", challengeId: result.challengeId, maskedEmail: result.maskedEmail, expiresAt: result.expiresAt });
        setMessage(result.deliveryFailed
          ? "We saved the address but couldn’t send the verification email. Try again."
          : `A verification message was sent to ${result.maskedEmail ?? "your email"}.`);
        setResendCooldown(result.deliveryFailed ? 0 : result.retryAfterSeconds ?? DEFAULT_COOLDOWN);
      } else if (accountStatus === "email_verification_required") {
        const result = await api.replaceUnverifiedEmail({ newEmail: email.trim(), currentPassword });
        setPendingProof({ kind: "email_verification", challengeId: result.challengeId, maskedEmail: result.maskedEmail, expiresAt: result.expiresAt });
        setMessage(result.deliveryFailed
          ? "We updated the address but couldn’t send the verification email. Try again."
          : `A new verification message was sent to ${result.maskedEmail ?? "the replacement email"}.`);
        setResendCooldown(result.deliveryFailed ? 0 : result.retryAfterSeconds ?? DEFAULT_COOLDOWN);
      } else {
        const result = await api.requestEmailChange({ email: email.trim(), currentPassword });
        if ("currentEmailFactorRequired" in result) {
          setPendingProof({ kind: "email_change_current_factor", challengeId: result.challengeId, maskedEmail: result.maskedEmail, expiresAt: result.expiresAt });
          setMessage(result.deliveryFailed
            ? "We couldn’t send a security code to your current email. Try again."
            : `A six-digit security code was sent to ${result.maskedEmail ?? "your current verified email"}. Confirm it before we contact the new address.`);
        } else {
          setPendingProof({ kind: "email_change", challengeId: result.challengeId, maskedEmail: result.maskedEmail, expiresAt: result.expiresAt });
          setMessage(result.deliveryFailed
            ? "We saved your new address but couldn’t send the verification email. Try again."
            : `A verification message was sent to ${result.maskedEmail ?? "your new email"}. Your current email remains active until confirmation.`);
        }
        setResendCooldown(result.deliveryFailed ? 0 : result.retryAfterSeconds ?? DEFAULT_COOLDOWN);
      }
      setProofCode("");
      setProofPassword("");
      setCurrentPassword("");
    } catch (caught) {
      const detail = safeAccountError(caught, "That email request could not be completed.");
      if (caught instanceof ApiError && caught.field === "email") {
        setEmailError(detail);
        emailRef.current?.focus();
      } else if (caught instanceof ApiError && caught.field === "currentPassword") {
        setPasswordError(detail);
        currentPasswordRef.current?.focus();
      } else {
        setError(detail);
      }
    } finally {
      setBusy(null);
    }
  }

  async function confirmProof(event: React.FormEvent) {
    event.preventDefault();
    if (!pendingProof || busy) return;
    clearFeedback();
    const token = proofCode.trim();
    if (!token) {
      setProofError(pendingProof.kind === "email_change" ? "Enter the verification code from your email." : "Enter the six-digit code.");
      proofRef.current?.focus();
      return;
    }
    if (pendingProof.kind !== "email_change" && !/^\d{6}$/.test(token)) {
      setProofError("Enter the complete six-digit code.");
      proofRef.current?.focus();
      return;
    }
    if (pendingProof.kind === "email_verification" && !proofPassword) {
      setProofPasswordError("Enter your current password.");
      proofPasswordRef.current?.focus();
      return;
    }

    setBusy("confirm-proof");
    try {
      if (pendingProof.kind === "email_verification") {
        const result = await confirmEmailVerification(pendingProof.challengeId, token, proofPassword);
        if ("accountResolutionRequired" in result) {
          setPendingProof(null);
          setProofCode("");
          setProofPassword("");
          setError("That email is already connected to another TRACE account. Use a different address.");
          return;
        }
        setMessage("Your email is verified and your account is ready.");
      } else if (pendingProof.kind === "email_change") {
        await api.confirmEmailChange({ challengeId: pendingProof.challengeId, token });
        await refreshUser();
        setMessage("Your verified email has been updated.");
      } else {
        const result = await api.confirmEmailChangeCurrentFactor({ challengeId: pendingProof.challengeId, code: token });
        setPendingProof({ kind: "email_change", challengeId: result.challengeId, maskedEmail: result.maskedEmail, expiresAt: result.expiresAt });
        setProofCode("");
        setMessage(result.deliveryFailed
          ? "Your current email was confirmed, but we couldn’t send the link to your new address. Try again."
          : `Current email confirmed. We sent a confirmation link to ${result.maskedEmail ?? "your new email"}.`);
        setResendCooldown(result.deliveryFailed ? 0 : result.retryAfterSeconds ?? DEFAULT_COOLDOWN);
        return;
      }
      setPendingProof(null);
      setProofCode("");
      setProofPassword("");
      setEmail("");
      setShowEmailForm(false);
    } catch (caught) {
      setProofPassword("");
      if (pendingProof.kind === "email_verification" && caught instanceof ApiError && (caught.field === "password" || caught.code === "invalid_verification_credentials" || caught.code === "invalid_credentials" || caught.code === "invalid_current_password" || caught.code === "reauth_throttled")) {
        setProofCode("");
        setProofPasswordError(safeAccountError(caught, "That code or password was not accepted. Check both and try again."));
        window.requestAnimationFrame(() => proofPasswordRef.current?.focus());
      } else {
        setProofError(safeAccountError(caught, "That code is invalid or expired. Request a new message and try again."));
        proofRef.current?.focus();
      }
    } finally {
      setBusy(null);
    }
  }

  async function resendProof() {
    if (!pendingProof || busy || resendCooldown > 0) return;
    clearFeedback();
    setProofPassword("");
    setBusy("resend");
    try {
      const result = pendingProof.kind === "email_change"
        ? await api.resendEmailChange({ challengeId: pendingProof.challengeId })
        : pendingProof.kind === "email_change_current_factor"
          ? await api.resendEmailChangeCurrentFactor({ challengeId: pendingProof.challengeId })
          : await api.resendEmailVerification({ challengeId: pendingProof.challengeId });
      setMessage(result.deliveryFailed ? "We couldn’t send the email. Try again." : "A new message is on its way.");
      setResendCooldown(result.deliveryFailed ? 0 : result.retryAfterSeconds ?? DEFAULT_COOLDOWN);
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === "resend_cooldown") {
        setResendCooldown(caught.retryAfterSeconds ?? DEFAULT_COOLDOWN);
        setError("Please wait before requesting another email.");
      } else {
        setError(safeAccountError(caught, "A new email could not be requested."));
      }
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className={styles.section} aria-labelledby="email-security-heading">
      <div className={styles.sectionIntro}>
        <span className={styles.icon}><Mail aria-hidden="true" /></span>
        <div>
          <h2 id="email-security-heading">Email and sign-in security</h2>
          <p>Your verified email is used for sign-in and account recovery.</p>
        </div>
      </div>

      <div className={styles.emailSecurity}>
        <div className={styles.emailStatus}>
          <span><strong>{accountStatus === "verified" ? "Verified email" : accountStatus === "email_upgrade_required" ? "Email needed" : "Verification pending"}</strong><small>{user.emailMasked ?? (accountStatus === "verified" ? "Verified address on file" : "No verified address yet")}</small></span>
          {accountStatus === "verified" ? <ShieldCheck aria-label="Verified" /> : null}
        </div>

        {error ? <p className={styles.error} role="alert">{error}</p> : null}
        {message ? <p className={styles.success} role="status">{message}</p> : null}

        {pendingProof?.kind === "email_change" ? (
          <div className={styles.linkProofPanel} role="group" aria-label="Confirm new email">
            <p>Open the link sent to {pendingProof.maskedEmail ?? "your new email"} to confirm the change. Your current email will stay active until then.</p>
            <p className={styles.securityNote}>The link expires after a short time. Requesting a new one will replace it.</p>
            <div className={styles.actions}>
              <button className={styles.secondaryButton} type="button" onClick={() => void resendProof()} disabled={Boolean(busy) || resendCooldown > 0}>{resendCooldown > 0 ? `Resend in ${resendCooldown}s` : "Resend confirmation link"}</button>
              <button className={styles.textButton} type="button" onClick={() => { setPendingProof(null); clearFeedback(); }} disabled={Boolean(busy)}>Close panel</button>
            </div>
          </div>
        ) : pendingProof ? (
          <form className={styles.form} onSubmit={confirmProof} noValidate>
            <label htmlFor="account-email-proof">{pendingProof.kind === "email_verification" ? "Six-digit verification code" : "Six-digit security code"}</label>
            <input
              ref={proofRef}
              id="account-email-proof"
              type="text"
              autoComplete="one-time-code"
              inputMode="numeric"
              pattern="[0-9]{6}"
              minLength={6}
              maxLength={6}
              value={proofCode}
              onChange={(event) => { setProofCode(event.target.value.replace(/\D/g, "")); setProofError(null); setError(null); }}
              aria-invalid={Boolean(proofError)}
              aria-describedby={proofError ? "account-email-proof-error" : undefined}
              required
            />
            {proofError ? <small className={styles.fieldError} id="account-email-proof-error">{proofError}</small> : null}
            {pendingProof.kind === "email_verification" ? (
              <>
                <label htmlFor="account-email-proof-password">Current password</label>
                <input
                  ref={proofPasswordRef}
                  id="account-email-proof-password"
                  type="password"
                  autoComplete="current-password"
                  value={proofPassword}
                  onChange={(event) => { setProofPassword(event.target.value); setProofPasswordError(null); setError(null); }}
                  aria-invalid={Boolean(proofPasswordError)}
                  aria-describedby={proofPasswordError ? "account-email-proof-password-error" : "account-email-proof-password-hint"}
                  required
                />
                <small id="account-email-proof-password-hint">Re-enter your password to finish verifying your email.</small>
                {proofPasswordError ? <small className={styles.fieldError} id="account-email-proof-password-error">{proofPasswordError}</small> : null}
              </>
            ) : null}
            <small className={styles.securityNote}>The code expires after a short time. Requesting a new one will replace it.</small>
            <div className={styles.actions}>
              <button className={styles.primaryButton} type="submit" disabled={Boolean(busy)}>{busy === "confirm-proof" ? "Confirming…" : "Confirm code"}</button>
              <button className={styles.textButton} type="button" onClick={() => void resendProof()} disabled={Boolean(busy) || resendCooldown > 0}>{resendCooldown > 0 ? `Resend in ${resendCooldown}s` : "Resend email"}</button>
              <button className={styles.textButton} type="button" onClick={() => { setPendingProof(null); setProofCode(""); setProofPassword(""); clearFeedback(); }} disabled={Boolean(busy)}>Not now</button>
            </div>
          </form>
        ) : (
          <>
            {accountStatus === "email_verification_required" ? (
              <p className={styles.securityNote}>Your email still needs verification. If the address is wrong or unreachable, replace it below using your current password.</p>
            ) : null}

            {(accountStatus === "email_upgrade_required" || showEmailForm) ? (
              <form className={styles.form} onSubmit={requestEmailAction} noValidate>
                <label htmlFor="account-email">{accountStatus === "email_upgrade_required" ? "Email address" : accountStatus === "email_verification_required" ? "Replacement email address" : "New email address"}</label>
                <input ref={emailRef} id="account-email" type="email" autoComplete="email" maxLength={254} value={email} onChange={(event) => { setEmail(event.target.value); setEmailError(null); setError(null); }} aria-invalid={Boolean(emailError)} aria-describedby={emailError ? "account-email-error" : undefined} required />
                {emailError ? <small className={styles.fieldError} id="account-email-error">{emailError}</small> : null}
                <label htmlFor="account-email-password">Current password</label>
                <input ref={currentPasswordRef} id="account-email-password" type="password" autoComplete="current-password" value={currentPassword} onChange={(event) => { setCurrentPassword(event.target.value); setPasswordError(null); setError(null); }} aria-invalid={Boolean(passwordError)} aria-describedby={passwordError ? "account-email-password-error" : undefined} required />
                {passwordError ? <small className={styles.fieldError} id="account-email-password-error">{passwordError}</small> : null}
                <div className={styles.actions}>
                  <button className={styles.primaryButton} type="submit" disabled={Boolean(busy)}>{busy === "email-request" ? "Sending…" : accountStatus === "email_upgrade_required" ? "Add and verify email" : accountStatus === "email_verification_required" ? "Replace email and send code" : "Verify new email"}</button>
                  {accountStatus === "verified" ? <button className={styles.textButton} type="button" onClick={() => { setShowEmailForm(false); setEmail(""); setCurrentPassword(""); clearFeedback(); }} disabled={Boolean(busy)}>Cancel</button> : null}
                </div>
              </form>
            ) : accountStatus === "verified" ? (
              <button className={styles.secondaryButton} type="button" onClick={() => { setShowEmailForm(true); clearFeedback(); }}>Change verified email…</button>
            ) : null}
          </>
        )}
      </div>
    </section>
  );
}
