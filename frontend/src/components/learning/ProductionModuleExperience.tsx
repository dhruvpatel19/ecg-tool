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
  MessageCircleQuestion,
  RotateCcw,
  SkipForward,
  Sparkles,
  Target,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ECGViewer } from "@/components/ECGViewer";
import { TutorChat } from "@/components/TutorChat";
import { LearningInteractionRenderer } from "@/components/learning/LearningInteractionRenderer";
import { api, type PathwayProgressItem } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { InteractionEvidence, LearningInteraction, ProductionModule, ProductionScene } from "@/lib/learning/interactionTypes";
import type { CasePacket, CaseSummary, ViewerAction, ViewerTaskEvidence, ViewerTaskSpec } from "@/lib/types";
import type { ECGPoint } from "@/lib/coordinates";
import { PRODUCTION_PATHWAY_ID } from "@/lib/pathways";

type SceneStatus = "not-started" | "viewed" | "attempted" | "needs-review" | "complete" | "skipped";

type SceneRuntime = {
  status: SceneStatus;
  activeInteractionIndex: number;
  revealedMechanismCount: number;
  evidence: Record<string, InteractionEvidence>;
  equivalentRetryCount: number;
  assistedInteractionIds: string[];
};

type RuntimeState = Record<string, Record<string, SceneRuntime>>;

const STORAGE_KEY = "trace-production-curriculum-v1";
const PATHWAY_ID = PRODUCTION_PATHWAY_ID;
const IMPORT_MARKER_PREFIX = "trace-production-guest-imported";

function emptyRuntime(): SceneRuntime {
  return { status: "not-started", activeInteractionIndex: 0, revealedMechanismCount: 1, evidence: {}, equivalentRetryCount: 0, assistedInteractionIds: [] };
}

function loadRuntime(): RuntimeState {
  if (typeof window === "undefined") return {};
  try {
    const parsed = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "{}");
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function saveRuntime(runtime: RuntimeState) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(runtime));
    window.dispatchEvent(new Event("trace-production-progress"));
  } catch {
    // The session remains usable in memory when storage is unavailable.
  }
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

function hasGuestProgress(runtime: RuntimeState) {
  return Object.values(runtime).some((scenes) => Object.values(scenes).some((scene) =>
    scene.status !== "not-started" || Object.keys(scene.evidence).length > 0,
  ));
}

function statusLabel(status: SceneStatus) {
  if (status === "complete") return "Complete";
  if (status === "needs-review") return "Needs review";
  if (status === "skipped") return "Skipped";
  if (status === "attempted") return "Attempted";
  if (status === "viewed") return "In progress";
  return "Not started";
}

