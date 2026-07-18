"use client";

import { Check, RotateCcw, Settings2, SlidersHorizontal } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  api,
  type LearningGuidanceLevel,
  type LearningPreferences,
  type LearningPrimaryGoal,
  type LearningRapidPace,
  type LearningSessionLength,
  type LearningTrainingStage,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  primeLearningPreferences,
  publishLearningPreferences,
  readLearningPreferences,
} from "@/lib/learningPreferences";
import styles from "./PreferencesPanel.module.css";

const trainingStages: Array<{ value: LearningTrainingStage; label: string }> = [
  { value: "not_set", label: "Prefer not to say" },
  { value: "preclinical", label: "Preclinical" },
  { value: "core_clerkship", label: "Core clerkship" },
  { value: "advanced_clerkship", label: "Advanced clerkship" },
  { value: "resident_review", label: "Resident or review" },
];

const primaryGoals: Array<{ value: LearningPrimaryGoal; label: string }> = [
  { value: "build_fundamentals", label: "Build ECG fundamentals" },
  { value: "exam_prep", label: "Prepare for exams" },
  { value: "clinical_reading", label: "Read ECGs in clinical settings" },
  { value: "emergency_prioritization", label: "Recognize urgent findings" },
  { value: "medication_safety", label: "Use ECGs for medication safety" },
];

const sessionLengths: LearningSessionLength[] = [5, 10, 25, 50];

const rapidPaces: Array<{ value: LearningRapidPace; label: string; detail: string }> = [
  { value: "untimed", label: "Untimed", detail: "Work through the whole read without a clock." },
  { value: "ward", label: "Ward pace", detail: "120 seconds for a compact full interpretation." },
  { value: "emergency", label: "Emergency", detail: "20 seconds to name one urgent finding." },
];

const guidanceLevels: Array<{ value: LearningGuidanceLevel; label: string; detail: string }> = [
  { value: "step_by_step", label: "Step by step", detail: "Open extra lesson context and show more mechanism links." },
  { value: "balanced", label: "Balanced", detail: "Keep extra lesson context available when you ask for it." },
  { value: "minimal", label: "Minimal", detail: "Keep extra lesson context collapsed until you open it." },
];

function preferenceDraft(preferences: LearningPreferences): Omit<LearningPreferences, "updatedAt"> {
  return {
    trainingStage: preferences.trainingStage,
    primaryGoal: preferences.primaryGoal,
    defaultSessionLength: preferences.defaultSessionLength,
    rapidPace: preferences.rapidPace,
    guidanceLevel: preferences.guidanceLevel,
    reduceMotion: preferences.reduceMotion,
    largeControls: preferences.largeControls,
  };
}

function preferencesMatch(
  left: Omit<LearningPreferences, "updatedAt">,
  right: Omit<LearningPreferences, "updatedAt">,
) {
  return left.trainingStage === right.trainingStage
    && left.primaryGoal === right.primaryGoal
    && left.defaultSessionLength === right.defaultSessionLength
    && left.rapidPace === right.rapidPace
    && left.guidanceLevel === right.guidanceLevel
    && left.reduceMotion === right.reduceMotion
    && left.largeControls === right.largeControls;
}

function savedTimeLabel(value: string | null) {
  if (!value) return "Using the standard setup. Change a choice to save your preferences.";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Saved";
  return `Last saved ${new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(parsed)}`;
}

