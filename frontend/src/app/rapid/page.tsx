"use client";

import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Brain,
  CheckCircle2,
  Clock3,
  GitBranch,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Timer,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ECGViewer } from "@/components/ECGViewer";
import { TutorChat } from "@/components/TutorChat";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { clinicalApi } from "@/lib/clinical";
import { conceptLabel } from "@/lib/coordinates";
import { resolveHandoffTarget, type HandoffTargetResolution } from "@/lib/learning/handoffTargets";
import type { LearningSubskill } from "@/lib/learning/interactionTypes";
import type {
  CasePacket,
  CaseSummary,
  RapidEvidenceReceipt,
  RapidRoundPayload,
  TutorMessageResponse,
  ViewerAction,
  ViewerTaskEvidence,
  ViewerTaskSpec,
} from "@/lib/types";

type PaceId = "ward" | "emergency" | "untimed";
type View = "setup" | "runner" | "complete";

type Pace = {
  id: PaceId;
  title: string;
  detail: string;
  seconds: number | null;
  icon: typeof Timer;
};

type SweepState = {
  rate: string;
  rhythm: string;
  axis: string;
  intervals: string;
  conduction: string;
  st_t: string;
  chambers: string;
  synthesis: string;
};

type RapidGrade = {
  score?: number;
  correctObjectives?: string[];
  missedObjectives?: string[];
  overcalledObjectives?: string[];
  misconceptions?: string[];
  feedback?: string;
  teachingPoints?: string[];
  revealedDiagnosis?: string;
};

type CaseResult = {
  caseId: string;
  displayId: string;
  score: number;
  timedOut: boolean;
  responseMs: number | null;
  correctObjectives: string[];
  missedObjectives: string[];
  overcalledObjectives: string[];
  misconceptions: string[];
  revealedDiagnosis: string;
};

type RapidConceptOption = { id: string; label: string };
type RapidConceptGroup = { id: string; label: string; concepts: RapidConceptOption[] };

type RapidSessionSnapshot = {
  version: 2;
  ownerKey: string;
  roundId?: string;
  context: string;
  view: View;
  paceId: PaceId;
  sessionLength: number;
  caseIndex: number;
  caseSummary: CaseSummary | null;
  packet: CasePacket | null;
  sweep: SweepState;
  selectedConcepts: string[];
  confidence: number;
  grade: RapidGrade | null;
  aiViewerActions: ViewerAction[];
  traceEvidence: ViewerTaskEvidence | null;
  traceReceipt: string;
  handoffReceipt: string;
  results: CaseResult[];
  startedAtEpochMs: number | null;
  deadlineAtEpochMs: number | null;
};

const PACES: Pace[] = [
  {
    id: "ward",
    title: "Ward read",
    detail: "75 seconds for a compact, systematic sweep without turning the task into a typing test.",
    seconds: 75,
    icon: Clock3,
  },
  {
    id: "emergency",
    title: "Time-pressured quick-look",
    detail: "20 seconds for one dominant resting-ECG finding. Not ACLS or acute-event certification.",
    seconds: 20,
    icon: Zap,
  },
  {
    id: "untimed",
    title: "Untimed practice",
    detail: "Build the same snap read without a clock.",
    seconds: null,
    icon: Activity,
  },
];

const EMPTY_SWEEP: SweepState = {
  rate: "",
  rhythm: "",
  axis: "",
  intervals: "",
  conduction: "",
  st_t: "",
  chambers: "",
  synthesis: "",
};

const SESSION_LENGTHS = [5, 10, 25, 50, 100, 500, 1000, 5000];
const RAPID_SESSION_KEY_PREFIX = "ecg-tool:rapid-round:v2";
const RAPID_TRACE_TASK: ViewerTaskSpec = {
  mode: "point",
  prompt: "Trace proof: mark one QRS complex in lead II before committing the full read.",
  concept: "qrs_complex",
  allowedLeads: ["II"],
};

function rapidSourceLabel(source: string) {
  if (source === "ptbxl") return "PTB-XL recording";
  if (source === "prepared_bundle") return "Prepared PTB-XL recording";
  if (source === "leipzig-heart-center") return "Leipzig expert rhythm window";
  return source.replaceAll("_", " ").replaceAll("-", " ");
}

const RAPID_CASE_CONCEPTS = [
  "normal_ecg", "rate", "sinus_rhythm", "axis_normal", "left_axis_deviation", "right_axis_deviation",
  "premature_ventricular_complex", "premature_atrial_complex", "bradycardia", "av_block_first_degree",
  "av_block_second_degree_mobitz_ii", "av_block_third_degree", "atrial_fibrillation", "atrial_flutter",
  "supraventricular_tachycardia", "wide_complex_tachycardia", "qrs_duration", "right_bundle_branch_block", "left_bundle_branch_block",
  "left_anterior_fascicular_block", "left_posterior_fascicular_block", "wolff_parkinson_white",
  "paced_rhythm",
  "left_ventricular_hypertrophy", "right_ventricular_hypertrophy", "atrial_enlargement", "qt_interval",
  "qtc_prolongation", "nonspecific_st_t_change", "st_depression", "t_wave_inversion", "myocardial_ischemia",
  "electrolyte_drug_pattern", "myocardial_infarction", "anterior_mi", "inferior_mi", "lateral_mi", "septal_mi", "posterior_mi", "pathologic_q_waves",
];

const FRAMEWORK_STEPS = [
  { key: "rate", label: "Rate" },
  { key: "rhythm", label: "Rhythm" },
  { key: "axis", label: "Axis" },
  { key: "intervals", label: "Intervals" },
  { key: "conduction", label: "QRS" },
  { key: "st_t", label: "ST–T" },
  { key: "chambers", label: "Chambers" },
  { key: "synthesis", label: "Synthesis" },
] as const;

const FALLBACK_CONCEPT_GROUPS: RapidConceptGroup[] = [{
  id: "validated-rapid-findings",
  label: "Validated rapid findings",
  concepts: RAPID_CASE_CONCEPTS.map((id) => ({ id, label: conceptLabel(id) })),
}];

function buildRapidConceptGroups(payload: Awaited<ReturnType<typeof api.concepts>>): RapidConceptGroup[] {
  const labels = new Map(payload.concepts.map((concept) => [concept.id, concept.label]));
  const seen = new Set<string>();
  const groups = payload.practiceGroups.flatMap((group) => {
    const concepts = group.concepts.flatMap((concept) => {
      if (!concept.available || seen.has(concept.id)) return [];
      seen.add(concept.id);
      return [{ id: concept.id, label: labels.get(concept.id) ?? concept.label ?? conceptLabel(concept.id) }];
    });
    return concepts.length ? [{ id: group.id, label: group.label, concepts }] : [];
  });
  const validatedRemainder = RAPID_CASE_CONCEPTS
    .filter((id) => !seen.has(id))
    .map((id) => ({ id, label: labels.get(id) ?? conceptLabel(id) }));
  if (validatedRemainder.length) {
    groups.push({ id: "validated-rapid-findings", label: "Additional validated findings", concepts: validatedRemainder });
  }
  return groups.length ? groups : FALLBACK_CONCEPT_GROUPS;
}

function frequencyRank(values: string[]): string[] {
  const counts = new Map<string, number>();
  values.forEach((value) => counts.set(value, (counts.get(value) ?? 0) + 1));
  return [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([value]) => value);
}

