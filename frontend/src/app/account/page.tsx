"use client";

import { KeyRound, LogOut, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function AccountPage() {
  const { user, logoutAll } = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!user) {
    return <div className="page"><section className="panel pad"><h1>Account security</h1><p className="muted">Sign in to manage a private student account.</p><Link className="button primary" href="/login?next=/account">Sign in</Link></section></div>;
  }

  async function changePassword(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    if (newPassword.length < 10) {
      setError("The new password must be at least 10 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("The new passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      await api.changePassword({ currentPassword, newPassword });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setMessage("Password changed. Other signed-in devices were revoked.");
    } catch (caught) {
      const detail = caught instanceof Error ? caught.message : "Password could not be changed.";
      setError(detail.includes("invalid_current_password") ? "The current password is incorrect." : detail);
    } finally {
      setBusy(false);
    }
  }

  async function revokeEverySession() {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await logoutAll();
    } catch {
      setError("Session revocation could not be confirmed. You remain signed in; try again.");
      setBusy(false);
    }
  }

  return (
    <div className="page auth-settings-page">
      <header className="page-header">
        <div><p className="eyebrow">Private student record</p><h1>Account security</h1><p className="muted">Signed in as {user.username}. Password changes rotate this device and revoke every other session.</p></div>
      </header>
      {error ? <div className="warning" role="alert">{error}</div> : null}
      {message ? <div className="selection-note" role="status">{message}</div> : null}
      <div className="grid two">
        <section className="panel pad">
          <h2><KeyRound size={18} aria-hidden="true" /> Change password</h2>
          <form className="form-grid" onSubmit={changePassword}>
            <div className="field full"><label htmlFor="current-password">Current password</label><input id="current-password" type="password" autoComplete="current-password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required /></div>
            <div className="field full"><label htmlFor="new-password">New password</label><input id="new-password" type="password" autoComplete="new-password" minLength={10} value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required /></div>
            <div className="field full"><label htmlFor="confirm-password">Confirm new password</label><input id="confirm-password" type="password" autoComplete="new-password" minLength={10} value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} required /></div>
            <button className="button primary" type="submit" disabled={busy}>Change password</button>
          </form>
        </section>
        <aside className="grid">
          <section className="panel pad">
            <h2><ShieldCheck size={18} aria-hidden="true" /> Session control</h2>
            <p className="muted">Use this if a shared or lost device may still be signed in. Every session, including this one, will be revoked.</p>
            <button className="button warn" type="button" onClick={() => void revokeEverySession()} disabled={busy}><LogOut size={16} aria-hidden="true" /> Sign out every device</button>
          </section>
          <section className="panel pad">
            <h2>Account recovery</h2>
            <p className="muted">Forgotten-password recovery is not enabled because this deployment has no verified email or institutional SSO channel. Contact your program administrator; never create a second account to replace a tracked record.</p>
          </section>
        </aside>
      </div>
    </div>
  );
}