export function PreferencesPanel() {
  const { identityKey } = useAuth();
  const [saved, setSaved] = useState<LearningPreferences | null>(null);
  const [draft, setDraft] = useState<Omit<LearningPreferences, "updatedAt"> | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setSaved(null);
    setDraft(null);
    setError(null);
    setStatus(null);
    readLearningPreferences(identityKey, { force: retryKey > 0 })
      .then((preferences) => {
        if (cancelled) return;
        setSaved(preferences);
        setDraft(preferenceDraft(preferences));
        publishLearningPreferences(preferences);
      })
      .catch(() => {
        if (!cancelled) setError("Your preferences could not be loaded. Nothing was changed.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [identityKey, retryKey]);

  const dirty = useMemo(
    () => Boolean(saved && draft && !preferencesMatch(preferenceDraft(saved), draft)),
    [draft, saved],
  );

  function updateDraft<K extends keyof Omit<LearningPreferences, "updatedAt">>(
    key: K,
    value: Omit<LearningPreferences, "updatedAt">[K],
  ) {
    setDraft((current) => current ? { ...current, [key]: value } : current);
    setStatus(null);
    setError(null);
  }

  async function savePreferences(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft || !dirty || saving) return;
    setSaving(true);
    setError(null);
    setStatus(null);
    try {
      const preferences = await api.updateLearningPreferences(draft);
      primeLearningPreferences(identityKey, preferences);
      setSaved(preferences);
      setDraft(preferenceDraft(preferences));
      publishLearningPreferences(preferences);
      setStatus("Preferences saved.");
    } catch {
      setError("Your preferences could not be saved. Your choices are still here so you can retry.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <section className={styles.loading} role="status" aria-label="Loading learning preferences">
        <h2 id="preferences-heading" className="sr-only">Learning preferences</h2>
        <span />
        <span />
        <p>Loading your preferences…</p>
      </section>
    );
  }

  if (!draft || !saved) {
    return (
      <section className={styles.loadError} role="alert">
        <Settings2 size={21} aria-hidden="true" />
        <div><h2 id="preferences-heading">Preferences are unavailable</h2><p>{error ?? "Your preferences could not be opened."}</p></div>
        <button className="button subtle" type="button" onClick={() => setRetryKey((value) => value + 1)}>Try again</button>
      </section>
    );
  }

  return (
    <form className={styles.form} onSubmit={savePreferences}>
      <section className={styles.intro} aria-labelledby="preferences-heading">
        <span className={styles.introIcon}><SlidersHorizontal size={20} aria-hidden="true" /></span>
        <div>
          <p className="eyebrow">Your setup</p>
          <h2 id="preferences-heading">Shape your learning workspace</h2>
          <p>Choose a starting setup for new sessions. You can still change any practice choice before a session begins.</p>
        </div>
        <small>{saved.updatedAt
          ? "Saved privately to your account."
          : "Preferences are private to your account and follow you across devices."}</small>
      </section>

      <div className={styles.grid}>
        <div className={styles.stack}>
          <fieldset className={styles.card}>
            <legend>About your learning</legend>
            <p className={styles.cardIntro}>Your stage and goal break ties between suitable routes; completed practice remains the main signal.</p>
            <label className={styles.selectField} htmlFor="preference-training-stage">
              <span>Where are you in training?</span>
              <select
                id="preference-training-stage"
                value={draft.trainingStage}
                onChange={(event) => updateDraft("trainingStage", event.target.value as LearningTrainingStage)}
              >
                {trainingStages.map((option) => <option value={option.value} key={option.value}>{option.label}</option>)}
              </select>
            </label>
            <label className={styles.selectField} htmlFor="preference-primary-goal">
              <span>What are you working toward?</span>
              <select
                id="preference-primary-goal"
                value={draft.primaryGoal}
                onChange={(event) => updateDraft("primaryGoal", event.target.value as LearningPrimaryGoal)}
              >
                {primaryGoals.map((option) => <option value={option.value} key={option.value}>{option.label}</option>)}
              </select>
            </label>
          </fieldset>

          <fieldset className={styles.card}>
            <legend>Display and interaction</legend>
            <p className={styles.cardIntro}>These choices change presentation only. They never change how an answer is scored.</p>
            <label className={styles.toggleCard}>
              <input
                type="checkbox"
                checked={draft.reduceMotion}
                onChange={(event) => updateDraft("reduceMotion", event.target.checked)}
              />
              <span><strong>Reduce motion</strong><small>Remove nonessential animation and smooth scrolling.</small></span>
            </label>
            <label className={styles.toggleCard}>
              <input
                type="checkbox"
                checked={draft.largeControls}
                onChange={(event) => updateDraft("largeControls", event.target.checked)}
              />
              <span><strong>Larger controls</strong><small>Increase common touch targets across the site.</small></span>
            </label>
          </fieldset>
        </div>

        <fieldset className={`${styles.card} ${styles.sessionCard}`}>
          <legend>Practice defaults</legend>
          <p className={styles.cardIntro}>Set the options you want selected first. Independent checks stay independent at every guidance level.</p>

          <fieldset className={styles.choiceGroup}>
            <legend>ECGs per session</legend>
            <div className={styles.lengthChoices}>
              {sessionLengths.map((length) => (
                <label key={length}>
                  <input
                    type="radio"
                    name="default-session-length"
                    value={length}
                    checked={draft.defaultSessionLength === length}
                    onChange={() => updateDraft("defaultSessionLength", length)}
                  />
                  <span><strong>{length}</strong><small>ECGs</small></span>
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset className={styles.choiceGroup}>
            <legend>Rapid Practice pace</legend>
            <div className={styles.optionChoices}>
              {rapidPaces.map((pace) => (
                <label key={pace.value}>
                  <input
                    type="radio"
                    name="rapid-pace"
                    value={pace.value}
                    checked={draft.rapidPace === pace.value}
                    onChange={() => updateDraft("rapidPace", pace.value)}
                  />
                  <span><strong>{pace.label}</strong><small>{pace.detail}</small></span>
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset className={styles.choiceGroup}>
            <legend>Guided lesson support</legend>
            <div className={styles.optionChoices}>
              {guidanceLevels.map((level) => (
                <label key={level.value}>
                  <input
                    type="radio"
                    name="guidance-level"
                    value={level.value}
                    checked={draft.guidanceLevel === level.value}
                    onChange={() => updateDraft("guidanceLevel", level.value)}
                  />
                  <span><strong>{level.label}</strong><small>{level.detail}</small></span>
                </label>
              ))}
            </div>
          </fieldset>
        </fieldset>
      </div>

      <div className={styles.saveBar}>
        <div aria-live="polite">
          {error ? <p className={styles.saveError} role="alert">{error}</p> : null}
          {status ? <p className={styles.savedStatus}><Check size={15} aria-hidden="true" /> {status}</p> : null}
          {!error && !status ? <p>{dirty ? "You have unsaved changes." : savedTimeLabel(saved.updatedAt)}</p> : null}
        </div>
        <div>
          <button
            className="button subtle"
            type="button"
            disabled={!dirty || saving}
            onClick={() => {
              setDraft(preferenceDraft(saved));
              setError(null);
              setStatus("Unsaved changes cleared.");
            }}
          >
            <RotateCcw size={15} aria-hidden="true" /> Undo changes
          </button>
          <button className="button primary" type="submit" disabled={!dirty || saving}>
            {saving ? "Saving…" : "Save preferences"}
          </button>
        </div>
      </div>
    </form>
  );
}
