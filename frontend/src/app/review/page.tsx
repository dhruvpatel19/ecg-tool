"use client";

import {
  ArrowRight,
  Brain,
  BrainCircuit,
  CalendarClock,
  CheckCircle2,
  CircleAlert,
  GitBranch,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Stethoscope,
  TimerReset,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { TutorChat } from "@/components/TutorChat";
import { api, type AdaptivePlan } from "@/lib/api";

const modeIcon = {
  train: BrainCircuit,
  rapid: TimerReset,
  clinical: Stethoscope,
};

export default function ReviewPage() {
  const [plan, setPlan] = useState<AdaptivePlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const coachContext = useMemo(() => plan ? {
    activity: "adaptive_mastery_plan",
    authority: "verified_scheduler_only",
    generatedAt: plan.generatedAt,
    explanation: plan.explanation,
    basis: plan.basis,
    primary: plan.primary ? {
      concept: plan.primary.caseConcept,
      label: plan.primary.label,
      subskill: plan.primary.subskill,
      reason: plan.primary.reason,
      eligibleDistinct: plan.primary.eligibleDistinct,
      independentAttempts: plan.primary.independentAttempts,
      independentMastery: plan.primary.independentMastery,
      dueState: plan.primary.dueState,
    } : null,
    priorities: plan.priorities.map((priority) => ({
      concept: priority.caseConcept,
      label: priority.label,
      subskill: priority.subskill,
      reason: priority.reason,
    })),
    prescribedStages: plan.stages.map((stage) => ({
      order: stage.order,
      mode: stage.mode,
      title: stage.title,
      purpose: stage.purpose,
      suggestedLength: stage.suggestedLength,
      receiptConcept: stage.receiptConcept,
      receiptSubskill: stage.receiptSubskill,
    })),
    integrationPrompt: plan.integration?.prompt ?? null,
    constraints: [
      "Do not change or score the deterministic plan.",
      "Do not infer a diagnosis or mastery value not present here.",
      "Recommend only the listed verified destinations.",
    ],
  } : {}, [plan]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    api.adaptivePlan()
      .then((response) => { if (active) setPlan(response); })
      .catch(() => { if (active) setError("Your verified competency evidence could not be loaded. No replacement plan was invented."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [retry]);

  return (
    <div className="page mastery-coach-page">
      <header className="page-header mastery-coach-header">
        <div>
          <p className="eyebrow">Adaptive mastery coach</p>
          <h1><Brain size={24} aria-hidden="true" /> Your next evidence plan</h1>
          <p className="muted">A separate scheduler reads verified concept × subskill receipts, spacing, calibration errors, ECG diversity, and the currently eligible corpus. The conversational tutor does not choose or score this queue.</p>
        </div>
        <div className="mastery-audit-chip"><ShieldCheck size={16} /><span><strong>Evidence-led</strong><small>No guessed mastery</small></span></div>
      </header>

      {loading ? <section className="panel pad mastery-loading" role="status"><span className="status-orb" /><strong>Building your plan from verified evidence…</strong></section> : null}
      {error ? <div className="warning" role="alert">{error} <button className="button subtle small" type="button" onClick={() => setRetry((value) => value + 1)}><RefreshCw size={14} /> Retry</button></div> : null}

      {plan ? <>
        <section className={`panel pad mastery-primary${plan.basis.baselineNeeded ? " baseline" : ""}`}>
          <div className="mastery-primary-copy">
            <span className="hero-kicker"><Sparkles size={14} /> {plan.basis.baselineNeeded ? "Baseline first" : "Highest-priority competency"}</span>
            <h2>{plan.basis.baselineNeeded ? "Establish what you can do independently." : plan.primary ? `${plan.primary.label} · ${plan.primary.subskill.replaceAll("_", " ")}` : "No eligible target is available."}</h2>
            <p>{plan.primary?.reason ?? plan.explanation}</p>
            <p className="muted mastery-explanation">{plan.explanation}</p>
          </div>
          <div className="mastery-basis" aria-label="Evidence used by the adaptive plan">
            <span><strong>{plan.basis.independentAttempts}</strong> independent receipts</span>
            <span><strong>{plan.basis.dueCompetencies}</strong> due now</span>
            <span><strong>{plan.basis.highConfidenceMisses}</strong> calibration flags</span>
            <span><strong>{plan.basis.eligibleConcepts}</strong> eligible concepts</span>
          </div>
        </section>

        <section className="mastery-section">
          <div className="section-heading-row">
            <div><p className="eyebrow">Executable evidence path</p><h2>Open the task that can close this exact gap.</h2></div>
            <p>Every listed destination has a server grader for the named receipt. Unsupported application work stays out of this mastery queue until its review ceiling changes.</p>
          </div>
          <div className="mastery-stage-grid">
            {plan.stages.map((stage) => {
              const Icon = modeIcon[stage.mode];
              return <article className={`panel mastery-stage stage-${stage.mode}`} key={`${stage.order}-${stage.mode}`}>
                <div className="mastery-stage-number">{String(stage.order).padStart(2, "0")}</div>
                <div className="mastery-stage-icon"><Icon size={19} /></div>
                <p className="eyebrow">{stage.mode} · {stage.suggestedLength} ECG{stage.suggestedLength === 1 ? "" : "s"}</p>
                <h3>{stage.title}</h3>
                <p>{stage.purpose}</p>
                <p className="selection-note"><strong>Receipt:</strong> {stage.receiptConcept.replaceAll("_", " ")} · {stage.receiptSubskill.replaceAll("_", " ")} · independent transfer</p>
                <Link className="button primary" href={stage.href}>Open {stage.mode} <ArrowRight size={15} /></Link>
              </article>;
            })}
          </div>
        </section>

        <section className="mastery-section">
          <div className="section-heading-row">
            <div><p className="eyebrow">Ask about your plan</p><h2>Reason with the mastery coach.</h2></div>
            <p>The coach can explain the verified queue and help you compare study strategies. It cannot award credit, change the schedule, or invent a case.</p>
          </div>
          <TutorChat
            mode="freeform"
            roleLabel="Plan coach · receipt-grounded"
            lessonId={`adaptive-plan:${plan.primary?.caseConcept ?? "baseline"}:${plan.primary?.subskill ?? "mixed"}`}
            openingPrompt="Ask why this target comes first, how the stages connect, or what evidence would move it toward durable recall."
            viewerState={coachContext}
          />
        </section>

        {plan.integration ? <section className="panel pad mastery-integration">
          <div className="mastery-integration-icon"><GitBranch size={21} /></div>
          <div><p className="eyebrow">Cross-concept integration</p><h2>Do not let an isolated finding replace the full read.</h2><p>{plan.integration.prompt}</p></div>
          <Link className="button" href={plan.integration.href}>Run integration read <ArrowRight size={15} /></Link>
        </section> : null}

        <section className="mastery-section">
          <div className="section-heading-row">
            <div><p className="eyebrow">Why these targets</p><h2>Priority queue</h2></div>
            <Link className="button subtle" href="/profile">Inspect every objective <ArrowRight size={14} /></Link>
          </div>
          <div className="mastery-priority-list">
            {plan.priorities.map((priority, index) => <article className="panel mastery-priority" key={`${priority.caseConcept}:${priority.subskill}`}>
              <span className="mastery-priority-rank">{index + 1}</span>
              <div>
                <div className="mastery-priority-title"><strong>{priority.label}</strong><span>{priority.subskill.replaceAll("_", " ")}</span>{priority.isDue ? <span className="due"><CalendarClock size={13} /> {priority.dueState}</span> : null}</div>
                <p>{priority.reason}</p>
                <small>{priority.eligibleDistinct.toLocaleString()} eligible ECGs · {priority.distinctSuccessfulEcgs} successful distinct ECGs · {priority.independentAttempts} independent attempts</small>
              </div>
              {priority.highConfidenceWrong ? <CircleAlert className="priority-alert" size={18} aria-label="High-confidence error priority" /> : <CheckCircle2 className="priority-ok" size={18} aria-hidden="true" />}
            </article>)}
          </div>
        </section>
      </> : null}
    </div>
  );
}
