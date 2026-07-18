"use client";

import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BrainCircuit,
  CheckCircle2,
  Clock3,
  GitBranch,
  Layers3,
  ListChecks,
  Siren,
  RotateCcw,
  ShieldCheck,
  ScanSearch,
  Sparkles,
  Timer,
  XCircle,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ECGViewer } from "@/components/ECGViewer";
import {
  RapidQuestionDeck,
  rapidTaskAnswered,
  type RapidTaskResponse,
} from "@/components/rapid/RapidQuestionDeck";
import { TutorChat } from "@/components/TutorChat";
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
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { clinicalApi } from "@/lib/clinical";
import { conceptLabel } from "@/lib/coordinates";
import { resolveHandoffTarget, type HandoffTargetResolution } from "@/lib/learning/handoffTargets";
import type { LearningSubskill } from "@/lib/learning/interactionTypes";
import { learningReturnLabel } from "@/lib/learning/learningReturn";
import { competencySkillLabel } from "@/lib/learning/skillLabels";
import { parseRapidLaunchIntent, RAPID_CASE_CONCEPTS, RAPID_EMERGENCY_RHYTHM_CONCEPTS, RAPID_SESSION_LENGTHS, RAPID_VISIBLE_SESSION_LENGTHS, rapidClinicalHandoffHref, rapidDebriefPracticeHref, rapidReceiptSummary } from "@/lib/learning/rapidLogic";
import { useLearningPreferences } from "@/lib/useLearningPreferences";
import type {
  CasePacket,
  CaseSummary,
  EcgCapability,
  RapidEvidenceReceipt,
  RapidRoundPayload,
  RapidTaskPacket,
  TutorMessageResponse,
  ViewerAction,
  ViewerTaskEvidence,
  ViewerTaskSpec,
} from "@/lib/types";

type PaceId = "ward" | "emergency" | "untimed";
type View = "setup" | "runner" | "complete";
type AnswerStage = "findings" | "sweep" | "commit";
type PracticeMode = "adaptive" | "mixed" | "emergency";
type QuestionDepth = "quick" | "focused" | "complete";

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
  taskFeedback?: Array<{
    taskId: string;
    prompt?: string;
    correct?: boolean;
    learnerAnswer?: string;
    supportedAnswer?: string;
    explanation?: string;
    closestMimic?: string;
    feedback?: string;
    correctAnswer?: string;
    correctChoiceId?: string;
    expectedValue?: number;
    unit?: string;
  }>;
};

type CaseResult = {
  caseId: EcgCapability;
  score: number;
  timedOut: boolean;
  responseMs: number | null;
  correctObjectives: string[];
  missedObjectives: string[];
  overcalledObjectives: string[];
  misconceptions: string[];
  revealedDiagnosis: string;
  competencyOutcomes: Array<{
    objectiveId: string;
    subskill: string;
    correct: boolean;
    score: number;
    formativeOnly: boolean;
  }>;
};

type RapidConceptOption = { id: string; label: string };
type RapidConceptGroup = { id: string; label: string; concepts: RapidConceptOption[] };

type RapidSessionSnapshot = {
  version: 4;
  ownerKey: string;
  roundId?: string;
  context: string;
  view: View;
  paceId: PaceId;
  practiceMode: PracticeMode;
  questionDepth: QuestionDepth;
  sessionLength: number;
  caseIndex: number;
  /** Only the opaque ref needed to match a server-restored draft is cached. */
  currentCaseRef: EcgCapability | null;
  sweep: SweepState;
  selectedConcepts: string[];
  confidence: number;
  grade: RapidGrade | null;
  aiViewerActions: ViewerAction[];
  traceEvidence: ViewerTaskEvidence | null;
  taskResponses: Record<string, RapidTaskResponse>;
  activeTaskIndex: number;
  traceReceipt: string;
  handoffReceipt: string;
  results: CaseResult[];
  startedAtEpochMs: number | null;
  deadlineAtEpochMs: number | null;
};

