"use client";

import { useCallback, useEffect, useState } from "react";
import type { LearningPreferences } from "./api";
import { useAuth } from "./auth";
import {
  learningPreferencesChangedEvent,
  readLearningPreferences,
} from "./learningPreferences";

type UseLearningPreferencesOptions = {
  /** Set false when a caller deliberately wants to defer the owner-bound read. */
  enabled?: boolean;
};

export type LearningPreferencesRead = {
  preferences: LearningPreferences | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
};

/**
 * Read the current browser owner's saved setup. Mode pages should wait for
 * `loading` to finish before applying the result, and should only use it to
 * prefill untouched setup controls; explicit URL handoffs and learner changes
 * remain authoritative.
 */
export function useLearningPreferences(
  { enabled = true }: UseLearningPreferencesOptions = {},
): LearningPreferencesRead {
  const { identityKey } = useAuth();
  const [preferences, setPreferences] = useState<LearningPreferences | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision((value) => value + 1), []);

  useEffect(() => {
    let cancelled = false;
    setPreferences(null);
    setError(null);
    if (!enabled) {
      setLoading(false);
      return () => { cancelled = true; };
    }

    setLoading(true);
    const handlePreferenceChange = (event: Event) => {
      const next = (event as CustomEvent<LearningPreferences>).detail;
      if (next && typeof next === "object") setPreferences(next);
    };
    window.addEventListener(learningPreferencesChangedEvent, handlePreferenceChange);
    readLearningPreferences(identityKey, { force: revision > 0 })
      .then((result) => {
        if (!cancelled) setPreferences(result);
      })
      .catch(() => {
        if (!cancelled) setError("Learning preferences could not be loaded.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
      window.removeEventListener(learningPreferencesChangedEvent, handlePreferenceChange);
    };
  }, [enabled, identityKey, revision]);

  return { preferences, loading, error, refresh };
}
