"use client";

import {
  ArrowLeft,
  ArrowRight,
  BadgeCheck,
  BookOpen,
  BrainCircuit,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Clock3,
  FlaskConical,
  ListTree,
  MessageCircleQuestion,
  RotateCcw,
  ScanLine,
  Sparkles,
  Target,
  X,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ECGViewer } from "@/components/ECGViewer";
import { TutorChat } from "@/components/TutorChat";
import { LearningInteractionRenderer } from "@/components/learning/LearningInteractionRenderer";
import {
  FoundationsTeachingRecap,
  FoundationsTeachingSequence,
  foundationsSceneHasTeaching,
} from "@/components/learning/FoundationsTeachingSequence";
import {
  ModuleTeachingRecap,
  ModuleTeachingSequence,
} from "@/components/learning/ModuleTeachingSequence";
import {
  LearningWorkspaceShell,
  ResponseRail,
  SessionBar,
  TutorDrawer,
  TutorTrigger,
  WaveformPane,
  WorkspaceBody,
  WorkspaceNotices,
} from "@/components/layout/LearningWorkspaceShell";
import { api, ApiError, type PathwayProgressItem } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { guidedHandoffHref } from "@/lib/learning/handoffTargets";
import { moduleSceneHasTeaching, resolveTutorTemplate } from "@/lib/learning/modulePedagogy";
import { evidenceRevealsSolution, interactionEvidenceResolved } from "@/lib/learning/interactionTypes";
import type { InteractionEvidence, LearningInteraction, ProductionModule, ProductionScene } from "@/lib/learning/interactionTypes";
import type { CasePacket, CaseSummary, ViewerAction, ViewerTaskEvidence, ViewerTaskSpec } from "@/lib/types";
import type { ECGPoint } from "@/lib/coordinates";
import { PRODUCTION_PATHWAY_ID } from "@/lib/pathways";
import { useLearningPreferences } from "@/lib/useLearningPreferences";
import styles from "./ProductionModuleExperience.module.css";

type SceneStatus = "not-started" | "viewed" | "attempted" | "needs-review" | "complete" | "skipped";

type GuidedSaveStatus = "saving" | "practice_saved" | "progress_updated" | "local_only";

type GuidedEventPayload = {
  learnerId: string;
  eventKey: string;
  moduleId: string;
  sceneId: string;
  interactionId: string;
  concept: string;
  subskills: string[];
  score: number;
  correct: boolean;
  attempts: number;
  assistance: "independent" | "scaffolded";
  hintsUsed: number;
  evidenceLevel: "guided" | "independent_transfer";
  caseId: string | null;
  guidedContext: string | null;
  caseProvenance: "real_eligible" | "authored_simulation" | "contrast_only";
  caseEligible: boolean;
  misconceptions: string[];
};

type GuidedOutboxEntry = {
  eventKey: string;
  payload: GuidedEventPayload;
};

const guidedOutboxKey = (learnerId: string) => `trace-guided-evidence-outbox-v1:${learnerId}`;

function readGuidedOutbox(learnerId: string): GuidedOutboxEntry[] {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(guidedOutboxKey(learnerId)) ?? "[]") as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((entry): entry is GuidedOutboxEntry => {
      if (!entry || typeof entry !== "object") return false;
      const candidate = entry as Partial<GuidedOutboxEntry>;
      return typeof candidate.eventKey === "string"
        && candidate.eventKey.length > 0
        && candidate.payload?.learnerId === learnerId
        && candidate.payload.eventKey === candidate.eventKey;
    });
  } catch {
    return [];
  }
}

function writeGuidedOutbox(learnerId: string, entries: GuidedOutboxEntry[]) {
  window.localStorage.setItem(guidedOutboxKey(learnerId), JSON.stringify(entries));
}

type SceneRuntime = {
  status: SceneStatus;
  activeInteractionIndex: number;
  revealedMechanismCount: number;
  teachingStep: number;
  teachingVisitedSteps: number[];
  teachingComplete: boolean;
  evidence: Record<string, InteractionEvidence>;
  equivalentRetryCount: number;
  assistedInteractionIds: string[];
  reviewLater: boolean;
};

type RuntimeState = Record<string, Record<string, SceneRuntime>>;

const PATHWAY_ID = PRODUCTION_PATHWAY_ID;

function emptyRuntime(): SceneRuntime {
  return {
    status: "not-started",
    activeInteractionIndex: 0,
    revealedMechanismCount: 1,
    teachingStep: 0,
    teachingVisitedSteps: [0],
    teachingComplete: false,
    evidence: {},
    equivalentRetryCount: 0,
    assistedInteractionIds: [],
    reviewLater: false,
  };
}

function runtimeToProgressItems(runtime: RuntimeState): PathwayProgressItem[] {
  return Object.entries(runtime).flatMap(([moduleId, scenes]) =>
    Object.entries(scenes).map(([sceneId, scene]) => ({
      pathwayId: PATHWAY_ID,
      moduleId,
      sceneId,
      status: scene.status,
      activeInteractionIndex: scene.activeInteractionIndex,
      completedActionIds: Object.entries(scene.evidence)
        .filter(([, evidence]) => evidence.correct)
        .map(([interactionId]) => interactionId),
      state: scene as unknown as Record<string, unknown>,
    })),
  );
}

function progressItemsToRuntime(items: PathwayProgressItem[]): RuntimeState {
  const runtime: RuntimeState = {};
  for (const item of items) {
    const state = item.state ?? {};
    runtime[item.moduleId] ??= {};
    const reviewLater = state.reviewLater === true && item.status !== "complete";
    const savedEvidence = state.evidence && typeof state.evidence === "object"
      ? state.evidence as Record<string, InteractionEvidence>
      : {};
    const teachingVisitedSteps = Array.isArray(state.teachingVisitedSteps)
      ? Array.from(new Set(state.teachingVisitedSteps.filter((step): step is number => Number.isInteger(step) && step >= 0)))
      : [0];
    // Progress written before the teaching studio existed must remain
    // resumable. Existing task evidence proves that the learner had already
    // entered practice, so migration unlocks it without erasing their work.
    const legacyPracticeStarted = Object.keys(savedEvidence).length > 0
      || item.activeInteractionIndex > 0
      || ["attempted", "needs-review", "complete"].includes(item.status);
    runtime[item.moduleId][item.sceneId] = {
      ...emptyRuntime(),
      ...(state as Partial<SceneRuntime>),
      status: reviewLater ? "skipped" : item.status,
      reviewLater,
      activeInteractionIndex: item.activeInteractionIndex,
      teachingVisitedSteps: teachingVisitedSteps.length ? teachingVisitedSteps : [0],
      teachingComplete: typeof state.teachingComplete === "boolean"
        ? state.teachingComplete
        : legacyPracticeStarted,
      evidence: savedEvidence,
    };
  }
  return runtime;
}

function newestResumableScene(items: PathwayProgressItem[], moduleId: string): string | null {
  return items
    .filter((item) => item.moduleId === moduleId
      && item.state?.reviewLater !== true
      && !["not-started", "complete", "skipped"].includes(item.status))
    .sort((left, right) => (
      (right.updatedAt ?? "").localeCompare(left.updatedAt ?? "")
      || (right.createdAt ?? "").localeCompare(left.createdAt ?? "")
      || left.sceneId.localeCompare(right.sceneId)
    ))[0]?.sceneId ?? null;
}

function statusLabel(status: SceneStatus) {
  if (status === "complete") return "Complete";
  if (status === "needs-review") return "Needs review";
  if (status === "skipped") return "Skipped";
  if (status === "attempted") return "Attempted";
  if (status === "viewed") return "In progress";
  return "Not started";
}

function skillLabel(value: string) {
  const labels: Record<string, string> = {
    apply_in_context: "use in context",
    calibrate_confidence: "calibrate confidence",
    discriminate: "tell apart",
    explain_mechanism: "explain",
    localize: "locate",
    measure: "measure",
    recognize: "identify",
    synthesize: "complete interpretation",
  };
  return labels[value] ?? value.replaceAll("_", " ");
}

function taskForInteraction(interaction: LearningInteraction): ViewerTaskSpec | undefined {
  if (interaction.kind === "point") return { mode: "point", prompt: interaction.gradePrompt, concept: interaction.concept, allowedLeads: interaction.allowedLeads };
  if (interaction.kind === "region") return { mode: "region", prompt: interaction.prompt, concept: interaction.concept, allowedLeads: interaction.allowedLeads, minimumDurationMs: interaction.minimumDurationMs };
  if (interaction.kind === "caliper") return { mode: "caliper", prompt: interaction.prompt, measurement: interaction.measurement, allowedLeads: interaction.target.lead ? [interaction.target.lead] : undefined };
  if (interaction.kind === "march") return { mode: "march", prompt: interaction.prompt, target: interaction.target, minimumMarkers: interaction.minimumMarkers };
  return undefined;
}

