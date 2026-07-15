"use client";

import {
  ArrowLeft,
  ArrowRight,
  BrainCircuit,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Clock3,
  FlaskConical,
  Link2,
  ListTree,
  MessageCircleQuestion,
  RotateCcw,
  SkipForward,
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
  DisclosureArea,
  LearningWorkspaceShell,
  ResponseRail,
  SessionBar,
  TutorDrawer,
  WaveformPane,
  WorkspaceBody,
  WorkspaceNotices,
} from "@/components/layout/LearningWorkspaceShell";
import { api, type PathwayProgressItem } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { guidedHandoffHref } from "@/lib/learning/handoffTargets";
import type { InteractionEvidence, LearningInteraction, ProductionModule, ProductionScene } from "@/lib/learning/interactionTypes";
import type { CasePacket, CaseSummary, ViewerAction, ViewerTaskEvidence, ViewerTaskSpec } from "@/lib/types";
import type { ECGPoint } from "@/lib/coordinates";
import { PRODUCTION_PATHWAY_ID } from "@/lib/pathways";
import { useLearningPreferences } from "@/lib/useLearningPreferences";
import styles from "./ProductionModuleExperience.module.css";

type SceneStatus = "not-started" | "viewed" | "attempted" | "needs-review" | "complete" | "skipped";

type GuidedSaveStatus = "saving" | "practice_saved" | "progress_updated" | "local_only";

type SceneRuntime = {
  status: SceneStatus;
  activeInteractionIndex: number;
  revealedMechanismCount: number;
  evidence: Record<string, InteractionEvidence>;
  equivalentRetryCount: number;
  assistedInteractionIds: string[];
};

type RuntimeState = Record<string, Record<string, SceneRuntime>>;

const PATHWAY_ID = PRODUCTION_PATHWAY_ID;

function emptyRuntime(): SceneRuntime {
  return { status: "not-started", activeInteractionIndex: 0, revealedMechanismCount: 1, evidence: {}, equivalentRetryCount: 0, assistedInteractionIds: [] };
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
    runtime[item.moduleId][item.sceneId] = {
      ...emptyRuntime(),
      ...(state as Partial<SceneRuntime>),
      status: item.status,
      activeInteractionIndex: item.activeInteractionIndex,
      evidence: state.evidence && typeof state.evidence === "object"
        ? state.evidence as Record<string, InteractionEvidence>
        : {},
    };
  }
  return runtime;
}

