"use client";

import {
  ArrowLeft,
  ArrowRight,
  Brain,
  CheckCircle2,
  Lightbulb,
  RefreshCw,
  Send,
  Sparkles,
  Target,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ECGViewer } from "@/components/ECGViewer";
import { TutorChat } from "@/components/TutorChat";
import { clinicalApi } from "@/lib/clinical";
import {
  FocusedPracticeSetup,
  type FocusedSkillOption,
  type FocusedTopicOption,
} from "@/components/training/FocusedPracticeSetup";
import {
  DEFAULT_FOCUSED_INTERPRETATION_STEPS,
  EMPTY_FOCUSED_INTERPRETATION,
  FocusedInterpretationReview,
  FocusedInterpretationStepper,
  type FocusedInterpretationStep,
  type FocusedInterpretationValue,
  type FocusedReviewedFrameworkRow,
} from "@/components/training/FocusedInterpretationStepper";
import { FocusedSetReview } from "@/components/training/FocusedSetReview";
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
import { conceptLabel, type ECGPoint } from "@/lib/coordinates";
import { resolveHandoffTarget, type HandoffTargetResolution } from "@/lib/learning/handoffTargets";
import type { LearningSubskill } from "@/lib/learning/interactionTypes";
import { learningReturnLabel } from "@/lib/learning/learningReturn";
import { competencySkillLabel } from "@/lib/learning/skillLabels";
import {
  campaignMatchesTrainingLaunch,
  parseTrainingLaunchIntent,
  safeTrainingReturn,
  trainingFeedbackHeading,
  trainingMasteryPresentation,
} from "@/lib/learning/trainingLogic";
import { useLearningPreferences } from "@/lib/useLearningPreferences";
import "./train.module.css";
import type {
  CasePacket,
  CaseSummary,
  ConceptGroup,
  ConceptSubskill,
  GroundedRoi,
  LearnerProfile,
  TrainingCampaignPayload,
  TrainingCampaignSummary,
  ViewerAction,
  ViewerTaskEvidence,
  ViewerTaskSpec,
} from "@/lib/types";

type CatalogConcept = {
  id: string;
  label: string;
  group: string;
  highYield?: boolean;
};

type DrillResult = {
  correct: boolean;
  classificationCorrect: boolean;
  focusGrounded: boolean;
  grade: Record<string, unknown>;
};

type TrainingTaskResult = {
  kind: "single_choice" | "matching" | "numeric_fill_in";
  complete: boolean;
  correct: boolean;
  score: number;
  submittedAnswer?: string | null;
  correctAnswer?: string | null;
  rows?: Array<{
    rowId: string;
    submittedChoiceId: string | null;
    correctChoiceId: string;
    correct: boolean;
  }>;
  submittedValue?: number | null;
  expectedValue?: number | null;
  tolerance?: number | null;
  unit?: "ms" | "bpm";
  systematicInterpretationComplete?: boolean;
  systematicInterpretation?: FocusedInterpretationValue;
  reviewedFramework?: FocusedReviewedFrameworkRow[];
};

type HintPlan = {
  text: string;
  actions: ViewerAction[];
};

type BinaryAnswer = "present" | "absent";

type TrainingAvailabilityInfo = {
  conceptId: string;
  source: "exact_target_index";
  subskills: Record<string, {
    available: boolean;
    independentReceiptsAvailable: boolean;
  }>;
};

const TRAINING_SUBSKILLS: FocusedSkillOption[] = [
  { id: "recognize", label: competencySkillLabel("recognize"), description: "Name the core pattern" },
  { id: "localize", label: competencySkillLabel("localize"), description: "Mark the relevant lead and segment" },
  { id: "measure", label: competencySkillLabel("measure"), description: "Use calipers and values" },
  { id: "discriminate", label: competencySkillLabel("discriminate"), description: "Separate close look-alikes" },
  { id: "explain_mechanism", label: competencySkillLabel("explain_mechanism"), description: "Connect form to cause" },
  { id: "synthesize", label: competencySkillLabel("synthesize"), description: "Use the full rate-to-impression sequence" },
  { id: "apply_in_context", label: competencySkillLabel("apply_in_context"), description: "Choose the context that matters" },
  { id: "calibrate_confidence", label: competencySkillLabel("calibrate_confidence"), description: "Match certainty to accuracy" },
];

const FOCUSED_CATEGORIES = [
  { id: "all", label: "All topics" },
  { id: "rhythm", label: "Rhythms" },
  { id: "conduction", label: "Conduction & axis" },
  { id: "intervals", label: "Intervals & AV block" },
  { id: "ischemia", label: "Ischemia & ST–T" },
  { id: "chamber", label: "Chambers & voltage" },
  { id: "foundations", label: "Core reading" },
] as const;

const FOCUSED_VISIBLE_LENGTHS = [5, 10, 20] as const;
const FOCUSED_INTERPRETATION_KEYS = [
  "rate", "rhythm", "axis", "intervals", "conduction", "st_t", "hypertrophy", "synthesis",
] as const;

function focusedInterpretationFrom(value: unknown): FocusedInterpretationValue {
  if (!value || typeof value !== "object") return { ...EMPTY_FOCUSED_INTERPRETATION };
  const source = value as Record<string, unknown>;
  return Object.fromEntries(FOCUSED_INTERPRETATION_KEYS.map((key) => [
    key,
    typeof source[key] === "string" ? source[key].slice(0, key === "synthesis" ? 600 : 300) : "",
  ])) as FocusedInterpretationValue;
}

function focusedCampaignLength(value: number) {
  if (value <= 5) return 5;
  if (value <= 10) return 10;
  return 20;
}

function focusedCategory(group: string) {
  if (group === "rhythm") return "rhythm";
  if (group === "conduction" || group === "axis") return "conduction";
  if (group === "intervals") return "intervals";
  if (group === "st_t_mi") return "ischemia";
  if (group === "hypertrophy") return "chamber";
  return "foundations";
}

function focusedCategoryLabel(category: string) {
  return FOCUSED_CATEGORIES.find((item) => item.id === category)?.label ?? "ECG foundations";
}

function isLearningSubskill(value: string): value is LearningSubskill {
  return TRAINING_SUBSKILLS.some((item) => item.id === value);
}

function trainingSkillLabel(value: string) {
  return competencySkillLabel(value);
}

function readableApiError(caught: unknown, fallback: string) {
  const detail = caught instanceof Error ? caught.message : "";
  if (!detail || /^\d{3}\b/.test(detail) || /internal server error|failed to fetch|networkerror/i.test(detail)) return fallback;
  return detail;
}

const MEASUREMENT_CLASSIFICATION_TARGETS = new Set(["rate", "qrs_duration", "qtc_prolongation", "qt_interval"]);

function classificationContract(concept: string, variant = 0) {
  const promptVariant = Math.max(0, variant) % 3;
  const options = (
    present: { id: "present"; label: string },
    absent: { id: "absent"; label: string },
  ): Array<{ id: BinaryAnswer; label: string }> => (
    variant % 2 === 0 ? [present, absent] : [absent, present]
  );
  if (concept === "rate") {
    const present = { id: "present" as const, label: "Within 60–100 bpm" };
    const absent = { id: "absent" as const, label: "Outside 60–100 bpm" };
    return {
      prompt: [
        "Classify the ventricular rate band from the tracing.",
        "Estimate the ventricular rate, then place it relative to the adult 60–100 bpm band.",
        "Which rate category is supported by the R–R spacing?",
      ][promptVariant],
      presentLabel: present.label,
      absentLabel: absent.label,
      options: options(present, absent),
    };
  }
  if (concept === "qrs_duration") {
    const present = { id: "present" as const, label: "Wide (≥120 ms)" };
    const absent = { id: "absent" as const, label: "Not wide (<120 ms)" };
    return {
      prompt: [
        "Is the measured QRS wide at the adult 120 ms threshold?",
        "Measure ventricular depolarization, then classify it against 120 ms.",
        "Does QRS onset-to-offset cross the adult wide-complex threshold?",
      ][promptVariant],
      presentLabel: present.label,
      absentLabel: absent.label,
      options: options(present, absent),
    };
  }
  if (concept === "qtc_prolongation") {
    const present = { id: "present" as const, label: "QTc ≥480 ms" };
    const absent = { id: "absent" as const, label: "QTc <480 ms" };
    return {
      prompt: [
        "Is the measured QTc at least 480 ms?",
        "Compare this ECG’s QTc with the 480 ms practice threshold.",
        "Which side of 480 ms does the measured QTc fall on?",
      ][promptVariant],
      presentLabel: present.label,
      absentLabel: absent.label,
      options: options(present, absent),
    };
  }
  const present = { id: "present" as const, label: "Target present" };
  const absent = { id: "absent" as const, label: "Target absent" };
  return {
    prompt: [
      `Does this tracing support ${conceptLabel(concept)}?`,
      `Decide whether the waveform evidence meets the reviewed pattern for ${conceptLabel(concept)}.`,
      `After checking the defining leads, is ${conceptLabel(concept)} supported or not supported?`,
    ][promptVariant],
    presentLabel: present.label,
    absentLabel: absent.label,
    options: options(present, absent),
  };
}

function availableConcepts(groups: ConceptGroup[]): ConceptSubskill[] {
  const unique = new Map<string, ConceptSubskill>();
  for (const group of groups) {
    if (!group.enabled) continue;
    for (const concept of group.concepts) {
      if (concept.available && !unique.has(concept.id)) unique.set(concept.id, concept);
    }
  }
  return [...unique.values()];
}

function chooseDefaultConcept(catalog: CatalogConcept[], groups: ConceptGroup[]): string {
  const available = availableConcepts(groups);
  const byId = new Map(available.map((concept) => [concept.id, concept]));
  const highYield = catalog.find((concept) => concept.highYield && byId.has(concept.id));
  if (highYield) return highYield.id;
  return [...available].sort((left, right) => right.reliableCaseCount - left.reliableCaseCount)[0]?.id ?? "";
}

function rankAdaptiveTargets(
  catalog: CatalogConcept[],
  groups: ConceptGroup[],
  profile: LearnerProfile | null,
  subskill: LearningSubskill,
): string[] {
  const highYield = new Set(catalog.filter((concept) => concept.highYield).map((concept) => concept.id));
  const available = availableConcepts(groups);
  // Generic interval nouns are not valid pathology-presence targets. Keep
  // them available for explicit measurement work, but do not let a fresh
  // recognition learner default into an ambiguous "Rate is present" drill.
  const focusedRows = subskill === "measure"
    ? available.filter((concept) => concept.id !== "qt_interval")
    : available.filter((concept) => !MEASUREMENT_CLASSIFICATION_TARGETS.has(concept.id));
  const rows = focusedRows.length ? focusedRows : available;
  return [...rows].sort((left, right) => {
    const leftReceipt = profile?.subskillMastery.find((row) => row.concept === left.id && row.subskill === subskill);
    const rightReceipt = profile?.subskillMastery.find((row) => row.concept === right.id && row.subskill === subskill);
    const leftRank = !leftReceipt || leftReceipt.independentAttempts === 0
      ? 1
      : leftReceipt.independentMastery < 0.7 || leftReceipt.highConfidenceWrong > 0 || leftReceipt.isDue ? 0 : 2;
    const rightRank = !rightReceipt || rightReceipt.independentAttempts === 0
      ? 1
      : rightReceipt.independentMastery < 0.7 || rightReceipt.highConfidenceWrong > 0 || rightReceipt.isDue ? 0 : 2;
    return leftRank - rightRank
      || Number(rightReceipt?.isDue ?? false) - Number(leftReceipt?.isDue ?? false)
      || (rightReceipt?.highConfidenceWrong ?? 0) - (leftReceipt?.highConfidenceWrong ?? 0)
      || (leftReceipt?.independentMastery ?? 1) - (rightReceipt?.independentMastery ?? 1)
      || Number(highYield.has(right.id)) - Number(highYield.has(left.id))
      || right.reliableCaseCount - left.reliableCaseCount;
  }).map((concept) => concept.id);
}