function caliperRoiConcept(measurement: "rr" | "pr" | "qrs" | "qt" | "custom") {
  if (measurement === "pr") return "pr_interval";
  if (measurement === "qrs") return "qrs_complex";
  if (measurement === "qt") return "qt_segment";
  return null;
}

type Eligibility = {
  eligible: boolean;
  reasons: string[];
  mode: "target" | "contrast" | "simulation" | "locked";
};

type GuidedEligibilityResult = {
  eligible: boolean;
  missingRequirementCount: number;
  message: string;
};

const FOUNDATIONS_ROUTE = [
  { label: "Signal", detail: "Confirm calibration and decide what the tracing can support." },
  { label: "Rate", detail: "Check regularity, then choose the right way to estimate rate." },
  { label: "Source", detail: "Find atrial activity and test how it relates to each QRS." },
  { label: "Axis", detail: "Use limb-lead polarity to estimate the main QRS direction." },
  { label: "Timing", detail: "Measure PR, QRS, and QT from the correct boundaries." },
  { label: "ST–T", detail: "Describe recovery changes against a stable baseline." },
  { label: "Synthesis", detail: "Combine the observations into one concise description." },
] as const;

function FoundationsRoutePreview({
  activeStep,
  visitedSteps,
  onSelectStep,
  onBeginPractice,
}: {
  activeStep: number;
  visitedSteps: number[];
  onSelectStep: (step: number) => void;
  onBeginPractice: () => void;
}) {
  const step = FOUNDATIONS_ROUTE[activeStep];
  const allVisited = FOUNDATIONS_ROUTE.every((_, index) => visitedSteps.includes(index));
  const nextUnvisited = FOUNDATIONS_ROUTE.findIndex((_, index) => !visitedSteps.includes(index));

  return (
    <section className={styles.routePreview} aria-labelledby="foundations-route-title">
      <div className={styles.routeSignal}>
        <svg viewBox="0 0 1000 170" role="img" aria-labelledby="foundations-route-title foundations-route-description">
          <title id="foundations-route-title">The seven-step ECG reading route</title>
          <desc id="foundations-route-description">A stylized ECG signal introduces a repeatable sequence from signal quality through synthesis.</desc>
          <defs>
            <pattern id="foundations-small-grid" width="20" height="20" patternUnits="userSpaceOnUse">
              <path d="M 20 0 L 0 0 0 20" fill="none" stroke="currentColor" strokeWidth="0.7" />
            </pattern>
            <pattern id="foundations-large-grid" width="100" height="100" patternUnits="userSpaceOnUse">
              <rect width="100" height="100" fill="url(#foundations-small-grid)" />
              <path d="M 100 0 L 0 0 0 100" fill="none" stroke="currentColor" strokeWidth="1.2" />
            </pattern>
          </defs>
          <rect className={styles.routeGrid} width="1000" height="170" fill="url(#foundations-large-grid)" />
          <path
            className={styles.routeTraceShadow}
            d="M0 96 L72 96 L87 91 L98 96 L127 96 L139 111 L151 32 L165 132 L179 76 L197 96 L273 96 L288 91 L299 96 L328 96 L340 111 L352 32 L366 132 L380 76 L398 96 L474 96 L489 91 L500 96 L529 96 L541 111 L553 32 L567 132 L581 76 L599 96 L675 96 L690 91 L701 96 L730 96 L742 111 L754 32 L768 132 L782 76 L800 96 L876 96 L891 91 L902 96 L931 96 L943 111 L955 32 L969 132 L983 76 L1000 96"
          />
          <path
            className={styles.routeTrace}
            pathLength="1"
            d="M0 96 L72 96 L87 91 L98 96 L127 96 L139 111 L151 32 L165 132 L179 76 L197 96 L273 96 L288 91 L299 96 L328 96 L340 111 L352 32 L366 132 L380 76 L398 96 L474 96 L489 91 L500 96 L529 96 L541 111 L553 32 L567 132 L581 76 L599 96 L675 96 L690 91 L701 96 L730 96 L742 111 L754 32 L768 132 L782 76 L800 96 L876 96 L891 91 L902 96 L931 96 L943 111 L955 32 L969 132 L983 76 L1000 96"
          />
        </svg>
        <div className={styles.routeStatement} aria-live="polite">
          <span>{String(activeStep + 1).padStart(2, "0")}</span>
          <p><strong>{step.label}</strong>{step.detail}</p>
        </div>
      </div>
      <ol className={styles.routeSteps} aria-label="Explore the ECG reading route">
        {FOUNDATIONS_ROUTE.map((item, index) => (
          <li key={item.label}>
            <button type="button" aria-pressed={index === activeStep} onClick={() => onSelectStep(index)}>
              <span>{visitedSteps.includes(index) ? <Check size={14} /> : index + 1}</span>
              <strong>{item.label}</strong>
            </button>
          </li>
        ))}
      </ol>
      <div className={styles.routeActions}>
        <p>{allVisited ? "You have seen the full reading route. Rebuild it from memory next." : `${visitedSteps.length} of ${FOUNDATIONS_ROUTE.length} checkpoints explored`}</p>
        {allVisited
          ? <button className="button primary" type="button" onClick={onBeginPractice}>Try the first check <ArrowRight size={15} /></button>
          : <button className="button primary" type="button" onClick={() => onSelectStep(nextUnvisited >= 0 ? nextUnvisited : Math.min(activeStep + 1, FOUNDATIONS_ROUTE.length - 1))}>Next checkpoint <ArrowRight size={15} /></button>}
      </div>
    </section>
  );
}

function guidedEligibilityRequest(scene: ProductionScene) {
  const measurements = new Set<string>();
  const rois = new Set<string>();
  const leads = new Set(scene.caseContract?.requiredLeads ?? []);
  for (const evidence of scene.caseContract?.requiredEvidence ?? []) {
    if (evidence.startsWith("measurement:")) measurements.add(evidence.slice("measurement:".length));
    if (evidence.startsWith("roi:")) rois.add(evidence.slice("roi:".length));
  }
  for (const interaction of scene.interactions) {
    if (interaction.kind === "point" || interaction.kind === "region") {
      rois.add(interaction.concept);
      interaction.allowedLeads?.forEach((lead) => leads.add(lead));
    }
    if ((interaction.kind === "caliper" || interaction.kind === "numeric_entry")
      && interaction.target.source === "packet_measurement"
      && interaction.target.measurementKey) {
      measurements.add(interaction.target.measurementKey);
    }
    if (interaction.kind === "caliper") {
      if (interaction.target.lead) leads.add(interaction.target.lead);
      const roi = caliperRoiConcept(interaction.measurement);
      if (roi) rois.add(roi);
    }
  }
  return {
    minimumTier: scene.caseContract?.minimumTier ?? "B",
    requiredLeads: [...leads],
    requiredMeasurements: [...measurements],
    requiredRois: [...rois],
    requiresPerBeatLandmarks: scene.interactions.some((interaction) => interaction.kind === "march"),
  };
}

function caseEligibility(
  scene: ProductionScene,
  packet: CasePacket | null,
  requestedUnavailable: boolean,
  serverEligibility: GuidedEligibilityResult | null,
): Eligibility {
  const contract = scene.caseContract;
  if (!contract) return { eligible: true, reasons: [], mode: "simulation" };
  const reasons: string[] = [];
  if (!packet) reasons.push("No ECG is loaded.");
  if (requestedUnavailable) reasons.push(`A suitable ${contract.requestedConcept.replaceAll("_", " ")} example is not available right now.`);
  if (packet && !serverEligibility) reasons.push("This ECG does not include everything needed for this question.");
  if (serverEligibility && !serverEligibility.eligible) reasons.push(serverEligibility.message);
  const uniqueReasons = Array.from(new Set(reasons));
  if (!uniqueReasons.length) return { eligible: true, reasons: [], mode: "target" };
  return {
    eligible: false,
    reasons: uniqueReasons,
    mode: contract.fallback === "contrast_only" ? "contrast" : contract.fallback === "authored_simulation" ? "simulation" : "locked",
  };
}

function eligibilityMessage(eligibility: Eligibility) {
  if (eligibility.mode === "contrast") return "Use this ECG as an example; it does not contain everything needed to score this particular question.";
  if (eligibility.mode === "simulation") return "This practice example teaches the method. You’ll apply it to a new ECG later.";
  return "A suitable ECG is not available for this question right now. You can continue and return later.";
}

type ModuleNavigationReference = Pick<ProductionModule, "id" | "shortTitle">;

