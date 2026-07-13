"use client";

import { ArrowLeft, CheckCircle2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, type PathwayProgressItem } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { FOUNDATIONS_PATHWAY_ID } from "@/lib/pathways";
import { readFoundationsProgress } from "@/lib/progress";

type FoundationsMessage = {
  source?: string;
  type?: string;
  completedScenes?: number;
  totalScenes?: number;
  done?: boolean;
  eventId?: string;
  sceneId?: string;
  interactionId?: string;
  concept?: string;
  subskills?: string[];
  score?: number;
  correct?: boolean;
  attempts?: number;
  assistance?: "independent" | "scaffolded";
  hintsUsed?: number;
  caseId?: string | null;
  caseProvenance?: "real_eligible" | "real_reviewed" | "authored_simulation" | "contrast_only" | "none";
  caseEligible?: boolean;
  misconceptions?: string[];
  currentIndex?: number;
  currentId?: string | null;
  bestAccuracy?: number;
  stateSnapshot?: {
    completed?: string[];
    skipped?: string[];
    current?: number;
    bestAccuracy?: number;
    nv?: Record<string, unknown>;
    testedOut?: Record<string, unknown>;
  };
};

const GUIDED_SUBSKILLS = new Set(["recognize", "localize", "measure", "discriminate", "explain_mechanism", "synthesize", "apply_in_context", "calibrate_confidence"]);

