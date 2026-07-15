"use client";

import { ArrowLeft, CheckCircle2, MailCheck, ShieldCheck, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { Suspense, useLayoutEffect, useRef, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { emailedLinkProof, PENDING_EMAIL_CHANGE_PROOF_KEY } from "@/lib/routeAccess";
import styles from "../../forgot-password/recovery.module.css";

type EmailChangeProof = {
  challengeId: string;
  token: string;
};

const TERMINAL_EMAIL_CHANGE_CODES = new Set([
  "challenge_attempts_exhausted",
  "challenge_expired",
  "challenge_invalid",
  "challenge_stale",
  "challenge_used",
  "account_changed",
  "email_unavailable",
]);

export default function ConfirmEmailChangePage() {
  return (
    <Suspense fallback={<EmailChangeLoading />}>
      <EmailChangeScreen />
    </Suspense>
  );
}

function EmailChangeLoading() {
  return (
    <div className={styles.recoveryPage}>
      <section className={styles.contextPanel} aria-labelledby="email-change-loading-title">
        <div>
          <span className={styles.contextIcon} aria-hidden="true"><MailCheck size={22} /></span>
          <p className={styles.eyebrow}>Account security</p>
          <h1 id="email-change-loading-title">Confirm your new email.</h1>
        </div>
      </section>
      <section className={styles.formCard} aria-label="Loading email change confirmation">
        <p>Checking your confirmation link…</p>
      </section>
    </div>
  );
}

function EmailChangeScreen() {
  const { user, loading, refreshUser } = useAuth();
  const [proof, setProof] = useState<EmailChangeProof>({ challengeId: "", token: "" });
  const [proofReady, setProofReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [complete, setComplete] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const completeProof = Boolean(proof.challengeId && proof.token);
  const proofCaptured = useRef(false);

  function clearStoredProof() {
    try {
      window.sessionStorage.removeItem(PENDING_EMAIL_CHANGE_PROOF_KEY);
    } catch {
      // The proof is still removed from React state on terminal outcomes.
    }
  }

  useLayoutEffect(() => {
    if (proofCaptured.current || typeof window === "undefined") return;
    proofCaptured.current = true;
    const fromUrl = emailedLinkProof(window.location.search, window.location.hash);
    try {
      if (fromUrl.challengeId && fromUrl.token) {
        window.sessionStorage.setItem(PENDING_EMAIL_CHANGE_PROOF_KEY, JSON.stringify({ ...fromUrl, savedAt: Date.now() }));
        setProof(fromUrl);
        return;
      }
      const raw = window.sessionStorage.getItem(PENDING_EMAIL_CHANGE_PROOF_KEY);
      if (raw) {
        const saved = JSON.parse(raw) as { challengeId?: unknown; token?: unknown; savedAt?: unknown };
        const fresh = typeof saved.savedAt === "number" && Date.now() - saved.savedAt < 24 * 60 * 60 * 1_000;
        if (fresh && typeof saved.challengeId === "string" && typeof saved.token === "string") {
          setProof({ challengeId: saved.challengeId.trim(), token: saved.token.trim() });
        } else {
          window.sessionStorage.removeItem(PENDING_EMAIL_CHANGE_PROOF_KEY);
        }
      }
    } catch {
      // An unavailable tab store leaves the mounted URL proof in memory. A
      // malformed stored handoff is treated as an incomplete link.
    } finally {
      if (window.location.search || window.location.hash) {
        window.history.replaceState(window.history.state, "", "/account/email-change");
      }
      setProofReady(true);
    }
  }, []);

  async function confirm() {
    if (!completeProof || busy) return;
    setBusy(true);
    setError(null);
    try {
      await api.confirmEmailChange({ challengeId: proof.challengeId, token: proof.token });
      clearStoredProof();
      await refreshUser();
      setComplete(true);
    } catch (caught) {
      const code = caught instanceof ApiError ? caught.code : null;
      if (code && TERMINAL_EMAIL_CHANGE_CODES.has(code)) {
        clearStoredProof();
      }
      if (code === "challenge_stale") {
        setError("Your account changed after this link was sent. Return to account settings and start again.");
      } else if (code === "email_unavailable") {
        setError("That email can no longer be added to this account. Return to account settings and choose another address.");
      } else if (code === "challenge_incorrect") {
        setError("That confirmation wasn’t accepted. Please try again.");
      } else if (code && TERMINAL_EMAIL_CHANGE_CODES.has(code)) {
        setError("This confirmation link is invalid, expired, or has already been used. Return to account settings and request a new message.");
      } else {
        setError("The email change could not be confirmed right now. Please try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.recoveryPage}>
      <section className={styles.contextPanel} aria-labelledby="email-change-page-title">
        <div>
          <span className={styles.contextIcon} aria-hidden="true"><MailCheck size={22} /></span>
          <p className={styles.eyebrow}>Account security</p>
          <h1 id="email-change-page-title">Confirm your new email.</h1>
          <p className={styles.contextCopy}>Your current email remains active until the new address is verified.</p>
        </div>
        <p className={styles.privacyNote}>
          <ShieldCheck size={16} aria-hidden="true" />
          For your security, confirmation links expire after a short time.
        </p>
      </section>

      <section className={styles.formCard} aria-labelledby="email-change-title">
        {!proofReady ? (
          <div className={styles.stateBlock} role="status">
            <span className={styles.stateIcon} aria-hidden="true"><MailCheck size={23} /></span>
            <h2 id="email-change-title">Checking your confirmation link</h2>
            <p>One moment while we check your link.</p>
          </div>
        ) : complete ? (
          <div className={styles.stateBlock} role="status" aria-live="polite">
            <span className={styles.stateIcon} aria-hidden="true"><CheckCircle2 size={23} /></span>
            <h2 id="email-change-title">Email updated</h2>
            <p>Your new email is verified. Other signed-in sessions were closed to protect your account.</p>
            <div className={styles.stateActions}>
              <Link className={styles.primaryLink} href="/account">Return to account settings</Link>
            </div>
          </div>
        ) : !completeProof ? (
          <div className={styles.stateBlock} role="alert">
            <span className={styles.stateIcon} aria-hidden="true"><TriangleAlert size={23} /></span>
            <h2 id="email-change-title">This confirmation link is incomplete</h2>
            <p>Return to account settings and request a new email-change message.</p>
            <div className={styles.stateActions}>
              <Link className={styles.primaryLink} href="/account">Return to account settings</Link>
            </div>
          </div>
        ) : (
          <div className={styles.stateBlock}>
            <span className={styles.stateIcon} aria-hidden="true"><MailCheck size={23} /></span>
            <h2 id="email-change-title">Verify the new address</h2>
            <p>Confirm this change only if you requested it from your account settings.</p>
            {error ? <p className={styles.formError} role="alert">{error}</p> : null}
            <div className={styles.stateActions}>
              <button className={styles.submitButton} type="button" onClick={() => void confirm()} disabled={busy || loading || !user}>
                <MailCheck size={17} aria-hidden="true" /> {busy ? "Confirming…" : loading ? "Checking session…" : "Confirm new email"}
              </button>
              <Link className={styles.secondaryLink} href="/account"><ArrowLeft size={15} aria-hidden="true" /> Cancel</Link>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
