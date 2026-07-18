"use client";

import {
  Activity,
  ArrowRight,
  BookOpenCheck,
  Building2,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  Clock3,
  HeartPulse,
  ListChecks,
  MessageSquareText,
  ShieldCheck,
  Sparkles,
  Star,
  Stethoscope,
  Target,
  UserRound,
} from "lucide-react";
import Link from "next/link";
import { useId, type ReactNode } from "react";
import type { ClinicalGrade, Lane, Mode, ShiftReport } from "@/lib/clinical";
import styles from "./ClinicalExperience.module.css";

export type ClinicalExperienceAction = {
  label: string;
  ariaLabel?: string;
  href?: string;
  onClick?: () => void;
  disabled?: boolean;
  icon?: ReactNode;
  tone?: "primary" | "secondary" | "quiet";
};

function actionClass(tone: ClinicalExperienceAction["tone"] = "secondary") {
  if (tone === "primary") return `${styles.action} ${styles.actionPrimary}`;
  if (tone === "quiet") return `${styles.action} ${styles.actionQuiet}`;
  return `${styles.action} ${styles.actionSecondary}`;
}

export function ClinicalActionControl({ action }: { action: ClinicalExperienceAction }) {
  const content = (
    <>
      {action.icon}
      <span>{action.label}</span>
    </>
  );
  const className = actionClass(action.tone);

  if (action.href && !action.disabled) {
    return <Link className={className} href={action.href} aria-label={action.ariaLabel}>{content}</Link>;
  }
  if (action.href && action.disabled) {
    return <span className={className} aria-disabled="true">{content}</span>;
  }
  return (
    <button
      className={className}
      type="button"
      aria-label={action.ariaLabel}
      onClick={action.onClick}
      disabled={action.disabled}
    >
      {content}
    </button>
  );
}

export type ClinicalSettingOption = {
  value: Lane;
  title: string;
  description: string;
  disabled?: boolean;
  disabledReason?: string;
};

export type ClinicalModeOption = {
  value: Mode;
  title: string;
  description: string;
};

const DEFAULT_SETTINGS: readonly ClinicalSettingOption[] = [
  {
    value: "clinic",
    title: "Outpatient clinic",
    description: "Ambulatory patients with common but important presentations.",
  },
  {
    value: "ward",
    title: "Inpatient ward",
    description: "Patients whose symptoms, monitoring, or treatment are evolving.",
  },
  {
    value: "ed",
    title: "Emergency care",
    description: "Time-sensitive cases from emergency and acute care settings.",
  },
];

const DEFAULT_MODES: readonly ClinicalModeOption[] = [
  {
    value: "learn",
    title: "Guided",
    description: "Work at your pace with structured review after each decision.",
  },
  {
    value: "shift",
    title: "On shift",
    description: "Make time-aware decisions with less guidance during the case.",
  },
];

function settingIcon(lane: Lane) {
  if (lane === "clinic") return <Stethoscope size={28} aria-hidden="true" />;
  if (lane === "ward") return <Building2 size={28} aria-hidden="true" />;
  return <Activity size={28} aria-hidden="true" />;
}

function modeIcon(mode: Mode) {
  return mode === "learn"
    ? <MessageSquareText size={25} aria-hidden="true" />
    : <UserRound size={25} aria-hidden="true" />;
}

function learnerFacingLane(lane: Lane) {
  return DEFAULT_SETTINGS.find((option) => option.value === lane)?.title ?? "Clinical setting";
}

function learnerFacingMode(mode: Mode) {
  return mode === "learn" ? "Guided" : "On shift";
}

export type ClinicalSetupHeroProps = {
  eyebrow?: string;
  title?: string;
  description?: string;
  action?: ClinicalExperienceAction;
};

export function ClinicalSetupHero({
  eyebrow = "Clinical cases",
  title = "Practice decisions in realistic patient care",
  description = "Manage evolving patients, interpret their ECGs, and connect each finding to the next clinical decision.",
  action,
}: ClinicalSetupHeroProps) {
  return (
    <header className={styles.setupHero}>
      <div>
        <p className={styles.eyebrow}>{eyebrow}</p>
        <h1>{title}</h1>
        <p className={styles.heroDescription}>{description}</p>
      </div>
      {action ? <ClinicalActionControl action={action} /> : null}
    </header>
  );
}

export type ClinicalSettingCardsProps = {
  value: Lane;
  onChange: (lane: Lane) => void;
  options?: readonly ClinicalSettingOption[];
  legend?: string;
};