function chooseAdaptiveTarget(
  catalog: CatalogConcept[],
  groups: ConceptGroup[],
  profile: LearnerProfile | null,
  subskill: LearningSubskill,
): string {
  return rankAdaptiveTargets(catalog, groups, profile, subskill)[0]
    ?? chooseDefaultConcept(catalog, groups);
}

function hintDomain(concept: string): { segment: string; leads: string[]; text: string; multi?: boolean } {
  if (concept.includes("lead_territor") || concept.includes("frontal_lead_map")) {
    return {
      segment: "qrs_complex",
      leads: ["II", "III", "aVF"],
      text: "Mark one inferior-lead QRS, then name the full contiguous inferior set: II, III, and aVF.",
      multi: true,
    };
  }
  if (concept.includes("axis")) {
    return {
      segment: "qrs_complex",
      leads: ["I", "aVF"],
      text: "Compare the net QRS direction in leads I and aVF before naming the axis.",
      multi: true,
    };
  }
  if (concept.includes("bundle") || concept.includes("qrs") || concept.includes("conduction")) {
    return {
      segment: "qrs_complex",
      leads: ["V1", "V6"],
      text: "Inspect QRS width and terminal morphology in V1 and V6; compare the two leads rather than using width alone.",
      multi: true,
    };
  }
  if (concept.includes("av_block") || concept.includes("pr_")) {
    return {
      segment: "pr_interval",
      leads: ["II"],
      text: "Follow P-to-QRS conduction in lead II and measure from the start of P to the start of QRS.",
    };
  }
  if (concept.includes("qt")) {
    return {
      segment: "qt_segment",
      leads: ["II", "V5"],
      text: "Trace from QRS onset through the end of T, then interpret the interval in the context of rate.",
    };
  }
  if (
    concept.includes("st_") ||
    concept.includes("t_wave") ||
    concept.includes("myocardial") ||
    concept.endsWith("_mi")
  ) {
    const leads = concept.includes("inferior")
      ? ["II", "III", "aVF"]
      : concept.includes("lateral")
        ? ["I", "aVL", "V5", "V6"]
        : ["V2", "V3", "V4"];
    return {
      segment: concept.includes("t_wave") ? "t_wave" : "st_segment",
      leads,
      text: "Compare the highlighted repolarization region with the baseline and then check neighboring contiguous leads.",
      multi: true,
    };
  }
  if (concept.includes("atrial") || concept.includes("sinus") || concept.includes("flutter")) {
    return {
      segment: "p_wave",
      leads: ["II"],
      text: "Stay in lead II and inspect atrial activity, regularity, and the P-to-QRS relationship across several beats.",
    };
  }
  if (concept.includes("hypertrophy") || concept.includes("enlargement") || concept.includes("r_wave")) {
    return {
      segment: "qrs_complex",
      leads: ["V1", "V5", "V6"],
      text: "Compare QRS amplitude and morphology across the precordial leads rather than judging a single complex.",
      multi: true,
    };
  }
  return {
    segment: "qrs_complex",
    leads: ["II"],
    text: "Use lead II to check spacing, rate, and the relationship between atrial activity and each QRS.",
  };
}

function taskForTraining(subskill: LearningSubskill, concept: string): ViewerTaskSpec | undefined {
  const domain = hintDomain(concept);
  if (subskill === "localize") {
    return {
      mode: "point",
      prompt: concept.includes("lead_territor") || concept.includes("frontal_lead_map")
        ? "Mark one QRS in the inferior territory, then name all contiguous inferior leads in the evidence statement."
        : `Mark one relevant ${domain.segment.replaceAll("_", " ")} in the specified lead before you classify.`,
      concept: domain.segment,
      allowedLeads: domain.leads,
    };
  }
  if (subskill === "measure") {
    const measurement = concept.includes("qt") ? "qt"
      : concept.includes("av_block") || concept.startsWith("pr_") ? "pr"
        : concept === "rate" ? "rr"
          : concept.includes("qrs") || concept.includes("bundle") || concept.includes("conduction") ? "qrs"
            : null;
    if (!measurement) return undefined;
    return {
      mode: "caliper",
      prompt: `Drag calipers across one ${measurement.toUpperCase()} interval before classifying.`,
      measurement,
      allowedLeads: domain.leads,
    };
  }
  return undefined;
}

function buildHintPlan(concept: string, rois: GroundedRoi[], waveformLeads: string[]): HintPlan {
  const domain = hintDomain(concept);
  const limit = domain.multi ? 2 : 1;
  const selectedRois = domain.leads
    .flatMap((lead) => rois.filter((roi) => roi.lead === lead && roi.concept === domain.segment).slice(0, 1))
    .slice(0, limit);

  if (selectedRois.length) {
    return {
      text: domain.text,
      actions: selectedRois.map((roi) => ({
        type: "highlightROI",
        lead: roi.lead,
        timeStart: roi.timeStartSec,
        timeEnd: roi.timeEndSec,
        ampMin: roi.ampMinMv,
        ampMax: roi.ampMaxMv,
        label: `Inspect ${roi.label}`,
      })),
    };
  }

  const selectedLeads = domain.leads.filter((lead) => waveformLeads.includes(lead)).slice(0, limit);
  return {
    text: domain.text,
    actions: selectedLeads.map((lead) => ({ type: "highlightLead", lead })),
  };
}

