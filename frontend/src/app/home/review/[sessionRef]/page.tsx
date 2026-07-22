"use client";

import {
  ArrowLeft,
  ArrowRight,
  BarChart3,
  Bookmark,
  BookmarkCheck,
  BrainCircuit,
  CheckCircle2,
  CircleAlert,
  Clock3,
  Lightbulb,
  RefreshCw,
  ScanLine,
  ShieldCheck,
  Stethoscope,
  Target,
  TimerReset,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  api,
  type CompetencyObjective,
  type LearningSessionAttempt,
  type LearningSessionReview,
} from "@/lib/api";
import { conceptLabel } from "@/lib/coordinates";
import { competencyPracticeHref } from "@/lib/competencyRoutes";
import { sessionOutcomeLabel } from "@/components/my-learning/SessionHistory";
import styles from "./review.module.css";

const modePresentation = {
  training: { label: "Focused practice", Icon: BrainCircuit },
  rapid: { label: "Rapid practice", Icon: TimerReset },
  clinical: { label: "Clinical cases", Icon: Stethoscope },
} as const;

function dateLabel(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Completion time unavailable";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function subskillLabel(value: string) {
  return value.replaceAll("_", " ");
}

function scoreLabel(value: number | null) {
  return value === null ? "Not scored" : `${Math.round(value * 100)}%`;
}

function skillSummary(
  competencies: LearningSessionAttempt["competencies"],
) {
  const questionSkillCount = competencies.filter(
    (competency) => competency.mappingSource === "committed_event",
  ).length;
  if (questionSkillCount > 0) {
    return `${questionSkillCount} skill${questionSkillCount === 1 ? "" : "s"} practiced`;
  }
  if (competencies.some((competency) => competency.mappingSource === "session_focus")) {
    return "Session skill";
  }
  return "No linked skill";
}

