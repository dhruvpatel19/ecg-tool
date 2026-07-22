// Module progress — read client-side today, forward-compatible with server progress.
//
// The Foundations module (embedded iframe, served same-origin from /public) persists
// its state in localStorage and ALSO postMessages a progress contract to the parent:
//   { source: "foundations", type: "ready"|"progress"|"complete",
//     completedScenes, totalScenes, currentIndex, currentId, part, done, bestAccuracy }
// (see foundations/app.js). This module reads that state and lets the hub / host page
// subscribe to live updates.
//
// Forward-compatibility: when a module is later ported to native React (or backed by a
// Phase-4 `/progress` endpoint), it emits/satisfies this SAME shape — callers don't change.

export interface ModuleProgress {
  completedScenes: number;
  totalScenes: number;
  done: boolean;
  started: boolean;
  bestAccuracy: number; // 0..100, retained from the legacy Foundations capstone
}

const FOUNDATIONS_KEY_PREFIX = "foundations_state_v1:";
const FOUNDATIONS_BEST_PREFIX = "found_best:";
const PRODUCTION_KEY = "trace-production-curriculum-v1";

export function validFoundationSceneIds(sceneIds: unknown, totalScenes = 13): string[] {
  if (!Array.isArray(sceneIds)) return [];
  const allowed = new Set(Array.from({ length: totalScenes }, (_, index) => `S${index}`));
  return [...new Set(sceneIds.filter((value): value is string => typeof value === "string" && allowed.has(value)))];
}

export function readFoundationsProgress(totalScenes = 13, ownerKey = "guest"): ModuleProgress {
  const empty: ModuleProgress = { completedScenes: 0, totalScenes, done: false, started: false, bestAccuracy: 0 };
  if (typeof window === "undefined") return empty;
  let completedScenes = 0;
  let started = false;
  try {
    const raw = window.localStorage.getItem(`${FOUNDATIONS_KEY_PREFIX}${ownerKey}`);
    if (raw) {
      const s = JSON.parse(raw) as {
        completed?: Record<string, boolean>;
        skipped?: Record<string, boolean>;
        needsReview?: Record<string, boolean>;
        current?: number;
      };
      const skipped = new Set(validFoundationSceneIds(
        s?.skipped ? Object.entries(s.skipped).filter(([, value]) => value === true).map(([sceneId]) => sceneId) : [],
        totalScenes,
      ));
      completedScenes = validFoundationSceneIds(
        s?.completed ? Object.entries(s.completed).filter(([, complete]) => complete === true).map(([sceneId]) => sceneId) : [],
        totalScenes,
      ).filter((sceneId) => !skipped.has(sceneId)).length;
      const needsReview = validFoundationSceneIds(
        s?.needsReview
          ? Object.entries(s.needsReview).filter(([, value]) => value === true).map(([sceneId]) => sceneId)
          : [],
        totalScenes,
      );
      const currentScene = Number.isInteger(s?.current) ? Math.max(0, Math.min(totalScenes - 1, Number(s.current))) : 0;
      started = completedScenes > 0 || needsReview.length > 0 || skipped.size > 0 || currentScene > 0;
    }
  } catch {
    // corrupt/unavailable storage → treat as not started
  }
  let bestAccuracy = 0;
  try {
    bestAccuracy = Number(window.localStorage.getItem(`${FOUNDATIONS_BEST_PREFIX}${ownerKey}`) || 0) || 0;
  } catch {
    /* ignore */
  }
  return { completedScenes, totalScenes, done: completedScenes >= totalScenes, started, bestAccuracy };
}

/** Read scene completion for one native production module without confusing it
 * with competency mastery. A skipped or needs-review scene counts as started,
 * but only `complete` advances the pathway meter. */
export function readProductionModuleProgress(moduleId: string, totalScenes: number): ModuleProgress {
  const empty: ModuleProgress = { completedScenes: 0, totalScenes, done: false, started: false, bestAccuracy: 0 };
  if (typeof window === "undefined") return empty;
  try {
    const all = JSON.parse(window.localStorage.getItem(PRODUCTION_KEY) ?? "{}") as Record<
      string,
      Record<string, { status?: string }>
    >;
    const scenes = Object.values(all?.[moduleId] ?? {});
    const completedScenes = scenes.filter((scene) => scene.status === "complete").length;
    const started = scenes.some((scene) => scene.status && scene.status !== "not-started");
    return {
      completedScenes,
      totalScenes,
      done: completedScenes >= totalScenes,
      started,
      bestAccuracy: 0,
    };
  } catch {
    return empty;
  }
}

/**
 * Subscribe to progress changes. Fires the callback when the embedded module writes
 * localStorage (cross-document `storage` event), postMessages a progress update, or the
 * tab/window regains focus. Returns an unsubscribe function.
 */
export function subscribeProgress(callback: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const onStorage = (e: StorageEvent) => {
    if (!e.key || e.key.startsWith(FOUNDATIONS_KEY_PREFIX) || e.key.startsWith(FOUNDATIONS_BEST_PREFIX) || e.key === PRODUCTION_KEY) callback();
  };
  const onMessage = (e: MessageEvent) => {
    if (e.origin === window.location.origin && (e.data as { source?: string })?.source === "foundations") callback();
  };
  const onFocus = () => callback();
  const onProductionProgress = () => callback();
  window.addEventListener("storage", onStorage);
  window.addEventListener("message", onMessage);
  window.addEventListener("focus", onFocus);
  document.addEventListener("visibilitychange", onFocus);
  window.addEventListener("trace-production-progress", onProductionProgress);
  return () => {
    window.removeEventListener("storage", onStorage);
    window.removeEventListener("message", onMessage);
    window.removeEventListener("focus", onFocus);
    document.removeEventListener("visibilitychange", onFocus);
    window.removeEventListener("trace-production-progress", onProductionProgress);
  };
}
