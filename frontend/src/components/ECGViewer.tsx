"use client";

import { ChevronLeft, ChevronRight, Crosshair, Eraser, HeartPulse, RefreshCw, Tag, Target, ZoomIn, ZoomOut } from "lucide-react";
import { PointerEvent, type ReactElement, useEffect, useId, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { leadLayout, mapPointToStandardEcgCoordinate, type ECGPoint } from "@/lib/coordinates";
import type { ClickGradeResult, GroundedRoi, MedianBeats, ViewerAction, ViewerTaskEvidence, ViewerTaskSpec, WaveformResponse } from "@/lib/types";

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
  caseId: string;
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
  /** "none" hides the toolbar + help (e.g. the prior viewer in a stacked old/new comparison). */
  toolbar?: "full" | "none";
  /** Optional curriculum task. When present, the viewer becomes the response surface rather than decorative context. */
  task?: ViewerTaskSpec;
  /** Emits the actual waveform evidence collected by the active curriculum task. */
  onTaskEvidence?: (evidence: ViewerTaskEvidence) => void;
};

export function ECGViewer({ caseId, actions = [], groundedRois = [], gradingRois = [], onCoordinate, gradeConcept, gradePrompt, medianBeats = null, onReady, toolbar = "full", task, onTaskEvidence }: ECGViewerProps) {
  const [waveform, setWaveform] = useState<WaveformResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [timeWindow, setTimeWindow] = useState({ start: 0, end: 10 });
  const [highlightedLeads, setHighlightedLeads] = useState<string[]>([]);
  const [overlays, setOverlays] = useState<ViewerAction[]>([]);
  const [selectedPoint, setSelectedPoint] = useState<ECGPoint | null>(null);
  const [dragStart, setDragStart] = useState<ViewerPoint | null>(null);
  const [userRois, setUserRois] = useState<UserRoi[]>([]);
  const [identifyMode, setIdentifyMode] = useState(false);
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
  const clipPrefix = useId().replaceAll(":", "");

  const medianAvailable = Boolean(medianBeats?.available);

  // Reset the one-shot ready signal when the case changes.
  useEffect(() => {
    readyFired.current = false;
  }, [caseId]);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    api
      .waveform(caseId, timeWindow.start, timeWindow.end)
      .then((data) => {
        if (!cancelled) {
          setWaveform(data);
          if (!readyFired.current) {
            readyFired.current = true;
            onReady?.();
          }
        }
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [caseId, timeWindow.start, timeWindow.end]);

  // Reset graded feedback and annotations when the case changes.
  useEffect(() => {
    setClickFeedback(null);
    setIdentifyMode(false);
    setUserRois([]);
    setOverlays([]);
    setHighlightedLeads([]);
    setSelectedPoint(null);
    setHoveredRoiKey(null);
    setMedianMode(false);
    setMarchPoints([]);
    setTaskFeedback(null);
  }, [caseId]);

  useEffect(() => {
    setMarchPoints([]);
    setTaskFeedback(null);
    setIdentifyMode(task?.mode === "point");
    setClickFeedback(null);
    const concept = taskRoiConcept(task);
    const reviewed = gradingRois.find((roi) => roi.concept === concept
      && (!task?.allowedLeads?.length || task.allowedLeads.includes(roi.lead)));
    const lead = reviewed?.lead ?? task?.allowedLeads?.[0] ?? "II";
    const nextWindow = reviewed
      ? fitActionWindowToLead(reviewed.timeStartSec - 0.12, reviewed.timeEndSec + 0.12, lead, waveform?.durationSec ?? 10)
      : { start: 0, end: waveform?.durationSec ?? 10 };
    setTimeWindow(nextWindow);
    setKeyboardLead(lead);
    const placement = mainLeadPlacement(lead, nextWindow) ?? (lead === "II" ? rhythmPlacement(nextWindow) : null);
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
      if (!stage || stage.scrollWidth <= stage.clientWidth) return;
      let column = 0;
      for (const row of leadLayout) {
        const index = row.indexOf(lead as never);
        if (index >= 0) { column = index; break; }
      }
      const columnWidth = stage.scrollWidth / COLS;
      stage.scrollLeft = Math.max(0, column * columnWidth - (stage.clientWidth - columnWidth) / 2);
    }, 0);
  }, [caseId, task?.mode, task?.prompt]);

  // Drop out of median-beat mode if the new case has no median beats.
  useEffect(() => {
    if (!medianAvailable) setMedianMode(false);
  }, [medianAvailable]);

  const signalByLead = useMemo(() => {
    const map = new Map<string, WaveformResponse["leads"][number]["points"]>();
    waveform?.leads.forEach((lead) => map.set(lead.lead, lead.points));
    return map;
  }, [waveform]);

  const printScale = useMemo(() => paperScale(timeWindow), [timeWindow.start, timeWindow.end]);

  function resetView() {
    setTimeWindow({ start: 0, end: waveform?.durationSec ?? 10 });
    setHighlightedLeads([]);
    setOverlays([]);
    setSelectedPoint(null);
  }

  function zoom(factor: number) {
    const duration = waveform?.durationSec ?? 10;
    const center = (timeWindow.start + timeWindow.end) / 2;
    const span = Math.max(0.8, Math.min(duration, (timeWindow.end - timeWindow.start) * factor));
    const start = Math.max(0, Math.min(duration - span, center - span / 2));
    setTimeWindow({ start, end: start + span });
  }

  function pan(delta: number) {
    const duration = waveform?.durationSec ?? 10;
    const span = timeWindow.end - timeWindow.start;
    const nextStart = Math.max(0, Math.min(duration - span, timeWindow.start + delta));
    setTimeWindow({ start: nextStart, end: nextStart + span });
  }

  function applyAction(action: ViewerAction) {
    if (action.type === "resetView") {
      resetView();
      return;
    }
    if (action.type === "zoom" && action.timeStart !== undefined && action.timeEnd !== undefined) {
      const duration = waveform?.durationSec ?? 10;
      setTimeWindow(fitActionWindowToLead(action.timeStart, action.timeEnd, action.leads?.[0], duration));
    }
    if (action.type === "highlightLead" && action.lead) {
      setHighlightedLeads((current) => Array.from(new Set([...current, action.lead as string])));
    }
    if (["highlightROI", "circleROI", "drawCaliper", "showFiducial"].includes(action.type)) {
      setOverlays((current) => [...current, action]);
      if (action.lead) {
        setHighlightedLeads((current) => Array.from(new Set([...current, action.lead as string])));
      }
    }
  }

  useEffect(() => {
    for (const action of actions) {
      applyAction(action);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(actions)]);

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
    setGrading(true);
    try {
      const result = await api.gradeClick(caseId, {
        lead: point.lead,
        timeSec: point.timeSec,
        amplitudeMv: point.amplitudeMv,
        concept: task?.mode === "point" ? task.concept : gradeConcept ?? null,
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
    if (task?.mode !== "region") return;
    setGrading(true);
    try {
      const result = await api.gradeRegion(caseId, {
        lead: roi.lead,
        timeStartSec: roi.timeStartSec,
        timeEndSec: roi.timeEndSec,
        ampMinMv: roi.ampMinMv,
        ampMaxMv: roi.ampMaxMv,
        concept: task.concept,
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
    if (task?.mode !== "caliper") return;
    const concept = taskRoiConcept(task);
    if (!concept) {
      setTaskFeedback(`${task.measurement.toUpperCase()} span: ${valueMs} ms in ${roi.lead}.`);
      onTaskEvidence?.({ mode: "caliper", lead: roi.lead, timeStartSec: roi.timeStartSec, timeEndSec: roi.timeEndSec, valueMs });
      return;
    }
    setGrading(true);
    try {
      const result = await api.gradeRegion(caseId, {
        lead: roi.lead,
        timeStartSec: roi.timeStartSec,
        timeEndSec: roi.timeEndSec,
        ampMinMv: roi.ampMinMv,
        ampMaxMv: roi.ampMaxMv,
        concept,
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
    if (task?.mode !== "march") return;
    const concept = task.target === "p_waves" ? "p_wave" : "qrs_complex";
    setGrading(true);
    try {
      const result = await api.gradeClick(caseId, {
        lead: point.lead,
        timeSec: point.timeSec,
        amplitudeMv: point.amplitudeMv,
        concept,
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
    const visiblePlacements = placementsForLead(lead, timeWindow);
    if (!visiblePlacements.some((placement) => placementContainsTime(placement, timeSec))) return null;
    const points = (signalByLead.get(lead) ?? []).filter((point) => visiblePlacements.some((placement) => placementContainsTime(placement, point.timeSec)));
    if (!points.length || !Number.isFinite(timeSec)) return null;
    let nearest = points[0];
    for (const point of points) {
      if (Math.abs(point.timeSec - timeSec) < Math.abs(nearest.timeSec - timeSec)) nearest = point;
    }
    return { lead, timeSec: nearest.timeSec, amplitudeMv: nearest.amplitudeMv };
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
    const placement = mainLeadPlacement(keyboardLead, timeWindow)
      ?? (keyboardLead === "II" ? rhythmPlacement(timeWindow) : null);
    if (!placement || !placementContainsTime(placement, start) || !placementContainsTime(placement, end)) {
      setTaskFeedback(placement
        ? `Both boundaries must stay inside the same visible ${keyboardLead} panel (${placement.timeStart.toFixed(3)}–${placement.timeEnd.toFixed(3)} s).`
        : `Lead ${keyboardLead} is not visible in this layout.`);
      return;
    }
    const startSec = Math.max(0, Math.min(start, waveform?.durationSec ?? 10));
    const endSec = Math.max(startSec, Math.min(end, waveform?.durationSec ?? 10));
    const segment = (signalByLead.get(keyboardLead) ?? []).filter((sample) => sample.timeSec >= startSec && sample.timeSec <= endSec);
    if (!segment.length) {
      setTaskFeedback("No waveform samples fall between those boundaries.");
      return;
    }
    const valueMs = Math.round((endSec - startSec) * 1000);
    const values = segment.map((sample) => sample.amplitudeMv);
    const roi: UserRoi = {
      lead: keyboardLead,
      timeStartSec: startSec,
      timeEndSec: endSec,
      ampMinMv: Math.min(...values) - 0.03,
      ampMaxMv: Math.max(...values) + 0.03,
      label: task.mode === "caliper" ? `${task.measurement.toUpperCase()} · ${valueMs} ms` : "Keyboard-selected region",
      concept: task.mode === "region" ? task.concept : task.measurement,
      source: "user",
      confidence: "low",
    };
    setUserRois((current) => [...current, roi]);
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
    if (identifyMode) return;
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
    setSelectedPoint(point);
    onCoordinate?.(point);
    if (task && !leadAllowed(point.lead)) {
      setTaskFeedback(`Use ${task.allowedLeads?.join(", ")}. Your mark in ${point.lead} was not submitted.`);
      setDragStart(null);
      return;
    }
    if (identifyMode) {
      void gradeAt(point);
      return;
    }
    if (task?.mode === "march") {
      void addMarchedPoint(point);
      setDragStart(null);
      return;
    }
    if (dragStart && dragStart.placementKey === point.placementKey && Math.abs(point.timeSec - dragStart.timeSec) > 0.04) {
      const timeStartSec = Math.min(dragStart.timeSec, point.timeSec);
      const timeEndSec = Math.max(dragStart.timeSec, point.timeSec);
      const valueMs = Math.round((timeEndSec - timeStartSec) * 1000);
      const roi: UserRoi = {
        lead: point.lead,
        timeStartSec,
        timeEndSec,
        ampMinMv: Math.min(dragStart.amplitudeMv, point.amplitudeMv),
        ampMaxMv: Math.max(dragStart.amplitudeMv, point.amplitudeMv),
        label: task?.mode === "caliper" ? `${task.measurement.toUpperCase()} · ${valueMs} ms` : "Learner annotation",
        concept: task?.mode === "region" ? task.concept : task?.mode === "caliper" ? task.measurement : "learner_annotation",
        source: "user",
        confidence: "low",
      };
      setUserRois((current) => [...current, roi]);
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

  return (
    <section className="panel ecg-viewer" aria-label="Interactive 12-lead ECG viewer">
      {toolbar === "none" ? null : (
      <div className="viewer-toolbar">
        <div className="viewer-toolbar-main">
          <strong>
            {medianMode ? <HeartPulse size={16} aria-hidden="true" /> : <Crosshair size={16} aria-hidden="true" />}
            {medianMode ? " Median beat (12-lead average)" : " Interactive 12-lead ECG"}
          </strong>
          <div className="muted">
            {medianMode
              ? `Averaged ~${Math.round(medianBeats?.durationMs ?? 0)} ms beat · ${medianBeats?.samplingFrequency ?? "..."} Hz · 25 mm/s · 10 mm/mV`
              : `Window ${timeWindow.start.toFixed(1)}s to ${timeWindow.end.toFixed(1)}s · ${waveform?.samplingFrequency ?? "..."} Hz · standard 3×4 sequential + II rhythm · ${PAPER_SPEED_MM_PER_SEC} mm/s · ${GAIN_MM_PER_MV} mm/mV`}
          </div>
          {!medianMode && highlightedLeads.length ? (
            <span className="pill">{highlightedLeads.join(", ")} highlighted</span>
          ) : null}
        </div>
        <div className="actions">
          <button
            className={`icon-button${medianMode ? " active" : ""}`}
            type="button"
            onClick={() => {
              if (!medianAvailable) return;
              setMedianMode((current) => !current);
              // Median view has no time axis to identify against; leave identify mode.
              setIdentifyMode(false);
              setClickFeedback(null);
            }}
            aria-pressed={medianMode}
            disabled={!medianAvailable}
            title={medianAvailable ? (medianMode ? "Hide median beat" : "Show median beat") : "No median beat available for this case"}
          >
            <HeartPulse size={18} aria-hidden="true" />
          </button>
          <button
            className={`icon-button${identifyMode ? " active" : ""}`}
            type="button"
            onClick={() => {
              setIdentifyMode((current) => !current);
              setClickFeedback(null);
            }}
            aria-pressed={identifyMode}
            disabled={medianMode || Boolean(task && task.mode !== "point")}
            title="Identify feature (click to grade)"
          >
            <Target size={18} aria-hidden="true" />
          </button>
          <button
            className={`icon-button${showAllLabels ? " active" : ""}`}
            type="button"
            onClick={() => setShowAllLabels((current) => !current)}
            aria-pressed={showAllLabels}
            disabled={medianMode}
            title={showAllLabels ? "Hide ROI labels" : "Show all ROI labels"}
          >
            <Tag size={17} aria-hidden="true" />
          </button>
          <button className="icon-button" type="button" onClick={() => zoom(0.55)} disabled={medianMode} title="Zoom in">
            <ZoomIn size={18} aria-hidden="true" />
          </button>
          <button className="icon-button" type="button" onClick={() => zoom(1.8)} disabled={medianMode} title="Zoom out">
            <ZoomOut size={18} aria-hidden="true" />
          </button>
          <button className="icon-button" type="button" onClick={() => pan(-0.8)} disabled={medianMode} title="Pan left">
            <ChevronLeft size={18} aria-hidden="true" />
          </button>
          <button className="icon-button" type="button" onClick={() => pan(0.8)} disabled={medianMode} title="Pan right">
            <ChevronRight size={18} aria-hidden="true" />
          </button>
          <button className="icon-button" type="button" onClick={() => setOverlays([])} disabled={medianMode} title="Clear AI highlights">
            <Eraser size={17} aria-hidden="true" />
          </button>
          <button className="icon-button" type="button" onClick={resetView} disabled={medianMode} title="Reset view">
            <RefreshCw size={17} aria-hidden="true" />
          </button>
        </div>
      </div>
      )}
      {error ? <div className="warning">{error}</div> : null}
      {identifyMode || task ? (
        <div className="identify-banner">
          <Target size={15} aria-hidden="true" />
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
              onClick={() => {
                setMarchPoints([]);
                setUserRois([]);
                setTaskFeedback(null);
                if (task.mode === "march") onTaskEvidence?.({ mode: "march", points: [] });
              }}
            >
              Clear task marks
            </button>
          ) : null}
        </div>
      ) : null}
      <div ref={stageRef} className={`viewer-stage${!medianMode && identifyMode ? " identify" : ""}`}>
        {medianMode && medianBeats ? (
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
            viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
            role="img"
            aria-label="Interactive standard 12-lead ECG with lead II rhythm strip"
            onPointerDown={onPointerDown}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerCancel}
            style={{ aspectRatio: `${WIDTH} / ${HEIGHT}`, minHeight: 0, touchAction: "none" }}
          >
            <PanelDefs prefix={clipPrefix} />
            <PaperGrid timeWindow={timeWindow} />
            {leadLayout.map((row, rowIndex) =>
              row.map((lead, columnIndex) => (
                <LeadPanel
                  key={lead}
                  lead={lead}
                  row={rowIndex}
                  column={columnIndex}
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
                  onHoverChange={(hovered) => setHoveredRoiKey((current) => (hovered ? key : current === key ? null : current))}
                />
              );
            })}
            {overlays.map((action, index) => (
              <ActionOverlay key={`${action.type}-${action.lead}-${index}`} action={action} timeWindow={timeWindow} clipPrefix={clipPrefix} />
            ))}
            {clickFeedback ? <ClickMarker feedback={clickFeedback} timeWindow={timeWindow} clipPrefix={clipPrefix} /> : null}
            {task?.mode === "march" ? marchPoints.map((point, index) => (
              <TaskMarker key={`${point.lead}-${point.timeSec}-${index}`} point={point} label={`${index + 1}`} timeWindow={timeWindow} clipPrefix={clipPrefix} />
            )) : null}
            <CalibrationMark height={HEIGHT} pxPerSec={printScale.pxPerSec} pxPerMv={printScale.pxPerMv} clipId={`${clipPrefix}-rhythm-clip`} />
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
                {(task.allowedLeads?.length ? task.allowedLeads : waveform?.leads.map((lead) => lead.lead) ?? ["II"]).map((lead) => <option key={lead} value={lead}>{lead}</option>)}
              </select>
            </label>
            <label>
              <span>{task.mode === "region" || task.mode === "caliper" ? "First boundary (seconds)" : "Time cursor (seconds)"}</span>
              <input type="number" min={mainLeadPlacement(keyboardLead, timeWindow)?.timeStart ?? timeWindow.start} max={mainLeadPlacement(keyboardLead, timeWindow)?.timeEnd ?? timeWindow.end} step={1 / (waveform?.samplingFrequency ?? 100)} value={keyboardStart} onChange={(event) => setKeyboardStart(event.target.value)} />
            </label>
            {task.mode === "region" || task.mode === "caliper" ? (
              <label>
                <span>Second boundary (seconds)</span>
                <input type="number" min={mainLeadPlacement(keyboardLead, timeWindow)?.timeStart ?? timeWindow.start} max={mainLeadPlacement(keyboardLead, timeWindow)?.timeEnd ?? timeWindow.end} step={1 / (waveform?.samplingFrequency ?? 100)} value={keyboardEnd} onChange={(event) => setKeyboardEnd(event.target.value)} />
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
      {toolbar === "none" ? null : (
        <div className="viewer-help">
          {medianMode
            ? "Median beat: one averaged complex per lead on the same square calibrated paper (small box 0.04 s × 0.1 mV, large box 0.2 s × 0.5 mV). Use it to compare morphology without beat-to-beat noise."
            : "Standard print: sequential 2.5-second lead columns plus a continuous lead-II rhythm strip at 25 mm/s and 10 mm/mV. Grid boxes stay square through zoom. Click to map the correct lead, acquisition time, and amplitude; drag within one panel to annotate."}
        </div>
      )}
      {clickFeedback ? (
        <div className={`click-feedback ${clickFeedback.noTarget ? "neutral" : clickFeedback.correct ? "ok" : "miss"}`}>
          <strong>{clickFeedback.noTarget ? "No target here" : clickFeedback.correct ? "Correct" : "Not yet"}</strong>
          <span>{clickFeedback.noTarget ? clickFeedback.feedback || "This case has no grounded target for that feature — nothing to identify here." : clickFeedback.feedback}</span>
          {clickFeedback.matchedRoi ? (
            <span className="muted">Matched ROI: {clickFeedback.matchedRoi.label} ({clickFeedback.matchedRoi.lead})</span>
          ) : null}
        </div>
      ) : null}
      {taskFeedback ? <div className="click-feedback neutral" role="status" aria-live="polite"><strong>Task evidence</strong><span>{taskFeedback}</span></div> : null}
      <div className="coordinate-readout">
        {selectedPoint ? (
          <>
            <span className="coord-chip"><Crosshair size={14} aria-hidden="true" /> {selectedPoint.lead}</span>
            <span>{selectedPoint.timeSec.toFixed((waveform?.samplingFrequency ?? 100) >= 500 ? 3 : 2)} sec</span>
            <span>{selectedPoint.amplitudeMv.toFixed(3)} mV</span>
            <span className="muted">source resolution ≈ {Math.round(1000 / (waveform?.samplingFrequency ?? 100))} ms</span>
          </>
        ) : (
          <span>No point selected</span>
        )}
      </div>
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

function placementsForLead(lead: string, timeWindow: TimeWindow): LeadPlacement[] {
  const main = mainLeadPlacement(lead, timeWindow);
  return [...(main ? [main] : []), ...(lead === "II" ? [rhythmPlacement(timeWindow)] : [])];
}

function placementContainsTime(placement: LeadPlacement, timeSec: number): boolean {
  return timeSec >= placement.timeStart - 1e-9 && timeSec <= placement.timeEnd + 1e-9;
}

function PanelDefs({ prefix }: { prefix: string }) {
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

function PaperGrid({ timeWindow }: { timeWindow: TimeWindow }) {
  const scale = paperScale(timeWindow);
  const minorLines: ReactElement[] = [];
  const majorLines: ReactElement[] = [];

  // Vertical paper lines stay anchored to absolute acquisition time through pan/zoom.
  const firstMinorTime = Math.ceil(timeWindow.start / SMALL_BOX_SEC) * SMALL_BOX_SEC;
  for (let t = firstMinorTime; t <= timeWindow.end + 1e-9; t += SMALL_BOX_SEC) {
    const x = (t - timeWindow.start) * scale.pxPerSec;
    const isMajor = Math.abs(t / LARGE_BOX_SEC - Math.round(t / LARGE_BOX_SEC)) < 1e-6;
    const line = <line key={`v-${t.toFixed(3)}`} x1={x} x2={x} y1={0} y2={HEIGHT} stroke={isMajor ? "#e6a3a3" : "#f6dcdc"} strokeWidth={isMajor ? 1.1 : 0.6} />;
    (isMajor ? majorLines : minorLines).push(line);
  }

  // Horizontal lines repeat around each lead's 0 mV baseline. Because both axes use
  // the same px/mm, the boxes remain square at every digital zoom level.
  for (let rowIndex = 0; rowIndex < ROWS; rowIndex += 1) {
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
      <rect x={0} y={0} width={WIDTH} height={HEIGHT} fill="#fffafa" />
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
  row,
  column,
  points,
  timeWindow,
  highlighted,
  clipPrefix,
}: {
  lead: string;
  row: number;
  column: number;
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

function ClickMarker({ feedback, timeWindow, clipPrefix }: { feedback: ClickFeedback; timeWindow: TimeWindow; clipPrefix: string }) {
  const scale = paperScale(timeWindow);
  const color = feedback.correct ? "#0e7c66" : "#c43c36";
  return (
    <>
      {placementsForLead(feedback.point.lead, timeWindow)
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

function TaskMarker({ point, label, timeWindow, clipPrefix }: { point: ECGPoint; label: string; timeWindow: TimeWindow; clipPrefix: string }) {
  const scale = paperScale(timeWindow);
  return (
    <>
      {placementsForLead(point.lead, timeWindow)
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
}: {
  roi: GroundedRoi;
  timeWindow: TimeWindow;
  user?: boolean;
  /** Whether to render the text label (default hidden; shown on hover / toggle / AI highlight). */
  showLabel?: boolean;
  onHoverChange?: (hovered: boolean) => void;
  clipPrefix: string;
}) {
  const scale = paperScale(timeWindow);
  const placements = placementsForLead(roi.lead, timeWindow).filter(
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

function ActionOverlay({ action, timeWindow, clipPrefix }: { action: ViewerAction; timeWindow: TimeWindow; clipPrefix: string }) {
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
      />
    );
  }
  if (action.type === "drawCaliper" && action.lead && action.timeStart !== undefined && action.timeEnd !== undefined) {
    const scale = paperScale(timeWindow);
    const durationMs = Math.round(Math.abs(action.timeEnd - action.timeStart) * 1000);
    return (
      <>
        {placementsForLead(action.lead, timeWindow)
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
        {placementsForLead(action.lead, timeWindow)
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
        {placementsForLead(action.lead, timeWindow)
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