export function ProductionModuleExperience({ module, totalModules, priorModule, nextModule }: {
  module: ProductionModule;
  totalModules: number;
  priorModule?: ModuleNavigationReference;
  nextModule?: ModuleNavigationReference;
}) {
  const { user, loading: authLoading } = useAuth();
  const { preferences: learningPreferences } = useLearningPreferences();
  const authenticatedUserId = user?.userId;
  const [sceneIndex, setSceneIndex] = useState(0);
  const [runtime, setRuntime] = useState<RuntimeState>({});
  const [runtimeReady, setRuntimeReady] = useState(false);
  const [pathwaySyncError, setPathwaySyncError] = useState<string | null>(null);
  const [sceneMapOpen, setSceneMapOpen] = useState(false);
  const [referenceOpen, setReferenceOpen] = useState(false);
  const [caseSummary, setCaseSummary] = useState<CaseSummary | null>(null);
  const [packet, setPacket] = useState<CasePacket | null>(null);
  const [guidedContext, setGuidedContext] = useState<string | null>(null);
  const [guidedEligibility, setGuidedEligibility] = useState<GuidedEligibilityResult | null>(null);
  const [caseError, setCaseError] = useState<string | null>(null);
  const [loadingCase, setLoadingCase] = useState(true);
  const [requestedUnavailable, setRequestedUnavailable] = useState(false);
  const [excludedCaseId, setExcludedCaseId] = useState<string | undefined>();
  const [viewerTaskEvidence, setViewerTaskEvidence] = useState<ViewerTaskEvidence | null>(null);
  const [viewerActions, setViewerActions] = useState<ViewerAction[]>([]);
  const [selectedPoint, setSelectedPoint] = useState<ECGPoint | null>(null);
  const [masteryReceipt, setMasteryReceipt] = useState<string | null>(null);
  const [guidedSaveStatus, setGuidedSaveStatus] = useState<GuidedSaveStatus | null>(null);
  const pendingDeepLinkedScene = useRef<string | null>(null);
  const pathwaySaveChain = useRef<Promise<unknown>>(Promise.resolve());
  const guidedOutbox = useRef<GuidedOutboxEntry[]>([]);
  const guidedOutboxFlush = useRef<Promise<void> | null>(null);
  const sceneMapTriggerRef = useRef<HTMLButtonElement | null>(null);
  const sceneMapCloseRef = useRef<HTMLButtonElement | null>(null);
  const referenceTriggerRef = useRef<HTMLButtonElement | null>(null);
  const referenceCloseRef = useRef<HTMLButtonElement | null>(null);
  const scene = module.scenes[sceneIndex];
  const activeSceneRef = useRef({ moduleId: module.id, sceneId: scene.id });
  activeSceneRef.current = { moduleId: module.id, sceneId: scene.id };

  const flushGuidedOutbox = useCallback(() => {
    if (!authenticatedUserId || guidedOutboxFlush.current) return guidedOutboxFlush.current;
    const run = (async () => {
      while (guidedOutbox.current.length > 0) {
        const entry = guidedOutbox.current[0];
        let receipt: Awaited<ReturnType<typeof api.recordGuidedEvent>>;
        try {
          receipt = await api.recordGuidedEvent(entry.payload);
        } catch (error) {
          const active = activeSceneRef.current;
          const permanentRejection = error instanceof ApiError
            && error.status >= 400
            && error.status < 500
            && ![408, 429].includes(error.status);
          if (permanentRejection) {
            guidedOutbox.current = guidedOutbox.current.filter((item) => item.eventKey !== entry.eventKey);
            try {
              writeGuidedOutbox(authenticatedUserId, guidedOutbox.current);
            } catch {
              // The rejected event cannot create a receipt. Continue draining
              // later attempts even if this stale local entry cannot be pruned.
            }
            if (active.moduleId === entry.payload.moduleId && active.sceneId === entry.payload.sceneId) {
              setGuidedSaveStatus("local_only");
              setMasteryReceipt("This answer could not be saved. Please try it again on a fresh tracing.");
            }
            continue;
          }
          if (active.moduleId === entry.payload.moduleId && active.sceneId === entry.payload.sceneId) {
            setGuidedSaveStatus("local_only");
            setMasteryReceipt("This lesson step is queued on this device and will sync when your connection returns.");
          }
          break;
        }
        guidedOutbox.current = guidedOutbox.current.filter((item) => item.eventKey !== entry.eventKey);
        try {
          writeGuidedOutbox(authenticatedUserId, guidedOutbox.current);
        } catch {
          // The server accepted this idempotent event. A stale device copy may
          // replay it, but the event key prevents another learning receipt.
        }
        const active = activeSceneRef.current;
        if (active.moduleId !== entry.payload.moduleId || active.sceneId !== entry.payload.sceneId) continue;
        const independent = receipt.effectiveEvidenceLevel === "independent_transfer"
          ? receipt.receipts.filter((item) => item.evidenceLevel === "independent_transfer")
          : [];
        if (independent.length) {
          setGuidedSaveStatus("progress_updated");
          setMasteryReceipt(`Progress updated for ${independent.map((item) => skillLabel(item.subskill)).join(", ")}.`);
        } else {
          setGuidedSaveStatus("practice_saved");
          setMasteryReceipt("Practice saved. Try the same skill on a fresh mixed ECG when you’re ready.");
        }
      }
    })().finally(() => {
      guidedOutboxFlush.current = null;
    });
    guidedOutboxFlush.current = run;
    return run;
  }, [authenticatedUserId]);

  useEffect(() => {
    if (!authenticatedUserId) {
      guidedOutbox.current = [];
      return;
    }
    guidedOutbox.current = readGuidedOutbox(authenticatedUserId);
    void flushGuidedOutbox();
    const retry = () => { void flushGuidedOutbox(); };
    window.addEventListener("online", retry);
    return () => window.removeEventListener("online", retry);
  }, [authenticatedUserId, flushGuidedOutbox]);

  useEffect(() => {
    if (!sceneMapOpen) return;
    const frame = window.requestAnimationFrame(() => sceneMapCloseRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [sceneMapOpen]);

  useEffect(() => {
    if (!referenceOpen) return;
    const frame = window.requestAnimationFrame(() => referenceCloseRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [referenceOpen]);

  useEffect(() => {
    const requestedScene = new URLSearchParams(window.location.search).get("scene");
    if (requestedScene) {
      const index = module.scenes.findIndex((item) => item.id === requestedScene);
      if (index >= 0) {
        pendingDeepLinkedScene.current = requestedScene;
        setSceneIndex(index);
      }
    }
  }, [module.id, module.scenes]);

  useEffect(() => {
    if (authLoading) return;
    let cancelled = false;
    setRuntimeReady(false);
    setPathwaySyncError(null);
    if (!authenticatedUserId) {
      setRuntime({});
      setRuntimeReady(false);
      return () => { cancelled = true; };
    }

    api.pathwayProgress(authenticatedUserId, PATHWAY_ID)
      .then((response) => {
        if (!cancelled) {
          const serverRuntime = progressItemsToRuntime(response.items);
          setRuntime(serverRuntime);
          if (!pendingDeepLinkedScene.current) {
            const resumableSceneId = newestResumableScene(response.items, module.id);
            const resumable = module.scenes.findIndex((item) => item.id === resumableSceneId);
            if (resumable >= 0) setSceneIndex(resumable);
          }
        }
      })
      .catch(() => {
        if (!cancelled) {
          setRuntime({});
          setPathwaySyncError("Your lesson progress could not be loaded. Check your connection and try again.");
        }
      })
      .finally(() => {
        if (!cancelled) setRuntimeReady(true);
      });
    return () => { cancelled = true; };
  }, [authLoading, authenticatedUserId, module.id, module.scenes]);

  useEffect(() => {
    if (!runtimeReady) return;
    if (pendingDeepLinkedScene.current !== scene.id) return;
    pendingDeepLinkedScene.current = null;
    const timer = window.setTimeout(() => {
      // Case scenes are deliberately ECG-first below the single-column
      // breakpoint. Focusing the semantically earlier lesson heading there
      // leaves keyboard focus off-screen because CSS places that frame after
      // the trace and active question. Keep entry focus visible without
      // sacrificing the ECG-first reading order.
      const compactCaseLayout = Boolean(scene.caseContract)
        && window.matchMedia("(max-width: 840px)").matches;
      const target = document.getElementById(
        compactCaseLayout ? "main-content" : "production-scene-title",
      );
      target?.focus({ preventScroll: true });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [runtimeReady, scene.caseContract, scene.id]);

  const updateSceneRuntime = useCallback((sceneId: string, updater: (current: SceneRuntime) => SceneRuntime) => {
    if (!user) return;
    setRuntime((current) => {
      const nextScene = updater(current[module.id]?.[sceneId] ?? emptyRuntime());
      const next = { ...current, [module.id]: { ...(current[module.id] ?? {}), [sceneId]: nextScene } };
      const item = runtimeToProgressItems({ [module.id]: { [sceneId]: nextScene } });
      pathwaySaveChain.current = pathwaySaveChain.current
        .catch(() => undefined)
        .then(() => api.savePathwayProgress(user.userId, item, "server"))
        .then(() => setPathwaySyncError(null))
        .catch(() => setPathwaySyncError("Your work is still open, but it could not be synced. Check your connection and try again."));
      return next;
    });
  }, [module.id, user]);

  useEffect(() => {
    if (!runtimeReady) return;
    const current = runtime[module.id]?.[scene.id] ?? emptyRuntime();
    if (current.status === "not-started") updateSceneRuntime(scene.id, (value) => ({ ...value, status: "viewed" }));
  }, [module.id, runtime, runtimeReady, scene.id, updateSceneRuntime]);

  useEffect(() => {
    setCaseSummary(null);
    setPacket(null);
    setGuidedContext(null);
    setGuidedEligibility(null);
    setCaseError(null);
    setRequestedUnavailable(false);
    setViewerTaskEvidence(null);
    setViewerActions([]);
    setSelectedPoint(null);
    setMasteryReceipt(null);
    setGuidedSaveStatus(null);
    const contract = scene.caseContract;
    if (!contract) {
      setLoadingCase(false);
      return;
    }
    let cancelled = false;
    setLoadingCase(true);
    api.tutorial(
      contract.selectorLessonId,
      contract.requestedConcept,
      excludedCaseId,
      {
        ...guidedEligibilityRequest(scene),
        casePoolSlot: excludedCaseId && contract.retryCasePoolSlot
          ? contract.retryCasePoolSlot
          : contract.casePoolSlot,
      },
    )
      .then(async (result) => {
        if (cancelled) return;
        setRequestedUnavailable(Boolean(result.selection?.requestedConceptUnavailable));
        setCaseSummary(result.recommendedCase);
        setPacket(result.recommendedPacket);
        setGuidedContext(result.guidedContext);
        setGuidedEligibility(result.guidedEligibility);
      })
      .catch((error: Error) => {
        if (!cancelled) setCaseError(error.message);
      })
      .finally(() => {
        if (!cancelled) setLoadingCase(false);
      });
    return () => { cancelled = true; };
  }, [excludedCaseId, scene]);

  const sceneRuntime = runtime[module.id]?.[scene.id] ?? emptyRuntime();
  const isFoundations = module.id === "foundations";
  const isFoundationsOpening = isFoundations && scene.id === "S0";
  const requiresFoundationsTeaching = isFoundations
    && (isFoundationsOpening || foundationsSceneHasTeaching(scene.id));
  const requiresModuleTeaching = !isFoundations && moduleSceneHasTeaching(module.id, scene);
  // Foundations keeps its deliberate learn-then-practise gate. Later modules
  // show the authored model above the ECG task so returning learners and
  // existing deep links remain usable while the studio can still be completed
  // and collapsed into a recap.
  const practiceReady = !requiresFoundationsTeaching || sceneRuntime.teachingComplete;
  const moduleTeachingActive = requiresModuleTeaching && !sceneRuntime.teachingComplete;
  const teachingFrameActive = (requiresFoundationsTeaching || requiresModuleTeaching)
    && !sceneRuntime.teachingComplete;
  const mechanismGuidanceOffset = learningPreferences?.guidanceLevel === "step_by_step"
    ? 1
    : learningPreferences?.guidanceLevel === "minimal"
      ? -1
      : 0;
  const visibleMechanismCount = Math.max(
    0,
    Math.min(
      scene.copy.mechanismNarration.length,
      sceneRuntime.revealedMechanismCount + mechanismGuidanceOffset,
    ),
  );
  const activeInteractionIndex = Math.min(sceneRuntime.activeInteractionIndex, Math.max(0, scene.interactions.length - 1));
  const activeInteraction = scene.interactions[activeInteractionIndex];
  const activeEvidence = activeInteraction ? sceneRuntime.evidence[activeInteraction.id] : undefined;
  const eligibility = useMemo(
    () => caseEligibility(scene, packet, requestedUnavailable, guidedEligibility),
    [guidedEligibility, packet, requestedUnavailable, scene],
  );

  // Do not accept learner input against an empty client runtime while saved
  // progress is still arriving. A late pathway response could otherwise
  // overwrite a teaching step or answer committed immediately after route load.
  if (!runtimeReady) {
    return (
      <div className="page">
        <section className="panel pad" role="status" aria-live="polite">
          <p className="eyebrow">{module.shortTitle}</p>
          <h1>Loading your lesson…</h1>
          <p>Restoring your place and saved evidence before the module becomes interactive.</p>
        </section>
      </div>
    );
  }

  const waveformInteraction = activeInteraction && ["point", "region", "caliper", "march"].includes(activeInteraction.kind);
  // Foundations uses authored, explanation-linked ECG models for scoring.
  // A server-selected real ECG is contrast material only and must not compete
  // visually with an unrelated authored target. Other modules, and any future
  // Foundations viewer task, retain the full ECG + response-rail layout.
  const showCaseViewer = Boolean(scene.caseContract && practiceReady && (!isFoundations || waveformInteraction));
  const requiresGroundedCase = Boolean(activeInteraction?.subskills.some((subskill) => ["recognize", "localize", "measure", "discriminate", "synthesize", "apply_in_context"].includes(subskill)));
  const caseResolutionComplete = !loadingCase && Boolean(packet || caseError);
  const evidenceBoundaryActive = Boolean(showCaseViewer && activeInteraction && !eligibility.eligible && caseResolutionComplete
    && (waveformInteraction || (eligibility.mode === "locked" && requiresGroundedCase)));
  const viewerTask = waveformInteraction && eligibility.eligible ? taskForInteraction(activeInteraction) : undefined;
  const sceneComplete = sceneRuntime.status === "complete";
  const completedCount = module.scenes.filter((item) => runtime[module.id]?.[item.id]?.status === "complete").length;
  const totalMinutes = module.scenes.reduce((sum, item) => sum + item.minutes, 0);
  const parts = Array.from(new Set(module.scenes.map((item) => item.partId)));
  const unresolvedPrerequisites = (scene.learningContract?.prerequisiteSceneIds ?? []).flatMap((sceneId) => {
    const status = runtime[module.id]?.[sceneId]?.status ?? "not-started";
    return status === "complete" ? [] : [{ sceneId, status }];
  });
  const waypoint = `${module.shortTitle} · ${scene.id} ${scene.copy.title} · action ${activeInteractionIndex + 1}`;
  const tutorTemplateContext = {
    actionNumber: activeInteractionIndex + 1,
    leads: activeInteraction && "allowedLeads" in activeInteraction ? activeInteraction.allowedLeads : undefined,
  };
  const tutorTangentBridge = resolveTutorTemplate(scene.tutor.tangentBridge, tutorTemplateContext);
  const tutorReturnPrompt = resolveTutorTemplate(scene.tutor.returnPrompt, tutorTemplateContext);
  const tutorOpeningPrompt = resolveTutorTemplate(scene.copy.openingTutorMessage, tutorTemplateContext);

  function recordEvidence(evidence: InteractionEvidence) {
    if (!authenticatedUserId) {
      setPathwaySyncError("Your account session could not be verified. Sign in again before saving this step.");
      return;
    }
    const recordedEvidence = sceneRuntime.assistedInteractionIds.includes(evidence.interactionId)
      ? { ...evidence, assistance: "scaffolded" as const, hintsUsed: Math.max(1, evidence.hintsUsed) }
      : evidence;
    updateSceneRuntime(scene.id, (current) => {
      const nextEvidence = { ...current.evidence, [recordedEvidence.interactionId]: recordedEvidence };
      const requiredIds = new Set(scene.completionRule.requiredInteractionIds);
      const required = scene.interactions.filter((interaction) => requiredIds.has(interaction.id));
      const requiredEvidence = required.map((interaction) => nextEvidence[interaction.id]).filter(Boolean);
      const allCorrect = required.length > 0 && required.every((interaction) => nextEvidence[interaction.id]?.correct);
      const allResolved = required.length > 0 && required.every((interaction) => interactionEvidenceResolved(nextEvidence[interaction.id]));
      const includesWorkedSolution = required.some((interaction) => evidenceRevealsSolution(nextEvidence[interaction.id]));
      const allAssessable = required.length > 0 && required.every((interaction) => nextEvidence[interaction.id]?.feedbackBranch !== "not_assessable");
      const meanScore = requiredEvidence.length ? requiredEvidence.reduce((sum, item) => sum + item.score, 0) / requiredEvidence.length : 0;
      const independentOrUnavailable = required.every((interaction) => {
        const item = nextEvidence[interaction.id];
        return item?.assistance === "independent" || item?.feedbackBranch === "not_assessable";
      });
      const independentGate = !scene.completionRule.requireIndependentAttempt || independentOrUnavailable;
      const demonstratedCompletion = allCorrect && meanScore >= scene.completionRule.minimumScore && independentGate;
      // A worked solution closes the lesson action after three unsuccessful
      // tries. It permits navigation, while the preserved incorrect and
      // scaffolded evidence prevents independent or mastery credit.
      const complete = allAssessable && allResolved && (demonstratedCompletion || includesWorkedSolution);
      const hasSubmittedEvidence = Object.values(nextEvidence).some((item) => item.feedbackBranch !== "not_assessable");
      return {
        ...current,
        evidence: nextEvidence,
        reviewLater: false,
        status: complete
          ? "complete"
          : recordedEvidence.feedbackBranch === "not_assessable"
            ? hasSubmittedEvidence ? "attempted" : "viewed"
            : recordedEvidence.correct ? "attempted" : "needs-review",
      };
    });
    if (recordedEvidence.feedbackBranch === "not_assessable") {
      setGuidedSaveStatus(null);
      setMasteryReceipt("This question was not scored because the ECG did not show enough to answer it safely.");
      return;
    }
    const receiptHandoff = scene.handoffs.find((handoff) => activeInteraction?.subskills.includes(handoff.subskill));
    const concept = scene.learningContract?.objectiveId
      ?? receiptHandoff?.concept
      ?? scene.handoffs[0]?.concept
      ?? scene.caseContract?.requestedConcept
      ?? "curriculum_foundation";
    const isFinalRequired = recordedEvidence.correct
      && recordedEvidence.assistance === "independent"
      && !evidenceRevealsSolution(recordedEvidence)
      && scene.completionRule.requiredInteractionIds.every((id) => {
        const item = id === recordedEvidence.interactionId ? recordedEvidence : sceneRuntime.evidence[id];
        return item?.correct && item.assistance === "independent" && !evidenceRevealsSolution(item);
      });
    const evidenceLevel = module.id !== "foundations"
      && isFinalRequired
      && scene.completionRule.requireIndependentAttempt
      && scene.learningContract?.evidenceCeiling === "independent_immediate_candidate"
      ? "independent_transfer"
      : "guided";
    // Every M01 scored action is authored or modeled. A real ECG may be shown
    // beside it as a governed contrast, but its patient identifier must never
    // be attached to an answer that was graded against authored targets.
    const foundationsAuthoredEvidence = module.id === "foundations";
    const caseProvenance = foundationsAuthoredEvidence || !scene.caseContract
      ? "authored_simulation"
      : eligibility.mode === "target"
        ? "real_eligible"
        : eligibility.mode === "contrast"
          ? "contrast_only"
          : "authored_simulation";
    const eventKey = [
      "guided",
      globalThis.crypto.randomUUID(),
      module.id,
      scene.id,
      recordedEvidence.interactionId,
    ].join(":").slice(0, 160);
    const payload: GuidedEventPayload = {
      learnerId: authenticatedUserId,
      eventKey,
      moduleId: module.id,
      sceneId: scene.id,
      interactionId: recordedEvidence.interactionId,
      concept,
      // A Guided receipt is one registered objective cell, not every skill the
      // interaction happens to exercise. Sending unrelated interaction skills
      // under this concept makes the server correctly reject the whole event.
      subskills: receiptHandoff ? [receiptHandoff.subskill] : (activeInteraction?.subskills.slice(0, 1) ?? ["recognize"]),
      score: recordedEvidence.score,
      correct: recordedEvidence.correct,
      attempts: recordedEvidence.attempts,
      assistance: recordedEvidence.assistance,
      hintsUsed: recordedEvidence.hintsUsed,
      evidenceLevel,
      caseId: foundationsAuthoredEvidence ? null : (caseSummary?.caseId ?? null),
      guidedContext: foundationsAuthoredEvidence ? null : guidedContext,
      caseProvenance,
      // Authored simulation is valid formative content, but it is never an
      // eligible real patient case. The server can preserve the guided event
      // without allowing it into independent/retention evidence.
      caseEligible: foundationsAuthoredEvidence ? false : eligibility.eligible,
      misconceptions: recordedEvidence.misconceptions,
    };
    guidedOutbox.current = [...guidedOutbox.current, { eventKey, payload }];
    setGuidedSaveStatus("saving");
    try {
      writeGuidedOutbox(authenticatedUserId, guidedOutbox.current);
    } catch {
      setGuidedSaveStatus("local_only");
      setMasteryReceipt("This answer is waiting to save. Keep this page open until your connection returns.");
    }
    void flushGuidedOutbox();
  }

  function recordTutorAssistance() {
    if (!activeInteraction || activeEvidence) return;
    updateSceneRuntime(scene.id, (current) => ({
      ...current,
      assistedInteractionIds: current.assistedInteractionIds.includes(activeInteraction.id)
        ? current.assistedInteractionIds
        : [...current.assistedInteractionIds, activeInteraction.id],
    }));
    setMasteryReceipt("Tutor help noted. Try a fresh ECG on your own next.");
  }

  function advanceInteraction() {
    if (!interactionEvidenceResolved(activeEvidence)) return;
    updateSceneRuntime(scene.id, (current) => ({
      ...current,
      activeInteractionIndex: Math.min(current.activeInteractionIndex + 1, scene.interactions.length - 1),
    }));
    setViewerTaskEvidence(null);
    document.getElementById("production-active-interaction")?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
  }

  function continueUnavailableScene() {
    updateSceneRuntime(scene.id, (current) => ({ ...current, status: "skipped", reviewLater: true }));
    setMasteryReceipt("This lesson is saved for later and remains available from the lesson map.");
    if (sceneIndex < module.scenes.length - 1) goToScene(sceneIndex + 1);
  }

  function startEquivalentRetry() {
    setExcludedCaseId(caseSummary?.caseId);
    updateSceneRuntime(scene.id, (current) => ({
      ...current,
      status: "viewed",
      reviewLater: false,
      evidence: {},
      activeInteractionIndex: 0,
      equivalentRetryCount: current.equivalentRetryCount + 1,
    }));
    setViewerTaskEvidence(null);
  }

  function goToScene(index: number) {
    if (index < 0 || index >= module.scenes.length) return;
    setSceneIndex(index);
    setSceneMapOpen(false);
    setExcludedCaseId(undefined);
    const next = module.scenes[index];
    window.history.replaceState(null, "", `/learn/${module.id}?scene=${encodeURIComponent(next.id)}`);
    window.setTimeout(() => {
      const compactCaseLayout = Boolean(next.caseContract)
        && window.matchMedia("(max-width: 840px)").matches;
      const target = document.getElementById(
        compactCaseLayout ? "main-content" : "production-scene-title",
      );
      if (compactCaseLayout) {
        window.scrollTo({ top: 0, behavior: "auto" });
      } else {
        target?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
      }
      target?.focus({ preventScroll: true });
    }, 0);
  }

  function closeSceneMap() {
    setSceneMapOpen(false);
    window.requestAnimationFrame(() => sceneMapTriggerRef.current?.focus());
  }

  function openFoundationsReference() {
    if (module.id !== "foundations") return;
    setReferenceOpen(true);
    if (scene.id === "S12") recordTutorAssistance();
  }

  function closeFoundationsReference() {
    setReferenceOpen(false);
    window.requestAnimationFrame(() => referenceTriggerRef.current?.focus());
  }

  function skipScene() {
    updateSceneRuntime(scene.id, (current) => ({ ...current, status: "skipped", reviewLater: true }));
    if (sceneIndex < module.scenes.length - 1) goToScene(sceneIndex + 1);
  }

  function selectTeachingStep(step: number) {
    updateSceneRuntime(scene.id, (current) => ({
      ...current,
      teachingStep: Math.max(0, step),
      teachingVisitedSteps: Array.from(new Set([...current.teachingVisitedSteps, Math.max(0, step)])).sort((left, right) => left - right),
      status: current.status === "not-started" ? "viewed" : current.status,
    }));
  }

  function beginGuidedPractice() {
    updateSceneRuntime(scene.id, (current) => ({
      ...current,
      teachingComplete: true,
      status: current.status === "not-started" ? "viewed" : current.status,
    }));
    window.requestAnimationFrame(() => {
      document.getElementById("production-active-interaction")?.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
        block: "start",
      });
    });
  }

  function reviewTeaching() {
    updateSceneRuntime(scene.id, (current) => ({
      ...current,
      teachingStep: 0,
      teachingVisitedSteps: [0],
      teachingComplete: false,
    }));
    window.requestAnimationFrame(() => {
      document.getElementById("production-scene-title")?.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
        block: "start",
      });
    });
  }

  const completionReceiptLabel = guidedSaveStatus === "progress_updated"
    ? "progress updated"
    : guidedSaveStatus === "practice_saved"
      ? "practice saved"
      : guidedSaveStatus === "local_only"
        ? "lesson saved on this device"
        : guidedSaveStatus === "saving"
          ? "saving practice"
          : "lesson complete";
  const needsIndependentRetry = scene.completionRule.requireIndependentAttempt
    && Object.values(sceneRuntime.evidence).some((item) => item.correct && item.assistance === "scaffolded" && item.feedbackBranch !== "not_assessable")
    && !sceneComplete;

  const workspacePhase = !practiceReady || moduleTeachingActive ? "teaching" : sceneComplete ? "complete" : activeEvidence ? "feedback" : "task";
  const lessonPhaseIndex = !practiceReady || moduleTeachingActive ? 0 : activeEvidence || sceneComplete ? 2 : 1;
  const activeTaskContent = (
    <div id="production-active-interaction" className={`guided-production-checkpoint ${styles.checkpoint}`} tabIndex={-1}>
      <div className={`production-action-progress ${styles.actionProgress}`}>
        <span>{activeInteractionIndex + 1} of {scene.interactions.length}</span>
        <div>{scene.interactions.map((interaction, index) => <i key={interaction.id} className={interactionEvidenceResolved(sceneRuntime.evidence[interaction.id]) ? "complete" : index === activeInteractionIndex ? "active" : ""} />)}</div>
      </div>
      {showCaseViewer && loadingCase ? <section className={`panel pad guided-loading ${styles.taskLoading}`} role="status" aria-live="polite" aria-busy="true">Checking this tracing before the question appears…</section> : activeInteraction && evidenceBoundaryActive ? (
        <section className="learning-interaction production-not-assessable" aria-labelledby={`${activeInteraction.id}-unavailable-title`}>
          <header className="learning-interaction-head"><div><p className="eyebrow"><CircleAlert size={14} /> Tracing unavailable</p><h3 id={`${activeInteraction.id}-unavailable-title`}>{activeInteraction.prompt}</h3><p>{activeInteraction.instructions}</p></div></header>
          <div className="learning-interaction-body"><div className="learning-branch partial" role="status"><CircleAlert size={19} /><span><strong>This ECG check is not available right now.</strong>{eligibilityMessage(eligibility)}</span></div></div>
          <footer className="learning-interaction-actions"><span className="muted">The lesson can continue; this skill will wait for a suitable ECG.</span><button className="button" type="button" onClick={continueUnavailableScene}>Review later and continue</button></footer>
        </section>
      ) : activeInteraction ? <LearningInteractionRenderer
        key={`${scene.id}-${activeInteraction.id}-${sceneRuntime.equivalentRetryCount}`}
        interaction={activeInteraction}
        viewerEvidence={viewerTask ? viewerTaskEvidence : null}
        savedEvidence={activeEvidence}
        gradePacketMeasurement={caseSummary && guidedContext ? (request) => api.gradeGuidedMeasurement(caseSummary.caseId, { ...request, guidedContext }) : undefined}
        onEvidence={recordEvidence}
      /> : null}
      {interactionEvidenceResolved(activeEvidence) && activeInteractionIndex < scene.interactions.length - 1 ? <div className={`production-continue ${styles.continue}`}><p>{evidenceRevealsSolution(activeEvidence) ? "Review the worked answer, then apply the idea in the next question." : "Nice work. The next question gives you a little less guidance."}</p><button className="button primary" type="button" onClick={advanceInteraction}>Continue <ArrowRight size={15} /></button></div> : null}
      {activeEvidence?.feedbackBranch === "not_assessable" ? <div className={`production-retry ${styles.retry}`}><CircleAlert size={18} /><span><strong>This question was not scored.</strong>The ECG did not show enough to answer it safely, so this lesson is not yet complete.</span><button className="button" type="button" onClick={continueUnavailableScene}>Review later and continue</button></div> : null}
      {masteryReceipt && !sceneComplete ? <p className="production-mastery-receipt" role="status" aria-live="polite"><CheckCircle2 size={15} /> {masteryReceipt}</p> : null}
      {needsIndependentRetry ? <div className={`production-retry ${styles.retry}`}><CircleAlert size={18} /><span><strong>Nice work with support.</strong>Try a fresh tracing on your own to add this skill to Progress.</span><button className="button" type="button" onClick={startEquivalentRetry}><RotateCcw size={15} /> Try a fresh tracing</button></div> : null}
    </div>
  );

  const completionAndNavigation = (
    <>
      {sceneComplete ? <section className={`guided-handoff ${styles.handoff}`} aria-label="Completion and transfer">
        <div><p className="eyebrow">Lesson complete · {completionReceiptLabel}</p><h2>{scene.copy.completionHeading}</h2><p>{scene.copy.completionBody}</p>{guidedSaveStatus !== "progress_updated" ? <p className={`selection-note ${styles.evidenceNote}`}>You finished this lesson. Practise the same skill on a fresh ECG to strengthen it in Progress.</p> : null}{masteryReceipt ? <p className="production-mastery-receipt"><CheckCircle2 size={15} /> {masteryReceipt}</p> : null}</div>
        <div className={`guided-handoff-grid ${styles.handoffGrid}`}>{scene.handoffs.map((handoff) => {
          const href = guidedHandoffHref(handoff, { moduleId: module.id, sceneId: scene.id });
          const Icon = handoff.mode === "train" ? Target : handoff.mode === "rapid" ? Clock3 : FlaskConical;
          const destinationSubskill = handoff.destination?.subskill ?? handoff.subskill;
          return <Link key={`${handoff.mode}-${destinationSubskill}-${handoff.destination?.focus ?? handoff.concept}`} href={href}><Icon size={18} /><span><strong>{handoff.label}</strong><small>{skillLabel(destinationSubskill)}</small></span><ArrowRight size={16} /></Link>;
        })}</div>
      </section> : null}
      <div className={`guided-scene-nav ${styles.sceneNav}`}>
        <button className="button subtle" type="button" onClick={() => goToScene(sceneIndex - 1)} disabled={sceneIndex === 0} aria-label="Previous scene"><ChevronLeft size={16} /> Previous</button>
        {sceneComplete
          ? <span className={styles.navStatus}><CheckCircle2 size={14} /> Lesson complete</span>
          : <button className={`button subtle ${styles.saveForLater}`} type="button" onClick={skipScene}>Save for later</button>}
        {sceneIndex < module.scenes.length - 1
          ? <button className="button primary" type="button" onClick={() => goToScene(sceneIndex + 1)} disabled={!sceneComplete}>Next scene <ChevronRight size={16} /></button>
          : !sceneComplete
            ? <button className="button primary" type="button" disabled>{nextModule ? "Next module" : "Mixed transfer"} <ChevronRight size={16} /></button>
            : nextModule
              ? <Link className="button primary" href={`/learn/${nextModule.id}`}>Next module <ChevronRight size={16} /></Link>
              : <Link className="button primary" href="/rapid">Mixed transfer <ArrowRight size={16} /></Link>}
      </div>
    </>
  );

  const sceneIntroduction = (
    <section className={`${styles.sceneFrame}${isFoundationsOpening ? ` ${styles.openingFrame}` : ""}${teachingFrameActive ? ` ${styles.teachingFrame}` : ""}${isFoundations && practiceReady ? ` ${styles.practiceFrame}` : ""}${scene.caseContract && requiresModuleTeaching ? ` ${styles.sceneMasthead}` : ""}`}>
      <header className={styles.sceneHeader} data-lesson-phase={lessonPhaseIndex}>
        <div>
          <p className="eyebrow">{scene.copy.eyebrow}</p>
          <h1 id="production-scene-title" tabIndex={-1}>{scene.copy.title}</h1>
          <p>{scene.copy.objective}</p>
        </div>
        <div className={styles.sceneHeaderAside}>
          {sceneComplete ? <span className={styles.sceneCompleteBadge}><CheckCircle2 size={15} /> Complete</span> : null}
          {scene.caseContract && !isFoundations ? <ol className={styles.lessonRunway} aria-label="Lesson sequence">
            {[
              { label: "Learn model", icon: BrainCircuit },
              { label: "Read ECG", icon: ScanLine },
              { label: "Commit + review", icon: BadgeCheck },
            ].map((phase, index) => {
              const Icon = phase.icon;
              const state = index < lessonPhaseIndex ? "complete" : index === lessonPhaseIndex ? "current" : "upcoming";
              return <li key={phase.label} data-state={state}>{state === "complete" ? <Check size={13} /> : <Icon size={14} />}<span>{phase.label}</span></li>;
            })}
          </ol> : null}
        </div>
      </header>

      {isFoundationsOpening && !practiceReady ? <FoundationsRoutePreview
        activeStep={Math.min(sceneRuntime.teachingStep, FOUNDATIONS_ROUTE.length - 1)}
        visitedSteps={sceneRuntime.teachingVisitedSteps}
        onSelectStep={selectTeachingStep}
        onBeginPractice={beginGuidedPractice}
      /> : isFoundationsOpening ? <FoundationsTeachingRecap sceneId="S0" onReview={reviewTeaching} /> : requiresFoundationsTeaching && !practiceReady ? <FoundationsTeachingSequence
        sceneId={scene.id}
        activeStep={sceneRuntime.teachingStep}
        visitedSteps={sceneRuntime.teachingVisitedSteps}
        onSelectStep={selectTeachingStep}
        onBeginPractice={beginGuidedPractice}
      /> : requiresFoundationsTeaching ? <FoundationsTeachingRecap sceneId={scene.id} onReview={reviewTeaching} /> : requiresModuleTeaching && scene.caseContract ? null : requiresModuleTeaching && !sceneRuntime.teachingComplete ? <ModuleTeachingSequence
        module={module}
        scene={scene}
        activeStep={sceneRuntime.teachingStep}
        visitedSteps={sceneRuntime.teachingVisitedSteps}
        onSelectStep={selectTeachingStep}
        onBeginPractice={beginGuidedPractice}
      /> : requiresModuleTeaching ? <ModuleTeachingRecap module={module} scene={scene} onReview={reviewTeaching} /> : isFoundations ? <div className={styles.practiceBrief}>
        {unresolvedPrerequisites.length ? <div className={`selection-note ${styles.prerequisiteNote}`} role="note"><CircleAlert size={16} /><span><strong>One step before you begin</strong> Finish the earlier lesson from Contents when you’re ready; this preview will not count as independent evidence.</span></div> : null}
        <div className={styles.practiceBriefLead}>
          <p className="eyebrow">{scene.id === "S12" ? "Independent integration" : "Guided practice · support fades"}</p>
          <h2>{scene.id === "S12" ? "Read first. Review second." : "Keep the evidence chain visible."}</h2>
          <p>{scene.copy.setup[0]}</p>
        </div>
        <ol aria-label="Reading expectations">
          {scene.copy.mechanismNarration.map((beat, index) => <li key={beat}><span>{index + 1}</span>{beat}</li>)}
        </ol>
        <aside><Sparkles size={16} /><span><strong>{scene.copy.clinicalConnectionHeading}</strong>{scene.copy.clinicalConnectionBody}</span></aside>
      </div> : <div className={styles.lessonBrief}>
        {unresolvedPrerequisites.length ? <div className={`selection-note ${styles.prerequisiteNote}`} role="note"><CircleAlert size={16} /><span><strong>Previewing this lesson</strong> You still have {unresolvedPrerequisites.length} earlier lesson{unresolvedPrerequisites.length === 1 ? "" : "s"} waiting. Keep exploring, then return from Contents when you’re ready.</span></div> : null}
        {scene.copy.setup[0] ? <p className={styles.setupLead}>{scene.copy.setup[0]}</p> : null}
        <div className={`production-mechanism ${styles.mechanism}`} aria-label="Key ideas">
          <p className="eyebrow">Key idea</p>
          {scene.copy.mechanismNarration.slice(0, visibleMechanismCount).map((beat, index) => <div key={beat}><i>{index + 1}</i><span>{beat}</span></div>)}
          {visibleMechanismCount < scene.copy.mechanismNarration.length ? <button className="button subtle small" type="button" onClick={() => updateSceneRuntime(scene.id, (current) => ({ ...current, revealedMechanismCount: current.revealedMechanismCount + 1 }))}>Show next idea <ArrowRight size={14} /></button> : null}
        </div>
        <details className={styles.contextDetails} open={learningPreferences?.guidanceLevel === "step_by_step" || undefined}>
          <summary>Why this matters</summary>
          <div>{scene.copy.setup.slice(1).map((paragraph) => <p key={paragraph}>{paragraph}</p>)}</div>
          <div className={`guided-clinical-bridge ${styles.clinicalBridge}`}><Sparkles size={16} /><span><strong>{scene.copy.clinicalConnectionHeading}</strong>{scene.copy.clinicalConnectionBody}</span></div>
        </details>
        <p className={`production-transition ${styles.transition}`}>{scene.copy.transitionIntoTask}</p>
      </div>}
    </section>
  );

  const tutorPanelContent = <>
    <section className={styles.tutorIntro}><h3><MessageCircleQuestion size={16} /> Ask Luna about this step</h3><p>{tutorTangentBridge}</p><small><strong>Boundary:</strong> The authored module owns the model, evidence rules, answer key, and score. Luna can question, clarify, and hint without replacing your first read.</small><small><strong>Return point:</strong> {tutorReturnPrompt}</small></section>
    <TutorChat mode="tutorial" caseId={caseSummary?.caseId ?? null} lessonId={scene.caseContract?.selectorLessonId ?? null} threadScope={`${module.id}:${scene.id}`} openingPrompt={`${tutorOpeningPrompt}${eligibility.reasons.length && !loadingCase ? ` ${scene.tutor.caseUnavailablePrompt}` : ""}`} lessonReturnPrompt={tutorReturnPrompt} lessonReturnLabel={scene.copy.returnLabel} waypointLabel={waypoint} collapsedByDefault={module.id === "foundations" && scene.id === "S12"} onReturnToLesson={() => { const target = document.getElementById("production-active-interaction"); target?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" }); target?.focus({ preventScroll: true }); }} viewerState={{ moduleId: module.id, moduleOrder: module.order, sceneId: scene.id, interactionId: activeInteraction?.id, interactionKind: activeInteraction?.kind, interactionPrompt: activeInteraction?.prompt, allowedLeads: activeInteraction && "allowedLeads" in activeInteraction ? activeInteraction.allowedLeads : undefined, measurement: activeInteraction?.kind === "caliper" ? activeInteraction.measurement : undefined, objective: scene.copy.objective, evidence: sceneRuntime.evidence, selectedPoint, caseEligibility: eligibility, evidenceCeiling: scene.learningContract?.evidenceCeiling, criticalRules: scene.learningContract?.criticalRules, socraticPrompts: scene.tutor.socraticPrompts, hintLadder: scene.tutor.hintLadder, objectiveUpdatesAllowed: false, pausedWaypoint: tutorReturnPrompt, layoutContract: scene.layout, returnLabel: scene.copy.returnLabel }} onViewerActions={setViewerActions} onAssistance={recordTutorAssistance} resetKey={`${module.id}-${scene.id}-${caseSummary?.caseId ?? "simulation"}-${sceneRuntime.equivalentRetryCount}`} />
  </>;

  const tutorLauncher = <TutorTrigger className={styles.tutorDock}>
    <span className={styles.tutorDockIcon}><MessageCircleQuestion size={17} aria-hidden="true" /></span>
    <span><strong>Ask Luna about this step</strong><small>{moduleTeachingActive ? "Clarify the model without revealing the ECG answer." : "Get a hint while keeping the tracing in view."}</small></span>
    <ChevronRight size={16} aria-hidden="true" />
  </TutorTrigger>;

  return (
    <div className={`page production-module ${styles.host}${isFoundations ? ` ${styles.foundationsHost}` : ""}${isFoundationsOpening ? ` ${styles.openingHost}` : ""}`} style={{ "--module-accent": module.accent } as React.CSSProperties}>
      <LearningWorkspaceShell className={`guided-module ${styles.shell}`} phase={workspacePhase} tutorResetKey={`${module.id}-${scene.id}-${caseSummary?.caseId ?? "simulation"}-${sceneRuntime.equivalentRetryCount}`}>
      <SessionBar className={styles.sessionBar} tutorAvailable tutorLabel="Ask Luna">
        <Link aria-label="Back to modules" className={`button subtle small ${styles.curriculumLink}`} href="/learn"><ArrowLeft size={15} /><span>Back</span></Link>
        <div className={styles.sessionIdentity}>
          <strong>{module.shortTitle}</strong>
          <small>Lesson {sceneIndex + 1} of {module.scenes.length}</small>
        </div>
        <div className={styles.sessionProgress} aria-label={`Lesson ${sceneIndex + 1} of ${module.scenes.length}`}>
          <progress value={sceneIndex + 1} max={module.scenes.length} aria-label={`Lesson ${sceneIndex + 1} of ${module.scenes.length}`} />
        </div>
        <button ref={sceneMapTriggerRef} className="button subtle small" type="button" aria-controls="production-scene-map" aria-expanded={sceneMapOpen} aria-haspopup="dialog" onClick={() => sceneMapOpen ? closeSceneMap() : setSceneMapOpen(true)}><ListTree size={15} /> Contents</button>
        {isFoundations ? <button ref={referenceTriggerRef} className="button subtle small" type="button" aria-label="Open the Foundations reference" aria-controls="foundations-reference-card" aria-expanded={referenceOpen} aria-haspopup="dialog" onClick={openFoundationsReference}><BookOpen size={15} /> Reference</button> : null}
      </SessionBar>

      {pathwaySyncError ? <WorkspaceNotices>
        <div className="selection-note warning" role="alert">
          <div><strong>Progress sync needs attention</strong><span>{pathwaySyncError}</span></div>
        </div>
      </WorkspaceNotices> : null}

      <WorkspaceBody className={`${styles.workspace}${showCaseViewer ? ` ${styles.ecgWorkspace}` : ""}`}>
        {scene.caseContract ? sceneIntroduction : null}
        {!scene.caseContract || practiceReady ? <WaveformPane className={styles.waveformPane} label={!practiceReady ? "Interactive lesson" : showCaseViewer ? "ECG and lesson context" : isFoundations && scene.id === "S12" ? "Independent read" : "Guided practice"}>
          {!scene.caseContract ? sceneIntroduction : null}

          {showCaseViewer ? <section className={`guided-viewer-wrap ${styles.viewerWrap}`} aria-label="ECG workspace" data-guided-region="ecg">
            <div className={`guided-viewer-label ${styles.viewerLabel}`}><div><p className="eyebrow">ECG</p><strong>{caseSummary ? isFoundations ? "ECG example" : "Practice ECG" : "Finding a suitable tracing…"}</strong></div>{packet ? <span>12-lead ECG</span> : null}</div>
            {loadingCase ? <div className={`panel pad guided-loading ${styles.viewerLoading}`}>Loading ECG…</div> : null}
            {caseError ? <div className="warning mode-recovery-notice" role="alert"><span>This ECG could not load. You can retry or continue the lesson without scoring this step.</span><button className="button subtle small" type="button" onClick={() => setExcludedCaseId(caseSummary?.caseId ?? `retry-${Date.now()}`)}><RotateCcw size={15} aria-hidden="true" /> Retry ECG</button></div> : null}
            {!loadingCase && (packet || caseError) && eligibility.reasons.length ? <details className={`${styles.eligibility} production-eligibility ${eligibility.mode}`}><summary>Why this tracing is limited</summary><p>{eligibilityMessage(eligibility)}</p></details> : null}
            {caseSummary && packet ? <ECGViewer ecgRef={caseSummary.caseId} waveformScope={{ kind: "guided", lessonId: scene.caseContract!.selectorLessonId }} actions={viewerActions} onCoordinate={setSelectedPoint} medianBeats={packet.ptbxl_plus.median_beats} task={viewerTask} onTaskEvidence={setViewerTaskEvidence} onTaskReset={() => setViewerTaskEvidence(null)} guidedContext={guidedContext} /> : null}
          </section> : practiceReady ? <section className={styles.mainTask} data-guided-region="task">{activeTaskContent}{completionAndNavigation}</section> : null}
        </WaveformPane> : null}

        {showCaseViewer ? <ResponseRail className={styles.responseRail} label={moduleTeachingActive ? "Authored model beside the ECG" : "Current ECG question"} phase={workspacePhase}>
          <section className={`${styles.responsePanel}${moduleTeachingActive ? ` ${styles.teachingRailPanel}` : ""}`}>
            {moduleTeachingActive ? <ModuleTeachingSequence
              module={module}
              scene={scene}
              activeStep={sceneRuntime.teachingStep}
              visitedSteps={sceneRuntime.teachingVisitedSteps}
              onSelectStep={selectTeachingStep}
              onBeginPractice={beginGuidedPractice}
              layout="rail"
            /> : <>
              {requiresModuleTeaching ? <ModuleTeachingRecap module={module} scene={scene} onReview={reviewTeaching} layout="rail" /> : null}
              {activeTaskContent}
              {completionAndNavigation}
            </>}
            {moduleTeachingActive ? completionAndNavigation : null}
            {tutorLauncher}
          </section>
          <TutorDrawer className={styles.railTutor} placement="rail" title={isFoundations ? "Foundations tutor" : `${module.shortTitle} · Luna tutor`}>
            {tutorPanelContent}
          </TutorDrawer>
        </ResponseRail> : null}
      </WorkspaceBody>

      {!showCaseViewer ? <TutorDrawer title={isFoundations ? "Foundations tutor" : `${module.shortTitle} · Luna tutor`}>
        {tutorPanelContent}
      </TutorDrawer> : null}

      {sceneMapOpen ? <div className={styles.sceneMapLayer}>
        <button className={styles.sceneMapBackdrop} type="button" tabIndex={-1} aria-label="Close scene map" onClick={closeSceneMap} />
        <aside id="production-scene-map" className={styles.sceneMap} role="dialog" aria-modal="true" aria-labelledby="production-scene-map-title" onKeyDown={(event) => {
          if (event.key === "Escape") { event.preventDefault(); closeSceneMap(); return; }
          if (event.key !== "Tab") return;
          const focusable = [...event.currentTarget.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])')];
          const first = focusable[0];
          const last = focusable.at(-1);
          if (!first || !last) return;
          if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
          else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        }}>
          <header><div><p className="eyebrow">Module {module.order} of {totalModules}</p><h2 id="production-scene-map-title">{module.title}</h2><p>{module.outcome}</p></div><button ref={sceneMapCloseRef} className="button subtle small" type="button" onClick={closeSceneMap}><X size={16} /> Close</button></header>
          <div className={styles.sceneMapMeta}><span><Clock3 size={14} /> About {totalMinutes} min</span><span><Target size={14} /> {parts.length} chapters</span><span><CheckCircle2 size={14} /> {completedCount}/{module.scenes.length} complete</span></div>
          <nav className={`guided-scene-list open ${styles.sceneList}`} aria-label="Module scenes">{parts.map((part) => <div className="guided-part" key={part}><p>{part}</p>{module.scenes.map((item, index) => {
            if (item.partId !== part) return null;
            const status = runtime[module.id]?.[item.id]?.status ?? "not-started";
            return <button className={`guided-scene-link${index === sceneIndex ? " active" : ""} ${status}`} key={item.id} type="button" onClick={() => goToScene(index)} aria-current={index === sceneIndex ? "step" : undefined}><span>{status === "complete" ? <Check size={13} /> : index + 1}</span><span><strong>{item.copy.title}</strong><small>{statusLabel(status)} · {item.minutes} min</small></span></button>;
          })}</div>)}</nav>
          <footer>{priorModule ? <Link href={`/learn/${priorModule.id}`}><ArrowLeft size={15} /> {priorModule.shortTitle}</Link> : <Link href="/learn/foundations"><ArrowLeft size={15} /> Foundations</Link>}<span>Module {module.order}/{totalModules}</span>{nextModule ? <Link href={`/learn/${nextModule.id}`}>{nextModule.shortTitle} <ArrowRight size={15} /></Link> : <Link href="/rapid">Mixed transfer <ArrowRight size={15} /></Link>}</footer>
        </aside>
      </div> : null}
      {referenceOpen ? <div className={styles.referenceLayer}>
        <button className={styles.sceneMapBackdrop} type="button" tabIndex={-1} aria-label="Close Foundations reference" onClick={closeFoundationsReference} />
        <aside id="foundations-reference-card" className={styles.referenceCard} role="dialog" aria-modal="true" aria-labelledby="foundations-reference-title" onKeyDown={(event) => {
          if (event.key === "Escape") { event.preventDefault(); closeFoundationsReference(); return; }
          if (event.key !== "Tab") return;
          const focusable = [...event.currentTarget.querySelectorAll<HTMLElement>('button:not([disabled]), [tabindex]:not([tabindex="-1"])')];
          const first = focusable[0];
          const last = focusable.at(-1);
          if (!first || !last) return;
          if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
          else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        }}>
          <header><div><p className="eyebrow">Quick retrieval · no active-case answer</p><h2 id="foundations-reference-title">Foundations reference · adult teaching cases</h2><p>Rows unlock after you view their teaching scene. Opening this card during the capstone records reference assistance.</p></div><button ref={referenceCloseRef} className="button subtle small" type="button" onClick={closeFoundationsReference}><X size={16} /> Close</button></header>
          <div className={styles.referenceRows}>{[
            { sceneId: "S2", term: "Calibration & grid", detail: "Read speed and gain first. At 25 mm/s: 1 small box = 40 ms, 1 large box = 200 ms. At 10 mm/mV: 10 mm = 1 mV." },
            { sceneId: "S3", term: "Task-specific quality", detail: "Name the domain, localize the limitation, preserve supported evidence, and use not assessable when needed." },
            { sceneId: "S4", term: "Regularity & rate", detail: "Regular: interval method. Irregular: count a true six-second continuous window ×10 and label the result an average." },
            { sceneId: "S5", term: "Atrial source & P–QRS", detail: "Sinus P-wave pattern needs repeatable P morphology/direction. Report the P–QRS relationship as a separate output." },
            { sceneId: "S6", term: "PR interval", detail: "P onset to QRS onset. Adult teaching reference: 120–200 ms; preserve rate and context." },
            { sceneId: "S6", term: "QRS duration", detail: "First departure to final return. <120 ms narrow; ≥120 ms wide in adult teaching cases. Narrow does not mean otherwise normal." },
            { sceneId: "S7", term: "Baseline-linked ST–T", detail: "Name the lead and stable reference, locate J, then describe ST direction and T shape without inventing a cause." },
            { sceneId: "S7", term: "QT endpoints", detail: "QRS onset to T-wave end. If T end is not readable, record QT as not assessable; later modules address correction." },
            { sceneId: "S8", term: "R/S progression", detail: "Compare V1 through V6 in order. Variation exists; exact transition requires reviewed QRS windows and representation metadata." },
            { sceneId: "S9", term: "Coarse axis", detail: "Use full-QRS polarity in I and aVF. For I+/aVF−, inspect lead II before calling definite left-axis deviation." },
          ].map((row) => {
            const status = runtime[module.id]?.[row.sceneId]?.status ?? "not-started";
            const unlocked = status !== "not-started" && status !== "skipped";
            return <article key={`${row.sceneId}-${row.term}`} className={unlocked ? styles.referenceUnlocked : styles.referenceLocked}><div><span>{row.sceneId}</span><strong>{row.term}</strong></div><p>{unlocked ? row.detail : "Later in Foundations"}</p></article>;
          })}</div>
          <footer>Reference ranges and patterns here are scoped to reviewed adult teaching cases. Age, technology, placement, clinical context, and local standards can change the interpretation.</footer>
        </aside>
      </div> : null}
      </LearningWorkspaceShell>
    </div>
  );
}
