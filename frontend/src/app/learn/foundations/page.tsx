"use client";

import { ArrowLeft, CheckCircle2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, type PathwayProgressItem } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { FOUNDATIONS_PATHWAY_ID } from "@/lib/pathways";
import { readFoundationsProgress, validFoundationSceneIds } from "@/lib/progress";
import styles from "./foundations.module.css";

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

type SafeFoundationSnapshot = {
  completed: string[];
  skipped: string[];
  current: number;
  bestAccuracy: number;
  nv: Record<string, unknown>;
  testedOut: Record<string, unknown>;
};

function safeFoundationSnapshot(
  snapshot: FoundationsMessage["stateSnapshot"] | undefined,
): SafeFoundationSnapshot {
  const skipped = validFoundationSceneIds(snapshot?.skipped);
  const skippedSet = new Set(skipped);
  return {
    completed: validFoundationSceneIds(snapshot?.completed).filter((sceneId) => !skippedSet.has(sceneId)),
    skipped,
    current: Number.isInteger(snapshot?.current) ? Math.max(0, Math.min(12, Number(snapshot?.current))) : 0,
    bestAccuracy: Math.max(0, Number(snapshot?.bestAccuracy ?? 0) || 0),
    nv: snapshot?.nv && typeof snapshot.nv === "object" ? snapshot.nv : {},
    testedOut: snapshot?.testedOut && typeof snapshot.testedOut === "object" ? snapshot.testedOut : {},
  };
}

function storeFoundationSnapshot(
  storageKey: string,
  bestKey: string,
  snapshot: SafeFoundationSnapshot,
) {
  let local: Record<string, unknown> = {};
  try { local = JSON.parse(window.localStorage.getItem(storageKey) ?? "{}"); } catch { local = {}; }
  window.localStorage.setItem(storageKey, JSON.stringify({
    ...local,
    completed: Object.fromEntries(snapshot.completed.map((sceneId) => [sceneId, true])),
    skipped: Object.fromEntries(snapshot.skipped.map((sceneId) => [sceneId, true])),
    current: snapshot.current,
    nv: snapshot.nv,
    testedOut: snapshot.testedOut,
  }));
  window.localStorage.setItem(bestKey, String(snapshot.bestAccuracy));
}

function foundationProgressItem(
  snapshot: SafeFoundationSnapshot,
  totalScenes = 13,
  currentId: string | null = null,
): PathwayProgressItem {
  return {
    pathwayId: FOUNDATIONS_PATHWAY_ID,
    moduleId: "foundations",
    sceneId: "foundations-progress",
    status: snapshot.completed.length >= totalScenes
      ? "complete"
      : snapshot.completed.length > 0 || snapshot.current > 0
        ? "attempted"
        : "viewed",
    activeInteractionIndex: snapshot.current,
    completedActionIds: snapshot.completed,
    state: {
      foundationState: snapshot,
      completedScenes: snapshot.completed.length,
      totalScenes,
      currentId,
      bestAccuracy: snapshot.bestAccuracy,
    },
  };
}

