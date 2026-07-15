"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { EcgCapability, WaveformResponse } from "@/lib/types";

// A read-only single-lead rhythm strip pinned under the 12-lead for rhythm/triage items.
const W = 1200;
const H = 120;
const AMP_MIN = -2;
const AMP_MAX = 2;

export function PinnedRhythmStrip({ ecgRef, sessionId, lead = "II" }: { ecgRef: EcgCapability; sessionId: string; lead?: string }) {
  const [data, setData] = useState<WaveformResponse | null>(null);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");
  const [retryVersion, setRetryVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoadState("loading");
    setData(null);
    api
      .waveform(ecgRef, 0, 10, [lead], { kind: "clinical", sessionId })
      .then((d) => {
        if (!cancelled) {
          const hasPoints = d.leads?.some((entry) => entry.points?.length > 0);
          setData(hasPoints ? d : null);
          setLoadState(hasPoints ? "ready" : "error");
        }
      })
      .catch(() => {
        if (!cancelled) {
          setData(null);
          setLoadState("error");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [ecgRef, sessionId, lead, retryVersion]);

  const points = data?.leads?.[0]?.points ?? [];
  const duration = data?.durationSec ?? 10;
  const scale = H / (AMP_MAX - AMP_MIN);
  const mid = H / 2;
  const path = points
    .map((p, i) => {
      const x = (p.timeSec / duration) * W;
      const y = mid - p.amplitudeMv * scale;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <div className="clinical-strip panel" aria-label={`Rhythm strip lead ${lead}`}>
      <div className="clinical-strip-label">Rhythm strip · {lead}</div>
      {loadState === "loading" ? (
        <div className="empty-state" role="status" aria-live="polite">
          Loading the magnified rhythm strip…
        </div>
      ) : loadState === "error" ? (
        <div className="empty-state" role="alert">
          <p>The magnified rhythm strip could not be loaded. The main ECG is unchanged.</p>
          <button className="button subtle" type="button" onClick={() => setRetryVersion((value) => value + 1)}>
            Retry rhythm strip
          </button>
        </div>
      ) : (
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Lead ${lead} rhythm strip`} preserveAspectRatio="none">
          <rect x={0} y={0} width={W} height={H} fill="#fffafa" />
          {path ? <path d={path} fill="none" stroke="#c43c36" strokeWidth={1.6} strokeLinejoin="round" /> : null}
        </svg>
      )}
    </div>
  );
}
