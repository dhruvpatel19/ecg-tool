"use client";

import {
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronDown,
  Search,
  Sparkles,
  Target,
} from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import type { LearningSubskill } from "@/lib/learning/interactionTypes";
import styles from "./FocusedPracticeSetup.module.css";

export type FocusedTopicOption = {
  id: string;
  label: string;
  category: string;
  categoryLabel: string;
  masteryLabel: string;
  masteryValue: number | null;
  recommended: boolean;
};

export type FocusedSkillOption = {
  id: LearningSubskill;
  label: string;
  description: string;
  availability?: "loading" | "available" | "unavailable" | "error";
};

type FocusedPracticeSetupProps = {
  returnTo?: string;
  returnLabel?: string;
  notices?: ReactNode;
  errorNotice?: ReactNode;
  query: string;
  onQueryChange: (value: string) => void;
  category: string;
  categories: Array<{ id: string; label: string }>;
  onCategoryChange: (value: string) => void;
  topics: FocusedTopicOption[];
  selectedTopic: FocusedTopicOption | null;
  selectedTopicId: string;
  onTopicSelect: (value: string) => void;
  showAllTopics: boolean;
  onToggleAllTopics: () => void;
  skills: FocusedSkillOption[];
  selectedSkill: LearningSubskill;
  onSkillSelect: (value: LearningSubskill) => void;
  adaptiveMode: boolean;
  recommendationText: string;
  onUseRecommendation: () => void;
  campaignLength: number;
  visibleLengths: readonly number[];
  extendedLengths: readonly number[];
  onLengthChange: (value: number) => void;
  poolLoading: boolean;
  poolAvailable: boolean;
  poolMessage?: string | null;
  loading: boolean;
  replaceActive: boolean;
  onStart: () => void;
};

function masteryTone(value: number | null) {
  if (value === null) return "new";
  if (value < 0.45) return "review";
  if (value < 0.72) return "building";
  return "strong";
}

