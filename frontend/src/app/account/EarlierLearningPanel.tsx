"use client";

import { ArchiveRestore, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type GuestProgressSummary } from "@/lib/api";
import { clearEarlierBrowserLearningState, useAuth } from "@/lib/auth";
import styles from "./account.module.css";

function readableActivityDate(value: string | null): string | null {
  if (!value) return null;
  const instant = new Date(value);
  if (Number.isNaN(instant.getTime())) return null;
  return new Intl.DateTimeFormat("en-US", { dateStyle: "medium" }).format(instant);
}

function clearEarlierBrowserMarkers() {
  clearEarlierBrowserLearningState();
}

export function EarlierLearningPanel() {
  const { user } = useAuth();
  const [summary, setSummary] = useState<GuestProgressSummary | null>(null);
  const [busy, setBusy] = useState<"attach" | "discard" | null>(null);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    if (!user || (user.accountStatus && user.accountStatus !== "verified")) return () => { active = false; };
    api.guestProgress()
      .then((result) => {
        if (active && result.hasProgress && result.claimable) setSummary(result);
      })
      .catch(() => {
        // This optional migration stays invisible unless a claimable record is positively identified.
      });
    return () => { active = false; };
  }, [user]);

  if (!summary && !outcome) return null;

  async function attach() {
    if (busy) return;
    setBusy("attach");
    setError(null);
    try {
      await api.claimLegacyProgress();
      clearEarlierBrowserMarkers();
      setSummary(null);
      setOutcome("Earlier learning was attached to this account.");
    } catch {
      setError("That earlier learning could not be attached. Refresh the page and try again.");
    } finally {
      setBusy(null);
    }
  }

  async function discard() {
    if (busy) return;
    setBusy("discard");
    setError(null);
    try {
      await api.deleteGuestProgress();
      clearEarlierBrowserMarkers();
      setSummary(null);
      setOutcome("Earlier browser learning was discarded.");
    } catch {
      setError("That earlier learning could not be discarded. Refresh the page and try again.");
    } finally {
      setBusy(null);
    }
  }

  if (outcome) {
    return <p className={styles.migrationOutcome} role="status">{outcome}</p>;
  }

  const lastActivity = readableActivityDate(summary?.lastActivityAt ?? null);
  return (
    <section className={`${styles.section} ${styles.migrationSection}`} aria-labelledby="earlier-learning-heading">
      <div className={styles.sectionIntro}>
        <span className={styles.icon}><ArchiveRestore aria-hidden="true" /></span>
        <div>
          <h2 id="earlier-learning-heading">Earlier browser learning found</h2>
          <p>An earlier beta version saved practice in this browser. Choose whether to add it to this verified account.</p>
        </div>
      </div>
      <div className={styles.migrationPanel}>
        <p><strong>{summary?.totalActivities ?? 0}</strong> saved learning {(summary?.totalActivities ?? 0) === 1 ? "activity" : "activities"}{lastActivity ? `, last used ${lastActivity}` : ""}.</p>
        {error ? <p className={styles.error} role="alert">{error}</p> : null}
        {confirmDiscard ? (
          <div className={styles.migrationConfirm} role="group" aria-label="Confirm discard earlier browser learning">
            <p>Discard this separate browser record permanently?</p>
            <div className={styles.actions}>
              <button className={styles.textButton} type="button" onClick={() => setConfirmDiscard(false)} disabled={Boolean(busy)}>Keep it</button>
              <button className={styles.dangerButton} type="button" onClick={() => void discard()} disabled={Boolean(busy)}>
                <Trash2 aria-hidden="true" /> {busy === "discard" ? "Discarding…" : "Discard record"}
              </button>
            </div>
          </div>
        ) : (
          <div className={styles.actions}>
            <button className={styles.primaryButton} type="button" onClick={() => void attach()} disabled={Boolean(busy)}>
              <ArchiveRestore aria-hidden="true" /> {busy === "attach" ? "Attaching…" : "Attach to my account"}
            </button>
            <button className={styles.textButton} type="button" onClick={() => setConfirmDiscard(true)} disabled={Boolean(busy)}>Discard…</button>
          </div>
        )}
      </div>
    </section>
  );
}