export function ClinicalSettingCards({
  value,
  onChange,
  options = DEFAULT_SETTINGS,
  legend = "Choose your practice setting",
}: ClinicalSettingCardsProps) {
  return (
    <fieldset className={styles.choiceFieldset}>
      <legend>{legend}</legend>
      <div className={styles.settingGrid}>
        {options.map((option) => {
          const selected = option.value === value;
          return (
            <button
              className={styles.settingCard}
              data-selected={selected || undefined}
              key={option.value}
              type="button"
              aria-pressed={selected}
              disabled={option.disabled}
              onClick={() => onChange(option.value)}
            >
              <span className={styles.settingIcon}>{settingIcon(option.value)}</span>
              <strong>{option.title}</strong>
              <span>{option.description}</span>
              {option.disabledReason ? <small>{option.disabledReason}</small> : null}
              {selected ? <span className={styles.selectedMark}><Check size={14} aria-hidden="true" /><span className={styles.srOnly}>Selected</span></span> : null}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

export type ClinicalModeCardsProps = {
  value: Mode;
  onChange: (mode: Mode) => void;
  options?: readonly ClinicalModeOption[];
  legend?: string;
};

export function ClinicalModeCards({
  value,
  onChange,
  options = DEFAULT_MODES,
  legend = "Choose your learning mode",
}: ClinicalModeCardsProps) {
  return (
    <fieldset className={styles.choiceFieldset}>
      <legend>{legend}</legend>
      <div className={styles.modeGrid}>
        {options.map((option) => {
          const selected = option.value === value;
          return (
            <button
              className={styles.modeCard}
              data-selected={selected || undefined}
              key={option.value}
              type="button"
              aria-pressed={selected}
              onClick={() => onChange(option.value)}
            >
              <span className={styles.modeIcon}>{modeIcon(option.value)}</span>
              <span className={styles.modeCopy}>
                <strong>{option.title}</strong>
                <small>{option.description}</small>
              </span>
              {selected ? <CheckCircle2 className={styles.modeCheck} size={18} aria-hidden="true" /> : null}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

export type ClinicalLengthSelectorProps = {
  value: number;
  onChange: (length: number) => void;
  options?: readonly number[];
  legend?: string;
  description?: string;
};

export function ClinicalLengthSelector({
  value,
  onChange,
  options = [5, 10],
  legend = "Set length",
  description = "Choose a focused set now; you can start another whenever you are ready.",
}: ClinicalLengthSelectorProps) {
  return (
    <fieldset className={`${styles.choiceFieldset} ${styles.lengthFieldset}`}>
      <legend>{legend}</legend>
      <p className={styles.fieldsetDescription}>{description}</p>
      <div className={styles.lengthChoices}>
        {options.map((option) => (
          <button
            className={styles.lengthChoice}
            data-selected={option === value || undefined}
            key={option}
            type="button"
            aria-pressed={option === value}
            onClick={() => onChange(option)}
          >
            {option} patient cases
          </button>
        ))}
      </div>
    </fieldset>
  );
}

function RecommendationPulse() {
  return (
    <svg className={styles.recommendationPulse} viewBox="0 0 320 96" role="presentation" aria-hidden="true">
      <path d="M0 52 L45 52 L55 45 L65 52 L87 52 L96 18 L108 80 L121 52 L160 52 L171 43 L181 52 L202 52 L211 27 L221 71 L233 52 L270 52 L281 47 L291 52 L320 52" />
    </svg>
  );
}

export type ClinicalRecommendationCardProps = {
  title?: string;
  body: string;
  focusLabel?: string;
  reason?: string;
  visual?: ReactNode;
  action?: ClinicalExperienceAction;
};

export function ClinicalRecommendationCard({
  title = "Recommended for you",
  body,
  focusLabel,
  reason,
  visual,
  action,
}: ClinicalRecommendationCardProps) {
  const headingId = useId();
  return (
    <section className={styles.recommendationCard} aria-labelledby={headingId}>
      <div className={styles.recommendationCopy}>
        <div className={styles.recommendationHeading}>
          <Star size={19} fill="currentColor" aria-hidden="true" />
          <h2 id={headingId}>{title}</h2>
        </div>
        <p>{body}</p>
        {reason ? <small>{reason}</small> : null}
        {focusLabel ? <span className={styles.focusPill}>Focus: {focusLabel}</span> : null}
        {action ? <ClinicalActionControl action={action} /> : null}
      </div>
      <div className={styles.recommendationVisual}>{visual ?? <RecommendationPulse />}</div>
    </section>
  );
}

export type ClinicalLaunchSummaryProps = {
  lane: Lane;
  mode: Mode;
  length: number;
  detail?: string;
};

export function ClinicalLaunchSummary({ lane, mode, length, detail }: ClinicalLaunchSummaryProps) {
  return (
    <div className={styles.launchSummary} aria-label="Selected learning set">
      <ListChecks size={18} aria-hidden="true" />
      <div>
        <strong>{learnerFacingLane(lane)} · {learnerFacingMode(mode)} · {length} cases</strong>
        <span>{detail ?? "Cases are varied so you can practice transferring the same reasoning across different patients."}</span>
      </div>
    </div>
  );
}

export type ClinicalSetupExperienceProps = {
  lane: Lane;
  onLaneChange: (lane: Lane) => void;
  mode: Mode;
  onModeChange: (mode: Mode) => void;
  length: number;
  onLengthChange: (length: number) => void;
  onStart: () => void;
  busy?: boolean;
  disabled?: boolean;
  startLabel?: string;
  busyLabel?: string;
  hero?: ClinicalSetupHeroProps;
  settingOptions?: readonly ClinicalSettingOption[];
  modeOptions?: readonly ClinicalModeOption[];
  lengthOptions?: readonly number[];
  recommendation?: ClinicalRecommendationCardProps;
  launchDetail?: string;
  notices?: ReactNode;
  footer?: ReactNode;
};

export function ClinicalSetupExperience({
  lane,
  onLaneChange,
  mode,
  onModeChange,
  length,
  onLengthChange,
  onStart,
  busy = false,
  disabled = false,
  startLabel,
  busyLabel = "Preparing your cases…",
  hero,
  settingOptions,
  modeOptions,
  lengthOptions,
  recommendation,
  launchDetail,
  notices,
  footer,
}: ClinicalSetupExperienceProps) {
  return (
    <div className={styles.setupExperience}>
      <ClinicalSetupHero {...hero} />
      {notices ? <div className={styles.noticeStack}>{notices}</div> : null}
      <div className={styles.setupPanel}>
        <ClinicalSettingCards value={lane} onChange={onLaneChange} options={settingOptions} />
        <ClinicalModeCards value={mode} onChange={onModeChange} options={modeOptions} />
        <ClinicalLengthSelector value={length} onChange={onLengthChange} options={lengthOptions} />
        {recommendation ? <ClinicalRecommendationCard {...recommendation} /> : null}
        <ClinicalLaunchSummary lane={lane} mode={mode} length={length} detail={launchDetail} />
        <button className={styles.launchButton} type="button" onClick={onStart} disabled={disabled || busy}>
          <span>{busy ? busyLabel : startLabel ?? (mode === "learn" ? "Begin learning set" : "Start shift")}</span>
          <ArrowRight size={18} aria-hidden="true" />
        </button>
        {footer ? <div className={styles.setupFooter}>{footer}</div> : null}
      </div>
    </div>
  );
}

export type ClinicalJourneyStageId = "presentation" | "ecg" | "decision" | "reassessment" | "handoff";
export type ClinicalJourneyStage = {
  id: ClinicalJourneyStageId;
  label: string;
  status: "complete" | "current" | "upcoming";
  detail?: string;
};

const JOURNEY_LABELS: ReadonlyArray<{ id: ClinicalJourneyStageId; label: string }> = [
  { id: "presentation", label: "Presentation" },
  { id: "ecg", label: "ECG" },
  { id: "decision", label: "Decision" },
  { id: "reassessment", label: "Reassessment" },
  { id: "handoff", label: "Handoff" },
];

export function buildClinicalJourney(activeStage: ClinicalJourneyStageId): ClinicalJourneyStage[] {
  const activeIndex = JOURNEY_LABELS.findIndex((stage) => stage.id === activeStage);
  return JOURNEY_LABELS.map((stage, index) => ({
    ...stage,
    status: index < activeIndex ? "complete" : index === activeIndex ? "current" : "upcoming",
  }));
}

export function ClinicalJourneyProgress({
  stages,
  label = "Patient journey",
}: {
  stages: readonly ClinicalJourneyStage[];
  label?: string;
}) {
  return (
    <nav className={styles.journey} aria-label={label} tabIndex={0}>
      <ol>
        {stages.map((stage) => (
          <li data-status={stage.status} key={stage.id} aria-current={stage.status === "current" ? "step" : undefined}>
            <span className={styles.journeyMarker} aria-hidden="true">
              {stage.status === "complete" ? <Check size={13} /> : null}
            </span>
            <span className={styles.journeyCopy}>
              <strong>{stage.label}</strong>
              {stage.detail ? <small>{stage.detail}</small> : null}
            </span>
            <span className={styles.srOnly}>{stage.status === "complete" ? "Completed" : stage.status === "current" ? "Current stage" : "Upcoming"}</span>
          </li>
        ))}
      </ol>
    </nav>
  );
}

export type ClinicalCaseProgressHeaderProps = {
  caseNumber: number;
  totalCases: number;
  lane: Lane;
  mode: Mode;
  stages: readonly ClinicalJourneyStage[];
  statusLabel?: string;
  timingLabel?: string;
  exitAction?: ClinicalExperienceAction;
  leadingAction?: ReactNode;
  trailingActions?: ReactNode;
};

export function ClinicalCaseProgressHeader({
  caseNumber,
  totalCases,
  lane,
  mode,
  stages,
  statusLabel,
  timingLabel,
  exitAction,
  leadingAction,
  trailingActions,
}: ClinicalCaseProgressHeaderProps) {
  return (
    <header className={styles.caseProgressHeader}>
      <div className={styles.caseProgressTopline}>
        <div className={styles.caseIdentity}>
          {leadingAction}
          <strong>Case {caseNumber} of {totalCases}</strong>
          <span aria-hidden="true" />
          <span><Building2 size={15} aria-hidden="true" /> {learnerFacingLane(lane)}</span>
        </div>
        <div className={styles.caseHeaderActions}>
          <span className={styles.caseStatus}><Clock3 size={14} aria-hidden="true" /> {statusLabel ?? timingLabel ?? (mode === "learn" ? "Untimed · Guided" : "On shift")}</span>
          {trailingActions}
          {exitAction ? <ClinicalActionControl action={{ ...exitAction, tone: exitAction.tone ?? "quiet" }} /> : null}
        </div>
      </div>
      <ClinicalJourneyProgress stages={stages} />
    </header>
  );
}

export type ClinicalVital = { label: string; value: string };
export type ClinicalPatientDetail = { label: string; value: string };

export type ClinicalPatientSnapshotProps = {
  patientLabel: string;
  reasonForEcg: string;
  history?: string;
  vitals?: readonly ClinicalVital[];
  details?: readonly ClinicalPatientDetail[];
  heading?: string;
  eyebrow?: string;
  action?: ReactNode;
};

export function ClinicalPatientSnapshot({
  patientLabel,
  reasonForEcg,
  history,
  vitals = [],
  details = [],
  heading = "Patient snapshot",
  eyebrow = "Before you interpret",
  action,
}: ClinicalPatientSnapshotProps) {
  const headingId = useId();
  return (
    <section className={styles.patientSnapshot} aria-labelledby={headingId}>
      <header className={styles.snapshotHeading}>
        <div>
          <p className={styles.eyebrow}>{eyebrow}</p>
          <h2 id={headingId}>{heading}</h2>
        </div>
        {action}
      </header>
      <div className={styles.snapshotGrid}>
        <div className={styles.patientIdentity}>
          <span className={styles.patientAvatar}><UserRound size={23} aria-hidden="true" /></span>
          <div>
            <strong>{patientLabel}</strong>
            <span>Reason for ECG</span>
            <p>{reasonForEcg}</p>
          </div>
        </div>
        {history ? (
          <div className={styles.snapshotSection}>
            <span>History of present illness</span>
            <p>{history}</p>
          </div>
        ) : null}
        {vitals.length ? (
          <div className={styles.snapshotSection}>
            <span>Vital signs</span>
            <dl className={styles.vitalsList}>
              {vitals.map((vital, index) => <div key={`${vital.label}-${index}`}><dt>{vital.label}</dt><dd>{vital.value}</dd></div>)}
            </dl>
          </div>
        ) : null}
        {details.length ? (
          <dl className={styles.snapshotDetails}>
            {details.map((detail, index) => <div key={`${detail.label}-${index}`}><dt>{detail.label}</dt><dd>{detail.value}</dd></div>)}
          </dl>
        ) : null}
      </div>
    </section>
  );
}

export type ClinicalReviewTone = "correct" | "developing" | "safety";
export type ClinicalAlternativeReview = {
  label: string;
  explanation: string;
};
export type ClinicalEvidenceStep = {
  id: string;
  title: string;
  description: string;
  timestamp?: string;
  status?: "complete" | "current" | "upcoming";
};

function reviewToneIcon(tone: ClinicalReviewTone) {
  if (tone === "correct") return <CheckCircle2 size={20} aria-hidden="true" />;
  if (tone === "safety") return <CircleAlert size={20} aria-hidden="true" />;
  return <Activity size={20} aria-hidden="true" />;
}

export type ClinicalAnswerReviewCardProps = {
  tone: ClinicalReviewTone;
  statusLabel: string;
  learnerAnswer: ReactNode;
  recommendedAnswer: ReactNode;
  rationale: ReactNode;
  supportingEvidence?: readonly string[];
  alternatives?: readonly ClinicalAlternativeReview[];
  safetyFlags?: ClinicalGrade["safetyFlags"];
};

export function ClinicalAnswerReviewCard({
  tone,
  statusLabel,
  learnerAnswer,
  recommendedAnswer,
  rationale,
  supportingEvidence = [],
  alternatives = [],
  safetyFlags = [],
}: ClinicalAnswerReviewCardProps) {
  return (
    <section className={styles.answerReviewCard} data-tone={tone} aria-label="Decision review">
      <div className={styles.reviewOutcome}>{reviewToneIcon(tone)}<strong>{statusLabel}</strong></div>
      <dl className={styles.answerComparison}>
        <div><dt>Your answer</dt><dd>{learnerAnswer}</dd></div>
        <div className={styles.recommendedAnswer}><dt>Best-supported answer</dt><dd>{recommendedAnswer}</dd></div>
      </dl>
      <div className={styles.reviewRationale}>
        <h3>Why it fits</h3>
        <div>{rationale}</div>
        {supportingEvidence.length ? <ul>{supportingEvidence.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul> : null}
      </div>
      {alternatives.length ? (
        <div className={styles.alternativeReview}>
          <h3>Why the closest alternatives do not fit</h3>
          {alternatives.map((alternative, index) => (
            <article key={`${alternative.label}-${index}`}>
              <strong>{alternative.label}</strong>
              <p>{alternative.explanation}</p>
            </article>
          ))}
        </div>
      ) : null}
      {safetyFlags.length ? (
        <div className={styles.safetyCorrection} role="note">
          <ShieldCheck size={17} aria-hidden="true" />
          <div><strong>Safety correction</strong><p>{safetyFlags.join(" · ")}</p></div>
        </div>
      ) : null}
    </section>
  );
}

export function ClinicalEvidenceTimeline({
  steps,
  heading = "Explanation timeline",
}: {
  steps: readonly ClinicalEvidenceStep[];
  heading?: string;
}) {
  const headingId = useId();
  return (
    <section className={styles.evidenceTimeline} aria-labelledby={headingId}>
      <h3 id={headingId}>{heading}</h3>
      <ol>
        {steps.map((step, index) => (
          <li data-status={step.status ?? "complete"} key={step.id}>
            <span className={styles.timelineMarker}>{step.status === "complete" ? <Check size={12} aria-hidden="true" /> : index + 1}</span>
            <div><strong>{step.title}</strong><p>{step.description}</p></div>
            {step.timestamp ? <time>{step.timestamp}</time> : null}
          </li>
        ))}
      </ol>
    </section>
  );
}

export type ClinicalImmediateReviewProps = ClinicalAnswerReviewCardProps & {
  title?: string;
  eyebrow?: string;
  ecgReview?: ReactNode;
  evidenceTimeline?: readonly ClinicalEvidenceStep[];
  teachingPoints?: ClinicalGrade["teachingPoints"];
  coaching?: ReactNode;
  transferCheck?: ReactNode;
  notices?: ReactNode;
  actions?: ReactNode;
};

export function ClinicalImmediateReview({
  title = "Review your decision",
  eyebrow = "Case review",
  ecgReview,
  evidenceTimeline = [],
  teachingPoints = [],
  coaching,
  transferCheck,
  notices,
  actions,
  ...answerReview
}: ClinicalImmediateReviewProps) {
  return (
    <div className={styles.immediateReview}>
      <header className={styles.reviewHeader}>
        <div><p className={styles.eyebrow}>{eyebrow}</p><h2>{title}</h2></div>
        {actions}
      </header>
      {notices ? <div className={styles.noticeStack}>{notices}</div> : null}
      <div className={styles.immediateReviewGrid} data-has-ecg={Boolean(ecgReview) || undefined}>
        {ecgReview ? (
          <div className={styles.ecgReviewColumn}>
            <section className={styles.ecgReviewFrame} aria-label="ECG with review evidence">{ecgReview}</section>
            {evidenceTimeline.length ? <ClinicalEvidenceTimeline steps={evidenceTimeline} /> : null}
          </div>
        ) : null}
        <ClinicalAnswerReviewCard {...answerReview} />
      </div>
      {(coaching || transferCheck || teachingPoints.length) ? (
        <div className={styles.reviewLearningGrid}>
          {coaching ? <section className={styles.learningCard}><Sparkles size={18} aria-hidden="true" /><div><h3>Ask about this case</h3>{coaching}</div></section> : null}
          {transferCheck ? <section className={styles.learningCard}><Target size={18} aria-hidden="true" /><div><h3>Test the concept</h3>{transferCheck}</div></section> : null}
          {teachingPoints.length ? (
            <section className={styles.learningCard}>
              <BookOpenCheck size={18} aria-hidden="true" />
              <div><h3>Take forward</h3><ul>{teachingPoints.map((point, index) => <li key={`${point}-${index}`}>{point}</li>)}</ul></div>
            </section>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export type ClinicalSetReviewHeroProps = {
  report?: ShiftReport;
  eyebrow?: string;
  title?: string;
  summary?: string;
  supportingText?: string;
  action?: ClinicalExperienceAction;
};

export function ClinicalSetReviewHero({
  report,
  eyebrow = "Set review",
  title = "Your clinical reasoning review is ready",
  summary,
  supportingText,
  action,
}: ClinicalSetReviewHeroProps) {
  const decisionSummary = report
    ? `You completed ${report.answered} of ${report.length} patient cases with ${Math.round(report.accuracy * 100)}% decision accuracy.`
    : "Review the decisions you made, the ECG evidence that mattered, and the best next step for your learning.";
  return (
    <header className={styles.setReviewHero}>
      <div>
        <p className={styles.eyebrow}>{eyebrow}</p>
        <h1>{title}</h1>
        <p className={styles.setReviewSummary}>{summary ?? decisionSummary}</p>
        {supportingText ? <p className={styles.setReviewSupporting}>{supportingText}</p> : null}
      </div>
      {action ? <ClinicalActionControl action={action} /> : null}
    </header>
  );
}

export type ClinicalDomainSummaryItem = {
  id: string;
  label: string;
  value: string;
  detail?: string;
  tone?: "positive" | "neutral" | "attention";
  icon?: ReactNode;
};

export function buildClinicalDomainSummaries(report: ShiftReport): ClinicalDomainSummaryItem[] {
  const domains = report.performanceDomains;
  const decisionScore = domains?.clinicalApplicationDecision.score ?? report.accuracy;
  const firstLookScore = domains?.ecgRecognitionFirstLook.broadCategory.score;
  const topicCount = report.debrief?.conceptEvidence.length ?? 0;
  return [
    {
      id: "completed",
      label: "Cases completed",
      value: `${report.answered}/${report.length}`,
      detail: learnerFacingLane(report.lane),
      tone: "neutral",
    },
    {
      id: "decisions",
      label: "Clinical decisions",
      value: decisionScore == null ? "Not assessed" : `${Math.round(decisionScore * 100)}%`,
      detail: "Best-supported patient-care choices",
      tone: decisionScore != null && decisionScore < 0.7 ? "attention" : "positive",
    },
    {
      id: "safety",
      label: "Safe decisions",
      value: domains?.safety.assessed ? `${domains.safety.safe}/${domains.safety.assessed}` : "Not assessed",
      detail: domains?.safety.flagged ? `${domains.safety.flagged} decision${domains.safety.flagged === 1 ? "" : "s"} to revisit` : "No safety concerns recorded",
      tone: domains?.safety.flagged ? "attention" : "positive",
    },
    {
      id: "recognition",
      label: "ECG reasoning",
      value: firstLookScore == null ? "Not assessed" : `${Math.round(firstLookScore * 100)}%`,
      detail: topicCount ? `${topicCount} topic${topicCount === 1 ? "" : "s"} connected` : "Trace evidence before the clinical decision",
      tone: firstLookScore != null && firstLookScore < 0.7 ? "attention" : "neutral",
    },
  ];
}

function domainIcon(id: string) {
  if (id === "completed") return <ListChecks size={21} aria-hidden="true" />;
  if (id === "decisions") return <CheckCircle2 size={21} aria-hidden="true" />;
  if (id === "safety") return <ShieldCheck size={21} aria-hidden="true" />;
  if (id === "recognition") return <HeartPulse size={21} aria-hidden="true" />;
  return <Activity size={21} aria-hidden="true" />;
}

export function ClinicalDomainSummaryGrid({ items }: { items: readonly ClinicalDomainSummaryItem[] }) {
  return (
    <section className={styles.domainSummaryGrid} aria-label="Learning set summary">
      {items.map((item) => (
        <article data-tone={item.tone ?? "neutral"} key={item.id}>
          <span className={styles.domainIcon}>{item.icon ?? domainIcon(item.id)}</span>
          <div><span>{item.label}</span><strong>{item.value}</strong>{item.detail ? <small>{item.detail}</small> : null}</div>
        </article>
      ))}
    </section>
  );
}

export type ClinicalCaseReviewItem = {
  id: string;
  index: number;
  title: string;
  context?: string;
  tags?: readonly string[];
  outcome: "appropriate" | "developing" | "attention";
  outcomeLabel: string;
  preview?: ReactNode;
  href?: string;
  onSelect?: () => void;
  ariaLabel?: string;
};

function MiniTraceArtwork() {
  return (
    <svg className={styles.miniTrace} viewBox="0 0 120 58" role="presentation" aria-hidden="true">
      <path d="M0 31 L22 31 L27 27 L32 31 L43 31 L48 8 L54 51 L60 31 L82 31 L87 27 L92 31 L120 31" />
    </svg>
  );
}

function CaseReviewRowContent({ item }: { item: ClinicalCaseReviewItem }) {
  const positive = item.outcome === "appropriate";
  return (
    <>
      <span className={styles.caseReviewIndex}>{item.index}</span>
      <span className={styles.casePreview}>{item.preview ?? <MiniTraceArtwork />}</span>
      <span className={styles.caseReviewCopy}>
        <strong>{item.title}</strong>
        {item.context ? <small>{item.context}</small> : null}
        {item.tags?.length ? <span className={styles.caseTags}>{item.tags.map((tag, index) => <span key={`${tag}-${index}`}>{tag}</span>)}</span> : null}
      </span>
      <span className={styles.caseOutcome} data-tone={item.outcome}>
        {positive ? <CheckCircle2 size={18} aria-hidden="true" /> : <CircleAlert size={18} aria-hidden="true" />}
        <span>{item.outcomeLabel}</span>
      </span>
      {(item.href || item.onSelect) ? <ChevronRight size={18} aria-hidden="true" /> : null}
    </>
  );
}

function ClinicalCaseReviewRow({ item }: { item: ClinicalCaseReviewItem }) {
  const className = styles.caseReviewRow;
  if (item.href) {
    return <Link className={className} href={item.href} aria-label={item.ariaLabel ?? `Review case ${item.index}: ${item.title}`}><CaseReviewRowContent item={item} /></Link>;
  }
  if (item.onSelect) {
    return <button className={className} type="button" onClick={item.onSelect} aria-label={item.ariaLabel ?? `Review case ${item.index}: ${item.title}`}><CaseReviewRowContent item={item} /></button>;
  }
  return <div className={className}><CaseReviewRowContent item={item} /></div>;
}

export type ClinicalCaseReviewListProps = {
  items: readonly ClinicalCaseReviewItem[];
  heading?: string;
  description?: string;
  emptyMessage?: string;
  action?: ClinicalExperienceAction;
};

export function ClinicalCaseReviewList({
  items,
  heading = "Your cases",
  description = "Open any case to review the ECG, your decision, and the explanation.",
  emptyMessage = "There are no completed cases to review yet.",
  action,
}: ClinicalCaseReviewListProps) {
  const headingId = useId();
  return (
    <section className={styles.caseReviewList} aria-labelledby={headingId}>
      <header><div><p className={styles.eyebrow}>Review your work</p><h2 id={headingId}>{heading}</h2><p>{description}</p></div></header>
      {items.length ? <ol>{items.map((item) => <li key={item.id}><ClinicalCaseReviewRow item={item} /></li>)}</ol> : <p className={styles.emptyCases}>{emptyMessage}</p>}
      {action ? <ClinicalActionControl action={action} /> : null}
    </section>
  );
}

export type ClinicalNextStepTopic = {
  id: string;
  label: string;
  status: "priority" | "developing" | "strong";
  statusLabel: string;
  progress?: number;
  href?: string;
};

export type ClinicalPersonalizedNextStepsProps = {
  title?: string;
  summary: string;
  topics?: readonly ClinicalNextStepTopic[];
  action?: ClinicalExperienceAction;
  secondaryAction?: ClinicalExperienceAction;
};

export function ClinicalPersonalizedNextSteps({
  title = "What to work on next",
  summary,
  topics = [],
  action,
  secondaryAction,
}: ClinicalPersonalizedNextStepsProps) {
  const headingId = useId();
  return (
    <section className={styles.nextStepsCard} aria-labelledby={headingId}>
      <p className={styles.eyebrow}>Personalized next step</p>
      <h2 id={headingId}>{title}</h2>
      <p>{summary}</p>
      {topics.length ? (
        <ul className={styles.nextStepTopics}>
          {topics.map((topic) => (
            <li data-status={topic.status} key={topic.id}>
              <div><strong>{topic.href ? <Link href={topic.href}>{topic.label}</Link> : topic.label}</strong><span>{topic.statusLabel}</span></div>
              {topic.progress != null ? <progress max={100} value={Math.max(0, Math.min(100, topic.progress))} aria-label={`${topic.label}: ${topic.progress}%`} /> : null}
            </li>
          ))}
        </ul>
      ) : null}
      {(action || secondaryAction) ? <div className={styles.cardActions}>{action ? <ClinicalActionControl action={action} /> : null}{secondaryAction ? <ClinicalActionControl action={secondaryAction} /> : null}</div> : null}
    </section>
  );
}

export type ClinicalSBIFeedback = {
  situation: string;
  behavior: string;
  impact: string;
  nextStep: string;
};

export type ClinicalSBICoachingCardProps = {
  feedback: ClinicalSBIFeedback;
  title?: string;
  personalizationNote?: string;
  action?: ClinicalExperienceAction;
};

export function ClinicalSBICoachingCard({
  feedback,
  title = "AI coach feedback",
  personalizationNote,
  action,
}: ClinicalSBICoachingCardProps) {
  const headingId = useId();
  const rows = [
    { key: "S", label: "Situation", value: feedback.situation },
    { key: "B", label: "Behavior", value: feedback.behavior },
    { key: "I", label: "Impact", value: feedback.impact },
    { key: "N", label: "Next step", value: feedback.nextStep },
  ];
  return (
    <section className={styles.sbiCard} aria-labelledby={headingId}>
      <div className={styles.sbiHeading}><Sparkles size={19} aria-hidden="true" /><div><p className={styles.eyebrow}>Grounded coaching</p><h2 id={headingId}>{title}</h2></div></div>
      {personalizationNote ? <p className={styles.personalizationNote}>{personalizationNote}</p> : null}
      <dl>
        {rows.map((row) => (
          <div key={row.key}>
            <dt><span aria-hidden="true">{row.key}</span>{row.label}</dt>
            <dd>{row.value}</dd>
          </div>
        ))}
      </dl>
      {action ? <ClinicalActionControl action={action} /> : null}
    </section>
  );
}

export type ClinicalSetReviewExperienceProps = {
  hero: ClinicalSetReviewHeroProps;
  summaryItems?: readonly ClinicalDomainSummaryItem[];
  cases: ClinicalCaseReviewListProps;
  nextSteps?: ClinicalPersonalizedNextStepsProps;
  coaching?: ClinicalSBICoachingCardProps;
  notices?: ReactNode;
  actions?: ReactNode;
};

export function ClinicalSetReviewExperience({
  hero,
  summaryItems,
  cases,
  nextSteps,
  coaching,
  notices,
  actions,
}: ClinicalSetReviewExperienceProps) {
  const derivedSummary = summaryItems ?? (hero.report ? buildClinicalDomainSummaries(hero.report) : []);
  return (
    <div className={styles.setReviewExperience}>
      <ClinicalSetReviewHero {...hero} />
      {notices ? <div className={styles.noticeStack}>{notices}</div> : null}
      {derivedSummary.length ? <ClinicalDomainSummaryGrid items={derivedSummary} /> : null}
      <div className={styles.setReviewGrid}>
        <ClinicalCaseReviewList {...cases} />
        {(nextSteps || coaching) ? <aside className={styles.setReviewAside} aria-label="Personalized learning guidance">{nextSteps ? <ClinicalPersonalizedNextSteps {...nextSteps} /> : null}{coaching ? <ClinicalSBICoachingCard {...coaching} /> : null}</aside> : null}
      </div>
      {actions ? <div className={styles.setReviewActions}>{actions}</div> : null}
    </div>
  );
}
