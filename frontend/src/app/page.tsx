"use client";

import {
  Activity,
  ArrowRight,
  BookOpenCheck,
  BrainCircuit,
  CheckCircle2,
  ChevronRight,
  CircleGauge,
  Clock3,
  Database,
  GraduationCap,
  ShieldCheck,
  Sparkles,
  Stethoscope,
  Target,
  TimerReset,
  TrendingUp,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { conceptLabel } from "@/lib/coordinates";
import { FOUNDATIONS_PATHWAY_ID } from "@/lib/pathways";
import { readFoundationsProgress, subscribeProgress, type ModuleProgress } from "@/lib/progress";
import type { LearnerProfile } from "@/lib/types";

type ApiState = {
  health: Record<string, unknown> | null;
  dataset: Record<string, unknown> | null;
  profile: LearnerProfile | null;
};

const modes = [
  {
    number: "01",
    title: "Learn",
    subtitle: "Guided pathways",
    description: "Build the mental model with an AI tutor that can pause, explain, demonstrate, and return you to the lesson.",
    href: "/learn",
    cta: "Continue learning",
    icon: GraduationCap,
    tone: "mint",
  },
  {
    number: "02",
    title: "Train",
    subtitle: "Deliberate practice",
    description: "Isolate one skill—RBBB morphology, QTc, axis, territories—and repeat it across diverse real tracings.",
    href: "/train",
    cta: "Open competency lab",
    icon: BrainCircuit,
    tone: "violet",
  },
  {
    number: "03",
    title: "Rapid",
    subtitle: "Full ECG reads",
    description: "Commit a structured interpretation under ward or emergency timing, then see exactly what you missed.",
    href: "/rapid",
    cta: "Start a rapid read",
    icon: TimerReset,
    tone: "amber",
  },
  {
    number: "04",
    title: "Cases",
    subtitle: "Clinical decisions",
    description: "Use the ECG in context: triage, medication safety, disposition, comparison, and defensible next steps.",
    href: "/practice",
    cta: "Enter clinical cases",
    icon: Stethoscope,
    tone: "coral",
  },
];

const onboardingOrder = [
  "normal_ecg", "rate", "sinus_rhythm", "axis_normal", "qrs_duration", "qt_interval",
  "atrial_fibrillation", "right_bundle_branch_block", "left_bundle_branch_block", "qtc_prolongation",
];

export default function DashboardPage() {
  const { user, identityKey } = useAuth();
  const [state, setState] = useState<ApiState>({ health: null, dataset: null, profile: null });
  const [foundations, setFoundations] = useState<ModuleProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    Promise.allSettled([api.health(), api.datasetStatus(), api.profile()])
      .then(([health, dataset, profile]) => {
        if (cancelled) return;
        setState({
          health: health.status === "fulfilled" ? health.value : null,
          dataset: dataset.status === "fulfilled" ? dataset.value : null,
          profile: profile.status === "fulfilled" ? profile.value : null,
        });
        const failures = [health, dataset, profile].filter((result) => result.status === "rejected");
        if (failures.length) setError(`${failures.length} learning service${failures.length === 1 ? "" : "s"} could not be loaded.`);
      });
    let unsubscribe = () => {};
    if (user) {
      api.pathwayProgress(user.userId, FOUNDATIONS_PATHWAY_ID).then((response) => {
        if (cancelled) return;
        const item = response.items.find((entry) => entry.moduleId === "foundations");
        if (!item) {
          setFoundations({ completedScenes: 0, totalScenes: 13, done: false, started: false, bestAccuracy: 0 });
          return;
        }
        const completedScenes = Number(item.state.completedScenes ?? item.completedActionIds.length);
        const totalScenes = Number(item.state.totalScenes ?? 13);
        setFoundations({
          completedScenes,
          totalScenes,
          done: item.status === "complete" || completedScenes >= totalScenes,
          started: item.status !== "not-started",
          bestAccuracy: Number(item.state.bestAccuracy ?? 0),
        });
      }).catch(() => {
        if (!cancelled) setFoundations(null);
      });
    } else {
      const refresh = () => setFoundations(readFoundationsProgress(13, identityKey));
      refresh();
      unsubscribe = subscribeProgress(refresh);
    }
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [identityKey, retryKey, user]);

  const profile = state.profile;
  const attempts = profile?.recentAttempts ?? [];
  const masteryRows = profile?.mastery ?? [];
  const observedSubskills = (profile?.subskillMastery ?? []).filter((row) => row.attempts > 0);
  const independentSubskills = observedSubskills.filter((row) => row.independentAttempts > 0);
  const masteryAverage = independentSubskills.length
    ? Math.round((independentSubskills.reduce((sum, row) => sum + row.independentMastery, 0) / independentSubskills.length) * 100)
    : null;
  const onboardingRank = new Map(onboardingOrder.map((objective, index) => [objective, index]));
  const weakReceipt = [...observedSubskills].sort((left, right) =>
    right.highConfidenceWrong - left.highConfidenceWrong ||
    left.independentMastery - right.independentMastery ||
    left.independentAttempts - right.independentAttempts ||
    (onboardingRank.get(left.concept) ?? 999) - (onboardingRank.get(right.concept) ?? 999),
  )[0];
  const weak = weakReceipt?.concept ?? "normal_ecg";
  const focusMastery = weakReceipt?.independentAttempts
    ? Math.round(weakReceipt.independentMastery * 100)
    : null;
  const profileAvailable = Boolean(profile) && !error;
  const hasObservedEvidence = observedSubskills.length > 0;
  const caseCount = Number(state.dataset?.student_facing_count ?? state.dataset?.case_count ?? 0);
  const tierDistribution = (state.dataset?.tier_distribution ?? {}) as Record<string, number>;
  const tierA = Number(tierDistribution.A ?? 0);
  const sourceCounts = ((state.dataset?.manifest as Record<string, unknown> | undefined)?.sourceCounts ?? {}) as Record<string, number>;
  const hasLeipzig = Number(sourceCounts["leipzig-heart-center"] ?? 0) > 0;
  const provider = state.health?.llmProvider === "openai-compatible" ? "AI tutor connected" : "Grounded demo tutor";
  const foundationPct = foundations?.totalScenes
    ? Math.round((foundations.completedScenes / foundations.totalScenes) * 100)
    : 0;

  const lastAttempt = attempts[0];
  const insights = useMemo(() => {
    const highConfidenceErrors = masteryRows.reduce((sum, row) => sum + row.highConfidenceWrong, 0);
    return [
      { label: "Independent evidence", value: masteryAverage === null ? "—" : `${masteryAverage}%`, icon: CircleGauge },
      { label: "Completed reads", value: String(profile?.attemptCount ?? 0), icon: CheckCircle2 },
      { label: "Calibration flags", value: String(highConfidenceErrors), icon: TrendingUp },
      { label: "Last score", value: lastAttempt ? `${Math.round(lastAttempt.score * 100)}%` : "—", icon: Clock3 },
    ];
  }, [lastAttempt, masteryAverage, masteryRows, profile?.attemptCount]);

  return (
    <div className="page dashboard-page">
      <header className="dashboard-topline">
        <div>
          <p className="eyebrow">Adaptive ECG learning</p>
          <h1>Build a read you can trust.</h1>
        </div>
        <div className="system-status" title="Tutor responses are constrained to curated case evidence">
          <span className="status-orb" aria-hidden="true" />
          <span>{provider}</span>
          <ShieldCheck size={15} aria-hidden="true" />
        </div>
      </header>

      {error ? (
        <div className="warning dashboard-warning">
          Learner data is incomplete, so personalized estimates are hidden. The curriculum remains available. <small>{error}</small>{" "}
          <button className="button subtle small" type="button" onClick={() => setRetryKey((value) => value + 1)}>Retry</button>
        </div>
      ) : null}

      <section className="dashboard-hero">
        <div className="hero-copy">
          <span className="hero-kicker"><Sparkles size={14} aria-hidden="true" /> Your next best step</span>
          <h2>{!profileAvailable
            ? "Your learning profile is temporarily unavailable."
            : !hasObservedEvidence
              ? "Find your ECG starting point."
              : focusMastery !== null && focusMastery < 55
                ? `Make ${conceptLabel(weak)} unmistakable.`
                : "Transfer your strongest skills to a mixed read."}</h2>
          <p>
            {!profileAvailable
              ? "You can continue the curriculum, but TRACE will not invent a mastery estimate or personalized recommendation while learner evidence is unavailable."
              : !hasObservedEvidence
                ? "No competency has been assessed yet. Start untimed so the first recommendation is based on your own ECG evidence rather than a default prior."
                : focusMastery !== null
                  ? `Your current independent ${weakReceipt?.subskill.replaceAll("_", " ") ?? "transfer"} evidence is ${focusMastery}%. The next set will focus, contrast, then test transfer on fresh tracings.`
                  : `You have formative work in ${conceptLabel(weak)}, but no independent transfer estimate yet. The next set will establish one without treating a prior as performance.`}
          </p>
          <div className="hero-actions">
            {profileAvailable && hasObservedEvidence ? (
              <Link className="button primary hero-primary" href="/review">
                <Target size={17} aria-hidden="true" /> Open my mastery plan <ArrowRight size={16} aria-hidden="true" />
              </Link>
            ) : (
              <Link className="button primary hero-primary" href="/rapid">
                <Target size={17} aria-hidden="true" /> Start an untimed baseline <ArrowRight size={16} aria-hidden="true" />
              </Link>
            )}
            <Link className="button hero-secondary" href="/learn">Open guided learning</Link>
          </div>
          <div className="hero-plan" aria-label="Adaptive session plan">
            <span><strong>01</strong> focused competency</span>
            <i aria-hidden="true" />
            <span><strong>02</strong> close mimics</span>
            <i aria-hidden="true" />
            <span><strong>03</strong> mixed transfer</span>
          </div>
        </div>

        <div className="hero-signal" aria-hidden="true">
          <div className="signal-label"><span>LEARNING EVIDENCE</span><span>{focusMastery === null ? "NOT YET ASSESSED" : `${focusMastery}%`}</span></div>
          <svg viewBox="0 0 720 240" preserveAspectRatio="none">
            <defs>
              <pattern id="hero-grid-small" width="12" height="12" patternUnits="userSpaceOnUse">
                <path d="M 12 0 L 0 0 0 12" fill="none" stroke="rgba(255,255,255,.08)" strokeWidth="1" />
              </pattern>
              <pattern id="hero-grid" width="60" height="60" patternUnits="userSpaceOnUse">
                <rect width="60" height="60" fill="url(#hero-grid-small)" />
                <path d="M 60 0 L 0 0 0 60" fill="none" stroke="rgba(255,255,255,.13)" strokeWidth="1" />
              </pattern>
              <linearGradient id="trace-glow" x1="0" x2="1">
                <stop offset="0" stopColor="#8ae3c3" />
                <stop offset=".55" stopColor="#ffffff" />
                <stop offset="1" stopColor="#f7c46c" />
              </linearGradient>
            </defs>
            <rect width="720" height="240" fill="url(#hero-grid)" />
            <path className="hero-trace-shadow" d="M0 126 L48 126 L62 121 L70 129 L80 126 L103 126 L113 115 L120 139 L129 126 L144 126 L154 120 L163 128 L174 126 L224 126 L238 122 L248 129 L258 126 L286 126 L300 110 L306 150 L317 126 L345 126 L356 119 L366 129 L378 126 L425 126 L439 121 L449 130 L460 126 L485 126 L499 112 L505 146 L516 126 L544 126 L556 118 L568 130 L580 126 L629 126 L643 122 L652 129 L664 126 L720 126" />
            <path className="hero-trace" d="M0 126 L48 126 L62 121 L70 129 L80 126 L103 126 L113 115 L120 139 L129 126 L144 126 L154 120 L163 128 L174 126 L224 126 L238 122 L248 129 L258 126 L286 126 L300 110 L306 150 L317 126 L345 126 L356 119 L366 129 L378 126 L425 126 L439 121 L449 130 L460 126 L485 126 L499 112 L505 146 L516 126 L544 126 L556 118 L568 130 L580 126 L629 126 L643 122 L652 129 L664 126 L720 126" />
          </svg>
          <div className="signal-footer">
            <span><Database size={14} /> {caseCount ? `${caseCount.toLocaleString()} teaching ECGs` : "Corpus status loading"}</span>
            <span>{tierA ? `${tierA.toLocaleString()} high-confidence` : "Tier status loading"}</span>
          </div>
        </div>
      </section>

      <section className="insight-strip" aria-label="Learning summary">
        {insights.map(({ label, value, icon: Icon }) => (
          <div className="insight-item" key={label}>
            <Icon size={17} aria-hidden="true" />
            <div><strong>{value}</strong><span>{label}</span></div>
          </div>
        ))}
      </section>

      <section className="dashboard-section">
        <div className="section-heading-row">
          <div>
            <p className="eyebrow">Four ways to build fluency</p>
            <h2>Choose the kind of work you need.</h2>
          </div>
          <p>One competency model follows you across every mode.</p>
        </div>
        <div className="mode-grid">
          {modes.map((mode) => {
            const Icon = mode.icon;
            return (
              <Link className={`mode-card mode-${mode.tone}`} href={mode.href} key={mode.title}>
                <div className="mode-card-top">
                  <span className="mode-number">{mode.number}</span>
                  <span className="mode-icon"><Icon size={20} aria-hidden="true" /></span>
                </div>
                <p>{mode.subtitle}</p>
                <h3>{mode.title}</h3>
                <span className="mode-description">{mode.description}</span>
                <span className="mode-cta">{mode.cta} <ChevronRight size={16} aria-hidden="true" /></span>
              </Link>
            );
          })}
        </div>
      </section>

      <div className="dashboard-lower-grid">
        <section className="panel continue-card">
          <div className="continue-visual" aria-hidden="true">
            <span className="continue-step">{foundationPct || 0}%</span>
            <BookOpenCheck size={27} />
          </div>
          <div className="continue-copy">
            <p className="eyebrow">Continue where you left off</p>
            <h2>Foundations · The systematic sweep</h2>
            <p>Move from individual waves to a complete, repeatable 12-lead read with progressively fading support.</p>
            <div className="continue-progress"><span style={{ width: `${Math.max(4, foundationPct)}%` }} /></div>
            <small>{foundations?.completedScenes ?? 0} of 13 learning scenes complete</small>
          </div>
          <Link className="round-link" href="/learn/foundations" aria-label="Continue Foundations">
            <ArrowRight size={19} aria-hidden="true" />
          </Link>
        </section>

        <section className="panel corpus-card">
          <div className="corpus-card-heading">
            <div>
              <p className="eyebrow">Real-world variation</p>
              <h2>Practice beyond the textbook tracing.</h2>
            </div>
            <Activity size={22} aria-hidden="true" />
          </div>
          <p>Every learner-facing record is de-identified, signal-checked, and confidence-gated before it can enter a session.</p>
          <div className="corpus-stats">
            <span><strong>{caseCount ? caseCount.toLocaleString() : "—"}</strong> learner-ready cases</span>
            <span><strong>{Object.keys((state.dataset?.manifest as Record<string, unknown> | undefined)?.conceptABCounts ?? {}).length || 30}</strong> grounded findings</span>
          </div>
          <div className="provenance-line"><ShieldCheck size={14} /> PTB-XL + PTB-XL+{hasLeipzig ? " · Leipzig expert rhythm annotations" : ""} · source-specific evidence gates</div>
        </section>
      </div>
    </div>
  );
}