const PACES: Pace[] = [
  {
    id: "ward",
    title: "Standard timer",
    detail: "A realistic clock that scales to the questions on each tracing.",
    seconds: 120,
    icon: Clock3,
  },
  {
    id: "emergency",
    title: "Speed round",
    detail: "Short recognition decisions when the task is designed for a quick look.",
    seconds: 20,
    icon: Zap,
  },
  {
    id: "untimed",
    title: "No timer",
    detail: "Work at your own pace while keeping the same focused question flow.",
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

// Keep the established storage key so in-progress drafts remain discoverable;
// the payload itself is versioned independently and is now privacy-minimized.
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
  if (source === "ecg-fragment-dangerous-arrhythmia") return "Reviewed high-risk rhythm fragment";
  if (source === "mit-bih-vfdb") return "MIT-BIH malignant ventricular rhythm segment";
  if (source === "staff-iii") return "STAFF III serial ischemia recording";
  return source.replaceAll("_", " ").replaceAll("-", " ");
}

function rapidFindingLabel(concept: string) {
  if (concept === "uncertain") return "Uncertain / no supported abnormality";
  return conceptLabel(concept)
    .replace(/\s+\([^()]+\)$/, "")
    .split(/\s+/)
    .map((word) => (/^[a-z]/.test(word) ? `${word[0].toUpperCase()}${word.slice(1)}` : word))
    .join(" ");
}

function normalizeExactFinding(value: string) {
  return value.trim().replace(/\s+/g, " ").toLocaleLowerCase();
}

function learningSkillLabel(value: string) {
  return competencySkillLabel(value);
}

type SweepStep = {
  key: keyof SweepState;
  label: string;
  prompt: string;
  placeholder: string;
  choices?: readonly string[];
};

const FRAMEWORK_STEPS: readonly SweepStep[] = [
  { key: "rate", label: "Rate", prompt: "What is the ventricular rate?", placeholder: "Optional: enter one estimate, e.g. 75 bpm", choices: ["Bradycardic", "Normal rate", "Tachycardic", "Rate uncertain"] },
  { key: "rhythm", label: "Rhythm", prompt: "Name the rhythm and regularity.", placeholder: "Optional: add a more precise rhythm description", choices: ["Regular sinus rhythm", "Irregularly irregular", "Regular non-sinus rhythm", "Rhythm uncertain"] },
  { key: "axis", label: "Axis", prompt: "What is the frontal-plane axis?", placeholder: "Optional: add a degree estimate", choices: ["Normal axis", "Left axis deviation", "Right axis deviation", "Extreme axis"] },
  { key: "intervals", label: "Intervals", prompt: "Summarize PR, QRS, and QT/QTc.", placeholder: "Optional: add measured intervals", choices: ["Intervals appear normal", "PR prolonged", "QRS prolonged", "QT/QTc prolonged", "Multiple interval abnormalities"] },
  { key: "conduction", label: "QRS", prompt: "Describe QRS width and conduction morphology.", placeholder: "Optional: name the conduction pattern", choices: ["Narrow QRS / no block", "RBBB pattern", "LBBB pattern", "Other wide QRS"] },
  { key: "st_t", label: "ST–T", prompt: "Describe the key repolarization finding.", placeholder: "Optional: add leads or morphology", choices: ["No acute ST–T abnormality", "ST elevation", "ST depression", "T-wave inversion", "Nonspecific ST–T change"] },
  { key: "chambers", label: "Chambers", prompt: "Is there chamber enlargement or hypertrophy?", placeholder: "Optional: add the chamber or criteria", choices: ["No chamber enlargement", "LVH pattern", "RVH pattern", "Atrial enlargement"] },
  { key: "synthesis", label: "Synthesis", prompt: "Commit one evidence-limited summary.", placeholder: "Lead with the most important finding" },
];

function firstIncompleteSweepIndex(sweep: SweepState) {
  const index = FRAMEWORK_STEPS.findIndex((step) => !sweep[step.key].trim());
  return index === -1 ? FRAMEWORK_STEPS.length - 1 : index;
}

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

function debriefTarget(results: CaseResult[]): { objectiveId: string; subskill: string } | null {
  const missedCells = results.flatMap((result) => result.competencyOutcomes.filter(
    (outcome) => !outcome.formativeOnly && !outcome.correct,
  ));
  if (missedCells.length) {
    const ranked = frequencyRank(missedCells.map((outcome) => `${outcome.objectiveId}\0${outcome.subskill}`));
    const [objectiveId, subskill] = ranked[0].split("\0");
    return { objectiveId, subskill };
  }
  const missedObjective = frequencyRank(results.flatMap((result) => result.missedObjectives))[0];
  if (missedObjective) return { objectiveId: missedObjective, subskill: "recognize" };
  const overcalledObjective = frequencyRank(results.flatMap((result) => result.overcalledObjectives))[0];
  if (overcalledObjective) return { objectiveId: overcalledObjective, subskill: "recognize" };
  const correctObjective = frequencyRank(results.flatMap((result) => result.correctObjectives))[0];
  return correctObjective ? { objectiveId: correctObjective, subskill: "recognize" } : null;
}

function deterministicDebriefFallback(results: CaseResult[]): string {
  const missedCells = results.flatMap((result) => result.competencyOutcomes.filter(
    (outcome) => !outcome.formativeOnly && !outcome.correct,
  ));
  if (missedCells.length) {
    const ranked = frequencyRank(missedCells.map((outcome) => `${outcome.objectiveId}\0${outcome.subskill}`));
    const [objectiveId, subskill] = ranked[0].split("\0");
    return `${conceptLabel(objectiveId)} · ${learningSkillLabel(subskill)} is the clearest place to focus next. Repeat that exact skill on a new tracing, then explain the discriminator.`;
  }
  const missed = frequencyRank(results.flatMap((result) => result.missedObjectives));
  const overcalled = frequencyRank(results.flatMap((result) => result.overcalledObjectives));
  if (missed.length) return `${conceptLabel(missed[0])} is the clearest place to focus next. Compare it with a close look-alike, then use the same clue in a clinical case.`;
  if (overcalled.length) return `${conceptLabel(overcalled[0])} was the most frequent overcall. Practice naming the positive evidence you require before committing that label.`;
  return "No single finding dominated this round. Keep the same rate–rhythm–axis–QRS–ST/T sequence while mixing the next set.";
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function rapidTaskResponseDisplay(
  taskPacket: RapidTaskPacket | null,
  responses: Record<string, RapidTaskResponse>,
  taskId: string,
) {
  const task = taskPacket?.tasks.find((candidate) => candidate.id === taskId);
  const response = responses[taskId];
  if (typeof response === "number" && Number.isFinite(response)) {
    return `${response}${task?.unit ? ` ${task.unit}` : ""}`;
  }
  if (typeof response === "string") {
    return task?.options?.find((option) => option.id === response)?.label ?? response;
  }
  if (Array.isArray(response)) {
    return response.map((value) => task?.options?.find((option) => option.id === value)?.label ?? value).join(", ");
  }
  if (response && typeof response === "object") {
    const record = response as Record<string, unknown>;
    const point = record.point;
    if (point && typeof point === "object" && "lead" in point && "timeSec" in point) {
      return `${String(point.lead)} at ${Number(point.timeSec).toFixed(2)} s`;
    }
    return Object.values(record).filter(Boolean).map(String).join(" · ");
  }
  return "No answer";
}

function epochMs(value: unknown): number | null {
  if (typeof value !== "string" || !value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function caseResultFromRecord(value: Record<string, unknown>): CaseResult {
  const competencyOutcomes = Array.isArray(value.competencyOutcomes)
    ? value.competencyOutcomes.flatMap((item) => {
        if (!isRecord(item)
          || typeof item.objectiveId !== "string"
          || typeof item.subskill !== "string"
          || typeof item.correct !== "boolean") return [];
        return [{
          objectiveId: item.objectiveId,
          subskill: item.subskill,
          correct: item.correct,
          score: typeof item.score === "number" && Number.isFinite(item.score) ? item.score : item.correct ? 1 : 0,
          formativeOnly: item.formativeOnly === true,
        }];
      })
    : [];
  return {
    caseId: typeof value.caseId === "string" ? value.caseId : "",
    score: typeof value.score === "number" ? value.score : 0,
    timedOut: value.timedOut === true,
    responseMs: typeof value.responseMs === "number" ? value.responseMs : null,
    correctObjectives: stringList(value.correctObjectives),
    missedObjectives: stringList(value.missedObjectives),
    overcalledObjectives: stringList(value.overcalledObjectives),
    misconceptions: stringList(value.misconceptions),
    revealedDiagnosis: typeof value.revealedDiagnosis === "string" ? value.revealedDiagnosis : "",
    competencyOutcomes,
  };
}

function receiptSummary(receipts: RapidEvidenceReceipt[]): string {
  return rapidReceiptSummary(receipts, conceptLabel);
}

function rapidSessionKey(ownerKey: string): string {
  return `${RAPID_SESSION_KEY_PREFIX}:${ownerKey}`;
}

function learnerScaleRapidLength(value: number | null | undefined): (typeof RAPID_VISIBLE_SESSION_LENGTHS)[number] {
  if (!value || value <= 5) return 5;
  if (value <= 10) return 10;
  return 20;
}

function readRapidSession(ownerKey: string): RapidSessionSnapshot | null {
  try {
    const parsed: unknown = JSON.parse(window.sessionStorage.getItem(rapidSessionKey(ownerKey)) ?? "null");
    if (!isRecord(parsed) || ![2, 3, 4].includes(Number(parsed.version)) || parsed.ownerKey !== ownerKey || parsed.context !== window.location.search) return null;
    if (!(["setup", "runner", "complete"] as unknown[]).includes(parsed.view)) return null;
    if (!(["ward", "emergency", "untimed"] as unknown[]).includes(parsed.paceId)) return null;
    if (parsed.view === "complete" && (typeof parsed.roundId !== "string" || !parsed.roundId || parsed.roundId.length > 160)) return null;
    if (!RAPID_SESSION_LENGTHS.includes(Number(parsed.sessionLength) as (typeof RAPID_SESSION_LENGTHS)[number]) || !Array.isArray(parsed.results)) return null;
    const savedSweep = parsed.sweep;
    if (!isRecord(savedSweep) || !Object.keys(EMPTY_SWEEP).every((key) => typeof savedSweep[key] === "string")) return null;
    if (!Array.isArray(parsed.selectedConcepts) || !parsed.selectedConcepts.every((item) => typeof item === "string")) return null;
    const legacyCaseSummary = parsed.caseSummary;
    const legacyPacket = parsed.packet;
    const currentCaseRef = Number(parsed.version) >= 3
      ? (typeof parsed.currentCaseRef === "string" ? parsed.currentCaseRef : null)
      : (isRecord(legacyCaseSummary) && typeof legacyCaseSummary.caseId === "string" ? legacyCaseSummary.caseId : null);
    if (parsed.version === 2 && parsed.view === "runner" && (
      !currentCaseRef || !isRecord(legacyPacket) || legacyPacket.case_id !== currentCaseRef
    )) return null;
    if (Number(parsed.version) >= 3 && parsed.view === "runner" && !currentCaseRef) return null;
    return {
      version: 4,
      ownerKey,
      roundId: typeof parsed.roundId === "string" ? parsed.roundId : undefined,
      context: window.location.search,
      view: parsed.view as View,
      paceId: parsed.paceId as PaceId,
      practiceMode: (["adaptive", "mixed", "emergency"] as unknown[]).includes(parsed.practiceMode)
        ? parsed.practiceMode as PracticeMode
        : "adaptive",
      questionDepth: (["quick", "focused", "complete"] as unknown[]).includes(parsed.questionDepth)
        ? parsed.questionDepth as QuestionDepth
        : "focused",
      sessionLength: Number(parsed.sessionLength),
      caseIndex: Number.isFinite(Number(parsed.caseIndex)) ? Number(parsed.caseIndex) : 0,
      currentCaseRef,
      sweep: savedSweep as SweepState,
      selectedConcepts: parsed.selectedConcepts,
      confidence: Number.isFinite(Number(parsed.confidence)) ? Number(parsed.confidence) : 3,
      grade: isRecord(parsed.grade) ? parsed.grade as RapidGrade : null,
      aiViewerActions: Array.isArray(parsed.aiViewerActions) ? parsed.aiViewerActions as ViewerAction[] : [],
      traceEvidence: isRecord(parsed.traceEvidence) ? parsed.traceEvidence as ViewerTaskEvidence : null,
      taskResponses: isRecord(parsed.taskResponses)
        ? parsed.taskResponses as Record<string, RapidTaskResponse>
        : {},
      activeTaskIndex: Number.isFinite(Number(parsed.activeTaskIndex)) ? Math.max(0, Number(parsed.activeTaskIndex)) : 0,
      traceReceipt: typeof parsed.traceReceipt === "string" ? parsed.traceReceipt : "",
      handoffReceipt: typeof parsed.handoffReceipt === "string" ? parsed.handoffReceipt : "",
      results: parsed.results.filter(isRecord).map(caseResultFromRecord),
      startedAtEpochMs: typeof parsed.startedAtEpochMs === "number" ? parsed.startedAtEpochMs : null,
      deadlineAtEpochMs: typeof parsed.deadlineAtEpochMs === "number" ? parsed.deadlineAtEpochMs : null,
    };
  } catch {
    return null;
  }
}

export default function RapidPage() {
  const { identityKey } = useAuth();
  const { preferences, loading: preferencesLoading } = useLearningPreferences();
  const [roundId, setRoundId] = useState("");
  const [sessionRetryKey, setSessionRetryKey] = useState(0);
  const [roundStatus, setRoundStatus] = useState<"active" | "complete" | "abandoned">("active");
  const [sessionReady, setSessionReady] = useState(false);
  const [view, setView] = useState<View>("setup");
  const [paceId, setPaceId] = useState<PaceId>("ward");
  const [practiceMode, setPracticeMode] = useState<PracticeMode>("adaptive");
  const [rhythmSupplement, setRhythmSupplement] = useState<NonNullable<RapidRoundPayload["rhythmSupplement"]>>({
    available: false,
    count: 0,
    targetCounts: {},
  });
  const [questionDepth, setQuestionDepth] = useState<QuestionDepth>("focused");
  const [sessionLength, setSessionLength] = useState(5);
  const [caseIndex, setCaseIndex] = useState(0);
  const [caseSummary, setCaseSummary] = useState<CaseSummary | null>(null);
  const [packet, setPacket] = useState<CasePacket | null>(null);
  const [sweep, setSweep] = useState<SweepState>(EMPTY_SWEEP);
  const [selectedConcepts, setSelectedConcepts] = useState<string[]>([]);
  const [findingSearch, setFindingSearch] = useState("");
  const [findingMenuOpen, setFindingMenuOpen] = useState(false);
  const [findingActiveIndex, setFindingActiveIndex] = useState(0);
  const [answerStage, setAnswerStage] = useState<AnswerStage>("findings");
  const [activeSweepIndex, setActiveSweepIndex] = useState(0);
  const [confidence, setConfidence] = useState(3);
  const [grade, setGrade] = useState<RapidGrade | null>(null);
  const [aiViewerActions, setAiViewerActions] = useState<ViewerAction[]>([]);
  const [traceEvidence, setTraceEvidence] = useState<ViewerTaskEvidence | null>(null);
  const [taskPacket, setTaskPacket] = useState<RapidTaskPacket | null>(null);
  const [taskResponses, setTaskResponses] = useState<Record<string, RapidTaskResponse>>({});
  const [activeTaskIndex, setActiveTaskIndex] = useState(0);
  const [results, setResults] = useState<CaseResult[]>([]);
  const [serverResultCount, setServerResultCount] = useState(0);
  const [conceptGroups, setConceptGroups] = useState<RapidConceptGroup[]>(FALLBACK_CONCEPT_GROUPS);
  const [rapidAvailableConcepts, setRapidAvailableConcepts] = useState<Set<string>>(new Set(RAPID_CASE_CONCEPTS));
  const [catalogLoaded, setCatalogLoaded] = useState(false);
  const [clinicalDestinations, setClinicalDestinations] = useState<Map<string, { lane: "clinic" | "ward" | "ed" }>>(new Map());
  const [remaining, setRemaining] = useState<number | null>(null);
  const [clockRunning, setClockRunning] = useState(false);
  const [roundDebrief, setRoundDebrief] = useState<TutorMessageResponse | null>(null);
  const [roundDebriefError, setRoundDebriefError] = useState("");
  const [roundDebriefBusy, setRoundDebriefBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirmAbandon, setConfirmAbandon] = useState(false);
  const [leaveAfterAbandon, setLeaveAfterAbandon] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [returnTo, setReturnTo] = useState("");
  const [handoffFocus, setHandoffFocus] = useState("");
  const [integrationSecondary, setIntegrationSecondary] = useState("");
  const [integrationLaunchError, setIntegrationLaunchError] = useState("");
  const [activeRoundIntentConflict, setActiveRoundIntentConflict] = useState("");
  const [paceSafetyNotice, setPaceSafetyNotice] = useState("");
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
  const submitRef = useRef<() => void>(() => undefined);
  const debriefRequestRef = useRef("");
  const restoredTimingRef = useRef<{ startedAtEpochMs: number | null; deadlineAtEpochMs: number | null } | null>(null);
  const abandonTriggerRef = useRef<HTMLButtonElement | null>(null);
  const dialogTriggerRef = useRef<HTMLButtonElement | null>(null);
  const abandonDialogRef = useRef<HTMLElement | null>(null);
  const keepPracticingRef = useRef<HTMLButtonElement | null>(null);
  const setupTouchedRef = useRef(false);

  const pace = PACES.find((item) => item.id === paceId) ?? PACES[0];
  const timeAllowanceSeconds = pace.seconds === null
    ? null
    : taskPacket?.estimatedSeconds ?? pace.seconds;
  const completeReadRequired = handoffSubskill === "synthesize" || Boolean(integrationSecondary);
  const score = typeof grade?.score === "number" ? grade.score : 0;
  const mixedTraceRequired = Boolean(taskPacket?.tasks.some((task) => ["trace_point", "point_localization", "trace_region"].includes(task.type)));
  const traceComplete = taskPacket
    ? !mixedTraceRequired || Boolean(traceEvidence)
    : paceId === "emergency" || (traceEvidence?.mode === "point" && Boolean(traceEvidence.point));
  const synthesisTaskComplete = Object.values(sweep).every((value) => value.trim().length > 0)
    && sweep.synthesis.trim().length >= 12
    && selectedConcepts.length > 0;
  const mixedTaskComplete = Boolean(taskPacket?.tasks.length) && taskPacket!.tasks.every((task) => (
    task.required === false || rapidTaskAnswered(task, taskResponses[task.id], traceComplete)
  ));
  const hasAnswer = taskPacket ? mixedTaskComplete : (paceId === "emergency"
    ? selectedConcepts.length === 1
    : synthesisTaskComplete) && traceComplete;
  const activeRapidTask = taskPacket?.tasks[Math.min(activeTaskIndex, Math.max(0, taskPacket.tasks.length - 1))];
  const estimatedRoundMinutes = Math.max(2, Math.ceil(
    sessionLength * (questionDepth === "quick" ? 0.6 : questionDepth === "focused" ? 1.6 : 3.2),
  ));
  const rapidViewerTask: ViewerTaskSpec | undefined = !grade && (activeRapidTask?.type === "trace_point" || activeRapidTask?.type === "point_localization")
    ? {
        mode: "point",
        prompt: activeRapidTask.prompt,
        concept: activeRapidTask.topicId || activeRapidTask.objectiveId || "qrs_complex",
        allowedLeads: taskPacket?.display.leads,
      }
    : !grade && activeRapidTask?.type === "trace_region"
      ? {
          mode: "region",
          prompt: activeRapidTask.prompt,
          concept: activeRapidTask.topicId || activeRapidTask.objectiveId || "st_segment",
          allowedLeads: taskPacket?.display.leads,
        }
      : undefined;
  const completedSweepCount = FRAMEWORK_STEPS.filter((step) => sweep[step.key].trim()).length;
  const activeSweepStep = FRAMEWORK_STEPS[activeSweepIndex] ?? FRAMEWORK_STEPS[0];
  const searchableFindings = useMemo(() => {
    const seen = new Set<string>();
    const values: RapidConceptOption[] = [{ id: "uncertain", label: rapidFindingLabel("uncertain") }];
    for (const group of conceptGroups) {
      for (const concept of group.concepts) {
        if (seen.has(concept.id)) continue;
        seen.add(concept.id);
        values.push(concept);
      }
    }
    return values;
  }, [conceptGroups]);
  const filteredFindings = useMemo(() => {
    const query = normalizeExactFinding(findingSearch);
    const matching = query
      ? searchableFindings.filter((concept) => (
          normalizeExactFinding(concept.id).includes(query)
          || normalizeExactFinding(concept.label).includes(query)
          || normalizeExactFinding(rapidFindingLabel(concept.id)).includes(query)
        ))
      : searchableFindings;
    return matching.slice(0, 8);
  }, [findingSearch, searchableFindings]);
  const chooseDominantFinding = useCallback((concept: RapidConceptOption) => {
    setSelectedConcepts([concept.id]);
    setFindingSearch(rapidFindingLabel(concept.id));
    setFindingMenuOpen(false);
    setFindingActiveIndex(0);
  }, []);

  useEffect(() => {
    setFindingActiveIndex((current) => Math.min(current, Math.max(0, filteredFindings.length - 1)));
  }, [filteredFindings.length]);

  const closeAbandonDialog = useCallback(() => {
    setConfirmAbandon(false);
    setLeaveAfterAbandon("");
    window.requestAnimationFrame(() => (dialogTriggerRef.current ?? abandonTriggerRef.current)?.focus());
  }, []);

  const openAbandonDialog = useCallback((trigger: HTMLButtonElement, destination = "") => {
    dialogTriggerRef.current = trigger;
    setLeaveAfterAbandon(destination);
    setConfirmAbandon(true);
  }, []);

  useEffect(() => {
    if (!confirmAbandon) return;
    const focusFrame = window.requestAnimationFrame(() => keepPracticingRef.current?.focus());
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeAbandonDialog();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = [...(abandonDialogRef.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ) ?? [])];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable.at(-1) ?? first;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [closeAbandonDialog, confirmAbandon]);

  const applyRoundPayload = useCallback((payload: RapidRoundPayload, restoreLocalDraft = false) => {
    if (payload.rhythmSupplement) setRhythmSupplement(payload.rhythmSupplement);
    const round = payload.round;
    if (!round) return false;
    setRoundId(round.roundId);
    setRoundStatus(round.status);
    setPaceId(round.pace);
    if (round.practiceMode) setPracticeMode(round.practiceMode);
    if (round.questionDepth) setQuestionDepth(round.questionDepth);
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
      setTaskPacket(null);
      setTaskResponses({});
      return true;
    }
    setCaseSummary(current.case);
    setPacket(current.packet);
    setTaskPacket(current.taskPacket ?? null);
    if (current.kind === "pending") {
      setView("runner");
      setCaseIndex(round.position);
      setGrade(null);
      setAiViewerActions([]);
      setTraceReceipt("");
      setHandoffReceipt("");
      setTaskResponses({});
      setActiveTaskIndex(0);
      submittingRef.current = false;
      const saved = restoreLocalDraft ? readRapidSession(identityKey) : null;
      const sameDraft = saved?.roundId === round.roundId && saved.currentCaseRef === current.case.caseId;
      setTaskResponses(sameDraft ? saved.taskResponses : {});
      setActiveTaskIndex(sameDraft ? saved.activeTaskIndex : 0);
      const restoredSweep = sameDraft ? saved.sweep : EMPTY_SWEEP;
      setSweep(restoredSweep);
      setSelectedConcepts(sameDraft ? saved.selectedConcepts : []);
      setFindingSearch(sameDraft && saved.selectedConcepts[0] ? rapidFindingLabel(saved.selectedConcepts[0]) : "");
      setAnswerStage("findings");
      setActiveSweepIndex(firstIncompleteSweepIndex(restoredSweep));
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
    const storedTaskResponses = answer.response.taskResponses;
    setTaskResponses(isRecord(storedTaskResponses)
      ? storedTaskResponses as Record<string, RapidTaskResponse>
      : {});
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
    if (preferencesLoading) return;
    let active = true;
    const launchIntent = parseRapidLaunchIntent(window.location.search);
    setSessionReady(false);
    setError(null);
    setActiveRoundIntentConflict("");
    api.activeRapidRound()
      .then((payload) => {
        if (!active) return;
        if (payload.rhythmSupplement) setRhythmSupplement(payload.rhythmSupplement);
        if (payload.round) {
          const requestedSubskill = launchIntent.subskill || null;
          const requestedReceipt = launchIntent.receiptConcept || null;
          const exactHandoffMismatch = Boolean(
            launchIntent.focus
            && (
              payload.round.focusConcept !== launchIntent.focus
              || (requestedSubskill && payload.round.focusSubskill !== requestedSubskill)
              || (requestedReceipt && payload.round.receiptConcept !== requestedReceipt)
            )
          );
          if (exactHandoffMismatch) {
            const savedTarget = payload.round.focusConcept
              ? conceptLabel(payload.round.focusConcept)
              : "mixed ECG practice";
            setActiveRoundIntentConflict(
              `Your saved Rapid round for ${savedTarget} was resumed unchanged. The recommended ${conceptLabel(launchIntent.focus)} check was not substituted into it. Finish or abandon the saved round, then open that recommendation again.`,
            );
          }
          applyRoundPayload(payload, true);
          return;
        }
        // Browser storage is now only a setup preference/draft cache. It can no
        // longer manufacture or advance an assessment without a server round.
        const saved = readRapidSession(identityKey);
        const completeReadDefaultPace: PaceId | null = launchIntent.completeReadRequired ? "untimed" : null;
        const explicitPace = launchIntent.pace ?? completeReadDefaultPace;
        const preferredPace = launchIntent.completeReadRequired && preferences?.rapidPace === "emergency"
          ? "ward"
          : preferences?.rapidPace ?? null;
        const preferredLength = preferences?.defaultSessionLength ?? null;
        if (!launchIntent.requestedPace && launchIntent.completeReadRequired && preferences?.rapidPace === "emergency") {
          setPaceSafetyNotice("Your saved Speed round preference was changed to Standard timer because this handoff requires a complete interpretation.");
        }
        if (saved?.view === "complete") {
          setRoundId(saved.roundId ?? "");
          setRoundStatus("complete");
          setPaceId(saved.paceId);
          setSessionLength(saved.sessionLength);
          // Completed rounds are intentionally absent from `/active`. Retain
          // their server id and restore from the ownership-gated result ledger;
          // neither the browser's bounded tail nor its count is authoritative.
          return api.rapidResults(saved.roundId!, 0, 5000)
            .then((response) => {
              if (!active) return;
              setServerResultCount(response.total);
              setResults(response.results.map(caseResultFromRecord));
              setView("complete");
            })
            .catch(() => {
              if (!active) return;
              // The bounded browser tail is never authoritative, but it is a
              // useful read-only recovery view. Preserve it instead of erasing
              // a completed learner experience when the ledger is briefly
              // unreachable; metrics and AI debrief remain explicitly partial.
              setResults(saved.results);
              setServerResultCount(saved.sessionLength);
              setView("complete");
              setRoundDebriefError("Showing a cached recent-results preview. Reconnect and reload to restore the authoritative full round review.");
            });
        } else if (saved?.view === "setup") {
          setPaceId(explicitPace ?? saved.paceId);
          setPracticeMode(launchIntent.practiceMode === "emergency"
            ? payload.rhythmSupplement?.available === true ? "emergency" : "adaptive"
            : launchIntent.practiceMode ?? (
              saved.practiceMode === "emergency" && payload.rhythmSupplement?.available !== true
                ? "adaptive"
                : saved.practiceMode
            ));
          setQuestionDepth(launchIntent.completeReadRequired ? "complete" : saved.questionDepth);
          setSessionLength(learnerScaleRapidLength(launchIntent.suggestedLength ?? saved.sessionLength));
        } else {
          setView("setup");
          if (!setupTouchedRef.current) {
            if (launchIntent.practiceMode === "emergency") {
              setPracticeMode(payload.rhythmSupplement?.available === true ? "emergency" : "adaptive");
            } else if (launchIntent.practiceMode) {
              setPracticeMode(launchIntent.practiceMode);
            }
            if (explicitPace ?? preferredPace) setPaceId((explicitPace ?? preferredPace) as PaceId);
            if (launchIntent.suggestedLength !== null || preferredLength !== null) {
              setSessionLength(learnerScaleRapidLength(launchIntent.suggestedLength ?? preferredLength ?? 5));
            }
          }
        }
      })
      .catch(() => {
        if (!active) return;
        if (launchIntent.practiceMode === "emergency") setPracticeMode("adaptive");
        const saved = readRapidSession(identityKey);
        if (saved?.view === "complete" && saved.roundId) {
          setRoundId(saved.roundId);
          setRoundStatus("complete");
          setPaceId(saved.paceId);
          setSessionLength(saved.sessionLength);
          setResults(saved.results);
          setServerResultCount(saved.sessionLength);
          setView("complete");
          setRoundDebriefError("Showing a cached recent-results preview. Reconnect and reload to restore the authoritative full round review.");
        } else if (saved?.view === "setup") {
          const explicitPace = launchIntent.pace ?? (launchIntent.completeReadRequired ? "untimed" : null);
          setPaceId(explicitPace ?? saved.paceId);
          // The active-round request failed, so supplement availability is not
          // authoritative. Fail closed instead of restoring an emergency drill
          // that may have no reviewed rhythm source at runtime.
          setPracticeMode(saved.practiceMode === "emergency" ? "adaptive" : saved.practiceMode);
          setQuestionDepth(launchIntent.completeReadRequired ? "complete" : saved.questionDepth);
          setSessionLength(learnerScaleRapidLength(launchIntent.suggestedLength ?? saved.sessionLength));
        } else if (!setupTouchedRef.current) {
          const preferredPace = launchIntent.completeReadRequired && preferences?.rapidPace === "emergency"
            ? "ward"
            : preferences?.rapidPace ?? null;
          const explicitPace = launchIntent.pace ?? (launchIntent.completeReadRequired ? "untimed" : null);
          if (explicitPace ?? preferredPace) setPaceId((explicitPace ?? preferredPace) as PaceId);
          setSessionLength(learnerScaleRapidLength(launchIntent.suggestedLength ?? preferences?.defaultSessionLength ?? 5));
        }
        if (saved?.view !== "complete") {
          setView("setup");
          setError("Rapid practice is temporarily unavailable. Try again once the connection is restored.");
        }
      })
      .finally(() => {
        if (active) setSessionReady(true);
      });
    return () => { active = false; };
  }, [identityKey, applyRoundPayload, preferences, preferencesLoading, sessionRetryKey]);

  useEffect(() => {
    if (!sessionReady) return;
    // Keep the prior draft while the next server-owned capability is in flight.
    if (view === "runner" && !caseSummary) return;
    const snapshot: RapidSessionSnapshot = {
      version: 4,
      ownerKey: identityKey,
      roundId: roundId || undefined,
      context: window.location.search,
      view,
      paceId,
      practiceMode,
      questionDepth,
      sessionLength,
      caseIndex,
      currentCaseRef: caseSummary?.caseId ?? null,
      sweep,
      selectedConcepts,
      confidence,
      grade,
      aiViewerActions,
      traceEvidence,
      taskResponses,
      activeTaskIndex,
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
  }, [sessionReady, identityKey, roundId, view, paceId, practiceMode, questionDepth, sessionLength, caseIndex, caseSummary, sweep, selectedConcepts, confidence, grade, aiViewerActions, traceEvidence, taskResponses, activeTaskIndex, traceReceipt, handoffReceipt, results, startedAtEpochMs, deadlineAtEpochMs]);

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
      .then(({ applicationCoverage }) => {
        if (!active) return;
        const preferredLanes = ["clinic", "ward", "ed"] as const;
        const destinations = new Map<string, { lane: "clinic" | "ward" | "ed" }>();
        Object.entries(applicationCoverage ?? {}).forEach(([concept, lanes]) => {
          const lane = preferredLanes.find((candidate) => {
            const depth = lanes[candidate];
            return Boolean(depth && depth.items > 0 && depth.distinctEcgs > 0);
          });
          if (lane) destinations.set(concept, { lane });
        });
        setClinicalDestinations(destinations);
      })
      .catch(() => {
        // A missing coverage contract must suppress the handoff, not advertise
        // a case family from a stale client-side assumption.
        if (active) setClinicalDestinations(new Map());
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const intent = parseRapidLaunchIntent(window.location.search);
    setReturnTo(intent.returnTo);
    setHandoffFocus(intent.focus);
    setIntegrationSecondary(intent.secondaryConcept);
    setIntegrationLaunchError(intent.secondaryConceptInvalid
      ? "This integration link does not name one valid, distinct secondary ECG concept. No substitute set will be started."
      : "");
    setHandoffReceiptConcept(intent.receiptConcept);
    setPaceSafetyNotice(intent.paceAdjustedForCompleteRead
      ? "Speed round was changed to Standard timer because this handoff requires a complete interpretation."
      : "");
    if (intent.subskill) {
      setHandoffSubskill(intent.subskill);
    }
    if (intent.practiceMode) setPracticeMode(intent.practiceMode);
    if (intent.completeReadRequired) setQuestionDepth("complete");
    if (intent.pace) setPaceId(intent.pace);
    else if (intent.completeReadRequired) setPaceId("untimed");
  }, []);

  useEffect(() => {
    if (!catalogLoaded) return;
    const resolution = handoffFocus ? resolveHandoffTarget(handoffFocus, rapidAvailableConcepts) : null;
    setHandoffResolution(resolution);
    setHandoffUnavailable(handoffFocus && !resolution
      ? `No suitable real ECG is currently available to check ${conceptLabel(handoffFocus)}. An unrelated tracing will not be substituted.`
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
    setTaskPacket(null);
    setTaskResponses({});
    setActiveTaskIndex(0);
    setPacket(null);
    setCaseSummary(null);
    setSweep(EMPTY_SWEEP);
    setSelectedConcepts([]);
    setFindingSearch("");
    setAnswerStage("findings");
    setActiveSweepIndex(0);
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
    if (integrationLaunchError) {
      setError(integrationLaunchError);
      return;
    }
    if (handoffFocus && !handoffResolution) {
      setError(handoffUnavailable || "This guided target has no validated Rapid case family.");
      return;
    }
    if (integrationSecondary && !rapidAvailableConcepts.has(integrationSecondary)) {
      setError(`No suitable real ECG is currently available for ${conceptLabel(integrationSecondary)}. The integration set was not started.`);
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
        learnerId: identityKey,
        contractVersion: "mixed-v2",
        practiceMode,
        questionDepth,
        pace: paceId,
        length: sessionLength,
        focusConcept: handoffResolution?.caseConcept ?? null,
        secondaryConcept: integrationSecondary || null,
        focusSubskill: handoffSubskill || null,
        contextKey: window.location.search,
        exclusions: [],
      });
      const nextRoundId = started.round?.roundId;
      if (!nextRoundId) throw new Error("TRACE could not create a Rapid round.");
      setRoundId(nextRoundId);
      await loadCase(nextRoundId);
    } catch (err) {
      setView("setup");
      setError(err instanceof Error ? err.message : "Could not start a Rapid round.");
    } finally {
      setBusy(false);
    }
  }, [identityKey, practiceMode, questionDepth, paceId, sessionLength, handoffFocus, handoffResolution, handoffSubskill, handoffUnavailable, integrationSecondary, integrationLaunchError, rapidAvailableConcepts, loadCase]);

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
          if (timeAllowanceSeconds !== null && authoritativeDeadline !== null) {
            const secondsLeft = Math.max(0, (authoritativeDeadline - nowEpochMs) / 1000);
            deadlineRef.current = performance.now() + secondsLeft * 1000;
            setRemaining(secondsLeft);
            if (secondsLeft <= 0) {
              setClockRunning(false);
              window.setTimeout(() => submitRef.current(), 0);
            } else {
              setClockRunning(true);
            }
          } else {
            setRemaining(null);
            setClockRunning(false);
          }
        }).catch((err) => {
          activatedCaseRef.current = "";
          setError(err instanceof Error ? err.message : "Could not start the Rapid timer.");
        });
        clockStartFrameRef.current = null;
      });
    });
  }, [grade, timeAllowanceSeconds, roundId, caseSummary]);

  useEffect(() => () => {
    if (clockStartFrameRef.current !== null) window.cancelAnimationFrame(clockStartFrameRef.current);
  }, []);

  const submit = useCallback(
    async () => {
      if (!roundId || !caseSummary || grade || submittingRef.current) return;
      submittingRef.current = true;
      setClockRunning(false);
      setBusy(true);
      setError(null);
      try {
        const submittedTaskResponses: Record<string, unknown> = taskPacket ? {} : { ...taskResponses };
        if (taskPacket) {
          for (const task of taskPacket.tasks) {
            if (["trace_point", "point_localization", "trace_region"].includes(task.type)) {
              if (traceEvidence?.mode === "point") submittedTaskResponses[task.id] = { point: traceEvidence.point };
              if (traceEvidence?.mode === "region") submittedTaskResponses[task.id] = { roi: traceEvidence.roi };
              continue;
            }
            const value = taskResponses[task.id];
            if (value === undefined) continue;
            if ((task.type === "numeric" || task.type === "numeric_fill_in") && typeof value === "string") {
              const numericValue = Number(value);
              if (Number.isFinite(numericValue)) submittedTaskResponses[task.id] = numericValue;
              continue;
            }
            submittedTaskResponses[task.id] = value;
          }
        }
        const response = await api.submitRapidCase(roundId, {
          caseId: caseSummary.caseId,
          taskResponses: submittedTaskResponses,
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
          freeTextAnswer: taskPacket
            ? Object.values(taskResponses).map((value) => typeof value === "string" ? value : "").filter(Boolean).join(" · ")
            : sweep.synthesis,
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
            ? `Progress saved: ${learningSkillLabel(handoffSubskill)} checked for ${conceptLabel(requestedReceipt)}${exactReceipt.correct === false ? "; this miss will guide the next review" : ""}.`
            : `This attempt did not update ${conceptLabel(requestedReceipt)} yet. Complete the highlighted ${learningSkillLabel(handoffSubskill)} task on the next ECG.`);
        }
      } catch (err) {
        submittingRef.current = false;
        setError(err instanceof Error ? err.message : "Could not grade this ECG.");
      } finally {
        setBusy(false);
      }
    },
    [roundId, caseSummary, grade, taskPacket, taskResponses, sweep, selectedConcepts, confidence, handoffFocus, handoffSubskill, handoffResolution, handoffReceiptConcept, results.length, traceEvidence, applyRoundPayload],
  );

  submitRef.current = submit;

  useEffect(() => {
    if (!clockRunning || timeAllowanceSeconds === null) return;
    const timer = window.setInterval(() => {
      const next = Math.max(0, (deadlineRef.current - performance.now()) / 1000);
      setRemaining(next);
      if (next <= 0) {
        window.clearInterval(timer);
        setClockRunning(false);
        submitRef.current();
      }
    }, 100);
    return () => window.clearInterval(timer);
  }, [clockRunning, timeAllowanceSeconds]);

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

  async function abandonRound() {
    if (!roundId || roundStatus !== "active" || busy) return;
    const destination = leaveAfterAbandon;
    const resumeClockOnFailure = clockRunning;
    submittingRef.current = true;
    setClockRunning(false);
    setBusy(true);
    setError(null);
    if (clockStartFrameRef.current !== null) {
      window.cancelAnimationFrame(clockStartFrameRef.current);
      clockStartFrameRef.current = null;
    }
    try {
      const abandoned = await api.abandonRapidRound(roundId);
      if (abandoned.round?.status !== "abandoned") {
        throw new Error("TRACE could not confirm that this Rapid round was abandoned.");
      }
      window.sessionStorage.removeItem(rapidSessionKey(identityKey));
      setRoundId("");
      setRoundStatus("active");
      setCaseIndex(0);
      setCaseSummary(null);
      setPacket(null);
      setSweep(EMPTY_SWEEP);
      setSelectedConcepts([]);
      setFindingSearch("");
      setConfidence(3);
      setGrade(null);
      setAiViewerActions([]);
      setTraceEvidence(null);
      setTaskPacket(null);
      setTaskResponses({});
      setActiveTaskIndex(0);
      setTraceReceipt("");
      setHandoffReceipt("");
      setResults([]);
      setServerResultCount(0);
      setRoundDebrief(null);
      setRoundDebriefError("");
      setStartedAtEpochMs(null);
      setDeadlineAtEpochMs(null);
      setRemaining(pace.seconds);
      setConfirmAbandon(false);
      setView("setup");
      submittingRef.current = false;
      if (destination) window.location.assign(destination);
    } catch (err) {
      submittingRef.current = Boolean(grade);
      setConfirmAbandon(false);
      setError(err instanceof Error ? err.message : "Could not abandon this Rapid round.");
      if (resumeClockOnFailure && !grade) setClockRunning(true);
    } finally {
      setBusy(false);
    }
  }

  function toggleConcept(concept: string) {
    if (grade) return;
    if (paceId === "emergency") {
      setSelectedConcepts([concept]);
      setFindingSearch(rapidFindingLabel(concept));
      return;
    }
    setSelectedConcepts((current) => {
      if (concept === "uncertain") return current.includes(concept) ? [] : [concept];
      const withoutUncertainty = current.filter((item) => item !== "uncertain");
      return withoutUncertainty.includes(concept)
        ? withoutUncertainty.filter((item) => item !== concept)
        : [...withoutUncertainty, concept];
    });
  }

  const sessionAverage = useMemo(
    () => (results.length ? results.reduce((sum, item) => sum + item.score, 0) / results.length : 0),
    [results],
  );
  const averageResponse = useMemo(() => {
    const values = results.flatMap((item) => (item.responseMs === null ? [] : [item.responseMs]));
    return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
  }, [results]);
  const resultLedgerTotal = Math.max(serverResultCount, results.length);
  const partialResultLedger = view === "complete" && resultLedgerTotal > results.length;
  const roundTarget = useMemo(() => debriefTarget(results), [results]);
  const roundTargetHref = useMemo(
    () => roundTarget ? rapidDebriefPracticeHref(roundTarget) : null,
    [roundTarget],
  );
  const clinicalHref = useMemo(
    () => rapidClinicalHandoffHref(results, clinicalDestinations),
    [results, clinicalDestinations],
  );
  const crossConceptBridge = useMemo(() => {
    const missed = frequencyRank(results.flatMap((result) => [
      ...result.missedObjectives,
      ...result.competencyOutcomes
        .filter((outcome) => !outcome.formativeOnly && !outcome.correct)
        .map((outcome) => outcome.objectiveId),
    ]));
    const correct = frequencyRank(results.flatMap((result) => result.correctObjectives));
    if (missed[0] && correct[0] && missed[0] !== correct[0]) {
      return `Connect ${conceptLabel(correct[0])} to ${conceptLabel(missed[0])}: use the feature you recognized as the anchor, then state the additional discriminator the missed diagnosis requires.`;
    }
    if (missed.length > 1) {
      return `Compare ${conceptLabel(missed[0])} with ${conceptLabel(missed[1])} side by side; name one shared feature and one decisive separator before looking at another label.`;
    }
    if (roundTarget) {
      return `Carry ${conceptLabel(roundTarget.objectiveId)} through three levels: recognize the pattern, localize or measure its evidence, then explain what changes in the clinical context.`;
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
    api.tutorMessage({
      mode: "practice",
      caseId: null,
      message: "Debrief this completed Rapid ECG round from its server-owned record.",
      viewerState: { activity: "rapid_round_debrief" },
      rapidRoundContext: {
        roundId,
        answerCount: results.length,
        version: "rapid-round-debrief-v1",
      },
    })
      .then(setRoundDebrief)
      .catch(() => setRoundDebriefError(deterministicDebriefFallback(results)))
      .finally(() => setRoundDebriefBusy(false));
  }, [view, results, roundId, serverResultCount]);

  if (!sessionReady) {
    return <div className="page rapid-page"><section className="panel pad" role="status" aria-live="polite" aria-busy="true">Restoring your Rapid round…</section></div>;
  }

  if (view === "setup") {
    return (
      <div className="page rapid-page rapid-setup">
        <header className="page-header rapid-header">
          <div>
            <p className="eyebrow rapid-eyebrow">Rapid practice</p>
            <h1><Timer size={24} aria-hidden="true" /> Choose how you want to read</h1>
            <p className="muted rapid-intro">
              Build speed without turning every tracing into the same checklist. Each ECG asks only
              the questions that its learning goal can support.
            </p>
          </div>
          {returnTo ? <Link className="button subtle" href={returnTo}><ArrowLeft size={16} /> {learningReturnLabel(returnTo)}</Link> : null}
        </header>

        {returnTo && !activeRoundIntentConflict ? <div className="selection-note">This round starts with <strong>{conceptLabel(handoffFocus)} · {handoffSubskill ? learningSkillLabel(handoffSubskill) : "focused check"}</strong>. {handoffResolution ? integrationSecondary ? <>This set reserves two distinct unannounced ECGs: one for <strong>{conceptLabel(handoffResolution.caseConcept)}</strong> and one for <strong>{conceptLabel(integrationSecondary)}</strong>. Later ECGs mix in related patterns.</> : <>The first ECG focuses on <strong>{conceptLabel(handoffResolution.caseConcept)}</strong>; later ECGs mix in related patterns.</> : "An unrelated ECG will not be substituted."}</div> : null}
        {activeRoundIntentConflict ? <div className="warning" role="alert">{activeRoundIntentConflict}</div> : null}
        {integrationLaunchError ? <div className="warning" role="alert">{integrationLaunchError}</div> : null}
        {paceSafetyNotice ? <div className="selection-note" role="status"><Clock3 size={15} aria-hidden="true" /> {paceSafetyNotice}</div> : null}
        {handoffUnavailable ? <div className="warning" role="alert">{handoffUnavailable}</div> : null}
        {error && error !== integrationLaunchError && error !== handoffUnavailable ? (
          <div className="warning mode-recovery-notice" role="alert">
            <span>{error}</span>
            {error.startsWith("Rapid practice is temporarily unavailable") || error.startsWith("The completed Rapid round") ? (
              <button className="button subtle small" type="button" onClick={() => setSessionRetryKey((value) => value + 1)}>
                <RotateCcw size={15} aria-hidden="true" /> Retry saved round check
              </button>
            ) : null}
          </div>
        ) : null}

        <section className="rapid-setup-shell">
          <div className="panel pad rapid-setup-panel">
            <fieldset className="rapid-setup-group">
              <legend>Practice plan</legend>
              <p>Choose how the next ECGs should be selected.</p>
              <div className="rapid-plan-grid">
                <button
                  type="button"
                  className={practiceMode === "adaptive" ? "selected" : ""}
                  aria-pressed={practiceMode === "adaptive"}
                  onClick={() => { setupTouchedRef.current = true; setPracticeMode("adaptive"); }}
                >
                  <BrainCircuit size={20} aria-hidden="true" />
                  <span><strong>Adaptive practice</strong><small>Prioritizes due skills and recent misses, with retention checks mixed in.</small></span>
                  <em>Recommended</em>
                </button>
                <button
                  type="button"
                  className={practiceMode === "mixed" ? "selected" : ""}
                  aria-pressed={practiceMode === "mixed"}
                  onClick={() => { setupTouchedRef.current = true; setPracticeMode("mixed"); }}
                >
                  <Layers3 size={20} aria-hidden="true" />
                  <span><strong>Mixed practice</strong><small>Balanced variety across rhythms, intervals, conduction, axis, and ST–T patterns.</small></span>
                </button>
                {rhythmSupplement.available && (
                  !handoffFocus
                  || RAPID_EMERGENCY_RHYTHM_CONCEPTS.includes(
                    handoffFocus as (typeof RAPID_EMERGENCY_RHYTHM_CONCEPTS)[number],
                  )
                ) ? (
                  <button
                    type="button"
                    className={practiceMode === "emergency" ? "selected" : ""}
                    aria-pressed={practiceMode === "emergency"}
                    onClick={() => {
                      setupTouchedRef.current = true;
                      setPracticeMode("emergency");
                      if (questionDepth === "complete") setQuestionDepth("focused");
                    }}
                  >
                    <Siren size={20} aria-hidden="true" />
                    <span>
                      <strong>Emergency rhythms</strong>
                      <small>Fast single-lead ventricular rhythm calls, followed by clearly separated 2025 AHA simulation context.</small>
                    </span>
                  </button>
                ) : null}
              </div>
            </fieldset>

            {practiceMode === "emergency" ? (
              <aside className="selection-note" role="note">
                <ShieldCheck size={15} aria-hidden="true" />
                <span><strong>Evidence boundary:</strong> the strip tests rhythm recognition. Pulse, stability, and the action pathway come only from the separately written scenario; management questions are formative.</span>
              </aside>
            ) : null}

            <fieldset className="rapid-setup-group">
              <legend>How deep should each read go?</legend>
              <p>The tracing determines the exact question type. Not every ECG needs a complete report.</p>
              <div className="rapid-depth-grid">
                {(practiceMode === "emergency" ? ([
                  ["quick", "Rhythm call", "One concise rhythm identification", Zap],
                  ["focused", "Rhythm + next step", "Recognition plus one separately contextualized question", ScanSearch],
                  ["complete", "Rhythm + evidence limits", "Three linked recognition, context, and uncertainty checks", ListChecks],
                ] as const) : ([
                  ["quick", "Quick recognition", "One focused call", Zap],
                  ["focused", "Focused read", "One to three linked questions", ScanSearch],
                  ["complete", "Complete interpretation", "A compact prioritized report", ListChecks],
                ] as const)).map(([id, title, detail, Icon]) => {
                  const unavailable = completeReadRequired && id !== "complete";
                  return (
                    <button
                      type="button"
                      key={id}
                      disabled={unavailable}
                      className={`${questionDepth === id ? "selected" : ""}${unavailable ? " unavailable" : ""}`}
                      aria-pressed={questionDepth === id}
                      onClick={() => {
                        setupTouchedRef.current = true;
                        setQuestionDepth(id);
                        if (id === "complete" && paceId === "emergency" && practiceMode !== "emergency") setPaceId("ward");
                      }}
                    >
                      <Icon size={20} aria-hidden="true" />
                      <span><strong>{title}</strong><small>{unavailable ? "This handoff requires a complete read." : detail}</small></span>
                    </button>
                  );
                })}
              </div>
            </fieldset>

            <fieldset className="rapid-setup-group rapid-timing-group">
              <legend>Timing</legend>
              <div className="rapid-timing-options">
                {PACES.map((item) => {
                  const Icon = item.icon;
                  const unavailable = (
                    completeReadRequired
                    || (questionDepth === "complete" && practiceMode !== "emergency")
                  ) && item.id === "emergency";
                  return (
                    <button
                      key={item.id}
                      type="button"
                      disabled={unavailable}
                      className={`${paceId === item.id ? "selected" : ""}${unavailable ? " unavailable" : ""}`}
                      aria-pressed={paceId === item.id}
                      title={item.detail}
                      onClick={() => { setupTouchedRef.current = true; setPaceId(item.id); setPaceSafetyNotice(""); }}
                    >
                      <Icon size={17} aria-hidden="true" /> {item.title}
                    </button>
                  );
                })}
              </div>
            </fieldset>

            <fieldset className="rapid-setup-group rapid-length-group">
              <legend>Round length</legend>
              <div className="rapid-length-options" aria-label="Rapid round length">
                {RAPID_VISIBLE_SESSION_LENGTHS.map((length) => (
                  <button
                    type="button"
                    key={length}
                    className={sessionLength === length ? "selected" : ""}
                    aria-pressed={sessionLength === length}
                    onClick={() => { setupTouchedRef.current = true; setSessionLength(length); }}
                  >
                    <strong>{length}</strong><span>ECGs</span>
                  </button>
                ))}
              </div>
              <p>No repeats within a round. You can pause safely between tracings.</p>
            </fieldset>
          </div>

          <aside className="panel pad rapid-round-preview" aria-label="Round preview">
            <p className="eyebrow">This round</p>
            <h2>{practiceMode === "adaptive"
              ? "Built around your next best reps"
              : practiceMode === "emergency"
                ? "High-risk rhythms, one decision at a time"
                : "A broad, balanced mix"}</h2>
            <div className="rapid-preview-count"><strong>{sessionLength}</strong><span>ECGs</span></div>
            <ul>
              {practiceMode === "adaptive" ? (
                <>
                  <li><BrainCircuit size={16} aria-hidden="true" /><span><strong>Current priorities</strong>Recent misses and due skills lead the set.</span></li>
                  <li><ShieldCheck size={16} aria-hidden="true" /><span><strong>Retention checks</strong>Mastered concepts stay active without dominating.</span></li>
                  <li><GitBranch size={16} aria-hidden="true" /><span><strong>Transfer</strong>Related look-alikes test whether the idea generalizes.</span></li>
                </>
              ) : practiceMode === "emergency" ? (
                <>
                  <li><Siren size={16} aria-hidden="true" /><span><strong>Single-lead recognition</strong>Source-author-labelled VF, ventricular flutter, VT, and polymorphic VT fragments.</span></li>
                  <li><GitBranch size={16} aria-hidden="true" /><span><strong>Source separation</strong>Patient state is stated explicitly and never inferred from the strip.</span></li>
                  <li><ShieldCheck size={16} aria-hidden="true" /><span><strong>Guideline context</strong>2025 AHA pathway questions are formative and version-labelled.</span></li>
                </>
              ) : (
                <>
                  <li><Layers3 size={16} aria-hidden="true" /><span><strong>Topic breadth</strong>Rhythm, conduction, intervals, axis, and ST–T findings.</span></li>
                  <li><ListChecks size={16} aria-hidden="true" /><span><strong>Question variety</strong>Typed calls, choices, measurements, and trace tasks.</span></li>
                  <li><ShieldCheck size={16} aria-hidden="true" /><span><strong>Blinded answers</strong>Feedback stays hidden until the ECG is submitted.</span></li>
                </>
              )}
            </ul>
            <div className="rapid-preview-summary">
              <span>{questionDepth === "quick" ? "Quick recognition" : questionDepth === "focused" ? "Focused read" : "Complete interpretation"}</span>
              <span>{pace.title}</span>
              <span>About {estimatedRoundMinutes} min</span>
            </div>
            <button
              className="button primary rapid-start"
              type="button"
              onClick={() => void startSession()}
              disabled={!catalogLoaded
                || Boolean(handoffUnavailable)
                || Boolean(handoffFocus && !handoffResolution)
                || (practiceMode === "emergency" && !rhythmSupplement.available)}
            >
              Start rapid set <ArrowRight size={16} aria-hidden="true" />
            </button>
          </aside>
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
            <h1><CheckCircle2 size={24} aria-hidden="true" /> Rapid round review</h1>
          </div>
        </header>
        <section className="panel pad rapid-summary">
          {partialResultLedger ? (
            <div className="warning rapid-ledger-recovery" role="status">
              <AlertTriangle size={17} aria-hidden="true" />
              <div>
                <strong>Cached review · full ledger temporarily unavailable</strong>
                <span>These are your most recent {results.length.toLocaleString()} saved ECG results. Scores and coaching below are a partial preview until your full learning record reconnects.</span>
              </div>
            </div>
          ) : null}
          <div className="metric-row rapid-summary-metrics">
            <div className="metric rapid-summary-metric"><span className="metric-label">{partialResultLedger ? "Cached average" : "Average score"}</span><strong>{Math.round(sessionAverage * 100)}%</strong></div>
            <div className="metric rapid-summary-metric"><span className="metric-label">Completed</span><strong>{resultLedgerTotal}/{sessionLength}</strong></div>
            <div className="metric rapid-summary-metric"><span className="metric-label">Average response</span><strong>{averageResponse === null ? "Untimed" : `${(averageResponse / 1000).toFixed(1)}s`}</strong></div>
            <div className="metric rapid-summary-metric"><span className="metric-label">{partialResultLedger ? "Cached timeouts" : "Timed out"}</span><strong>{results.filter((item) => item.timedOut).length}</strong></div>
          </div>
          {results.length > 50 ? <p className="muted">Showing the most recent 50 of {resultLedgerTotal.toLocaleString()} ECGs. Your full round remains saved.</p> : null}
          <div className="list rapid-result-list">
            {results.slice(-50).map((item, index, recentResults) => (
              <div className="list-item rapid-result-row" key={`${item.caseId}-${index}`}>
                <div>
                  <strong>ECG {resultLedgerTotal - recentResults.length + index + 1}</strong>
                  <span className="muted rapid-result-meta">
                    {Math.round(item.score * 100)}%{item.timedOut ? " · time expired" : item.responseMs ? ` · ${(item.responseMs / 1000).toFixed(1)}s` : ""}
                  </span>
                </div>
                <div className="rapid-result-learning">
                  {item.competencyOutcomes.some((outcome) => !outcome.formativeOnly && !outcome.correct)
                    ? <span className="review">Review {item.competencyOutcomes
                        .filter((outcome) => !outcome.formativeOnly && !outcome.correct)
                        .slice(0, 2)
                        .map((outcome) => `${conceptLabel(outcome.objectiveId)} · ${learningSkillLabel(outcome.subskill)}`)
                        .join(" / ")}</span>
                    : item.missedObjectives.length
                      ? <span className="review">Review {item.missedObjectives.slice(0, 2).map(conceptLabel).join(" · ")}</span>
                    : item.overcalledObjectives.length
                      ? <span className="review">Recheck {item.overcalledObjectives.slice(0, 2).map(conceptLabel).join(" · ")}</span>
                      : <span className="strong">Targets met</span>}
                </div>
              </div>
            ))}
          </div>
          <section className="rapid-round-coach" aria-live="polite" aria-busy={roundDebriefBusy}>
            <div className="rapid-coach-kicker"><Sparkles size={15} aria-hidden="true" /> AI reflection grounded in this round</div>
            <h2>Choose the next useful move</h2>
            {roundDebriefBusy ? <p className="muted">Reviewing this round…</p> : (
              <>
                <p>{roundDebrief?.tutorMessage || roundDebrief?.feedback || roundDebriefError || deterministicDebriefFallback(results)}</p>
                {roundDebrief?.socraticQuestion ? <p className="rapid-coach-question"><strong>Think next:</strong> {roundDebrief.socraticQuestion}</p> : null}
              </>
            )}
            <div className="rapid-cross-concept">
              <GitBranch size={17} aria-hidden="true" />
              <div><strong>Connect this skill</strong><p>{crossConceptBridge}</p></div>
            </div>
            <div className="actions rapid-handoffs">
              {roundTarget && roundTargetHref ? (
                <Link className="button primary" href={roundTargetHref}>
                  {roundTargetHref.startsWith("/rapid?")
                    ? `Practice ${conceptLabel(roundTarget.objectiveId)} in Emergency Rapid`
                    : `Train ${conceptLabel(roundTarget.objectiveId)} · ${learningSkillLabel(roundTarget.subskill)}`} <ArrowRight size={15} aria-hidden="true" />
                </Link>
              ) : null}
              {clinicalHref ? (
                <Link className="button" href={clinicalHref}>
                  Apply in a clinical case <ArrowRight size={15} aria-hidden="true" />
                </Link>
              ) : null}
            </div>
          </section>
          <div className="actions rapid-complete-actions">
            <Link className="button primary" href="/home?panel=activity">
              Review ECGs &amp; answers <ArrowRight size={16} aria-hidden="true" />
            </Link>
            <button className="button rapid-restart" type="button" onClick={() => void startSession()}>
              <RotateCcw size={16} aria-hidden="true" /> Repeat this round
            </button>
            <button className="button rapid-new-setup" type="button" onClick={() => setView("setup")}>Change setup</button>
            {returnTo ? <Link className="button" href={returnTo}><ArrowLeft size={16} /> {learningReturnLabel(returnTo)}</Link> : null}
          </div>
        </section>
      </div>
    );
  }

  const correct = stringList(grade?.correctObjectives);
  const missed = stringList(grade?.missedObjectives);
  const overcalled = stringList(grade?.overcalledObjectives);
  const timerPercent = timeAllowanceSeconds && remaining !== null ? Math.max(0, Math.min(100, (remaining / timeAllowanceSeconds) * 100)) : 100;
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

  const responsePhase = grade ? "feedback" : "response";

  return (
    <LearningWorkspaceShell
      className={`page rapid-page rapid-runner rapid-${paceId}`}
      phase={responsePhase}
      tutorResetKey={`${caseSummary?.caseId ?? "loading"}:${responsePhase}`}
    >
      <SessionBar className="rapid-hud" tutorAvailable={Boolean(grade)} tutorLabel="Open tutor">
        <span className="pill rapid-mode-pill"><Timer size={14} aria-hidden="true" /> {pace.title}</span>
        <strong className="rapid-progress">ECG {caseIndex + 1} / {sessionLength}</strong>
        {taskPacket ? (
          <span className="pill rapid-question-count">
            {taskPacket.tasks.length} {taskPacket.tasks.length === 1 ? "question" : "questions"}
          </span>
        ) : null}
        {returnTo ? (
          <button
            className="button subtle small"
            type="button"
            aria-haspopup="dialog"
            onClick={(event) => openAbandonDialog(event.currentTarget, returnTo)}
            disabled={busy || confirmAbandon}
          >
            <ArrowLeft size={15} /> {learningReturnLabel(returnTo)}
          </button>
        ) : null}
        {roundStatus === "active" && grade ? (
          <Link className="button subtle small rapid-pause" href="/">
            Pause between ECGs
          </Link>
        ) : null}
        {roundStatus === "active" ? (
          <button
            ref={abandonTriggerRef}
            className="button subtle small rapid-abandon"
            type="button"
            aria-haspopup="dialog"
            onClick={(event) => openAbandonDialog(event.currentTarget)}
            disabled={busy}
          >
            <XCircle size={15} aria-hidden="true" /> Abandon round
          </button>
        ) : null}
        {timeAllowanceSeconds !== null ? (
          <span
            className={`pill rapid-timer${!grade && clockRunning && remaining !== null && remaining <= 5 ? " rapid-timer-urgent" : ""}`}
            aria-label={grade ? "Rapid read complete" : clockRunning ? "Rapid timer running" : "Rapid timer waiting for ECG"}
            data-clock-state={grade ? "complete" : clockRunning ? "running" : "waiting"}
          >
            {grade ? "Read complete" : clockRunning ? `${Math.ceil(remaining ?? timeAllowanceSeconds)}s` : "ECG loading"}
          </span>
        ) : grade ? (
          <span
            className="pill rapid-timer"
            aria-label="Rapid read complete"
            data-clock-state="complete"
          >
            Read complete
          </span>
        ) : <span className="pill rapid-untimed">Untimed</span>}
      </SessionBar>

      {confirmAbandon || activeRoundIntentConflict || error ? (
        <WorkspaceNotices>
          {confirmAbandon ? (
            <div className="rapid-abandon-modal-layer">
              <button
                className="rapid-abandon-backdrop"
                type="button"
                tabIndex={-1}
                aria-hidden="true"
                onClick={closeAbandonDialog}
              />
              <section
                ref={abandonDialogRef}
                className="panel pad rapid-abandon-confirmation"
                role="alertdialog"
                aria-modal="true"
                aria-labelledby="rapid-abandon-title"
                aria-describedby="rapid-abandon-description"
              >
                <h2 id="rapid-abandon-title">{leaveAfterAbandon ? "Leave this Rapid round?" : "Abandon this Rapid round?"}</h2>
                <p id="rapid-abandon-description" className="muted">
                  {results.length
                    ? "Your submitted ECGs stay in learning history as a partial round and can be reviewed. "
                    : "No ECG from this round has been submitted, so the round will not appear in learning history. "}
                  The current unsubmitted ECG will be discarded and will not be scored or count toward progress. This {sessionLength.toLocaleString()}-ECG round cannot be resumed.
                </p>
                <div className="actions">
                  <button className="button warn" type="button" onClick={() => void abandonRound()} disabled={busy}>
                    {leaveAfterAbandon ? `${learningReturnLabel(leaveAfterAbandon)} and abandon round` : "Abandon round and change setup"}
                  </button>
                  <button ref={keepPracticingRef} className="button" type="button" onClick={closeAbandonDialog} disabled={busy}>
                    Keep practicing
                  </button>
                </div>
              </section>
            </div>
          ) : null}
          {activeRoundIntentConflict ? <div className="warning rapid-error" role="alert">{activeRoundIntentConflict}</div> : null}
          {error ? <div className="warning rapid-error" role="alert">{error}</div> : null}
        </WorkspaceNotices>
      ) : null}

      {caseSummary && packet ? (
        <WorkspaceBody className={`rapid-workspace${!grade && timeAllowanceSeconds !== null && !clockRunning ? " rapid-workspace-arming" : ""}`}>
          <WaveformPane className="rapid-tracing" label="Rapid ECG waveform">
            <ECGViewer
              ecgRef={caseSummary.caseId}
              waveformScope={{ kind: "rapid", roundId }}
              actions={caseViewerActions}
              toolbar={grade ? "clinical" : "none"}
              onReady={onViewerReady}
              groundedRois={grade ? packet.ptbxl_plus.fiducials.rois ?? [] : []}
              medianBeats={packet.ptbxl_plus.median_beats ?? null}
              task={taskPacket ? rapidViewerTask : !grade && paceId !== "emergency" ? RAPID_TRACE_TASK : undefined}
              presentation={taskPacket?.display.kind === "rhythm_strip"
                ? { kind: "rhythm_strip", leads: taskPacket.display.leads }
                : { kind: "twelve_lead" }}
              reviewMode={Boolean(grade)}
              onTaskEvidence={setTraceEvidence}
              onTaskReset={() => setTraceEvidence(null)}
              gradingMode="deferred"
            />
            {grade && traceEvidence?.mode === "point" && traceEvidence.correct === true && !traceEvidence.noTarget ? (
              <p className="selection-note rapid-restored-trace" aria-label="Committed trace proof">
                <strong>Committed trace proof:</strong> QRS in lead {traceEvidence.point.lead} at {traceEvidence.point.timeSec.toFixed(2)}s.
              </p>
            ) : null}
          </WaveformPane>

          <ResponseRail
            className="rapid-response-rail"
            label={grade ? "Rapid ECG feedback" : "Rapid ECG response"}
            phase={responsePhase}
          >
            {!grade ? (
            taskPacket ? (
              <RapidQuestionDeck
                tasks={taskPacket.tasks}
                responses={taskResponses}
                activeIndex={activeTaskIndex}
                onActiveIndexChange={setActiveTaskIndex}
                onResponse={(taskId, response) => setTaskResponses((current) => ({ ...current, [taskId]: response }))}
                onSubmit={() => void submit()}
                traceComplete={traceComplete}
                disabled={busy || !clockRunning && timeAllowanceSeconds !== null}
                submitting={busy}
              />
            ) : (
            <section className={`panel pad rapid-answer-panel rapid-legacy-answer${paceId === "emergency" ? " rapid-quick-response" : ""}`}>
              <div className="rapid-answer-heading">
                <div>
                  <p className="eyebrow rapid-answer-eyebrow">Commit your read</p>
                  <h2>What matters on this ECG?</h2>
                </div>
              </div>

              {paceId !== "emergency" ? (
                <div className="rapid-answer-stages" role="tablist" aria-label="Rapid response steps">
                  {([
                    ["findings", "Findings", selectedConcepts.length ? `${selectedConcepts.length} selected` : "Choose"],
                    ["sweep", "Sweep", `${completedSweepCount}/8`],
                    ["commit", "Commit", traceComplete ? "Trace ready" : "Trace needed"],
                  ] as const).map(([stage, label, status], index) => (
                    <button
                      type="button"
                      role="tab"
                      id={`rapid-response-tab-${stage}`}
                      aria-controls={`rapid-response-panel-${stage}`}
                      key={stage}
                      aria-selected={answerStage === stage}
                      tabIndex={answerStage === stage ? 0 : -1}
                      className={answerStage === stage ? "active" : ""}
                      onClick={() => {
                        if (stage === "sweep") setActiveSweepIndex(firstIncompleteSweepIndex(sweep));
                        setAnswerStage(stage);
                      }}
                      onKeyDown={(event) => {
                        const stages: AnswerStage[] = ["findings", "sweep", "commit"];
                        const currentIndex = stages.indexOf(stage);
                        let nextIndex = currentIndex;
                        if (event.key === "ArrowRight") nextIndex = (currentIndex + 1) % stages.length;
                        else if (event.key === "ArrowLeft") nextIndex = (currentIndex - 1 + stages.length) % stages.length;
                        else if (event.key === "Home") nextIndex = 0;
                        else if (event.key === "End") nextIndex = stages.length - 1;
                        else return;
                        event.preventDefault();
                        const nextStage = stages[nextIndex];
                        if (nextStage === "sweep") setActiveSweepIndex(firstIncompleteSweepIndex(sweep));
                        setAnswerStage(nextStage);
                        window.requestAnimationFrame(() => document.getElementById(`rapid-response-tab-${nextStage}`)?.focus());
                      }}
                    >
                      <span>{index + 1}</span><strong>{label}</strong><small>{status}</small>
                    </button>
                  ))}
                </div>
              ) : null}

              {paceId === "emergency" || answerStage === "findings" ? (
                <div
                  className="rapid-recognition"
                  data-catalog-loaded={catalogLoaded ? "true" : "false"}
                  role={paceId === "emergency" ? undefined : "tabpanel"}
                  id={paceId === "emergency" ? undefined : "rapid-response-panel-findings"}
                  aria-labelledby={paceId === "emergency" ? undefined : "rapid-response-tab-findings"}
                >
                  <label htmlFor={paceId === "emergency" ? "rapid-dominant-finding" : "rapid-add-finding"}>
                    {paceId === "emergency" ? "One dominant finding" : "Findings you can support"}
                  </label>
                  {paceId === "emergency" ? (
                    <div className="rapid-finding-combobox">
                      <input
                        id="rapid-dominant-finding"
                        className="rapid-dominant-select"
                        type="search"
                        role="combobox"
                        aria-label="Search one dominant ECG finding"
                        aria-autocomplete="list"
                        aria-expanded={findingMenuOpen}
                        aria-controls="rapid-dominant-finding-options"
                        aria-activedescendant={findingMenuOpen && filteredFindings[findingActiveIndex]
                          ? `rapid-finding-option-${filteredFindings[findingActiveIndex].id}`
                          : undefined}
                        aria-invalid={Boolean(findingSearch && !selectedConcepts.length)}
                        placeholder="Type to filter, then choose…"
                        value={findingSearch}
                        onFocus={() => setFindingMenuOpen(true)}
                        onBlur={() => window.setTimeout(() => setFindingMenuOpen(false), 100)}
                        onChange={(event) => {
                          const value = event.target.value;
                          setFindingSearch(value);
                          setSelectedConcepts([]);
                          setFindingMenuOpen(true);
                          setFindingActiveIndex(0);
                        }}
                        onKeyDown={(event) => {
                          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                            event.preventDefault();
                            setFindingMenuOpen(true);
                            setFindingActiveIndex((current) => {
                              if (!filteredFindings.length) return 0;
                              const delta = event.key === "ArrowDown" ? 1 : -1;
                              return (current + delta + filteredFindings.length) % filteredFindings.length;
                            });
                          } else if (event.key === "Enter" && findingMenuOpen && filteredFindings[findingActiveIndex]) {
                            event.preventDefault();
                            chooseDominantFinding(filteredFindings[findingActiveIndex]);
                          } else if (event.key === "Escape") {
                            event.preventDefault();
                            setFindingMenuOpen(false);
                          }
                        }}
                      />
                      {findingMenuOpen ? (
                        <ul id="rapid-dominant-finding-options" className="rapid-finding-options" role="listbox" aria-label="Filtered ECG findings">
                          {filteredFindings.length ? filteredFindings.map((concept, index) => (
                            <li
                              id={`rapid-finding-option-${concept.id}`}
                              role="option"
                              aria-selected={selectedConcepts[0] === concept.id}
                              data-active={index === findingActiveIndex ? "true" : "false"}
                              key={concept.id}
                              onMouseDown={(event) => event.preventDefault()}
                              onClick={() => chooseDominantFinding(concept)}
                            >
                              {rapidFindingLabel(concept.id)}
                            </li>
                          )) : <li className="rapid-finding-empty" role="option" aria-selected="false" aria-disabled="true">No validated finding matches that search.</li>}
                        </ul>
                      ) : null}
                      <p className="rapid-finding-hint" role="status">
                        {selectedConcepts[0]
                          ? `Selected: ${rapidFindingLabel(selectedConcepts[0])}`
                          : findingSearch
                            ? "Choose a finding from the filtered list to commit."
                            : "Start typing a rhythm, conduction, axis, or ST–T finding."}
                      </p>
                    </div>
                  ) : (
                    <select
                      id="rapid-add-finding"
                      className="rapid-dominant-select"
                      aria-label="Add ECG finding"
                      value=""
                      onChange={(event) => {
                        const value = event.target.value;
                        if (value && !selectedConcepts.includes(value)) toggleConcept(value);
                      }}
                    >
                      <option value="">Add a finding…</option>
                      <option value="uncertain">Uncertain / no supported abnormality</option>
                      {conceptGroups.map((group) => (
                        <optgroup label={group.label} key={group.id}>
                          {group.concepts.map((concept) => <option value={concept.id} key={concept.id}>{concept.label}</option>)}
                        </optgroup>
                      ))}
                    </select>
                  )}
                  {paceId !== "emergency" ? (
                    <>
                      <p className="rapid-finding-hint">Choose only labels you would put in the final read. You can add more than one.</p>
                      <div className="rapid-selected-findings" aria-label="Selected ECG findings" aria-live="polite">
                        {selectedConcepts.length ? selectedConcepts.map((concept) => (
                          <button type="button" key={concept} onClick={() => toggleConcept(concept)} aria-label={`Remove ${rapidFindingLabel(concept)}`}>
                            {rapidFindingLabel(concept)} <span aria-hidden="true">×</span>
                          </button>
                        )) : <span>No finding selected yet.</span>}
                      </div>
                      <button
                        className="button primary rapid-stage-next"
                        type="button"
                        onClick={() => {
                          setActiveSweepIndex(firstIncompleteSweepIndex(sweep));
                          setAnswerStage("sweep");
                        }}
                      >
                        Continue to systematic sweep <ArrowRight size={15} aria-hidden="true" />
                      </button>
                    </>
                  ) : null}
                </div>
              ) : null}

              {paceId !== "emergency" && answerStage === "sweep" ? (
                <div className="rapid-progressive-sweep" role="tabpanel" id="rapid-response-panel-sweep" aria-labelledby="rapid-response-tab-sweep">
                  <ol className="rapid-framework" aria-label="ECG interpretation framework">
                    {FRAMEWORK_STEPS.map((step, index) => {
                      const complete = Boolean(sweep[step.key].trim());
                      const current = activeSweepIndex === index;
                      return (
                        <li className={`${complete ? "complete " : ""}${current ? "current" : ""}`.trim()} key={step.key} aria-current={current ? "step" : undefined}>
                          <button type="button" onClick={() => setActiveSweepIndex(index)} aria-label={`${index + 1}. ${step.label}${complete ? " complete" : ""}`}>
                            <span>{complete ? "✓" : index + 1}</span><small>{step.label}</small>
                          </button>
                        </li>
                      );
                    })}
                  </ol>
                  <div className="field rapid-active-sweep-field">
                    <label id={`rapid-${activeSweepStep.key}-label`} htmlFor={`rapid-${activeSweepStep.key}`}>{activeSweepStep.label === "Synthesis" ? "One-line synthesis" : activeSweepStep.label}</label>
                    <p>{activeSweepStep.prompt}</p>
                    {activeSweepStep.choices ? (
                      <div className="rapid-sweep-choices" role="group" aria-label={`${activeSweepStep.label} quick choices`}>
                        {activeSweepStep.choices.map((choice) => (
                          <button
                            type="button"
                            className={sweep[activeSweepStep.key] === choice ? "selected" : ""}
                            aria-pressed={sweep[activeSweepStep.key] === choice}
                            key={choice}
                            onClick={() => setSweep((current) => ({ ...current, [activeSweepStep.key]: choice }))}
                          >
                            {choice}
                          </button>
                        ))}
                      </div>
                    ) : null}
                    {activeSweepStep.choices ? <span className="rapid-custom-entry-label">Or type a more precise entry</span> : null}
                    <input
                      id={`rapid-${activeSweepStep.key}`}
                      aria-label={activeSweepStep.label === "Synthesis" ? "One-line synthesis" : activeSweepStep.label}
                      value={sweep[activeSweepStep.key]}
                      placeholder={activeSweepStep.placeholder}
                      onChange={(event) => setSweep((current) => ({ ...current, [activeSweepStep.key]: event.target.value }))}
                      autoComplete="off"
                    />
                  </div>
                  <div className="rapid-step-actions">
                    <button className="button subtle" type="button" onClick={() => activeSweepIndex === 0 ? setAnswerStage("findings") : setActiveSweepIndex((value) => value - 1)}>
                      <ArrowLeft size={15} aria-hidden="true" /> {activeSweepIndex === 0 ? "Findings" : "Previous"}
                    </button>
                    <button className="button primary" type="button" onClick={() => {
                      if (activeSweepIndex < FRAMEWORK_STEPS.length - 1) setActiveSweepIndex((value) => value + 1);
                      else setAnswerStage("commit");
                    }}>
                      {activeSweepIndex === FRAMEWORK_STEPS.length - 1 ? "Review & commit" : "Next"} <ArrowRight size={15} aria-hidden="true" />
                    </button>
                  </div>
                </div>
              ) : null}

              {paceId !== "emergency" && answerStage === "commit" ? (
                <div className="rapid-commit-review" role="tabpanel" id="rapid-response-panel-commit" aria-labelledby="rapid-response-tab-commit">
                  <dl>
                    <div><dt>Findings</dt><dd>{selectedConcepts.length ? selectedConcepts.map(rapidFindingLabel).join(", ") : "None selected"}</dd></div>
                    <div><dt>Systematic sweep</dt><dd>{completedSweepCount}/8 complete</dd></div>
                  </dl>
                  <p className={`selection-note${synthesisTaskComplete ? " complete" : ""}`} role="status">
                    <strong>Complete-read check:</strong> {synthesisTaskComplete
                      ? "All eight steps and a supported finding are ready to submit."
                      : "Complete all eight sweep steps, select a finding (including normal if appropriate), and write a 12+ character synthesis."}
                  </p>
                  <p className={`selection-note rapid-trace-status${traceComplete ? " complete" : ""}`} role="status">
                    <strong>Trace proof:</strong> {traceComplete
                      ? "QRS mark recorded. Correctness will be revealed after commitment."
                      : "Mark one QRS in lead II above (or use the precise-entry alternative) before commitment."}
                  </p>
                </div>
              ) : null}

              {paceId === "emergency" ? <p className="selection-note rapid-quick-note">Commit one dominant finding and confidence. Feedback then explains what to verify in a complete read; this clock measures prioritization, not typing.</p> : null}

              {paceId === "emergency" || answerStage === "commit" ? (
                <div className="rapid-commit-row">
                  {paceId !== "emergency" ? <button className="button subtle rapid-back-to-sweep" type="button" onClick={() => setAnswerStage("sweep")}><ArrowLeft size={15} /> Sweep</button> : null}
                  <div className="field rapid-confidence">
                    <label htmlFor="rapid-confidence">Confidence</label>
                    <select id="rapid-confidence" value={confidence} onChange={(event) => setConfidence(Number(event.target.value))}>
                      <option value={1}>1 · guessing</option>
                      <option value={2}>2 · low</option>
                      <option value={3}>3 · moderate</option>
                      <option value={4}>4 · high</option>
                      <option value={5}>5 · certain</option>
                    </select>
                  </div>
                  <button className="button primary rapid-submit" type="button" disabled={busy || !hasAnswer} onClick={() => void submit()}>
                    {busy ? "Grading…" : "Commit interpretation"} <ArrowRight size={16} aria-hidden="true" />
                  </button>
                </div>
              ) : null}
            </section>
            )
          ) : (
            <section className={`panel pad rapid-feedback${score >= 0.6 ? " rapid-feedback-ok" : " rapid-feedback-miss"}`}>
              <div className="rapid-feedback-heading">
                <h2>
                  {score >= 0.6 ? <CheckCircle2 size={19} aria-hidden="true" /> : <AlertTriangle size={19} aria-hidden="true" />} Case feedback
                </h2>
                <strong className="rapid-score">{Math.round(score * 100)}%</strong>
              </div>
              <p className="rapid-feedback-copy">
                {score >= 0.85
                  ? "Strong read. Carry the same evidence-first sequence into the next ECG."
                  : score >= 0.6
                    ? "Mostly there. Recheck the missed finding before moving on."
                    : "Pause and compare your call with the grounded findings below before the next ECG."}
              </p>

              {grade.taskFeedback?.length ? (
                <div className="rapid-task-feedback-list">
                  {grade.taskFeedback.map((item, index) => (
                    <article className={item.correct ? "correct" : "review"} key={item.taskId || index}>
                      <header>
                        <span>Question {index + 1}</span>
                        <strong>{item.correct ? "Correct" : "Review"}</strong>
                      </header>
                      {item.prompt || taskPacket?.tasks.find((task) => task.id === item.taskId)?.prompt ? (
                        <h3>{item.prompt || taskPacket?.tasks.find((task) => task.id === item.taskId)?.prompt}</h3>
                      ) : null}
                      <dl>
                        <div><dt>Your answer</dt><dd>{item.learnerAnswer || rapidTaskResponseDisplay(taskPacket, taskResponses, item.taskId)}</dd></div>
                        <div><dt>Supported answer</dt><dd>{item.supportedAnswer
                          || item.correctAnswer
                          || (item.correctChoiceId
                            ? taskPacket?.tasks.find((task) => task.id === item.taskId)?.options?.find((option) => option.id === item.correctChoiceId)?.label
                            : "")
                          || (typeof item.expectedValue === "number" ? `${item.expectedValue} ${item.unit || ""}`.trim() : "")
                          || "See the reviewed findings below"}</dd></div>
                      </dl>
                      {item.explanation || item.feedback ? <p><strong>Why it fits:</strong> {item.explanation || item.feedback}</p> : null}
                      {item.closestMimic ? <p><strong>Closest mimic:</strong> {item.closestMimic}</p> : null}
                    </article>
                  ))}
                </div>
              ) : null}

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
                    {missed.length ? missed.map((item) => <span className="pill disabled rapid-objective" key={item}>{conceptLabel(item)}</span>) : <span className="muted">No supported target findings missed.</span>}
                  </div>
                </div>
                <div className="evidence-card rapid-overcalled">
                  <h3>Overcalled</h3>
                  <div className="pill-row rapid-overcalled-list">
                    {overcalled.length ? overcalled.map((item) => <span className="pill disabled rapid-objective" key={item}>{conceptLabel(item)}</span>) : <span className="muted">No unsupported call detected.</span>}
                  </div>
                </div>
              </div>

              <div className="rapid-next-focus">
                <strong>Carry forward</strong>
                <p>
                  {missed.length
                    ? `On the next ECG, verify ${conceptLabel(missed[0])} from explicit trace evidence before committing.`
                    : overcalled.length
                      ? `Require positive evidence before calling ${conceptLabel(overcalled[0])}.`
                      : "Keep the same rate → rhythm → axis → intervals → morphology sequence."}
                </p>
              </div>
              {traceReceipt ? <p className="selection-note rapid-trace-receipt">{traceReceipt}</p> : null}
              {handoffReceipt ? <p className="selection-note rapid-handoff-receipt">{handoffReceipt}</p> : null}
              <button className="button primary rapid-next" type="button" onClick={() => void advance()} disabled={busy}>
                {caseIndex + 1 >= sessionLength ? "Finish round" : "Next ECG"} <ArrowRight size={16} aria-hidden="true" />
              </button>
            </section>
            )}
          </ResponseRail>
        </WorkspaceBody>
      ) : (
        <section className={`panel pad rapid-loading${error ? " rapid-loading-error" : ""}`} role={error ? undefined : "status"} aria-live={error ? undefined : "polite"} aria-busy={busy || undefined}>
          <span>{busy
            ? "Selecting a new ECG…"
            : error
              ? "Your round is still saved. Retry this ECG when the connection returns."
              : "No ECG loaded."}</span>
          {error && roundId ? (
            <button className="button subtle small" type="button" onClick={() => void loadCase()} disabled={busy}>
              <RotateCcw size={15} aria-hidden="true" /> Retry ECG
            </button>
          ) : null}
        </section>
      )}

      <DisclosureArea className="rapid-disclosure">
        {caseSummary ? <span className="rapid-source"><ShieldCheck size={13} aria-hidden="true" /> {grade ? rapidSourceLabel(caseSummary.source) : "Reviewed real ECG"}</span> : null}
        <span className="rapid-silence"><ShieldCheck size={13} aria-hidden="true" /> {grade ? "Tutor available for a post-commit debrief" : "Tutor silent until commitment"}</span>
        {timeAllowanceSeconds !== null && !grade ? (
          <progress
            className="rapid-clockbar"
            aria-label={`${Math.ceil(remaining ?? timeAllowanceSeconds)} seconds remaining`}
            max={100}
            value={timerPercent}
          />
        ) : null}
      </DisclosureArea>

      <TutorDrawer title="Rapid ECG tutor · post-commit">
        {grade && caseSummary ? (
          <TutorChat
            mode="practice"
            roleLabel="Debrief · post-commit"
            ecgRef={caseSummary.caseId}
            threadScope={`rapid:${roundId}`}
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
            collapsedByDefault={false}
          />
        ) : null}
      </TutorDrawer>
    </LearningWorkspaceShell>
  );
}
