import type { LearningResumeSession } from "@/lib/api";
import { MODULES } from "@/lib/modules";

export type LearningResumePresentation = {
  href: string;
  title: string;
  detail: string;
  phaseLabel: string;
  cta: string;
};

const modeCopy = {
  guided: { title: "Continue Guided learning", cta: "Continue Guided learning", unit: "scenes" },
  training: { title: "Continue Focused practice", cta: "Continue Focused practice", unit: "ECGs" },
  rapid: { title: "Continue Rapid practice", cta: "Continue Rapid practice", unit: "ECGs" },
  clinical: { title: "Continue Clinical cases", cta: "Continue Clinical cases", unit: "cases" },
} as const;

const phaseLabel = {
  // The resume snapshot intentionally does not expose a raw deadline. Use
  // wording that stays true both before and after that server-owned instant.
  deadline: "Timed ECG needs attention",
  feedback: "Feedback ready",
  in_progress: "Session in progress",
} as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasOnlyKeys(value: Record<string, unknown>, allowed: string[]): boolean {
  const keys = Object.keys(value);
  return keys.length === allowed.length && keys.every((key) => allowed.includes(key));
}

/**
 * Convert a server-owned destination discriminator into one authored app route.
 * This function intentionally rejects unknown keys and mismatched mode/kind
 * pairs; no URL supplied by stored learner data is ever navigated directly.
 */
export function learningResumeHref(session: LearningResumeSession | unknown): string | null {
  if (!isRecord(session) || !isRecord(session.destination)) return null;
  const mode = session.mode;
  const destination = session.destination;
  if (mode === "training" && destination.kind === "training" && hasOnlyKeys(destination, ["kind"])) return "/train";
  if (mode === "rapid" && destination.kind === "rapid" && hasOnlyKeys(destination, ["kind"])) return "/rapid";
  if (mode === "clinical" && destination.kind === "clinical" && hasOnlyKeys(destination, ["kind"])) return "/practice";
  if (mode !== "guided" || destination.kind !== "guided" || !hasOnlyKeys(destination, ["kind", "moduleId", "sceneId"])) {
    return null;
  }
  if (typeof destination.moduleId !== "string") return null;
  const module = MODULES.find((item) => item.id === destination.moduleId && item.status === "ready");
  if (!module) return null;
  if (module.id === "foundations") {
    return destination.sceneId === null ? "/learn/foundations" : null;
  }
  if (typeof destination.sceneId !== "string") return null;
  const expectedModuleNumber = module.order + 1;
  const scenePrefix = expectedModuleNumber <= 3
    ? `M${String(expectedModuleNumber).padStart(2, "0")}.S`
    : `m${String(expectedModuleNumber).padStart(2, "0")}-s`;
  const ordinal = destination.sceneId.startsWith(scenePrefix)
    ? destination.sceneId.slice(scenePrefix.length)
    : "";
  const sceneIndex = /^\d{1,2}$/.test(ordinal) ? Number(ordinal) : -1;
  if (
    sceneIndex < 0
    || sceneIndex >= (module.sceneCount ?? 0)
  ) {
    return null;
  }
  return `/learn/${module.id}?scene=${encodeURIComponent(destination.sceneId)}`;
}

export function learningResumePresentation(
  session: LearningResumeSession | unknown,
): LearningResumePresentation | null {
  const href = learningResumeHref(session);
  if (!href || !isRecord(session)) return null;
  const mode = session.mode;
  const phase = session.phase;
  if (
    typeof mode !== "string"
    || typeof phase !== "string"
    || !(mode in modeCopy)
    || !(phase in phaseLabel)
  ) return null;
  const copy = modeCopy[mode as keyof typeof modeCopy];
  const rawCompleted = typeof session.completed === "number" && Number.isFinite(session.completed) ? session.completed : 0;
  const rawTotal = typeof session.total === "number" && Number.isFinite(session.total) ? session.total : 0;
  const total = Math.max(0, Math.floor(rawTotal));
  const completed = Math.max(0, Math.min(Math.floor(rawCompleted), total));
  let detail = `${completed} of ${total} ${copy.unit} complete.`;
  const destination = session.destination;
  if (mode === "guided" && isRecord(destination) && typeof destination.moduleId === "string") {
    const module = MODULES.find((item) => item.id === destination.moduleId);
    if (module) detail = `${module.title} · ${completed} of ${total} scenes complete.`;
  }
  return {
    href,
    title: copy.title,
    detail,
    phaseLabel: phaseLabel[phase as keyof typeof phaseLabel],
    cta: copy.cta,
  };
}
