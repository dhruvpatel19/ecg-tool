"use client";

import {
  BrainCircuit,
  CheckCircle2,
  Eye,
  EyeOff,
  GraduationCap,
  LogIn,
  MailCheck,
  ShieldCheck,
  Stethoscope,
  TimerReset,
  UserPlus,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  ApiError,
  api,
  type AccountResolutionResponse,
  type AuthAttemptResponse,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { safeAppPath } from "@/lib/routeAccess";
import styles from "./login.module.css";

type AuthMode = "login" | "register";
type AuthField = "identifier" | "email" | "replacementEmail" | "password" | "passwordConfirmation" | "verificationCode";
type FieldErrors = Partial<Record<AuthField, string>>;
type PendingChallenge = {
  kind: "email_verification";
  challengeId: string;
  maskedEmail: string | null;
  expiresAt: string | null;
};

const RESEND_COOLDOWN_SECONDS = 60;

// Deidentified Lead II segment from PTB-XL case 3 (CC BY 4.0), already
// included in the approved Foundations teaching corpus.
const registrationLeadII = [
  -0.079, -0.057, -0.061, 0.251, 0.248, -0.092, -0.09, -0.075, -0.067, -0.096,
  -0.073, -0.025, -0.02, 0.015, 0.089, 0.095, 0.145, 0.187, 0.244, 0.249,
  0.156, 0.073, 0.062, 0.047, 0.008, 0.04, 0.027, 0.012, -0.021, -0.031,
  -0.024, -0.057, -0.063, -0.092, -0.086, -0.055, -0.034, -0.08, -0.067, -0.073,
  -0.053, -0.034, -0.044, -0.015, 0.011, 0.095, 0.098, 0.057, 0.055, 0.029,
  -0.003, 0.033, 0.542, 0.103, -0.021, -0.058, -0.03, -0.034, -0.055, -0.049,
  -0.042, -0.019, -0.002, 0.018, 0.026, 0.004, 0.029, -0.007, 0.045, -0.002,
  -0.067, -0.123, -0.148, -0.172, -0.167, -0.14, -0.161, -0.15, -0.139, -0.113,
  -0.125, -0.117, -0.112, -0.105, -0.106, -0.057, -0.045, -0.036, -0.044, -0.074,
  -0.052, 0.003, -0.023, 0.013, 0.083, 0.06, 0.006, -0.046, -0.021, -0.058,
  0.127, 0.639, 0.016, -0.062, -0.059, -0.031, 0.003, -0.016, -0.028, -0.012,
  0.033, 0.036, 0.041, 0.11, 0.112, 0.132, 0.144, 0.138, 0.083, 0.094,
];
const registrationLeadIIPoints = registrationLeadII
  .map((value, index) => `${(index * 720 / (registrationLeadII.length - 1)).toFixed(1)},${(45 - value * 58).toFixed(1)}`)
  .join(" ");

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="page"><div className="panel pad">Loading account access…</div></div>}>
      <LoginScreen />
    </Suspense>
  );
}

export function safePostAuthPath(requested: string | null): string {
  return safeAppPath(requested, "/dashboard");
}