export function FocusedPracticeSetup({
  returnTo,
  returnLabel,
  notices,
  errorNotice,
  query,
  onQueryChange,
  category,
  categories,
  onCategoryChange,
  topics,
  selectedTopic,
  selectedTopicId,
  onTopicSelect,
  showAllTopics,
  onToggleAllTopics,
  skills,
  selectedSkill,
  onSkillSelect,
  adaptiveMode,
  recommendationText,
  onUseRecommendation,
  campaignLength,
  visibleLengths,
  extendedLengths,
  onLengthChange,
  poolLoading,
  poolAvailable,
  poolMessage,
  loading,
  replaceActive,
  onStart,
}: FocusedPracticeSetupProps) {
  const visibleTopics = showAllTopics || query.trim() ? topics : topics.slice(0, 10);
  const selectedSkillMeta = skills.find((skill) => skill.id === selectedSkill) ?? skills[0];
  const selectedLengthIsExtended = !visibleLengths.includes(campaignLength);

  return (
    <main className={styles.page}>
      <section className={`train-campaign-setup train-setup-single ${styles.shell}`} aria-label="Configure focused practice">
        <header className={styles.header}>
          <div>
            <p className={styles.eyebrow}>Focused practice</p>
            <h1>What do you want to strengthen?</h1>
            <p>Choose a topic, then practice one specific reading skill across examples, close look-alikes, and normal contrasts.</p>
          </div>
          {returnTo ? (
            <Link className={`button subtle ${styles.returnLink}`} href={returnTo}>
              <ArrowLeft size={16} aria-hidden="true" /> {returnLabel ?? "Return"}
            </Link>
          ) : null}
        </header>

        {notices}
        {errorNotice}

        <div className={styles.workspace}>
          <section className={styles.topicBrowser} aria-labelledby="focused-topic-heading">
            <div className={styles.sectionHeading}>
              <div>
                <span>1</span>
                <div>
                  <h2 id="focused-topic-heading">Choose a topic</h2>
                  <p>Every ECG in the set will test this concept.</p>
                </div>
              </div>
              <button
                className={`${styles.recommendButton} ${adaptiveMode ? styles.active : ""}`}
                type="button"
                aria-pressed={adaptiveMode}
                onClick={() => onUseRecommendation()}
                disabled={loading}
              >
                <Sparkles size={15} aria-hidden="true" /> Use my recommendation
              </button>
            </div>

            <div className={styles.searchRow}>
              <label className={styles.search} htmlFor="train-concept-search">
                <Search size={18} aria-hidden="true" />
                <span className="sr-only">Find a topic</span>
                <input
                  id="train-concept-search"
                  type="search"
                  value={query}
                  onChange={(event) => onQueryChange(event.target.value)}
                  placeholder="Search ECG topics"
                  autoComplete="off"
                  disabled={loading}
                />
              </label>
              <div className={styles.categoryTabs} role="group" aria-label="Topic categories">
                {categories.map((item) => (
                  <button
                    type="button"
                    key={item.id}
                    aria-pressed={category === item.id}
                    className={category === item.id ? styles.selectedTab : ""}
                    onClick={() => onCategoryChange(item.id)}
                    disabled={loading}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>

            <div id="train-concept-search-status" className="sr-only" aria-live="polite">
              {topics.length} matching topic{topics.length === 1 ? "" : "s"}; {visibleTopics.length} currently shown.
            </div>

            {visibleTopics.length ? (
              <div id="focused-topic-grid" className={styles.topicGrid} role="group" aria-label="Available focused practice topics">
                {visibleTopics.map((topic) => {
                  const selected = topic.id === selectedTopicId;
                  return (
                    <button
                      className={`${styles.topicCard} ${selected ? styles.selectedTopic : ""}`}
                      type="button"
                      key={topic.id}
                      aria-pressed={selected}
                      onClick={() => onTopicSelect(topic.id)}
                      disabled={loading}
                    >
                      <span className={styles.topicIcon} aria-hidden="true"><Target size={18} /></span>
                      <span className={styles.topicCopy}>
                        <strong>{topic.label}</strong>
                        <small>{topic.categoryLabel}</small>
                      </span>
                      {selected ? <Check className={styles.topicCheck} size={18} aria-hidden="true" /> : null}
                      <span className={styles.topicMeta} data-tone={masteryTone(topic.masteryValue)}>
                        {topic.recommended ? <Sparkles size={12} aria-hidden="true" /> : null}
                        {topic.recommended && topic.masteryLabel === "Not assessed yet" ? "Recommended first check" : topic.masteryLabel}
                      </span>
                    </button>
                  );
                })}
              </div>
            ) : (
              <div className={styles.noTopics} role="status">
                <strong>No topics match that search.</strong>
                <span>Try another term or choose a different category.</span>
              </div>
            )}

            {topics.length > 10 && !query.trim() ? (
              <button
                className={styles.showMore}
                type="button"
                onClick={onToggleAllTopics}
                aria-expanded={showAllTopics}
                aria-controls="focused-topic-grid"
                disabled={loading}
              >
                {showAllTopics ? "Show fewer topics" : `Show all ${topics.length} topics`} <ChevronDown size={15} aria-hidden="true" />
              </button>
            ) : null}

          </section>

          <aside className={styles.plan} aria-labelledby="focused-plan-heading">
            <div className={styles.planTitle}>
              <span>2</span>
              <div>
                <p>Your practice plan</p>
                <h2 id="focused-plan-heading">{selectedTopic?.label ?? "Choose a topic"}</h2>
              </div>
            </div>

            <div className={styles.recommendation}>
              <Sparkles size={17} aria-hidden="true" />
              <div><strong>{adaptiveMode ? "Recommended for you" : "Your selected focus"}</strong><span>{recommendationText}</span></div>
            </div>

            <fieldset className={styles.skillFieldset}>
              <legend>Which skill do you want to practice?</legend>
              <div className={styles.skillGrid}>
                {skills.map((skill) => {
                  const selected = skill.id === selectedSkill;
                  const unavailable = skill.availability === "unavailable";
                  const checking = skill.availability === "loading";
                  const availabilityError = skill.availability === "error";
                  return (
                    <button
                      type="button"
                      key={skill.id}
                      className={selected ? styles.selectedSkill : ""}
                      aria-pressed={selected}
                      onClick={() => onSkillSelect(skill.id)}
                      disabled={loading || unavailable || checking || availabilityError}
                    >
                      <span>{selected ? <Check size={14} aria-hidden="true" /> : <Target size={14} aria-hidden="true" />}</span>
                      <strong>{skill.label}</strong>
                      <small>{skill.description}</small>
                      {unavailable ? <em>Not available for this topic</em> : null}
                      {availabilityError ? <em>Availability could not be checked</em> : null}
                    </button>
                  );
                })}
              </div>
            </fieldset>

            <fieldset className={styles.lengthFieldset}>
              <legend>How long should this set be?</legend>
              <div className={styles.lengthChoices}>
                {visibleLengths.map((length) => (
                  <button
                    key={length}
                    type="button"
                    aria-label={`Up to ${length.toLocaleString()} ECGs`}
                    aria-pressed={campaignLength === length}
                    className={campaignLength === length ? styles.selectedLength : ""}
                    onClick={() => onLengthChange(length)}
                    disabled={loading}
                  >
                    <strong>{length}</strong><span>ECGs</span>
                  </button>
                ))}
              </div>
              {extendedLengths.length ? (
                <details className={styles.extendedLengths} open={selectedLengthIsExtended}>
                  <summary>More set lengths</summary>
                  <label htmlFor="train-campaign-length">Maximum number of ECGs</label>
                  <select
                    id="train-campaign-length"
                    value={campaignLength}
                    onChange={(event) => onLengthChange(Number(event.target.value))}
                    disabled={loading}
                  >
                    {[...visibleLengths, ...extendedLengths].map((length) => (
                      <option value={length} key={length}>Up to {length.toLocaleString()}</option>
                    ))}
                  </select>
                </details>
              ) : null}
            </fieldset>

            <div className={styles.planSummary}>
              <div><span>Topic</span><strong>{selectedTopic?.label ?? "Not selected"}</strong></div>
              <div><span>Skill</span><strong>{selectedSkillMeta?.label ?? "Not selected"}</strong></div>
              <div><span>Set</span><strong>Up to {campaignLength.toLocaleString()} ECGs</strong></div>
            </div>

            {!poolLoading && !poolAvailable ? (
              <div className={styles.poolWarning} role="status">
                <strong>This exact practice combination is not ready yet.</strong>
                <span>{poolMessage ?? "Choose another skill or topic to continue."}</span>
              </div>
            ) : null}

            <button
              className={`button primary train-start-button ${styles.startButton}`}
              type="button"
              onClick={onStart}
              disabled={loading || poolLoading || !selectedTopic || !poolAvailable}
            >
              {poolLoading ? "Preparing this plan…" : replaceActive ? "Replace saved set and start" : "Start focused practice"}
              {!poolLoading ? <ArrowRight size={17} aria-hidden="true" /> : null}
            </button>
            <p className={styles.startNote}>Your progress is saved after each answer. Hints remain available without revealing the answer first.</p>
          </aside>
        </div>
      </section>
    </main>
  );
}
