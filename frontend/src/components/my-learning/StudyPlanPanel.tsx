"use client";

import {
  ArrowRight,
  CalendarDays,
  ChevronDown,
  GitBranch,
  ListChecks,
  MessageSquare,
  RefreshCw,
  Sparkles,
  Stethoscope,
} from "lucide-react";
import Link from "next/link";
import type { AdaptivePlan, AdaptivePriority } from "@/lib/api";
import { conceptLabel } from "@/lib/coordinates";
import type { LearningHomeRecommendation } from "@/lib/learningHome";
import { competencySkillLabel as subskillLabel } from "@/lib/learning/skillLabels";
import styles from "./StudyPlanPanel.module.css";

function modeLabel(mode: AdaptivePlan["stages"][number]["mode"]) {
  if (mode === "rapid") return "rapid practice";
  if (mode === "clinical") return "clinical case";
  return "focused practice";
}

function priorityCopy(priority: AdaptivePriority) {
  if (priority.highConfidenceWrong) return "You felt confident on a recent miss, so another example can help you check the pattern more carefully.";
  if (priority.isDue) return "It has been a while since you practiced this skill, so a quick check can help it stick.";
  if (priority.state === "unseen") return "You have not tried this skill in a scored check yet.";
  if (priority.lapses) return "Your recent results varied, so this skill is worth another look.";
  return "A few more varied ECGs can make this skill feel steadier.";
}

type StudyPlanPanelProps = {
  plan: AdaptivePlan | null;
  loading: boolean;
  failed: boolean;
  recommendation: LearningHomeRecommendation;
  onRetry: () => void;
  onOpenCoach: (draft?: string) => void;
  onSchedulePlan: () => void;
};