function newestResumableScene(items: PathwayProgressItem[], moduleId: string): string | null {
  return items
    .filter((item) => item.moduleId === moduleId && !["not-started", "complete", "skipped"].includes(item.status))
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

function supportLabel(value: string) {
  if (value === "independent") return "solo check";
  if (value === "faded") return "light support";
  return "guided practice";
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
  if (!packet) reasons.push("No case packet is loaded.");
  if (requestedUnavailable) reasons.push(`No eligible ${contract.requestedConcept.replaceAll("_", " ")} exemplar is available.`);
  if (packet && !serverEligibility) reasons.push("This scene cannot yet verify the ECG evidence needed for an independent assessment.");
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
  if (eligibility.mode === "contrast") return "This ECG is useful for comparison, but it cannot score the target finding.";
  if (eligibility.mode === "simulation") return "This authored exercise teaches the reasoning, but it is not a scored ECG check.";
  return "A suitable real ECG is not available for this check right now. You can continue the lesson without changing progress for this skill.";
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
  const guidedReceiptSequence = useRef(0);
  const sceneMapTriggerRef = useRef<HTMLButtonElement | null>(null);
  const sceneMapCloseRef = useRef<HTMLButtonElement | null>(null);
  const scene = module.scenes[sceneIndex];

  useEffect(() => {
    if (!sceneMapOpen) return;
    const frame = window.requestAnimationFrame(() => sceneMapCloseRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [sceneMapOpen]);

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
  }, [scene.caseContract, scene.id]);

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
    guidedReceiptSequence.current += 1;
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
      guidedEligibilityRequest(scene),
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
  const waveformInteraction = activeInteraction && ["point", "region", "caliper", "march"].includes(activeInteraction.kind);
  const requiresGroundedCase = Boolean(activeInteraction?.subskills.some((subskill) => ["recognize", "localize", "measure", "discriminate", "synthesize", "apply_in_context"].includes(subskill)));
  const caseResolutionComplete = !loadingCase && Boolean(packet || caseError);
  const evidenceBoundaryActive = Boolean(activeInteraction && !eligibility.eligible && caseResolutionComplete
    && (waveformInteraction || (eligibility.mode === "locked" && requiresGroundedCase)));
  const viewerTask = waveformInteraction && eligibility.eligible ? taskForInteraction(activeInteraction) : undefined;
  const sceneComplete = sceneRuntime.status === "complete";
  const completedCount = module.scenes.filter((item) => runtime[module.id]?.[item.id]?.status === "complete").length;
  const skippedCount = module.scenes.filter((item) => runtime[module.id]?.[item.id]?.status === "skipped").length;
  const progressPercent = Math.round((completedCount / module.scenes.length) * 100);
  const totalMinutes = module.scenes.reduce((sum, item) => sum + item.minutes, 0);
  const parts = Array.from(new Set(module.scenes.map((item) => item.partId)));
  const waypoint = `${module.shortTitle} · ${scene.id} ${scene.copy.title} · action ${activeInteractionIndex + 1}`;

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
      const meanScore = requiredEvidence.length ? requiredEvidence.reduce((sum, item) => sum + item.score, 0) / requiredEvidence.length : 0;
      const independentOrUnavailable = required.every((interaction) => {
        const item = nextEvidence[interaction.id];
        return item?.assistance === "independent" || item?.feedbackBranch === "not_assessable";
      });
      const independentGate = !scene.completionRule.requireIndependentAttempt || independentOrUnavailable;
      const complete = allCorrect && meanScore >= scene.completionRule.minimumScore && independentGate;
      return {
        ...current,
        evidence: nextEvidence,
        status: complete ? "complete" : recordedEvidence.correct ? "attempted" : "needs-review",
      };
    });
    const receiptHandoff = scene.handoffs.find((handoff) => activeInteraction?.subskills.includes(handoff.subskill));
    const concept = receiptHandoff?.concept
      ?? scene.handoffs[0]?.concept
      ?? scene.caseContract?.requestedConcept
      ?? "curriculum_foundation";
    const isFinalRequired = scene.completionRule.requiredInteractionIds.every((id) => id === recordedEvidence.interactionId || sceneRuntime.evidence[id]?.correct);
    const evidenceLevel = isFinalRequired && scene.completionRule.requireIndependentAttempt ? "independent_transfer" : "guided";
    const caseProvenance = !scene.caseContract
      ? "authored_simulation"
      : eligibility.mode === "target"
        ? "real_eligible"
        : eligibility.mode === "contrast"
          ? "contrast_only"
          : "authored_simulation";
    const receiptSequence = ++guidedReceiptSequence.current;
    setGuidedSaveStatus("saving");
    void api.recordGuidedEvent({
      learnerId: authenticatedUserId,
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
      caseId: caseSummary?.caseId ?? null,
      guidedContext,
      caseProvenance,
      caseEligible: eligibility.eligible,
      misconceptions: recordedEvidence.misconceptions,
    }).then((receipt) => {
      if (receiptSequence !== guidedReceiptSequence.current) return;
      const independent = receipt.effectiveEvidenceLevel === "independent_transfer"
        ? receipt.receipts.filter((item) => item.evidenceLevel === "independent_transfer")
        : [];
      if (independent.length) {
        setGuidedSaveStatus("progress_updated");
        setMasteryReceipt(`Progress updated for ${independent.map((item) => skillLabel(item.subskill)).join(", ")}.`);
        return;
      }
      setGuidedSaveStatus("practice_saved");
      setMasteryReceipt("Lesson practice saved. Try the skill on a fresh mixed ECG before your mastery estimate changes.");
    }).catch(() => {
      if (receiptSequence !== guidedReceiptSequence.current) return;
      setGuidedSaveStatus("local_only");
      setMasteryReceipt("This lesson step is saved on this device. Account sync is temporarily unavailable.");
    });
  }

  function recordTutorAssistance() {
    if (!activeInteraction || activeEvidence) return;
    updateSceneRuntime(scene.id, (current) => ({
      ...current,
      assistedInteractionIds: current.assistedInteractionIds.includes(activeInteraction.id)
        ? current.assistedInteractionIds
        : [...current.assistedInteractionIds, activeInteraction.id],
    }));
    setMasteryReceipt("Tutor help noted. Try the next equivalent ECG without help to update your mastery estimate.");
  }

  function advanceInteraction() {
    if (!activeEvidence?.correct) return;
    updateSceneRuntime(scene.id, (current) => ({
      ...current,
      activeInteractionIndex: Math.min(current.activeInteractionIndex + 1, scene.interactions.length - 1),
    }));
    setViewerTaskEvidence(null);
    document.getElementById("production-active-interaction")?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
  }

  function acknowledgeUnavailableEvidence() {
    if (!activeInteraction || !evidenceBoundaryActive || eligibility.eligible) return;
    recordEvidence({
      interactionId: activeInteraction.id,
      kind: activeInteraction.kind,
      correct: true,
      partial: false,
      score: 1,
      attempts: 1,
      assistance: "scaffolded",
      hintsUsed: 0,
      response: { notAssessable: true, reasons: eligibility.reasons },
      misconceptions: [],
      feedbackBranch: "not_assessable",
    });
  }

  function startEquivalentRetry() {
    setExcludedCaseId(caseSummary?.caseId);
    updateSceneRuntime(scene.id, (current) => ({
      ...current,
      status: "viewed",
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

  function skipScene() {
    updateSceneRuntime(scene.id, (current) => ({ ...current, status: "skipped" }));
    if (sceneIndex < module.scenes.length - 1) goToScene(sceneIndex + 1);
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

  const workspacePhase = sceneComplete ? "complete" : activeEvidence ? "feedback" : "task";
  const activeTaskContent = (
    <div id="production-active-interaction" className={`guided-production-checkpoint ${styles.checkpoint}`} tabIndex={-1}>
      <div className={`production-action-progress ${styles.actionProgress}`}>
        <span>Action {activeInteractionIndex + 1} of {scene.interactions.length}</span>
        <div>{scene.interactions.map((interaction, index) => <i key={interaction.id} className={sceneRuntime.evidence[interaction.id]?.correct ? "complete" : index === activeInteractionIndex ? "active" : ""} />)}</div>
      </div>
      {scene.caseContract && loadingCase ? <section className={`panel pad guided-loading ${styles.taskLoading}`} role="status" aria-live="polite" aria-busy="true">Checking this tracing before the question appears…</section> : activeInteraction && evidenceBoundaryActive ? (
        <section className="learning-interaction production-not-assessable" aria-labelledby={`${activeInteraction.id}-unavailable-title`}>
          <header className="learning-interaction-head"><div><p className="eyebrow"><CircleAlert size={14} /> Practice boundary</p><h3 id={`${activeInteraction.id}-unavailable-title`}>{activeInteraction.prompt}</h3><p>{activeInteraction.instructions}</p></div><span>Practice step</span></header>
          <div className="learning-interaction-body"><div className="learning-branch partial" role="status"><CircleAlert size={19} /><span><strong>This ECG check is not available right now.</strong>{eligibilityMessage(eligibility)}</span></div></div>
          <footer className="learning-interaction-actions"><span className="muted">The lesson can continue; this skill will wait for a suitable ECG.</span><button className="button" type="button" onClick={acknowledgeUnavailableEvidence} disabled={activeEvidence?.feedbackBranch === "not_assessable"}>Continue without scoring</button></footer>
        </section>
      ) : activeInteraction ? <LearningInteractionRenderer
        key={`${scene.id}-${activeInteraction.id}-${sceneRuntime.equivalentRetryCount}`}
        interaction={activeInteraction}
        viewerEvidence={viewerTask ? viewerTaskEvidence : null}
        savedEvidence={activeEvidence}
        gradePacketMeasurement={caseSummary && guidedContext ? (request) => api.gradeGuidedMeasurement(caseSummary.caseId, { ...request, guidedContext }) : undefined}
        onEvidence={recordEvidence}
      /> : null}
      {activeEvidence?.correct && activeInteractionIndex < scene.interactions.length - 1 ? <div className={`production-continue ${styles.continue}`}><p>Keep this evidence. The next action removes one layer of support.</p><button className="button primary" type="button" onClick={advanceInteraction}>Continue to the next action <ArrowRight size={15} /></button></div> : null}
      {masteryReceipt && !sceneComplete ? <p className="production-mastery-receipt" role="status" aria-live="polite"><CheckCircle2 size={15} /> {masteryReceipt}</p> : null}
      {needsIndependentRetry ? <div className={`production-retry ${styles.retry}`}><CircleAlert size={18} /><span><strong>Nice work with support.</strong>Try a fresh tracing on your own to add this skill to Progress.</span><button className="button" type="button" onClick={startEquivalentRetry}><RotateCcw size={15} /> Try a fresh tracing</button></div> : null}
    </div>
  );

  const completionAndNavigation = (
    <>
      {sceneComplete ? <section className={`guided-handoff ${styles.handoff}`} aria-label="Completion and transfer">
        <div><p className="eyebrow">Scene complete · {completionReceiptLabel}</p><h2>{scene.copy.completionHeading}</h2><p>{scene.copy.completionBody}</p>{guidedSaveStatus !== "progress_updated" ? <p className={`selection-note ${styles.evidenceNote}`}>You finished this lesson step. A fresh mixed ECG check is still needed before this skill changes in Progress.</p> : null}{masteryReceipt ? <p className="production-mastery-receipt"><CheckCircle2 size={15} /> {masteryReceipt}</p> : null}</div>
        <div className={`guided-handoff-grid ${styles.handoffGrid}`}>{scene.handoffs.map((handoff) => {
          const href = guidedHandoffHref(handoff, { moduleId: module.id, sceneId: scene.id });
          const Icon = handoff.mode === "train" ? Target : handoff.mode === "rapid" ? Clock3 : FlaskConical;
          const destinationSubskill = handoff.destination?.subskill ?? handoff.subskill;
          return <Link key={`${handoff.mode}-${destinationSubskill}-${handoff.destination?.focus ?? handoff.concept}`} href={href}><Icon size={18} /><span><strong>{handoff.label}</strong><small>{skillLabel(destinationSubskill)} · {supportLabel(handoff.supportLevel)}</small></span><ArrowRight size={16} /></Link>;
        })}</div>
      </section> : null}
      <div className={`guided-scene-nav ${styles.sceneNav}`}>
        <button className="button subtle" type="button" onClick={() => goToScene(sceneIndex - 1)} disabled={sceneIndex === 0} aria-label="Previous scene"><ChevronLeft size={16} /> Previous</button>
        <span>{statusLabel(sceneRuntime.status)}</span>
        {sceneIndex < module.scenes.length - 1 ? <button className="button primary" type="button" onClick={() => goToScene(sceneIndex + 1)} disabled={!sceneComplete}>Next scene <ChevronRight size={16} /></button> : nextModule ? <Link className="button primary" href={`/learn/${nextModule.id}`}>Next module <ChevronRight size={16} /></Link> : <Link className="button primary" href="/rapid">Mixed transfer <ArrowRight size={16} /></Link>}
      </div>
    </>
  );

  return (
    <div className={`page production-module ${styles.host}`} style={{ "--module-accent": module.accent } as React.CSSProperties}>
      <LearningWorkspaceShell className={`guided-module ${styles.shell}`} phase={workspacePhase} tutorResetKey={`${module.id}-${scene.id}-${caseSummary?.caseId ?? "simulation"}-${sceneRuntime.equivalentRetryCount}`}>
      <SessionBar className={styles.sessionBar} tutorAvailable tutorLabel="Open tutor">
        <Link aria-label="Back to Guided curriculum" className={`button subtle small ${styles.curriculumLink}`} href="/learn"><ArrowLeft size={15} /><span>Curriculum</span></Link>
        <div className={styles.sessionIdentity}>
          <span>Module {module.order}/{totalModules}</span>
          <strong>{module.shortTitle}</strong>
          <small>Scene {sceneIndex + 1}/{module.scenes.length}</small>
        </div>
        <div className={styles.sessionProgress} aria-label={`${completedCount} of ${module.scenes.length} scenes complete`}>
          <progress value={completedCount} max={module.scenes.length} aria-label={`${completedCount} of ${module.scenes.length} scenes complete`} />
          <span>{progressPercent}%</span>
        </div>
        <button ref={sceneMapTriggerRef} className="button subtle small" type="button" aria-controls="production-scene-map" aria-expanded={sceneMapOpen} aria-haspopup="dialog" onClick={() => sceneMapOpen ? closeSceneMap() : setSceneMapOpen(true)}><ListTree size={15} /> Scene map</button>
      </SessionBar>

      {pathwaySyncError ? <WorkspaceNotices>
        <div className="selection-note warning" role="alert">
          <div><strong>Progress sync needs attention</strong><span>{pathwaySyncError}</span></div>
        </div>
      </WorkspaceNotices> : null}

      <WorkspaceBody className={`${styles.workspace}${scene.caseContract ? ` ${styles.ecgWorkspace}` : ""}`}>
        <WaveformPane className={styles.waveformPane} label={scene.caseContract ? "ECG and lesson context" : "Interactive lesson workspace"}>
          <section className={styles.sceneFrame}>
            <header className={styles.sceneHeader}>
              <div>
                <p className="eyebrow">{scene.copy.eyebrow}</p>
                <h1 id="production-scene-title" tabIndex={-1}>{scene.copy.title}</h1>
                <p>{scene.copy.objective}</p>
              </div>
              <button className={`button subtle small ${styles.skipButton}`} type="button" onClick={skipScene}><SkipForward size={15} /> Review later</button>
            </header>

            <div className={styles.lessonBrief}>
              {scene.copy.setup[0] ? <p className={styles.setupLead}>{scene.copy.setup[0]}</p> : null}
              <div className={`production-mechanism ${styles.mechanism}`} aria-label="Mechanism narration">
                <p className="eyebrow"><BrainCircuit size={15} /> Build the mechanism</p>
                {scene.copy.mechanismNarration.slice(0, visibleMechanismCount).map((beat, index) => <div key={beat}><i>{index + 1}</i><span>{beat}</span></div>)}
                {visibleMechanismCount < scene.copy.mechanismNarration.length ? <button className="button subtle small" type="button" onClick={() => updateSceneRuntime(scene.id, (current) => ({ ...current, revealedMechanismCount: current.revealedMechanismCount + 1 }))}>{visibleMechanismCount === 0 ? "Show first link" : "Reveal next link"} <ArrowRight size={14} /></button> : null}
              </div>
              <details className={styles.contextDetails} open={learningPreferences?.guidanceLevel === "step_by_step" || undefined}>
                <summary>More context & clinical connection</summary>
                <div>{scene.copy.setup.slice(1).map((paragraph) => <p key={paragraph}>{paragraph}</p>)}</div>
                <div className={`guided-clinical-bridge ${styles.clinicalBridge}`}><Sparkles size={16} /><span><strong>{scene.copy.clinicalConnectionHeading}</strong>{scene.copy.clinicalConnectionBody}</span></div>
              </details>
              <p className={`production-transition ${styles.transition}`}>{scene.copy.transitionIntoTask}</p>
            </div>
          </section>

          {scene.caseContract ? <section className={`guided-viewer-wrap ${styles.viewerWrap}`} aria-label="ECG workspace" data-guided-region="ecg">
            <div className={`guided-viewer-label ${styles.viewerLabel}`}><div><p className="eyebrow">ECG</p><strong>{caseSummary ? "Grounded teaching ECG" : "Finding a suitable tracing…"}</strong></div>{packet ? <span>Real 12-lead ECG</span> : null}</div>
            {loadingCase ? <div className={`panel pad guided-loading ${styles.viewerLoading}`}>Loading ECG…</div> : null}
            {caseError ? <div className="warning mode-recovery-notice" role="alert"><span>This ECG could not load. You can retry or continue the lesson without scoring this step.</span><button className="button subtle small" type="button" onClick={() => setExcludedCaseId(caseSummary?.caseId ?? `retry-${Date.now()}`)}><RotateCcw size={15} aria-hidden="true" /> Retry ECG</button></div> : null}
            {!loadingCase && (packet || caseError) && eligibility.reasons.length ? <details className={`${styles.eligibility} production-eligibility ${eligibility.mode}`}><summary>About this ECG check</summary><p>{eligibilityMessage(eligibility)}</p></details> : null}
            {caseSummary && packet ? <ECGViewer ecgRef={caseSummary.caseId} waveformScope={{ kind: "guided", lessonId: scene.caseContract.selectorLessonId }} actions={viewerActions} onCoordinate={setSelectedPoint} medianBeats={packet.ptbxl_plus.median_beats} task={viewerTask} onTaskEvidence={setViewerTaskEvidence} guidedContext={guidedContext} /> : null}
          </section> : <section className={styles.mainTask} data-guided-region="task">{activeTaskContent}</section>}
        </WaveformPane>

        <ResponseRail className={styles.responseRail} label={scene.caseContract ? "Current ECG question" : "Scene progress and transfer"} phase={workspacePhase}>
          <section className={`panel ${styles.responsePanel}`}>
            {scene.caseContract ? activeTaskContent : <div className={styles.sceneGuide}>
              <p className="eyebrow">Scene guide</p>
              <h2>One task at a time</h2>
              <p>Complete the active interaction in the main workspace. Feedback appears there immediately.</p>
              <dl>
                <div><dt>Recall</dt><dd>{scene.connections.recallFrom}</dd></div>
                <div><dt>Now</dt><dd>{scene.connections.changesNow}</dd></div>
                <div><dt>Reuse</dt><dd>{scene.connections.reuseNext}</dd></div>
              </dl>
            </div>}
            {completionAndNavigation}
          </section>
        </ResponseRail>
      </WorkspaceBody>

      <DisclosureArea className={styles.disclosure}>
        <span role="status"><CheckCircle2 size={14} /> {authLoading || !runtimeReady ? "Loading progress…" : "Private progress synced to your account"}</span>
        <span>{completedCount}/{module.scenes.length} complete · {skippedCount} review later</span>
        <details><summary><Link2 size={14} /> About this check</summary><div><p>Your mastery estimate changes only after you complete the required task on a suitable ECG without revealed answers.</p><p>Lesson references: {scene.source.map((source) => `${source.document} · ${source.section}`).join(" · ")}</p></div></details>
      </DisclosureArea>

      <TutorDrawer title={`${module.shortTitle} tutor`}>
        <section className={styles.tutorIntro}><h3><MessageCircleQuestion size={16} /> Ask about this step</h3><p>{scene.tutor.tangentBridge}</p><small><strong>Return point:</strong> {scene.tutor.returnPrompt}</small></section>
        <TutorChat mode="tutorial" caseId={caseSummary?.caseId ?? null} lessonId={scene.caseContract?.selectorLessonId ?? null} threadScope={`${module.id}:${scene.id}`} openingPrompt={`${scene.copy.openingTutorMessage}${eligibility.reasons.length && !loadingCase ? ` ${scene.tutor.caseUnavailablePrompt}` : ""}`} lessonReturnPrompt={scene.tutor.returnPrompt} lessonReturnLabel={scene.copy.returnLabel} waypointLabel={waypoint} collapsedByDefault={false} onReturnToLesson={() => { const target = document.getElementById("production-active-interaction"); target?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" }); target?.focus({ preventScroll: true }); }} viewerState={{ moduleId: module.id, moduleOrder: module.order, sceneId: scene.id, interactionId: activeInteraction?.id, interactionKind: activeInteraction?.kind, interactionPrompt: activeInteraction?.prompt, allowedLeads: activeInteraction && "allowedLeads" in activeInteraction ? activeInteraction.allowedLeads : undefined, measurement: activeInteraction?.kind === "caliper" ? activeInteraction.measurement : undefined, objective: scene.copy.objective, evidence: sceneRuntime.evidence, selectedPoint, caseEligibility: eligibility, pausedWaypoint: scene.tutor.returnPrompt, layoutContract: scene.layout, returnLabel: scene.copy.returnLabel }} onViewerActions={setViewerActions} onAssistance={recordTutorAssistance} resetKey={`${module.id}-${scene.id}-${caseSummary?.caseId ?? "simulation"}-${sceneRuntime.equivalentRetryCount}`} />
      </TutorDrawer>

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
      </LearningWorkspaceShell>
    </div>
  );
}
