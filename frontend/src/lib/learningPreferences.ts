import { api, type LearningPreferences } from "./api";

export const learningPreferencesChangedEvent = "trace:learning-preferences-changed";
export const guestLearningPreferencesMarker = "trace:guest-learning-preferences";

export const defaultLearningPreferences: LearningPreferences = {
  trainingStage: "not_set",
  primaryGoal: "build_fundamentals",
  defaultSessionLength: 10,
  rapidPace: "untimed",
  guidanceLevel: "balanced",
  reduceMotion: false,
  largeControls: false,
  updatedAt: null,
};

type DisplayPreferences = Pick<LearningPreferences, "reduceMotion" | "largeControls">;

type PreferencesCacheEntry = {
  value: LearningPreferences | null;
  request: Promise<LearningPreferences> | null;
};

const preferencesCache = new Map<string, PreferencesCacheEntry>();

function cacheEntry(identityKey: string) {
  const existing = preferencesCache.get(identityKey);
  if (existing) return existing;
  const created: PreferencesCacheEntry = { value: null, request: null };
  preferencesCache.set(identityKey, created);
  return created;
}

/**
 * Share the owner-bound preferences read across the shell bridge and whichever
 * learning mode is mounted. A forced read bypasses a settled value, while an
 * already-running request is still coalesced so StrictMode cannot duplicate it.
 */
export function readLearningPreferences(identityKey: string, { force = false } = {}) {
  const entry = cacheEntry(identityKey);
  if (!force && entry.value) return Promise.resolve(entry.value);
  if (entry.request) return entry.request;

  const request = api.learningPreferences()
    .then((preferences) => {
      if (entry.request === request) entry.value = preferences;
      return preferences;
    })
    .finally(() => {
      if (entry.request === request) entry.request = null;
    });
  entry.request = request;
  return request;
}

export function primeLearningPreferences(identityKey: string, preferences: LearningPreferences) {
  const entry = cacheEntry(identityKey);
  entry.value = preferences;
}

export function applyLearningDisplayPreferences(preferences: DisplayPreferences | null) {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  if (preferences?.reduceMotion === true) root.dataset.reduceMotion = "true";
  else delete root.dataset.reduceMotion;
  if (preferences?.largeControls === true) root.dataset.largeControls = "true";
  else delete root.dataset.largeControls;
}

export function publishLearningPreferences(preferences: LearningPreferences) {
  if (typeof window === "undefined") return;
  applyLearningDisplayPreferences(preferences);
  window.dispatchEvent(new CustomEvent<LearningPreferences>(learningPreferencesChangedEvent, { detail: preferences }));
}

export function hasGuestLearningPreferencesMarker() {
  return typeof window !== "undefined" && window.localStorage.getItem(guestLearningPreferencesMarker) === "saved";
}

export function markGuestLearningPreferences() {
  if (typeof window !== "undefined") window.localStorage.setItem(guestLearningPreferencesMarker, "saved");
}

export function clearGuestLearningPreferencesMarker() {
  if (typeof window !== "undefined") window.localStorage.removeItem(guestLearningPreferencesMarker);
}
