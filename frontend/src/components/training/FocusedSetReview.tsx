"use client";

import {
  ArrowLeft,
  ArrowRight,
  Brain,
  CalendarDays,
  CheckCircle2,
  ClipboardCheck,
  History,
  RefreshCw,
  Sparkles,
  Target,
  TrendingUp,
} from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import type { TrainingCampaignSummary } from "@/lib/types";
import styles from "./FocusedSetReview.module.css";

type FocusedSetReviewProps = {
  conceptId: string;
  conceptLabel: string;
  skillLabel: string;
  total: number;
  summary: TrainingCampaignSummary | null;
  masteryLabel: string;
  readyForRapid: boolean;
  rapidHref?: string;
  rapidTitle?: string;
  rapidDetail?: string;
  sessionRef: string | null;
  sessionLookupPending: boolean;
  loading: boolean;
  error?: string | null;
  tutor: ReactNode;
  onRepeat: () => void;
  onRepeatShort: () => void;
  onPracticeRecommendation?: () => void;
  clinicalHref?: string;
  returnTo?: string;
  returnLabel?: string;
};

function resultLabel(correct: boolean, classificationCorrect: boolean) {
  if (correct && classificationCorrect) return "Both targets met";
  if (correct) return "Skill met · pattern review";
  if (classificationCorrect) return "Pattern met · skill review";
  return "Review both targets";
}