export default function LearningSessionReviewPage() {
  const params = useParams<{ sessionRef: string | string[] }>();
  const rawRef = params.sessionRef;
  const sessionRef = Array.isArray(rawRef) ? rawRef[0] : rawRef;
  const [review, setReview] = useState<LearningSessionReview | null>(null);
  const [objectives, setObjectives] = useState<CompetencyObjective[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState<"not_found" | "unavailable" | null>(null);
  const [routesLoading, setRoutesLoading] = useState(true);
  const [routesFailed, setRoutesFailed] = useState(false);
  const [savedOnly, setSavedOnly] = useState(false);
  const [savingAttempt, setSavingAttempt] = useState<number | null>(null);
  const [flagError, setFlagError] = useState<string | null>(null);
  const [flagStatus, setFlagStatus] = useState("");
  const [retryKey, setRetryKey] = useState(0);
  const [routesRetryKey, setRoutesRetryKey] = useState(0);
  const savedOnlyButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setFailed(null);
    setFlagError(null);

    api.learningSession(sessionRef)
      .then((value) => { if (!cancelled) setReview(value); })
      .catch((error: unknown) => {
        if (cancelled) return;
        setReview(null);
        setFailed(error instanceof ApiError && error.status === 404 ? "not_found" : "unavailable");
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [retryKey, sessionRef]);

  useEffect(() => {
    let cancelled = false;
    setRoutesLoading(true);
    setRoutesFailed(false);

    api.competencies()
      .then((value) => {
        if (cancelled) return;
        setObjectives(value.objectives);
      })
      .catch(() => {
        if (!cancelled) setRoutesFailed(true);
      })
      .finally(() => {
        if (!cancelled) setRoutesLoading(false);
      });

    return () => { cancelled = true; };
  }, [routesRetryKey, sessionRef]);

  const practiceRoutes = useMemo(() => {
    const routes = new Map<string, string>();
    const reviewReturn = `/home/review/${encodeURIComponent(sessionRef)}`;
    objectives.forEach((objective) => {
      objective.subskills.forEach((cell) => {
        const href = competencyPracticeHref(cell.independentReceipt, reviewReturn);
        if (href) routes.set(`${objective.objectiveId}:${cell.subskill}`, href);
      });
    });
    return routes;
  }, [objectives, sessionRef]);

  async function updateFlag(attemptIndex: number, flagged: boolean) {
    if (!review || savingAttempt !== null) return;
    setSavingAttempt(attemptIndex);
    setFlagError(null);
    setFlagStatus("");
    try {
      const result = await api.setLearningSessionFlag(review.session.sessionRef, attemptIndex, flagged);
      setReview((current) => current ? {
        ...current,
        session: { ...current.session, flaggedCount: result.flaggedCount },
        attempts: current.attempts.map((attempt) => attempt.index === result.attemptIndex
          ? { ...attempt, flagged: result.flagged }
          : attempt),
      } : current);
      setFlagStatus(result.flagged
        ? `Question ${result.attemptIndex} saved for review.`
        : `Question ${result.attemptIndex} removed from saved review.`);
      if (savedOnly && !result.flagged) {
        requestAnimationFrame(() => savedOnlyButtonRef.current?.focus());
      }
    } catch {
      setFlagError("That item could not be updated. Your existing saved-review list is unchanged.");
    } finally {
      setSavingAttempt(null);
    }
  }

  if (loading) {
    return <div className={`page ${styles.page}`}><div className={styles.loading} role="status">Opening your completed session…</div></div>;
  }

  if (!review || failed) {
    return (
      <div className={`page ${styles.page}`}>
        <Link className={styles.back} href="/home?panel=activity"><ArrowLeft size={16} aria-hidden="true" /> Back to history</Link>
        <section className={styles.error} role="alert">
          <CircleAlert size={24} aria-hidden="true" />
          <div>
            <h1>{failed === "not_found" ? "This session is not available" : "We couldn’t load this session"}</h1>
            <p>{failed === "not_found" ? "The link may be invalid, expired, or connected to another account." : "Your completed work is still safe. Try opening the session again."}</p>
          </div>
          {failed === "unavailable" ? <button type="button" onClick={() => setRetryKey((value) => value + 1)}><RefreshCw size={15} aria-hidden="true" /> Retry</button> : null}
        </section>
      </div>
    );
  }

  const { session, attempts } = review;
  const presentation = modePresentation[session.mode];
  const ModeIcon = presentation.Icon;
  const scoredAttempts = attempts.filter((attempt) => attempt.score !== null).length;
  const confidenceRecorded = attempts.filter((attempt) => attempt.confidence !== null).length;
  const lowerConfidence = attempts.filter((attempt) => attempt.confidence !== null && attempt.confidence <= 2).length;
  const supportRecorded = attempts.filter((attempt) => attempt.assistance !== null).length;
  const supportedAttempts = attempts.filter((attempt) => attempt.assistance !== null && attempt.assistance.hintsUsed > 0).length;
  const visibleAttempts = savedOnly ? attempts.filter((attempt) => attempt.flagged) : attempts;
  const focusedSkill = session.focusCompetencies[0]?.subskill;
  const showsConfidence = session.mode === "rapid"
    || (session.mode === "training" && focusedSkill === "calibrate_confidence");
  const isPartialPractice = session.status === "abandoned" && (session.mode === "rapid" || session.mode === "training");
  const partialSessionLabel = session.mode === "training" ? "Partial Focused set" : "Partial Rapid round";

  return (
    <div className={`page ${styles.page}`}>
      <Link className={styles.back} href="/home?panel=activity"><ArrowLeft size={16} aria-hidden="true" /> Back to history</Link>

      <header className={styles.header}>
        <span className={styles.modeIcon} data-mode={session.mode} aria-hidden="true"><ModeIcon size={22} /></span>
        <div>
          <p className="eyebrow">{isPartialPractice ? "Partial practice review" : "Session review"}</p>
          <h1>{isPartialPractice ? partialSessionLabel : presentation.label}</h1>
          <p>{isPartialPractice ? "Ended" : "Completed"} {dateLabel(session.completedAt)} · {session.attempted} of {session.total} {isPartialPractice ? "submitted" : "questions completed"}</p>
        </div>
        <div className={styles.headlineOutcome}><span>{session.mode === "clinical" ? "Formative score" : "Score"}</span><strong>{sessionOutcomeLabel(session)}</strong></div>
      </header>

      <aside className={styles.reviewNotice} role="note">
        <ShieldCheck size={20} aria-hidden="true" />
        <p><strong>Review only.</strong> {isPartialPractice
          ? `This ${session.mode === "training" ? "set" : "round"} ended early. Only submitted ECGs are shown; the unanswered ECG was discarded and was not scored. Reviewing cannot change your progress.`
          : `This session is finished, so opening a question won’t change your answers or progress.${session.mode === "clinical" ? " Clinical case results are formative: they shape recommendations but do not update scored skill progress." : ""}`}</p>
      </aside>

      <section className={styles.summary} aria-label="Session summary">
        <article><BarChart3 size={18} aria-hidden="true" /><div><span>{isPartialPractice ? "Submitted ECGs scored" : "Questions scored"}</span><strong>{scoredAttempts}/{attempts.length}</strong></div></article>
        {showsConfidence ? <article><Target size={18} aria-hidden="true" /><div><span>Lower-confidence answers</span><strong>{confidenceRecorded ? `${lowerConfidence} of ${confidenceRecorded}` : "—"}</strong></div></article> : null}
        <article><Lightbulb size={18} aria-hidden="true" /><div><span>Questions with hints</span><strong>{supportRecorded ? `${supportedAttempts} of ${supportRecorded}` : "—"}</strong></div></article>
        <article><Bookmark size={18} aria-hidden="true" /><div><span>Saved for review</span><strong>{session.flaggedCount}</strong></div></article>
      </section>

      {flagError ? <p className={styles.flagError} role="alert">{flagError}</p> : null}
      <p className="sr-only" role="status" aria-live="polite">{flagStatus}</p>

      <section className={styles.attempts} aria-labelledby="session-questions-heading">
        <header>
          <div><p className="eyebrow">Review your work</p><h2 id="session-questions-heading">{isPartialPractice ? "Submitted ECGs" : "Questions"}</h2></div>
          <div className={styles.attemptHeaderActions}>
            <p>Open a question to see your answer, feedback, ECG, and related skills.</p>
            <button ref={savedOnlyButtonRef} type="button" aria-pressed={savedOnly} onClick={() => setSavedOnly((value) => !value)}><Bookmark size={14} aria-hidden="true" /> Saved ({session.flaggedCount})</button>
          </div>
        </header>

        {visibleAttempts.length ? (
          <div className={styles.attemptList}>
            {visibleAttempts.map((attempt) => (
              <details className={styles.attempt} key={attempt.index}>
                <summary>
                  <span className={styles.attemptIndex}>{attempt.index}</span>
                  <span className={styles.attemptCopy}><strong>{isPartialPractice ? "Submitted ECG" : "Question"} {attempt.index}</strong><small>{attempt.flagged ? "Saved · " : ""}{skillSummary(attempt.competencies)}</small></span>
                  <span className={styles.attemptSignals}>
                    <strong>{scoreLabel(attempt.score)}</strong>
                    <small>{showsConfidence ? `${attempt.confidence !== null ? `Confidence ${attempt.confidence}/5` : "Confidence not recorded"} · ` : ""}{attempt.assistance === null
                      ? "Support not recorded"
                      : attempt.assistance.hintsUsed > 0
                        ? `${attempt.assistance.hintsUsed} hint${attempt.assistance.hintsUsed === 1 ? "" : "s"}`
                        : "No hints"}</small>
                  </span>
                  <span className={styles.expand}>Review <ArrowRight size={15} aria-hidden="true" /></span>
                </summary>
                <div className={styles.attemptBody}>
                  {attempt.competencies.length ? (
                    <section className={styles.skillSection} aria-label={`Skills for question ${attempt.index}`}>
                      <h3>Skills in this question</h3>
                      <ul>
                        {attempt.competencies.map((competency, index) => {
                          const key = `${competency.objectiveId}:${competency.subskill}`;
                          const href = practiceRoutes.get(key);
                          const label = conceptLabel(competency.objectiveId);
                          const isSessionFocus = competency.mappingSource === "session_focus";
                          return (
                            <li key={`${key}:${index}`}>
                              <span className={styles.competencyIcon} aria-hidden="true">{competency.score !== null && competency.score >= .7 ? <CheckCircle2 size={17} /> : <Clock3 size={17} />}</span>
                              <div><strong>{label}</strong><span>{subskillLabel(competency.subskill)} · {isSessionFocus ? "Practiced in this session" : scoreLabel(competency.score)}</span></div>
                              {href ? <Link href={href} aria-label={`Practice ${label}: ${subskillLabel(competency.subskill)}`}>Practice this skill <ArrowRight size={14} aria-hidden="true" /></Link> : routesLoading ? <small role="status">Finding a practice option…</small> : routesFailed ? <small><button className="button" type="button" aria-label={`Retry finding practice for ${label}`} onClick={() => setRoutesRetryKey((value) => value + 1)}><RefreshCw size={14} aria-hidden="true" /> Retry</button></small> : <small>Practice isn’t available for this skill yet</small>}
                            </li>
                          );
                        })}
                      </ul>
                    </section>
                  ) : <p>No skill was linked to this question.</p>}
                  <div className={styles.attemptActions}>
                    <Link href={`/home/review/${encodeURIComponent(session.sessionRef)}/attempt/${attempt.index}`}>
                      <ScanLine size={17} aria-hidden="true" /> Review question &amp; ECG <ArrowRight size={14} aria-hidden="true" />
                    </Link>
                    <button type="button" disabled={savingAttempt !== null} onClick={() => void updateFlag(attempt.index, !attempt.flagged)}>
                      {attempt.flagged ? <BookmarkCheck size={15} aria-hidden="true" /> : <Bookmark size={15} aria-hidden="true" />}
                      {savingAttempt === attempt.index ? "Updating…" : attempt.flagged ? "Remove saved" : "Save question"}
                    </button>
                  </div>
                </div>
              </details>
            ))}
          </div>
        ) : (
          <div className={styles.empty}><p>{savedOnly ? "No questions from this session are saved yet." : "There are no questions available to review in this session."}</p></div>
        )}
      </section>
    </div>
  );
}