function debriefTarget(results: CaseResult[]): string | null {
  return frequencyRank(results.flatMap((result) => result.missedObjectives))[0]
    ?? frequencyRank(results.flatMap((result) => result.overcalledObjectives))[0]
    ?? frequencyRank(results.flatMap((result) => result.correctObjectives))[0]
    ?? null;
}

function clinicalHandoffHref(results: CaseResult[], supportedConcepts: ReadonlySet<string>): string | null {
  const target = frequencyRank([
    ...results.flatMap((result) => result.missedObjectives),
    ...results.flatMap((result) => result.correctObjectives),
  ]).find((concept) => supportedConcepts.has(concept));
  return target ? `/practice?concept=${encodeURIComponent(target)}&mode=learn&returnTo=/rapid` : null;
}

function deterministicDebriefFallback(results: CaseResult[]): string {
  const missed = frequencyRank(results.flatMap((result) => result.missedObjectives));
  const overcalled = frequencyRank(results.flatMap((result) => result.overcalledObjectives));
  if (missed.length) return `Your deterministic receipts point first to ${conceptLabel(missed[0])}. Re-run it against a close mimic, then carry the same discriminator into a clinical decision.`;
  if (overcalled.length) return `${conceptLabel(overcalled[0])} was the most frequent overcall. Practice naming the positive evidence you require before committing that label.`;
  return "Your deterministic receipts did not identify one dominant miss. Increase interleaving and preserve the same rate–rhythm–axis–QRS–ST/T sequence on the next round.";
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function epochMs(value: unknown): number | null {
  if (typeof value !== "string" || !value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function caseResultFromRecord(value: Record<string, unknown>): CaseResult {
  return {
    caseId: typeof value.caseId === "string" ? value.caseId : "",
    displayId: typeof value.displayId === "string" ? value.displayId : String(value.caseId ?? "ECG"),
    score: typeof value.score === "number" ? value.score : 0,
    timedOut: value.timedOut === true,
    responseMs: typeof value.responseMs === "number" ? value.responseMs : null,
    correctObjectives: stringList(value.correctObjectives),
    missedObjectives: stringList(value.missedObjectives),
    overcalledObjectives: stringList(value.overcalledObjectives),
    misconceptions: stringList(value.misconceptions),
    revealedDiagnosis: typeof value.revealedDiagnosis === "string" ? value.revealedDiagnosis : "",
  };
}

function receiptSummary(receipts: RapidEvidenceReceipt[]): string {
  const accepted = receipts.filter((receipt) => receipt.accepted);
  const recognition = accepted.filter((receipt) => receipt.subskill === "recognize");
  const localized = accepted.some((receipt) => receipt.subskill === "localize" && receipt.concept === "qrs_complex");
  const synthesized = accepted.filter((receipt) => receipt.subskill === "synthesize");
  const parts: string[] = [];
  if (recognition.length) parts.push(`explicit recognition: ${recognition.map((item) => conceptLabel(item.concept)).join(", ")}`);
  if (localized) parts.push("server-verified QRS localization");
  if (synthesized.length) parts.push(`complete-read synthesis ${synthesized.some((item) => item.correct === false) ? "attempt" : "success"}: ${synthesized.map((item) => conceptLabel(item.concept)).join(", ")}`);
  return parts.length
    ? `Exact server receipt${parts.length === 1 ? "" : "s"}: ${parts.join(" · ")}. Free-text inference did not update mastery.`
    : "No mastery receipt was created. Rapid credit requires an explicit supported finding, server-verified trace location, or a prescribed complete structured-sweep task.";
}

function rapidSessionKey(ownerKey: string): string {
  return `${RAPID_SESSION_KEY_PREFIX}:${ownerKey}`;
}

function readRapidSession(ownerKey: string): RapidSessionSnapshot | null {
  try {
    const parsed: unknown = JSON.parse(window.sessionStorage.getItem(rapidSessionKey(ownerKey)) ?? "null");
    if (!isRecord(parsed) || parsed.version !== 2 || parsed.ownerKey !== ownerKey || parsed.context !== window.location.search) return null;
    if (!(["setup", "runner", "complete"] as unknown[]).includes(parsed.view)) return null;
    if (!(["ward", "emergency", "untimed"] as unknown[]).includes(parsed.paceId)) return null;
    if (!SESSION_LENGTHS.includes(Number(parsed.sessionLength)) || !Array.isArray(parsed.results)) return null;
    const savedSweep = parsed.sweep;
    if (!isRecord(savedSweep) || !Object.keys(EMPTY_SWEEP).every((key) => typeof savedSweep[key] === "string")) return null;
    if (!Array.isArray(parsed.selectedConcepts) || !parsed.selectedConcepts.every((item) => typeof item === "string")) return null;
    const caseSummary = parsed.caseSummary;
    const packet = parsed.packet;
    if (parsed.view === "runner" && (
      !isRecord(caseSummary) || typeof caseSummary.caseId !== "string"
      || !isRecord(packet) || packet.case_id !== caseSummary.caseId
    )) return null;
    return parsed as RapidSessionSnapshot;
  } catch {
    return null;
  }
}

export default function RapidPage() {
  const { identityKey } = useAuth();
  const [roundId, setRoundId] = useState("");
  const [roundStatus, setRoundStatus] = useState<"active" | "complete" | "abandoned">("active");
  const [sessionReady, setSessionReady] = useState(false);
  const [view, setView] = useState<View>("setup");
  const [paceId, setPaceId] = useState<PaceId>("ward");
  const [sessionLength, setSessionLength] = useState(5);
  const [caseIndex, setCaseIndex] = useState(0);
  const [caseSummary, setCaseSummary] = useState<CaseSummary | null>(null);
  const [packet, setPacket] = useState<CasePacket | null>(null);
  const [sweep, setSweep] = useState<SweepState>(EMPTY_SWEEP);
  const [selectedConcepts, setSelectedConcepts] = useState<string[]>([]);
  const [confidence, setConfidence] = useState(3);
  const [grade, setGrade] = useState<RapidGrade | null>(null);
  const [aiViewerActions, setAiViewerActions] = useState<ViewerAction[]>([]);
  const [traceEvidence, setTraceEvidence] = useState<ViewerTaskEvidence | null>(null);
  const [results, setResults] = useState<CaseResult[]>([]);
  const [serverResultCount, setServerResultCount] = useState(0);
  const [conceptGroups, setConceptGroups] = useState<RapidConceptGroup[]>(FALLBACK_CONCEPT_GROUPS);
  const [rapidAvailableConcepts, setRapidAvailableConcepts] = useState<Set<string>>(new Set(RAPID_CASE_CONCEPTS));
  const [catalogLoaded, setCatalogLoaded] = useState(false);
  const [clinicalSupportedConcepts, setClinicalSupportedConcepts] = useState<Set<string>>(new Set());
  const [remaining, setRemaining] = useState<number | null>(null);
  const [clockRunning, setClockRunning] = useState(false);
  const [roundDebrief, setRoundDebrief] = useState<TutorMessageResponse | null>(null);
  const [roundDebriefError, setRoundDebriefError] = useState("");
  const [roundDebriefBusy, setRoundDebriefBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [returnTo, setReturnTo] = useState("");
  const [handoffFocus, setHandoffFocus] = useState("");
  const [handoffSubskill, setHandoffSubskill] = useState<LearningSubskill | "">("");
  const [handoffReceiptConcept, setHandoffReceiptConcept] = useState("");
  const [handoffReceipt, setHandoffReceipt] = useState("");
  const [handoffResolution, setHandoffResolution] = useState<HandoffTargetResolution | null>(null);
  const [handoffUnavailable, setHandoffUnavailable] = useState("");
  const [traceReceipt, setTraceReceipt] = useState("");
  const [startedAtEpochMs, setStartedAtEpochMs] = useState<number | null>(null);
  const [deadlineAtEpochMs, setDeadlineAtEpochMs] = useState<number | null>(null);

  const deadlineRef = useRef(0);
  const readyAtRef = useRef(0);
  const clockStartFrameRef = useRef<number | null>(null);
  const submittingRef = useRef(false);
  const activatedCaseRef = useRef("");
  const submitRef = useRef<(timedOut: boolean) => void>(() => undefined);
  const debriefRequestRef = useRef("");
  const restoredTimingRef = useRef<{ startedAtEpochMs: number | null; deadlineAtEpochMs: number | null } | null>(null);

  const pace = PACES.find((item) => item.id === paceId) ?? PACES[0];
  const score = typeof grade?.score === "number" ? grade.score : 0;
  const traceComplete = paceId === "emergency"
    || (traceEvidence?.mode === "point" && traceEvidence.correct === true && !traceEvidence.noTarget);
  const synthesisTaskComplete = Object.values(sweep).every((value) => value.trim().length > 0)
    && sweep.synthesis.trim().length >= 12
    && selectedConcepts.length > 0;
  const hasAnswer = (handoffSubskill === "synthesize" ? synthesisTaskComplete : (
    selectedConcepts.length > 0 || Object.values(sweep).some((value) => value.trim().length > 0)
  )) && traceComplete;
  const frameworkCurrentIndex = FRAMEWORK_STEPS.findIndex((step) => !sweep[step.key].trim());

  const applyRoundPayload = useCallback((payload: RapidRoundPayload, restoreLocalDraft = false) => {
    const round = payload.round;
    if (!round) return false;
    setRoundId(round.roundId);
    setRoundStatus(round.status);
    setPaceId(round.pace);
    setSessionLength(round.length);
    const incomingResults = payload.results.map(caseResultFromRecord);
    setServerResultCount(payload.resultCount ?? incomingResults.length);
    setResults((currentResults) => {
      const merged = new Map(currentResults.map((item) => [item.caseId, item]));
      incomingResults.forEach((item) => merged.set(item.caseId, item));
      return [...merged.values()];
    });
    const current = payload.current;
    if (!current) {
      setView(round.status === "complete" ? "complete" : "runner");
      setCaseSummary(null);
      setPacket(null);
      return true;
    }
    setCaseSummary(current.case);
    setPacket(current.packet);
    if (current.kind === "pending") {
      setView("runner");
      setCaseIndex(round.position);
      setGrade(null);
      setAiViewerActions([]);
      setTraceReceipt("");
      setHandoffReceipt("");
      submittingRef.current = false;
      const saved = restoreLocalDraft ? readRapidSession(identityKey) : null;
      const sameDraft = saved?.roundId === round.roundId && saved.caseSummary?.caseId === current.case.caseId;
      setSweep(sameDraft ? saved.sweep : EMPTY_SWEEP);
      setSelectedConcepts(sameDraft ? saved.selectedConcepts : []);
      setConfidence(sameDraft ? saved.confidence : 3);
      setTraceEvidence(sameDraft ? saved.traceEvidence : null);
      const started = epochMs(round.pendingStartedAt ?? current.startedAt);
      const deadline = epochMs(round.pendingDeadlineAt ?? current.deadlineAt);
      setStartedAtEpochMs(started);
      setDeadlineAtEpochMs(deadline);
      restoredTimingRef.current = { startedAtEpochMs: started, deadlineAtEpochMs: deadline };
      setRemaining(deadline === null ? null : Math.max(0, (deadline - Date.now()) / 1000));
      return true;
    }
    const answer = current.answer;
    if (!answer) return true;
    setView("runner");
    setCaseIndex(Math.max(0, round.position - 1));
    setGrade(answer.grade as RapidGrade);
    const storedTrace = (answer.response.traceEvidence as ViewerTaskEvidence | null | undefined) ?? null;
    setTraceEvidence(storedTrace?.mode === "point"
      ? {
          ...storedTrace,
          correct: answer.traceGrade?.correct === true,
          noTarget: answer.traceGrade?.noTarget === true,
          feedback: typeof answer.traceGrade?.feedback === "string" ? answer.traceGrade.feedback : storedTrace.feedback,
        }
      : storedTrace);
    setTraceReceipt(receiptSummary(answer.receipts));
    const result = answer.result;
    setStartedAtEpochMs(epochMs(result.startedAt));
    setDeadlineAtEpochMs(epochMs(result.deadlineAt));
    setClockRunning(false);
    setRemaining(0);
    submittingRef.current = true;
    return true;
  }, [identityKey]);

  useEffect(() => {
    let active = true;
    setSessionReady(false);
    api.activeRapidRound()
      .then((payload) => {
        if (!active) return;
        if (payload.round) {
          applyRoundPayload(payload, true);
          return;
        }
        // Browser storage is now only a setup preference/draft cache. It can no
        // longer manufacture or advance an assessment without a server round.
        const saved = readRapidSession(identityKey);
        if (saved?.view === "complete") {
          setView("complete");
          setPaceId(saved.paceId);
          setSessionLength(saved.sessionLength);
          setResults(saved.results);
        } else if (saved?.view === "setup") {
          setPaceId(saved.paceId);
          setSessionLength(saved.sessionLength);
        } else {
          setView("setup");
        }
      })
      .catch(() => {
        if (!active) return;
        const saved = readRapidSession(identityKey);
        if (saved?.view === "setup") {
          setPaceId(saved.paceId);
          setSessionLength(saved.sessionLength);
        }
        setView("setup");
        setError("Rapid round discovery is temporarily unavailable; a new assessment cannot start until the server reconnects.");
      })
      .finally(() => {
        if (active) setSessionReady(true);
      });
    return () => { active = false; };
  }, [identityKey, applyRoundPayload]);

  useEffect(() => {
    if (!sessionReady) return;
    // Keep the last complete case snapshot while the next selector request is in flight.
    if (view === "runner" && (!caseSummary || !packet)) return;
    const snapshot: RapidSessionSnapshot = {
      version: 2,
      ownerKey: identityKey,
      roundId: roundId || undefined,
      context: window.location.search,
      view,
      paceId,
      sessionLength,
      caseIndex,
      caseSummary,
      packet,
      sweep,
      selectedConcepts,
      confidence,
      grade,
      aiViewerActions,
      traceEvidence,
      traceReceipt,
      handoffReceipt,
      // The server owns the complete answer ledger. Keep only a small local
      // recovery tail so a 5,000-ECG marathon cannot exhaust sessionStorage.
      results: results.slice(-100),
      startedAtEpochMs,
      deadlineAtEpochMs,
    };
    try {
      window.sessionStorage.setItem(rapidSessionKey(identityKey), JSON.stringify(snapshot));
    } catch {
      // A storage quota or privacy setting must not interrupt a live assessment.
    }
  }, [sessionReady, identityKey, roundId, view, paceId, sessionLength, caseIndex, caseSummary, packet, sweep, selectedConcepts, confidence, grade, aiViewerActions, traceEvidence, traceReceipt, handoffReceipt, results, startedAtEpochMs, deadlineAtEpochMs]);

  useEffect(() => {
    let active = true;
    api.concepts()
      .then((payload) => {
        if (!active) return;
        const groups = buildRapidConceptGroups(payload);
        setConceptGroups(groups);
        setRapidAvailableConcepts(new Set(groups.flatMap((group) => group.concepts.map((concept) => concept.id))));
      })
      .catch(() => {
        // The complete validated fallback remains answerable if catalog loading fails.
      })
      .finally(() => {
        if (active) setCatalogLoaded(true);
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    clinicalApi.bankCoverage()
      .then(({ coverage }) => {
        if (!active) return;
        setClinicalSupportedConcepts(new Set(
          Object.entries(coverage)
            .filter(([, depth]) => depth.items > 0 && depth.distinctEcgs > 0)
            .map(([concept]) => concept),
        ));
      })
      .catch(() => {
        // A missing coverage contract must suppress the handoff, not advertise
        // a case family from a stale client-side assumption.
        if (active) setClinicalSupportedConcepts(new Set());
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const requestedReturn = params.get("returnTo") ?? "";
    if (requestedReturn.startsWith("/learn/") || requestedReturn === "/review") setReturnTo(requestedReturn);
    const requestedFocus = params.get("focus") ?? "";
    setHandoffFocus(requestedFocus);
    const requestedSubskill = params.get("subskill") ?? "";
    setHandoffReceiptConcept(params.get("receiptConcept") ?? requestedFocus);
    if (["recognize", "localize", "measure", "discriminate", "explain_mechanism", "synthesize", "apply_in_context", "calibrate_confidence"].includes(requestedSubskill)) {
      setHandoffSubskill(requestedSubskill as LearningSubskill);
      if (requestedSubskill === "synthesize") setPaceId("untimed");
    }
  }, []);

  useEffect(() => {
    if (!catalogLoaded) return;
    const resolution = handoffFocus ? resolveHandoffTarget(handoffFocus, rapidAvailableConcepts) : null;
    setHandoffResolution(resolution);
    setHandoffUnavailable(handoffFocus && !resolution
      ? `No validated Rapid case family can currently prove ${handoffFocus.replaceAll("_", " ")}. No substitute case or competency receipt will be created.`
      : "");
  }, [catalogLoaded, handoffFocus, rapidAvailableConcepts]);

  const loadCase = useCallback(async (activeRoundId = roundId) => {
    if (!activeRoundId) return;
    if (clockStartFrameRef.current !== null) window.cancelAnimationFrame(clockStartFrameRef.current);
    setBusy(true);
    setError(null);
    setGrade(null);
    setAiViewerActions([]);
    setTraceEvidence(null);
    setPacket(null);
    setCaseSummary(null);
    setSweep(EMPTY_SWEEP);
    setSelectedConcepts([]);
    setConfidence(3);
    setClockRunning(false);
    setHandoffReceipt("");
    setTraceReceipt("");
    setRemaining(pace.seconds);
    setStartedAtEpochMs(null);
    setDeadlineAtEpochMs(null);
    restoredTimingRef.current = null;
    readyAtRef.current = 0;
    submittingRef.current = false;
    activatedCaseRef.current = "";
    try {
      const next = await api.nextRapidCase(activeRoundId);
      applyRoundPayload(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load a rapid-practice ECG.");
    } finally {
      setBusy(false);
    }
  }, [roundId, pace.seconds, applyRoundPayload]);

  const startSession = useCallback(async () => {
    if (handoffFocus && !handoffResolution) {
      setError(handoffUnavailable || "This guided target has no validated Rapid case family.");
      return;
    }
    window.sessionStorage.removeItem(rapidSessionKey(identityKey));
    setResults([]);
    setServerResultCount(0);
    setRoundDebrief(null);
    setRoundDebriefError("");
    debriefRequestRef.current = "";
    setCaseIndex(0);
    setView("runner");
    setBusy(true);
    setError(null);
    try {
      const started = await api.startRapidRound({
        learnerId: "demo",
        pace: paceId,
        length: sessionLength,
        focusConcept: handoffResolution?.caseConcept ?? null,
        focusSubskill: handoffSubskill || null,
        contextKey: window.location.search,
        exclusions: [],
      });
      const nextRoundId = started.round?.roundId;
      if (!nextRoundId) throw new Error("The server did not create a Rapid round.");
      setRoundId(nextRoundId);
      await loadCase(nextRoundId);
    } catch (err) {
      setView("setup");
      setError(err instanceof Error ? err.message : "Could not start a Rapid round.");
    } finally {
      setBusy(false);
    }
  }, [identityKey, paceId, sessionLength, handoffFocus, handoffResolution, handoffSubskill, handoffUnavailable, loadCase]);

  const onViewerReady = useCallback(() => {
    if (grade || submittingRef.current || !roundId || !caseSummary) return;
    const activationKey = `${roundId}:${caseSummary.caseId}`;
    if (activatedCaseRef.current === activationKey) return;
    activatedCaseRef.current = activationKey;
    // ECGViewer resolves its waveform request just before React paints the SVG.
    // Two animation frames make the assessment clock begin only after the paper
    // and its response controls are visibly committed to the page.
    clockStartFrameRef.current = window.requestAnimationFrame(() => {
      clockStartFrameRef.current = window.requestAnimationFrame(() => {
        void api.nextRapidCase(roundId, true).then((activated) => {
          const nowEpochMs = Date.now();
          const serverStart = epochMs(activated.round?.pendingStartedAt);
          const serverDeadline = epochMs(activated.round?.pendingDeadlineAt);
          const restoredTiming = restoredTimingRef.current;
          restoredTimingRef.current = null;
          const authoritativeStart = serverStart ?? restoredTiming?.startedAtEpochMs ?? nowEpochMs;
          const authoritativeDeadline = serverDeadline ?? restoredTiming?.deadlineAtEpochMs ?? null;
          readyAtRef.current = performance.now() - Math.max(0, nowEpochMs - authoritativeStart);
          setStartedAtEpochMs(authoritativeStart);
          setDeadlineAtEpochMs(authoritativeDeadline);
          if (pace.seconds !== null && authoritativeDeadline !== null) {
            const secondsLeft = Math.max(0, (authoritativeDeadline - nowEpochMs) / 1000);
            deadlineRef.current = performance.now() + secondsLeft * 1000;
            setRemaining(secondsLeft);
            if (secondsLeft <= 0) {
              setClockRunning(false);
              window.setTimeout(() => submitRef.current(true), 0);
            } else {
              setClockRunning(true);
            }
          } else {
            setRemaining(null);
            setClockRunning(false);
          }
        }).catch((err) => {
          activatedCaseRef.current = "";
          setError(err instanceof Error ? err.message : "Could not activate the server-owned Rapid timer.");
        });
        clockStartFrameRef.current = null;
      });
    });
  }, [grade, pace.seconds, roundId, caseSummary]);

  useEffect(() => () => {
    if (clockStartFrameRef.current !== null) window.cancelAnimationFrame(clockStartFrameRef.current);
  }, []);

  const submit = useCallback(
    async (_timedOut: boolean) => {
      if (!roundId || !caseSummary || grade || submittingRef.current) return;
      submittingRef.current = true;
      setClockRunning(false);
      setBusy(true);
      setError(null);
      try {
        const response = await api.submitRapidCase(roundId, {
          caseId: caseSummary.caseId,
          structuredAnswer: {
            framework: "clerkship",
            rate: sweep.rate,
            rhythm: sweep.rhythm,
            axis: sweep.axis,
            intervals: sweep.intervals,
            conduction: sweep.conduction,
            st_t: sweep.st_t,
            hypertrophy: sweep.chambers,
            synthesis: sweep.synthesis,
            selectedConcepts,
          },
          freeTextAnswer: sweep.synthesis,
          confidence,
          traceEvidence,
        });
        applyRoundPayload(response);
        const receipts = response.receipts ?? response.answer?.receipts ?? [];
        setTraceReceipt(receiptSummary(receipts));
        if (handoffFocus && handoffSubskill && handoffResolution && results.length === 0) {
          const groundedTarget = handoffResolution.caseConcept;
          const requestedReceipt = handoffReceiptConcept || groundedTarget;
          const exactReceipt = receipts.find((receipt) =>
            receipt.accepted && receipt.concept === requestedReceipt && receipt.subskill === handoffSubskill
          );
          setHandoffReceipt(exactReceipt
            ? `Independent ${handoffSubskill.replaceAll("_", " ")} receipt recorded for ${conceptLabel(requestedReceipt)}${exactReceipt.correct === false ? " as a scored retrieval miss" : ""}.`
            : `No ${handoffSubskill.replaceAll("_", " ")} mastery receipt was created; review the exact task gate above rather than treating free text or overall score as evidence.`);
        }
      } catch (err) {
        submittingRef.current = false;
        setError(err instanceof Error ? err.message : "Could not grade this ECG.");
      } finally {
        setBusy(false);
      }
    },
    [roundId, caseSummary, grade, sweep, selectedConcepts, confidence, handoffFocus, handoffSubskill, handoffResolution, handoffReceiptConcept, results.length, traceEvidence, applyRoundPayload],
  );

  submitRef.current = submit;

  useEffect(() => {
    if (!clockRunning || pace.seconds === null) return;
    const timer = window.setInterval(() => {
      const next = Math.max(0, (deadlineRef.current - performance.now()) / 1000);
      setRemaining(next);
      if (next <= 0) {
        window.clearInterval(timer);
        setClockRunning(false);
        submitRef.current(true);
      }
    }, 100);
    return () => window.clearInterval(timer);
  }, [clockRunning, pace.seconds]);

  async function advance() {
    if (roundStatus === "complete" || caseIndex + 1 >= sessionLength) {
      if (roundId) {
        setBusy(true);
        try {
          applyRoundPayload(await api.nextRapidCase(roundId));
        } catch (err) {
          setError(err instanceof Error ? err.message : "Could not finish the Rapid round.");
        } finally {
          setBusy(false);
        }
      } else {
        setView("complete");
      }
      return;
    }
    setCaseIndex((current) => current + 1);
    await loadCase();
  }

  function toggleConcept(concept: string) {
    if (grade) return;
    if (paceId === "emergency") {
      setSelectedConcepts([concept]);
      return;
    }
    setSelectedConcepts((current) =>
      current.includes(concept) ? current.filter((item) => item !== concept) : [...current, concept],
    );
  }

  const sessionAverage = useMemo(
    () => (results.length ? results.reduce((sum, item) => sum + item.score, 0) / results.length : 0),
    [results],
  );
  const averageResponse = useMemo(() => {
    const values = results.flatMap((item) => (item.responseMs === null ? [] : [item.responseMs]));
    return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
  }, [results]);
  const roundTarget = useMemo(() => debriefTarget(results), [results]);
  const clinicalHref = useMemo(
    () => clinicalHandoffHref(results, clinicalSupportedConcepts),
    [results, clinicalSupportedConcepts],
  );
  const crossConceptBridge = useMemo(() => {
    const missed = frequencyRank(results.flatMap((result) => result.missedObjectives));
    const correct = frequencyRank(results.flatMap((result) => result.correctObjectives));
    if (missed[0] && correct[0] && missed[0] !== correct[0]) {
      return `Connect ${conceptLabel(correct[0])} to ${conceptLabel(missed[0])}: use the feature you recognized as the anchor, then state the additional discriminator the missed diagnosis requires.`;
    }
    if (missed.length > 1) {
      return `Compare ${conceptLabel(missed[0])} with ${conceptLabel(missed[1])} side by side; name one shared feature and one decisive separator before looking at another label.`;
    }
    if (roundTarget) {
      return `Carry ${conceptLabel(roundTarget)} through three levels: recognize the pattern, localize or measure its evidence, then explain what changes in the clinical context.`;
    }
    return "Keep the same framework across normal and abnormal tracings so speed comes from a stable sequence, not from skipping steps.";
  }, [results, roundTarget]);

  useEffect(() => {
    if (view !== "complete" || !roundId || serverResultCount <= results.length) return;
    let active = true;
    api.rapidResults(roundId, 0, 5000)
      .then((response) => {
        if (!active) return;
        setServerResultCount(response.total);
        setResults(response.results.map(caseResultFromRecord));
      })
      .catch(() => {
        if (active) setRoundDebriefError("The complete result ledger could not be loaded; retry after reconnecting.");
      });
    return () => { active = false; };
  }, [view, roundId, serverResultCount, results.length]);

  useEffect(() => {
    if (view !== "complete" || !results.length) return;
    if (serverResultCount > results.length) return;
    const lastResult = results.at(-1);
    const requestKey = `${results.length}:${lastResult?.caseId ?? ""}:${lastResult?.score ?? 0}`;
    if (debriefRequestRef.current === requestKey) return;
    debriefRequestRef.current = requestKey;
    setRoundDebriefBusy(true);
    setRoundDebriefError("");
    const receiptSample = results.slice(-25).map((result) => ({
      caseId: result.caseId,
      score: result.score,
      timedOut: result.timedOut,
      responseMs: result.responseMs,
      correct: result.correctObjectives,
      missed: result.missedObjectives,
      overcalled: result.overcalledObjectives,
      misconceptions: result.misconceptions,
    }));
    api.tutorMessage({
      mode: "practice",
      caseId: results.at(-1)?.caseId ?? null,
      message: `Debrief this completed ${paceId} rapid ECG round using only this deterministic aggregate and recent receipt sample. Identify one recurring reasoning pattern, connect at least two ECG concepts when supported, and give one concise next-step question. Do not add diagnoses or measurements. Aggregate: ${JSON.stringify({ completed: results.length, averageScore: sessionAverage, timedOut: results.filter((item) => item.timedOut).length, commonCorrect: frequencyRank(results.flatMap((item) => item.correctObjectives)).slice(0, 8), commonMissed: frequencyRank(results.flatMap((item) => item.missedObjectives)).slice(0, 8), commonOvercalls: frequencyRank(results.flatMap((item) => item.overcalledObjectives)).slice(0, 8) })}. Recent sample: ${JSON.stringify(receiptSample)}`,
      viewerState: {
        activity: "rapid_round_debrief",
        pace: paceId,
        completedCaseCount: results.length,
        recentDeterministicReceipts: receiptSample,
        deterministicOnly: true,
      },
    })
      .then(setRoundDebrief)
      .catch(() => setRoundDebriefError(deterministicDebriefFallback(results)))
      .finally(() => setRoundDebriefBusy(false));
  }, [view, results, paceId, sessionAverage, serverResultCount]);

  if (!sessionReady) {
    return <div className="page rapid-page"><section className="panel pad">Restoring your Rapid round…</section></div>;
  }

  if (view === "setup") {
    return (
      <div className="page rapid-page rapid-setup">
        <header className="page-header rapid-header">
          <div>
            <p className="eyebrow rapid-eyebrow">Mode 3 · rapid interpretation</p>
            <h1><Timer size={24} aria-hidden="true" /> Rapid ECG rounds</h1>
            <p className="muted rapid-intro">
              Real, blinded 12-lead ECGs. Commit a snap read, rate your confidence, then see deterministic
              case-grounded feedback. The tutor stays silent until you submit.
            </p>
          </div>
          {returnTo ? <Link className="button subtle" href={returnTo}><ArrowLeft size={16} /> Return to lesson</Link> : null}
        </header>

        {returnTo ? <div className="selection-note">This mixed transfer was launched for <strong>{handoffFocus.replaceAll("_", " ")} · {handoffSubskill ? handoffSubskill.replaceAll("_", " ") : "target concept"}</strong>. {handoffResolution ? <>The first case is constrained to <strong>{conceptLabel(handoffResolution.caseConcept)}</strong>{handoffResolution.exact ? "" : ` because ${handoffResolution.rationale}`}; later cases interleave the corpus.</> : "No unrelated case will be substituted."}</div> : null}
        {handoffUnavailable ? <div className="warning" role="alert">{handoffUnavailable}</div> : null}

        <section className="panel pad rapid-setup-panel">
          <div className="rapid-pace-grid" style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
            {PACES.map((item) => {
              const Icon = item.icon;
              const active = paceId === item.id;
              const unavailableForSynthesis = handoffSubskill === "synthesize" && item.id === "emergency";
              return (
                <button
                  className={`list-item rapid-pace${active ? " rapid-pace-active" : ""}`}
                  key={item.id}
                  type="button"
                  aria-pressed={active}
                  disabled={unavailableForSynthesis}
                  onClick={() => setPaceId(item.id)}
                  style={{ borderColor: active ? "var(--accent)" : undefined, textAlign: "left", cursor: unavailableForSynthesis ? "not-allowed" : "pointer", opacity: unavailableForSynthesis ? 0.55 : 1 }}
                >
                  <strong className="rapid-pace-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <Icon size={18} aria-hidden="true" /> {item.title}
                  </strong>
                  <p className="muted rapid-pace-detail" style={{ margin: "7px 0 0" }}>{unavailableForSynthesis ? "Unavailable for this receipt: a 20-second dominant-finding task cannot assess a complete structured synthesis." : item.detail}</p>
                </button>
              );
            })}
          </div>

          <div className="rapid-length" style={{ marginTop: 18 }}>
            <label className="field" style={{ display: "block", marginTop: 8, maxWidth: 320 }}>
              <span>Unique ECGs in this round</span>
              <select aria-label="Rapid round length" value={sessionLength} onChange={(event) => setSessionLength(Number(event.target.value))}>
                {SESSION_LENGTHS.map((length) => <option value={length} key={length}>{length.toLocaleString()} ECGs</option>)}
              </select>
            </label>
            <p className="muted" style={{ margin: "8px 0 0" }}>Every tracing is unique within the server-owned round. The full eligible corpus—not a demo bank—is available; 5,000-case marathons remain resumable across devices.</p>
          </div>

          <div className="rapid-setup-note selection-note" style={{ marginTop: 18 }}>
            <ShieldCheck size={16} aria-hidden="true" /> Diagnoses, concept labels, ROIs, and reports remain blinded until commitment.
          </div>
          {handoffSubskill === "synthesize" ? <div className="selection-note" style={{ marginTop: 10 }}>
            <strong>Independent synthesis gate:</strong> complete rate, rhythm, axis, intervals, QRS/conduction, ST–T, chambers, and an evidence-limited one-line synthesis; explicitly select the supported focus and avoid unsupported calls.
          </div> : null}
          <button
            className="button primary rapid-start"
            type="button"
            onClick={() => void startSession()}
            disabled={!catalogLoaded || Boolean(handoffUnavailable) || Boolean(handoffFocus && !handoffResolution)}
            style={{ marginTop: 16 }}
          >
            Start {pace.title.toLowerCase()} <ArrowRight size={16} aria-hidden="true" />
          </button>
        </section>
      </div>
    );
  }

  if (view === "complete") {
    return (
      <div className="page rapid-page rapid-complete">
        <header className="page-header rapid-header">
          <div>
            <p className="eyebrow rapid-eyebrow">Round complete</p>
            <h1><CheckCircle2 size={24} aria-hidden="true" /> Rapid round debrief</h1>
          </div>
        </header>
        <section className="panel pad rapid-summary">
          <div className="metric-row rapid-summary-metrics">
            <div className="metric rapid-summary-metric"><span className="metric-label">Average score</span><strong>{Math.round(sessionAverage * 100)}%</strong></div>
            <div className="metric rapid-summary-metric"><span className="metric-label">Completed</span><strong>{results.length}/{sessionLength}</strong></div>
            <div className="metric rapid-summary-metric"><span className="metric-label">Average response</span><strong>{averageResponse === null ? "Untimed" : `${(averageResponse / 1000).toFixed(1)}s`}</strong></div>
            <div className="metric rapid-summary-metric"><span className="metric-label">Timed out</span><strong>{results.filter((item) => item.timedOut).length}</strong></div>
          </div>
          {results.length > 50 ? <p className="muted">Showing the most recent 50 of {results.length.toLocaleString()} completed ECGs; all results remain in the server ledger and summary.</p> : null}
          <div className="list rapid-result-list" style={{ marginTop: 16 }}>
            {results.slice(-50).map((item, index) => (
              <div className="list-item rapid-result-row" key={`${item.caseId}-${index}`}>
                <strong>{index + 1}. {item.displayId}</strong>
                <span className="muted rapid-result-meta" style={{ marginLeft: 10 }}>
                  {Math.round(item.score * 100)}%{item.timedOut ? " · time" : item.responseMs ? ` · ${(item.responseMs / 1000).toFixed(1)}s` : ""}
                </span>
              </div>
            ))}
          </div>
          <section className="rapid-round-coach" aria-live="polite" aria-busy={roundDebriefBusy}>
            <div className="rapid-coach-kicker"><Sparkles size={15} aria-hidden="true" /> Grounded AI round coach</div>
            <h2>Turn the receipts into a next move</h2>
            {roundDebriefBusy ? <p className="muted">Connecting the deterministic case results…</p> : (
              <>
                <p>{roundDebrief?.tutorMessage || roundDebrief?.feedback || roundDebriefError || deterministicDebriefFallback(results)}</p>
                {roundDebrief?.socraticQuestion ? <p className="rapid-coach-question"><strong>Think next:</strong> {roundDebrief.socraticQuestion}</p> : null}
              </>
            )}
            <div className="rapid-cross-concept">
              <GitBranch size={17} aria-hidden="true" />
              <div><strong>Cross-concept bridge</strong><p>{crossConceptBridge}</p></div>
            </div>
            <div className="actions rapid-handoffs">
              {roundTarget ? (
                <Link className="button primary" href={`/train?focus=${encodeURIComponent(roundTarget)}&subskill=recognize&returnTo=/rapid`}>
                  Train {conceptLabel(roundTarget)} <ArrowRight size={15} aria-hidden="true" />
                </Link>
              ) : null}
              {clinicalHref ? (
                <Link className="button" href={clinicalHref}>
                  Apply in a clinical case <ArrowRight size={15} aria-hidden="true" />
                </Link>
              ) : null}
            </div>
          </section>
          <div className="actions rapid-complete-actions" style={{ marginTop: 16 }}>
            <button className="button primary rapid-restart" type="button" onClick={() => void startSession()}>
              <RotateCcw size={16} aria-hidden="true" /> Repeat this round
            </button>
            <button className="button rapid-new-setup" type="button" onClick={() => setView("setup")}>Change setup</button>
            {returnTo ? <Link className="button" href={returnTo}><ArrowLeft size={16} /> Return to lesson</Link> : null}
          </div>
        </section>
      </div>
    );
  }

  const correct = stringList(grade?.correctObjectives);
  const missed = stringList(grade?.missedObjectives);
  const overcalled = stringList(grade?.overcalledObjectives);
  const teachingPoints = stringList(grade?.teachingPoints);
  const timerPercent = pace.seconds && remaining !== null ? Math.max(0, Math.min(100, (remaining / pace.seconds) * 100)) : 100;
  const restoredTraceActions: ViewerAction[] = grade
    && traceEvidence?.mode === "point"
    && traceEvidence.correct === true
    && !traceEvidence.noTarget
    ? [{
        type: "showFiducial",
        lead: traceEvidence.point.lead,
        timeSec: traceEvidence.point.timeSec,
        label: "Committed QRS trace proof",
      }]
    : [];
  const caseViewerActions = grade
    ? [...restoredTraceActions, ...aiViewerActions]
    : [];

  return (
    <div className={`page rapid-page rapid-runner rapid-${paceId}`}>
      <header className="rapid-hud" style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
        <span className="pill rapid-mode-pill"><Timer size={14} aria-hidden="true" /> {pace.title}</span>
        <strong className="rapid-progress">ECG {caseIndex + 1} / {sessionLength}</strong>
        {caseSummary ? <span className="muted rapid-source"><ShieldCheck size={13} aria-hidden="true" /> {rapidSourceLabel(caseSummary.source)}</span> : null}
        <span className="muted rapid-silence"><ShieldCheck size={13} aria-hidden="true" /> Tutor silent until commitment</span>
        {returnTo ? <Link className="button subtle small" href={returnTo}><ArrowLeft size={15} /> Return to lesson</Link> : null}
        {pace.seconds !== null ? (
          <span
            className={`pill rapid-timer${!grade && clockRunning && remaining !== null && remaining <= 5 ? " rapid-timer-urgent" : ""}`}
            aria-label={grade ? "Rapid read complete" : clockRunning ? "Rapid timer running" : "Rapid timer waiting for ECG"}
            data-clock-state={grade ? "complete" : clockRunning ? "running" : "waiting"}
            style={{ marginLeft: "auto" }}
          >
            {grade ? "Read complete" : clockRunning ? `${Math.ceil(remaining ?? pace.seconds)}s` : "ECG loading"}
          </span>
        ) : grade ? (
          <span
            className="pill rapid-timer"
            aria-label="Rapid read complete"
            data-clock-state="complete"
            style={{ marginLeft: "auto" }}
          >
            Read complete
          </span>
        ) : <span className="pill rapid-untimed" style={{ marginLeft: "auto" }}>Untimed</span>}
      </header>

      {pace.seconds !== null && !grade ? (
        <div className="mastery-bar rapid-clockbar" aria-label={`${Math.ceil(remaining ?? pace.seconds)} seconds remaining`} style={{ marginTop: 10 }}>
          <span style={{ width: `${timerPercent}%` }} />
        </div>
      ) : null}
      {error ? <div className="warning rapid-error" style={{ marginTop: 12 }}>{error}</div> : null}

      {caseSummary && packet ? (
        <div className="rapid-workspace" style={{ display: "grid", gap: 16, marginTop: 14 }}>
          <section className="rapid-tracing">
            <ECGViewer
              caseId={caseSummary.caseId}
              actions={caseViewerActions}
              toolbar={grade ? "full" : "none"}
              onReady={onViewerReady}
              groundedRois={grade ? packet.ptbxl_plus.fiducials.rois ?? [] : []}
              medianBeats={packet.ptbxl_plus.median_beats ?? null}
              task={!grade && paceId !== "emergency" ? RAPID_TRACE_TASK : undefined}
              onTaskEvidence={setTraceEvidence}
            />
            {grade && traceEvidence?.mode === "point" && traceEvidence.correct === true && !traceEvidence.noTarget ? (
              <p className="selection-note rapid-restored-trace" aria-label="Committed trace proof" style={{ marginTop: 10 }}>
                <strong>Committed trace proof:</strong> QRS in lead {traceEvidence.point.lead} at {traceEvidence.point.timeSec.toFixed(2)}s.
              </p>
            ) : null}
          </section>

          {!grade ? (
            <section className={`panel pad rapid-answer-panel${paceId === "emergency" ? " rapid-quick-response" : ""}`}>
              <div className="rapid-answer-heading" style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                <div>
                  <p className="eyebrow rapid-answer-eyebrow">Commit your read</p>
                  <h2 style={{ margin: 0 }}>What matters on this ECG?</h2>
                </div>
                <span className="muted rapid-case-id">{caseSummary.displayId}</span>
              </div>

              {paceId !== "emergency" ? (
                <ol className="rapid-framework" aria-label="ECG interpretation framework">
                  {FRAMEWORK_STEPS.map((step, index) => {
                    const complete = Boolean(sweep[step.key].trim());
                    const current = frameworkCurrentIndex === index || (frameworkCurrentIndex === -1 && index === FRAMEWORK_STEPS.length - 1);
                    return (
                      <li className={`${complete ? "complete " : ""}${current ? "current" : ""}`.trim()} key={step.key} aria-current={current ? "step" : undefined}>
                        <span>{index + 1}</span>{step.label}
                      </li>
                    );
                  })}
                </ol>
              ) : null}
              {handoffSubskill === "synthesize" && !grade ? (
                <p className={`selection-note${synthesisTaskComplete ? " complete" : ""}`} role="status">
                  <strong>Exact synthesis receipt:</strong> {synthesisTaskComplete
                    ? "All eight sweep components and an explicit finding are ready for the server rubric."
                    : "Complete every sweep component, select at least one finding, and write a 12+ character evidence-limited synthesis."}
                </p>
              ) : null}

              <div className="rapid-recognition" style={{ marginTop: 14 }} data-catalog-loaded={catalogLoaded ? "true" : "false"}>
                <strong>{paceId === "emergency" ? "One dominant finding" : "Recognition tags"}</strong>
                {paceId === "emergency" ? (
                  <select
                    aria-label="One dominant ECG finding"
                    value={selectedConcepts[0] ?? ""}
                    onChange={(event) => setSelectedConcepts(event.target.value ? [event.target.value] : [])}
                    style={{ display: "block", marginTop: 8, minHeight: 44, width: "min(100%, 420px)" }}
                  >
                    <option value="">Choose the highest-yield finding…</option>
                    {conceptGroups.map((group) => (
                      <optgroup label={group.label} key={group.id}>
                        {group.concepts.map((concept) => <option value={concept.id} key={concept.id}>{concept.label}</option>)}
                      </optgroup>
                    ))}
                  </select>
                ) : (
                  <div className="rapid-recognition-options" style={{ marginTop: 8 }}>
                    {conceptGroups.map((group) => (
                      <div className="rapid-recognition-group" key={group.id}>
                        <span>{group.label}</span>
                        <div className="pill-row">
                          {group.concepts.map((concept) => {
                            const active = selectedConcepts.includes(concept.id);
                            return (
                              <button
                                className={`pill rapid-recognition-option${active ? " rapid-recognition-selected" : ""}`}
                                key={concept.id}
                                type="button"
                                aria-pressed={active}
                                onClick={() => toggleConcept(concept.id)}
                                style={{ cursor: "pointer", borderColor: active ? "var(--accent)" : undefined }}
                              >
                                {concept.label}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {paceId !== "emergency" ? <div className="form-grid rapid-sweep" style={{ marginTop: 14 }}>
                {([
                  ["rate", "Rate", "e.g. 75 bpm"],
                  ["rhythm", "Rhythm", "e.g. sinus, regular"],
                  ["axis", "Axis", "normal / left / right"],
                  ["intervals", "Intervals", "PR, QRS, QT/QTc"],
                  ["conduction", "QRS / conduction", "width and morphology"],
                  ["st_t", "ST-T", "key repolarization finding"],
                  ["chambers", "Chambers / voltage", "hypertrophy or enlargement"],
                ] as const).map(([key, label, placeholder]) => (
                  <div className="field rapid-sweep-field" key={key}>
                    <label htmlFor={`rapid-${key}`}>{label}</label>
                    <input
                      id={`rapid-${key}`}
                      value={sweep[key]}
                      placeholder={placeholder}
                      onChange={(event) => setSweep((current) => ({ ...current, [key]: event.target.value }))}
                    />
                  </div>
                ))}
                <div className="field full rapid-synthesis-field">
                  <label htmlFor="rapid-synthesis">One-line synthesis</label>
                  <input
                    id="rapid-synthesis"
                    value={sweep.synthesis}
                    placeholder="Lead with the most important finding"
                    onChange={(event) => setSweep((current) => ({ ...current, synthesis: event.target.value }))}
                  />
                </div>
              </div> : <p className="selection-note" style={{ marginTop: 12 }}>Commit one dominant finding and confidence. The complete sweep appears in the debrief; this clock measures prioritization, not typing speed.</p>}

              {paceId !== "emergency" ? (
                <p className={`selection-note rapid-trace-status${traceComplete ? " complete" : ""}`} role="status">
                  <strong>Trace proof:</strong> {traceComplete
                    ? "Validated QRS mark recorded for this read."
                    : "Mark one QRS in lead II above (or use the precise-entry alternative) before commitment."}
                </p>
              ) : null}

              <div className="rapid-commit-row" style={{ display: "flex", alignItems: "end", flexWrap: "wrap", gap: 12, marginTop: 14 }}>
                <div className="field rapid-confidence" style={{ minWidth: 180 }}>
                  <label htmlFor="rapid-confidence">Confidence</label>
                  <select id="rapid-confidence" value={confidence} onChange={(event) => setConfidence(Number(event.target.value))}>
                    <option value={1}>1 · guessing</option>
                    <option value={2}>2 · low</option>
                    <option value={3}>3 · moderate</option>
                    <option value={4}>4 · high</option>
                    <option value={5}>5 · certain</option>
                  </select>
                </div>
                <button className="button primary rapid-submit" type="button" disabled={busy || !hasAnswer} onClick={() => void submit(false)}>
                  {busy ? "Grading…" : "Commit interpretation"} <ArrowRight size={16} aria-hidden="true" />
                </button>
              </div>
            </section>
          ) : (
            <section className={`panel pad rapid-feedback${score >= 0.6 ? " rapid-feedback-ok" : " rapid-feedback-miss"}`}>
              <div className="rapid-feedback-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                <h2 style={{ margin: 0 }}>
                  {score >= 0.6 ? <CheckCircle2 size={19} aria-hidden="true" /> : <AlertTriangle size={19} aria-hidden="true" />} Deterministic feedback
                </h2>
                <strong className="rapid-score" style={{ fontSize: "1.4rem" }}>{Math.round(score * 100)}%</strong>
              </div>
              {grade.feedback ? <p className="rapid-feedback-copy">{grade.feedback}</p> : null}

              <div className="evidence-grid rapid-feedback-grid">
                <div className="evidence-card rapid-correct">
                  <h3>Recognized</h3>
                  <div className="pill-row rapid-correct-list">
                    {correct.length ? correct.map((item) => <span className="pill rapid-objective" key={item}>{conceptLabel(item)}</span>) : <span className="muted">No target finding matched.</span>}
                  </div>
                </div>
                <div className="evidence-card rapid-missed">
                  <h3>Review</h3>
                  <div className="pill-row rapid-missed-list">
                    {missed.length ? missed.map((item) => <span className="pill disabled rapid-objective" key={item}>{conceptLabel(item)}</span>) : <span className="muted">No grounded targets missed.</span>}
                  </div>
                </div>
                <div className="evidence-card rapid-overcalled">
                  <h3>Overcalled</h3>
                  <div className="pill-row rapid-overcalled-list">
                    {overcalled.length ? overcalled.map((item) => <span className="pill disabled rapid-objective" key={item}>{conceptLabel(item)}</span>) : <span className="muted">No unsupported call detected.</span>}
                  </div>
                </div>
              </div>

              {teachingPoints.length ? (
                <div className="list rapid-teaching-points" style={{ marginTop: 14 }}>
                  {teachingPoints.slice(0, 4).map((point) => <div className="list-item rapid-teaching-point" key={point}>{point}</div>)}
                </div>
              ) : null}
              {grade.revealedDiagnosis ? <p className="uncertainty rapid-reference" style={{ marginTop: 12 }}>Grounded reference: {grade.revealedDiagnosis}</p> : null}
              {traceReceipt ? <p className="selection-note" style={{ marginTop: 12 }}>{traceReceipt}</p> : null}
              {handoffReceipt ? <p className="selection-note" style={{ marginTop: 12 }}>{handoffReceipt}</p> : null}
              <TutorChat
                mode="practice"
                roleLabel="Debrief · post-commit"
                caseId={caseSummary.caseId}
                openingPrompt="Ask why the key finding fits, request a grounded highlight, or compare it with the closest mimic."
                viewerState={{
                  activity: "rapid_case_debrief",
                  pace: paceId,
                  score,
                  correctObjectives: correct,
                  missedObjectives: missed,
                  overcalledObjectives: overcalled,
                  committed: true,
                }}
                onViewerActions={setAiViewerActions}
                resetKey={caseSummary.caseId}
                collapsedByDefault
              />
              <button className="button primary rapid-next" type="button" onClick={() => void advance()} disabled={busy} style={{ marginTop: 16 }}>
                {caseIndex + 1 >= sessionLength ? "Finish round" : "Next ECG"} <ArrowRight size={16} aria-hidden="true" />
              </button>
            </section>
          )}
        </div>
      ) : (
        <section className="panel pad rapid-loading" style={{ marginTop: 14 }}>
          {busy ? "Selecting a blinded ECG from the corpus…" : error ?? "No ECG loaded."}
        </section>
      )}
    </div>
  );
}