export function FocusedSetReview({
  conceptId,
  conceptLabel,
  skillLabel,
  total,
  summary,
  masteryLabel,
  readyForRapid,
  rapidHref,
  rapidTitle = "Test mixed recognition",
  rapidDetail = "Move into Rapid Practice",
  sessionRef,
  sessionLookupPending,
  loading,
  error,
  tutor,
  onRepeat,
  onRepeatShort,
  onPracticeRecommendation,
  clinicalHref,
  returnTo,
  returnLabel,
}: FocusedSetReviewProps) {
  const attempted = summary?.attempted ?? 0;
  const skillMet = summary?.correct ?? 0;
  const patternMet = summary?.classificationCorrect ?? 0;
  const bothMet = summary?.fullTaskCorrect ?? 0;
  const recent = summary?.recent ?? [];
  const needsSkill = skillMet < patternMet;
  const needsPattern = patternMet < skillMet;
  const impact = needsSkill
    ? `You are spotting ${conceptLabel} more reliably than you are completing the ${skillLabel.toLowerCase()} task. Separating those two results prevents a correct label from hiding an evidence gap.`
    : needsPattern
      ? `Your ${skillLabel.toLowerCase()} reasoning is stronger than your first pattern decision. A shorter recognition set can make the initial read more dependable.`
      : skillMet === attempted && attempted > 0
        ? `Your pattern decision and selected skill moved together across this set. The next useful test is whether the same skill transfers when the topic is no longer named.`
        : `The misses affected both the initial pattern decision and the selected skill. Reviewing the exact ECGs below will show where the reasoning separated from the waveform.`;
  const nextStep = readyForRapid
    ? "Move to mixed Rapid Practice so the target is no longer announced in advance."
    : needsSkill
      ? `Repeat a short ${skillLabel.toLowerCase()} set, then review one missed ECG without a hint.`
      : needsPattern
        ? `Use a 5-ECG recognition set for ${conceptLabel}, then return to this skill.`
        : `Review the missed ECGs, then repeat a 5-ECG set while the discriminators are fresh.`;

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <p>Focused practice complete</p>
          <h1>Turn this set into your next read.</h1>
          <span>{conceptLabel} · {skillLabel}</span>
        </div>
        <div className={styles.headerActions}>
          {returnTo ? <Link className="button subtle" href={returnTo}><ArrowLeft size={16} aria-hidden="true" /> {returnLabel ?? "Return"}</Link> : null}
          <button className="button primary" type="button" onClick={onRepeat} disabled={loading}>
            <RefreshCw size={16} aria-hidden="true" /> Start another set
          </button>
        </div>
      </header>

      {error ? <div className={`warning ${styles.actionError}`} role="alert">{error}</div> : null}

      <section className={styles.metrics} aria-label="Focused practice results">
        <div className={styles.primaryMetric}>
          <span><Target size={22} aria-hidden="true" /></span>
          <div><strong>{skillMet}/{attempted || total}</strong><small>{skillLabel} tasks met</small></div>
        </div>
        <div><span>Pattern decisions</span><strong>{patternMet}/{attempted || total}</strong><small>scored separately</small></div>
        <div><span>Both targets</span><strong>{bothMet}/{attempted || total}</strong><small>pattern + selected skill</small></div>
        <div><span>Progress</span><strong>{masteryLabel}</strong><small>{summary?.independentReceipts ?? 0} mixed check{summary?.independentReceipts === 1 ? "" : "s"} recorded</small></div>
      </section>

      <div className={styles.layout}>
        <section className={styles.reviewPanel} aria-labelledby="focused-review-heading">
          <div className={styles.sectionHeading}>
            <div>
              <p>Review your ECGs</p>
              <h2 id="focused-review-heading">See the exact questions and traces again</h2>
            </div>
            {sessionRef ? (
              <Link className="button subtle small" href={`/home/review/${encodeURIComponent(sessionRef)}`}>
                <History size={15} aria-hidden="true" /> Open full set review
              </Link>
            ) : sessionLookupPending ? (
              <span className={styles.reviewLoading}>Preparing ECG review…</span>
            ) : (
              <Link className="button subtle small" href="/home?panel=activity">
                <History size={15} aria-hidden="true" /> Find in learning history
              </Link>
            )}
          </div>

          {attempted > recent.length ? (
            <p className={styles.recentNotice}>Showing the most recent {recent.length} of {attempted} ECGs. Open the full set review for the complete history.</p>
          ) : null}

          <ol className={styles.attemptList}>
            {recent.map((attempt) => {
              const label = resultLabel(attempt.correct, attempt.classificationCorrect);
              const met = attempt.correct && attempt.classificationCorrect;
              const attemptHref = sessionRef
                ? `/home/review/${encodeURIComponent(sessionRef)}/attempt/${attempt.position + 1}`
                : null;
              return (
                <li key={attempt.position} data-status={met ? "met" : "review"}>
                  <span className={styles.attemptNumber}>{attempt.position + 1}</span>
                  <span className={styles.attemptStatus}>
                    {met ? <CheckCircle2 size={17} aria-hidden="true" /> : <ClipboardCheck size={17} aria-hidden="true" />}
                  </span>
                  <div>
                    <strong>ECG {attempt.position + 1}</strong>
                    <small>{label}</small>
                  </div>
                  <div className={styles.attemptMeta}>
                    <span>{attempt.hintsUsed ? "Hint used" : "Independent read"}</span>
                    <span>{attempt.evidenceLevel === "independent_transfer" ? "Counted toward mastery" : "Skill-building practice"}</span>
                  </div>
                  {attemptHref ? (
                    <Link href={attemptHref}>Review ECG &amp; answer <ArrowRight size={14} aria-hidden="true" /></Link>
                  ) : sessionLookupPending ? (
                    <span className={styles.pendingLink}>Review link preparing</span>
                  ) : (
                    <Link href="/home?panel=activity">Find in history <ArrowRight size={14} aria-hidden="true" /></Link>
                  )}
                </li>
              );
            })}
          </ol>
        </section>

        <aside className={styles.sideColumn}>
          <section className={styles.coachCard} aria-labelledby="focused-coach-heading">
            <div className={styles.coachHeading}>
              <span><Brain size={19} aria-hidden="true" /></span>
              <div><p>Luna coach</p><h2 id="focused-coach-heading">Feedback grounded in this set</h2></div>
            </div>
            <dl className={styles.sbiGrid}>
              <div><dt>Situation</dt><dd>You completed {attempted} focused ECGs on {conceptLabel}, practicing {skillLabel.toLowerCase()}.</dd></div>
              <div><dt>What you did</dt><dd>You met {skillMet} selected-skill tasks and {patternMet} first pattern decisions.</dd></div>
              <div><dt>Impact</dt><dd>{impact}</dd></div>
              <div><dt>Next step</dt><dd>{nextStep}</dd></div>
            </dl>
            <div className={styles.tutorWrap}>{tutor}</div>
          </section>

          <section className={styles.nextCard} aria-labelledby="focused-next-heading">
            <div className={styles.nextHeading}><Sparkles size={18} aria-hidden="true" /><h2 id="focused-next-heading">Keep this moving</h2></div>
            <div className={styles.nextGrid}>
              {readyForRapid ? (
                <Link href={rapidHref ?? `/rapid?focus=${encodeURIComponent(conceptId)}&receiptConcept=${encodeURIComponent(conceptId)}&subskill=recognize`}>
                  <TrendingUp size={18} aria-hidden="true" /><span><strong>{rapidTitle}</strong><small>{rapidDetail}</small></span>
                </Link>
              ) : (
                <button type="button" onClick={onRepeatShort} disabled={loading}>
                  <Target size={18} aria-hidden="true" /><span><strong>Repeat a short set</strong><small>Consolidate this skill</small></span>
                </button>
              )}
              {onPracticeRecommendation ? (
                <button type="button" onClick={onPracticeRecommendation} disabled={loading}>
                  <Sparkles size={18} aria-hidden="true" /><span><strong>Practice a recommended topic</strong><small>Keep the same reading skill</small></span>
                </button>
              ) : null}
              <Link href="/home?panel=calendar"><CalendarDays size={18} aria-hidden="true" /><span><strong>Schedule a revisit</strong><small>Put retention on your calendar</small></span></Link>
              <Link href="/home?panel=competencies"><TrendingUp size={18} aria-hidden="true" /><span><strong>View progress</strong><small>See objective mastery</small></span></Link>
              {clinicalHref ? <Link href={clinicalHref}><ClipboardCheck size={18} aria-hidden="true" /><span><strong>Use it in a clinical case</strong><small>Apply this pattern in context</small></span></Link> : null}
              <Link href="/home?panel=activity"><History size={18} aria-hidden="true" /><span><strong>Open learning history</strong><small>Return to any completed set</small></span></Link>
            </div>
          </section>
        </aside>
      </div>
    </main>
  );
}
