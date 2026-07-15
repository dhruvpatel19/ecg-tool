"use client";

import {
  ArrowRight,
  BookOpenCheck,
  BrainCircuit,
  CircleGauge,
  GraduationCap,
  Sparkles,
  Stethoscope,
  Target,
  TimerReset,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import {
  api,
  type AdaptivePlan,
  type LearningResumeSession,
  type LearningResumeSnapshot,
} from "@/lib/api";
import {
  learningResumePresentation,
  type LearningResumePresentation,
} from "@/lib/learningResume";
import type { LearnerProfile } from "@/lib/types";
import styles from "../dashboard.module.css";

const modes = [
  {
    title: "Guided learning",
    description: "Build the mental model with guided, interactive lessons.",
    href: "/learn",
    cta: "Open guided learning",
    icon: GraduationCap,
  },
  {
    title: "Focused practice",
    description: "Repeat one finding across real ECGs and close mimics.",
    href: "/train",
    cta: "Open focused practice",
    icon: BrainCircuit,
  },
  {
    title: "Rapid practice",
    description: "Practice complete reads with ward or emergency pacing.",
    href: "/rapid",
    cta: "Start rapid practice",
    icon: TimerReset,
  },
  {
    title: "Clinical cases",
    description: "Use the ECG inside realistic clinical decisions.",
    href: "/practice",
    cta: "Open clinical cases",
    icon: Stethoscope,
  },
];

export default function DashboardPage() {
  const [profile, setProfile] = useState<LearnerProfile | null>(null);
  const [adaptivePlan, setAdaptivePlan] = useState<AdaptivePlan | null>(null);
  const [resume, setResume] = useState<LearningResumeSnapshot | null>(null);
  const [loadingProfile, setLoadingProfile] = useState(true);
  const [loadingPlan, setLoadingPlan] = useState(true);
  const [loadingResume, setLoadingResume] = useState(true);
  const [profileFailed, setProfileFailed] = useState(false);
  const [planFailed, setPlanFailed] = useState(false);
  const [resumeFailed, setResumeFailed] = useState(false);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoadingProfile(true);
    setLoadingPlan(true);
    setLoadingResume(true);
    setProfile(null);
    setAdaptivePlan(null);
    setResume(null);
    setProfileFailed(false);
    setPlanFailed(false);
    setResumeFailed(false);
    api.profile()
      .then((value) => {
        if (!cancelled) setProfile(value);
      })
      .catch(() => {
        if (!cancelled) {
          setProfile(null);
          setProfileFailed(true);
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingProfile(false);
      });
    api.adaptivePlan()
      .then((value) => {
        if (!cancelled) setAdaptivePlan(value);
      })
      .catch(() => {
        if (!cancelled) {
          setAdaptivePlan(null);
          setPlanFailed(true);
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingPlan(false);
      });
    api.learningResume()
      .then((value) => {
        if (!cancelled) setResume(value);
      })
      .catch(() => {
        if (!cancelled) {
          setResume(null);
          setResumeFailed(true);
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingResume(false);
      });

    return () => {
      cancelled = true;
    };
  }, [retryKey]);

  const subskills = profile?.subskillMastery ?? [];
  const assessed = subskills.filter((row) => row.independentAttempts > 0);
  const masteryAverage = assessed.length
    ? Math.round(assessed.reduce((sum, row) => sum + row.independentMastery, 0) / assessed.length * 100)
    : null;
  const dueCount = subskills.filter((row) => row.isDue).length;

  const compatibleResume = resume?.version === "learning-resume-v1" ? resume : null;
  const resumable = [compatibleResume?.primary, ...(compatibleResume?.additional ?? [])]
    .filter((session): session is LearningResumeSession => session !== null && session !== undefined)
    .map((session) => ({ session, presentation: learningResumePresentation(session) }))
    .filter((item): item is { session: LearningResumeSession; presentation: LearningResumePresentation } => (
      item.presentation !== null
    ));
  const primaryResume = resumable[0] ?? null;
  const additionalResumes = resumable.slice(1);

  const runnableStage = adaptivePlan?.stages
    .filter((stage) => stage.href.trim().length > 0)
    .sort((left, right) => left.order - right.order)[0] ?? null;
  const guidedRemediation = adaptivePlan?.guidedRemediation?.href.trim()
    ? adaptivePlan.guidedRemediation
    : null;
  const recommendedStep = guidedRemediation ?? runnableStage;
  const personalizedRecommendation = !loadingPlan && Boolean(recommendedStep);
  const planUnavailable = !loadingPlan && planFailed;
  const baselineNeeded = !loadingPlan
    && !planFailed
    && !recommendedStep
    && Boolean(adaptivePlan?.basis.baselineNeeded);
  const primaryLoading = loadingResume || (!primaryResume && loadingPlan);
  const nextTitle = loadingResume
    ? "Checking your saved sessions…"
    : primaryResume?.presentation.title
      ?? (loadingPlan
        ? "Building your next step…"
        : recommendedStep?.title
          ?? (baselineNeeded ? "Start with an untimed baseline." : "Try an untimed rapid ECG."));
  const nextCopy = loadingResume
    ? "Looking for unfinished work across every learning mode."
    : primaryResume?.presentation.detail
      ?? (loadingPlan
        ? "Checking your saved practice plan."
        : recommendedStep?.purpose
          ?? (baselineNeeded
            ? "Complete a short mixed ECG set to create the first independent evidence for future recommendations."
            : "This is a general practice option, not a recommendation based on your progress."));
  const nextReason = !primaryResume && personalizedRecommendation
    ? guidedRemediation?.reason || adaptivePlan?.primary?.reason || adaptivePlan?.explanation || null
    : null;
  const nextHref = primaryResume?.presentation.href
    ?? recommendedStep?.href
    ?? (baselineNeeded
      ? "/rapid?pace=untimed&suggestedLength=10"
      : "/rapid?pace=untimed&suggestedLength=5");
  const nextLabel = loadingResume
    ? "Checking saved sessions"
    : primaryResume?.presentation.cta
      ?? (loadingPlan
        ? "Preparing next step"
        : personalizedRecommendation
          ? guidedRemediation ? "Open guided review" : "Start recommended practice"
          : baselineNeeded ? "Start baseline" : "Start general practice");
  const warningParts = [
    resumeFailed ? "Your saved sessions could not be checked; no session was changed." : null,
    profileFailed ? "Your learning snapshot is temporarily unavailable." : null,
    planUnavailable ? "Your personalized next step is temporarily unavailable; any fallback shown is general practice." : null,
  ].filter(Boolean);
  const warningMessage = warningParts.length ? warningParts.join(" ") : null;

  return (
    <div className={`page ${styles.page}`}>
      <header className={styles.header}>
        <div>
          <p className="eyebrow">Today</p>
          <h1>Build a read you can trust.</h1>
          <p>One clear next step, then the ECG does the teaching.</p>
        </div>
        <Link className={styles.progressLink} href="/profile">
          <CircleGauge size={17} aria-hidden="true" /> View progress
        </Link>
      </header>

      {warningMessage ? (
        <div className={styles.warning} role="status">
          <span>{warningMessage}</span>
          <button type="button" onClick={() => setRetryKey((value) => value + 1)}>Retry</button>
        </div>
      ) : null}

      <section className={styles.nextCard} aria-labelledby="next-step-title">
        <div className={styles.nextIcon} aria-hidden="true">
          {primaryResume ? <BookOpenCheck size={21} /> : <Sparkles size={21} />}
        </div>
        <div className={styles.nextCopy}>
          <p className="eyebrow">
            {loadingResume
              ? "Continue"
              : primaryResume?.presentation.phaseLabel
                ?? (baselineNeeded
                  ? "Baseline · not yet personalized"
                  : planUnavailable || !recommendedStep
                    ? "General practice · not personalized"
                    : "Recommended next")}
          </p>
          <h2 id="next-step-title">{nextTitle}</h2>
          <p>{nextCopy}</p>
          {nextReason ? <small className={styles.nextReason}>Why now: {nextReason}</small> : null}
          {primaryResume && !loadingPlan && recommendedStep ? (
            <Link className={styles.afterLink} href={recommendedStep.href}>
              <span>After you finish</span>
              <strong>{recommendedStep.title}</strong>
              <ArrowRight size={14} aria-hidden="true" />
            </Link>
          ) : null}
        </div>
        <div className={styles.nextAction}>
          {primaryLoading ? (
            <button className="button primary" type="button" disabled aria-disabled="true">
              <Target size={16} aria-hidden="true" /> {nextLabel} <ArrowRight size={16} aria-hidden="true" />
            </button>
          ) : (
            <Link className="button primary" href={nextHref}>
              <Target size={16} aria-hidden="true" /> {nextLabel} <ArrowRight size={16} aria-hidden="true" />
            </Link>
          )}
        </div>
        <dl className={styles.snapshot} aria-label="Learning snapshot">
          <div><dt>Independent estimate</dt><dd>{loadingProfile ? "Loading" : profileFailed ? "Unavailable" : masteryAverage === null ? "Not assessed" : `${masteryAverage}%`}</dd></div>
          <div><dt>Independent skills</dt><dd>{loadingProfile ? "Loading" : profileFailed ? "Unavailable" : assessed.length}</dd></div>
          <div><dt>Skills due</dt><dd>{loadingProfile ? "Loading" : profileFailed ? "Unavailable" : dueCount}</dd></div>
        </dl>
      </section>

      <section className={styles.modes} aria-labelledby="mode-heading">
        <div className={styles.sectionHeading}>
          <div>
            <p className="eyebrow">Learning modes</p>
            <h2 id="mode-heading">Choose the kind of work you need.</h2>
          </div>
          <span>Choose the mode that fits today’s learning goal.</span>
        </div>
        <div className={styles.modeGrid}>
          {modes.map(({ title, description, href, cta, icon: Icon }) => (
            <Link className={styles.modeCard} href={href} key={title} aria-label={cta}>
              <span className={styles.modeIcon}><Icon size={19} aria-hidden="true" /></span>
              <span className={styles.modeCopy}><strong>{title}</strong><small>{description}</small></span>
              <ArrowRight size={17} aria-hidden="true" />
            </Link>
          ))}
        </div>
      </section>

      {additionalResumes.length ? (
        <section className={styles.lower} aria-label="Other open sessions">
          <div className={styles.additionalCard}>
            <div className={styles.additionalHeading}>
              <span>Other open sessions</span>
              <small>Continue any without losing your primary place.</small>
            </div>
            <div className={styles.additionalList}>
              {additionalResumes.map(({ session, presentation }) => {
                if (!presentation) return null;
                const Icon = session.mode === "guided"
                  ? GraduationCap
                  : session.mode === "training"
                    ? BrainCircuit
                    : session.mode === "rapid"
                      ? TimerReset
                      : Stethoscope;
                return (
                  <Link href={presentation.href} key={session.mode} aria-label={presentation.cta}>
                    <Icon size={16} aria-hidden="true" />
                    <span><strong>{presentation.title.replace("Continue ", "")}</strong><small>{presentation.phaseLabel} · {presentation.detail}</small></span>
                    <ArrowRight size={15} aria-hidden="true" />
                  </Link>
                );
              })}
            </div>
          </div>
        </section>
      ) : null}
    </div>
  );
}
