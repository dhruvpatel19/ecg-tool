"use client";

import { ChevronLeft, ChevronRight, Crosshair, Eye, EyeOff, HeartPulse, MousePointer2, PencilLine, RefreshCw, Ruler, Target, Trash2, Undo2, ZoomIn, ZoomOut } from "lucide-react";
import { PointerEvent, type ReactElement, useEffect, useId, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { leadLayout, mapPointToStandardEcgCoordinate, type ECGPoint } from "@/lib/coordinates";
import type { ClickGradeResult, EcgCapability, GroundedRoi, MedianBeats, ViewerAction, ViewerTaskEvidence, ViewerTaskSpec, WaveformResponse, WaveformScope } from "@/lib/types";

const WIDTH = 1200;
// At the default 10-second window, 1200 px / (10 s * 25 mm/s) = 4.8 px/mm.
// Four 4 mV rows at 10 mm/mV therefore require 4 * 4 * 10 * 4.8 = 768 px.
// This makes every 1 mm ECG box square and gives the standard 2.5 s per column.
const HEIGHT = 768;
const COLS = 4;
const LEAD_ROWS = 3;
const ROWS = 4;
const CELL_W = WIDTH / COLS;
const CELL_H = HEIGHT / ROWS;
// ECG paper standard at 25 mm/s, 10 mm/mV.
const PAPER_SPEED_MM_PER_SEC = 25;
const GAIN_MM_PER_MV = 10;
const SMALL_BOX_SEC = 0.04;
const LARGE_BOX_SEC = 0.2;
const DEFAULT_DURATION_SEC = 10;
const DEFAULT_PX_PER_MM = WIDTH / (DEFAULT_DURATION_SEC * PAPER_SPEED_MM_PER_SEC);
const MEDIAN_HEIGHT = CELL_H * LEAD_ROWS;

type UserRoi = GroundedRoi & { source: "user" };

type ClickFeedback = ClickGradeResult & { point: ECGPoint };

type ViewerPoint = ECGPoint & { placementKey: string };

type ViewerTool = "inspect" | "point" | "region" | "caliper" | "march" | "annotate";

type ScopedWaveformState = {
  ecgRef: EcgCapability;
  scopeKey: string;
  windowKey: string;
  data: WaveformResponse;
};

type ScopedRequestState = {
  ecgRef: EcgCapability;
  scopeKey: string;
  windowKey: string;
};

function taskTool(task?: ViewerTaskSpec): ViewerTool | null {
  if (!task) return null;
  return task.mode;
}

function windowKey(start: number, end: number) {
  return `${start.toFixed(6)}:${end.toFixed(6)}`;
}

function taskRoiConcept(task?: ViewerTaskSpec) {
  if (!task) return null;
  if (task.mode === "point" || task.mode === "region") return task.concept;
  if (task.mode === "caliper") {
    if (task.measurement === "pr") return "pr_interval";
    if (task.measurement === "qrs") return "qrs_complex";
    if (task.measurement === "qt") return "qt_segment";
    return null;
  }
  if (task.mode === "march") return task.target === "p_waves" ? "p_wave" : "qrs_complex";
  return null;
}

type ECGViewerProps = {
  /** Opaque ECG request capability. It must never be rendered as a learner label. */
  ecgRef: EcgCapability;
  /** Owner/session scope required by assessment waveform routes. */
  waveformScope?: WaveformScope;
  actions?: ViewerAction[];
  groundedRois?: GroundedRoi[];
  /** Hidden reviewed geometry used to frame and validate a task without revealing labels. */
  gradingRois?: GroundedRoi[];
  onCoordinate?: (point: ECGPoint) => void;
  /** Concept the lesson wants the learner to click (e.g. "st_segment"); scopes /grade/click. */
  gradeConcept?: string;
  /** Optional label shown in the identify-feature banner (e.g. "the J point"). */
  gradePrompt?: string;
  /** Clean averaged median beat per lead (from the case packet) for the median-beat view. */
  medianBeats?: MedianBeats | null;
  /** Fired once after the first waveform for this case renders (used to start the decision clock). */
  onReady?: () => void;
  /** "clinical" uses a contextual, labeled command bar; "none" hides toolbar + help. */
  toolbar?: "full" | "clinical" | "none";
  /** Optional curriculum task. When present, the viewer becomes the response surface rather than decorative context. */
  task?: ViewerTaskSpec;
  /** Emits the actual waveform evidence collected by the active curriculum task. */
  onTaskEvidence?: (evidence: ViewerTaskEvidence) => void;
  /** Clears parent-owned evidence when learner task marks are removed. */
  onTaskReset?: () => void;
  /** Assessment modes collect raw evidence; only Guided may request immediate correctness. */
  gradingMode?: "immediate" | "deferred";
  /** Completed review keeps local annotation tools but removes every grading affordance. */
  reviewMode?: boolean;
  /** Assessment-selected ECG surface. Rhythm strips render one-to-three full-width leads. */
  presentation?: {
    kind: "twelve_lead" | "rhythm_strip";
    leads?: string[];
  };
  /** Server-signed context required by immediate Guided grading endpoints. */
  guidedContext?: string | null;
};

export function ECGViewer({ ecgRef, waveformScope, actions = [], groundedRois = [], gradingRois = [], onCoordinate, gradeConcept, gradePrompt, medianBeats = null, onReady, toolbar, task, onTaskEvidence, onTaskReset, gradingMode = "immediate", reviewMode = false, presentation = { kind: "twelve_lead" }, guidedContext = null }: ECGViewerProps) {
  const [loadedWaveform, setLoadedWaveform] = useState<ScopedWaveformState | null>(null);
  const [loadError, setLoadError] = useState<(ScopedRequestState & { message: string }) | null>(null);
  const [loadingRequest, setLoadingRequest] = useState<ScopedRequestState | null>(null);
  const [loadVersion, setLoadVersion] = useState(0);
  const [timeWindow, setTimeWindow] = useState({ start: 0, end: 10 });
  const [highlightedLeads, setHighlightedLeads] = useState<string[]>([]);
  const [overlays, setOverlays] = useState<ViewerAction[]>([]);
  const [selectedPoint, setSelectedPoint] = useState<ECGPoint | null>(null);
  const [dragStart, setDragStart] = useState<ViewerPoint | null>(null);
  const [userRois, setUserRois] = useState<UserRoi[]>([]);
  const [selectedTool, setSelectedTool] = useState<ViewerTool>("inspect");
  const [clickFeedback, setClickFeedback] = useState<ClickFeedback | null>(null);
  const [grading, setGrading] = useState(false);
  const [showAllLabels, setShowAllLabels] = useState(false);
  const [hoveredRoiKey, setHoveredRoiKey] = useState<string | null>(null);
  const [medianMode, setMedianMode] = useState(false);
  const [marchPoints, setMarchPoints] = useState<ECGPoint[]>([]);
  const [taskFeedback, setTaskFeedback] = useState<string | null>(null);
  const [keyboardLead, setKeyboardLead] = useState("II");
  const [keyboardStart, setKeyboardStart] = useState("0.50");
  const [keyboardEnd, setKeyboardEnd] = useState("0.70");
  const svgRef = useRef<SVGSVGElement | null>(null);
  const stageRef = useRef<HTMLDivElement | null>(null);
  const readyFired = useRef(false);
  const onReadyRef = useRef(onReady);
  const taskRef = useRef(task);
  const gradingRoisRef = useRef(gradingRois);
  const initializedTaskKeyRef = useRef<string | null>(null);
  const clipPrefix = useId().replaceAll(":", "");

  onReadyRef.current = onReady;
  taskRef.current = task;
  gradingRoisRef.current = gradingRois;

  // Parents construct task/ROI objects while rendering. Depend on their
  // semantic contents so an equivalent rerender does not reset the ECG view,
  // while a genuinely different task still does.
  const taskSignature = task ? JSON.stringify(task) : "";
  const gradingRoisSignature = gradingMode === "immediate"
    ? gradingRois.map((roi) => `${roi.concept}:${roi.lead}:${roi.timeStartSec}:${roi.timeEndSec}`).join("|")
    : "";
  const waveformScopeKind = waveformScope?.kind ?? "catalog";
  const waveformReviewSessionRef = waveformScope?.kind === "review" ? waveformScope.sessionRef : "";
  const waveformReviewAttemptIndex = waveformScope?.kind === "review" ? waveformScope.attemptIndex : 0;
  const waveformScopeId = waveformScope?.kind === "guided"
    ? waveformScope.lessonId
    : waveformScope?.kind === "training"
      ? waveformScope.campaignId
    : waveformScope?.kind === "rapid"
      ? waveformScope.roundId
      : waveformScope?.kind === "clinical"
        ? waveformScope.sessionId
        : waveformScope?.kind === "review"
          ? `${waveformReviewSessionRef}:${waveformReviewAttemptIndex}`
        : "";
  const waveformScopeKey = `${waveformScopeKind}:${waveformScopeId}`;
  const presentationLeadSignature = (presentation.leads ?? []).filter(Boolean).join("|");
  const rhythmStripLeads = useMemo(() => presentation.kind === "rhythm_strip"
    ? Array.from(new Set(presentationLeadSignature ? presentationLeadSignature.split("|") : ["II"])).slice(0, 3)
    : [], [presentation.kind, presentationLeadSignature]);
  const rhythmStripMode = rhythmStripLeads.length > 0;
  const presentationHeight = rhythmStripMode ? CELL_H * rhythmStripLeads.length : HEIGHT;
  const presentationSignature = `${presentation.kind}:${rhythmStripLeads.join(",")}`;
  const taskInitializationKey = `${ecgRef}|${waveformScopeKey}|${gradingMode}|${taskSignature}|${gradingRoisSignature}|${presentationSignature}`;
  const requestedWindowKey = windowKey(timeWindow.start, timeWindow.end);
  const effectiveToolbar = toolbar ?? (waveformScopeKind === "clinical" ? "clinical" : "full");
  const lockedTool = taskTool(task);
  const activeTool = lockedTool ?? selectedTool;
  const identifyMode = activeTool === "point";

  // A prop change must hide the previous patient's trace during the very first
  // render, before effects have a chance to run. Matching the requested window
  // also prevents a narrow, previously loaded response from being stretched or
  // presented as complete while a wider pan/zoom request is in flight.
  const waveform = loadedWaveform
    && loadedWaveform.ecgRef === ecgRef
    && loadedWaveform.scopeKey === waveformScopeKey
    && loadedWaveform.windowKey === requestedWindowKey
    ? loadedWaveform.data
    : null;
  const error = loadError
    && loadError.ecgRef === ecgRef
    && loadError.scopeKey === waveformScopeKey
    && loadError.windowKey === requestedWindowKey
    ? loadError.message
    : null;
  const loading = Boolean(
    loadingRequest
    && loadingRequest.ecgRef === ecgRef
    && loadingRequest.scopeKey === waveformScopeKey
    && loadingRequest.windowKey === requestedWindowKey,
  ) || (!waveform && !error);
  const waveformDuration = loadedWaveform
    && loadedWaveform.ecgRef === ecgRef
    && loadedWaveform.scopeKey === waveformScopeKey
    ? loadedWaveform.data.durationSec
    : DEFAULT_DURATION_SEC;
  const medianAvailable = Boolean(medianBeats?.available) && !rhythmStripMode;

  // Reset the one-shot ready signal when the scoped ECG request changes.
  useEffect(() => {
    readyFired.current = false;
  }, [ecgRef, waveformScopeKey]);

  useEffect(() => {
    let cancelled = false;
    const requestWindowKey = windowKey(timeWindow.start, timeWindow.end);
    const requestScope: WaveformScope = waveformScopeKind === "guided"
      ? { kind: "guided", lessonId: waveformScopeId }
      : waveformScopeKind === "training"
        ? { kind: "training", campaignId: waveformScopeId }
      : waveformScopeKind === "rapid"
        ? { kind: "rapid", roundId: waveformScopeId }
        : waveformScopeKind === "clinical"
          ? { kind: "clinical", sessionId: waveformScopeId }
          : waveformScopeKind === "review"
            ? {
                kind: "review",
                sessionRef: waveformReviewSessionRef,
                attemptIndex: waveformReviewAttemptIndex,
              }
          : { kind: "catalog" };
    setLoadError(null);
    setLoadingRequest({ ecgRef, scopeKey: waveformScopeKey, windowKey: requestWindowKey });
    api
      .waveform(ecgRef, timeWindow.start, timeWindow.end, undefined, requestScope)
      .then((data) => {
        if ((data.ecgRef ?? data.caseId) !== ecgRef) {
          throw new Error("Waveform capability mismatch");
        }
        if (!cancelled) {
          setLoadedWaveform({ ecgRef, scopeKey: waveformScopeKey, windowKey: requestWindowKey, data });
          setLoadingRequest(null);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setLoadingRequest(null);
          setLoadError({
            ecgRef,
            scopeKey: waveformScopeKey,
            windowKey: requestWindowKey,
            message: err.name === "AbortError"
              ? "This ECG took too long to load."
              : "This ECG could not be loaded.",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [ecgRef, waveformReviewAttemptIndex, waveformReviewSessionRef, waveformScopeId, waveformScopeKey, waveformScopeKind, timeWindow.start, timeWindow.end, loadVersion]);

  // A resolved network request is not the same as a learner-visible tracing.
  // Fire readiness on the paint after React has committed the scoped waveform
  // and SVG, so timed assessments cannot begin while the prior loading state is
  // still on screen.
  useEffect(() => {
    if (!waveform || readyFired.current) return;
    const frame = window.requestAnimationFrame(() => {
      if (!svgRef.current || readyFired.current) return;
      readyFired.current = true;
      onReadyRef.current?.();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [waveform]);

  // Reset graded feedback and annotations when the scoped ECG request changes.
  useEffect(() => {
    setClickFeedback(null);
    setSelectedTool("inspect");
    setUserRois([]);
    setOverlays([]);
    setHighlightedLeads([]);
    setSelectedPoint(null);
    setHoveredRoiKey(null);
    setMedianMode(false);
    setMarchPoints([]);
    setTaskFeedback(null);
  }, [ecgRef, waveformScopeKey]);

  useEffect(() => {
    if (!reviewMode) return;
    setSelectedTool("inspect");
    setClickFeedback(null);
    setTaskFeedback(null);
  }, [reviewMode]);

  useEffect(() => {
    // Loading a waveform (and later zooming or panning it) may change the
    // response duration. That must not reinitialize precise-entry controls and
    // overwrite evidence the learner has already entered for this task.
    if (initializedTaskKeyRef.current === taskInitializationKey) return;
    initializedTaskKeyRef.current = taskInitializationKey;
    const activeTask = taskRef.current;
    const activeGradingRois = gradingRoisRef.current;
    setMarchPoints([]);
    setUserRois([]);
    setTaskFeedback(null);
    setSelectedTool("inspect");
    setClickFeedback(null);
    const concept = taskRoiConcept(activeTask);
    // Reviewed answer geometry may frame a scaffolded Guided task. Deferred
    // assessment modes must remain blind: an answer ROI must never choose the
    // lead, viewport, scroll position, or precise-entry defaults precommit.
    const reviewed = gradingMode === "immediate"
      ? activeGradingRois.find((roi) => roi.concept === concept
        && (!activeTask?.allowedLeads?.length || activeTask.allowedLeads.includes(roi.lead)))
      : undefined;
    const lead = reviewed?.lead
      ?? activeTask?.allowedLeads?.find((candidate) => !rhythmStripMode || rhythmStripLeads.includes(candidate))
      ?? rhythmStripLeads[0]
      ?? activeTask?.allowedLeads?.[0]
      ?? "II";
    const nextWindow = reviewed
      ? fitActionWindowToLead(reviewed.timeStartSec - 0.12, reviewed.timeEndSec + 0.12, lead, waveform?.durationSec ?? 10)
      : { start: 0, end: waveform?.durationSec ?? 10 };
    setTimeWindow(nextWindow);
    setKeyboardLead(lead);
    const placement = placementsForLead(lead, nextWindow, rhythmStripMode ? rhythmStripLeads : undefined)[0] ?? null;
    // When a reviewed boundary exists, make the precise-entry alternative begin on
    // that sampled interval. A generic percentage of the visible panel can land
    // between the input's sampling steps and imply a clinically unrelated default.
    const first = reviewed?.timeStartSec
      ?? (placement ? placement.timeStart + (placement.timeEnd - placement.timeStart) * 0.18 : nextWindow.start);
    const second = reviewed?.timeEndSec
      ?? (placement ? placement.timeStart + (placement.timeEnd - placement.timeStart) * 0.72 : Math.min(nextWindow.end, first + 0.2));
    setKeyboardStart(first.toFixed(3));
    setKeyboardEnd(second.toFixed(3));
    window.setTimeout(() => {
      const stage = stageRef.current;
      if (!stage || rhythmStripMode || stage.scrollWidth <= stage.clientWidth) return;
      let column = 0;
      for (const row of leadLayout) {
        const index = row.indexOf(lead as never);
        if (index >= 0) { column = index; break; }
      }
      const columnWidth = stage.scrollWidth / COLS;
      stage.scrollLeft = Math.max(0, column * columnWidth - (stage.clientWidth - columnWidth) / 2);
    }, 0);
  }, [ecgRef, waveformScopeKey, gradingMode, taskSignature, gradingRoisSignature, taskInitializationKey, waveform?.durationSec, presentationSignature, rhythmStripLeads, rhythmStripMode]);

  // Drop out of median-beat mode if the new case has no median beats.
  useEffect(() => {
    if (!medianAvailable) setMedianMode(false);
  }, [medianAvailable]);

  const signalByLead = useMemo(() => {
    const map = new Map<string, WaveformResponse["leads"][number]["points"]>();
    waveform?.leads.forEach((lead) => map.set(lead.lead, lead.points));
    return map;
  }, [waveform]);

  const printScale = useMemo(() => paperScale(timeWindow), [timeWindow]);
  const actionsSignature = JSON.stringify(actions);

  function resetView() {
    setTimeWindow({ start: 0, end: waveformDuration });
    setSelectedPoint(null);
  }

  function zoom(factor: number) {
    const duration = waveformDuration;
    const center = (timeWindow.start + timeWindow.end) / 2;
    const span = Math.max(0.8, Math.min(duration, (timeWindow.end - timeWindow.start) * factor));
    const start = Math.max(0, Math.min(duration - span, center - span / 2));
    setTimeWindow({ start, end: start + span });
  }

  function pan(delta: number) {
    const duration = waveformDuration;
    const span = timeWindow.end - timeWindow.start;
    const nextStart = Math.max(0, Math.min(duration - span, timeWindow.start + delta));
    setTimeWindow({ start: nextStart, end: nextStart + span });
  }

  useEffect(() => {
    const nextActions = JSON.parse(actionsSignature) as ViewerAction[];
    let visibleStart = 0;
    for (let index = 0; index < nextActions.length; index += 1) {
      if (nextActions[index].type === "resetView") visibleStart = index + 1;
    }
    const visibleActions = nextActions.slice(visibleStart);
    const nextOverlays = visibleActions.filter((action) => ["highlightROI", "circleROI", "drawCaliper", "showFiducial"].includes(action.type));
    const uniqueOverlays = Array.from(new Map(nextOverlays.map((action) => [JSON.stringify(action), action])).values());
    setOverlays(uniqueOverlays);
    setHighlightedLeads(Array.from(new Set(
      visibleActions
        .filter((action) => action.type === "highlightLead" || ["highlightROI", "circleROI", "drawCaliper", "showFiducial"].includes(action.type))
        .map((action) => action.lead)
        .filter((lead): lead is string => Boolean(lead)),
    )));

    if (visibleStart > 0) {
      setTimeWindow({ start: 0, end: waveformDuration });
      setSelectedPoint(null);
    }
    const zoomAction = [...visibleActions].reverse().find((action) => action.type === "zoom" && action.timeStart !== undefined && action.timeEnd !== undefined);
    if (zoomAction?.timeStart !== undefined && zoomAction.timeEnd !== undefined) {
      setTimeWindow(fitActionWindowToLead(zoomAction.timeStart, zoomAction.timeEnd, zoomAction.leads?.[0], waveformDuration));
    }
  }, [actionsSignature, ecgRef, waveformDuration, waveformScopeKey]);

  function eventToPoint(event: PointerEvent<SVGSVGElement>): ViewerPoint | null {
    const svg = svgRef.current;
    if (!svg) return null;
    let x: number;
    let y: number;
    const matrix = svg.getScreenCTM();
    if (matrix) {
      const screenPoint = svg.createSVGPoint();
      screenPoint.x = event.clientX;
      screenPoint.y = event.clientY;
      const localPoint = screenPoint.matrixTransform(matrix.inverse());
      x = localPoint.x;
      y = localPoint.y;
    } else {
      const rect = svg.getBoundingClientRect();
      x = ((event.clientX - rect.left) / rect.width) * WIDTH;
      y = ((event.clientY - rect.top) / rect.height) * HEIGHT;
    }
    try {
      if (rhythmStripMode) {
        if (x < 0 || x > WIDTH || y < 0 || y > presentationHeight) return null;
        const row = Math.min(Math.floor(y / CELL_H), rhythmStripLeads.length - 1);
        const lead = rhythmStripLeads[row];
        if (!lead) return null;
        const localY = y - row * CELL_H;
        const scale = paperScale(timeWindow);
        return {
          lead,
          timeSec: Number((timeWindow.start + x / scale.pxPerSec).toFixed(3)),
          amplitudeMv: Number(((CELL_H / 2 - localY) / scale.pxPerMv).toFixed(3)),
          placementKey: `strip-${row}`,
        };
      }
      const point = mapPointToStandardEcgCoordinate(
        x,
        y,
        WIDTH,
        HEIGHT,
        timeWindow.start,
        timeWindow.end,
        PAPER_SPEED_MM_PER_SEC,
        GAIN_MM_PER_MV,
      );
      const row = Math.min(Math.floor(y / CELL_H), ROWS - 1);
      const column = Math.min(Math.floor(x / CELL_W), COLS - 1);
      return { ...point, placementKey: row === ROWS - 1 ? "rhythm-II" : `lead-${row}-${column}` };
    } catch {
      return null;
    }
  }

  async function gradeAt(point: ECGPoint) {
    if (grading) return null;
    if (reviewMode) {
      setClickFeedback(null);
      setTaskFeedback(null);
      return null;
    }
    if (gradingMode === "deferred") {
      setClickFeedback(null);
      setTaskFeedback("Point recorded. Correctness will be revealed after you commit your response.");
      if (task?.mode === "point") onTaskEvidence?.({ mode: "point", point });
      return null;
    }
    setGrading(true);
    try {
      const result = await api.gradeClick(ecgRef, {
        lead: point.lead,
        timeSec: point.timeSec,
        amplitudeMv: point.amplitudeMv,
        concept: task?.mode === "point" ? task.concept : gradeConcept ?? null,
        guidedContext,
      });
      setClickFeedback({ ...result, point });
      if (task?.mode === "point") {
        onTaskEvidence?.({ mode: "point", point, correct: result.correct, noTarget: result.noTarget, feedback: result.feedback });
      }
      return result;
    } catch (err) {
      const fallback = {
        correct: false,
        feedback: err instanceof Error ? err.message : "Could not grade this click.",
        matchedRoi: null,
        point,
      };
      setClickFeedback(fallback);
      if (task?.mode === "point") onTaskEvidence?.({ mode: "point", point, correct: false, feedback: fallback.feedback });
      return fallback;
    } finally {
      setGrading(false);
    }
  }

  async function gradeRegion(roi: UserRoi) {
    if (grading) return;
    if (task?.mode !== "region") return;
    if (gradingMode === "deferred") {
      setTaskFeedback("Region recorded. Correctness will be revealed after you commit your response.");
      onTaskEvidence?.({ mode: "region", roi });
      return;
    }
    setGrading(true);
    try {
      const result = await api.gradeRegion(ecgRef, {
        lead: roi.lead,
        timeStartSec: roi.timeStartSec,
        timeEndSec: roi.timeEndSec,
        ampMinMv: roi.ampMinMv,
        ampMaxMv: roi.ampMaxMv,
        concept: task.concept,
        guidedContext,
      });
      setTaskFeedback(result.feedback);
      onTaskEvidence?.({ mode: "region", roi, correct: result.correct, noTarget: result.noTarget, feedback: result.feedback });
    } catch (error) {
      const feedback = error instanceof Error ? error.message : "The region could not be graded.";
      setTaskFeedback(feedback);
      onTaskEvidence?.({ mode: "region", roi, correct: false, feedback });
    } finally {
      setGrading(false);
    }
  }

  async function gradeCaliperRegion(roi: UserRoi, valueMs: number) {
    if (grading) return;
    if (task?.mode !== "caliper") return;
    const concept = taskRoiConcept(task);
    if (!concept) {
      setTaskFeedback(`${task.measurement.toUpperCase()} span: ${valueMs} ms in ${roi.lead}.`);
      onTaskEvidence?.({ mode: "caliper", lead: roi.lead, timeStartSec: roi.timeStartSec, timeEndSec: roi.timeEndSec, valueMs });
      return;
    }
    if (gradingMode === "deferred") {
      setTaskFeedback(`${task.measurement.toUpperCase()} span recorded at ${valueMs} ms. Correctness will be revealed after commit.`);
      onTaskEvidence?.({ mode: "caliper", lead: roi.lead, timeStartSec: roi.timeStartSec, timeEndSec: roi.timeEndSec, valueMs });
      return;
    }
    setGrading(true);
    try {
      const result = await api.gradeRegion(ecgRef, {
        lead: roi.lead,
        timeStartSec: roi.timeStartSec,
        timeEndSec: roi.timeEndSec,
        ampMinMv: roi.ampMinMv,
        ampMaxMv: roi.ampMaxMv,
        concept,
        guidedContext,
      });
      const feedback = result.noTarget
        ? `No reviewed ${concept.replaceAll("_", " ")} boundary is available here. ${result.feedback}`
        : result.correct
          ? `${task.measurement.toUpperCase()} boundaries overlap the reviewed waveform region · ${valueMs} ms.`
          : `The ${valueMs} ms span does not sit on the reviewed ${concept.replaceAll("_", " ")} boundaries. ${result.feedback}`;
      setTaskFeedback(feedback);
      onTaskEvidence?.({ mode: "caliper", lead: roi.lead, timeStartSec: roi.timeStartSec, timeEndSec: roi.timeEndSec, valueMs, correct: result.correct, noTarget: result.noTarget, feedback });
    } catch (error) {
      const feedback = error instanceof Error ? error.message : "The caliper boundaries could not be validated.";
      setTaskFeedback(feedback);
      onTaskEvidence?.({ mode: "caliper", lead: roi.lead, timeStartSec: roi.timeStartSec, timeEndSec: roi.timeEndSec, valueMs, correct: false, feedback });
    } finally {
      setGrading(false);
    }
  }

  async function addMarchedPoint(point: ECGPoint) {
    if (grading) return;
    if (task?.mode !== "march") return;
    if (gradingMode === "deferred") {
      setMarchPoints((current) => {
        const duplicate = current.some((existing) => existing.lead === point.lead && Math.abs(existing.timeSec - point.timeSec) < 0.08);
        const next = duplicate ? current : [...current, point].sort((a, b) => a.timeSec - b.timeSec);
        setTaskFeedback(`${next.length} of ${task.minimumMarkers} markers recorded. Correctness follows commit.`);
        onTaskEvidence?.({ mode: "march", points: next });
        return next;
      });
      return;
    }
    const concept = task.target === "p_waves" ? "p_wave" : "qrs_complex";
    setGrading(true);
    try {
      const result = await api.gradeClick(ecgRef, {
        lead: point.lead,
        timeSec: point.timeSec,
        amplitudeMv: point.amplitudeMv,
        concept,
        guidedContext,
      });
      if (!result.correct) {
        setTaskFeedback(result.noTarget ? `This case cannot safely grade ${task.target.replaceAll("_", " ")}: ${result.feedback}` : result.feedback);
        return;
      }
      setMarchPoints((current) => {
        const duplicate = current.some((existing) => existing.lead === point.lead && Math.abs(existing.timeSec - point.timeSec) < 0.08);
        const next = duplicate ? current : [...current, point].sort((a, b) => a.timeSec - b.timeSec);
        setTaskFeedback(`${next.length} of ${task.minimumMarkers} validated markers placed.`);
        onTaskEvidence?.({ mode: "march", points: next });
        return next;
      });
    } catch (error) {
      setTaskFeedback(error instanceof Error ? error.message : "The marker could not be graded.");
    } finally {
      setGrading(false);
    }
  }

  function waveformPointAt(lead: string, timeSec: number): ECGPoint | null {
    const visiblePlacements = placementsForLead(lead, timeWindow, rhythmStripMode ? rhythmStripLeads : undefined);
    if (!visiblePlacements.some((placement) => placementContainsTime(placement, timeSec))) return null;
    const points = (signalByLead.get(lead) ?? []).filter((point) => visiblePlacements.some((placement) => placementContainsTime(placement, point.timeSec)));
    if (!points.length || !Number.isFinite(timeSec)) return null;
    let nearest = points[0];
    for (const point of points) {
      if (Math.abs(point.timeSec - timeSec) < Math.abs(nearest.timeSec - timeSec)) nearest = point;
    }
    return { lead, timeSec: nearest.timeSec, amplitudeMv: nearest.amplitudeMv };
  }

  function waveformRoi(
    lead: string,
    timeStartSec: number,
    timeEndSec: number,
    label: string,
    concept: string,
  ): UserRoi | null {
    const segment = (signalByLead.get(lead) ?? []).filter(
      (sample) => sample.timeSec >= timeStartSec && sample.timeSec <= timeEndSec,
    );
    if (!segment.length) return null;
    const amplitudes = segment.map((sample) => sample.amplitudeMv);
    return {
      lead,
      timeStartSec,
      timeEndSec,
      ampMinMv: Math.min(...amplitudes) - 0.03,
      ampMaxMv: Math.max(...amplitudes) + 0.03,
      label,
      concept,
      source: "user",
      confidence: "low",
    };
  }

  async function submitKeyboardTask() {
    if (!task) return;
    const start = Number(keyboardStart);
    const end = Number(keyboardEnd);
    const point = waveformPointAt(keyboardLead, start);
    if (!point) {
      setTaskFeedback("Choose an available lead and a time within the displayed tracing.");
      return;
    }
    setSelectedPoint(point);
    onCoordinate?.(point);
    if (task.mode === "point") {
      await gradeAt(point);
      return;
    }
    if (task.mode === "march") {
      await addMarchedPoint(point);
      return;
    }
    if (!Number.isFinite(end) || end <= start) {
      setTaskFeedback("The second boundary must occur after the first boundary.");
      return;
    }
    const placements = placementsForLead(keyboardLead, timeWindow, rhythmStripMode ? rhythmStripLeads : undefined);
    const placement = placements.find((candidate) => placementContainsTime(candidate, start) && placementContainsTime(candidate, end));
    if (!placement) {
      const firstPlacement = placements[0];
      setTaskFeedback(firstPlacement
        ? `Both boundaries must stay inside the same visible ${keyboardLead} panel.`
        : `Lead ${keyboardLead} is not visible in this layout.`);
      return;
    }
    const startSec = Math.max(0, Math.min(start, waveformDuration));
    const endSec = Math.max(startSec, Math.min(end, waveformDuration));
    const valueMs = Math.round((endSec - startSec) * 1000);
    const roi = waveformRoi(
      keyboardLead,
      startSec,
      endSec,
      task.mode === "caliper" ? `${task.measurement.toUpperCase()} · ${valueMs} ms` : "Keyboard-selected region",
      task.mode === "region" ? task.concept : task.measurement,
    );
    if (!roi) {
      setTaskFeedback("No waveform samples fall between those boundaries.");
      return;
    }
    setUserRois([roi]);
    onTaskReset?.();
    if (task.mode === "region") {
      const minimum = task.minimumDurationMs ?? 0;
      if (valueMs < minimum) setTaskFeedback(`Make the region at least ${minimum} ms wide so it contains the full feature.`);
      else await gradeRegion(roi);
      return;
    }
    await gradeCaliperRegion(roi, valueMs);
  }

  function leadAllowed(lead: string) {
    return !task?.allowedLeads?.length || task.allowedLeads.includes(lead);
  }

  function onPointerDown(event: PointerEvent<SVGSVGElement>) {
    if (grading || medianMode || !["region", "caliper", "annotate"].includes(activeTool)) return;
    const point = eventToPoint(event);
    if (point) {
      event.currentTarget.setPointerCapture(event.pointerId);
      setDragStart(point);
    }
  }

  async function onPointerUp(event: PointerEvent<SVGSVGElement>) {
    const point = eventToPoint(event);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    if (!point) {
      setDragStart(null);
      return;
    }
    if (task && !leadAllowed(point.lead)) {
      setTaskFeedback(`Use ${task.allowedLeads?.join(", ")}. Your mark in ${point.lead} was not submitted.`);
      setDragStart(null);
      return;
    }
    setSelectedPoint(point);
    onCoordinate?.(point);
    if (activeTool === "point") {
      if (!grading) void gradeAt(point);
      setDragStart(null);
      return;
    }
    if (activeTool === "march") {
      if (!grading) void addMarchedPoint(point);
      setDragStart(null);
      return;
    }
    if (activeTool === "inspect") {
      setDragStart(null);
      return;
    }
    if (dragStart && dragStart.placementKey === point.placementKey && Math.abs(point.timeSec - dragStart.timeSec) > 0.04) {
      const timeStartSec = Math.min(dragStart.timeSec, point.timeSec);
      const timeEndSec = Math.max(dragStart.timeSec, point.timeSec);
      const valueMs = Math.round((timeEndSec - timeStartSec) * 1000);
      const roi = activeTool === "annotate"
        ? {
            lead: point.lead,
            timeStartSec,
            timeEndSec,
            ampMinMv: Math.min(dragStart.amplitudeMv, point.amplitudeMv),
            ampMaxMv: Math.max(dragStart.amplitudeMv, point.amplitudeMv),
            label: "Learner annotation",
            concept: "learner_annotation",
            source: "user" as const,
            confidence: "low",
          }
        : waveformRoi(
            point.lead,
            timeStartSec,
            timeEndSec,
            task?.mode === "caliper" ? `${task.measurement.toUpperCase()} · ${valueMs} ms` : "Learner-selected region",
            task?.mode === "region" ? task.concept : task?.mode === "caliper" ? task.measurement : "learner_annotation",
          );
      if (!roi) {
        setTaskFeedback("No waveform samples fall between those boundaries.");
        setDragStart(null);
        return;
      }
      if (activeTool === "annotate") {
        setUserRois((current) => [...current, roi]);
      } else {
        setUserRois([roi]);
        onTaskReset?.();
      }
      if (task?.mode === "region") {
        const minimum = task.minimumDurationMs ?? 0;
        if (valueMs < minimum) setTaskFeedback(`Make the region at least ${minimum} ms wide so it contains the full feature.`);
        else void gradeRegion(roi);
      }
      if (task?.mode === "caliper") {
        await gradeCaliperRegion(roi, valueMs);
      }
    }
    setDragStart(null);
  }

  function onPointerCancel(event: PointerEvent<SVGSVGElement>) {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    setDragStart(null);
  }

  function clearTaskMarks() {
    setMarchPoints([]);
    setUserRois([]);
    setTaskFeedback(null);
    onTaskReset?.();
    if (task?.mode === "march") onTaskEvidence?.({ mode: "march", points: [] });
  }

  const visibleSpan = timeWindow.end - timeWindow.start;
  const atFullView = timeWindow.start <= 1e-6 && timeWindow.end >= waveformDuration - 1e-6;
  const canPanLeft = !medianMode && !loading && timeWindow.start > 1e-6;
  const canPanRight = !medianMode && !loading && timeWindow.end < waveformDuration - 1e-6;
  const panStep = Math.max(0.1, visibleSpan * 0.25);
  const hasLabelledRois = groundedRois.length + userRois.length > 0;
  const activeToolLabel = activeTool === "point"
    ? "Mark point"
    : activeTool === "region"
      ? "Select region"
      : activeTool === "caliper"
        ? "Measure"
        : activeTool === "march"
          ? "Place markers"
          : activeTool === "annotate"
            ? "Annotate"
            : "Inspect";
  const toolHint = medianMode
    ? "Compare averaged morphology across all 12 leads."
    : task?.prompt
      ?? (activeTool === "annotate"
        ? "Drag on one lead to add a temporary note."
        : activeTool === "point"
          ? `Click ${gradePrompt ?? "the requested feature"} on the tracing.`
          : "Inspect the tracing. Use the view controls to examine morphology.");
  const keyboardPlacement = placementsForLead(keyboardLead, timeWindow, rhythmStripMode ? rhythmStripLeads : undefined)[0] ?? null;
  const keyboardLeadOptions = rhythmStripMode
    ? rhythmStripLeads.filter((lead) => !task?.allowedLeads?.length || task.allowedLeads.includes(lead))
    : task?.allowedLeads?.length
      ? task.allowedLeads
      : waveform?.leads.map((lead) => lead.lead) ?? ["II"];

  return (
    <section className="panel ecg-viewer" aria-label={rhythmStripMode ? "Interactive ECG rhythm strips" : "Interactive 12-lead ECG viewer"} aria-busy={loading}>
      {effectiveToolbar === "none" ? null : (
      <div className="viewer-toolbar" data-preset={effectiveToolbar}>
        <div className="viewer-toolbar-main">
          <strong>
            {medianMode ? <HeartPulse size={16} aria-hidden="true" /> : <Crosshair size={16} aria-hidden="true" />}
            {medianMode ? "Median beat" : rhythmStripMode ? "Rhythm strips" : effectiveToolbar === "clinical" ? "12-lead ECG" : "Interactive 12-lead ECG"}
          </strong>
          <div className="viewer-tool-hint">{toolHint}</div>
          {!medianMode ? <div className="viewer-window-label">Window {timeWindow.start.toFixed(1)}–{timeWindow.end.toFixed(1)} s</div> : null}
          {!medianMode && highlightedLeads.length ? (
            <span className="pill">{highlightedLeads.join(", ")} highlighted</span>
          ) : null}
        </div>
        <div className="viewer-command-groups" role="toolbar" aria-label="ECG tools">
          <div className="viewer-command-group" role="group" aria-label="Interaction tool">
            {task ? (
              <span className="viewer-tool-indicator" aria-label={`Active tool: ${activeToolLabel}`}>
                {activeTool === "point" ? <Target size={17} aria-hidden="true" /> : activeTool === "caliper" ? <Ruler size={17} aria-hidden="true" /> : activeTool === "annotate" ? <PencilLine size={17} aria-hidden="true" /> : <Crosshair size={17} aria-hidden="true" />}
                <span>{activeToolLabel}</span>
              </span>
            ) : (
              <button
                className={`icon-button viewer-tool-button${activeTool === "inspect" ? " active" : ""}`}
                type="button"
                onClick={() => setSelectedTool("inspect")}
                aria-pressed={activeTool === "inspect"}
                aria-label="Inspect ECG"
              >
                <MousePointer2 size={17} aria-hidden="true" /><span>Inspect</span>
              </button>
            )}
            {!task && reviewMode ? (
              <button
                className={`icon-button viewer-tool-button${activeTool === "annotate" ? " active" : ""}`}
                type="button"
                onClick={() => setSelectedTool("annotate")}
                aria-pressed={activeTool === "annotate"}
                aria-label="Annotate ECG"
              >
                <PencilLine size={17} aria-hidden="true" /><span>Annotate</span>
              </button>
            ) : null}
            {!task && !reviewMode && gradeConcept ? (
              <button
                className={`icon-button viewer-tool-button${activeTool === "point" ? " active" : ""}`}
                type="button"
                onClick={() => { setSelectedTool("point"); setClickFeedback(null); }}
                aria-pressed={activeTool === "point"}
                aria-label="Identify a feature on the ECG"
              >
                <Target size={17} aria-hidden="true" /><span>Mark point</span>
              </button>
            ) : null}
          </div>

          {!task && userRois.length ? (
            <div className="viewer-command-group" role="group" aria-label="Learner annotations">
              <button className="icon-button viewer-tool-button" type="button" onClick={() => setUserRois((current) => current.slice(0, -1))} aria-label="Undo last ECG annotation">
                <Undo2 size={17} aria-hidden="true" /><span>Undo</span>
              </button>
              <button className="icon-button viewer-tool-button danger" type="button" onClick={() => setUserRois([])} aria-label="Clear ECG annotations">
                <Trash2 size={17} aria-hidden="true" /><span>Clear</span>
              </button>
            </div>
          ) : null}

          {hasLabelledRois && !medianMode ? (
            <div className="viewer-command-group" role="group" aria-label="Annotation display">
              <button
                className={`icon-button viewer-tool-button${showAllLabels ? " active" : ""}`}
                type="button"
                onClick={() => setShowAllLabels((current) => !current)}
                aria-pressed={showAllLabels}
                aria-label={showAllLabels ? "Hide ECG annotation labels" : "Show ECG annotation labels"}
              >
                {showAllLabels ? <EyeOff size={17} aria-hidden="true" /> : <Eye size={17} aria-hidden="true" />}
                <span>{showAllLabels ? "Hide labels" : "Labels"}</span>
              </button>
            </div>
          ) : null}

          <div className="viewer-command-group" role="group" aria-label="ECG view controls">
            {medianAvailable && !task ? (
              <button
                className={`icon-button viewer-tool-button${medianMode ? " active" : ""}`}
                type="button"
                onClick={() => { setMedianMode((current) => !current); setClickFeedback(null); }}
                aria-pressed={medianMode}
                aria-label={medianMode ? "Hide median beat" : "Show median beat"}
              >
                <HeartPulse size={17} aria-hidden="true" /><span>{medianMode ? "12-lead" : "Median"}</span>
              </button>
            ) : null}
            <button
              className="icon-button viewer-tool-button"
              type="button"
              onClick={() => zoom(1.8)}
              disabled={medianMode || loading || atFullView}
              aria-label="Zoom out"
            >
              <ZoomOut size={17} aria-hidden="true" /><span>Zoom out</span>
            </button>
            <button className="icon-button viewer-tool-button" type="button" onClick={() => zoom(0.55)} disabled={medianMode || loading || visibleSpan <= 0.8001} aria-label="Zoom in">
              <ZoomIn size={17} aria-hidden="true" /><span>Zoom in</span>
            </button>
            <button className="icon-button viewer-tool-button" type="button" onClick={resetView} disabled={medianMode || loading || atFullView} aria-label="Reset ECG view">
              <RefreshCw size={17} aria-hidden="true" /><span>Fit</span>
            </button>
            <button className="icon-button viewer-tool-button compact" type="button" onClick={() => pan(-panStep)} disabled={!canPanLeft} aria-label="Pan ECG left">
              <ChevronLeft size={17} aria-hidden="true" /><span>Left</span>
            </button>
            <button className="icon-button viewer-tool-button compact" type="button" onClick={() => pan(panStep)} disabled={!canPanRight} aria-label="Pan ECG right">
              <ChevronRight size={17} aria-hidden="true" /><span>Right</span>
            </button>
          </div>
        </div>
      </div>
      )}
      {error ? (
        <div className="warning viewer-load-error" role="alert">
          <span>{error}</span>
          <button className="button subtle small" type="button" onClick={() => setLoadVersion((value) => value + 1)}>
            Retry ECG
          </button>
        </div>
      ) : null}
      {identifyMode || task ? (
        <div className="identify-banner">
          {activeTool === "caliper" ? <Ruler size={15} aria-hidden="true" /> : <Target size={15} aria-hidden="true" />}
          <span>
            {task?.prompt ?? `Identify feature mode: click ${gradePrompt ?? "the target feature"} on the trace.`}
            {task?.mode === "region" || task?.mode === "caliper" ? " Drag from the first boundary to the second within one lead panel." : ""}
            {task?.mode === "march" ? ` Place at least ${task.minimumMarkers} markers; select Clear task marks to restart.` : ""}
            {grading ? " Grading..." : ""}
          </span>
          {task?.mode === "march" || task?.mode === "region" || task?.mode === "caliper" ? (
            <button
              className="button subtle small"
              type="button"
              onClick={clearTaskMarks}
            >
              Clear task marks
            </button>
          ) : null}
        </div>
      ) : null}
      <div
        ref={stageRef}
        className={`viewer-stage tool-${activeTool}${!medianMode && identifyMode ? " identify" : ""}`}
        role="region"
        aria-label="Scrollable ECG tracing"
        tabIndex={0}
      >
        {!waveform ? (
          <div className="viewer-loading" role="status" aria-live="polite">
            {error ? "ECG unavailable." : "Loading ECG…"}
          </div>
        ) : medianMode && medianBeats ? (
          <svg
            viewBox={`0 0 ${WIDTH} ${MEDIAN_HEIGHT}`}
            role="img"
            aria-label="12-lead median beat"
            style={{ aspectRatio: `${WIDTH} / ${MEDIAN_HEIGHT}`, minHeight: 0 }}
          >
            <MedianPanelDefs prefix={clipPrefix} />
            <MedianPaperGrid />
            {leadLayout.map((row, rowIndex) =>
              row.map((lead, columnIndex) => (
                <MedianBeatPanel
                  key={lead}
                  lead={lead}
                  row={rowIndex}
                  column={columnIndex}
                  beat={medianBeats.beats[lead] ?? []}
                  durationMs={medianBeats.durationMs}
                  clipPrefix={clipPrefix}
                />
              )),
            )}
            <CalibrationMark
              height={MEDIAN_HEIGHT}
              pxPerSec={PAPER_SPEED_MM_PER_SEC * DEFAULT_PX_PER_MM}
              pxPerMv={GAIN_MM_PER_MV * DEFAULT_PX_PER_MM}
              clipId={`${clipPrefix}-median-clip-2-0`}
            />
          </svg>
        ) : (
          <svg
            ref={svgRef}
            viewBox={`0 0 ${WIDTH} ${presentationHeight}`}
            role="img"
            aria-label={rhythmStripMode
              ? `Interactive rhythm strips for ${rhythmStripLeads.join(", ")}`
              : "Interactive standard 12-lead ECG with lead II rhythm strip"}
            onPointerDown={onPointerDown}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerCancel}
            style={{
              aspectRatio: `${WIDTH} / ${presentationHeight}`,
              minHeight: 0,
              touchAction: ["region", "caliper", "annotate"].includes(activeTool) ? "none" : "pan-x pan-y",
            }}
          >
            <PanelDefs prefix={clipPrefix} stripLeads={rhythmStripMode ? rhythmStripLeads : undefined} />
            <PaperGrid timeWindow={timeWindow} height={presentationHeight} rows={rhythmStripMode ? rhythmStripLeads.length : ROWS} />
            {rhythmStripMode ? rhythmStripLeads.map((lead, row) => (
              <RhythmLeadStripPanel
                key={lead}
                lead={lead}
                row={row}
                points={signalByLead.get(lead) ?? []}
                timeWindow={timeWindow}
                highlighted={highlightedLeads.includes(lead)}
                clipPrefix={clipPrefix}
              />
            )) : (
              <>
                {leadLayout.map((row) =>
                  row.map((lead) => (
                    <LeadPanel
                      key={lead}
                      lead={lead}
                      points={signalByLead.get(lead) ?? []}
                      timeWindow={timeWindow}
                      highlighted={highlightedLeads.includes(lead)}
                      clipPrefix={clipPrefix}
                    />
                  )),
                )}
                <RhythmStripPanel
                  lead="II"
                  points={signalByLead.get("II") ?? []}
                  timeWindow={timeWindow}
                  highlighted={highlightedLeads.includes("II")}
                  clipPrefix={clipPrefix}
                />
              </>
            )}
            {[...groundedRois, ...userRois].map((roi, index) => {
              const key = `${roi.lead}-${roi.label}-${index}`;
              return (
                <RoiOverlay
                  key={key}
                  roi={roi}
                  timeWindow={timeWindow}
                  user={roi.source === "user"}
                  showLabel={showAllLabels || hoveredRoiKey === key}
                  clipPrefix={clipPrefix}
                  displayLeads={rhythmStripMode ? rhythmStripLeads : undefined}
                  onHoverChange={(hovered) => setHoveredRoiKey((current) => (hovered ? key : current === key ? null : current))}
                />
              );
            })}
            {overlays.map((action, index) => (
              <ActionOverlay key={`${action.type}-${action.lead}-${index}`} action={action} timeWindow={timeWindow} clipPrefix={clipPrefix} displayLeads={rhythmStripMode ? rhythmStripLeads : undefined} />
            ))}
            {clickFeedback ? <ClickMarker feedback={clickFeedback} timeWindow={timeWindow} clipPrefix={clipPrefix} displayLeads={rhythmStripMode ? rhythmStripLeads : undefined} /> : null}
            {task?.mode === "march" ? marchPoints.map((point, index) => (
              <TaskMarker key={`${point.lead}-${point.timeSec}-${index}`} point={point} label={`${index + 1}`} timeWindow={timeWindow} clipPrefix={clipPrefix} displayLeads={rhythmStripMode ? rhythmStripLeads : undefined} />
            )) : null}
            <CalibrationMark
              height={presentationHeight}
              pxPerSec={printScale.pxPerSec}
              pxPerMv={printScale.pxPerMv}
              clipId={`${clipPrefix}-${rhythmStripMode ? `strip-clip-${rhythmStripLeads.length - 1}` : "rhythm-clip"}`}
            />
          </svg>
        )}
      </div>
      {task ? (
        <details className="viewer-keyboard-task">
          <summary>Keyboard / precise-entry alternative</summary>
          <p>
            Select a lead, then move the time cursor with the arrow keys. Its sampled voltage is announced below.
            {task.mode === "region" || task.mode === "caliper" ? " Enter both boundaries to select the same interval without dragging." : " Submit the cursor to place the same point without clicking the trace."}
          </p>
          <div className="viewer-keyboard-fields">
            <label>
              <span>Lead</span>
              <select aria-label="Keyboard task lead" value={keyboardLead} onChange={(event) => setKeyboardLead(event.target.value)}>
                {(keyboardLeadOptions.length ? keyboardLeadOptions : rhythmStripLeads.length ? rhythmStripLeads : ["II"]).map((lead) => <option key={lead} value={lead}>{lead}</option>)}
              </select>
            </label>
            <label>
              <span>{task.mode === "region" || task.mode === "caliper" ? "First boundary (seconds)" : "Time cursor (seconds)"}</span>
              <input type="number" min={keyboardPlacement?.timeStart ?? timeWindow.start} max={keyboardPlacement?.timeEnd ?? timeWindow.end} step={1 / (waveform?.samplingFrequency ?? 100)} value={keyboardStart} onChange={(event) => setKeyboardStart(event.target.value)} />
            </label>
            {task.mode === "region" || task.mode === "caliper" ? (
              <label>
                <span>Second boundary (seconds)</span>
                <input type="number" min={keyboardPlacement?.timeStart ?? timeWindow.start} max={keyboardPlacement?.timeEnd ?? timeWindow.end} step={1 / (waveform?.samplingFrequency ?? 100)} value={keyboardEnd} onChange={(event) => setKeyboardEnd(event.target.value)} />
              </label>
            ) : null}
            <output aria-live="polite">
              {(() => {
                const point = waveformPointAt(keyboardLead, Number(keyboardStart));
                return point ? `${point.lead}, ${point.timeSec.toFixed(3)} seconds, ${point.amplitudeMv.toFixed(3)} millivolts` : "No sampled point selected";
              })()}
            </output>
            <button className="button" type="button" onClick={() => void submitKeyboardTask()} disabled={grading || !waveform}>
              {task.mode === "march" ? "Add validated marker" : task.mode === "region" ? "Grade selected region" : task.mode === "caliper" ? "Use these caliper boundaries" : "Grade selected point"}
            </button>
          </div>
        </details>
      ) : null}
      {effectiveToolbar !== "full" ? null : (
        <details className="viewer-help">
          <summary>{medianMode ? "About the median beat" : "ECG paper and controls"}</summary>
          <p>
            {medianMode
              ? "Median beat: one averaged complex per lead on the same square calibrated paper (small box 0.04 s × 0.1 mV, large box 0.2 s × 0.5 mV). Use it to compare morphology without beat-to-beat noise."
              : "Standard print: sequential 2.5-second lead columns plus a continuous lead-II rhythm strip at 25 mm/s and 10 mm/mV. Grid boxes stay square through zoom. Select an interaction tool before adding a mark."}
          </p>
        </details>
      )}
      {clickFeedback ? (
        <div className={`click-feedback ${clickFeedback.noTarget ? "neutral" : clickFeedback.correct ? "ok" : "miss"}`} role="status" aria-live="polite">
          <strong>{clickFeedback.noTarget ? "No target here" : clickFeedback.correct ? "Correct" : "Not yet"}</strong>
          <span>{clickFeedback.noTarget ? clickFeedback.feedback || "This case has no grounded target for that feature — nothing to identify here." : clickFeedback.feedback}</span>
          {clickFeedback.matchedRoi ? (
            <span className="muted">Matched ROI: {clickFeedback.matchedRoi.label} ({clickFeedback.matchedRoi.lead})</span>
          ) : null}
        </div>
      ) : null}
      {taskFeedback ? <div className="click-feedback neutral" role="status" aria-live="polite"><strong>Task evidence</strong><span>{taskFeedback}</span></div> : null}
      {selectedPoint && (effectiveToolbar !== "clinical" || Boolean(task)) ? <div className="coordinate-readout">
        <span className="coord-chip"><Crosshair size={14} aria-hidden="true" /> {selectedPoint.lead}</span>
        <span>{selectedPoint.timeSec.toFixed((waveform?.samplingFrequency ?? 100) >= 500 ? 3 : 2)} sec</span>
        <span>{selectedPoint.amplitudeMv.toFixed(3)} mV</span>
        <span className="muted">source resolution ≈ {Math.round(1000 / (waveform?.samplingFrequency ?? 100))} ms</span>
      </div> : null}
    </section>
  );
}

type TimeWindow = { start: number; end: number };

/**
 * A sequential 3×4 print gives each lead only its column-owned quarter of the
 * selected time window. Center an AI zoom target inside the named lead's column
 * instead of the whole page; otherwise the tutor can truthfully select an ROI
 * yet make it invisible (for example a lead-I ROI centered in column 3 time).
 */
export function fitActionWindowToLead(start: number, end: number, lead: string | undefined, duration: number): TimeWindow {
  const rawSpan = Math.max(0.8, Math.min(duration, end - start));
  const target = (start + end) / 2;
  let column = -1;
  if (lead) {
    for (const row of leadLayout) {
      const index = row.indexOf(lead as never);
      if (index >= 0) {
        column = index;
        break;
      }
    }
  }
  const targetFraction = column >= 0 ? (column + 0.5) / COLS : 0.5;
  let nextStart = target - rawSpan * targetFraction;
  nextStart = Math.max(0, Math.min(Math.max(0, duration - rawSpan), nextStart));
  return { start: nextStart, end: nextStart + rawSpan };
}

type PaperScale = {
  spanSec: number;
  segmentSec: number;
  pxPerSec: number;
  pxPerMm: number;
  pxPerMv: number;
};

type LeadPlacement = {
  key: string;
  lead: string;
  row: number;
  column: number;
  x0: number;
  y0: number;
  width: number;
  height: number;
  timeStart: number;
  timeEnd: number;
  clipId: string;
};

function paperScale(timeWindow: TimeWindow): PaperScale {
  const spanSec = Math.max(timeWindow.end - timeWindow.start, 0.0001);
  const pxPerSec = WIDTH / spanSec;
  const pxPerMm = pxPerSec / PAPER_SPEED_MM_PER_SEC;
  return {
    spanSec,
    segmentSec: spanSec / COLS,
    pxPerSec,
    pxPerMm,
    pxPerMv: GAIN_MM_PER_MV * pxPerMm,
  };
}

function mainLeadPlacement(lead: string, timeWindow: TimeWindow): LeadPlacement | null {
  const scale = paperScale(timeWindow);
  for (let row = 0; row < leadLayout.length; row += 1) {
    const column = leadLayout[row].indexOf(lead as never);
    if (column < 0) continue;
    return {
      key: `lead-${row}-${column}`,
      lead,
      row,
      column,
      x0: column * CELL_W,
      y0: row * CELL_H,
      width: CELL_W,
      height: CELL_H,
      timeStart: timeWindow.start + column * scale.segmentSec,
      timeEnd: timeWindow.start + (column + 1) * scale.segmentSec,
      clipId: `lead-clip-${row}-${column}`,
    };
  }
  return null;
}

function rhythmPlacement(timeWindow: TimeWindow): LeadPlacement {
  return {
    key: "rhythm-II",
    lead: "II",
    row: ROWS - 1,
    column: 0,
    x0: 0,
    y0: (ROWS - 1) * CELL_H,
    width: WIDTH,
    height: CELL_H,
    timeStart: timeWindow.start,
    timeEnd: timeWindow.end,
    clipId: "rhythm-clip",
  };
}

function rhythmLeadPlacement(lead: string, row: number, timeWindow: TimeWindow): LeadPlacement {
  return {
    key: `strip-${row}`,
    lead,
    row,
    column: 0,
    x0: 0,
    y0: row * CELL_H,
    width: WIDTH,
    height: CELL_H,
    timeStart: timeWindow.start,
    timeEnd: timeWindow.end,
    clipId: `strip-clip-${row}`,
  };
}

function placementsForLead(lead: string, timeWindow: TimeWindow, stripLeads?: readonly string[]): LeadPlacement[] {
  if (stripLeads?.length) {
    const row = stripLeads.indexOf(lead);
    return row >= 0 ? [rhythmLeadPlacement(lead, row, timeWindow)] : [];
  }
  const main = mainLeadPlacement(lead, timeWindow);
  return [...(main ? [main] : []), ...(lead === "II" ? [rhythmPlacement(timeWindow)] : [])];
}

function placementContainsTime(placement: LeadPlacement, timeSec: number): boolean {
  return timeSec >= placement.timeStart - 1e-9 && timeSec <= placement.timeEnd + 1e-9;
}

function PanelDefs({ prefix, stripLeads = [] }: { prefix: string; stripLeads?: readonly string[] }) {
  return (
    <defs>
      {leadLayout.map((row, rowIndex) =>
        row.map((lead, columnIndex) => (
          <clipPath id={`${prefix}-lead-clip-${rowIndex}-${columnIndex}`} key={`clip-${lead}`}>
            <rect x={columnIndex * CELL_W + 2} y={rowIndex * CELL_H + 2} width={CELL_W - 4} height={CELL_H - 4} />
          </clipPath>
        )),
      )}
      <clipPath id={`${prefix}-rhythm-clip`}>
        <rect x={2} y={(ROWS - 1) * CELL_H + 2} width={WIDTH - 4} height={CELL_H - 4} />
      </clipPath>
      {stripLeads.map((lead, row) => (
        <clipPath id={`${prefix}-strip-clip-${row}`} key={`strip-clip-${lead}-${row}`}>
          <rect x={2} y={row * CELL_H + 2} width={WIDTH - 4} height={CELL_H - 4} />
        </clipPath>
      ))}
    </defs>
  );
}

function MedianPanelDefs({ prefix }: { prefix: string }) {
  return (
    <defs>
      {leadLayout.map((row, rowIndex) =>
        row.map((lead, columnIndex) => (
          <clipPath id={`${prefix}-median-clip-${rowIndex}-${columnIndex}`} key={`median-clip-${lead}`}>
            <rect x={columnIndex * CELL_W + 2} y={rowIndex * CELL_H + 2} width={CELL_W - 4} height={CELL_H - 4} />
          </clipPath>
        )),
      )}
    </defs>
  );
}

function PaperGrid({ timeWindow, height = HEIGHT, rows = ROWS }: { timeWindow: TimeWindow; height?: number; rows?: number }) {
  const scale = paperScale(timeWindow);
  const minorLines: ReactElement[] = [];
  const majorLines: ReactElement[] = [];

  // Vertical paper lines stay anchored to absolute acquisition time through pan/zoom.
  const firstMinorTime = Math.ceil(timeWindow.start / SMALL_BOX_SEC) * SMALL_BOX_SEC;
  for (let t = firstMinorTime; t <= timeWindow.end + 1e-9; t += SMALL_BOX_SEC) {
    const x = (t - timeWindow.start) * scale.pxPerSec;
    const isMajor = Math.abs(t / LARGE_BOX_SEC - Math.round(t / LARGE_BOX_SEC)) < 1e-6;
    const line = <line key={`v-${t.toFixed(3)}`} x1={x} x2={x} y1={0} y2={height} stroke={isMajor ? "#e6a3a3" : "#f6dcdc"} strokeWidth={isMajor ? 1.1 : 0.6} />;
    (isMajor ? majorLines : minorLines).push(line);
  }

  // Horizontal lines repeat around each lead's 0 mV baseline. Because both axes use
  // the same px/mm, the boxes remain square at every digital zoom level.
  for (let rowIndex = 0; rowIndex < rows; rowIndex += 1) {
    const mid = rowIndex * CELL_H + CELL_H / 2;
    const boxes = Math.ceil(CELL_H / (2 * scale.pxPerMm));
    for (let box = -boxes; box <= boxes; box += 1) {
      const y = mid + box * scale.pxPerMm;
      if (y < rowIndex * CELL_H - 1e-9 || y > (rowIndex + 1) * CELL_H + 1e-9) continue;
      const isMajor = box % 5 === 0;
      const line = (
        <line key={`h-${rowIndex}-${box}`} x1={0} x2={WIDTH} y1={y} y2={y} stroke={isMajor ? "#e6a3a3" : "#f6dcdc"} strokeWidth={isMajor ? 1.1 : 0.6} />
      );
      (isMajor ? majorLines : minorLines).push(line);
    }
  }

  return (
    <g>
      <rect x={0} y={0} width={WIDTH} height={height} fill="#fffafa" />
      {minorLines}
      {majorLines}
    </g>
  );
}

function CalibrationMark({ height, pxPerSec, pxPerMv, clipId }: { height: number; pxPerSec: number; pxPerMv: number; clipId: string }) {
  // Standard calibration pulse: one large box (0.2 s / 5 mm) wide and 1 mV
  // (10 mm) tall. Both dimensions come from the same paper transform.
  const baseX = 16;
  const baseY = height - 16;
  const pulseH = 1.0 * pxPerMv;
  const pulseW = LARGE_BOX_SEC * pxPerSec;
  const leadIn = SMALL_BOX_SEC * pxPerSec;
  const d = `M${baseX},${baseY} L${baseX + leadIn},${baseY} L${baseX + leadIn},${baseY - pulseH} L${baseX + leadIn + pulseW},${baseY - pulseH} L${baseX + leadIn + pulseW},${baseY} L${baseX + leadIn * 2 + pulseW},${baseY}`;
  return (
    <g aria-hidden="true" clipPath={`url(#${clipId})`}>
      <path d={d} fill="none" stroke="#9aa3a0" strokeWidth={2} />
      <text x={baseX + pulseW + leadIn * 2 + 8} y={baseY - 5} fontSize={13} fontWeight={700} fill="#5f6b67" style={{ paintOrder: "stroke" }} stroke="#fffafa" strokeWidth={3}>
        {PAPER_SPEED_MM_PER_SEC} mm/s · {GAIN_MM_PER_MV} mm/mV
      </text>
    </g>
  );
}

/**
 * Calibrated grid for the median-beat view. Each lead cell spans `durationMs`
 * across its width, so the same 0.04 s small box / 0.2 s large box spacing holds.
 * Time origin is local to each cell (the median beat has no absolute time).
 */
function MedianPaperGrid() {
  const minorLines: ReactElement[] = [];
  const majorLines: ReactElement[] = [];

  for (let col = 0; col < COLS; col += 1) {
    for (let box = 0; box * DEFAULT_PX_PER_MM <= CELL_W + 1e-9; box += 1) {
      const x = col * CELL_W + box * DEFAULT_PX_PER_MM;
      const isMajor = box % 5 === 0;
      const line = (
        <line key={`mv-${col}-${box}`} x1={x} x2={x} y1={0} y2={MEDIAN_HEIGHT} stroke={isMajor ? "#e6a3a3" : "#f6dcdc"} strokeWidth={isMajor ? 1.1 : 0.6} />
      );
      (isMajor ? majorLines : minorLines).push(line);
    }
  }

  for (let rowIndex = 0; rowIndex < LEAD_ROWS; rowIndex += 1) {
    const mid = rowIndex * CELL_H + CELL_H / 2;
    const boxes = Math.ceil(CELL_H / (2 * DEFAULT_PX_PER_MM));
    for (let box = -boxes; box <= boxes; box += 1) {
      const y = mid + box * DEFAULT_PX_PER_MM;
      if (y < rowIndex * CELL_H - 1e-9 || y > (rowIndex + 1) * CELL_H + 1e-9) continue;
      const isMajor = box % 5 === 0;
      const line = (
        <line key={`mh-${rowIndex}-${box}`} x1={0} x2={WIDTH} y1={y} y2={y} stroke={isMajor ? "#e6a3a3" : "#f6dcdc"} strokeWidth={isMajor ? 1.1 : 0.6} />
      );
      (isMajor ? majorLines : minorLines).push(line);
    }
  }

  return (
    <g>
      <rect x={0} y={0} width={WIDTH} height={MEDIAN_HEIGHT} fill="#fffafa" />
      {minorLines}
      {majorLines}
    </g>
  );
}

/** One averaged median complex for a lead, plotted across its cell with the standard amplitude scale. */
function MedianBeatPanel({
  lead,
  row,
  column,
  beat,
  durationMs,
  clipPrefix,
}: {
  lead: string;
  row: number;
  column: number;
  beat: number[];
  durationMs: number;
  clipPrefix: string;
}) {
  const x0 = column * CELL_W;
  const y0 = row * CELL_H;
  const mid = y0 + CELL_H / 2;
  const pxPerSec = PAPER_SPEED_MM_PER_SEC * DEFAULT_PX_PER_MM;
  const pxPerMv = GAIN_MM_PER_MV * DEFAULT_PX_PER_MM;
  const traceWidth = Math.min(CELL_W - 24, Math.max(0, (durationMs / 1000) * pxPerSec));
  const traceX = x0 + (CELL_W - traceWidth) / 2;
  const count = beat.length;
  const path =
    count > 1
      ? beat
          .map((amplitudeMv, index) => {
            const x = traceX + (index / (count - 1)) * traceWidth;
            const y = mid - amplitudeMv * pxPerMv;
            return `${index === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
          })
          .join(" ")
      : "";
  return (
    <g>
      <rect x={x0 + 2} y={y0 + 2} width={CELL_W - 4} height={CELL_H - 4} fill="transparent" stroke="#d7ddda" strokeWidth={1} />
      <text x={x0 + 12} y={y0 + 24} fontSize={18} fontWeight={800} fill="#17201d">
        {lead}
      </text>
      {path ? (
        <path d={path} fill="none" stroke="#c43c36" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" clipPath={`url(#${clipPrefix}-median-clip-${row}-${column})`} />
      ) : (
        <text x={x0 + 12} y={mid} fontSize={13} fill="#9aa3a0">
          No median beat
        </text>
      )}
    </g>
  );
}

function LeadPanel({
  lead,
  points,
  timeWindow,
  highlighted,
  clipPrefix,
}: {
  lead: string;
  points: Array<{ timeSec: number; amplitudeMv: number }>;
  timeWindow: TimeWindow;
  highlighted: boolean;
  clipPrefix: string;
}) {
  const placement = mainLeadPlacement(lead, timeWindow);
  if (!placement) return null;
  const scale = paperScale(timeWindow);
  const mid = placement.y0 + placement.height / 2;
  const path = points
    .filter((point) => placementContainsTime(placement, point.timeSec))
    .map((point, index) => {
      const x = (point.timeSec - timeWindow.start) * scale.pxPerSec;
      const y = mid - point.amplitudeMv * scale.pxPerMv;
      return `${index === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  return (
    <g>
      <rect x={placement.x0 + 2} y={placement.y0 + 2} width={placement.width - 4} height={placement.height - 4} fill={highlighted ? "rgba(14,124,102,0.09)" : "transparent"} stroke={highlighted ? "#0e7c66" : "#d7ddda"} strokeWidth={highlighted ? 2 : 1} />
      <text x={placement.x0 + 12} y={placement.y0 + 24} fontSize={18} fontWeight={800} fill="#17201d" style={{ paintOrder: "stroke" }} stroke="#fffafa" strokeWidth={3}>
        {lead}
      </text>
      <path d={path} fill="none" stroke="#c43c36" strokeWidth={1.8} strokeLinejoin="round" strokeLinecap="round" clipPath={`url(#${clipPrefix}-${placement.clipId})`} />
    </g>
  );
}

function RhythmStripPanel({
  lead,
  points,
  timeWindow,
  highlighted,
  clipPrefix,
}: {
  lead: "II";
  points: Array<{ timeSec: number; amplitudeMv: number }>;
  timeWindow: TimeWindow;
  highlighted: boolean;
  clipPrefix: string;
}) {
  const placement = rhythmPlacement(timeWindow);
  const scale = paperScale(timeWindow);
  const mid = placement.y0 + placement.height / 2;
  const path = points
    .filter((point) => placementContainsTime(placement, point.timeSec))
    .map((point, index) => {
      const x = (point.timeSec - timeWindow.start) * scale.pxPerSec;
      const y = mid - point.amplitudeMv * scale.pxPerMv;
      return `${index === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  return (
    <g>
      <rect x={2} y={placement.y0 + 2} width={WIDTH - 4} height={CELL_H - 4} fill={highlighted ? "rgba(14,124,102,0.09)" : "transparent"} stroke={highlighted ? "#0e7c66" : "#d7ddda"} strokeWidth={highlighted ? 2 : 1} />
      <text x={12} y={placement.y0 + 24} fontSize={18} fontWeight={800} fill="#17201d" style={{ paintOrder: "stroke" }} stroke="#fffafa" strokeWidth={3}>
        {lead} · rhythm strip
      </text>
      <path d={path} fill="none" stroke="#c43c36" strokeWidth={1.8} strokeLinejoin="round" strokeLinecap="round" clipPath={`url(#${clipPrefix}-${placement.clipId})`} />
    </g>
  );
}

function RhythmLeadStripPanel({
  lead,
  row,
  points,
  timeWindow,
  highlighted,
  clipPrefix,
}: {
  lead: string;
  row: number;
  points: Array<{ timeSec: number; amplitudeMv: number }>;
  timeWindow: TimeWindow;
  highlighted: boolean;
  clipPrefix: string;
}) {
  const placement = rhythmLeadPlacement(lead, row, timeWindow);
  const scale = paperScale(timeWindow);
  const mid = placement.y0 + placement.height / 2;
  const path = points
    .filter((point) => placementContainsTime(placement, point.timeSec))
    .map((point, index) => {
      const x = (point.timeSec - timeWindow.start) * scale.pxPerSec;
      const y = mid - point.amplitudeMv * scale.pxPerMv;
      return `${index === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  return (
    <g>
      <rect x={2} y={placement.y0 + 2} width={WIDTH - 4} height={CELL_H - 4} fill={highlighted ? "rgba(14,124,102,0.09)" : "transparent"} stroke={highlighted ? "#0e7c66" : "#d7ddda"} strokeWidth={highlighted ? 2 : 1} />
      <text x={12} y={placement.y0 + 24} fontSize={18} fontWeight={800} fill="#17201d" style={{ paintOrder: "stroke" }} stroke="#fffafa" strokeWidth={3}>
        {lead} · rhythm strip
      </text>
      {path ? (
        <path d={path} fill="none" stroke="#c43c36" strokeWidth={1.8} strokeLinejoin="round" strokeLinecap="round" clipPath={`url(#${clipPrefix}-${placement.clipId})`} />
      ) : (
        <text x={12} y={mid + 6} fontSize={14} fill="#7a8581">Lead unavailable in this waveform</text>
      )}
    </g>
  );
}

function ClickMarker({ feedback, timeWindow, clipPrefix, displayLeads }: { feedback: ClickFeedback; timeWindow: TimeWindow; clipPrefix: string; displayLeads?: readonly string[] }) {
  const scale = paperScale(timeWindow);
  const color = feedback.correct ? "#0e7c66" : "#c43c36";
  return (
    <>
      {placementsForLead(feedback.point.lead, timeWindow, displayLeads)
        .filter((placement) => placementContainsTime(placement, feedback.point.timeSec))
        .map((placement) => {
          const x = (feedback.point.timeSec - timeWindow.start) * scale.pxPerSec;
          const y = placement.y0 + placement.height / 2 - feedback.point.amplitudeMv * scale.pxPerMv;
          return (
            <g key={`marker-${placement.key}`} aria-hidden="true" clipPath={`url(#${clipPrefix}-${placement.clipId})`}>
              <circle cx={x} cy={y} r={11} fill="none" stroke={color} strokeWidth={2.5} />
              <line x1={x - 16} x2={x + 16} y1={y} y2={y} stroke={color} strokeWidth={1.5} />
              <line x1={x} x2={x} y1={y - 16} y2={y + 16} stroke={color} strokeWidth={1.5} />
            </g>
          );
        })}
    </>
  );
}

function TaskMarker({ point, label, timeWindow, clipPrefix, displayLeads }: { point: ECGPoint; label: string; timeWindow: TimeWindow; clipPrefix: string; displayLeads?: readonly string[] }) {
  const scale = paperScale(timeWindow);
  return (
    <>
      {placementsForLead(point.lead, timeWindow, displayLeads)
        .filter((placement) => placementContainsTime(placement, point.timeSec))
        .map((placement) => {
          const x = (point.timeSec - timeWindow.start) * scale.pxPerSec;
          const y = placement.y0 + placement.height / 2 - point.amplitudeMv * scale.pxPerMv;
          return (
            <g key={`task-${placement.key}-${label}`} aria-hidden="true" clipPath={`url(#${clipPrefix}-${placement.clipId})`}>
              <circle cx={x} cy={y} r={13} fill="#315f8a" stroke="#ffffff" strokeWidth={2} />
              <text x={x} y={y + 4.5} textAnchor="middle" fontSize={12} fontWeight={800} fill="#ffffff">{label}</text>
            </g>
          );
        })}
    </>
  );
}

function RoiOverlay({
  roi,
  timeWindow,
  user,
  showLabel = false,
  onHoverChange,
  clipPrefix,
  displayLeads,
}: {
  roi: GroundedRoi;
  timeWindow: TimeWindow;
  user?: boolean;
  /** Whether to render the text label (default hidden; shown on hover / toggle / AI highlight). */
  showLabel?: boolean;
  onHoverChange?: (hovered: boolean) => void;
  clipPrefix: string;
  displayLeads?: readonly string[];
}) {
  const scale = paperScale(timeWindow);
  const placements = placementsForLead(roi.lead, timeWindow, displayLeads).filter(
    (placement) => roi.timeEndSec >= placement.timeStart && roi.timeStartSec <= placement.timeEnd,
  );
  if (!placements.length) return null;
  const labelText = roi.label;
  return (
    <>
      {placements.map((placement) => {
        const rawX1 = (roi.timeStartSec - timeWindow.start) * scale.pxPerSec;
        const rawX2 = (roi.timeEndSec - timeWindow.start) * scale.pxPerSec;
        const x1 = Math.max(placement.x0, rawX1);
        const x2 = Math.min(placement.x0 + placement.width, rawX2);
        const y1 = placement.y0 + placement.height / 2 - roi.ampMaxMv * scale.pxPerMv;
        const y2 = placement.y0 + placement.height / 2 - roi.ampMinMv * scale.pxPerMv;
        return (
          <g
            key={`roi-${placement.key}`}
            clipPath={`url(#${clipPrefix}-${placement.clipId})`}
            onPointerEnter={onHoverChange ? () => onHoverChange(true) : undefined}
            onPointerLeave={onHoverChange ? () => onHoverChange(false) : undefined}
            style={onHoverChange ? { cursor: "help" } : undefined}
          >
            <rect x={x1} y={Math.min(y1, y2)} width={Math.max(5, x2 - x1)} height={Math.max(12, Math.abs(y2 - y1))} fill={user ? "rgba(49,95,138,0.12)" : "rgba(14,124,102,0.16)"} stroke={user ? "#315f8a" : "#0e7c66"} strokeWidth={2} rx={6} />
            {showLabel ? (
              <text x={Math.max(placement.x0 + 8, x1)} y={Math.max(placement.y0 + 18, Math.min(y1, y2) - 5)} fontSize={13} fontWeight={700} fill={user ? "#315f8a" : "#075f4d"} style={{ paintOrder: "stroke" }} stroke="#fffafa" strokeWidth={3}>
                {labelText}
              </text>
            ) : null}
          </g>
        );
      })}
    </>
  );
}

function ActionOverlay({ action, timeWindow, clipPrefix, displayLeads }: { action: ViewerAction; timeWindow: TimeWindow; clipPrefix: string; displayLeads?: readonly string[] }) {
  if (action.type === "highlightROI" && action.lead && action.timeStart !== undefined && action.timeEnd !== undefined && action.ampMin !== undefined && action.ampMax !== undefined) {
    return (
      <RoiOverlay
        roi={{
          lead: action.lead,
          timeStartSec: action.timeStart,
          timeEndSec: action.timeEnd,
          ampMinMv: action.ampMin,
          ampMaxMv: action.ampMax,
          label: action.label ?? "AI highlight",
          concept: "ai_highlight",
          source: "ai_tutor",
          confidence: "medium",
        }}
        timeWindow={timeWindow}
        showLabel
        clipPrefix={clipPrefix}
        displayLeads={displayLeads}
      />
    );
  }
  if (action.type === "drawCaliper" && action.lead && action.timeStart !== undefined && action.timeEnd !== undefined) {
    const scale = paperScale(timeWindow);
    const durationMs = Math.round(Math.abs(action.timeEnd - action.timeStart) * 1000);
    return (
      <>
        {placementsForLead(action.lead, timeWindow, displayLeads)
          .filter((placement) => action.timeEnd! >= placement.timeStart && action.timeStart! <= placement.timeEnd)
          .map((placement) => {
            const x1 = Math.max(placement.x0, (action.timeStart! - timeWindow.start) * scale.pxPerSec);
            const x2 = Math.min(placement.x0 + placement.width, (action.timeEnd! - timeWindow.start) * scale.pxPerSec);
            const y = placement.y0 + placement.height - 28;
            return (
              <g key={`caliper-${placement.key}`} clipPath={`url(#${clipPrefix}-${placement.clipId})`}>
                <line x1={x1} x2={x2} y1={y} y2={y} stroke="#315f8a" strokeWidth={3} />
                <line x1={x1} x2={x1} y1={y - 10} y2={y + 10} stroke="#315f8a" strokeWidth={2} />
                <line x1={x2} x2={x2} y1={y - 10} y2={y + 10} stroke="#315f8a" strokeWidth={2} />
                <text x={(x1 + x2) / 2} y={y - 14} textAnchor="middle" fontSize={13} fontWeight={700} fill="#315f8a" style={{ paintOrder: "stroke" }} stroke="#fffafa" strokeWidth={3}>
                  {action.label ?? `${durationMs} ms`}
                </text>
              </g>
            );
          })}
      </>
    );
  }
  if (action.type === "circleROI" && action.lead && action.timeStart !== undefined && action.timeEnd !== undefined) {
    const scale = paperScale(timeWindow);
    const centerTime = (action.timeStart + action.timeEnd) / 2;
    const centerAmp = action.ampMin !== undefined && action.ampMax !== undefined ? (action.ampMin + action.ampMax) / 2 : 0;
    return (
      <>
        {placementsForLead(action.lead, timeWindow, displayLeads)
          .filter((placement) => placementContainsTime(placement, centerTime))
          .map((placement) => {
            const cx = (centerTime - timeWindow.start) * scale.pxPerSec;
            const cy = placement.y0 + placement.height / 2 - centerAmp * scale.pxPerMv;
            const rx = Math.max(24, Math.abs(action.timeEnd! - action.timeStart!) * scale.pxPerSec / 2);
            return <ellipse key={`circle-${placement.key}`} cx={cx} cy={cy} rx={rx} ry={24} fill="none" stroke="#b76318" strokeWidth={3} clipPath={`url(#${clipPrefix}-${placement.clipId})`} />;
          })}
      </>
    );
  }
  if (action.type === "showFiducial" && action.lead && action.timeSec !== undefined) {
    const scale = paperScale(timeWindow);
    return (
      <>
        {placementsForLead(action.lead, timeWindow, displayLeads)
          .filter((placement) => placementContainsTime(placement, action.timeSec!))
          .map((placement) => {
            const x = (action.timeSec! - timeWindow.start) * scale.pxPerSec;
            return (
              <g key={`fiducial-${placement.key}`} clipPath={`url(#${clipPrefix}-${placement.clipId})`}>
                <line x1={x} x2={x} y1={placement.y0 + 12} y2={placement.y0 + placement.height - 12} stroke="#b76318" strokeDasharray="6 5" strokeWidth={2} />
                <text x={x + 6} y={placement.y0 + 42} fontSize={13} fontWeight={700} fill="#b76318" style={{ paintOrder: "stroke" }} stroke="#fffafa" strokeWidth={3}>
                  {action.label ?? "Fiducial"}
                </text>
              </g>
            );
          })}
      </>
    );
  }
  return null;
}
