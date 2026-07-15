"use client";

import {
  ArrowRight,
  ChevronDown,
  GitBranch,
  ListChecks,
  MessageSquare,
  RefreshCw,
  Sparkles,
  Stethoscope,
  X,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { TutorChat } from "@/components/TutorChat";
import type { AdaptivePlan, AdaptivePriority } from "@/lib/api";
import { conceptLabel } from "@/lib/coordinates";
import styles from "@/app/review/review.module.css";

const PLAN_COACH_VIEWER_STATE = {
  activity: "adaptive_mastery_plan",
  surface: "profile-plan",
} as const;

const PLAN_COACH_SCOPE = "adaptive-mastery-plan";

const SUBSKILL_LABELS: Record<string, string> = {
  recognize: "spot and name",
  localize: "locate on the tracing",
  measure: "measure accurately",
  discriminate: "separate close look-alikes",
  explain_mechanism: "explain the mechanism",
  synthesize: "build a complete read",
  apply_in_context: "apply in a clinical setting",
  calibrate_confidence: "match confidence to accuracy",
};

function subskillLabel(value: string) {
  return SUBSKILL_LABELS[value] ?? value.replaceAll("_", " ");
}

function modeLabel(mode: AdaptivePlan["stages"][number]["mode"]) {
  if (mode === "rapid") return "rapid read";
  if (mode === "clinical") return "clinical case";
  return "focused practice";
}

function ctaLabel(mode: AdaptivePlan["stages"][number]["mode"]) {
  if (mode === "rapid") return "Start rapid practice";
  if (mode === "clinical") return "Start clinical case";
  return "Start focused practice";
}

function recommendationTitle(plan: AdaptivePlan) {
  if (plan.guidedRemediation) return plan.guidedRemediation.title;
  const label = plan.primary ? conceptLabel(plan.primary.objectiveId) : "your ECG foundations";
  if (plan.basis.baselineNeeded) return `Start with ${label}`;
  if (plan.primary?.highConfidenceWrong) return `Recheck ${label}`;
  if (plan.primary?.isDue) return `Refresh ${label}`;
  if (plan.primary?.state === "unseen") return `Build ${label}`;
  return `Strengthen ${label}`;
}

function recommendationCopy(plan: AdaptivePlan) {
  if (plan.guidedRemediation) return plan.guidedRemediation.purpose;
  const skill = subskillLabel(plan.primary?.subskill ?? "recognize");
  if (plan.basis.baselineNeeded) return `Complete a short set focused on how well you can ${skill}. This gives your coach a useful starting point for what comes next.`;
  if (plan.primary?.highConfidenceWrong) return `A recent confident miss makes this a useful place to slow down, ${skill}, and check your reasoning.`;
  if (plan.primary?.isDue) return `You have seen this before. A fresh example now will help make your ${skill} skill more dependable.`;
  if (plan.primary?.state === "unseen") return `This is an important gap in your current practice history. Begin with a real ECG and focus on how to ${skill}.`;
  return `Another varied ECG will help you ${skill} more consistently without adding unnecessary review.`;
}

function whyCopy(plan: AdaptivePlan) {
  if (plan.guidedRemediation) return plan.guidedRemediation.reason;
  if (plan.basis.baselineNeeded) return "You have not completed a scored practice check yet, so a short baseline set comes first.";
  if (plan.primary?.highConfidenceWrong) return "Confidence and accuracy did not line up on a recent attempt, so this deserves an early second look.";
  if (plan.primary?.isDue) return "Enough time has passed for a useful retrieval check before the skill fades.";
  if (plan.primary?.state === "unseen") return "This skill has not appeared in your completed practice yet.";
  return "This is the clearest current opportunity to turn recent practice into a more reliable skill.";
}

function priorityCopy(priority: AdaptivePriority) {
  if (priority.highConfidenceWrong) return "Revisit a confident miss and make the trace evidence explicit.";
  if (priority.isDue) return "Ready for a spaced retrieval check.";
  if (priority.state === "unseen") return "Not yet checked in scored practice.";
  if (priority.lapses) return "Recent performance varied across examples.";
  return "More varied ECGs will make this skill steadier.";
}

type StudyPlanPanelProps = {
  plan: AdaptivePlan | null;
  loading: boolean;
  failed: boolean;
  onRetry: () => void;
};

export function StudyPlanPanel({ plan, loading, failed, onRetry }: StudyPlanPanelProps) {
  const [coachOpen, setCoachOpen] = useState(false);
  const coachTriggerRef = useRef<HTMLButtonElement | null>(null);
  const coachDrawerRef = useRef<HTMLElement | null>(null);
  const coachCloseRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!coachOpen) return;
    const trigger = coachTriggerRef.current;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const frame = window.requestAnimationFrame(() => coachCloseRef.current?.focus());

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setCoachOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(coachDrawerRef.current?.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ) ?? []).filter((element) => !element.hasAttribute("hidden"));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable.at(-1)!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      trigger?.focus();
    };
  }, [coachOpen]);

  if (loading) {
    return (
      <section className={styles.loadingCard} role="status" aria-live="polite" aria-label="Loading your next practice step">
        <div className={styles.loadingIcon} aria-hidden="true"><Sparkles size={20} /></div>
        <div><strong>Finding your best next step…</strong><p>Checking your recent practice without changing your saved progress.</p></div>
        <div className={styles.loadingBar} aria-hidden="true"><span /></div>
      </section>
    );
  }

  if (failed || !plan) {
    return (
      <section className={styles.errorCard} role="alert">
        <div><strong>Nothing was changed.</strong><p>We couldn’t load your study plan. Your saved progress is unchanged.</p></div>
        <button className="button subtle" type="button" onClick={onRetry}><RefreshCw size={15} aria-hidden="true" /> Try again</button>
      </section>
    );
  }

  const runnableStages = plan.stages
    .filter((stage) => stage.href.trim().length > 0)
    .sort((left, right) => left.order - right.order);
  const firstStage = runnableStages[0] ?? null;
  const guidedRemediation = plan.guidedRemediation?.href.trim() ? plan.guidedRemediation : null;
  const fallbackKind = !guidedRemediation && !firstStage
    ? plan.basis.baselineNeeded ? "baseline" : "general"
    : null;
  const fallbackHref = fallbackKind === "baseline"
    ? "/rapid?pace=untimed&suggestedLength=10&returnTo=%2Fprofile%3Ftab%3Dplan"
    : "/rapid?pace=untimed&suggestedLength=5&returnTo=%2Fprofile%3Ftab%3Dplan";
  const actionHref = guidedRemediation?.href ?? firstStage?.href ?? fallbackHref;
  const actionLabel = guidedRemediation
    ? "Open guided review"
    : firstStage
      ? ctaLabel(firstStage.mode)
      : fallbackKind === "baseline"
        ? "Start baseline"
        : "Start general practice";
  const heading = fallbackKind === "baseline"
    ? "Establish an independent baseline"
    : fallbackKind === "general"
      ? "No personalized step is available"
      : recommendationTitle(plan);
  const description = fallbackKind === "baseline"
    ? "Complete a short untimed mixed set to create the first independent evidence for future recommendations."
    : fallbackKind === "general"
      ? "Your saved evidence is unchanged. This general untimed option is available without being described as progress-based."
      : recommendationCopy(plan);
  const followUpStages = guidedRemediation ? runnableStages : runnableStages.slice(1);
  const morePriorities = plan.priorities.filter((priority) => (
    !plan.primary || priority.objectiveId !== plan.primary.objectiveId || priority.subskill !== plan.primary.subskill
  )).slice(0, 5);

  return (
    <div className={styles.embeddedPanel} data-primary-mode={guidedRemediation ? "guided" : firstStage?.mode ?? fallbackKind ?? "none"}>
      <section className={styles.recommendation} aria-labelledby="coach-recommendation-title">
        <div className={styles.recommendationCopy}>
          <span className={styles.recommendationKicker}>
            <Sparkles size={15} aria-hidden="true" />
            {fallbackKind === "baseline" ? "Baseline · not yet personalized" : fallbackKind === "general" ? "General practice · not personalized" : "Recommended next"}
          </span>
          <h2 id="coach-recommendation-title">{heading}</h2>
          <p>{description}</p>
          {guidedRemediation ? (
            <div className={styles.taskMeta} aria-label="Recommended guided review details">
              <span>1 authored scene</span>
              <span>supportive review</span>
              <span>formative · does not update mastery</span>
            </div>
          ) : firstStage ? (
            <div className={styles.taskMeta} aria-label="Recommended practice details">
              <span>{firstStage.suggestedLength} ECG{firstStage.suggestedLength === 1 ? "" : "s"}</span>
              <span>{subskillLabel(firstStage.receiptSubskill)}</span>
              <span>{modeLabel(firstStage.mode)}</span>
            </div>
          ) : (
            <div className={styles.taskMeta} aria-label="General practice details">
              <span>{fallbackKind === "baseline" ? "10 ECGs" : "5 ECGs"}</span>
              <span>untimed</span>
              <span>{fallbackKind === "baseline" ? "baseline · not yet personalized" : "general · not personalized"}</span>
            </div>
          )}
          <div className={styles.primaryActions}>
            <Link className={`button primary ${styles.primaryCta}`} href={actionHref} data-testid="recommended-action">
              {actionLabel} <ArrowRight size={16} aria-hidden="true" />
            </Link>
            <button ref={coachTriggerRef} className={`button subtle ${styles.coachButton}`} type="button" aria-haspopup="dialog" aria-expanded={coachOpen} onClick={() => setCoachOpen(true)}>
              <MessageSquare size={16} aria-hidden="true" /> Ask the plan coach
            </button>
          </div>
        </div>
        <div className={styles.recommendationNote}>
          <span>{fallbackKind ? "What this means" : "Why now"}</span>
          <p>{fallbackKind === "baseline"
            ? "No independently scored competency observation is available yet, so this creates a starting point."
            : fallbackKind === "general"
              ? "The planner returned no runnable personalized stage. General practice will not be presented as an adaptive recommendation."
              : whyCopy(plan)}</p>
        </div>
      </section>

      <section className={styles.disclosures} aria-label="More from your study plan">
        <details className={styles.disclosure}>
          <summary><span className={styles.summaryIcon}><ListChecks size={18} aria-hidden="true" /></span><span><strong>{fallbackKind ? "Why this option" : "Why this recommendation"}</strong><small>{fallbackKind ? "See why this is not yet personalized." : "See the practice signals behind today’s choice."}</small></span><ChevronDown className={styles.chevron} size={18} aria-hidden="true" /></summary>
          <div className={styles.disclosureBody}>
            <p>{fallbackKind === "baseline"
              ? "A baseline is needed before the scheduler can use your own independent evidence."
              : fallbackKind === "general"
                ? "The scheduler returned no runnable personalized stage, so this option is deliberately labeled as general practice."
                : whyCopy(plan)}</p>
            <div className={styles.signalGrid}>
              <span><strong>{plan.basis.independentCompetencyObservations ?? plan.basis.independentAttempts}</strong> objective checks recorded</span>
              <span><strong>{plan.basis.dueCompetencies}</strong> skills ready to revisit</span>
              <span><strong>{plan.basis.highConfidenceMisses}</strong> confidence mismatches to review</span>
            </div>
          </div>
        </details>

        {followUpStages.length ? (
          <details className={styles.disclosure}>
            <summary><span className={styles.summaryIcon}><ArrowRight size={18} aria-hidden="true" /></span><span><strong>What comes after this</strong><small>Preview the next steps without leaving this page.</small></span><ChevronDown className={styles.chevron} size={18} aria-hidden="true" /></summary>
            <div className={styles.disclosureBody}>
              <ol className={styles.stageList}>{followUpStages.map((stage) => (
                <li key={`${stage.order}-${stage.mode}`}><span>{stage.order}</span><div><strong>{conceptLabel(stage.receiptConcept)}</strong><small>{subskillLabel(stage.receiptSubskill)} · {modeLabel(stage.mode)}</small></div><Link href={stage.href}>Open <ArrowRight size={14} aria-hidden="true" /></Link></li>
              ))}</ol>
            </div>
          </details>
        ) : null}

        {plan.integration ? (
          <details className={styles.disclosure}>
            <summary><span className={styles.summaryIcon}><GitBranch size={18} aria-hidden="true" /></span><span><strong>Connect it to a full ECG read</strong><small>Bring this skill back into a complete interpretation.</small></span><ChevronDown className={styles.chevron} size={18} aria-hidden="true" /></summary>
            <div className={`${styles.disclosureBody} ${styles.integrationBody}`}><p>{plan.integration.prompt}</p><Link className="button" href={plan.integration.href}>Practice the full read <ArrowRight size={15} aria-hidden="true" /></Link></div>
          </details>
        ) : null}

        {plan.clinicalApplication ? (
          <details className={styles.disclosure}>
            <summary><span className={styles.summaryIcon}><Stethoscope size={18} aria-hidden="true" /></span><span><strong>Apply it in a patient case</strong><small>Use the pattern in context after the ECG check.</small></span><ChevronDown className={styles.chevron} size={18} aria-hidden="true" /></summary>
            <div className={`${styles.disclosureBody} ${styles.integrationBody}`}><div><p>{plan.clinicalApplication.purpose}</p><small className="muted">Cases shape future recommendations; mixed ECG checks update mastery.</small></div><Link className="button" href={plan.clinicalApplication.href}>Open clinical case <ArrowRight size={15} aria-hidden="true" /></Link></div>
          </details>
        ) : null}

        {morePriorities.length ? (
          <details className={styles.disclosure}>
            <summary><span className={styles.summaryIcon}><ListChecks size={18} aria-hidden="true" /></span><span><strong>Other skills to revisit</strong><small>Keep the wider plan available without crowding today’s task.</small></span><ChevronDown className={styles.chevron} size={18} aria-hidden="true" /></summary>
            <div className={styles.disclosureBody}><ul className={styles.priorityList}>{morePriorities.map((priority) => (
              <li key={`${priority.caseConcept}:${priority.subskill}`}><div><strong>{conceptLabel(priority.objectiveId)}</strong><span>{subskillLabel(priority.subskill)}</span></div><p>{priorityCopy(priority)}</p></li>
            ))}</ul></div>
          </details>
        ) : null}
      </section>

      {coachOpen ? (
        <div className={styles.drawerBackdrop} onMouseDown={(event) => { if (event.target === event.currentTarget) setCoachOpen(false); }}>
          <aside ref={coachDrawerRef} className={styles.coachDrawer} role="dialog" aria-modal="true" aria-labelledby="plan-coach-title" aria-describedby="plan-coach-description">
            <header className={styles.drawerHeader}>
              <div><p className="eyebrow">Plan coach</p><h2 id="plan-coach-title">Ask about this plan</h2><p id="plan-coach-description">The coach can explain your current recommendation. It cannot score work or change your progress.</p></div>
              <button ref={coachCloseRef} className={styles.closeButton} type="button" aria-label="Close plan coach" onClick={() => setCoachOpen(false)}><X size={20} aria-hidden="true" /></button>
            </header>
            <div className={styles.drawerContent}>
              <TutorChat mode="freeform" roleLabel="Plan coach" lessonId={PLAN_COACH_SCOPE} openingPrompt="Ask why this comes first, how to approach it, or how it connects to your broader ECG reading skills." viewerState={PLAN_COACH_VIEWER_STATE} adaptiveContext={plan.coachContext} resetKey={plan.coachContext.contextId} />
            </div>
          </aside>
        </div>
      ) : null}
    </div>
  );
}
