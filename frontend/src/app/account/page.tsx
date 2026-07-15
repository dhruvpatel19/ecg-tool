"use client";

import { Download, KeyRound, Laptop, LogOut, RefreshCw, ShieldCheck, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, type AccountSession } from "@/lib/api";
import { clearAuthenticatedBrowserState, useAuth } from "@/lib/auth";
import { EarlierLearningPanel } from "./EarlierLearningPanel";
import { EmailSecurityPanel } from "./EmailSecurityPanel";
import styles from "./account.module.css";

type BusyAction = "password" | "other-sessions" | "all-sessions" | "export" | "delete" | null;

const sessionTimeFormatter = new Intl.DateTimeFormat("en-US", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "UTC",
});

function formatSessionTime(value: string): string {
  const instant = new Date(value);
  return Number.isNaN(instant.getTime()) ? "time unavailable" : `${sessionTimeFormatter.format(instant)} UTC`;
}

function readableError(caught: unknown, fallback: string): string {
  const detail = caught instanceof Error ? caught.message : fallback;
  if (detail.includes("invalid_current_password")) return "The current password is incorrect.";
  if (detail.includes("confirmation_mismatch")) return "The confirmation must match your username.";
  if (detail.includes("password_too_common")) return "Choose a less common password that is not your username.";
  if (detail.includes("password_unchanged")) return "The new password must be different from your current password.";
  if (detail.includes("reauth_throttled")) return "Too many password attempts. Wait 15 minutes, then try again.";
  return fallback;
}