export function StudyPlanPanel({ plan, loading, failed, recommendation, onRetry, onOpenCoach, onSchedulePlan }: StudyPlanPanelProps) {
  if (loading) {
    return (
      <section className={styles.loadingCard} role="status" aria-live="polite" aria-label="Loading your next practice step">
        <span className={styles.loadingIcon} aria-hidden="true"><Sparkles size={20} /></span>
        <div><strong>Finding your best next step with Luna…</strong><p>Looking at your recent work without changing your progress.</p></div>
        <span className={styles.loadingBar} aria-hidden="true"><span /></span>
      </section>
    );
  }

  if (failed || !plan) {
    return (
      <section className={styles.errorCard} role="alert">
        <div><strong>Your plan could not be loaded.</strong><p>Nothing was changed. Your saved progress is safe.</p></div>
        <button className="button subtle" type="button" onClick={onRetry}><RefreshCw size={15} aria-hidden="true" /> Try again</button>
      </section>
    );
  }

  const runnableStages = plan.stages
    .filter((stage) => stage.href.trim().length > 0)
    .sort((left, right) => left.order - right.order);
  const firstStage = runnableStages[0] ?? null;
  const guidedRemediation = plan.guidedRemediation?.href.trim() ? plan.guidedRemediation : null;
  const isResume = recommendation.kind === "resume";
  const fallbackKind = recommendation.kind === "baseline" || recommendation.kind === "general"
    ? recommendation.kind
    : null;
  const actionHref = recommendation.href!;
  const followUpStages = isResume || fallbackKind === "general" || guidedRemediation ? runnableStages : runnableStages.slice(1);
  const morePriorities = (fallbackKind === "baseline" ? [] : plan.priorities).filter((priority) => (
    !plan.primary || priority.objectiveId !== plan.primary.objectiveId || priority.subskill !== plan.primary.subskill
  )).slice(0, 5);
  const recommendationReason = isResume
    ? "Finish your saved session first so you can keep your momentum without juggling two activities."
    : fallbackKind === "baseline"
      ? "A short starting check gives Luna enough information to choose practice that fits you."
      : fallbackKind === "general"
        ? "Luna needs a little more practice history before choosing a skill-specific step."
        : recommendation.kind === "guided"
          ? "A guided review gives you extra support on the skill that needs the most attention."
          : plan.primary
            ? priorityCopy(plan.primary)
            : "This step keeps your practice moving while Luna learns what helps you most.";
  const learnerDescription = isResume
    ? recommendation.detail
    : fallbackKind === "baseline"
      ? "This short, untimed check helps Luna learn what you already know and choose what to study next."
      : fallbackKind === "general"
        ? "Try a short untimed set while Luna gets your personalized plan ready."
        : recommendation.kind === "guided" && guidedRemediation
          ? `Review ${conceptLabel(guidedRemediation.concept)} with support, then try a fresh ECG on your own.`
          : firstStage
            ? `Practice ${conceptLabel(firstStage.receiptConcept)} across ${firstStage.suggestedLength} ECG${firstStage.suggestedLength === 1 ? "" : "s"}.`
            : recommendation.detail;
  const nextRoadmap = isResume && recommendation.after
    ? recommendation.after
    : followUpStages[0]
      ? {
          title: `${conceptLabel(followUpStages[0].receiptConcept)}: ${subskillLabel(followUpStages[0].receiptSubskill)}`,
          href: followUpStages[0].href,
        }
      : null;
  const applyRoadmap = fallbackKind === "baseline"
    ? null
    : plan.clinicalApplication
    ? { title: `Apply ${conceptLabel(plan.clinicalApplication.concept)} in a patient case`, href: plan.clinicalApplication.href, label: "Patient case" }
    : plan.integration
      ? { title: "Bring it into a full ECG read", href: plan.integration.href, label: "Full read" }
      : null;

  return (
    <div className={styles.plan} data-primary-mode={isResume ? "resume" : fallbackKind ?? (guidedRemediation ? "guided" : firstStage?.mode ?? "none")}>
      <section className={styles.coachCard} aria-labelledby="coach-recommendation-title">
        <div className={styles.coachLead}>
          <span className={styles.coachIdentity}><Sparkles size={16} aria-hidden="true" /> Luna · your study coach</span>
          <p className={styles.focusLabel}>Your next step</p>
          <h2 id="coach-recommendation-title">{recommendation.title}</h2>
          <p className={styles.description}>{learnerDescription}</p>

          {isResume && recommendation.resume ? (
            <div className={styles.taskMeta} aria-label="Saved activity details">
              <span>Saved {recommendation.resume.mode === "training" ? "focused practice" : recommendation.resume.mode}</span>
              <span>{recommendation.resume.completed} of {recommendation.resume.total} complete</span>
            </div>
          ) : recommendation.kind === "guided" && guidedRemediation ? (
            <div className={styles.taskMeta} aria-label="Recommended guided review details">
              <span>Guided review</span><span>One short lesson</span>
            </div>
          ) : !fallbackKind && firstStage ? (
            <div className={styles.taskMeta} aria-label="Recommended practice details">
              <span>{firstStage.suggestedLength} ECG{firstStage.suggestedLength === 1 ? "" : "s"}</span>
              <span>{subskillLabel(firstStage.receiptSubskill)}</span>
              <span>{modeLabel(firstStage.mode)}</span>
            </div>
          ) : (
            <div className={styles.taskMeta} aria-label="General practice details">
              <span>5 ECGs</span><span>Untimed</span><span>{fallbackKind === "baseline" ? "Starting check" : "General practice"}</span>
            </div>
          )}

          <div className={styles.primaryActions}>
            <Link className={`button primary ${styles.primaryCta}`} href={actionHref} data-testid="recommended-action">
              {recommendation.cta} <ArrowRight size={16} aria-hidden="true" />
            </Link>
            {plan.calendarAction ? (
              <button className="button subtle" type="button" onClick={onSchedulePlan}>
                <CalendarDays size={16} aria-hidden="true" /> {plan.calendarAction.relationship === "follow_up" || isResume ? "Add follow-up to week" : "Add to my week"}
              </button>
            ) : null}
          </div>
        </div>

        <aside className={styles.coachNote} aria-label="Luna's explanation">
          <span>Why this next?</span>
          <p>{recommendationReason}</p>
          <button type="button" disabled={!plan.coachContext} onClick={() => onOpenCoach(isResume ? "What should I study after I finish my saved session?" : "Help me fit this next step into my week.")}>
            <MessageSquare size={16} aria-hidden="true" /> Plan with Luna
          </button>
          {!plan.coachContext ? <small>Luna will be available when your plan refreshes.</small> : null}
        </aside>
      </section>

      <section className={styles.roadmap} aria-labelledby="study-roadmap-heading">
        <header>
          <div><p>Your plan</p><h3 id="study-roadmap-heading">Now → Next → Apply</h3></div>
          <small>One clear step at a time</small>
        </header>
        <ol>
          <li data-step="now">
            <span>Now</span>
            <div><strong>{recommendation.title}</strong><small>{recommendation.cta}</small></div>
            <Link href={actionHref} aria-label={`Open now: ${recommendation.title}`}><ArrowRight size={16} aria-hidden="true" /></Link>
          </li>
          <li data-step="next">
            <span>Next</span>
            <div><strong>{nextRoadmap?.title ?? "Build from this result"}</strong><small>{nextRoadmap ? "Your follow-up" : "Luna will choose after you finish"}</small></div>
            {nextRoadmap ? <Link href={nextRoadmap.href} aria-label={`Open next: ${nextRoadmap.title}`}><ArrowRight size={16} aria-hidden="true" /></Link> : <i aria-hidden="true" />}
          </li>
          <li data-step="apply">
            <span>Apply</span>
            <div><strong>{applyRoadmap?.title ?? "Use the skill in a complete read"}</strong><small>{applyRoadmap?.label ?? "Unlocked as your plan develops"}</small></div>
            {applyRoadmap ? <Link href={applyRoadmap.href} aria-label={`Open apply step: ${applyRoadmap.title}`}><ArrowRight size={16} aria-hidden="true" /></Link> : <i aria-hidden="true" />}
          </li>
        </ol>
      </section>

      <section className={styles.details} aria-label="More from your study plan">
        <details>
          <summary><span><ListChecks size={18} aria-hidden="true" /></span><span><strong>{isResume ? "Why continue first" : "Why this next?"}</strong><small>See what Luna is responding to.</small></span><ChevronDown size={18} aria-hidden="true" /></summary>
          <div className={styles.detailBody}>
            <p>{recommendationReason}</p>
            {isResume && recommendation.after ? (
              <Link className="button subtle" href={recommendation.after.href}>Then: {recommendation.after.title} <ArrowRight size={15} aria-hidden="true" /></Link>
            ) : (
              <div className={styles.signalGrid}>
                <span><strong>{plan.basis.independentCompetencyObservations ?? plan.basis.independentAttempts}</strong> skill checks</span>
                <span><strong>{plan.basis.dueCompetencies}</strong> skills to revisit</span>
                <span><strong>{plan.basis.highConfidenceMisses}</strong> skills to double-check</span>
              </div>
            )}
          </div>
        </details>

        {followUpStages.length ? (
          <details>
            <summary><span><ArrowRight size={18} aria-hidden="true" /></span><span><strong>What comes after this</strong><small>Preview later practice when you want it.</small></span><ChevronDown size={18} aria-hidden="true" /></summary>
            <div className={styles.detailBody}>
              <ol className={styles.stageList}>{followUpStages.map((stage) => (
                <li key={`${stage.order}-${stage.mode}`}><span>{stage.order}</span><div><strong>{conceptLabel(stage.receiptConcept)}</strong><small>{subskillLabel(stage.receiptSubskill)} · {modeLabel(stage.mode)}</small></div><Link href={stage.href}>Open <ArrowRight size={14} aria-hidden="true" /></Link></li>
              ))}</ol>
            </div>
          </details>
        ) : null}

        {fallbackKind !== "baseline" && plan.integration ? (
          <details>
            <summary><span><GitBranch size={18} aria-hidden="true" /></span><span><strong>Connect it to a full ECG read</strong><small>Put the skill back into the whole interpretation.</small></span><ChevronDown size={18} aria-hidden="true" /></summary>
            <div className={`${styles.detailBody} ${styles.linkedDetail}`}><p>Practice a complete ECG read that connects {conceptLabel(plan.integration.primaryConcept)} with {conceptLabel(plan.integration.secondaryConcept)}.</p><Link className="button" href={plan.integration.href}>Practice the full read <ArrowRight size={15} aria-hidden="true" /></Link></div>
          </details>
        ) : null}

        {fallbackKind !== "baseline" && plan.clinicalApplication ? (
          <details>
            <summary><span><Stethoscope size={18} aria-hidden="true" /></span><span><strong>Apply it in a patient case</strong><small>Use the pattern in context.</small></span><ChevronDown size={18} aria-hidden="true" /></summary>
            <div className={`${styles.detailBody} ${styles.linkedDetail}`}><p>Use this ECG finding in a patient case. Case work helps Luna choose later practice; scored ECG checks update your progress.</p><Link className="button" href={plan.clinicalApplication.href}>Open clinical case <ArrowRight size={15} aria-hidden="true" /></Link></div>
          </details>
        ) : null}

        {morePriorities.length ? (
          <details>
            <summary><span><ListChecks size={18} aria-hidden="true" /></span><span><strong>Other skills to revisit</strong><small>Keep them nearby without crowding today.</small></span><ChevronDown size={18} aria-hidden="true" /></summary>
            <div className={styles.detailBody}><ul className={styles.priorityList}>{morePriorities.map((priority) => (
              <li key={`${priority.caseConcept}:${priority.subskill}`}><div><strong>{conceptLabel(priority.objectiveId)}</strong><span>{subskillLabel(priority.subskill)}</span></div><p>{priorityCopy(priority)}</p></li>
            ))}</ul></div>
          </details>
        ) : null}
      </section>
    </div>
  );
}
