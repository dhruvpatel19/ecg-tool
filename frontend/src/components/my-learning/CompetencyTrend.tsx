"use client";

import { BarChart3, RefreshCw } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { api, type CompetencyTrend as CompetencyTrendResponse } from "@/lib/api";
import styles from "./CompetencyTrend.module.css";

type CompetencyTrendProps = {
  objectiveId: string;
  subskill: string;
  label: string;
};

const modeLabels: Record<string, string> = {
  guided: "Guided learning",
  training: "Focused practice",
  rapid: "Rapid check",
  clinical: "Clinical scenario",
};

function dateLabel(value: string) {
  const instant = new Date(value);
  if (Number.isNaN(instant.getTime())) return "Date unavailable";
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(instant);
}

function checkTypeLabel(independent: boolean, status: "verified" | "legacy") {
  if (status === "legacy") return "Older activity";
  return independent ? "Scored ECG check" : "Formative practice";
}

export function CompetencyTrend({ objectiveId, subskill, label }: CompetencyTrendProps) {
  const headingId = `${useId().replaceAll(":", "")}-trend-heading`;
  const [trend, setTrend] = useState<CompetencyTrendResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const requestGeneration = useRef(0);

  useEffect(() => () => { requestGeneration.current += 1; }, []);

  async function loadTrend() {
    if (loading) return;
    const generation = requestGeneration.current + 1;
    requestGeneration.current = generation;
    setLoading(true);
    setError(false);
    try {
      const value = await api.competencyTrend(objectiveId, subskill, 20);
      if (requestGeneration.current === generation) setTrend(value);
    } catch {
      if (requestGeneration.current === generation) {
        setTrend(null);
        setError(true);
      }
    } finally {
      if (requestGeneration.current === generation) setLoading(false);
    }
  }

  const points = useMemo(() => trend?.points ?? [], [trend]);
  const plotted = useMemo(() => points.map((point, index) => ({
    ...point,
    x: points.length === 1 ? 50 : 6 + (index / Math.max(1, points.length - 1)) * 88,
    y: 88 - point.score * 76,
  })), [points]);

  return (
    <details
      className={styles.trend}
      onToggle={(event) => {
        if (event.currentTarget.open && !trend && !loading && !error) void loadTrend();
      }}
    >
      <summary>
        <span><BarChart3 size={16} aria-hidden="true" /><strong>Progress over time</strong></span>
        <small>See completed practice</small>
      </summary>
      <div className={styles.body} aria-labelledby={headingId}>
        <div className={styles.heading}>
          <div><h5 id={headingId}>{label}</h5><p>Each point is one completed skill observation. Filled dots are scored ECG checks.</p></div>
          <div className={styles.legend} aria-label="Practice type legend"><span><i data-independent="true" /> Scored ECG check</span><span><i /> Formative practice</span></div>
        </div>

        {loading ? <div className={styles.status} role="status">Loading skill history…</div> : null}
        {error ? (
          <div className={styles.status} role="alert">
            <span>Performance history is temporarily unavailable.</span>
            <button type="button" onClick={() => void loadTrend()}><RefreshCw size={14} aria-hidden="true" /> Retry</button>
          </div>
        ) : null}
        {!loading && !error && trend && !points.length ? (
          <p className={styles.empty}>No completed practice for this skill yet.</p>
        ) : null}

        {!loading && !error && points.length ? (
          <>
            <div className={styles.chart} aria-hidden="true">
              <span className={styles.high}>100%</span><span className={styles.mid}>50%</span><span className={styles.low}>0%</span>
              <svg viewBox="0 0 100 100" preserveAspectRatio="none">
                <line x1="5" x2="96" y1="12" y2="12" />
                <line x1="5" x2="96" y1="50" y2="50" />
                <line x1="5" x2="96" y1="88" y2="88" />
                {plotted.length > 1 ? (
                  <polyline points={plotted.map((point) => `${point.x},${point.y}`).join(" ")} />
                ) : null}
                {plotted.map((point, index) => (
                  <circle
                    key={`${point.occurredAt}:${index}`}
                    cx={point.x}
                    cy={point.y}
                    r="2.3"
                    data-independent={point.independent || undefined}
                  />
                ))}
              </svg>
            </div>
            <ol className={styles.timeline} aria-label={`${label} check history`}>
              {points.map((point, index) => (
                <li key={`${point.occurredAt}:${index}`}>
                  <span className={styles.marker} data-independent={point.independent || undefined} aria-hidden="true" />
                  <div><strong>{Math.round(point.score * 100)}%</strong><span>{modeLabels[point.mode] ?? point.mode} · {checkTypeLabel(point.independent, point.recordStatus)}</span></div>
                  <time dateTime={point.occurredAt}>{dateLabel(point.occurredAt)}</time>
                </li>
              ))}
            </ol>
            {trend?.hasMore ? <p className={styles.limitNote}>Showing your 20 most recent checks.</p> : null}
          </>
        ) : null}
      </div>
    </details>
  );
}