export default function AccountPage() {
  const { user, logoutAll } = useAuth();
  const userId = user?.userId ?? null;
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busyAction, setBusyAction] = useState<BusyAction>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showDelete, setShowDelete] = useState(false);
  const [deletePassword, setDeletePassword] = useState("");
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [sessions, setSessions] = useState<AccountSession[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [revokingSessionId, setRevokingSessionId] = useState<string | null>(null);
  const [showLogoutAllConfirm, setShowLogoutAllConfirm] = useState(false);
  const [showExport, setShowExport] = useState(false);
  const [exportPassword, setExportPassword] = useState("");
  const [exportError, setExportError] = useState<string | null>(null);
  const exportPasswordRef = useRef<HTMLInputElement>(null);
  const currentPasswordRef = useRef<HTMLInputElement>(null);
  const newPasswordRef = useRef<HTMLInputElement>(null);
  const confirmPasswordRef = useRef<HTMLInputElement>(null);
  const deleteConfirmationRef = useRef<HTMLInputElement>(null);
  const deletePasswordRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let active = true;
    if (!userId) {
      setSessions([]);
      setSessionsLoading(false);
      setSessionError(null);
      return () => { active = false; };
    }
    setSessionsLoading(true);
    setSessionError(null);
    api.sessions()
      .then((result) => {
        if (active) setSessions(result.sessions);
      })
      .catch(() => {
        if (active) {
          setSessions([]);
          setSessionError("Signed-in sessions could not be loaded.");
        }
      })
      .finally(() => {
        if (active) setSessionsLoading(false);
      });
    return () => { active = false; };
  }, [userId]);

  if (!user) {
    return (
      <div className={styles.signedOut} role="status" aria-live="polite">
        <ShieldCheck aria-hidden="true" />
        <h1>Opening account settings…</h1>
      </div>
    );
  }

  const username = user.username;
  const displayName = user.displayName;
  const busy = busyAction !== null || revokingSessionId !== null;
  const otherSessionCount = sessions.filter((session) => !session.current).length;

  function begin(action: Exclude<BusyAction, null>) {
    setBusyAction(action);
    setError(null);
    setMessage(null);
  }

  async function refreshSessions() {
    setSessionsLoading(true);
    setSessionError(null);
    try {
      const result = await api.sessions();
      setSessions(result.sessions);
    } catch {
      setSessionError("Signed-in sessions could not be loaded.");
    } finally {
      setSessionsLoading(false);
    }
  }

  async function changePassword(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    if (newPassword.length < 10) {
      setError("The new password must be at least 10 characters.");
      newPasswordRef.current?.focus();
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("The new passwords do not match.");
      confirmPasswordRef.current?.focus();
      return;
    }
    begin("password");
    try {
      await api.changePassword({ currentPassword, newPassword });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setMessage("Password changed. Other signed-in sessions were revoked.");
      await refreshSessions();
    } catch (caught) {
      setError(readableError(caught, "Password could not be changed. Please try again."));
      const detail = caught instanceof Error ? caught.message : "";
      window.requestAnimationFrame(() => {
        if (detail.includes("invalid_current_password")) currentPasswordRef.current?.focus();
        else newPasswordRef.current?.focus();
      });
    } finally {
      setBusyAction(null);
    }
  }

  async function revokeOtherSessions() {
    begin("other-sessions");
    try {
      const result = await api.logoutOthers();
      setMessage(
        result.revokedOtherSessions
          ? `${result.revokedOtherSessions} other ${result.revokedOtherSessions === 1 ? "session was" : "sessions were"} signed out.`
          : "No other signed-in sessions were found.",
      );
      await refreshSessions();
    } catch {
      setError("Other sessions could not be revoked. Please try again.");
    } finally {
      setBusyAction(null);
    }
  }

  async function revokeSession(session: AccountSession) {
    if (session.current) return;
    setRevokingSessionId(session.sessionId);
    setError(null);
    setMessage(null);
    try {
      await api.revokeSession(session.sessionId);
      setMessage("Other session signed out.");
      await refreshSessions();
    } catch {
      setError("That session could not be signed out. The list was refreshed; try again.");
      await refreshSessions();
    } finally {
      setRevokingSessionId(null);
    }
  }

  async function revokeEverySession() {
    begin("all-sessions");
    try {
      await logoutAll();
    } catch {
      setError("Session revocation could not be confirmed. You remain signed in; try again.");
      setBusyAction(null);
    }
  }

  async function downloadProgress(event: React.FormEvent) {
    event.preventDefault();
    if (!exportPassword) {
      setExportError("Enter your current password to continue.");
      exportPasswordRef.current?.focus();
      return;
    }
    begin("export");
    setExportError(null);
    try {
      await api.authorizeExport({ currentPassword: exportPassword });
      const exported = await api.exportProgress();
      const blob = new Blob([JSON.stringify(exported, null, 2)], { type: "application/json" });
      const href = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = href;
      anchor.download = `ecg-progress-${username}.json`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(href);
      setExportPassword("");
      setShowExport(false);
      setMessage("Your progress export is ready.");
    } catch (caught) {
      const raw = caught instanceof Error ? caught.message : "";
      const retryMessage = raw.includes("invalid_current_password")
        ? "That password is incorrect. No export was created. Try again."
        : raw.includes("reauth_throttled")
          ? "Too many password attempts. Wait 15 minutes, then try again."
          : raw.includes("export_authorization")
            ? "The one-time export approval expired or was already used. Confirm your password and try again."
            : "Your progress export could not be prepared. Confirm your password and try again.";
      setExportPassword("");
      setExportError(retryMessage);
      window.requestAnimationFrame(() => exportPasswordRef.current?.focus());
    } finally {
      setBusyAction(null);
    }
  }

  async function deleteAccount(event: React.FormEvent) {
    event.preventDefault();
    if (deleteConfirmation.trim() !== username) {
      setError("Type your username exactly to confirm deletion.");
      deleteConfirmationRef.current?.focus();
      return;
    }
    begin("delete");
    try {
      await api.deleteAccount({
        currentPassword: deletePassword,
        confirmation: deleteConfirmation,
      });
      const localCleanupComplete = clearAuthenticatedBrowserState(userId ?? "");
      window.location.replace(
        localCleanupComplete
          ? "/login?accountDeleted=1"
          : "/login?accountDeleted=1&localCleanup=failed",
      );
    } catch (caught) {
      setError(readableError(caught, "Account deletion could not be completed. Please try again."));
      const detail = caught instanceof Error ? caught.message : "";
      window.requestAnimationFrame(() => {
        if (detail.includes("confirmation_mismatch")) deleteConfirmationRef.current?.focus();
        else deletePasswordRef.current?.focus();
      });
      setBusyAction(null);
    }
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Your private learning record</p>
          <h1>Account and privacy</h1>
          <p>{displayName} <span aria-hidden="true">·</span> @{username}</p>
        </div>
        <ShieldCheck aria-hidden="true" />
      </header>

      <div className={styles.feedback} aria-live="polite">
        {error ? <p className={styles.error} role="alert">{error}</p> : null}
        {message ? <p className={styles.success} role="status">{message}</p> : null}
      </div>

      <EmailSecurityPanel />
      <EarlierLearningPanel />

      <section className={styles.section} aria-labelledby="password-heading">
        <div className={styles.sectionIntro}>
          <span className={styles.icon}><KeyRound aria-hidden="true" /></span>
          <div><h2 id="password-heading">Change password</h2><p>This signs out every other session and keeps this one active.</p></div>
        </div>
        <form className={styles.form} onSubmit={changePassword}>
          <label htmlFor="current-password">Current password</label>
          <input ref={currentPasswordRef} id="current-password" type="password" autoComplete="current-password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required />
          <label htmlFor="new-password">New password</label>
          <input ref={newPasswordRef} id="new-password" type="password" autoComplete="new-password" minLength={10} maxLength={256} value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required aria-describedby="password-requirement" />
          <p id="password-requirement" className={styles.hint}>10–256 characters. Avoid your username, repeated characters, and common passwords.</p>
          <label htmlFor="confirm-password">Confirm new password</label>
          <input ref={confirmPasswordRef} id="confirm-password" type="password" autoComplete="new-password" minLength={10} maxLength={256} value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} required />
          <div className={styles.actions}>
            <button className={styles.primaryButton} type="submit" disabled={busy}>
              {busyAction === "password" ? "Changing…" : "Change password"}
            </button>
          </div>
        </form>
      </section>

      <section className={styles.section} aria-labelledby="sessions-heading">
        <div className={styles.sectionIntro}>
          <span className={styles.icon}><Laptop aria-hidden="true" /></span>
          <div><h2 id="sessions-heading">Signed-in sessions</h2><p>We do not collect device names or locations. Review individual sign-ins and revoke ones you no longer need.</p></div>
        </div>
        <div className={styles.sessionPanel}>
          <div className={styles.sessionSummary} aria-live="polite">
            <strong>{sessionsLoading ? "Loading sessions…" : `${sessions.length} active ${sessions.length === 1 ? "session" : "sessions"}`}</strong>
            {!sessionsLoading && !sessionError ? <span>{otherSessionCount} other</span> : null}
          </div>

          {sessionError ? (
            <div className={styles.sessionError} role="alert">
              <span>{sessionError}</span>
              <button className={styles.textButton} type="button" onClick={() => void refreshSessions()} disabled={busy || sessionsLoading}>
                <RefreshCw aria-hidden="true" /> Retry
              </button>
            </div>
          ) : sessionsLoading && sessions.length === 0 ? (
            <p className={styles.sessionLoading} role="status">Loading signed-in sessions…</p>
          ) : (
            <ul className={styles.sessionList} aria-label="Active sessions">
              {sessions.map((session) => (
                <li className={styles.sessionRow} key={session.sessionId}>
                  <Laptop aria-hidden="true" />
                  <span className={styles.sessionMeta}>
                    <strong>{session.current ? "This session" : "Other session"}</strong>
                    <small>Started {formatSessionTime(session.createdAt)}</small>
                    <small>Expires {formatSessionTime(session.expiresAt)}</small>
                  </span>
                  {session.current ? (
                    <span className={styles.currentBadge}>Current</span>
                  ) : (
                    <button
                      className={styles.sessionAction}
                      type="button"
                      aria-label={`Sign out other session started ${formatSessionTime(session.createdAt)}`}
                      onClick={() => void revokeSession(session)}
                      disabled={busy}
                    >
                      {revokingSessionId === session.sessionId ? "Signing out…" : "Sign out"}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}

          <div className={styles.actions}>
            <button
              className={styles.secondaryButton}
              type="button"
              onClick={() => void revokeOtherSessions()}
              disabled={busy || sessionsLoading || otherSessionCount === 0}
            >
              <ShieldCheck aria-hidden="true" /> {busyAction === "other-sessions" ? "Signing out…" : "Sign out all other sessions"}
            </button>
            {!showLogoutAllConfirm ? (
              <button className={styles.textButton} type="button" onClick={() => { setShowLogoutAllConfirm(true); setError(null); setMessage(null); }} disabled={busy}>
                <LogOut aria-hidden="true" /> Sign out everywhere…
              </button>
            ) : null}
          </div>

          {showLogoutAllConfirm ? (
            <div className={styles.logoutConfirm} role="group" aria-label="Confirm sign out everywhere">
              <strong>Sign out every session?</strong>
              <p>This includes this session. You will need to sign in again here.</p>
              <div>
                <button className={styles.textButton} type="button" onClick={() => setShowLogoutAllConfirm(false)} disabled={busy}>Cancel</button>
                <button className={styles.confirmLogoutButton} type="button" onClick={() => void revokeEverySession()} disabled={busy}>
                  <LogOut aria-hidden="true" /> {busyAction === "all-sessions" ? "Signing out…" : "Confirm sign out everywhere"}
                </button>
              </div>
            </div>
          ) : null}
        </div>
      </section>

      <section className={styles.section} aria-labelledby="data-heading">
        <div className={styles.sectionIntro}>
          <span className={styles.icon}><Download aria-hidden="true" /></span>
          <div><h2 id="data-heading">Your learning data</h2><p>Download your progress, answers, skill estimates, practice history, and tutor conversations as JSON. Passwords and sign-in secrets are never included.</p></div>
        </div>
        {!showExport ? (
          <div className={styles.actions}>
            <button className={styles.secondaryButton} type="button" onClick={() => { setShowExport(true); setExportError(null); setError(null); setMessage(null); }} disabled={busy}>
              <Download aria-hidden="true" /> Download progress…
            </button>
          </div>
        ) : (
          <form className={styles.exportForm} onSubmit={downloadProgress} aria-labelledby="export-confirm-heading">
            <div className={styles.exportHeading}>
              <strong id="export-confirm-heading">Confirm password to export</strong>
              <button className={styles.closeButton} type="button" aria-label="Cancel progress export" onClick={() => { setShowExport(false); setExportPassword(""); setExportError(null); }} disabled={busy}>
                <X aria-hidden="true" />
              </button>
            </div>
            <p id="export-confirm-note">This creates a one-time approval for this signed-in session. It expires after five minutes and is used immediately.</p>
            {exportError ? <p className={styles.exportError} id="export-confirm-error" role="alert">{exportError}</p> : null}
            <label htmlFor="export-password">Current password</label>
            <input
              ref={exportPasswordRef}
              id="export-password"
              type="password"
              autoComplete="current-password"
              value={exportPassword}
              onChange={(event) => { setExportPassword(event.target.value); setExportError(null); }}
              aria-describedby={exportError ? "export-confirm-note export-confirm-error" : "export-confirm-note"}
              autoFocus
              required
            />
            <button className={styles.primaryButton} type="submit" disabled={busy}>
              <Download aria-hidden="true" /> {busyAction === "export" ? "Confirming and preparing…" : "Confirm and download"}
            </button>
          </form>
        )}
      </section>

      <aside className={styles.recoveryNote}>
        <strong>Account recovery</strong>
        <p>Your verified email can restore access if you forget your password. <Link href="/forgot-password">Request a password-reset link</Link>.</p>
      </aside>

      <section className={styles.danger} aria-labelledby="delete-heading">
        <div className={styles.sectionIntro}>
          <span className={styles.dangerIcon}><Trash2 aria-hidden="true" /></span>
          <div><h2 id="delete-heading">Delete account</h2><p>Permanently removes your account, progress, mode sessions, answers, and tutor history.</p></div>
        </div>
        {!showDelete ? (
          <button className={styles.dangerButton} type="button" onClick={() => { setShowDelete(true); setError(null); setMessage(null); }} disabled={busy}>
            Delete account…
          </button>
        ) : (
          <form className={styles.deleteForm} onSubmit={deleteAccount}>
            <div className={styles.deleteHeading}>
              <strong>This cannot be undone.</strong>
              <button className={styles.closeButton} type="button" aria-label="Cancel account deletion" onClick={() => { setShowDelete(false); setDeletePassword(""); setDeleteConfirmation(""); }} disabled={busy}>
                <X aria-hidden="true" />
              </button>
            </div>
            <label htmlFor="delete-confirmation">Type <strong>{username}</strong> to confirm</label>
            <input ref={deleteConfirmationRef} id="delete-confirmation" value={deleteConfirmation} onChange={(event) => setDeleteConfirmation(event.target.value)} autoComplete="off" required />
            <label htmlFor="delete-password">Current password</label>
            <input ref={deletePasswordRef} id="delete-password" type="password" autoComplete="current-password" value={deletePassword} onChange={(event) => setDeletePassword(event.target.value)} required />
            <button className={styles.confirmDeleteButton} type="submit" disabled={busy || deleteConfirmation.trim() !== username}>
              <Trash2 aria-hidden="true" /> {busyAction === "delete" ? "Deleting…" : "Permanently delete my account"}
            </button>
          </form>
        )}
      </section>
    </div>
  );
}