export default function FoundationsModulePage() {
  const { user, identityKey } = useAuth();
  const [completed, setCompleted] = useState(0);
  const [total, setTotal] = useState(13);
  const [done, setDone] = useState(false);
  const [iframeReady, setIframeReady] = useState(false);
  const [frameHeight, setFrameHeight] = useState(720);
  const [syncError, setSyncError] = useState<string | null>(null);
  const recordedEvidence = useRef(new Set<string>());
  const lastProgressSignature = useRef("");
  const progressSaveChain = useRef<Promise<unknown>>(Promise.resolve());
  const iframeRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    if (!iframeReady) return;
    const frame = iframeRef.current;
    if (!frame) return;

    let resizeObserver: ResizeObserver | null = null;
    let animationFrame = 0;

    const measure = () => {
      window.cancelAnimationFrame(animationFrame);
      animationFrame = window.requestAnimationFrame(() => {
        try {
          const documentElement = frame.contentDocument?.documentElement;
          const body = frame.contentDocument?.body;
          if (!documentElement || !body) return;
          const measuredHeight = Math.ceil(Math.max(
            documentElement.scrollHeight,
            body.scrollHeight,
            documentElement.getBoundingClientRect().height,
            body.getBoundingClientRect().height,
          ));
          if (measuredHeight > 0) {
            setFrameHeight((current) => Math.abs(current - measuredHeight) > 1 ? measuredHeight : current);
          }
        } catch {
          // Same-origin Foundations is expected in production. If that contract
          // changes, the conservative minimum height below remains usable.
        }
      });
    };

    const connect = () => {
      resizeObserver?.disconnect();
      try {
        const documentElement = frame.contentDocument?.documentElement;
        const body = frame.contentDocument?.body;
        const head = frame.contentDocument?.head;
        if (!documentElement || !body || !head) return;

        let embeddedStyle = frame.contentDocument?.getElementById("trace-foundations-seamless-embed") as HTMLStyleElement | null;
        if (!embeddedStyle) {
          embeddedStyle = frame.contentDocument!.createElement("style");
          embeddedStyle.id = "trace-foundations-seamless-embed";
          embeddedStyle.textContent = `
            html, body { height: auto !important; min-height: 0 !important; }
            body { overflow: hidden !important; }
            .app { height: auto !important; min-height: 0 !important; }
            .stage { flex: none !important; min-height: 0 !important; align-items: start !important; }
            .scene-col, .tutor-col { height: auto !important; min-height: 0 !important; overflow: visible !important; }
            .scene-scroll, .tutor-stream { flex: none !important; max-height: none !important; overflow: visible !important; }
          `;
          head.appendChild(embeddedStyle);
        }

        resizeObserver = new ResizeObserver(measure);
        resizeObserver.observe(documentElement);
        resizeObserver.observe(body);
        measure();
      } catch {
        // Keep the embedded module available even if the seamless-size contract
        // cannot be installed; its minimum height remains a safe fallback.
      }
    };

    frame.addEventListener("load", connect);
    window.addEventListener("resize", measure);
    if (frame.contentDocument?.readyState === "complete") connect();

    return () => {
      frame.removeEventListener("load", connect);
      window.removeEventListener("resize", measure);
      resizeObserver?.disconnect();
      window.cancelAnimationFrame(animationFrame);
    };
  }, [iframeReady, identityKey]);

  useEffect(() => {
    let cancelled = false;
    setIframeReady(false);
    setSyncError(null);
    if (!user) return () => { cancelled = true; };
    const storageKey = `foundations_state_v1:${identityKey}`;
    const bestKey = `found_best:${identityKey}`;

    api.pathwayProgress(user.userId, FOUNDATIONS_PATHWAY_ID)
      .then((response) => {
        if (cancelled) return;
        const item = response.items.find((entry) => entry.moduleId === "foundations");
        const snapshot = item?.state?.foundationState as FoundationsMessage["stateSnapshot"] | undefined;
        if (snapshot) {
          const serverSnapshot = safeFoundationSnapshot(snapshot);
          storeFoundationSnapshot(storageKey, bestKey, serverSnapshot);
        }
        const seed = readFoundationsProgress(13, identityKey);
        setCompleted(seed.completedScenes);
        setTotal(seed.totalScenes);
        setDone(seed.done);
      })
      .catch(() => setSyncError("Your Foundations progress could not be loaded. Check your connection and try again."))
      .finally(() => { if (!cancelled) setIframeReady(true); });
    return () => { cancelled = true; };
  }, [identityKey, user]);

  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      if (e.origin !== window.location.origin) return;
      if (e.source !== iframeRef.current?.contentWindow) return;
      const data = e.data as FoundationsMessage;
      if (data?.source !== "foundations") return;
      if (!user) return;
      if (typeof data.completedScenes === "number") setCompleted(data.completedScenes);
      if (typeof data.totalScenes === "number") setTotal(data.totalScenes);
      if (typeof data.done === "boolean") setDone(data.done);
      if (["ready", "progress", "complete"].includes(data.type ?? "") && data.stateSnapshot) {
        const safeSnapshot = safeFoundationSnapshot(data.stateSnapshot);
        const signature = JSON.stringify(safeSnapshot);
        if (signature !== lastProgressSignature.current) {
          lastProgressSignature.current = signature;
          const item = foundationProgressItem(safeSnapshot, data.totalScenes ?? 13, data.currentId ?? null);
          // Preserve message order so a slower earlier request can never replace
          // a newer nested state snapshot on the server.
          progressSaveChain.current = progressSaveChain.current
            .catch(() => undefined)
            .then(() => api.savePathwayProgress(user.userId, [item], "server"))
            .then(() => setSyncError(null))
            .catch(() => setSyncError("Foundations remains open, but your progress could not be synced. Check your connection and try again."));
        }
      }
      if (data.type === "learning-evidence" && data.eventId && data.sceneId && data.interactionId && data.concept) {
        if (recordedEvidence.current.has(data.eventId)) return;
        const subskills = (data.subskills ?? []).filter((value) => GUIDED_SUBSKILLS.has(value));
        if (!subskills.length || typeof data.score !== "number" || typeof data.correct !== "boolean") return;
        recordedEvidence.current.add(data.eventId);
        const provenance = data.caseProvenance ?? "authored_simulation";
        void api.recordGuidedEvent({
          learnerId: user.userId,
          // The embedded curriculum emits a unique id for each genuine
          // checkpoint interaction. Preserve it at the server boundary so an
          // exact network replay deduplicates while a later, otherwise
          // identical attempt after refresh remains a new learning event.
          eventKey: `foundations:${data.eventId}`.slice(0, 160),
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
    <div className={styles.page}>
      <header className={styles.header}>
        <Link className="button subtle" href="/learn">
          <ArrowLeft size={15} aria-hidden="true" /> Modules
        </Link>
        <div className={styles.identity}>
          <strong>Foundations of the ECG Read</strong>
          <span className="muted">Module 1 of 10 · guided</span>
        </div>
        <span className={`pill ${styles.progress}`}>
          {done ? <><CheckCircle2 size={13} aria-hidden="true" /> Complete</> : `${completed}/${total} scenes`}
        </span>
      </header>

      {syncError ? <div className={`warning ${styles.notice}`} role="alert">{syncError}</div> : null}

      <p id="foundations-frame-help" className={styles.frameHelp}>The interactive Foundations lesson follows. Tab moves into its controls; Shift plus Tab returns to the module controls.</p>

      {iframeReady ? <div className={styles.frameBoundary}>
        <iframe
          ref={iframeRef}
          src={`/foundations/index.html?owner=${encodeURIComponent(identityKey)}`}
          title="Foundations of the ECG Read"
          aria-describedby="foundations-frame-help"
          scrolling="no"
          className={styles.frame}
          style={{ height: `${frameHeight}px` }}
        />
      </div> : <div className={`panel pad ${styles.loading}`} role="status">Loading private Foundations progress…</div>}
    </div>
  );
}
