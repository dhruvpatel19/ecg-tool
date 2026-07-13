"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { WaveformResponse } from "@/lib/types";

// A read-only single-lead rhythm strip pinned under the 12-lead for rhythm/triage items.
const W = 1200;
const H = 120;
const AMP_MIN = -2;
const AMP_MAX = 2;

export function PinnedRhythmStrip({ caseId, lead = "II" }: { caseId: string; lead?: string }) {
  const [data, setData] = useState<WaveformResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .waveform(caseId, 0, 10, [lead])
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch(() => {
        if (!cancelled) setData(null);
      });
    return () => {
      cancelled = true;
    };
  }, [caseId, lead]);

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
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Lead ${lead} rhythm strip`} preserveAspectRatio="none">
        <rect x={0} y={0} width={W} height={H} fill="#fffafa" />
        {path ? <path d={path} fill="none" stroke="#c43c36" strokeWidth={1.6} strokeLinejoin="round" /> : null}
      </svg>
    </div>
  );
}
