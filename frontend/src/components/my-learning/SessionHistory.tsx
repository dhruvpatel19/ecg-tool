"use client";

import { ArrowRight, Bookmark, BrainCircuit, History, Stethoscope, TimerReset } from "lucide-react";
import Link from "next/link";
import type { LearningSessionSummary } from "@/lib/api";
import { conceptLabel } from "@/lib/coordinates";
import { competencySkillLabel as subskillLabel } from "@/lib/learning/skillLabels";
import styles from "./SessionHistory.module.css";

type SessionHistoryProps = {
  items: LearningSessionSummary[];
  loading: boolean;
  failed?: boolean;
  compact?: boolean;
  emptyState?: "sessions" | "saved";
  emptyAction?: { href: string; label: string };
};

const modePresentation = {
  training: { label: "Focused practice", Icon: BrainCircuit },
  rapid: { label: "Rapid practice", Icon: TimerReset },
  clinical: { label: "Clinical cases", Icon: Stethoscope },
} as const;

function occurredLabel(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Completion time unavailable";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: date.getFullYear() === new Date().getFullYear() ? undefined : "numeric",
  }).format(date);
}

export function sessionOutcomeLabel(item: LearningSessionSummary) {
  if (item.score !== null) return `${Math.round(item.score * 100)}%`;
  if (item.correctCount !== null && item.attempted > 0) return `${item.correctCount}/${item.attempted}`;
  return "Not scored";
}

function sessionOutcomeMetricLabel(item: LearningSessionSummary) {
  if (item.score !== null) return item.mode === "clinical" ? "formative score" : "score";
  if (item.correctCount === null) return "not scored";
  return item.mode === "training" ? "skill tasks met" : "correct";
}

export function SessionHistory({ items, loading, failed = false, compact = false, emptyState = "sessions", emptyAction }: SessionHistoryProps) {
  if (loading) {
    return <div className={styles.loading} role="status">Loading your sessions…</div>;
  }

  if (failed) {
    return (
      <div className={styles.empty} data-state="error" role="status">
        <History size={20} aria-hidden="true" />
        <span><strong>Session history is temporarily unavailable.</strong><small>Your saved work is still safe. Try again in a moment.</small></span>
      </div>
    );
  }

  if (!items.length) {
    const EmptyIcon = emptyState === "saved" ? Bookmark : History;
    return (
      <div className={styles.empty} data-state={emptyState}>
        <EmptyIcon size={20} aria-hidden="true" />
        {emptyState === "saved" ? (
          <span><strong>No saved items yet.</strong><small>Save a question or ECG while reviewing a session, then find it here.</small></span>
        ) : (
          <span><strong>No activity yet.</strong><small>Complete a practice session and it will appear here.</small></span>
        )}
        {emptyState === "sessions" && emptyAction ? (
          <Link className={styles.emptyAction} href={emptyAction.href}>{emptyAction.label} <ArrowRight size={14} aria-hidden="true" /></Link>
        ) : null}
      </div>
    );
  }

  return (
    <div className={styles.list} data-compact={compact || undefined} data-testid="session-history">
      {items.map((item) => {
        const presentation = modePresentation[item.mode];
        const Icon = presentation.Icon;
        const focus = item.focusCompetencies[0];
        const isPartialPractice = item.status === "abandoned" && (item.mode === "rapid" || item.mode === "training");
        const sessionLabel = isPartialPractice
          ? item.mode === "rapid" ? "Partial Rapid round" : "Partial Focused set"
          : presentation.label;
        return (
          <article className={styles.row} key={item.sessionRef}>
            <span className={styles.icon} data-mode={item.mode} aria-hidden="true"><Icon size={17} /></span>
            <div className={styles.copy}>
              <strong>{sessionLabel}</strong>
              <span>{occurredLabel(item.completedAt)} · {item.attempted} of {item.total} {isPartialPractice ? "submitted · ended early" : "completed"}</span>
              {focus ? <small>{conceptLabel(focus.objectiveId)} · {subskillLabel(focus.subskill)}</small> : <small>Mixed skills</small>}
              {item.flaggedCount > 0 ? <span className={styles.saved}><Bookmark size={12} aria-hidden="true" /> {item.flaggedCount} saved for review</span> : null}
            </div>
            <div className={styles.outcome}>
              <strong>{sessionOutcomeLabel(item)}</strong>
              <span>{sessionOutcomeMetricLabel(item)}</span>
            </div>
            {item.reviewAvailable ? (
              <Link href={`/home/review/${encodeURIComponent(item.sessionRef)}`} aria-label={`Review ${sessionLabel} from ${occurredLabel(item.completedAt)}`}>
                <span>{compact ? "Review" : isPartialPractice ? "Review partial practice" : "Review session"}</span><ArrowRight size={15} aria-hidden="true" />
              </Link>
            ) : (
              <span className={styles.unavailable}>Review unavailable</span>
            )}
          </article>
        );
      })}
    </div>
  );
}