function LoginScreen() {
  const {
    user,
    loading: authLoading,
    login,
    register,
    confirmEmailVerification,
  } = useAuth();
  const router = useRouter();
  const search = useSearchParams();
  const next = safePostAuthPath(search.get("next"));
  const requestedMode: AuthMode = search.get("mode") === "register" ? "register" : "login";
  const [verificationLink] = useState(() => ({
    challengeId: search.get("challengeId")?.trim() ?? "",
    token: search.get("token")?.trim() ?? "",
  }));
  const hasVerificationLink = Boolean(verificationLink.challengeId && verificationLink.token);

  const [mode, setMode] = useState<AuthMode>(requestedMode);
  const [identifier, setIdentifier] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showPasswordConfirmation, setShowPasswordConfirmation] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [busy, setBusy] = useState(false);
  const [challenge, setChallenge] = useState<PendingChallenge | null>(null);
  const [verificationCode, setVerificationCode] = useState("");
  const [correctingEmail, setCorrectingEmail] = useState(false);
  const [replacementEmail, setReplacementEmail] = useState("");
  const [challengeMessage, setChallengeMessage] = useState<string | null>(null);
  const [accountResolution, setAccountResolution] = useState<AccountResolutionResponse | null>(null);
  const [registrationBlocked, setRegistrationBlocked] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);
  const passwordsMatch = mode === "register"
    && password.length >= 10
    && password === passwordConfirmation;

  const identifierRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const replacementEmailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const passwordConfirmationRef = useRef<HTMLInputElement>(null);
  const verificationCodeRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setMode(requestedMode);
  }, [requestedMode]);

  useLayoutEffect(() => {
    if (!hasVerificationLink || typeof window === "undefined") return;
    const cleanParams = new URLSearchParams();
    if (next !== "/dashboard") cleanParams.set("next", next);
    const cleanQuery = cleanParams.toString();
    window.history.replaceState(window.history.state, "", cleanQuery ? `/login?${cleanQuery}` : "/login");
  }, [hasVerificationLink, next]);

  useEffect(() => {
    if (!hasVerificationLink) return;
    setChallenge({
      kind: "email_verification",
      challengeId: verificationLink.challengeId,
      maskedEmail: null,
      expiresAt: null,
    });
    setVerificationCode(verificationLink.token);
    setChallengeMessage("Your verification link is ready to confirm.");
  }, [hasVerificationLink, verificationLink]);

  useEffect(() => {
    if (resendCooldown <= 0) return;
    const timer = window.setTimeout(() => setResendCooldown((value) => Math.max(0, value - 1)), 1_000);
    return () => window.clearTimeout(timer);
  }, [resendCooldown]);

  useEffect(() => {
    if (authLoading || !user || hasVerificationLink) return;
    if (user.accountStatus && user.accountStatus !== "verified") {
      router.replace("/account?setup=email");
    } else {
      router.replace(next);
    }
  }, [authLoading, hasVerificationLink, next, router, user]);

  function authHref(nextMode: AuthMode): string {
    const params = new URLSearchParams();
    if (nextMode === "register") params.set("mode", "register");
    if (next !== "/dashboard") params.set("next", next);
    const query = params.toString();
    return query ? `/login?${query}` : "/login";
  }

  function focusField(field: AuthField) {
    const target = {
      identifier: identifierRef,
      email: emailRef,
      replacementEmail: replacementEmailRef,
      password: passwordRef,
      passwordConfirmation: passwordConfirmationRef,
      verificationCode: verificationCodeRef,
    }[field];
    window.requestAnimationFrame(() => target.current?.focus());
  }

  function setFieldFailure(field: AuthField, message: string) {
    setFieldErrors({ [field]: message });
    setError("Check the highlighted field and try again.");
    focusField(field);
  }

  function clearFeedback() {
    setError(null);
    setFieldErrors({});
    setChallengeMessage(null);
    setRegistrationBlocked(false);
  }

  function presentAuthError(caught: unknown) {
    if (!(caught instanceof ApiError)) {
      setError("TRACE could not complete that account request. Please try again.");
      return;
    }
    const code = caught.code;
    if (code === "invalid_email" || code === "email_required") {
      setFieldFailure("email", "Enter a valid email address.");
    } else if (code === "password_too_short") {
      setFieldFailure("password", "Use at least 10 characters.");
    } else if (code === "password_too_common") {
      setFieldFailure("password", "Choose a less common passphrase that is not your username.");
    } else if (code === "username_taken") {
      setError("We couldn’t create the account. Please try again.");
    } else if (code === "account_exists" || code === "registration_unavailable") {
      setError("We couldn’t create an account with those details. Try another username, or sign in or reset your password if the account may be yours.");
      setRegistrationBlocked(true);
    } else if (code === "email_delivery_unavailable") {
      setError("Email delivery is temporarily unavailable. Please try again later.");
    } else if (code === "registration_throttled" || caught.status === 429) {
      setError("Too many account attempts. Please wait a few minutes and try again.");
    } else if (caught.status === 401) {
      setError("Incorrect email or password.");
      focusField("identifier");
    } else {
      setError("TRACE could not complete that account request. Please check your details and try again.");
    }
  }

  function presentChallenge(result: AuthAttemptResponse) {
    if ("verificationRequired" in result && result.verificationRequired) {
      setAccountResolution(null);
      setPassword("");
      setPasswordConfirmation("");
      setShowPassword(false);
      setShowPasswordConfirmation(false);
      setChallenge({
        kind: "email_verification",
        challengeId: result.challengeId,
        maskedEmail: result.maskedEmail,
        expiresAt: result.expiresAt,
      });
      setVerificationCode("");
      setCorrectingEmail(false);
      setReplacementEmail("");
      setChallengeMessage(result.deliveryFailed
        ? "We couldn’t send the verification email. Try again."
        : `We sent a six-digit verification code to ${result.maskedEmail ?? "your email address"}.`);
      setResendCooldown(result.deliveryFailed ? 0 : result.retryAfterSeconds ?? RESEND_COOLDOWN_SECONDS);
      return true;
    }
    return false;
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    clearFeedback();

    const nextErrors: FieldErrors = {};
    if (mode === "login") {
      if (!identifier.trim()) nextErrors.identifier = "Enter your email address.";
      else if (!identifierRef.current?.validity.valid) nextErrors.identifier = "Enter a valid email address.";
    }
    if (mode === "register") {
      if (!email.trim()) nextErrors.email = "Enter your email address.";
      else if (!emailRef.current?.validity.valid) nextErrors.email = "Enter a valid email address.";
    }
    if (!password) nextErrors.password = "Enter your password.";
    else if (mode === "register" && password.length < 10) nextErrors.password = "Use at least 10 characters.";
    if (mode === "register" && password !== passwordConfirmation) {
      nextErrors.passwordConfirmation = "Enter the same password again.";
    }
    const firstInvalid = ([mode === "login" ? "identifier" : "email", "password", "passwordConfirmation"] as AuthField[])
      .find((field) => nextErrors[field]);
    if (firstInvalid) {
      setFieldErrors(nextErrors);
      setError("Check the highlighted fields and try again.");
      focusField(firstInvalid);
      return;
    }

    setBusy(true);
    try {
      const result = mode === "register"
        ? await register(email.trim(), password)
        : await login(identifier.trim(), password);
      if (!presentChallenge(result)) router.push(next);
    } catch (caught) {
      presentAuthError(caught);
    } finally {
      setBusy(false);
    }
  }

  async function confirmChallenge(event: React.FormEvent) {
    event.preventDefault();
    if (!challenge || busy) return;
    clearFeedback();
    const code = verificationCode.trim();
    if (!code) {
      setFieldFailure("verificationCode", "Enter the verification code from your email.");
      return;
    }
    if (!/^\d{6}$/.test(code)) {
      setFieldFailure("verificationCode", "Enter the complete six-digit code.");
      return;
    }
    if (!password) {
      setFieldFailure("password", "Enter your password again to verify this account.");
      return;
    }

    setBusy(true);
    try {
      const result = await confirmEmailVerification(challenge.challengeId, code, password);
      if ("accountResolutionRequired" in result) {
        setVerificationCode("");
        setPassword("");
        setChallenge(null);
        setChallengeMessage(null);
        setAccountResolution(result);
        return;
      }
      setVerificationCode("");
      setPassword("");
      router.replace(next);
    } catch (caught) {
      const codeName = caught instanceof ApiError ? caught.code : null;
      if (codeName === "invalid_verification_credentials" || codeName === "invalid_current_password" || codeName === "invalid_credentials" || (caught instanceof ApiError && caught.status === 401)) {
        setPassword("");
        setVerificationCode("");
        setFieldFailure("password", "That code or password was not accepted. Check the email and enter both again.");
        return;
      }
      if (codeName === "reauth_throttled") {
        setPassword("");
        setVerificationCode("");
        setFieldFailure("password", "Too many verification attempts. Wait before trying again.");
        return;
      }
      const message = codeName === "challenge_incorrect"
        ? "That code was not accepted. Check the message and try again."
        : codeName === "challenge_attempts_exhausted"
          ? "That challenge has reached its attempt limit. Start the sign-in flow again."
          : codeName === "challenge_used"
            ? "That challenge was already used. Sign in again to continue."
            : "That verification code or link is invalid or expired. Request a new message and try again.";
      setVerificationCode("");
      setPassword("");
      setFieldFailure("verificationCode", message);
    } finally {
      setBusy(false);
    }
  }

  async function replacePendingEmail(event: React.FormEvent) {
    event.preventDefault();
    if (!challenge || challenge.kind !== "email_verification" || busy) return;
    clearFeedback();
    if (!replacementEmail.trim() || !replacementEmailRef.current?.validity.valid) {
      setFieldFailure("replacementEmail", "Enter a valid replacement email address.");
      return;
    }
    if (!password) {
      setFieldFailure("password", "Enter the password from this registration attempt.");
      return;
    }

    setBusy(true);
    try {
      const result = await api.replaceUnverifiedEmail({
        challengeId: challenge.challengeId,
        currentPassword: password,
        newEmail: replacementEmail.trim(),
      });
      setChallenge({
        kind: "email_verification",
        challengeId: result.challengeId,
        maskedEmail: result.maskedEmail,
        expiresAt: result.expiresAt,
      });
      setVerificationCode("");
      setPassword("");
      setReplacementEmail("");
      setCorrectingEmail(false);
      setChallengeMessage(result.deliveryFailed
        ? "The address was updated, but the verification email could not be sent. Retry now."
        : `A new verification message was sent to ${result.maskedEmail ?? "the replacement email"}.`);
      setResendCooldown(result.deliveryFailed ? 0 : result.retryAfterSeconds ?? RESEND_COOLDOWN_SECONDS);
    } catch (caught) {
      const code = caught instanceof ApiError ? caught.code : null;
      if (code === "invalid_email") {
        setFieldFailure("replacementEmail", "Enter a valid replacement email address.");
      } else if (code === "reauth_throttled" || (caught instanceof ApiError && caught.status === 429)) {
        setError("Too many attempts. Wait before trying to update this email again.");
      } else {
        setPassword("");
        setError("We couldn’t update the email. Check the address and password, then try again.");
        focusField("password");
      }
    } finally {
      setBusy(false);
    }
  }

  async function resendChallenge() {
    if (!challenge || busy || resendCooldown > 0) return;
    clearFeedback();
    setBusy(true);
    try {
      const result = await api.resendEmailVerification({ challengeId: challenge.challengeId });
      if (result.deliveryFailed) {
        setVerificationCode("");
        setPassword("");
        setChallengeMessage("We couldn’t send the email. Try again.");
        setResendCooldown(0);
      } else {
        setVerificationCode("");
        setPassword("");
        setChallengeMessage("A new message is on its way.");
        setResendCooldown(result.retryAfterSeconds ?? RESEND_COOLDOWN_SECONDS);
      }
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === "resend_cooldown") {
        setResendCooldown(caught.retryAfterSeconds ?? RESEND_COOLDOWN_SECONDS);
        setError("Please wait before requesting another message.");
      } else if (caught instanceof ApiError && caught.code === "resend_limit") {
        setError("This challenge cannot send more messages. Return to sign in and start again.");
      } else {
        setError("A new message could not be requested. Please try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  function selectMode(nextMode: AuthMode) {
    setMode(nextMode);
    setChallenge(null);
    setAccountResolution(null);
    setVerificationCode("");
    setCorrectingEmail(false);
    setReplacementEmail("");
    setPassword("");
    setPasswordConfirmation("");
    setShowPassword(false);
    setShowPasswordConfirmation(false);
    clearFeedback();
    router.replace(authHref(nextMode), { scroll: false });
  }

  function handleModeKeyDown(event: React.KeyboardEvent<HTMLButtonElement>) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const nextMode = event.key === "ArrowLeft" || event.key === "Home" ? "login" : "register";
    selectMode(nextMode);
    document.getElementById(`auth-tab-${nextMode}`)?.focus();
  }

  function returnToSignIn() {
    setChallenge(null);
    setAccountResolution(null);
    setVerificationCode("");
    setCorrectingEmail(false);
    setReplacementEmail("");
    selectMode("login");
  }

  function beginEmailCorrection() {
    clearFeedback();
    setVerificationCode("");
    setPassword("");
    setReplacementEmail("");
    setCorrectingEmail(true);
    window.requestAnimationFrame(() => replacementEmailRef.current?.focus());
  }

  const challengeDestination = challenge?.maskedEmail ?? "the email address on your account";
  const showRegistrationContext = mode === "register" && !challenge && !accountResolution;
  const resolutionNeedsReset = accountResolution?.suggestedAction === "reset_password";

  return (
    <div className={`page auth-page ${styles.authPage} ${showRegistrationContext ? styles.registrationAuthPage : styles.focusedAuthPage}`}>
      {showRegistrationContext ? <section className={styles.welcome} aria-labelledby="auth-welcome-title">
        <div className={styles.welcomeCopy}>
          <p className={styles.kicker}>Practice that changes how you read</p>
          <h1 id="auth-welcome-title">See the tracing. Make the call. Learn from every read.</h1>
          <p>
            Build ECG reasoning through guided lessons, deliberate repetition, rapid reads,
            and clinical reasoning—all in one learning record.
          </p>
        </div>

        <ol className={styles.modePath} aria-label="Four ECG learning modes">
          <li><GraduationCap aria-hidden="true" /><span><strong>Learn</strong><small>Build the mental model</small></span></li>
          <li><BrainCircuit aria-hidden="true" /><span><strong>Train</strong><small>Repeat one visual skill</small></span></li>
          <li><TimerReset aria-hidden="true" /><span><strong>Rapid</strong><small>Practice a complete read</small></span></li>
          <li><Stethoscope aria-hidden="true" /><span><strong>Cases</strong><small>Use it in patient scenarios</small></span></li>
        </ol>

        <div className={styles.traceSignal} aria-hidden="true">
          <div className={styles.traceMeta}><span>Lead II</span><small>PTB-XL case 3 · CC BY 4.0</small></div>
          <svg viewBox="0 0 720 90" preserveAspectRatio="none">
            <defs>
              <pattern id="registration-ecg-small-grid" width="12" height="12" patternUnits="userSpaceOnUse">
                <path d="M 12 0 L 0 0 0 12" fill="none" stroke="rgba(235, 196, 190, .13)" strokeWidth=".7" />
              </pattern>
            </defs>
            <rect width="720" height="90" fill="url(#registration-ecg-small-grid)" />
            <polyline points={registrationLeadIIPoints} fill="none" stroke="#76d4b0" strokeWidth="2" vectorEffect="non-scaling-stroke" />
          </svg>
        </div>

        <p className={styles.coachingNote}>
          <ShieldCheck size={17} aria-hidden="true" />
          <span><strong>Designed for learning.</strong> AI coaches your reasoning; it does not replace clinical judgment.</span>
        </p>
      </section> : (
        <div className={styles.focusedBrand} aria-label="TRACE ECG learning">
          <strong>TRACE</strong>
          <svg viewBox="0 0 720 90" role="img" aria-label="Lead II ECG cue" preserveAspectRatio="none">
            <polyline points={registrationLeadIIPoints} fill="none" stroke="currentColor" strokeWidth="1.7" vectorEffect="non-scaling-stroke" />
          </svg>
          <span>ECG learning</span>
        </div>
      )}

      <section className={`auth-card ${styles.authCard} ${showRegistrationContext ? "" : styles.focusedAuthCard}`} aria-labelledby="auth-title">
        <header className={styles.formHeader}>
          <p>{accountResolution ? "Email confirmed" : correctingEmail ? "Fix the destination" : challenge ? "One more step" : mode === "login" ? "Welcome back" : "Start learning"}</p>
          {showRegistrationContext ? (
            <h2 id="auth-title">Create your account</h2>
          ) : (
            <h1 id="auth-title">
              {accountResolution
                ? "This email already has a TRACE account"
                : correctingEmail
                  ? "Use a different email"
                : challenge
                  ? "Verify your email"
                  : "Sign in"}
            </h1>
          )}
          <span>
            {accountResolution
              ? "No new account was created. Choose how you’d like to continue."
              : correctingEmail
                ? "Enter the replacement address and the password from this registration attempt."
              : challenge
              ? `Use the message sent to ${challengeDestination}.`
              : mode === "login"
                ? "Continue where you left off on any device."
                : "Create an account to save your progress."}
          </span>
        </header>

        {search.get("accountDeleted") === "1" ? (
          <div className={`${styles.notice} ${styles.successNotice}`} role="status">
            Your account and live learning record were deleted.
            {search.get("localCleanup") === "failed"
              ? " This browser blocked local draft cleanup; clear this site’s browser data before another person uses it."
              : null}
          </div>
        ) : null}
        {search.get("verificationLink") === "invalid" ? (
          <div className={`${styles.notice} ${styles.errorNotice}`} role="alert">
            That verification link is incomplete. Sign in to request a new message.
          </div>
        ) : null}
        {search.get("passwordReset") === "1" ? (
          <div className={`${styles.notice} ${styles.successNotice}`} role="status">
            Your password was updated. Sign in with your new password.
          </div>
        ) : null}

        {!challenge && !accountResolution ? (
          <div className={styles.modeTabs} role="tablist" aria-label="Authentication mode">
            <button id="auth-tab-login" type="button" role="tab" aria-selected={mode === "login"} aria-controls="auth-panel" tabIndex={mode === "login" ? 0 : -1} className={mode === "login" ? styles.activeTab : ""} onClick={() => selectMode("login")} onKeyDown={handleModeKeyDown}>Sign in</button>
            <button id="auth-tab-register" type="button" role="tab" aria-selected={mode === "register"} aria-controls="auth-panel" tabIndex={mode === "register" ? 0 : -1} className={mode === "register" ? styles.activeTab : ""} onClick={() => selectMode("register")} onKeyDown={handleModeKeyDown}>Register</button>
          </div>
        ) : null}

        {error ? <div className={`${styles.notice} ${styles.errorNotice}`} id="auth-error" role="alert">{error}</div> : null}
        {registrationBlocked && error ? (
          <div className={styles.registrationHelp} aria-label="Existing account options">
            <button type="button" onClick={() => selectMode("login")}>Sign in instead</button>
            <Link href="/forgot-password">Reset password</Link>
          </div>
        ) : null}
        {challengeMessage ? <div className={`${styles.notice} ${styles.successNotice}`} role="status">{challengeMessage}</div> : null}

        {accountResolution ? (
          <section className={styles.accountResolution} aria-labelledby="account-resolution-heading">
            <div>
              <MailCheck size={20} aria-hidden="true" />
              <div>
                <h2 id="account-resolution-heading">{resolutionNeedsReset ? "Finish recovering this account" : "Continue with the account you already have"}</h2>
                <p>{resolutionNeedsReset
                  ? "An account already uses this email. Reset the password before signing in."
                  : "Sign in with your existing password, or reset it if you do not remember it."}</p>
              </div>
            </div>
            <div className={styles.resolutionActions}>
              {resolutionNeedsReset ? (
                <>
                  <Link className={styles.submitButton} href="/forgot-password">Reset password</Link>
                  <button className={styles.secondaryAction} type="button" onClick={() => selectMode("login")}>Back to sign in</button>
                </>
              ) : (
                <>
                  <button className={styles.submitButton} type="button" onClick={() => selectMode("login")}>Sign in</button>
                  <Link className={styles.secondaryAction} href="/forgot-password">Reset password</Link>
                </>
              )}
            </div>
          </section>
        ) : challenge && correctingEmail && challenge.kind === "email_verification" ? (
          <form className={styles.authForm} onSubmit={replacePendingEmail} noValidate>
            <div className={styles.field}>
              <label htmlFor="auth-replacement-email">Replacement email</label>
              <input
                ref={replacementEmailRef}
                id="auth-replacement-email"
                name="replacementEmail"
                type="email"
                autoComplete="email"
                maxLength={254}
                value={replacementEmail}
                onChange={(event) => {
                  setReplacementEmail(event.target.value);
                  setFieldErrors((current) => ({ ...current, replacementEmail: undefined }));
                  setError(null);
                }}
                aria-invalid={Boolean(fieldErrors.replacementEmail)}
                aria-describedby={fieldErrors.replacementEmail ? "auth-replacement-email-error" : "auth-replacement-email-note"}
                required
              />
              <small className={styles.fieldHint} id="auth-replacement-email-note">We’ll send a new verification message to this address.</small>
              {fieldErrors.replacementEmail ? <small className={styles.fieldError} id="auth-replacement-email-error">{fieldErrors.replacementEmail}</small> : null}
            </div>
            <div className={styles.field}>
              <label htmlFor="auth-replacement-password">Registration password</label>
              <input
                ref={passwordRef}
                id="auth-replacement-password"
                name="currentPassword"
                type="password"
                autoComplete="current-password"
                maxLength={256}
                value={password}
                onChange={(event) => {
                  setPassword(event.target.value);
                  setFieldErrors((current) => ({ ...current, password: undefined }));
                  setError(null);
                }}
                aria-invalid={Boolean(fieldErrors.password)}
                aria-describedby={fieldErrors.password ? "auth-replacement-password-error" : "auth-replacement-password-note"}
                required
              />
              <small className={styles.fieldHint} id="auth-replacement-password-note">Enter the password you just chose.</small>
              {fieldErrors.password ? <small className={styles.fieldError} id="auth-replacement-password-error">{fieldErrors.password}</small> : null}
            </div>
            <button className={styles.submitButton} type="submit" disabled={busy}>
              <MailCheck size={17} aria-hidden="true" /> {busy ? "Updating…" : "Update email and send code"}
            </button>
            <div className={styles.challengeActions}>
              <button className={styles.textButton} type="button" onClick={() => { setCorrectingEmail(false); setReplacementEmail(""); setPassword(""); clearFeedback(); }} disabled={busy}>Back to verification</button>
              <button className={styles.textButton} type="button" onClick={returnToSignIn} disabled={busy}>Back to sign in</button>
            </div>
          </form>
        ) : challenge ? (
          <form className={styles.authForm} onSubmit={confirmChallenge} noValidate>
            <div className={styles.field}>
              <label htmlFor="auth-verification-code">
                Six-digit verification code
              </label>
              <input
                ref={verificationCodeRef}
                id="auth-verification-code"
                name="one-time-code"
                type="text"
                autoComplete="one-time-code"
                inputMode="numeric"
                pattern="[0-9]{6}"
                minLength={6}
                maxLength={6}
                spellCheck={false}
                value={verificationCode}
                onChange={(event) => {
                  const value = event.target.value.replace(/\D/g, "");
                  setVerificationCode(value);
                  setFieldErrors((current) => ({ ...current, verificationCode: undefined }));
                  setError(null);
                }}
                aria-invalid={Boolean(fieldErrors.verificationCode)}
                aria-describedby={fieldErrors.verificationCode ? "auth-verification-error" : undefined}
                autoFocus
                required
              />
              {fieldErrors.verificationCode ? <small className={styles.fieldError} id="auth-verification-error">{fieldErrors.verificationCode}</small> : null}
            </div>
            <div className={styles.field}>
                <label htmlFor="auth-verification-password">Password</label>
                <input
                  ref={passwordRef}
                  id="auth-verification-password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  maxLength={256}
                  value={password}
                  onChange={(event) => {
                    setPassword(event.target.value);
                    setFieldErrors((current) => ({
                      ...current,
                      password: undefined,
                      ...(mode === "register" ? { passwordConfirmation: undefined } : {}),
                    }));
                    setError(null);
                  }}
                  aria-invalid={Boolean(fieldErrors.password)}
                  aria-describedby={fieldErrors.password ? "auth-verification-password-error" : "auth-verification-password-note"}
                  required
                />
                <small className={styles.fieldHint} id="auth-verification-password-note">Re-enter your password to finish creating your account.</small>
                {fieldErrors.password ? <small className={styles.fieldError} id="auth-verification-password-error">{fieldErrors.password}</small> : null}
            </div>
            <button className={styles.submitButton} type="submit" disabled={busy}>
              <MailCheck size={17} aria-hidden="true" /> {busy ? "Verifying…" : "Verify email"}
            </button>
            <div className={styles.challengeActions}>
              <button className={styles.textButton} type="button" onClick={() => void resendChallenge()} disabled={busy || resendCooldown > 0}>
                {resendCooldown > 0 ? `Resend in ${resendCooldown}s` : "Resend email"}
              </button>
              <button className={styles.textButton} type="button" onClick={beginEmailCorrection} disabled={busy}>Use a different email</button>
              <button className={styles.textButton} type="button" onClick={returnToSignIn} disabled={busy}>Back to sign in</button>
            </div>
          </form>
        ) : (
          <form className={styles.authForm} id="auth-panel" role="tabpanel" aria-labelledby={`auth-tab-${mode}`} onSubmit={onSubmit} noValidate>
            {mode === "login" ? <div className={styles.field}>
              <label htmlFor="auth-email-signin">Email</label>
              <input
                ref={identifierRef}
                id="auth-email-signin"
                name="identifier"
                type="email"
                autoComplete="email"
                maxLength={254}
                value={identifier}
                onChange={(event) => { setIdentifier(event.target.value); setFieldErrors((current) => ({ ...current, identifier: undefined })); setError(null); }}
                aria-invalid={Boolean(fieldErrors.identifier)}
                aria-describedby={fieldErrors.identifier ? "auth-identifier-error" : undefined}
                required
              />
              {fieldErrors.identifier ? <small className={styles.fieldError} id="auth-identifier-error">{fieldErrors.identifier}</small> : null}
            </div> : null}

            {mode === "register" ? (
              <>
                <div className={`${styles.field} ${styles.registrationEmailField}`}>
                  <label htmlFor="auth-email">Email</label>
                  <input
                    ref={emailRef}
                    id="auth-email"
                    name="email"
                    type="email"
                    autoComplete="email"
                    maxLength={254}
                    value={email}
                    onChange={(event) => { setEmail(event.target.value); setFieldErrors((current) => ({ ...current, email: undefined })); setError(null); }}
                    aria-invalid={Boolean(fieldErrors.email)}
                    aria-describedby={fieldErrors.email ? "auth-email-error" : "auth-email-note"}
                    required
                  />
                  <small className={styles.fieldHint} id="auth-email-note">We use this only for verification, account recovery, and security messages.</small>
                  {fieldErrors.email ? <small className={styles.fieldError} id="auth-email-error">{fieldErrors.email}</small> : null}
                </div>
              </>
            ) : null}

            <div className={styles.field}>
              <label htmlFor="auth-password">Password</label>
              <div className={styles.passwordField}>
                <input
                  ref={passwordRef}
                  id="auth-password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  minLength={mode === "register" ? 10 : undefined}
                  maxLength={256}
                  autoComplete={mode === "register" ? "new-password" : "current-password"}
                  value={password}
                  onChange={(event) => { setPassword(event.target.value); setFieldErrors((current) => ({ ...current, password: undefined })); setError(null); }}
                  aria-invalid={Boolean(fieldErrors.password)}
                  aria-describedby={[mode === "register" ? "auth-password-requirement" : null, fieldErrors.password ? "auth-password-error" : null].filter(Boolean).join(" ") || undefined}
                  required
                />
                <button className={styles.passwordToggle} type="button" aria-label={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword} onClick={() => setShowPassword((visible) => !visible)}>
                  {showPassword ? <EyeOff size={17} aria-hidden="true" /> : <Eye size={17} aria-hidden="true" />}
                </button>
              </div>
              {fieldErrors.password ? <small className={styles.fieldError} id="auth-password-error">{fieldErrors.password}</small> : null}
              {mode === "login" ? <Link className={styles.forgotLink} href="/forgot-password">Forgot your password?</Link> : null}
              {mode === "register" ? <small className={styles.passwordHint} id="auth-password-requirement">Use 10–256 characters. Avoid repeated characters and common passwords.</small> : null}
            </div>

            {mode === "register" ? (
              <>
                <div className={styles.field}>
                  <label htmlFor="auth-password-confirm">Confirm password</label>
                  <div className={`${styles.passwordField} ${passwordsMatch ? styles.passwordMatch : ""}`}>
                    <input
                      ref={passwordConfirmationRef}
                      id="auth-password-confirm"
                      name="passwordConfirmation"
                      type={showPasswordConfirmation ? "text" : "password"}
                      minLength={10}
                      maxLength={256}
                      autoComplete="new-password"
                      value={passwordConfirmation}
                      onChange={(event) => { setPasswordConfirmation(event.target.value); setFieldErrors((current) => ({ ...current, passwordConfirmation: undefined })); setError(null); }}
                      aria-invalid={Boolean(fieldErrors.passwordConfirmation)}
                      aria-describedby={fieldErrors.passwordConfirmation
                        ? "auth-password-confirm-error"
                        : passwordsMatch
                          ? "auth-password-confirm-match"
                          : undefined}
                      required
                    />
                    <button className={styles.passwordToggle} type="button" aria-label={showPasswordConfirmation ? "Hide confirmation password" : "Show confirmation password"} aria-pressed={showPasswordConfirmation} onClick={() => setShowPasswordConfirmation((visible) => !visible)}>
                      {showPasswordConfirmation ? <EyeOff size={17} aria-hidden="true" /> : <Eye size={17} aria-hidden="true" />}
                    </button>
                  </div>
                  {fieldErrors.passwordConfirmation ? <small className={styles.fieldError} id="auth-password-confirm-error">{fieldErrors.passwordConfirmation}</small> : null}
                  {passwordsMatch && !fieldErrors.passwordConfirmation ? (
                    <small className={styles.fieldSuccess} id="auth-password-confirm-match" role="status">
                      <CheckCircle2 size={14} aria-hidden="true" /> Passwords match
                    </small>
                  ) : null}
                </div>
              </>
            ) : null}

            <button className={styles.submitButton} type="submit" disabled={busy}>
              {mode === "login" ? <LogIn size={17} aria-hidden="true" /> : <UserPlus size={17} aria-hidden="true" />}
              {busy ? "Please wait..." : mode === "login" ? "Sign in" : "Create account"}
            </button>
            {mode === "register" ? (
              <p className={styles.termsNote}>
                By creating an account, you agree to the <Link href="/terms">Terms</Link> and acknowledge the <Link href="/privacy">Privacy Notice</Link>.
              </p>
            ) : null}
          </form>
        )}

        <p className={styles.privacyNote}>
          <ShieldCheck size={14} aria-hidden="true" />
          Account progress is private. TRACE is for education, not clinical diagnosis.
        </p>
      </section>
    </div>
  );
}