function compactSceneId(sceneId: string) {
  return sceneId.split(/[.-]/).at(-1)?.toUpperCase() ?? sceneId;
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

function caseEligibility(scene: ProductionScene, packet: CasePacket | null, requestedUnavailable: boolean): Eligibility {
  const contract = scene.caseContract;
  if (!contract) return { eligible: true, reasons: [], mode: "simulation" };
  const reasons: string[] = [];
  if (!packet) reasons.push("No case packet is loaded.");
  if (requestedUnavailable) reasons.push(`No eligible ${contract.requestedConcept.replaceAll("_", " ")} exemplar is available.`);
  if (packet && !["A", "B"].includes(packet.teaching_tier)) reasons.push(`Teaching tier ${packet.teaching_tier} is below the ${contract.minimumTier} requirement.`);
  if (packet && contract.minimumTier === "A" && packet.teaching_tier !== "A") reasons.push("This scene requires a Tier A exemplar.");
  if (packet && !packet.supported_objectives?.includes(contract.requestedConcept)) reasons.push("The case packet does not support the requested objective.");
  for (const lead of contract.requiredLeads ?? []) {
    if (packet && !packet.waveform.leads.includes(lead)) reasons.push(`Required lead ${lead} is missing.`);
  }
  for (const evidence of contract.requiredEvidence) {
    if (!packet) continue;
    if (evidence.startsWith("measurement:")) {
      const key = evidence.slice("measurement:".length);
      if (packet.ptbxl_plus.measurements[key] === undefined) reasons.push(`Required measurement ${key} is unavailable.`);
    }
    if (evidence.startsWith("roi:")) {
      const concept = evidence.slice("roi:".length);
      const rois = packet.ptbxl_plus.fiducials.rois ?? [];
      if (!rois.some((roi) => roi.concept === concept)) reasons.push(`Required ${concept.replaceAll("_", " ")} geometry is unavailable.`);
    }
  }
  const uniqueReasons = Array.from(new Set(reasons));
  if (!uniqueReasons.length) return { eligible: true, reasons: [], mode: "target" };
  return {
    eligible: false,
    reasons: uniqueReasons,
    mode: contract.fallback === "contrast_only" ? "contrast" : contract.fallback === "authored_simulation" ? "simulation" : "locked",
  };
}

function interactionCaseEligibility(
  scene: ProductionScene,
  base: Eligibility,
  interaction: LearningInteraction | undefined,
  packet: CasePacket | null,
): Eligibility {
  if (!base.eligible || !interaction || !packet) return base;
  const reasons: string[] = [];
  if (interaction.kind === "point" || interaction.kind === "region") {
    const matching = (packet.ptbxl_plus.fiducials.rois ?? []).filter((roi) =>
      roi.concept === interaction.concept && (!interaction.allowedLeads?.length || interaction.allowedLeads.includes(roi.lead)));
    if (!matching.length) reasons.push(`No reviewed ${interaction.concept.replaceAll("_", " ")} geometry exists in the permitted leads.`);
  }
  if (interaction.kind === "caliper" && interaction.target.source === "packet_measurement") {
    const key = interaction.target.measurementKey;
    if (!key || packet.ptbxl_plus.measurements[key] === undefined) reasons.push(`The grounded ${key ?? interaction.measurement} measurement is unavailable.`);
    const roiConcept = caliperRoiConcept(interaction.measurement);
    if (roiConcept) {
      const matching = (packet.ptbxl_plus.fiducials.rois ?? []).some((roi) => roi.concept === roiConcept
        && (!interaction.target.lead || roi.lead === interaction.target.lead));
      if (!matching) reasons.push(`Reviewed ${roiConcept.replaceAll("_", " ")} boundaries are unavailable in the required lead.`);
    }
  }
  if (interaction.kind === "march") {
    const perBeatLandmarks = (packet.ptbxl_plus.fiducials as Record<string, unknown>).per_beat_landmarks;
    const irregularObjectives = new Set([
      "atrial_fibrillation",
      "atrial_flutter",
      "premature_atrial_complex",
      "premature_ventricular_complex",
      "av_block_second_degree_mobitz_i",
      "av_block_second_degree_mobitz_ii",
      "av_block_third_degree",
    ]);
    const irregular = packet.supported_objectives?.some((objective) => irregularObjectives.has(objective));
    if (irregular && !Array.isArray(perBeatLandmarks)) reasons.push("This irregular tracing lacks reviewed per-beat landmarks for a scored march.");
  }
  if (!reasons.length) return base;
  const fallback = scene.caseContract?.fallback ?? "lock_scene";
  return {
    eligible: false,
    reasons,
    mode: fallback === "contrast_only" ? "contrast" : fallback === "authored_simulation" ? "simulation" : "locked",
  };
}

type ModuleNavigationReference = Pick<ProductionModule, "id" | "shortTitle">;

export function ProductionModuleExperience({ module, totalModules, priorModule, nextModule }: {
  module: ProductionModule;
  totalModules: number;
  priorModule?: ModuleNavigationReference;
  nextModule?: ModuleNavigationReference;
}) {
  const { user, loading: authLoading } = useAuth();
  const [sceneIndex, setSceneIndex] = useState(0);
  const [runtime, setRuntime] = useState<RuntimeState>({});
  const [runtimeReady, setRuntimeReady] = useState(false);
  const [pathwaySyncError, setPathwaySyncError] = useState<string | null>(null);
  const [guestImportAvailable, setGuestImportAvailable] = useState(false);
  const [importingGuest, setImportingGuest] = useState(false);
  const [sceneMapOpen, setSceneMapOpen] = useState(false);
  const [caseSummary, setCaseSummary] = useState<CaseSummary | null>(null);
  const [packet, setPacket] = useState<CasePacket | null>(null);
  const [caseError, setCaseError] = useState<string | null>(null);
  const [loadingCase, setLoadingCase] = useState(true);
  const [requestedUnavailable, setRequestedUnavailable] = useState(false);
  const [excludedCaseId, setExcludedCaseId] = useState<string | undefined>();
  const [viewerTaskEvidence, setViewerTaskEvidence] = useState<ViewerTaskEvidence | null>(null);
  const [viewerActions, setViewerActions] = useState<ViewerAction[]>([]);
  const [selectedPoint, setSelectedPoint] = useState<ECGPoint | null>(null);
  const [masteryReceipt, setMasteryReceipt] = useState<string | null>(null);
  const pendingDeepLinkedScene = useRef<string | null>(null);
  const pathwaySaveChain = useRef<Promise<unknown>>(Promise.resolve());
  const scene = module.scenes[sceneIndex];

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
    if (!user) {
      const guestRuntime = loadRuntime();
      setRuntime(guestRuntime);
      if (!pendingDeepLinkedScene.current) {
        const resumable = module.scenes.findIndex((item) => {
          const status = guestRuntime[module.id]?.[item.id]?.status;
          return status && status !== "not-started" && status !== "complete";
        });
        if (resumable >= 0) setSceneIndex(resumable);
      }
      setGuestImportAvailable(false);
      setRuntimeReady(true);
      return () => { cancelled = true; };
    }

    const guestRuntime = loadRuntime();
    const importMarker = `${IMPORT_MARKER_PREFIX}:${user.userId}`;
    setGuestImportAvailable(hasGuestProgress(guestRuntime) && window.localStorage.getItem(importMarker) !== "true");
    api.pathwayProgress(user.userId, PATHWAY_ID)
      .then((response) => {
        if (!cancelled) {
          setRuntime(progressItemsToRuntime(response.items));
          if (!pendingDeepLinkedScene.current) {
            const resumableIds = new Set(response.items
              .filter((item) => item.moduleId === module.id && item.status !== "not-started" && item.status !== "complete")
              .map((item) => item.sceneId));
            const resumable = module.scenes.findIndex((item) => resumableIds.has(item.id));
            if (resumable >= 0) setSceneIndex(resumable);
          }
        }
      })
      .catch((error: Error) => {
        if (!cancelled) {
          setRuntime({});
          setPathwaySyncError(`Private pathway progress could not be loaded. ${error.message}`);
        }
      })
      .finally(() => {
        if (!cancelled) setRuntimeReady(true);
      });
    return () => { cancelled = true; };
  }, [authLoading, module.id, module.scenes, user?.userId]);

  useEffect(() => {
    if (pendingDeepLinkedScene.current !== scene.id) return;
    pendingDeepLinkedScene.current = null;
    const timer = window.setTimeout(() => {
      const target = document.getElementById("production-scene-title");
      target?.scrollIntoView({ behavior: "auto", block: "start" });
      target?.focus({ preventScroll: true });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [scene.id]);

  const updateSceneRuntime = useCallback((sceneId: string, updater: (current: SceneRuntime) => SceneRuntime) => {
    setRuntime((current) => {
      const nextScene = updater(current[module.id]?.[sceneId] ?? emptyRuntime());
      const next = { ...current, [module.id]: { ...(current[module.id] ?? {}), [sceneId]: nextScene } };
      if (user) {
        const item = runtimeToProgressItems({ [module.id]: { [sceneId]: nextScene } });
        pathwaySaveChain.current = pathwaySaveChain.current
          .catch(() => undefined)
          .then(() => api.savePathwayProgress(user.userId, item, "server"))
          .then(() => setPathwaySyncError(null))
          .catch((error: Error) => setPathwaySyncError(`Your work is still open, but server sync failed. ${error.message}`));
      } else {
        saveRuntime(next);
      }
      return next;
    });
  }, [module.id, user]);

  useEffect(() => {
    if (!runtimeReady) return;
    const current = runtime[module.id]?.[scene.id] ?? emptyRuntime();
    if (current.status === "not-started") updateSceneRuntime(scene.id, (value) => ({ ...value, status: "viewed" }));
  }, [module.id, runtime, runtimeReady, scene.id, updateSceneRuntime]);

  async function importGuestProgress() {
    if (!user || importingGuest) return;
    const guestRuntime = loadRuntime();
    const items = runtimeToProgressItems(guestRuntime);
    if (!items.length) {
      setGuestImportAvailable(false);
      return;
    }
    setImportingGuest(true);
    setPathwaySyncError(null);
    try {
      const response = await api.savePathwayProgress(user.userId, items, "guest_import");
      const hydrated = await api.pathwayProgress(user.userId, PATHWAY_ID);
      setRuntime(progressItemsToRuntime(hydrated.items.length ? hydrated.items : response.items));
      window.localStorage.setItem(`${IMPORT_MARKER_PREFIX}:${user.userId}`, "true");
      setGuestImportAvailable(false);
    } catch (error) {
      setPathwaySyncError(`Guest progress was not imported. ${error instanceof Error ? error.message : "Try again."}`);
    } finally {
      setImportingGuest(false);
    }
  }

  useEffect(() => {
    setCaseSummary(null);
    setPacket(null);
    setCaseError(null);
    setRequestedUnavailable(false);
    setViewerTaskEvidence(null);
    setViewerActions([]);
    setSelectedPoint(null);
    setMasteryReceipt(null);
    const contract = scene.caseContract;
    if (!contract) {
      setLoadingCase(false);
      return;
    }
    let cancelled = false;
    setLoadingCase(true);
    api.tutorial(contract.selectorLessonId, contract.requestedConcept, excludedCaseId)
      .then(async (result) => {
        if (cancelled) return;
        setRequestedUnavailable(Boolean(result.selection?.requestedConceptUnavailable));
        setCaseSummary(result.recommendedCase);
        const nextPacket = await api.packet(result.recommendedCase.caseId);
        if (!cancelled) setPacket(nextPacket);
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
  const activeInteractionIndex = Math.min(sceneRuntime.activeInteractionIndex, Math.max(0, scene.interactions.length - 1));
  const activeInteraction = scene.interactions[activeInteractionIndex];
  const activeEvidence = activeInteraction ? sceneRuntime.evidence[activeInteraction.id] : undefined;
  const baseEligibility = useMemo(() => caseEligibility(scene, packet, requestedUnavailable), [packet, requestedUnavailable, scene]);
  const eligibility = useMemo(() => interactionCaseEligibility(scene, baseEligibility, activeInteraction, packet), [activeInteraction, baseEligibility, packet, scene]);
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
  const returnTo = encodeURIComponent(`/learn/${module.id}?scene=${scene.id}`);
  const waypoint = `${module.shortTitle} · ${scene.id} ${scene.copy.title} · action ${activeInteractionIndex + 1}`;

  function recordEvidence(evidence: InteractionEvidence) {
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
    const concept = scene.caseContract?.requestedConcept ?? scene.handoffs[0]?.concept ?? "curriculum_foundation";
    const isFinalRequired = scene.completionRule.requiredInteractionIds.every((id) => id === recordedEvidence.interactionId || sceneRuntime.evidence[id]?.correct);
    const evidenceLevel = isFinalRequired && scene.completionRule.requireIndependentAttempt ? "independent_transfer" : "guided";
    const caseProvenance = !scene.caseContract
      ? "authored_simulation"
      : eligibility.mode === "target"
        ? "real_eligible"
        : eligibility.mode === "contrast"
          ? "contrast_only"
          : "authored_simulation";
    void api.recordGuidedEvent({
      learnerId: "demo",
      moduleId: module.id,
      sceneId: scene.id,
      interactionId: recordedEvidence.interactionId,
      concept,
      subskills: activeInteraction?.subskills ?? ["recognize"],
      score: recordedEvidence.score,
      correct: recordedEvidence.correct,
      attempts: recordedEvidence.attempts,
      assistance: recordedEvidence.assistance,
      hintsUsed: recordedEvidence.hintsUsed,
      evidenceLevel,
      caseId: caseSummary?.caseId ?? null,
      caseProvenance,
      caseEligible: eligibility.eligible,
      misconceptions: recordedEvidence.misconceptions,
    }).then((receipt) => {
      const independent = receipt.receipts.filter((item) => item.evidenceLevel === "independent_transfer");
      setMasteryReceipt(independent.length
        ? `Independent evidence recorded for ${independent.map((item) => item.subskill.replaceAll("_", " ")).join(", ")}.`
        : "Formative evidence recorded; independent mastery is unchanged until an eligible transfer.");
    }).catch(() => setMasteryReceipt("The lesson result is saved locally; the server receipt is temporarily unavailable."));
  }

  function recordTutorAssistance() {
    if (!activeInteraction || activeEvidence) return;
    updateSceneRuntime(scene.id, (current) => ({
      ...current,
      assistedInteractionIds: current.assistedInteractionIds.includes(activeInteraction.id)
        ? current.assistedInteractionIds
        : [...current.assistedInteractionIds, activeInteraction.id],
    }));
    setMasteryReceipt("Tutor assistance recorded for this action; the next success is formative until an equivalent independent retry.");
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
      const target = document.getElementById("production-scene-title");
      target?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
      target?.focus({ preventScroll: true });
    }, 0);
  }

  function skipScene() {
    updateSceneRuntime(scene.id, (current) => ({ ...current, status: "skipped" }));
    if (sceneIndex < module.scenes.length - 1) goToScene(sceneIndex + 1);
  }

  const requiredEvidenceForScene = scene.completionRule.requiredInteractionIds.map((id) => sceneRuntime.evidence[id]).filter(Boolean);
  const visualSubskills = new Set(["recognize", "localize", "measure", "discriminate", "synthesize"]);
  const hasIndependentlyEligibleRealCase = Boolean(scene.caseContract && baseEligibility.eligible && caseSummary?.source !== "fixture");
  const sceneHasIndependentEvidence = requiredEvidenceForScene.length === scene.completionRule.requiredInteractionIds.length
    && requiredEvidenceForScene.every((item) => {
      const interaction = scene.interactions.find((candidate) => candidate.id === item.interactionId);
      const subskillsEligible = interaction?.subskills.every((subskill) => {
        if (subskill === "apply_in_context") return false;
        if (visualSubskills.has(subskill)) return hasIndependentlyEligibleRealCase;
        return true;
      });
      return item.correct && item.assistance === "independent" && item.feedbackBranch !== "not_assessable" && Boolean(subskillsEligible);
    });
  const needsIndependentRetry = scene.completionRule.requireIndependentAttempt
    && Object.values(sceneRuntime.evidence).some((item) => item.correct && item.assistance === "scaffolded" && item.feedbackBranch !== "not_assessable")
    && !sceneComplete;

  return (
    <div className="page guided-module production-module" style={{ "--module-accent": module.accent } as React.CSSProperties}>
      <header className="guided-module-header">
        <div className="guided-module-heading">
          <Link className="button subtle small" href="/learn"><ArrowLeft size={15} /> Curriculum</Link>
          <p className="eyebrow">Module {module.order} of {totalModules} · Production guided pathway</p>
          <h1>{module.title}</h1>
          <p>{module.outcome}</p>
          <div className="guided-module-meta">
            <span><Clock3 size={15} /> About {totalMinutes} min total · resume anytime</span>
            <span><Target size={15} /> {module.scenes.length} scenes · {parts.length} chapters</span>
            <details className="guided-source-map">
              <summary><Link2 size={15} /> Source map · {module.sourceRequirementIds.length} requirements</summary>
              <div>{module.sourceRequirementIds.map((sourceId) => <code key={sourceId}>{sourceId}</code>)}</div>
            </details>
          </div>
        </div>
        <div className="guided-progress-card" aria-label={`${completedCount} of ${module.scenes.length} scenes complete`}>
          <div><strong>{progressPercent}%</strong><span>scene completion</span></div>
          <div className="guided-progress-track"><i style={{ width: `${progressPercent}%` }} /></div>
          <p><CheckCircle2 size={14} /> {completedCount} complete · {skippedCount} skipped</p>
          <small>Independent transfer—not time spent or revealed copy—advances competency.</small>
        </div>
      </header>

      <div className={`selection-note production-pathway-sync${pathwaySyncError ? " warning" : ""}`} role={pathwaySyncError ? "alert" : "status"}>
        <div>
          <strong>{authLoading || !runtimeReady ? "Loading pathway progress…" : user ? "Private pathway sync" : "Guest pathway"}</strong>
          <span>{pathwaySyncError ?? (user
            ? "Scene position and completed actions are saved to your account and can resume on another device."
            : "Scene progress is stored only on this device. Sign in when you want private cross-device progress.")}</span>
        </div>
        {user && guestImportAvailable ? (
          <button className="button subtle small" type="button" disabled={importingGuest} onClick={() => void importGuestProgress()}>
            {importingGuest ? "Importing…" : "Import this device’s guest progress"}
          </button>
        ) : null}
      </div>

      <section className="guided-context-strip" aria-label="Learning connections">
        <div><ChevronLeft size={16} /><span><small>Recall from</small><strong>{scene.connections.recallFrom}</strong></span></div>
        <div className="current"><BrainCircuit size={17} /><span><small>Now</small><strong>{scene.connections.changesNow}</strong></span></div>
        <div><ChevronRight size={16} /><span><small>Reuse next</small><strong>{scene.connections.reuseNext}</strong></span></div>
      </section>

      <div className="guided-workspace production-workspace">
        <nav className="guided-scene-rail" aria-label="Module scenes">
          <div className="guided-rail-title"><span>Scene map · {sceneIndex + 1}/{module.scenes.length}</span><button className="button subtle small guided-rail-toggle" type="button" aria-expanded={sceneMapOpen} onClick={() => setSceneMapOpen((open) => !open)}>{sceneMapOpen ? "Hide scenes" : "Choose scene"}</button><small>Skipped and scaffolded remain visible; neither means mastered.</small></div>
          <div className={`guided-scene-list${sceneMapOpen ? " open" : ""}`}>{parts.map((part) => <div className="guided-part" key={part}>
            <p>{part}</p>
            {module.scenes.map((item, index) => {
              if (item.partId !== part) return null;
              const status = runtime[module.id]?.[item.id]?.status ?? "not-started";
              return <button className={`guided-scene-link${index === sceneIndex ? " active" : ""} ${status}`} key={item.id} type="button" onClick={() => goToScene(index)} aria-current={index === sceneIndex ? "step" : undefined}>
                <span title={item.id}>{status === "complete" ? <Check size={13} /> : compactSceneId(item.id)}</span>
                <span><strong>{item.copy.title}</strong><small>{statusLabel(status)} · {item.minutes} min</small></span>
              </button>;
            })}
          </div>)}</div>
        </nav>

        <main className="guided-stage">
          <section className="guided-scene-card production-scene-card">
            <header className="guided-scene-head">
              <div><p className="eyebrow">{scene.copy.eyebrow} · Scene {sceneIndex + 1}/{module.scenes.length}</p><h2 id="production-scene-title" tabIndex={-1}>{scene.copy.title}</h2><p>{scene.copy.objective}</p></div>
              <button className="button subtle small" type="button" onClick={skipScene}><SkipForward size={15} /> Skip & review later</button>
            </header>
            <div className="production-copy-stage">
              {scene.copy.setup.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
              <div className="production-mechanism" aria-label="Mechanism narration">
                <p className="eyebrow"><BrainCircuit size={15} /> Build the mechanism</p>
                {scene.copy.mechanismNarration.slice(0, sceneRuntime.revealedMechanismCount).map((beat, index) => <div key={beat}><i>{index + 1}</i><span>{beat}</span></div>)}
                {sceneRuntime.revealedMechanismCount < scene.copy.mechanismNarration.length ? <button className="button subtle small" type="button" onClick={() => updateSceneRuntime(scene.id, (current) => ({ ...current, revealedMechanismCount: current.revealedMechanismCount + 1 }))}>Reveal the next consequence <ArrowRight size={14} /></button> : null}
              </div>
              <div className="guided-clinical-bridge"><Sparkles size={16} /><span><strong>{scene.copy.clinicalConnectionHeading}</strong>{scene.copy.clinicalConnectionBody}</span></div>
              <p className="production-transition">{scene.copy.transitionIntoTask}</p>
              <details className="production-source-note"><summary>Why this scene is here</summary><p>{scene.source.map((source) => `${source.document} § ${source.section}: ${source.requirementIds.join(", ")}`).join(" · ")}</p></details>
            </div>
          </section>

          {scene.caseContract ? <section className="guided-viewer-wrap" aria-label="Grounded ECG workspace">
            <div className="guided-viewer-label"><div><p className="eyebrow">Grounded ECG workspace</p><strong>{caseSummary?.displayId ?? "Selecting an eligible tracing…"}</strong></div>{packet ? <span>Tier {packet.teaching_tier} · {packet.waveform.sampling_frequency} Hz · {eligibility.mode}</span> : null}</div>
            {loadingCase ? <div className="panel pad guided-loading">Checking the case contract and loading the tracing…</div> : null}
            {caseError ? <div className="warning">The tracing could not load: {caseError}</div> : null}
            {!loadingCase && (packet || caseError) && eligibility.reasons.length ? <div className={`selection-note production-eligibility ${eligibility.mode}`}><strong>{eligibility.mode === "locked" ? "Scene locked for this case" : eligibility.mode === "contrast" ? "Contrast-only tracing" : "Authored mechanism task"}</strong><span>{eligibility.reasons.join(" ")}</span></div> : null}
            {caseSummary && packet ? <ECGViewer caseId={caseSummary.caseId} actions={viewerActions} groundedRois={sceneComplete ? packet.ptbxl_plus.fiducials.rois ?? [] : []} gradingRois={packet.ptbxl_plus.fiducials.rois ?? []} onCoordinate={setSelectedPoint} medianBeats={packet.ptbxl_plus.median_beats} task={viewerTask} onTaskEvidence={setViewerTaskEvidence} /> : null}
          </section> : null}

          <div id="production-active-interaction" className="guided-production-checkpoint" tabIndex={-1}>
            <div className="production-action-progress"><span>Action {activeInteractionIndex + 1} of {scene.interactions.length}</span><div>{scene.interactions.map((interaction, index) => <i key={interaction.id} className={sceneRuntime.evidence[interaction.id]?.correct ? "complete" : index === activeInteractionIndex ? "active" : ""} />)}</div></div>
            {scene.caseContract && loadingCase ? <section className="panel pad guided-loading">The active interaction will appear after its case contract is checked.</section> : activeInteraction && evidenceBoundaryActive ? (
              <section className="learning-interaction production-not-assessable" aria-labelledby={`${activeInteraction.id}-unavailable-title`}>
                <header className="learning-interaction-head"><div><p className="eyebrow"><CircleAlert size={14} /> Evidence boundary</p><h3 id={`${activeInteraction.id}-unavailable-title`}>{activeInteraction.prompt}</h3><p>{activeInteraction.instructions}</p></div><span>Not independently assessable</span></header>
                <div className="learning-interaction-body"><div className="learning-branch partial" role="status"><CircleAlert size={19} /><span><strong>The required exemplar is unavailable.</strong>{eligibility.reasons.join(" ")} The mechanism teaching remains available, but this tracing cannot prove {activeInteraction.subskills.map((skill) => skill.replaceAll("_", " ")).join(" or ")}.</span></div></div>
                <footer className="learning-interaction-actions"><span className="muted">This records formative coverage only; independent mastery is unchanged.</span><button className="button" type="button" onClick={acknowledgeUnavailableEvidence} disabled={activeEvidence?.feedbackBranch === "not_assessable"}>Acknowledge evidence limit & continue</button></footer>
              </section>
            ) : activeInteraction ? <LearningInteractionRenderer key={`${scene.id}-${activeInteraction.id}-${sceneRuntime.equivalentRetryCount}`} interaction={activeInteraction} packetMeasurements={packet?.ptbxl_plus.measurements} viewerEvidence={viewerTask ? viewerTaskEvidence : null} savedEvidence={activeEvidence} onEvidence={recordEvidence} /> : null}
            {activeEvidence?.correct && activeInteractionIndex < scene.interactions.length - 1 ? <div className="production-continue"><p>Keep the evidence you just established. The next action removes one layer of support.</p><button className="button primary" type="button" onClick={advanceInteraction}>Continue to the next action <ArrowRight size={15} /></button></div> : null}
            {masteryReceipt && !sceneComplete ? <p className="production-mastery-receipt" role="status" aria-live="polite"><CheckCircle2 size={15} /> {masteryReceipt}</p> : null}
            {needsIndependentRetry ? <div className="production-retry"><CircleAlert size={18} /><span><strong>Understanding shown; independent evidence still needed.</strong>This success followed the hint ladder. Use an equivalent tracing before completion can count as independent.</span><button className="button" type="button" onClick={startEquivalentRetry}><RotateCcw size={15} /> Load equivalent retry</button></div> : null}
          </div>

          {sceneComplete ? <section className="guided-handoff panel pad" aria-label="Completion and transfer">
            <div><p className="eyebrow">Scene complete · {sceneHasIndependentEvidence ? "independent evidence recorded" : "formative evidence recorded"}</p><h2>{scene.copy.completionHeading}</h2><p>{scene.copy.completionBody}</p>{!sceneHasIndependentEvidence ? <p className="selection-note">The content path is complete, but the unavailable case contract means this scene did not establish independent visual competence. Use the linked Training or Rapid task when an eligible tracing is available.</p> : null}{masteryReceipt ? <p className="production-mastery-receipt"><CheckCircle2 size={15} /> {masteryReceipt}</p> : null}</div>
            <div className="guided-handoff-grid">{scene.handoffs.map((handoff) => {
              const params = new URLSearchParams({ focus: handoff.concept, subskill: handoff.subskill, support: handoff.supportLevel, origin: `${module.id}:${scene.id}`, returnTo: decodeURIComponent(returnTo) });
              const href = handoff.mode === "train" ? `/train?${params}` : handoff.mode === "rapid" ? `/rapid?${params}` : `/practice?${params}`;
              const Icon = handoff.mode === "train" ? Target : handoff.mode === "rapid" ? Clock3 : FlaskConical;
              return <Link key={`${handoff.mode}-${handoff.subskill}`} href={href}><Icon size={18} /><span><strong>{handoff.label}</strong><small>{handoff.subskill.replaceAll("_", " ")} · {handoff.supportLevel}</small></span><ArrowRight size={16} /></Link>;
            })}</div>
          </section> : null}

          <div className="guided-scene-nav">
            <button className="button" type="button" onClick={() => goToScene(sceneIndex - 1)} disabled={sceneIndex === 0}><ChevronLeft size={16} /> Previous</button>
            <span>{statusLabel(sceneRuntime.status)} · {scene.minutes} min</span>
            {sceneIndex < module.scenes.length - 1 ? <button className="button primary" type="button" onClick={() => goToScene(sceneIndex + 1)} disabled={!sceneComplete}>Next scene <ChevronRight size={16} /></button> : nextModule ? <Link className="button primary" href={`/learn/${nextModule.id}`}>Next module <ChevronRight size={16} /></Link> : <Link className="button primary" href="/rapid">Begin mixed transfer <ArrowRight size={16} /></Link>}
          </div>
        </main>

        <aside className="guided-tutor-dock">
          <TutorChat mode="tutorial" caseId={caseSummary?.caseId ?? null} lessonId={scene.caseContract?.selectorLessonId ?? null} openingPrompt={`${scene.copy.openingTutorMessage}${eligibility.reasons.length && !loadingCase ? ` ${scene.tutor.caseUnavailablePrompt}` : ""}`} lessonReturnPrompt={scene.tutor.returnPrompt} lessonReturnLabel={scene.copy.returnLabel} waypointLabel={waypoint} collapsedByDefault={["m06-s11", "m10-s11"].includes(scene.id.toLowerCase())} onReturnToLesson={() => { const target = document.getElementById("production-active-interaction"); target?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" }); target?.focus({ preventScroll: true }); }} viewerState={{ moduleId: module.id, moduleOrder: module.order, sceneId: scene.id, interactionId: activeInteraction?.id, interactionKind: activeInteraction?.kind, interactionPrompt: activeInteraction?.prompt, allowedLeads: activeInteraction && "allowedLeads" in activeInteraction ? activeInteraction.allowedLeads : undefined, measurement: activeInteraction?.kind === "caliper" ? activeInteraction.measurement : undefined, objective: scene.copy.objective, evidence: sceneRuntime.evidence, selectedPoint, caseEligibility: eligibility, pausedWaypoint: scene.tutor.returnPrompt, layoutContract: scene.layout, returnLabel: scene.copy.returnLabel }} onViewerActions={setViewerActions} onAssistance={recordTutorAssistance} resetKey={`${module.id}-${scene.id}-${caseSummary?.caseId ?? "simulation"}-${sceneRuntime.equivalentRetryCount}`} />
          <section className="panel pad guided-tutor-note"><h3><MessageCircleQuestion size={16} /> Ask the tangent</h3><p>{scene.tutor.tangentBridge}</p><p><strong>Return:</strong> {scene.tutor.returnPrompt}</p></section>
        </aside>
      </div>

      <footer className="guided-module-footer">
        {priorModule ? <Link href={`/learn/${priorModule.id}`}><ArrowLeft size={15} /> {priorModule.shortTitle}</Link> : <Link href="/learn/foundations"><ArrowLeft size={15} /> Foundations</Link>}
        <span>Module {module.order}/{totalModules} · {completedCount}/{module.scenes.length} complete · {skippedCount} review later</span>
        {nextModule ? <Link href={`/learn/${nextModule.id}`}>{nextModule.shortTitle} <ArrowRight size={15} /></Link> : <Link href="/rapid">Mixed transfer <ArrowRight size={15} /></Link>}
      </footer>
    </div>
  );
}