export default function TrainPage() {
  const { preferences: learningPreferences, loading: preferencesLoading } = useLearningPreferences();
  const [groups, setGroups] = useState<ConceptGroup[]>([]);
  const [catalog, setCatalog] = useState<CatalogConcept[]>([]);
  const [profile, setProfile] = useState<LearnerProfile | null>(null);
  const [trainingTarget, setTrainingTarget] = useState("");
  const [conceptQuery, setConceptQuery] = useState("");
  const [topicCategory, setTopicCategory] = useState("all");
  const [showAllTopics, setShowAllTopics] = useState(false);
  const [trainingSubskill, setTrainingSubskill] = useState<LearningSubskill>("recognize");
  const [adaptiveMode, setAdaptiveMode] = useState(true);
  const [resolvedAdaptiveTarget, setResolvedAdaptiveTarget] = useState("");
  const [caseFocus, setCaseFocus] = useState("");
  const [caseSummary, setCaseSummary] = useState<CaseSummary | null>(null);
  const [packet, setPacket] = useState<CasePacket | null>(null);
  const [selectedAnswer, setSelectedAnswer] = useState<BinaryAnswer | "">("");
  const [classificationTruth, setClassificationTruth] = useState<BinaryAnswer | null>(null);
  const [evidenceNote, setEvidenceNote] = useState("");
  const [subskillTaskAnswer, setSubskillTaskAnswer] = useState("");
  const [subskillTaskMatches, setSubskillTaskMatches] = useState<Record<string, string>>({});
  const [subskillTaskValue, setSubskillTaskValue] = useState("");
  const [structuredInterpretation, setStructuredInterpretation] = useState<FocusedInterpretationValue>(EMPTY_FOCUSED_INTERPRETATION);
  const [interpretationStepIndex, setInterpretationStepIndex] = useState(0);
  const [confidence, setConfidence] = useState<number | null>(null);
  const [hintsUsed, setHintsUsed] = useState(0);
  const [hintText, setHintText] = useState("");
  const [selectedPoint, setSelectedPoint] = useState<ECGPoint | null>(null);
  const [viewerActions, setViewerActions] = useState<ViewerAction[]>([]);
  const [viewerTaskEvidence, setViewerTaskEvidence] = useState<ViewerTaskEvidence | null>(null);
  const [subskillReceipt, setSubskillReceipt] = useState<string | null>(null);
  const [result, setResult] = useState<DrillResult | null>(null);
  const [emptyReason, setEmptyReason] = useState<string | null>(null);
  const [booting, setBooting] = useState(true);
  const [bootRetryKey, setBootRetryKey] = useState(0);
  const [poolRetryKey, setPoolRetryKey] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [returnTo, setReturnTo] = useState("");
  const [handoffConcept, setHandoffConcept] = useState("");
  const [handoffResolution, setHandoffResolution] = useState<HandoffTargetResolution | null>(null);
  const [campaignPayload, setCampaignPayload] = useState<TrainingCampaignPayload | null>(null);
  const [campaignLength, setCampaignLength] = useState<number>(10);
  const [skillAvailability, setSkillAvailability] = useState<TrainingAvailabilityInfo | null>(null);
  const [availabilityFailed, setAvailabilityFailed] = useState(false);
  const [poolLoading, setPoolLoading] = useState(false);
  const [replaceActiveOnStart, setReplaceActiveOnStart] = useState(false);
  const [sessionComplete, setSessionComplete] = useState(false);
  const [confirmAbandon, setConfirmAbandon] = useState(false);
  const [completedSessionRef, setCompletedSessionRef] = useState<string | null>(null);
  const [completedSessionLookupPending, setCompletedSessionLookupPending] = useState(false);
  const [showSetReview, setShowSetReview] = useState(false);
  const [clinicalDestinations, setClinicalDestinations] = useState<Map<string, "clinic" | "ward" | "ed">>(new Map());
  const abandonTriggerRef = useRef<HTMLButtonElement | null>(null);
  const abandonDialogRef = useRef<HTMLElement | null>(null);
  const keepTrainingRef = useRef<HTMLButtonElement | null>(null);
  const campaignLengthTouchedRef = useRef(false);
  const explicitCampaignLengthRef = useRef(false);
  const hydratedDraftKeyRef = useRef("");

  const closeAbandonDialog = useCallback(() => {
    setConfirmAbandon(false);
    window.requestAnimationFrame(() => abandonTriggerRef.current?.focus());
  }, []);

  useEffect(() => {
    if (!confirmAbandon) return;
    const focusFrame = window.requestAnimationFrame(() => keepTrainingRef.current?.focus());
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

  useEffect(() => {
    let cancelled = false;
    async function boot() {
      setBooting(true);
      setError(null);
      try {
        const [conceptData, learnerData, activeCampaign] = await Promise.all([
          api.concepts(),
          api.profile(),
          api.activeTrainingCampaign(),
        ]);
        if (cancelled) return;
        setGroups(conceptData.practiceGroups);
        setCatalog(conceptData.concepts);
        setProfile(learnerData);
        const intent = parseTrainingLaunchIntent(window.location.search);
        explicitCampaignLengthRef.current = intent.suggestedLength !== null;
        setReturnTo(intent.returnTo);
        setCampaignLength(focusedCampaignLength(intent.suggestedLength ?? 10));
        const initialSubskill = intent.subskill || "recognize";
        setTrainingSubskill(initialSubskill);

        const availableIds = availableConcepts(conceptData.practiceGroups)
          .map((concept) => concept.id)
          .filter((conceptId) => conceptId !== "qt_interval");
        const resolution = intent.requestedCaseConcept
          ? resolveHandoffTarget(intent.requestedCaseConcept, availableIds)
          : null;
        if (intent.requestedCaseConcept && !resolution) {
          setReplaceActiveOnStart(Boolean(activeCampaign.campaign));
          setAdaptiveMode(false);
          setHandoffConcept(intent.isHandoff ? intent.receiptConcept : "");
          setTrainingTarget("");
          setEmptyReason(
            `No reviewed real ECGs are available for ${intent.requestedCaseConcept.replaceAll("_", " ")}. Return to the prior activity or choose a different skill; no substitute attempt will be recorded.`,
          );
          return;
        }
        const initialTarget = resolution?.caseConcept
          ?? chooseAdaptiveTarget(conceptData.concepts, conceptData.practiceGroups, learnerData, initialSubskill);
        const intendedReceipt = intent.receiptConcept || initialTarget;
        const effectiveResolution: HandoffTargetResolution | null = resolution && intendedReceipt !== resolution.caseConcept
          ? {
              requestedConcept: intendedReceipt,
              caseConcept: resolution.caseConcept,
              exact: false,
              rationale: "the handoff supplies a validated ECG case family for this broader competency",
            }
          : resolution;
        const explicitConflict = Boolean(
          activeCampaign.campaign
          && intent.hasExplicitPreset
          && !campaignMatchesTrainingLaunch(activeCampaign.campaign, intent, initialTarget),
        );

        if (activeCampaign.campaign && !explicitConflict) {
          const resumed = activeCampaign.campaign;
          const resumedContext = new URLSearchParams(resumed.contextKey);
          const receiptConcept = intent.isHandoff
            ? intendedReceipt
            : resumedContext.get("receiptConcept") || resumed.conceptId;
          const resumedReturn = intent.returnTo || safeTrainingReturn(resumedContext.get("returnTo") || "");
          setTrainingTarget(resumed.conceptId);
          if (isLearningSubskill(resumed.subskill)) setTrainingSubskill(resumed.subskill);
          setCampaignLength(resumed.requestedLength);
          setAdaptiveMode(resumedContext.get("adaptive") === "true");
          if (intent.isHandoff || receiptConcept !== resumed.conceptId || resumedReturn) {
            setHandoffConcept(receiptConcept);
            setHandoffResolution(effectiveResolution ?? (receiptConcept !== resumed.conceptId ? {
              requestedConcept: receiptConcept,
              caseConcept: resumed.conceptId,
              exact: false,
              rationale: "the saved campaign preserves its validated proxy target",
            } : null));
          }
          setReturnTo(resumedReturn);
          applyCampaignPayload(activeCampaign, receiptConcept);
          return;
        }

        setReplaceActiveOnStart(explicitConflict);
        setHandoffConcept(intent.isHandoff ? intendedReceipt : "");
        setHandoffResolution(intent.isHandoff ? effectiveResolution : null);
        setAdaptiveMode(!intent.requestedCaseConcept);
        setTrainingTarget(initialTarget);
        if (!initialTarget) {
          setEmptyReason("No concept currently has enough reviewed real ECGs for competency training.");
        } else {
          setEmptyReason("Choose a set length, then start when you are ready.");
        }
      } catch (err) {
        if (!cancelled) setError(readableApiError(err, "Training could not be loaded. Try again in a moment."));
      } finally {
        if (!cancelled) setBooting(false);
      }
    }
    void boot();
    return () => {
      cancelled = true;
    };
    // The initial load intentionally uses the freshly fetched catalog/profile.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bootRetryKey]);

  useEffect(() => {
    let cancelled = false;
    clinicalApi.bankCoverage()
      .then(({ applicationCoverage }) => {
        if (cancelled) return;
        const lanes = ["clinic", "ward", "ed"] as const;
        const destinations = new Map<string, "clinic" | "ward" | "ed">();
        Object.entries(applicationCoverage ?? {}).forEach(([concept, coverage]) => {
          const lane = lanes.find((candidate) => {
            const depth = coverage[candidate];
            return Boolean(depth && depth.items > 0 && depth.distinctEcgs > 0);
          });
          if (lane) destinations.set(concept, lane);
        });
        setClinicalDestinations(destinations);
      })
      .catch(() => {
        if (!cancelled) setClinicalDestinations(new Map());
      });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (
      booting
      || preferencesLoading
      || !learningPreferences
      || campaignPayload?.campaign
      || explicitCampaignLengthRef.current
      || campaignLengthTouchedRef.current
    ) return;
    setCampaignLength(focusedCampaignLength(learningPreferences.defaultSessionLength));
  }, [booting, campaignPayload?.campaign, learningPreferences, preferencesLoading]);

  useEffect(() => {
    if (!trainingTarget || campaignPayload?.campaign) return;
    let cancelled = false;
    setPoolLoading(true);
    setError(null);
    setSkillAvailability(null);
    setAvailabilityFailed(false);
    api.trainingAvailability(trainingTarget)
      .then((availability) => {
        if (!cancelled) setSkillAvailability(availability);
      })
      .catch((err) => {
        if (cancelled) return;
        setAvailabilityFailed(true);
        setError(readableApiError(err, "Available ECGs could not be checked. Try again."));
      })
      .finally(() => {
        if (!cancelled) setPoolLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [campaignPayload?.campaign, poolRetryKey, trainingTarget]);

  const selectedAvailability = skillAvailability?.subskills[trainingSubskill] ?? null;

  useEffect(() => {
    if (campaignPayload?.campaign || poolLoading || !trainingTarget) return;
    setEmptyReason(selectedAvailability?.available
      ? "Choose a set length, then start when you are ready."
      : "No distinct reviewed real ECGs currently support this concept and skill combination.");
  }, [campaignPayload?.campaign, poolLoading, selectedAvailability?.available, trainingTarget]);

  const selectorGroups = useMemo(() => {
    const seen = new Set<string>();
    return groups
      .filter((group) => group.enabled)
      .map((group) => ({
        ...group,
        concepts: group.concepts.filter((concept) => {
          if (!concept.available || concept.id === "qt_interval" || seen.has(concept.id)) return false;
          seen.add(concept.id);
          return true;
        }),
      }))
      .filter((group) => group.concepts.length > 0);
  }, [groups]);
  const searchableConcepts = useMemo(() => selectorGroups.flatMap((group) => (
    group.concepts.map((concept) => ({
      ...concept,
      groupLabel: group.label,
    }))
  )), [selectorGroups]);
  const suggestedAdaptiveTarget = resolvedAdaptiveTarget
    || chooseAdaptiveTarget(catalog, groups, profile, trainingSubskill);
  const focusedSkillOptions = TRAINING_SUBSKILLS.map((skill): FocusedSkillOption => ({
    ...skill,
    availability: availabilityFailed
      ? "error"
      : poolLoading || !trainingTarget || !skillAvailability
        ? "loading"
      : skillAvailability.subskills[skill.id]?.available
        ? "available"
        : "unavailable",
  }));
  const catalogById = useMemo(() => new Map(catalog.map((concept) => [concept.id, concept])), [catalog]);
  const allTopicOptions: FocusedTopicOption[] = searchableConcepts.map((concept) => {
    const category = focusedCategory(catalogById.get(concept.id)?.group ?? "foundations");
    const presentation = trainingMasteryPresentation(profile, concept.id, trainingSubskill);
    return {
      id: concept.id,
      label: concept.label,
      category,
      categoryLabel: focusedCategoryLabel(category),
      masteryLabel: presentation.label,
      masteryValue: presentation.value,
      recommended: concept.id === suggestedAdaptiveTarget,
    };
  });
  const normalizedConceptQuery = conceptQuery.trim().toLocaleLowerCase();
  const visibleTopicOptions = allTopicOptions
    .filter((concept) => (
      (topicCategory === "all" || concept.category === topicCategory)
      && (
        !normalizedConceptQuery
        || concept.label.toLocaleLowerCase().includes(normalizedConceptQuery)
        || concept.id.replaceAll("_", " ").toLocaleLowerCase().includes(normalizedConceptQuery)
        || concept.categoryLabel.toLocaleLowerCase().includes(normalizedConceptQuery)
      )
    ))
    .sort((left, right) => (
      Number(right.id === suggestedAdaptiveTarget) - Number(left.id === suggestedAdaptiveTarget)
      || Number(right.id === trainingTarget) - Number(left.id === trainingTarget)
      || (left.masteryValue ?? -1) - (right.masteryValue ?? -1)
      || left.label.localeCompare(right.label)
    ));
  const selectedTopicOption = allTopicOptions.find((topic) => topic.id === trainingTarget) ?? null;
  const evidenceConcept = handoffConcept || trainingTarget;
  const classificationTarget = trainingTarget;
  const clinicalResolution = evidenceConcept
    ? resolveHandoffTarget(evidenceConcept, clinicalDestinations.keys())
    : null;
  const clinicalLane = clinicalResolution?.exact
    ? clinicalDestinations.get(clinicalResolution.caseConcept)
    : undefined;
  const clinicalHref = clinicalResolution?.exact && clinicalLane
    ? `/practice?${new URLSearchParams({
        focus: clinicalResolution.caseConcept,
        subskill: "apply_in_context",
        lane: clinicalLane,
        length: "5",
      }).toString()}`
    : undefined;
  const taskVariant = campaignPayload?.current?.slot.position ?? 0;
  const answerContract = campaignPayload?.current?.classification
    ?? classificationContract(classificationTarget, taskVariant);
  const masteryPresentation = trainingMasteryPresentation(profile, evidenceConcept, trainingSubskill);
  const focusConfidence = evidenceConcept ? packet?.concept_confidence?.[evidenceConcept] : undefined;
  const selectedAnswerLabel = selectedAnswer === "present" ? answerContract.presentLabel
    : selectedAnswer === "absent" ? answerContract.absentLabel
      : "No decision";
  const groundedAnswerLabel = classificationTruth === "present" ? answerContract.presentLabel
    : classificationTruth === "absent" ? answerContract.absentLabel
      : "Ground truth unavailable";
  const waveformRois = packet?.ptbxl_plus.fiducials.rois ?? [];
  const viewerTask = taskForTraining(trainingSubskill, evidenceConcept);
  const subskillTask = campaignPayload?.current?.task ?? null;
  const interpretationSteps: FocusedInterpretationStep[] = subskillTask?.kind === "single_choice"
    && subskillTask.frameworkSteps?.length
    ? subskillTask.frameworkSteps.map((step) => {
        const fallback = DEFAULT_FOCUSED_INTERPRETATION_STEPS.find((candidate) => candidate.key === step.key);
        return { ...fallback, ...step, choices: step.choices ?? fallback?.choices } as FocusedInterpretationStep;
      })
    : DEFAULT_FOCUSED_INTERPRETATION_STEPS;
  const activeSubskillLabel = trainingSkillLabel(trainingSubskill);
  const primaryWorkspacePrompt = trainingSubskill === "synthesize"
    ? "Complete the formal rate-to-impression ECG sequence."
    : answerContract.prompt;
  const campaign = campaignPayload?.campaign ?? null;
  const campaignSummary: TrainingCampaignSummary | null = campaignPayload?.summary ?? null;
  const currentSlot = campaignPayload?.current?.slot ?? null;
  const pendingDraftKey = profile && campaign && campaignPayload?.current?.kind === "pending" && currentSlot
    ? `ecg-tool:focused-draft:v1:${profile.learnerId}:${campaign.campaignId}:${currentSlot.position}`
    : "";

  useEffect(() => {
    hydratedDraftKeyRef.current = "";
    if (!pendingDraftKey) return;
    try {
      const parsed = JSON.parse(window.sessionStorage.getItem(pendingDraftKey) ?? "null") as unknown;
      if (parsed && typeof parsed === "object") {
        const draft = parsed as Record<string, unknown>;
        if (draft.version === 1 && draft.concept === campaign?.conceptId && draft.subskill === campaign?.subskill) {
          if (draft.selectedAnswer === "present" || draft.selectedAnswer === "absent") setSelectedAnswer(draft.selectedAnswer);
          if (typeof draft.evidenceNote === "string") setEvidenceNote(draft.evidenceNote.slice(0, 2000));
          if (typeof draft.subskillTaskAnswer === "string") setSubskillTaskAnswer(draft.subskillTaskAnswer.slice(0, 240));
          if (draft.subskillTaskMatches && typeof draft.subskillTaskMatches === "object") {
            const matches = Object.fromEntries(Object.entries(draft.subskillTaskMatches as Record<string, unknown>)
              .filter((entry): entry is [string, string] => typeof entry[1] === "string")
              .slice(0, 20));
            setSubskillTaskMatches(matches);
          }
          if (typeof draft.subskillTaskValue === "string") setSubskillTaskValue(draft.subskillTaskValue.slice(0, 40));
          setStructuredInterpretation(focusedInterpretationFrom(draft.structuredInterpretation));
          if (
            typeof draft.interpretationStepIndex === "number"
            && Number.isInteger(draft.interpretationStepIndex)
            && draft.interpretationStepIndex >= 0
            && draft.interpretationStepIndex < FOCUSED_INTERPRETATION_KEYS.length
          ) setInterpretationStepIndex(draft.interpretationStepIndex);
          if (
            campaign?.subskill === "calibrate_confidence"
            && typeof draft.confidence === "number"
            && draft.confidence >= 1
            && draft.confidence <= 5
          ) setConfidence(draft.confidence);
          if (draft.viewerTaskEvidence && typeof draft.viewerTaskEvidence === "object") {
            setViewerTaskEvidence(draft.viewerTaskEvidence as ViewerTaskEvidence);
          }
        }
      }
    } catch {
      // A malformed or unavailable browser draft never blocks the server-owned campaign.
    }
    hydratedDraftKeyRef.current = pendingDraftKey;
  }, [campaign?.conceptId, campaign?.subskill, pendingDraftKey]);

  useEffect(() => {
    if (!pendingDraftKey || hydratedDraftKeyRef.current !== pendingDraftKey) return;
    try {
      window.sessionStorage.setItem(pendingDraftKey, JSON.stringify({
        version: 1,
        concept: campaign?.conceptId,
        subskill: campaign?.subskill,
        selectedAnswer,
        evidenceNote,
        subskillTaskAnswer,
        subskillTaskMatches,
        subskillTaskValue,
        structuredInterpretation,
        interpretationStepIndex,
        ...(campaign?.subskill === "calibrate_confidence" ? { confidence } : {}),
        viewerTaskEvidence,
      }));
    } catch {
      // Private browsing or quota limits must not interrupt a live practice set.
    }
  }, [campaign?.conceptId, campaign?.subskill, confidence, evidenceNote, interpretationStepIndex, pendingDraftKey, selectedAnswer, structuredInterpretation, subskillTaskAnswer, subskillTaskMatches, subskillTaskValue, viewerTaskEvidence]);
  const sessionCorrect = campaignSummary?.correct ?? 0;
  const sessionClassificationCorrect = campaignSummary?.classificationCorrect ?? 0;
  const fullTaskCorrect = campaignSummary?.fullTaskCorrect ?? 0;
  const independentReceipts = campaignSummary?.independentReceipts ?? 0;
  const committedCount = campaignSummary?.attempted ?? 0;
  const campaignTotal = campaign?.length ?? 0;

  useEffect(() => {
    if (!sessionComplete || !campaign) {
      setCompletedSessionRef(null);
      setCompletedSessionLookupPending(false);
      return;
    }
    let cancelled = false;
    setCompletedSessionLookupPending(true);
    api.learningSessions(20)
      .then((page) => {
        if (cancelled) return;
        const exact = page.items.find((item) => (
          item.mode === "training"
          && item.startedAt === campaign.createdAt
          && item.focusCompetencies.some((focus) => (
            focus.objectiveId === evidenceConcept && focus.subskill === campaign.subskill
          ))
        ));
        setCompletedSessionRef(exact?.sessionRef ?? null);
      })
      .catch(() => {
        if (!cancelled) setCompletedSessionRef(null);
      })
      .finally(() => {
        if (!cancelled) setCompletedSessionLookupPending(false);
      });
    return () => {
      cancelled = true;
    };
  }, [campaign, evidenceConcept, sessionComplete]);

  const readyForRapid = campaignTotal > 0 && (
    (trainingSubskill === "recognize" && sessionCorrect / campaignTotal >= 0.8)
    || (trainingSubskill === "synthesize" && fullTaskCorrect / campaignTotal >= 0.8)
  );
  const rapidTransferHref = trainingSubskill === "synthesize"
    ? `/rapid?${new URLSearchParams({
        focus: trainingTarget,
        receiptConcept: evidenceConcept,
        subskill: "synthesize",
        pace: "untimed",
        suggestedLength: "5",
      }).toString()}`
    : `/rapid?${new URLSearchParams({
        focus: evidenceConcept,
        receiptConcept: evidenceConcept,
        subskill: "recognize",
      }).toString()}`;
  const suggestedMastery = trainingMasteryPresentation(profile, suggestedAdaptiveTarget, trainingSubskill);
  const measurementRehearsal = result?.grade.trainingOutcomeKind === "unverified_rehearsal";
  const feedbackHeading = trainingFeedbackHeading({
    correct: result?.correct === true,
    expectedAnswer: classificationTruth,
    measurementRehearsal,
    subskillLabel: activeSubskillLabel,
  });
  const classificationCorrect = result?.classificationCorrect === true;
  const taskResult = (result?.grade.trainingSubskillTaskResult ?? null) as TrainingTaskResult | null;
  const correctTaskOption = taskResult?.kind === "single_choice" && subskillTask?.kind === "single_choice"
    ? subskillTask.options.find((option) => option.id === taskResult.correctAnswer)
    : null;
  const submittedTaskOption = taskResult?.kind === "single_choice" && subskillTask?.kind === "single_choice"
    ? subskillTask.options.find((option) => option.id === taskResult.submittedAnswer)
    : null;
  const commitGaps = missingCommitRequirements();
  const evidenceNoteRequired = (trainingSubskill === "measure" && !viewerTask)
    || (trainingSubskill === "localize" && (
      evidenceConcept.includes("lead_territor") || evidenceConcept.includes("frontal_lead_map")
    ));
  const feedbackEvidenceConcept = trainingSubskill === "measure"
    ? evidenceConcept
    : classificationTruth === "absent" && caseFocus
      ? caseFocus
      : evidenceConcept;
  const feedbackEvidenceDomain = hintDomain(feedbackEvidenceConcept);
  const reviewWaveformRois = waveformRois
    .filter((roi) => (
      roi.concept === feedbackEvidenceDomain.segment
      && feedbackEvidenceDomain.leads.includes(roi.lead)
    ))
    .slice(0, 6);
  const reviewedEvidenceLabels = [...new Set(
    reviewWaveformRois
      .map((roi) => `${roi.lead} · ${roi.label.replaceAll("_", " ")}`),
  )].slice(0, 3);
  const carryForwardCopy = measurementRehearsal
    ? "Repeat this method on an ECG with a verified numeric target before treating the value as accurate."
    : result?.correct && classificationCorrect
      ? `Carry the same waveform evidence and ${activeSubskillLabel.toLowerCase()} reasoning into a fresh mixed ECG.`
      : result?.correct
        ? `Your ${activeSubskillLabel.toLowerCase()} task was met, but the target-pattern decision was not. Re-read the highlighted waveform before moving on.`
        : classificationCorrect
          ? `Your target-pattern decision was correct. Rework the ${activeSubskillLabel.toLowerCase()} task before treating this skill as secure.`
          : `Recheck both the highlighted evidence for ${conceptLabel(classificationTarget)} and the ${activeSubskillLabel.toLowerCase()} task.`;
  const viewerState = useMemo(
    () => ({ selectedPoint, trainingTarget: evidenceConcept, groundedCaseTarget: trainingTarget, trainingSubskill, viewerTaskEvidence, hintsUsed, committed: Boolean(result) }),
    [selectedPoint, evidenceConcept, trainingTarget, trainingSubskill, viewerTaskEvidence, hintsUsed, result],
  );

  function clearResponseState() {
    setResult(null);
    setSelectedAnswer("");
    setClassificationTruth(null);
    setEvidenceNote("");
    setSubskillTaskAnswer("");
    setSubskillTaskMatches({});
    setSubskillTaskValue("");
    setStructuredInterpretation({ ...EMPTY_FOCUSED_INTERPRETATION });
    setInterpretationStepIndex(0);
    setConfidence(null);
    setHintsUsed(0);
    setHintText("");
    setSelectedPoint(null);
    setViewerActions([]);
    setViewerTaskEvidence(null);
    setSubskillReceipt(null);
  }

  function clearWorkspace(message: string) {
    clearResponseState();
    setCaseFocus("");
    setCaseSummary(null);
    setPacket(null);
    setSessionComplete(false);
    setShowSetReview(false);
    setCompletedSessionRef(null);
    setCompletedSessionLookupPending(false);
    setEmptyReason(message);
  }

  function applyCampaignPayload(next: TrainingCampaignPayload, receiptConceptOverride?: string) {
    setCampaignPayload(next);
    const nextCampaign = next.campaign;
    if (!nextCampaign) {
      clearWorkspace("Choose a set length, then start when you are ready.");
      return;
    }
    setTrainingTarget(nextCampaign.conceptId);
    if (isLearningSubskill(nextCampaign.subskill)) setTrainingSubskill(nextCampaign.subskill);
    setCampaignLength(nextCampaign.requestedLength);
    setSessionComplete(nextCampaign.status === "complete");
    if (nextCampaign.status !== "complete") setShowSetReview(false);

    const current = next.current;
    if (!current) {
      if (nextCampaign.status === "complete") setShowSetReview(true);
      setCaseFocus("");
      setCaseSummary(null);
      setPacket(null);
      clearResponseState();
      setEmptyReason(nextCampaign.status === "complete"
        ? "Training set complete. Your results and ECG history are saved."
        : "Preparing the next unique ECG in this set.");
      return;
    }

    setCaseFocus(current.slot.caseFocus ?? "");
    setCaseSummary(current.case);
    setPacket(current.packet);
    setEmptyReason(null);
    if (current.kind === "pending") {
      clearResponseState();
      return;
    }

    const answer = current.answer ?? next.answer;
    if (!answer) {
      clearResponseState();
      return;
    }
    const response = answer.response;
    setSelectedAnswer(response.selectedAnswer);
    setClassificationTruth(response.expectedAnswer);
    setEvidenceNote(response.evidenceNote ?? "");
    setSubskillTaskAnswer(response.subskillTaskAnswer ?? "");
    setSubskillTaskMatches(response.subskillTaskMatches ?? {});
    setSubskillTaskValue(response.subskillTaskValue == null ? "" : String(response.subskillTaskValue));
    setStructuredInterpretation(focusedInterpretationFrom(response.structuredInterpretation));
    setInterpretationStepIndex(FOCUSED_INTERPRETATION_KEYS.length - 1);
    setConfidence(response.confidence);
    setHintsUsed(response.hintsUsed);
    setViewerTaskEvidence(response.viewerTaskEvidence ?? null);
    setHintText(response.hintsUsed ? "A visual hint was used before this answer was checked." : "");
    setSubskillReceipt(answer.receipt.effectiveEvidenceLevel === "independent_transfer"
      ? `Progress updated: ${conceptLabel(receiptConceptOverride || handoffConcept || nextCampaign.conceptId)} · ${trainingSkillLabel(nextCampaign.subskill)} · ${answer.summary.correct ? "met" : "recheck"}.`
      : `Practice saved: ${conceptLabel(receiptConceptOverride || handoffConcept || nextCampaign.conceptId)} · ${trainingSkillLabel(nextCampaign.subskill)}.`);
    setResult({
      correct: answer.summary.correct,
      classificationCorrect: answer.summary.classificationCorrect,
      focusGrounded: answer.summary.focusGrounded,
      grade: answer.grade,
    });
    const feedbackPlan = buildHintPlan(
      nextCampaign.subskill === "measure"
        ? (receiptConceptOverride || handoffConcept || nextCampaign.conceptId)
        : response.expectedAnswer === "present"
          ? nextCampaign.conceptId
          : (current.slot.caseFocus ?? nextCampaign.conceptId),
      current.packet.ptbxl_plus.fiducials.rois ?? [],
      current.packet.waveform.leads,
    );
    setViewerActions(feedbackPlan.actions);
  }

  async function startCampaign(
    replaceActive = replaceActiveOnStart,
    requestedLength = campaignLength,
  ) {
    if (!trainingTarget || !selectedAvailability?.available) return;
    setLoading(true);
    setError(null);
    try {
      const contextKey = new URLSearchParams({
        receiptConcept: evidenceConcept,
        returnTo,
        adaptive: String(adaptiveMode),
      }).toString();
      const next = await api.startTrainingCampaign({
        conceptId: trainingTarget,
        subskill: trainingSubskill,
        length: requestedLength,
        contextKey,
        replaceActive,
      });
      setReplaceActiveOnStart(false);
      applyCampaignPayload(next, evidenceConcept);
    } catch (err) {
      setError(readableApiError(err, "The training set could not be started. Try again."));
    } finally {
      setLoading(false);
    }
  }

  async function abandonCurrentCampaign() {
    if (!campaign || campaign.status !== "active") return;
    setLoading(true);
    setError(null);
    try {
      await api.abandonTrainingCampaign(campaign.campaignId);
      if (pendingDraftKey) window.sessionStorage.removeItem(pendingDraftKey);
      setConfirmAbandon(false);
      setCampaignPayload(null);
      setReplaceActiveOnStart(false);
      clearWorkspace("Training set closed. Choose a skill and length to start again.");
    } catch (err) {
      setError(readableApiError(err, "The training set could not be closed. Try again."));
      closeAbandonDialog();
    } finally {
      setLoading(false);
    }
  }

  async function prepareNextWeakConcept() {
    if (!campaign) return;
    setLoading(true);
    setError(null);
    try {
      const target = await findEligibleAdaptiveTarget(trainingSubskill, trainingTarget);
      if (!target) throw new Error("No other reviewed topic is ready for this exact skill yet.");
      setCampaignPayload(null);
      setReplaceActiveOnStart(false);
      setHandoffConcept("");
      setHandoffResolution(null);
      setAdaptiveMode(true);
      setResolvedAdaptiveTarget(target);
      setSkillAvailability(null);
      setAvailabilityFailed(false);
      setPoolLoading(true);
      setTrainingTarget(target);
      campaignLengthTouchedRef.current = true;
      setCampaignLength(5);
      clearWorkspace("Finding fresh ECGs for the skill that needs the most practice…");
    } catch (err) {
      setError(readableApiError(err, "The next recommended skill could not be prepared. Try again."));
    } finally {
      setLoading(false);
    }
  }

  function resetCurrentSet() {
    void startCampaign(Boolean(campaign));
  }

  function startShortSet() {
    campaignLengthTouchedRef.current = true;
    setCampaignLength(5);
    void startCampaign(Boolean(campaign), 5);
  }

  function changeTarget(value: string) {
    if (campaign || value === trainingTarget) return;
    clearWorkspace("Finding fresh ECGs for this skill…");
    setHandoffConcept("");
    setHandoffResolution(null);
    setAdaptiveMode(false);
    setSkillAvailability(null);
    setAvailabilityFailed(false);
    setPoolLoading(true);
    setTrainingTarget(value);
  }

  function changeSubskill(value: string) {
    if (!isLearningSubskill(value) || campaign) return;
    clearWorkspace("Rechecking the real-ECG pool for this subskill…");
    setTrainingSubskill(value);
    setResolvedAdaptiveTarget("");
    const target = adaptiveMode ? chooseAdaptiveTarget(catalog, groups, profile, value) : trainingTarget;
    if (adaptiveMode && target !== trainingTarget) {
      setSkillAvailability(null);
      setAvailabilityFailed(false);
      setPoolLoading(true);
    }
    setTrainingTarget(target);
    if (adaptiveMode) void enableAdaptiveMode(value);
  }

  async function loadNextAdaptiveDrill() {
    if (!campaign || sessionComplete) return;
    setLoading(true);
    setError(null);
    try {
      const next = await api.nextTrainingCampaignCase(campaign.campaignId);
      applyCampaignPayload(next, evidenceConcept);
    } catch (err) {
      setError(readableApiError(err, "The next ECG could not be loaded. Try again."));
    } finally {
      setLoading(false);
    }
  }

  async function findEligibleAdaptiveTarget(subskill: LearningSubskill, exclude = "") {
    const candidates = rankAdaptiveTargets(catalog, groups, profile, subskill)
      .filter((candidate) => candidate !== exclude);
    for (const candidate of candidates) {
      const cached = candidate === trainingTarget ? skillAvailability : null;
      try {
        const availability = cached ?? await api.trainingAvailability(candidate);
        if (availability.subskills[subskill]?.available) return candidate;
      } catch {
        // Try the next ranked topic; a transient pool failure should not turn
        // an unrelated topic into the recommendation.
      }
    }
    return "";
  }

  async function enableAdaptiveMode(subskill = trainingSubskill) {
    if (campaign) return;
    setLoading(true);
    setError(null);
    try {
      const target = await findEligibleAdaptiveTarget(subskill);
      if (!target) throw new Error("No reviewed ECG pool is ready for that skill yet.");
      clearWorkspace("Finding ECGs for the skill that needs the most practice…");
      setAdaptiveMode(true);
      setResolvedAdaptiveTarget(target);
      setHandoffConcept("");
      setHandoffResolution(null);
      setConceptQuery("");
      setTopicCategory("all");
      setShowAllTopics(false);
      if (target !== trainingTarget) {
        setSkillAvailability(null);
        setAvailabilityFailed(false);
        setPoolLoading(true);
      } else if (!skillAvailability) {
        setAvailabilityFailed(false);
        setPoolLoading(true);
        setPoolRetryKey((value) => value + 1);
      }
      setTrainingTarget(target);
    } catch (err) {
      setError(readableApiError(err, "A runnable recommendation could not be found. Choose a topic manually."));
    } finally {
      setLoading(false);
    }
  }

  function subskillEvidenceIsValid(evidence = viewerTaskEvidence) {
    if (trainingSubskill === "recognize") return true;
    if (trainingSubskill === "calibrate_confidence") return confidence !== null;
    if (trainingSubskill === "localize") {
      const pointValid = evidence?.mode === "point" && Boolean(evidence.point);
      if (!pointValid) return false;
      if (evidenceConcept.includes("lead_territor") || evidenceConcept.includes("frontal_lead_map")) {
        const note = evidenceNote.toLowerCase();
        return ["ii", "iii", "avf"].every((lead) => new RegExp(`(^|[^a-z])${lead}([^a-z]|$)`, "i").test(note))
          && (note.includes("inferior") || note.includes("contiguous"));
      }
      return true;
    }
    if (trainingSubskill === "measure") {
      if (!viewerTask) return evidenceNote.trim().length >= 15 && /\d/.test(evidenceNote);
      const traceComplete = evidence?.mode === "caliper"
        && Number.isFinite(evidence.valueMs)
        && evidence.valueMs > 0;
      if (!traceComplete) return false;
      if (subskillTask?.kind !== "numeric_fill_in") return false;
      const value = Number(subskillTaskValue);
      return subskillTaskValue.trim() !== ""
        && Number.isFinite(value)
        && value >= subskillTask.minValue
        && value <= subskillTask.maxValue;
    }
    if (trainingSubskill === "synthesize") {
      return FOCUSED_INTERPRETATION_KEYS.every((key) => structuredInterpretation[key].trim().length > 0)
        && structuredInterpretation.synthesis.trim().length >= 12
        && subskillTask?.kind === "single_choice"
        && Boolean(subskillTaskAnswer);
    }
    if (["discriminate", "explain_mechanism", "apply_in_context"].includes(trainingSubskill)) {
      if (subskillTask?.kind === "single_choice") return Boolean(subskillTaskAnswer);
      if (subskillTask?.kind === "matching") {
        const selected = subskillTask.rows.map((row) => subskillTaskMatches[row.id]);
        const choices = new Set(subskillTask.choices.map((choice) => choice.id));
        return selected.every((choiceId): choiceId is string => Boolean(choiceId && choices.has(choiceId)))
          && new Set(selected).size === subskillTask.rows.length;
      }
      return false;
    }
    return false;
  }

  function missingCommitRequirements(): string[] {
    const gaps: string[] = [];
    if (!selectedAnswer) gaps.push("Choose the target-pattern decision.");

    if (trainingSubskill === "calibrate_confidence" && confidence === null) {
      gaps.push("Choose how certain you are before checking this calibration task.");
    }

    if (trainingSubskill === "localize") {
      if (viewerTaskEvidence?.mode !== "point" || !viewerTaskEvidence.point) {
        gaps.push("Place one evidence point on the waveform.");
      }
      if (
        (evidenceConcept.includes("lead_territor") || evidenceConcept.includes("frontal_lead_map"))
        && !(["ii", "iii", "avf"].every((lead) => new RegExp(`(^|[^a-z])${lead}([^a-z]|$)`, "i").test(evidenceNote.toLowerCase()))
          && (evidenceNote.toLowerCase().includes("inferior") || evidenceNote.toLowerCase().includes("contiguous")))
      ) {
        gaps.push("Name leads II, III, aVF and the inferior/contiguous relationship in the evidence note.");
      }
    } else if (trainingSubskill === "measure") {
      if (viewerTask) {
        if (
          viewerTaskEvidence?.mode !== "caliper"
          || !Number.isFinite(viewerTaskEvidence.valueMs)
          || (viewerTaskEvidence.valueMs ?? 0) <= 0
        ) {
          gaps.push("Place both caliper points on the waveform.");
        }
        if (subskillTask?.kind === "numeric_fill_in") {
          const value = Number(subskillTaskValue);
          if (
            subskillTaskValue.trim() === ""
            || !Number.isFinite(value)
            || value < subskillTask.minValue
            || value > subskillTask.maxValue
          ) gaps.push(`Enter a ${subskillTask.minValue}–${subskillTask.maxValue} ${subskillTask.unit} estimate.`);
        }
      } else if (evidenceNote.trim().length < 15 || !/\d/.test(evidenceNote)) {
        gaps.push("Record a numeric estimate and measurement method in the evidence note.");
      }
    } else if (trainingSubskill === "synthesize") {
      const missingSteps = interpretationSteps.filter((step) => !structuredInterpretation[step.key].trim());
      if (missingSteps.length) gaps.push(`Complete ${missingSteps.length} remaining systematic interpretation step${missingSteps.length === 1 ? "" : "s"}.`);
      if (structuredInterpretation.synthesis.trim() && structuredInterpretation.synthesis.trim().length < 12) {
        gaps.push("Write a concise final impression of at least 12 characters.");
      }
      if (subskillTask?.kind === "single_choice" && !subskillTaskAnswer) {
        gaps.push("Choose the reviewed evidence-bounded synthesis in the final step.");
      }
    } else if (["discriminate", "explain_mechanism", "apply_in_context"].includes(trainingSubskill)) {
      if (subskillTask?.kind === "single_choice" && !subskillTaskAnswer) {
        gaps.push("Answer the selected-skill question.");
      } else if (subskillTask?.kind === "matching") {
        const validChoices = new Set(subskillTask.choices.map((choice) => choice.id));
        const selected = subskillTask.rows.map((row) => subskillTaskMatches[row.id]);
        if (
          !selected.every((choiceId): choiceId is string => Boolean(choiceId && validChoices.has(choiceId)))
          || new Set(selected).size !== subskillTask.rows.length
        ) gaps.push("Complete every match, using each evidence source once.");
      }
    }
    return gaps;
  }

  function requestHint() {
    if (!packet || result || hintsUsed > 0) return;
    const plan = buildHintPlan(evidenceConcept, waveformRois, packet.waveform.leads);
    setHintsUsed(1);
    setHintText(plan.text);
    setViewerActions(plan.actions);
  }

  async function commitAnswer() {
    if (!campaign || !caseSummary || !packet || !selectedAnswer || result || !subskillEvidenceIsValid()) return;
    setLoading(true);
    setError(null);
    try {
      const next = await api.submitTrainingCampaignCase(campaign.campaignId, {
        caseId: caseSummary.caseId,
        selectedAnswer,
        confidence: trainingSubskill === "calibrate_confidence" ? confidence : null,
        hintsUsed,
        evidenceNote,
        viewerTaskEvidence,
        subskillTaskAnswer,
        subskillTaskMatches,
        subskillTaskValue: subskillTaskValue.trim() === "" ? null : Number(subskillTaskValue),
        structuredInterpretation: trainingSubskill === "synthesize" ? structuredInterpretation : null,
        receiptConcept: evidenceConcept,
      });
      if (pendingDraftKey) window.sessionStorage.removeItem(pendingDraftKey);
      applyCampaignPayload(next, evidenceConcept);
      try {
        setProfile(await api.profile());
      } catch {
        // The durable answer and receipt already succeeded; profile refresh can wait for reload.
      }
    } catch (err) {
      setError(readableApiError(err, "Your answer could not be saved. Try again."));
    } finally {
      setLoading(false);
    }
  }

  if (booting) {
    return (
      <div className="page train-page">
        <div className="panel pad train-loading">Loading your skills and available ECGs…</div>
      </div>
    );
  }

  if (!campaign) {
    return (
      <FocusedPracticeSetup
        returnTo={returnTo}
        returnLabel={returnTo ? learningReturnLabel(returnTo) : undefined}
        notices={(
          <>
            {returnTo ? (
              <p className="selection-note train-setup-handoff">
                This practice was chosen from your last activity for <strong>{conceptLabel(evidenceConcept)} · {trainingSkillLabel(trainingSubskill)}</strong>. Your place there is saved.
                {handoffResolution && !handoffResolution.exact ? <> The closest available ECG topic is <strong>{conceptLabel(handoffResolution.caseConcept)}</strong>.</> : null}
              </p>
            ) : null}
            {replaceActiveOnStart ? (
              <p className="uncertainty train-setup-handoff" role="status">
                Starting this plan will close your saved set. Completed ECGs will remain in your learning history.
              </p>
            ) : null}
          </>
        )}
        errorNotice={error ? (
          <div className="warning train-error mode-recovery-notice" role="alert">
            <span>{error}</span>
            <button className="button subtle small" type="button" onClick={() => {
              setBootRetryKey((value) => value + 1);
              setPoolRetryKey((value) => value + 1);
            }}>
              <RefreshCw size={15} aria-hidden="true" /> Retry loading
            </button>
          </div>
        ) : null}
        query={conceptQuery}
        onQueryChange={(value) => {
          setConceptQuery(value);
          setShowAllTopics(false);
        }}
        category={topicCategory}
        categories={[...FOCUSED_CATEGORIES]}
        onCategoryChange={(value) => {
          setTopicCategory(value);
          setShowAllTopics(false);
        }}
        topics={visibleTopicOptions}
        selectedTopic={selectedTopicOption}
        selectedTopicId={trainingTarget}
        onTopicSelect={(value) => {
          changeTarget(value);
          setConceptQuery("");
        }}
        showAllTopics={showAllTopics || Boolean(normalizedConceptQuery)}
        onToggleAllTopics={() => setShowAllTopics((value) => !value)}
        skills={focusedSkillOptions}
        selectedSkill={trainingSubskill}
        onSkillSelect={changeSubskill}
        adaptiveMode={adaptiveMode}
        recommendationText={adaptiveMode
          ? `${suggestedMastery.label}. This plan starts with ${trainingSkillLabel(trainingSubskill).toLowerCase()}.`
          : `${masteryPresentation.label}. You can switch the skill without changing the topic.`}
        onUseRecommendation={enableAdaptiveMode}
        campaignLength={campaignLength}
        visibleLengths={FOCUSED_VISIBLE_LENGTHS}
        extendedLengths={[]}
        onLengthChange={(value) => {
          campaignLengthTouchedRef.current = true;
          setCampaignLength(value);
        }}
        poolLoading={poolLoading}
        poolAvailable={Boolean(selectedAvailability?.available)}
        poolMessage={emptyReason}
        loading={loading}
        replaceActive={replaceActiveOnStart}
        onStart={() => void startCampaign()}
      />
    );
  }

  if (sessionComplete && showSetReview) {
    const lunaSetScope = `training-set:${campaign.campaignId}:${campaign.length}`;
    return (
      <FocusedSetReview
        conceptId={evidenceConcept}
        conceptLabel={conceptLabel(evidenceConcept)}
        skillLabel={trainingSkillLabel(trainingSubskill)}
        total={campaign.length}
        summary={campaignSummary}
        masteryLabel={masteryPresentation.label}
        readyForRapid={readyForRapid}
        rapidHref={rapidTransferHref}
        rapidTitle={trainingSubskill === "synthesize" ? "Try an unannounced full read" : undefined}
        rapidDetail={trainingSubskill === "synthesize" ? "Transfer the same sequence into Rapid Practice" : undefined}
        sessionRef={completedSessionRef}
        sessionLookupPending={completedSessionLookupPending}
        loading={loading}
        error={error}
        tutor={(
          <TutorChat
            mode="practice"
            roleLabel="Luna · set review"
            lessonId={lunaSetScope}
            threadScope={lunaSetScope}
            viewerState={{ activity: "training_set_debrief" }}
            trainingSetContext={{
              campaignId: campaign.campaignId,
              answerCount: campaign.length,
              version: "training-set-debrief-v1",
            }}
            openingPrompt="Ask Luna to explain a recurring miss, connect this set to your recent progress, or create a short follow-up check. Luna uses the saved results from this set."
            resetKey={lunaSetScope}
            collapsedByDefault
          />
        )}
        onRepeat={resetCurrentSet}
        onRepeatShort={startShortSet}
        onPracticeRecommendation={suggestedAdaptiveTarget && suggestedAdaptiveTarget !== trainingTarget
          ? () => void prepareNextWeakConcept()
          : undefined}
        clinicalHref={clinicalHref}
        returnTo={returnTo}
        returnLabel={returnTo ? learningReturnLabel(returnTo) : undefined}
      />
    );
  }

  const workspacePhase = result ? "feedback" : sessionComplete ? "complete" : "response";
  const debriefPanel = sessionComplete ? (
    <section className="panel pad train-debrief-panel" aria-live="polite">
      <p className="eyebrow">Training set complete</p>
      <h2>{sessionCorrect.toLocaleString()}/{campaign.length.toLocaleString()} {trainingSkillLabel(trainingSubskill).toLowerCase()} skill checks met</h2>
      <p className="muted">
        Topic decision: {sessionClassificationCorrect.toLocaleString()}/{campaign.length.toLocaleString()} correct · both the decision and selected skill: {fullTaskCorrect.toLocaleString()}/{campaign.length.toLocaleString()}. {independentReceipts} fresh mixed ECG check{independentReceipts === 1 ? "" : "s"} contributed to your mastery estimate.
      </p>
      <div className="selection-note train-next-recommendation">
        <strong><Sparkles size={15} aria-hidden="true" /> Recommended next</strong>
        {readyForRapid ? (
          <p>{trainingSubskill === "synthesize"
            ? "You completed at least 80% of both the formal interpretation task and the target-pattern check. Try the same sequence in Rapid Practice, where the target is no longer announced."
            : "You met at least 80% of the focused recognition checks. Move to Rapid Practice for an independent mixed read where the target is no longer named in advance."}</p>
        ) : (
          <p>Try another focused set. It will mix the target with close comparisons and fresh ECGs.</p>
        )}
      </div>
      <div className="actions train-debrief-actions">
        <button className="button primary" type="button" onClick={resetCurrentSet} disabled={loading}>
          <RefreshCw size={16} aria-hidden="true" /> Start another set
        </button>
        {readyForRapid ? (
          <Link className="button" href={rapidTransferHref}>
            {trainingSubskill === "synthesize" ? "Start an unannounced full read" : "Start mixed Rapid"} <ArrowRight size={16} aria-hidden="true" />
          </Link>
        ) : null}
        {!handoffConcept && suggestedAdaptiveTarget && suggestedAdaptiveTarget !== trainingTarget ? (
          <button className="button subtle" type="button" onClick={() => void prepareNextWeakConcept()} disabled={loading}>
            Practice a recommended topic
          </button>
        ) : null}
        {returnTo ? <Link className="button subtle" href={returnTo}><ArrowLeft size={16} aria-hidden="true" /> {learningReturnLabel(returnTo)}</Link> : null}
      </div>
    </section>
  ) : null;

  return (
    <div className="page train-page train-page-active">
      <LearningWorkspaceShell className="train-runner" phase={workspacePhase} tutorResetKey={caseSummary?.caseId}>
        <SessionBar className="train-session-bar" tutorAvailable={Boolean(result && caseSummary)} tutorLabel="Ask Luna">
          <section className="train-session-summary" aria-label="Focused training set">
            <div className="train-session-identity">
              <span className="eyebrow">Focused practice · ECG {currentSlot ? currentSlot.position + 1 : committedCount} of {campaign.length.toLocaleString()}</span>
              <strong>{conceptLabel(evidenceConcept)} · {activeSubskillLabel}</strong>
            </div>
            <progress
              className="train-session-progress-native"
              value={committedCount}
              max={Math.max(1, campaign.length)}
              aria-label={`${committedCount} of ${campaign.length} cases completed`}
            />
            <span className="train-session-count">{committedCount.toLocaleString()} complete</span>
          </section>
          {returnTo ? <Link className="button subtle small train-return-link" href={returnTo}><ArrowLeft size={15} aria-hidden="true" /> {learningReturnLabel(returnTo)}</Link> : null}
          {!sessionComplete ? (
            <button ref={abandonTriggerRef} className="button warn small train-abandon-button" type="button" onClick={() => setConfirmAbandon(true)} disabled={loading || confirmAbandon}>
              <XCircle size={15} aria-hidden="true" /> Exit set
            </button>
          ) : null}
        </SessionBar>

        <WorkspaceNotices>
          {confirmAbandon ? (
            <div className="train-abandon-modal-layer">
              <button className="train-abandon-backdrop" type="button" tabIndex={-1} aria-hidden="true" onClick={closeAbandonDialog} />
              <section
                ref={abandonDialogRef}
                className="panel pad train-abandon-confirmation"
                role="alertdialog"
                aria-modal="true"
                aria-labelledby="train-abandon-title"
                aria-describedby="train-abandon-description"
              >
                <h2 id="train-abandon-title">Leave this training set?</h2>
                <p id="train-abandon-description" className="muted">
                  Completed ECGs stay in your learning history. Your current unsubmitted answer will be discarded, and this {campaign.length.toLocaleString()}-ECG set cannot be resumed.
                </p>
                <div className="actions">
                  <button className="button warn" type="button" onClick={() => void abandonCurrentCampaign()} disabled={loading}>
                    Leave set and change setup
                  </button>
                  <button ref={keepTrainingRef} className="button" type="button" onClick={closeAbandonDialog} disabled={loading}>
                    Keep training
                  </button>
                </div>
              </section>
            </div>
          ) : null}
          {returnTo ? (
            <p className="selection-note train-active-handoff">
              Launched from another learning activity for <strong>{conceptLabel(evidenceConcept)} · {trainingSkillLabel(trainingSubskill)}</strong>. Your prior place is saved.
              {handoffResolution && !handoffResolution.exact ? <> The first ECG uses the closest supported pattern: <strong>{conceptLabel(handoffResolution.caseConcept)}</strong>.</> : null}
            </p>
          ) : null}
          {error ? <div className="warning train-error" role="alert">{error}</div> : null}
        </WorkspaceNotices>

        {packet && !result && !sessionComplete ? (
          <section className="train-mobile-task-dock" aria-label="Current training task">
            <div>
              <span>{conceptLabel(classificationTarget)} · {activeSubskillLabel}</span>
              <strong>{primaryWorkspacePrompt}</strong>
              {viewerTask ? <small>On trace: {viewerTask.prompt}</small> : null}
            </div>
            <a className="button subtle small" href="#train-response-task">Go to response</a>
          </section>
        ) : null}

        <WorkspaceBody className={`train-active-workspace${trainingSubskill === "synthesize" && !result ? " train-systematic-workspace" : ""}`}>
          <WaveformPane className="train-viewer-pane" label="Training ECG waveform">
            {packet ? (
              <header className="train-waveform-taskbar">
                <div>
                  <span>{result ? "Review the tracing" : `ECG ${currentSlot ? currentSlot.position + 1 : committedCount + 1} · ${activeSubskillLabel}`}</span>
                  <strong>{result
                    ? `Compare your response with the reviewed evidence for ${conceptLabel(classificationTarget)}.`
                    : primaryWorkspacePrompt}</strong>
                </div>
                {viewerTask && !result ? <small>{viewerTask.prompt}</small> : <small>{conceptLabel(evidenceConcept)}</small>}
              </header>
            ) : null}
            {caseSummary ? (
              <ECGViewer
                ecgRef={caseSummary.caseId}
                waveformScope={{ kind: "training", campaignId: campaign.campaignId }}
                actions={viewerActions}
                groundedRois={result ? reviewWaveformRois : []}
                gradingRois={result ? reviewWaveformRois : []}
                onCoordinate={setSelectedPoint}
                medianBeats={packet?.ptbxl_plus.median_beats ?? null}
                task={!result ? viewerTask : undefined}
                onTaskEvidence={setViewerTaskEvidence}
                taskEvidence={!result ? viewerTaskEvidence : null}
                onTaskReset={() => setViewerTaskEvidence(null)}
                gradingMode="deferred"
                toolbar="practice"
                reviewMode={Boolean(result)}
                reviewEvidence={result ? viewerTaskEvidence : null}
              />
            ) : (
              <div className="panel pad train-empty" role="status" aria-live="polite">{emptyReason ?? "Preparing the ECG…"}</div>
            )}
          </WaveformPane>

          <ResponseRail className={`train-response-rail${trainingSubskill === "synthesize" && !result ? " train-response-rail-systematic" : ""}`} label={result ? "Training feedback" : sessionComplete ? "Set review" : "Training response"} phase={workspacePhase}>
            {result && packet ? (
              <>
                <section className="panel pad train-feedback-panel" aria-live="polite">
                  <h2>
                    {measurementRehearsal || result.correct ? <CheckCircle2 size={18} aria-hidden="true" /> : <XCircle size={18} aria-hidden="true" />}
                    {feedbackHeading}
                  </h2>
                  <div className="train-feedback-axes" aria-label="Separate pattern and skill results">
                    <div data-status={classificationCorrect ? "met" : "review"}>
                      <span>Target-pattern decision</span>
                      <strong>{classificationCorrect ? "Correct" : "Needs review"}</strong>
                      <small>Reviewed answer: {groundedAnswerLabel}</small>
                    </div>
                    <div data-status={measurementRehearsal ? "rehearsal" : result.correct ? "met" : "review"}>
                      <span>{activeSubskillLabel}</span>
                      <strong>{measurementRehearsal ? "Rehearsal saved" : result.correct ? "Task met" : "Needs review"}</strong>
                      <small>{measurementRehearsal ? "No verified numeric key" : "Scored separately from the pattern decision"}</small>
                    </div>
                  </div>
                  <div className="train-review-story">
                    <section>
                      <span>What you chose</span>
                      <strong>{selectedAnswerLabel}</strong>
                      <p>{taskResult?.kind === "single_choice"
                        ? submittedTaskOption?.label ?? "No skill response"
                        : taskResult?.kind === "numeric_fill_in"
                          ? `${taskResult.submittedValue ?? "No value"} ${taskResult.unit}`
                          : taskResult?.kind === "matching"
                            ? `${taskResult.rows?.filter((row) => row.correct).length ?? 0} of ${taskResult.rows?.length ?? 0} pairs supported`
                            : evidenceNote.trim() || "Pattern decision only"}</p>
                    </section>
                    <section>
                      <span>What the ECG supports</span>
                      <strong>{groundedAnswerLabel}</strong>
                      <p>{classificationTruth === "absent" && caseFocus
                        ? `The closest supported contrast is ${conceptLabel(caseFocus)}. ${reviewedEvidenceLabels.length ? `${reviewedEvidenceLabels.join(" · ")}. ` : ""}${feedbackEvidenceDomain.text}`
                        : reviewedEvidenceLabels.length
                          ? `${reviewedEvidenceLabels.join(" · ")}. ${feedbackEvidenceDomain.text}`
                          : feedbackEvidenceDomain.text}</p>
                    </section>
                    <section>
                      <span>Why it matters</span>
                      <strong>{classificationCorrect === result.correct
                        ? classificationCorrect ? "The decision and reasoning agree" : "Both layers need review"
                        : "The two skills separated"}</strong>
                      <p>{measurementRehearsal
                        ? "This value is rehearsal because the ECG has no verified numeric key."
                        : classificationCorrect === result.correct
                          ? classificationCorrect
                            ? "You linked the target decision to the selected skill."
                            : "Recheck the waveform discriminator before repeating the task."
                          : "A correct label does not automatically prove the evidence skill—and the reverse is also true."}</p>
                    </section>
                    <section>
                      <span>Try next</span>
                      <strong>Carry one discriminator forward</strong>
                      <p>{carryForwardCopy}</p>
                    </section>
                  </div>
                  {taskResult?.kind === "numeric_fill_in" ? (
                    <section className="train-task-feedback" aria-label="Measurement answer review">
                      <strong>{taskResult.correct ? "Measurement within range" : "Measurement needs review"}</strong>
                      <p>
                        You entered {taskResult.submittedValue ?? "no value"} {taskResult.unit}. The reviewed ECG measurement is {taskResult.expectedValue} {taskResult.unit}
                        {taskResult.tolerance != null ? ` (accepted within ±${taskResult.tolerance} ${taskResult.unit})` : ""}.
                      </p>
                    </section>
                  ) : taskResult?.kind === "single_choice" && subskillTask?.kind === "single_choice" ? (
                    <section className="train-task-feedback" aria-label="Selected skill answer review">
                      <strong>{taskResult.correct ? "Selected-skill answer supported" : "Selected-skill answer needs review"}</strong>
                      <p>Correct response: <strong>{correctTaskOption?.label ?? "Reviewed key unavailable"}</strong></p>
                      {!taskResult.correct ? <p>Your response: {submittedTaskOption?.label ?? "No valid response"}</p> : null}
                    </section>
                  ) : taskResult?.kind === "matching" && subskillTask?.kind === "matching" ? (
                    <section className="train-task-feedback" aria-labelledby="train-matching-feedback-heading">
                      <strong id="train-matching-feedback-heading">Evidence source review</strong>
                      <ul>
                        {taskResult.rows?.map((rowResult) => {
                          const row = subskillTask.rows.find((candidate) => candidate.id === rowResult.rowId);
                          const correctChoice = subskillTask.choices.find((choice) => choice.id === rowResult.correctChoiceId);
                          const submittedChoice = subskillTask.choices.find((choice) => choice.id === rowResult.submittedChoiceId);
                          return (
                            <li className={rowResult.correct ? "correct" : "incorrect"} key={rowResult.rowId}>
                              <strong>{row?.clause ?? "Statement"}</strong>
                              <span>Correct source: {correctChoice?.label ?? rowResult.correctChoiceId}</span>
                              {!rowResult.correct && rowResult.submittedChoiceId ? (
                                <span>Your source: {submittedChoice?.label ?? rowResult.submittedChoiceId}</span>
                              ) : null}
                            </li>
                          );
                        })}
                      </ul>
                    </section>
                  ) : null}
                  {trainingSubskill === "synthesize" ? (
                    <FocusedInterpretationReview
                      submitted={taskResult?.systematicInterpretation ?? structuredInterpretation}
                      reviewed={taskResult?.reviewedFramework ?? []}
                      steps={interpretationSteps}
                    />
                  ) : null}
                  {!result.focusGrounded ? (
                    <p className="warning train-grounding-mismatch">
                      This ECG could not verify the selected training target, so it will not affect your mastery estimate.
                    </p>
                  ) : null}
                  {subskillReceipt ? <p className="selection-note train-mastery-delta">{subskillReceipt}</p> : null}
                  <div className="pill-row train-feedback-tags">
                    <span className={`pill ${result.correct || measurementRehearsal ? "" : "disabled"}`}>{conceptLabel(evidenceConcept)} · {trainingSkillLabel(trainingSubskill)}</span>
                    <span className={`pill ${classificationCorrect ? "" : "disabled"}`}>Pattern decision · {classificationCorrect ? "met" : "review"}</span>
                    {classificationTruth === "absent" ? <span className="pill">Contrast finding: {conceptLabel(caseFocus)}</span> : null}
                  </div>
                  {focusConfidence?.warnings.length ? (
                    <p className="uncertainty train-confidence-warning">Localized noise limits fine-detail claims; use the clearest displayed leads.</p>
                  ) : null}
                  {!sessionComplete ? (
                    <button className="button primary train-next-button" type="button" onClick={loadNextAdaptiveDrill} disabled={loading}>
                      Next ECG <ArrowRight size={16} aria-hidden="true" />
                    </button>
                  ) : (
                    <button className="button primary train-next-button" type="button" onClick={() => setShowSetReview(true)} disabled={loading}>
                      Review this set <ArrowRight size={16} aria-hidden="true" />
                    </button>
                  )}
                </section>

              </>
            ) : sessionComplete ? debriefPanel : packet ? (
              <>
                <section className="panel pad train-drill-panel" id="train-response-task">
                  {trainingSubskill === "synthesize" && subskillTask?.kind === "single_choice" ? (
                    <FocusedInterpretationStepper
                      value={structuredInterpretation}
                      onChange={setStructuredInterpretation}
                      activeIndex={interpretationStepIndex}
                      onActiveIndexChange={setInterpretationStepIndex}
                      steps={interpretationSteps}
                      classificationPrompt={answerContract.prompt}
                      classificationOptions={answerContract.options}
                      selectedClassification={selectedAnswer}
                      onClassificationChange={setSelectedAnswer}
                      synthesisPrompt={subskillTask.prompt}
                      synthesisOptions={subskillTask.options}
                      selectedSynthesis={subskillTaskAnswer}
                      onSynthesisChange={setSubskillTaskAnswer}
                      disabled={loading}
                    />
                  ) : (
                    <>
                    <div className="train-current-target">
                    <div>
                      <p className="eyebrow">Quick read</p>
                      <h2>{answerContract.prompt}</h2>
                      <strong className="train-current-concept">{conceptLabel(classificationTarget)} · first decision</strong>
                    </div>
                    <span className="pill">1</span>
                  </div>
                  <p className="muted train-task-prompt">
                    {trainingSubskill === "recognize"
                      ? "Focus on the crux of the tracing and make one concise pattern decision."
                      : <>Make a concise target decision first. The next prompt tests <strong>{activeSubskillLabel.toLowerCase()}</strong> without requiring a full interpretation sweep.</>}
                  </p>
                  {handoffResolution && !handoffResolution.exact ? (
                    <p className="selection-note train-task-note">
                      This activity uses the closest available ECG pattern while preserving your original learning target.
                    </p>
                  ) : null}
                  <div className="grid train-options" role="group" aria-label="Target decision">
                    {answerContract.options.map((option) => {
                      const selected = option.id === selectedAnswer;
                      return (
                        <button
                          className={`button ${selected ? "primary" : "subtle"} train-option`}
                          type="button"
                          key={option.id}
                          aria-pressed={selected}
                          onClick={() => setSelectedAnswer(option.id)}
                          disabled={loading}
                        >
                          {selected ? <CheckCircle2 size={16} aria-hidden="true" /> : <Target size={16} aria-hidden="true" />}
                          {option.label}
                        </button>
                      );
                    })}
                  </div>

                  {subskillTask && caseSummary ? (
                    <div className="panel pad train-subskill-task" data-kind={subskillTask.kind}>
                      <div className="train-subskill-heading">
                        <div>
                          <p className="eyebrow">Skill challenge · {subskillTask.kind === "single_choice" ? "choose one" : subskillTask.kind === "matching" ? "match evidence" : subskillTask.kind === "numeric_fill_in" ? "numeric fill-in" : "certainty check"}</p>
                          <h3>{subskillTask.prompt}</h3>
                        </div>
                        <span className="pill">2</span>
                      </div>
                      {subskillTask.kind === "single_choice" ? (
                        <div className="grid train-subskill-options" role="radiogroup" aria-label={subskillTask.prompt}>
                          {subskillTask.options.map((option) => {
                            const selected = subskillTaskAnswer === option.id;
                            return (
                              <button
                                className={`button ${selected ? "primary" : "subtle"}`}
                                key={option.id}
                                type="button"
                                role="radio"
                                aria-checked={selected}
                                onClick={() => setSubskillTaskAnswer(option.id)}
                                disabled={loading}
                              >
                                {selected ? <CheckCircle2 size={15} aria-hidden="true" /> : <Target size={15} aria-hidden="true" />}
                                {option.label}
                              </button>
                            );
                          })}
                        </div>
                      ) : subskillTask.kind === "matching" ? (
                        <fieldset className="train-subskill-matching" aria-describedby={`training-match-help-${campaign.position}`}>
                          <legend>Pair each statement with its best evidence source</legend>
                          <p id={`training-match-help-${campaign.position}`} className="muted">
                            Use each source once.
                          </p>
                          <div className="train-subskill-matching-rows">
                            {subskillTask.rows.map((row, index) => {
                              const selectedElsewhere = new Set(
                                Object.entries(subskillTaskMatches)
                                  .filter(([rowId]) => rowId !== row.id)
                                  .map(([, choiceId]) => choiceId),
                              );
                              return (
                                <div className="train-subskill-matching-row" key={row.id}>
                                  <div>
                                    <span>Statement {index + 1}</span>
                                    <strong>{row.clause}</strong>
                                  </div>
                                  <div className="train-match-choices" role="group" aria-label={`Evidence source for statement ${index + 1}`}>
                                    {subskillTask.choices.map((choice) => {
                                      const selected = subskillTaskMatches[row.id] === choice.id;
                                      const used = !selected && selectedElsewhere.has(choice.id);
                                      return (
                                        <button
                                          key={choice.id}
                                          type="button"
                                          aria-pressed={selected}
                                          disabled={loading || used}
                                          onClick={() => setSubskillTaskMatches((current) => {
                                            const matches = { ...current };
                                            if (selected) delete matches[row.id];
                                            else matches[row.id] = choice.id;
                                            return matches;
                                          })}
                                        >
                                          {selected ? <CheckCircle2 size={13} aria-hidden="true" /> : null}
                                          {choice.label}
                                        </button>
                                      );
                                    })}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </fieldset>
                      ) : subskillTask.kind === "numeric_fill_in" ? (
                        <div className="field train-subskill-fill-in">
                          <label htmlFor={`training-value-${campaign.position}`}>
                            {subskillTask.responseLabel} ({subskillTask.unit})
                          </label>
                          <input
                            id={`training-value-${campaign.position}`}
                            type="number"
                            inputMode="decimal"
                            autoComplete="off"
                            min={subskillTask.minValue}
                            max={subskillTask.maxValue}
                            step={subskillTask.step}
                            value={subskillTaskValue}
                            onChange={(event) => setSubskillTaskValue(event.target.value)}
                            aria-describedby={`training-value-help-${campaign.position}`}
                            disabled={loading}
                          />
                          <span id={`training-value-help-${campaign.position}`} className="muted">
                            Enter one trace-based estimate. The reviewed value and tolerance stay hidden until you check your answer.
                          </span>
                        </div>
                      ) : (
                        <p className="selection-note"><strong>Confidence check:</strong> your confidence is compared with whether your submitted answer was correct. A reliable pattern takes several ECGs.</p>
                      )}
                      <p className="muted train-subskill-boundary">
                        {subskillTask.kind === "matching"
                          ? "Complete every pair. The evidence map appears after you check the answer."
                          : subskillTask.kind === "numeric_fill_in"
                            ? "Enter the value and place the calipers on the tracing; both parts belong to this measurement."
                        : trainingSubskill === "synthesize"
                          ? "Choose the interpretation that preserves the most important supported evidence."
                          : trainingSubskill === "apply_in_context"
                            ? "Choose the clinical information needed to use this ECG safely. Management decisions are practiced in Clinical Cases."
                            : trainingSubskill === "explain_mechanism"
                              ? "Choose the causal chain that best connects the morphology to its electrophysiology."
                              : "Complete this skill challenge before checking the answer."}
                      </p>
                    </div>
                  ) : null}

                  {viewerTask && !subskillTask ? (
                    <section className="train-trace-challenge" aria-label="ECG annotation challenge">
                      <div>
                        <p className="eyebrow">Skill challenge · ECG annotation</p>
                        <h3>{viewerTask.prompt}</h3>
                        <span>{trainingSubskill === "localize"
                          ? "This scores the relevant lead and waveform segment—not the full morphology by itself. Your mark remains visible during review."
                          : "Use the active waveform tool. Your mark will remain visible beside the reviewed evidence after submission."}</span>
                      </div>
                      <span className={viewerTaskEvidence ? "complete" : ""}>{viewerTaskEvidence ? <CheckCircle2 size={15} aria-hidden="true" /> : "2"}</span>
                    </section>
                  ) : null}

                  {trainingSubskill === "measure" && !viewerTask ? (
                    <p className="uncertainty train-viewer-task">
                      <strong>Measurement rehearsal only:</strong> this ECG has no reviewed numeric reference for this measurement. Record your method and value below, but it will not be marked correct or change your mastery estimate.
                    </p>
                  ) : null}

                    </>
                  )}

                  {trainingSubskill !== "synthesize" ? <div className="field train-evidence-field">
                    <label htmlFor="train-evidence-note">{evidenceNoteRequired ? "Evidence response" : "What evidence drove your answer?"} <span className="muted">{evidenceNoteRequired ? "(required)" : "(optional short answer)"}</span></label>
                    <textarea
                      id="train-evidence-note"
                      value={evidenceNote}
                      onChange={(event) => setEvidenceNote(event.target.value)}
                      placeholder="Name the lead, waveform, interval, or discriminator."
                      disabled={loading}
                    />
                  </div> : null}

                  {trainingSubskill === "calibrate_confidence" ? (
                    <fieldset className="train-confidence-field">
                      <legend>How certain are you?</legend>
                      <div className="train-confidence-scale">
                        {([
                          [1, "Guessing"],
                          [2, "Unsure"],
                          [3, "Moderate"],
                          [4, "Confident"],
                          [5, "Very certain"],
                        ] as const).map(([value, label]) => (
                          <button
                            key={value}
                            type="button"
                            aria-pressed={confidence === value}
                            className={confidence === value ? "active" : ""}
                            onClick={() => setConfidence(Number(value))}
                            disabled={loading}
                          >
                            <strong>{value}</strong><span>{label}</span>
                          </button>
                        ))}
                      </div>
                    </fieldset>
                  ) : null}

                  <div className="actions train-drill-actions">
                    <button className="button warn train-hint-button" type="button" onClick={requestHint} disabled={hintsUsed > 0 || loading}>
                      <Lightbulb size={16} aria-hidden="true" />
                      {hintsUsed ? "Hint used" : "Show one hint"}
                    </button>
                    <button
                      className="button primary train-commit-button"
                      type="button"
                      onClick={() => void commitAnswer()}
                      disabled={commitGaps.length > 0 || loading}
                      aria-describedby={commitGaps.length ? "training-commit-requirements" : undefined}
                    >
                      <Send size={16} aria-hidden="true" />
                      Check answer
                    </button>
                  </div>
                  <p className="muted train-hint-boundary">
                    A hint helps you find the evidence; this ECG remains saved as guided practice.
                  </p>
                  {commitGaps.length ? (
                    <div id="training-commit-requirements" className="train-commit-requirements" role="status" aria-live="polite">
                      <strong>Ready when you complete:</strong>
                      <ul>{commitGaps.map((gap) => <li key={gap}>{gap}</li>)}</ul>
                    </div>
                  ) : null}
                  {hintText ? <p className="uncertainty train-hint-text">{hintText}</p> : null}
                </section>
                <p className="train-tutor-lock-inline"><Brain size={15} aria-hidden="true" /> Luna unlocks after you check the answer, so your first read stays independent.</p>
              </>
            ) : (
              <div className="panel pad train-empty" role="status" aria-live="polite">{emptyReason ?? "Loading the next ECG…"}</div>
            )}
          </ResponseRail>
        </WorkspaceBody>

        <DisclosureArea className="train-disclosure">
          <span className="train-disclosure-summary"><Target size={14} aria-hidden="true" /> {conceptLabel(evidenceConcept)} · {activeSubskillLabel}</span>
          <details className="train-phase-disclosure">
            <summary>How this focused set works</summary>
            <p>Examples, close look-alikes, and normal contrasts are mixed across the set. Your current answer stays hidden until you check it.</p>
          </details>
        </DisclosureArea>

        <TutorDrawer title="Ask Luna about this ECG">
          {result && caseSummary ? (
            <TutorChat
              mode="practice"
              roleLabel="Luna · ECG review"
              ecgRef={caseSummary.caseId}
              threadScope={`training:${campaign.campaignId}`}
              viewerState={viewerState}
              onViewerActions={setViewerActions}
              openingPrompt={trainingSubskill === "synthesize"
                ? "Ask Luna to audit one step of your rate-to-impression sequence, explain a grounded review finding, or create a short follow-up check from this ECG."
                : `Ask why ${conceptLabel(classificationTarget)} was ${classificationTruth === "present" ? "supported" : "not supported"}, how the closest alternative differs, or ask Luna to highlight the decisive feature.`}
              resetKey={caseSummary.caseId}
            />
          ) : null}
        </TutorDrawer>
      </LearningWorkspaceShell>
    </div>
  );
}
