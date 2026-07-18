import type { AdaptivePlan, LearningResumeSession, LearningResumeSnapshot } from "@/lib/api";
import { competencySkillLabel as skillLabel } from "@/lib/learning/skillLabels";
import { learningResumePresentation } from "@/lib/learningResume";

export type LearningHomeRecommendation = {
  kind: "resume" | "guided" | "personalized" | "baseline" | "general" | "loading";
  eyebrow: string;
  title: string;
  detail: string;
  href: string | null;
  cta: string;
  reason: string | null;
  personalized: boolean;
  resume: LearningResumeSession | null;
  after: { title: string; href: string } | null;
};

function firstRunnableStage(plan: AdaptivePlan | null) {
  return plan?.stages
    .filter((stage) => stage.href.trim().length > 0)
    .sort((left, right) => left.order - right.order)[0] ?? null;
}

function stageTitle(stage: AdaptivePlan["stages"][number]) {
  if (!/^(Check|Build)\s/i.test(stage.title.trim())) return stage.title.trim();
  const label = stage.title
    .replace(/^Check /, "")
    .replace(/^Build /, "")
    .replace(/ · independent recognition$/i, "")
    .replace(/ · complete-read synthesis$/i, "")
    .trim();
  const skill = skillLabel(stage.receiptSubskill);
  if (stage.receiptSubskill === "synthesize") return `Practice a complete ECG read: ${label}`;
  if (stage.mode === "rapid") return `Check ${label}: ${skill}`;
  if (stage.mode === "clinical") return `Apply ${label} in a case`;
  return `Practice ${label}: ${skill}`;
}

function stageDetail(stage: AdaptivePlan["stages"][number]) {
  const count = stage.suggestedLength;
  if (stage.mode === "clinical") {
    return "Apply the ECG finding in a patient case, then return to your plan.";
  }
  if (stage.mode === "rapid") {
    return `Work through ${count} fresh ECG${count === 1 ? "" : "s"}. Your results will help Luna choose what comes next.`;
  }
  return `Practice this skill across ${count} ECG${count === 1 ? "" : "s"}, then try it again without hints.`;
}

function recommendationReason(plan: AdaptivePlan | null) {
  const priority = plan?.primary;
  if (!priority) return null;
  const label = `${priority.label}: ${skillLabel(priority.subskill)}`;
  if (priority.dueState === "overdue") {
    return `${label} is ready for a quick review because it has been a while since your last check.`;
  }
  if (priority.isDue) {
    return `${label} is ready to review now. A fresh ECG will show whether it still feels familiar.`;
  }
  if (priority.highConfidenceWrong > 0) {
    return `You were confident on a missed ${label} question, so a focused review can help correct the pattern.`;
  }
  if (priority.independentAttempts > 0) {
    return `Your recent ${label} results suggest that one more focused check would be useful.`;
  }
  if (priority.attempts > 0) {
    return `You have practiced ${label} with guidance. The next step is to try it on a fresh ECG.`;
  }
  return `${label} is a useful first skill for Luna to check before tailoring the rest of your plan.`;
}

/**
 * One presentation contract for every learning-home surface. The deterministic
 * scheduler owns the destination; this helper only resolves resume precedence
 * and honest fallback language.
 */
export function learningHomeRecommendation(
  plan: AdaptivePlan | null,
  resumeSnapshot: LearningResumeSnapshot | null,
  options: { planLoading: boolean; resumeLoading: boolean; planFailed: boolean },
): LearningHomeRecommendation {
  const compatibleResume = resumeSnapshot?.version === "learning-resume-v1" ? resumeSnapshot : null;
  const resumeCandidates = [compatibleResume?.primary, ...(compatibleResume?.additional ?? [])]
    .filter((session): session is LearningResumeSession => Boolean(session));
  const firstResume = resumeCandidates.find((session) => learningResumePresentation(session)) ?? null;
  const resume = firstResume ? learningResumePresentation(firstResume) : null;
  const guided = plan?.guidedRemediation?.href.trim() ? plan.guidedRemediation : null;
  const stage = firstRunnableStage(plan);
  const after = guided
    ? { title: `Review ${plan?.primary?.label ?? "this skill"} with guidance`, href: guided.href }
    : stage
      ? { title: stageTitle(stage), href: stage.href }
      : null;

  if (options.resumeLoading) {
    return {
      kind: "loading",
      eyebrow: "Checking your work",
      title: "Checking your saved learning…",
      detail: "Looking for an unfinished session so you can pick up in the right place.",
      href: null,
      cta: "Checking saved work",
      reason: null,
      personalized: false,
      resume: null,
      after: null,
    };
  }

  if (firstResume && resume) {
    return {
      kind: "resume",
      eyebrow: resume.phaseLabel,
      title: resume.title,
      detail: resume.detail,
      href: resume.href,
      cta: resume.cta,
      reason: null,
      personalized: true,
      resume: firstResume,
      after: options.planLoading ? null : after,
    };
  }

  if (options.planLoading) {
    return {
      kind: "loading",
      eyebrow: "Luna is getting ready",
      title: "Building your next step…",
      detail: "Reviewing your recent practice and what is ready to revisit.",
      href: null,
      cta: "Preparing your next step",
      reason: null,
      personalized: false,
      resume: null,
      after: null,
    };
  }

  // A runnable planner stage may still be emitted while the learner has no
  // independent baseline. Do not present that cold-start route as if it were
  // already personalized from evidence that does not exist.
  if (!options.planFailed && plan?.basis.baselineNeeded) {
    const selectedStartingCheck = stage;
    return {
      kind: "baseline",
      eyebrow: "First step",
      title: "Take a 5-ECG starting check",
      detail: "This short, untimed check helps Luna learn what you already know and choose what to study next.",
      href: selectedStartingCheck?.href ?? "/rapid?pace=untimed&suggestedLength=5&returnTo=%2Fhome",
      cta: "Start 5-ECG check",
      reason: "You have not completed a scored ECG check yet, so Luna needs a quick starting point before tailoring your plan.",
      personalized: false,
      resume: null,
      after: null,
    };
  }

  if (guided) {
    return {
      kind: "guided",
      eyebrow: "Start here",
      title: `Review ${plan?.primary?.label ?? "this skill"} with guidance`,
      detail: `Work through a short guided lesson, then try ${plan?.primary?.label ?? "the skill"} on a fresh ECG.`,
      href: guided.href,
      cta: "Start guided review",
      reason: recommendationReason(plan),
      personalized: true,
      resume: null,
      after: null,
    };
  }

  if (stage) {
    return {
      kind: "personalized",
      eyebrow: "Start here",
      title: stageTitle(stage),
      detail: stageDetail(stage),
      href: stage.href,
      cta: stage.mode === "rapid" ? "Start rapid practice" : stage.mode === "clinical" ? "Open clinical case" : "Start focused practice",
      reason: recommendationReason(plan),
      personalized: true,
      resume: null,
      after: null,
    };
  }

  return {
    kind: "general",
    eyebrow: "Practice option",
    title: "Keep your ECG reading active",
    detail: "Your tailored plan is unavailable right now, but you can still complete a short untimed set.",
    href: "/rapid?pace=untimed&suggestedLength=5&returnTo=%2Fhome",
    cta: "Start general practice",
    reason: null,
    personalized: false,
    resume: null,
    after: null,
  };
}
