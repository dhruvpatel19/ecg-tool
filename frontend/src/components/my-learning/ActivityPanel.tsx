"use client";

import { Activity, BrainCircuit, GraduationCap, RefreshCw, Stethoscope, TimerReset } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  api,
  type LearningActivityItem,
  type LearningActivityMode,
} from "@/lib/api";
import { conceptLabel } from "@/lib/coordinates";
import styles from "./ActivityPanel.module.css";

const filters: Array<{ mode: LearningActivityMode; label: string }> = [
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

function skillLabel(value: string | null) {
  if (!value) return "Skill not recorded";
  const labels: Record<string, string> = {
    recognize: "Identify",
    localize: "Locate on the trace",
    measure: "Measure",
    discriminate: "Tell apart",
    explain_mechanism: "Explain mechanism",
    synthesize: "Complete interpretation",
    apply_in_context: "Apply in context",
    calibrate_confidence: "Calibrate confidence",
  };
  return labels[value] ?? value.replaceAll("_", " ");
}

function evidenceLabel(item: LearningActivityItem) {
  if (item.evidence === "independent") return "Independent check";
  if (item.evidence === "formative") return "Formative practice";
  return "Legacy record · not used for mastery";
}

function occurredLabel(value: string) {
  const instant = new Date(value);
  if (Number.isNaN(instant.getTime())) return "Time unavailable";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(instant);
}

export function ActivityPanel() {
  const [mode, setMode] = useState<LearningActivityMode>("all");
  const [items, setItems] = useState<LearningActivityItem[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api.learningActivity(mode, 20)
      .then((page) => {
        if (cancelled) return;
        setItems(page.items);
        setCursor(page.nextCursor);
        setHasMore(page.hasMore);
      })
      .catch(() => {
        if (cancelled) return;
        setItems([]);
        setCursor(null);
        setHasMore(false);
        setError("Your activity history could not be loaded. Your saved work is unchanged.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [mode, retryKey]);

  const statusText = useMemo(() => {
    if (loading) return "Loading completed learning activity…";
    if (error) return error;
    if (!items.length) return mode === "all" ? "No completed learning activity yet." : `No completed ${filters.find((item) => item.mode === mode)?.label.toLowerCase()} activity yet.`;
    return `${items.length} completed ${items.length === 1 ? "item" : "items"} shown${hasMore ? "; more available" : ""}.`;
  }, [error, hasMore, items.length, loading, mode]);

  async function loadMore() {
    if (!cursor || loadingMore) return;
    setLoadingMore(true);
    setError(null);
    try {
      const page = await api.learningActivity(mode, 20, cursor);
      setItems((current) => {
        const seen = new Set(current.map((item) => item.id));
        return [...current, ...page.items.filter((item) => !seen.has(item.id))];
      });
      setCursor(page.nextCursor);
      setHasMore(page.hasMore);
    } catch {
      setError("More activity could not be loaded. The items already shown are still available.");
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <section className={styles.panel} aria-labelledby="learning-activity-heading">
      <header className={styles.heading}>
        <div>
          <p className="eyebrow">Practice history</p>
          <h2 id="learning-activity-heading"><Activity size={19} aria-hidden="true" /> Completed activity</h2>
          <p>Scores, confidence, assistance, and evidence type—without exposing case answers.</p>
        </div>
        <div className={styles.filters} role="group" aria-label="Filter completed activity">
          {filters.map((filter) => (
            <button
              type="button"
              key={filter.mode}
              aria-pressed={mode === filter.mode}
              className={mode === filter.mode ? styles.activeFilter : ""}
              onClick={() => {
                if (mode === filter.mode) return;
                setLoading(true);
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
      </header>

      <p className="sr-only" role="status" aria-live="polite">{statusText}</p>
      {loading ? (
        <div className={styles.loading} role="status" aria-label="Loading completed learning activity">
          <span /><span /><span />
        </div>
      ) : null}

      {!loading && error && !items.length ? (
        <div className={styles.error} role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => setRetryKey((value) => value + 1)}><RefreshCw size={15} aria-hidden="true" /> Retry</button>
        </div>
      ) : null}

      {!loading && !error && !items.length ? (
        <div className={styles.empty}>
          <Activity size={22} aria-hidden="true" />
          <div><strong>No completed work in this view yet.</strong><p>Submitted Guided tasks, Focused ECGs, Rapid reads, and Clinical cases will appear here.</p></div>
        </div>
      ) : null}

      {items.length ? (
        <div className={styles.list} data-testid="activity-list">
          {items.map((item) => {
            const presentation = modePresentation[item.mode];
            const Icon = presentation.Icon;
            const testedCompetencies = item.testedCompetencies?.length
              ? item.testedCompetencies
              : item.objectiveId && item.subskill
                ? [{ objectiveId: item.objectiveId, subskill: item.subskill, evidence: item.evidence }]
                : [];
            const groupedAssessment = item.kind === "ecg_attempt" && testedCompetencies.length > 1;
            const objectiveLabels = Array.from(new Set(
              testedCompetencies.map((competency) => conceptLabel(competency.objectiveId)),
            ));
            const groupedTitle = item.mode === "rapid"
              ? "Rapid ECG"
              : item.mode === "clinical"
                ? "Clinical case"
                : "Focused ECG";
            return (
              <article key={item.id} className={styles.item} data-evidence={item.evidence} data-testid="activity-item">
                <span className={styles.modeIcon} aria-hidden="true"><Icon size={17} /></span>
                <div className={styles.itemCopy}>
                  <div className={styles.itemTitle}>
                    <strong>{groupedAssessment ? `${groupedTitle} · ${testedCompetencies.length} skills checked` : item.objectiveId ? conceptLabel(item.objectiveId) : presentation.label}</strong>
                    <span>{presentation.label}</span>
                  </div>
                  <p>{groupedAssessment ? objectiveLabels.join(" · ") : skillLabel(item.subskill)} · {occurredLabel(item.occurredAt)}</p>
                  <div className={styles.tags}>
                    <span>{evidenceLabel(item)}</span>
                    <span>{item.assistance === "assisted" ? "Support used" : item.assistance === "unassisted" ? "Unassisted" : "Assistance not recorded"}</span>
                    {item.confidence ? <span>Confidence {item.confidence}/5</span> : null}
                  </div>
                </div>
                <div className={styles.result} data-review={item.reviewRecommended || undefined}>
                  <strong>{item.score === null ? "—" : `${Math.round(item.score * 100)}%`}</strong>
                  <small>{item.score === null ? "Unverified" : item.reviewRecommended ? "Revisit" : "Complete"}</small>
                </div>
              </article>
            );
          })}
        </div>
      ) : null}

      {error && items.length ? <p className={styles.inlineError} role="alert">{error}</p> : null}
      {hasMore ? (
        <button className={styles.loadMore} type="button" disabled={loadingMore} onClick={() => void loadMore()}>
          {loadingMore ? "Loading more…" : "Load more activity"}
        </button>
      ) : null}
    </section>
  );
}
