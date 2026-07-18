"use client";

import {
  Activity,
  ArrowRight,
  BrainCircuit,
  ChevronDown,
  GraduationCap,
  Info,
  RefreshCw,
  ScanLine,
  Search,
  Stethoscope,
  TimerReset,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import {
  api,
  type CompetencyObjective,
  type LearningActivityItem,
  type LearningActivityMode,
} from "@/lib/api";
import { conceptLabel } from "@/lib/coordinates";
import { competencyPracticeHref } from "@/lib/competencyRoutes";
import { competencySkillLabel as skillLabel } from "@/lib/learning/skillLabels";
import styles from "./ActivityPanel.module.css";

type OutcomeFilter = "all" | "scored" | "unverified";
type ReviewFilter = "all" | "recommended" | "not_recommended";
type PresentedCompetency = {
  objectiveId: string;
  subskill: string;
  evidence: "formative" | "independent" | "legacy_unverified";
};

export type ActivityPanelProps = {
  /** Reuse an already-loaded competency map; omit to let the panel fetch practice routes independently. */
  competencyObjectives?: CompetencyObjective[];
};

const modeFilters: Array<{ mode: LearningActivityMode; label: string }> = [
  { mode: "all", label: "All" },
  { mode: "guided", label: "Guided" },
  { mode: "training", label: "Focused" },
  { mode: "rapid", label: "Rapid" },
  { mode: "clinical", label: "Clinical" },
];

const modePresentation = {
  guided: { label: "Guided lesson", Icon: GraduationCap },
  training: { label: "Focused practice", Icon: BrainCircuit },
  rapid: { label: "Rapid practice", Icon: TimerReset },
  clinical: { label: "Clinical case", Icon: Stethoscope },
} as const;

function evidenceLabel(item: LearningActivityItem) {
  if (item.evidence === "independent") return "Scored check";
  if (item.evidence === "formative") return "Formative practice";
  return "Older record";
}

function competencyEvidenceLabel(evidence: PresentedCompetency["evidence"]) {
  if (evidence === "independent") return "Scored check";
  if (evidence === "formative") return "Practice";
  return "Older record";
}

function evidenceInterpretation(item: LearningActivityItem) {
  if (item.evidence === "independent") {
    return "This scored check updates your skill progress.";
  }
  if (item.evidence === "formative") {
    return "This practice helps Luna choose what to suggest next. It does not change your scored progress.";
  }
  return "This older record stays in your history but does not change your skill progress.";
}

function supportInterpretation(item: LearningActivityItem) {
  if (item.assistance === "assisted") {
    return "You used guidance during this practice.";
  }
  if (item.assistance === "unassisted") {
    return "No guidance was used during this practice.";
  }
  return "Guidance use was not recorded for this activity.";
}

function confidenceInterpretation(item: LearningActivityItem) {
  if (item.confidence === null) return "No confidence rating was saved for this activity.";
  if (item.confidence <= 2) return `${item.confidence}/5 · You felt unsure after this activity.`;
  if (item.confidence === 3) return "3/5 · You felt somewhat confident after this activity.";
  return `${item.confidence}/5 · You felt confident after this activity.`;
}

function outcomeInterpretation(item: LearningActivityItem) {
  if (item.score === null) {
    return "A score was not saved for this activity. It is not counted as 0.";
  }
  if (item.reviewRecommended) {
    return `${Math.round(item.score * 100)}% · Luna suggests another short practice.`;
  }
  return `${Math.round(item.score * 100)}% · Saved to your history.`;
}

function occurredLabel(value: string) {
  const instant = new Date(value);
  if (Number.isNaN(instant.getTime())) return "Time unavailable";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(instant);
}

function presentedCompetencies(item: LearningActivityItem): PresentedCompetency[] {
  const recorded = item.testedCompetencies?.length
    ? item.testedCompetencies
    : item.objectiveId && item.subskill
    ? [{ objectiveId: item.objectiveId, subskill: item.subskill, evidence: item.evidence }]
    : [];

  const seen = new Set<string>();
  return recorded.filter((competency) => {
    const key = `${competency.objectiveId}:${competency.subskill}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function objectiveName(objectiveId: string, objectiveLabels: Map<string, string>) {
  return objectiveLabels.get(objectiveId) ?? conceptLabel(objectiveId);
}

function activityTitle(
  item: LearningActivityItem,
  competencies: PresentedCompetency[],
  objectiveLabels: Map<string, string>,
) {
  const primary = competencies[0];
  if (primary) return objectiveName(primary.objectiveId, objectiveLabels);
  return item.objectiveId
    ? objectiveName(item.objectiveId, objectiveLabels)
    : modePresentation[item.mode].label;
}

function activityContext(competencies: PresentedCompetency[], fallbackSubskill: string | null) {
  const primary = competencies[0];
  if (!primary) return skillLabel(fallbackSubskill);
  const additionalCount = competencies.length - 1;
  return additionalCount > 0
    ? `${skillLabel(primary.subskill)} · ${additionalCount} more ${additionalCount === 1 ? "skill" : "skills"}`
    : skillLabel(primary.subskill);
}

export function ActivityPanel({ competencyObjectives }: ActivityPanelProps = {}) {
  const generatedId = useId().replaceAll(":", "");
  const headingId = `${generatedId}-learning-activity-heading`;
  const filterScopeId = `${generatedId}-activity-filter-scope`;
  const [mode, setMode] = useState<LearningActivityMode>("all");
  const [items, setItems] = useState<LearningActivityItem[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [query, setQuery] = useState("");
  const [outcomeFilter, setOutcomeFilter] = useState<OutcomeFilter>("all");
  const [reviewFilter, setReviewFilter] = useState<ReviewFilter>("all");
  const [fetchedObjectives, setFetchedObjectives] = useState<CompetencyObjective[]>([]);
  const [practiceRoutesLoading, setPracticeRoutesLoading] = useState(competencyObjectives === undefined);
  const [practiceRoutesFailed, setPracticeRoutesFailed] = useState(false);
  const activityGenerationRef = useRef(0);
  const paginationRequestRef = useRef<{ generation: number; cursor: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    const requestGeneration = activityGenerationRef.current + 1;
    activityGenerationRef.current = requestGeneration;
    paginationRequestRef.current = null;
    setLoading(true);
    setLoadingMore(false);
    setError(null);
    api.learningActivity(mode, 20)
      .then((page) => {
        if (cancelled || activityGenerationRef.current !== requestGeneration) return;
        setItems(page.items);
        setCursor(page.nextCursor);
        setHasMore(page.hasMore);
      })
      .catch(() => {
        if (cancelled || activityGenerationRef.current !== requestGeneration) return;
        setItems([]);
        setCursor(null);
        setHasMore(false);
        setError("Your activity history could not be loaded. Your saved work is unchanged.");
      })
      .finally(() => {
        if (!cancelled && activityGenerationRef.current === requestGeneration) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [mode, retryKey]);

  useEffect(() => {
    let cancelled = false;
    if (competencyObjectives !== undefined) {
      setFetchedObjectives([]);
      setPracticeRoutesLoading(false);
      setPracticeRoutesFailed(false);
      return () => { cancelled = true; };
    }

    setPracticeRoutesLoading(true);
    setPracticeRoutesFailed(false);
    api.competencies()
      .then((response) => {
        if (!cancelled) setFetchedObjectives(response.objectives);
      })
      .catch(() => {
        if (cancelled) return;
        setFetchedObjectives([]);
        setPracticeRoutesFailed(true);
      })
      .finally(() => {
        if (!cancelled) setPracticeRoutesLoading(false);
      });
    return () => { cancelled = true; };
  }, [competencyObjectives]);

  const routeObjectives = competencyObjectives ?? fetchedObjectives;
  const objectiveLabels = useMemo(
    () => new Map(routeObjectives.map((objective) => [objective.objectiveId, objective.label])),
    [routeObjectives],
  );
  const practiceRoutes = useMemo(() => {
    const routes = new Map<string, string>();
    routeObjectives.forEach((objective) => {
      objective.subskills.forEach((cell) => {
        const href = competencyPracticeHref(cell.independentReceipt, "/home?panel=activity");
        if (href) routes.set(`${objective.objectiveId}:${cell.subskill}`, href);
      });
    });
    return routes;
  }, [routeObjectives]);

  const displayedItems = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return items.filter((item) => {
      if (outcomeFilter === "scored" && item.score === null) return false;
      if (outcomeFilter === "unverified" && item.score !== null) return false;
      if (reviewFilter === "recommended" && !item.reviewRecommended) return false;
      if (reviewFilter === "not_recommended" && item.reviewRecommended) return false;
      if (!normalized) return true;

      const competencies = presentedCompetencies(item);
      const searchable = [
        modePresentation[item.mode].label,
        item.objectiveId ? conceptLabel(item.objectiveId) : "",
        item.objectiveId ? objectiveLabels.get(item.objectiveId) ?? "" : "",
        skillLabel(item.subskill),
        ...competencies.flatMap((competency) => [
          conceptLabel(competency.objectiveId),
          objectiveLabels.get(competency.objectiveId) ?? "",
          skillLabel(competency.subskill),
        ]),
      ].join(" ").toLocaleLowerCase();
      return searchable.includes(normalized);
    });
  }, [items, objectiveLabels, outcomeFilter, query, reviewFilter]);

  const localFiltersActive = Boolean(query.trim()) || outcomeFilter !== "all" || reviewFilter !== "all";
  const statusText = useMemo(() => {
    if (loading) return "Loading your history…";
    if (error && !items.length) return error;
    if (!items.length) {
      return mode === "all"
        ? "No older activity yet."
        : `No ${modeFilters.find((item) => item.mode === mode)?.label.toLowerCase()} activity yet.`;
    }
    const visible = displayedItems.length;
    return `${visible} of ${items.length} loaded ${items.length === 1 ? "activity" : "activities"} match${hasMore ? "; more history is available" : ""}.`;
  }, [displayedItems.length, error, hasMore, items.length, loading, mode]);

  async function loadMore() {
    if (!cursor || loadingMore) return;
    const request = { generation: activityGenerationRef.current, cursor };
    if (paginationRequestRef.current?.generation === request.generation) return;
    paginationRequestRef.current = request;
    setLoadingMore(true);
    setError(null);
    try {
      const page = await api.learningActivity(mode, 20, request.cursor);
      if (paginationRequestRef.current !== request || activityGenerationRef.current !== request.generation) return;
      setItems((current) => {
        const seen = new Set(current.map((item) => item.id));
        return [...current, ...page.items.filter((item) => !seen.has(item.id))];
      });
      setCursor(page.nextCursor);
      setHasMore(page.hasMore);
    } catch {
      if (paginationRequestRef.current !== request || activityGenerationRef.current !== request.generation) return;
      setError("More activity could not be loaded. The items already shown are still available.");
    } finally {
      if (paginationRequestRef.current === request) {
        paginationRequestRef.current = null;
        setLoadingMore(false);
      }
    }
  }

  function clearLocalFilters() {
    setQuery("");
    setOutcomeFilter("all");
    setReviewFilter("all");
  }

  // A brand-new learner already sees the single session empty state above this
  // section. Do not follow it with an empty toolbar and a second empty message.
  if (!loading && !error && mode === "all" && items.length === 0) return null;

  if (loading && items.length === 0) {
    return (
      <section className={styles.panel} aria-label="Activity details">
        <div className={styles.initialStatus} role="status">
          <Activity size={19} aria-hidden="true" />
          <span><strong>Loading activity details…</strong><small>Your filters will appear when your recent practice is ready.</small></span>
        </div>
      </section>
    );
  }

  if (error && items.length === 0) {
    return (
      <section className={styles.panel} aria-label="Activity details">
        <div className={styles.error} role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => setRetryKey((value) => value + 1)}><RefreshCw size={15} aria-hidden="true" /> Retry</button>
        </div>
      </section>
    );
  }

  return (
    <section className={styles.panel} aria-labelledby={headingId}>
      <header className={styles.heading}>
        <div>
          <p className="eyebrow">Activity details</p>
          <h2 id={headingId}><Activity size={19} aria-hidden="true" /> Explore your activity</h2>
          <p>Search and filter practice details, including scores and skills.</p>
        </div>
      </header>

      <details className={styles.evidenceLegend} aria-label="How activity affects progress">
        <summary className={styles.legendSummary}>
          <Info size={18} aria-hidden="true" />
          <span className={styles.legendIntro}>
            <strong>What the activity labels mean</strong>
            <span>See when practice changes your skill progress.</span>
          </span>
          <ChevronDown className={styles.legendChevron} size={17} aria-hidden="true" />
        </summary>
        <dl>
          <div data-evidence="independent"><dt>Scored check</dt><dd>Updates the skill progress you see on your dashboard.</dd></div>
          <div data-evidence="formative"><dt>Formative practice</dt><dd>Helps Luna choose what to suggest next without changing scored progress.</dd></div>
          <div data-evidence="legacy_unverified"><dt>Older record</dt><dd>Stays in your history without changing current progress.</dd></div>
        </dl>
      </details>

      <div className={styles.filterBar}>
        <div className={styles.modeFilters} role="group" aria-label="Filter activity by practice type">
          {modeFilters.map((filter) => (
            <button
              type="button"
              key={filter.mode}
              aria-pressed={mode === filter.mode}
              className={mode === filter.mode ? styles.activeFilter : ""}
              onClick={() => {
                if (mode === filter.mode) return;
                activityGenerationRef.current += 1;
                paginationRequestRef.current = null;
                setLoading(true);
                setLoadingMore(false);
                setError(null);
                setMode(filter.mode);
                setItems([]);
                setCursor(null);
                setHasMore(false);
              }}
            >
              {filter.label}
            </button>
          ))}
        </div>
        <label className={styles.searchField} htmlFor={`${generatedId}-activity-search`}>
          <span>Search recent history</span>
          <span className={styles.searchControl}>
            <Search size={16} aria-hidden="true" />
            <input
              id={`${generatedId}-activity-search`}
              type="search"
              aria-describedby={filterScopeId}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Skill or topic"
            />
          </span>
        </label>
        <label htmlFor={`${generatedId}-outcome-filter`}>
          <span>Score</span>
          <select id={`${generatedId}-outcome-filter`} aria-describedby={filterScopeId} value={outcomeFilter} onChange={(event) => setOutcomeFilter(event.target.value as OutcomeFilter)}>
            <option value="all">All scores</option>
            <option value="scored">Scored</option>
            <option value="unverified">Not scored</option>
          </select>
        </label>
        <label htmlFor={`${generatedId}-review-filter`}>
          <span>Follow-up</span>
          <select id={`${generatedId}-review-filter`} aria-describedby={filterScopeId} value={reviewFilter} onChange={(event) => setReviewFilter(event.target.value as ReviewFilter)}>
            <option value="all">All activity</option>
            <option value="recommended">Review suggested</option>
            <option value="not_recommended">No review suggested</option>
          </select>
        </label>
        {localFiltersActive ? <button className={styles.clearFilters} type="button" onClick={clearLocalFilters}>Clear filters</button> : null}
        <p id={filterScopeId}>Search includes the latest {items.length} activit{items.length === 1 ? "y" : "ies"} shown below. Load older activity to search further back.</p>
      </div>

      <div className={styles.results} aria-busy={loading || loadingMore}>
        <p className="sr-only" role="status" aria-live="polite">{statusText}</p>
        {loading ? (
          <div className={styles.loading} role="status" aria-label="Loading older activity">
            <span /><span /><span />
          </div>
        ) : null}

        {!loading && !error && !items.length ? (
          <div className={styles.empty}>
            <div><strong>No older activity in this view.</strong><p>Your completed practice will appear here as your history grows.</p></div>
          </div>
        ) : null}

        {!loading && items.length > 0 && !displayedItems.length ? (
          <div className={styles.filteredEmpty}>
            <Search size={21} aria-hidden="true" />
            <div><strong>No loaded activity matches.</strong><p>{hasMore ? "Clear a filter or load more to search further back." : "Clear a filter or try a broader skill name."}</p></div>
            <button type="button" onClick={clearLocalFilters}>Clear filters</button>
          </div>
        ) : null}

        {displayedItems.length ? (
          <div className={styles.list} data-testid="activity-list">
          {displayedItems.map((item) => {
            const presentation = modePresentation[item.mode];
            const Icon = presentation.Icon;
            const competencies = presentedCompetencies(item);
            return (
              <details key={item.id} className={styles.item} data-evidence={item.evidence} data-review={item.reviewRecommended || undefined} data-testid="activity-item">
                <summary>
                  <span className={styles.modeIcon} aria-hidden="true"><Icon size={17} /></span>
                  <span className={styles.itemCopy}>
                    <span className={styles.itemTitle}>
                      <strong>{activityTitle(item, competencies, objectiveLabels)}</strong>
                      <span>{presentation.label}</span>
                    </span>
                    <span className={styles.itemLine}>{activityContext(competencies, item.subskill)} · {occurredLabel(item.occurredAt)}</span>
                    <span className={styles.tags}>
                      <span>{evidenceLabel(item)}</span>
                      {item.review?.sessionStatus === "abandoned" ? <span>Partial round</span> : null}
                      {item.assistance === "assisted" ? <span>Support used</span> : null}
                      {item.mode !== "clinical" && item.confidence !== null ? <span>Confidence {item.confidence}/5</span> : null}
                    </span>
                  </span>
                  <span className={styles.result}>
                    <strong>{item.score === null ? "—" : `${Math.round(item.score * 100)}%`}</strong>
                    <small>{item.score === null ? "Not scored" : item.reviewRecommended ? "Review suggested" : "Completed"}</small>
                  </span>
                  <span className={styles.expandCue}>View details <ChevronDown size={16} aria-hidden="true" /></span>
                </summary>

                <div className={styles.detailsBody}>
                  <h3 className={styles.outcomeHeading}>What happened</h3>

                  <dl className={styles.interpretationGrid}>
                    <div><dt>Score</dt><dd>{outcomeInterpretation(item)}</dd></div>
                    {item.mode !== "clinical" ? <div><dt>Confidence</dt><dd>{confidenceInterpretation(item)}</dd></div> : null}
                    <div><dt>Guidance</dt><dd>{supportInterpretation(item)}</dd></div>
                    <div><dt>Progress</dt><dd>{evidenceInterpretation(item)}</dd></div>
                  </dl>

                  {item.review ? (
                    <div className={styles.reviewAction}>
                      <div>
                        <strong>{item.review.sessionStatus === "abandoned" ? "Submitted ECG available" : "Question review available"}</strong>
                        <span>{item.review.sessionStatus === "abandoned" ? "This answer was committed before the round ended early." : "Reopen the exact ECG, your answer, and its feedback."}</span>
                      </div>
                      <Link href={`/home/review/${encodeURIComponent(item.review.sessionRef)}/attempt/${item.review.attemptIndex}`}>
                        <ScanLine size={15} aria-hidden="true" /> Review question &amp; ECG <ArrowRight size={14} aria-hidden="true" />
                      </Link>
                    </div>
                  ) : null}

                  <section className={styles.competencyDetails} aria-labelledby={`${generatedId}-${item.id.replaceAll(/[^a-zA-Z0-9_-]/g, "-")}-competencies`}>
                    <div className={styles.detailHeading}>
                      <div><strong id={`${generatedId}-${item.id.replaceAll(/[^a-zA-Z0-9_-]/g, "-")}-competencies`}>Skills practiced</strong><span>Skills included in this activity.</span></div>
                      {item.reviewRecommended ? <span className={styles.revisitBadge}>Practice again</span> : null}
                    </div>
                    {competencies.length ? (
                      <ul className={styles.competencyList}>
                        {competencies.map((competency, index) => {
                          const name = objectiveName(competency.objectiveId, objectiveLabels);
                          const href = practiceRoutes.get(`${competency.objectiveId}:${competency.subskill}`);
                          return (
                            <li key={`${competency.objectiveId}:${competency.subskill}:${index}`}>
                              <span className={styles.competencyIndex} aria-hidden="true">{index + 1}</span>
                              <span className={styles.competencyCopy}>
                                <strong>{name}</strong>
                                <span>{skillLabel(competency.subskill)} · {competencyEvidenceLabel(competency.evidence)}</span>
                              </span>
                              {href ? (
                                <Link href={href} aria-label={`Practice ${name}: ${skillLabel(competency.subskill)}`}>
                                  Practice this skill <ArrowRight size={14} aria-hidden="true" />
                                </Link>
                              ) : (
                                <span className={styles.routeUnavailable}>{practiceRoutesLoading
                                  ? "Finding practice…"
                                  : practiceRoutesFailed
                                    ? "Practice is temporarily unavailable"
                                    : "No matching practice is available"}</span>
                              )}
                            </li>
                          );
                        })}
                      </ul>
                    ) : (
                      <p className={styles.noCompetencies}>No skill details were saved for this activity.</p>
                    )}
                  </section>
                </div>
              </details>
            );
          })}
          </div>
        ) : null}

        {error && items.length ? <p className={styles.inlineError} role="alert">{error}</p> : null}
        {hasMore ? (
          <button className={styles.loadMore} type="button" disabled={loadingMore} onClick={() => void loadMore()}>
            {loadingMore ? "Loading more…" : "Load older activity"}
          </button>
        ) : null}
      </div>
    </section>
  );
}