export default function FoundationsModulePage() {
  const { user, identityKey } = useAuth();
  const [completed, setCompleted] = useState(0);
  const [total, setTotal] = useState(13);
  const [done, setDone] = useState(false);
  const [iframeReady, setIframeReady] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);
  const recordedEvidence = useRef(new Set<string>());
  const lastProgressSignature = useRef("");
  const progressSaveChain = useRef<Promise<unknown>>(Promise.resolve());
  const iframeRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    let cancelled = false;
    setIframeReady(false);
    setSyncError(null);
    const storageKey = `foundations_state_v1:${identityKey}`;
    const bestKey = `found_best:${identityKey}`;

    if (!user) {
      // One-time migration of the former unscoped guest preview. Never import it
      // into a signed-in account because its owner cannot be established.
      if (!window.localStorage.getItem(storageKey)) {
        const legacy = window.localStorage.getItem("foundations_state_v1");
        const legacyBest = window.localStorage.getItem("found_best");
        if (legacy) window.localStorage.setItem(storageKey, legacy);
        if (legacyBest) window.localStorage.setItem(bestKey, legacyBest);
      }
      const seed = readFoundationsProgress(13, identityKey);
      setCompleted(seed.completedScenes);
      setTotal(seed.totalScenes);
      setDone(seed.done);
      setIframeReady(true);
      return () => { cancelled = true; };
    }

    api.pathwayProgress(user.userId, FOUNDATIONS_PATHWAY_ID)
      .then((response) => {
        if (cancelled) return;
        const item = response.items.find((entry) => entry.moduleId === "foundations");
        const snapshot = item?.state?.foundationState as FoundationsMessage["stateSnapshot"] | undefined;
        if (snapshot) {
          let local: Record<string, unknown> = {};
          try { local = JSON.parse(window.localStorage.getItem(storageKey) ?? "{}"); } catch { local = {}; }
          const completedMap = Object.fromEntries((snapshot.completed ?? []).map((sceneId) => [sceneId, true]));
          const skippedMap = Object.fromEntries((snapshot.skipped ?? []).map((sceneId) => [sceneId, true]));
          window.localStorage.setItem(storageKey, JSON.stringify({
            ...local,
            completed: completedMap,
            skipped: skippedMap,
            current: snapshot.current ?? 0,
            nv: snapshot.nv ?? local.nv ?? {},
            testedOut: snapshot.testedOut ?? local.testedOut ?? {},
          }));
          window.localStorage.setItem(bestKey, String(snapshot.bestAccuracy ?? 0));
        }
        const seed = readFoundationsProgress(13, identityKey);
        setCompleted(seed.completedScenes);
        setTotal(seed.totalScenes);
        setDone(seed.done);
      })
      .catch((error: Error) => setSyncError(`Private Foundations progress could not load. ${error.message}`))
      .finally(() => { if (!cancelled) setIframeReady(true); });
    return () => { cancelled = true; };
  }, [identityKey, user]);

  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      if (e.origin !== window.location.origin) return;
      if (e.source !== iframeRef.current?.contentWindow) return;
      const data = e.data as FoundationsMessage;
      if (data?.source !== "foundations") return;
      if (typeof data.completedScenes === "number") setCompleted(data.completedScenes);
      if (typeof data.totalScenes === "number") setTotal(data.totalScenes);
      if (typeof data.done === "boolean") setDone(data.done);
      if ((data.type === "progress" || data.type === "complete") && user && data.stateSnapshot) {
        const signature = JSON.stringify(data.stateSnapshot);
        if (signature !== lastProgressSignature.current) {
          lastProgressSignature.current = signature;
          const item: PathwayProgressItem = {
            pathwayId: FOUNDATIONS_PATHWAY_ID,
            moduleId: "foundations",
            sceneId: "foundations-progress",
            status: data.done ? "complete" : (data.completedScenes ?? 0) > 0 || (data.currentIndex ?? 0) > 0 ? "attempted" : "viewed",
            activeInteractionIndex: Math.max(0, data.currentIndex ?? 0),
            completedActionIds: data.stateSnapshot.completed ?? [],
            state: {
              foundationState: data.stateSnapshot,
              completedScenes: data.completedScenes ?? 0,
              totalScenes: data.totalScenes ?? 13,
              currentId: data.currentId ?? null,
              bestAccuracy: data.bestAccuracy ?? 0,
            },
          };
          // Preserve message order so a slower earlier request can never replace
          // a newer nested state snapshot on the server.
          progressSaveChain.current = progressSaveChain.current
            .catch(() => undefined)
            .then(() => api.savePathwayProgress(user.userId, [item]))
            .catch((error: Error) => {
              setSyncError(`Foundations remains open, but server sync failed. ${error.message}`);
            });
        }
      }
      if (data.type === "learning-evidence" && data.eventId && data.sceneId && data.interactionId && data.concept) {
        if (recordedEvidence.current.has(data.eventId)) return;
        const subskills = (data.subskills ?? []).filter((value) => GUIDED_SUBSKILLS.has(value));
        if (!subskills.length || typeof data.score !== "number" || typeof data.correct !== "boolean") return;
        recordedEvidence.current.add(data.eventId);
        const provenance = data.caseProvenance ?? "authored_simulation";
        void api.recordGuidedEvent({
          learnerId: "demo",
          moduleId: "foundations",
          sceneId: data.sceneId,
          interactionId: data.interactionId,
          concept: data.concept,
          subskills,
          score: Math.max(0, Math.min(1, data.score)),
          correct: data.correct,
          attempts: Math.max(1, data.attempts ?? 1),
          assistance: data.assistance === "scaffolded" ? "scaffolded" : "independent",
          hintsUsed: Math.max(0, data.hintsUsed ?? 0),
          // Foundations produces guided receipts. Synthetic visual activities never
          // request independent transfer, even when completed without a hint.
          evidenceLevel: "guided",
          caseId: data.caseId ?? null,
          caseProvenance: provenance,
          caseEligible: provenance === "authored_simulation" ? false : Boolean(data.caseEligible),
          misconceptions: data.misconceptions ?? [],
        }).catch(() => {
          // Iframe progress remains saved locally; the next successful interaction
          // will continue sending precise receipts without changing visual mastery.
        });
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [user]);

  return (
    <div style={{ height: "calc(100vh - 48px)", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <header
        style={{
          display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap",
          padding: "0 4px 12px", borderBottom: "1px solid var(--border, #e2e5e9)", marginBottom: 12,
        }}
      >
        <Link className="button subtle" href="/learn">
          <ArrowLeft size={15} aria-hidden="true" /> Modules
        </Link>
        <div style={{ minWidth: 0 }}>
          <strong style={{ display: "block" }}>Foundations — Reading an ECG</strong>
          <span className="muted" style={{ fontSize: "0.82rem" }}>Module 1 of 10 · guided</span>
        </div>
        <span className="pill" style={{ marginLeft: "auto" }}>
          {done ? <><CheckCircle2 size={13} aria-hidden="true" /> Complete</> : `${completed}/${total} scenes`}
        </span>
      </header>

      {syncError ? <div className="warning" role="alert" style={{ marginBottom: 10 }}>{syncError}</div> : null}

      {iframeReady ? <iframe
        ref={iframeRef}
        src={`/foundations/index.html?owner=${encodeURIComponent(identityKey)}`}
        title="Foundations — Reading an ECG"
        style={{ flex: 1, width: "100%", border: 0, borderRadius: 12, background: "#faf9f5", minHeight: 0 }}
      /> : <div className="panel pad" role="status">Loading private Foundations progress…</div>}
    </div>
  );
}
