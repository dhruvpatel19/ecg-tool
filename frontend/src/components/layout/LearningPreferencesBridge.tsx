"use client";

import { useEffect } from "react";
import type { LearningPreferences } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  applyLearningDisplayPreferences,
  learningPreferencesChangedEvent,
  readLearningPreferences,
} from "@/lib/learningPreferences";

export function LearningPreferencesBridge() {
  const { identityKey, user } = useAuth();

  useEffect(() => {
    let cancelled = false;
    // Never leave the prior browser identity's display choices on the shell
    // while the current owner-bound record is loading.
    applyLearningDisplayPreferences(null);

    const handlePreferenceChange = (event: Event) => {
      const preferences = (event as CustomEvent<LearningPreferences>).detail;
      if (!preferences || typeof preferences !== "object") return;
      applyLearningDisplayPreferences({
        reduceMotion: preferences.reduceMotion === true,
        largeControls: preferences.largeControls === true,
      });
    };

    window.addEventListener(learningPreferencesChangedEvent, handlePreferenceChange);
    // Display preferences are account-owned. Public pages never materialize or
    // read a browser-guest learner record.
    if (user) {
      readLearningPreferences(identityKey)
        .then((preferences) => {
          if (!cancelled) {
            applyLearningDisplayPreferences({
              reduceMotion: preferences.reduceMotion === true,
              largeControls: preferences.largeControls === true,
            });
          }
        })
        .catch(() => {
          // Display preferences are optional enhancement. The safe fallback is
          // the standard shell plus the operating-system reduced-motion query.
          if (!cancelled) applyLearningDisplayPreferences(null);
        });
    }

    return () => {
      cancelled = true;
      window.removeEventListener(learningPreferencesChangedEvent, handlePreferenceChange);
      applyLearningDisplayPreferences(null);
    };
  }, [identityKey, user]);

  return null;
}
