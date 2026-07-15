"use client";

import {
  ArrowLeft,
  ArrowRight,
  Brain,
  CheckCircle2,
  Eye,
  Lightbulb,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  Target,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ECGViewer } from "@/components/ECGViewer";
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
import { conceptLabel, type ECGPoint } from "@/lib/coordinates";
import { resolveHandoffTarget, type HandoffTargetResolution } from "@/lib/learning/handoffTargets";
import type { LearningSubskill } from "@/lib/learning/interactionTypes";
import { learningReturnLabel } from "@/lib/learning/learningReturn";
import {
  campaignMatchesTrainingLaunch,
  parseTrainingLaunchIntent,
  safeTrainingReturn,
  TRAINING_SESSION_LENGTHS,
  trainingFeedbackHeading,
  trainingMasteryPresentation,
} from "@/lib/learning/trainingLogic";
import { useLearningPreferences } from "@/lib/useLearningPreferences";
import styles from "./train.module.css";
import type {
  CasePacket,
  CaseSummary,
  ConceptGroup,
  ConceptSubskill,
  GroundedRoi,
  LearnerProfile,
  TrainingCampaignPayload,
  TrainingCampaignSummary,
  TrainingPhase,
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
};

type HintPlan = {
  text: string;
  actions: ViewerAction[];
};

type SessionPhase = TrainingPhase;
type BinaryAnswer = "present" | "absent";

const PHASE_SUMMARY: Array<{ phase: SessionPhase; label: string }> = [
  { phase: "target", label: "Build target" },
  { phase: "mimic", label: "Close mimic" },
  { phase: "negative", label: "Normal / negative" },
  { phase: "transfer", label: "Transfer" },
];

const PHASE_META: Record<SessionPhase, { label: string; purpose: string }> = {
  target: { label: "Build target", purpose: "Study and retrieve the defining evidence" },
  mimic: { label: "Close mimic", purpose: "Name the discriminator and resist a nearby look-alike" },
  negative: { label: "Normal / negative", purpose: "Calibrate absence, uncertainty, and overcalling" },
  transfer: { label: "Unannounced transfer", purpose: "Apply the skill without knowing the case role" },
};

type TrainingPoolInfo = {
  conceptId: string;
  subskill: string;
  eligibleDistinct: number;
  roleCounts: { target: number; mimic: number; negative: number };
  allowedLengths: number[];
  source: "audited_waveform_only";
  independentReceiptsAvailable: boolean;
};

const TRAINING_SUBSKILLS: Array<{ id: LearningSubskill; label: string }> = [
  { id: "recognize", label: "Recognize the pattern" },
  { id: "localize", label: "Localize the evidence" },
  { id: "measure", label: "Measure it" },
  { id: "discriminate", label: "Distinguish a close mimic" },
  { id: "explain_mechanism", label: "Explain the mechanism" },
  { id: "synthesize", label: "Synthesize the finding" },
  { id: "apply_in_context", label: "Identify needed clinical context" },
  { id: "calibrate_confidence", label: "Calibrate confidence" },
];

function isLearningSubskill(value: string): value is LearningSubskill {
  return TRAINING_SUBSKILLS.some((item) => item.id === value);
}

function sourceLabel(source?: string) {
  if (source === "fixture") return "Unavailable practice item";
  if (source === "prepared_bundle") return "Prepared PTB-XL bundle";
  if (source === "ptbxl") return "PTB-XL + PTB-XL+";
  if (source === "leipzig-heart-center") return "Leipzig expert rhythm window";
  return source ? source.replaceAll("_", " ") : "Loading source";
}

function trainingSkillLabel(value: string) {
  return TRAINING_SUBSKILLS.find((item) => item.id === value)?.label ?? value.replaceAll("_", " ");
}

function readableApiError(caught: unknown, fallback: string) {
  const detail = caught instanceof Error ? caught.message : "";
  if (!detail || /^\d{3}\b/.test(detail) || /internal server error|failed to fetch|networkerror/i.test(detail)) return fallback;
  return detail;
}

const MEASUREMENT_CLASSIFICATION_TARGETS = new Set(["rate", "qrs_duration", "qt_interval"]);

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
  if (concept === "qt_interval") {
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

function masteryClass(value: number) {
  if (value < 0.45) return "low";
  if (value < 0.7) return "medium";
  return "";
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

function chooseAdaptiveTarget(
  catalog: CatalogConcept[],
  groups: ConceptGroup[],
  profile: LearnerProfile | null,
  subskill: LearningSubskill,
): string {
  const highYield = new Set(catalog.filter((concept) => concept.highYield).map((concept) => concept.id));
  const available = availableConcepts(groups);
  // Generic interval nouns are not valid pathology-presence targets. Keep
  // them available for explicit measurement work, but do not let a fresh
  // recognition learner default into an ambiguous "Rate is present" drill.
  const focusedRows = subskill === "measure"
    ? available
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
  })[0]?.id ?? chooseDefaultConcept(catalog, groups);
}

function selectionReasonLabel(reason?: string) {
  if (reason === "adaptive_recheck" || reason?.includes("recheck") || reason?.includes("miss") || reason?.includes("overcall")) {
    return "selected after your last response for another evidence check";
  }
  if (reason === "adaptive_variation" || reason?.includes("success")) {
    return "selected to vary the next comparison after your last response";
  }
  return "part of the planned mixed sequence";
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
        : `Click the decisive ${domain.segment.replaceAll("_", " ")} evidence before you classify.`,
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
  const [trainingSubskill, setTrainingSubskill] = useState<LearningSubskill>("recognize");
  const [adaptiveMode, setAdaptiveMode] = useState(true);
  const [caseFocus, setCaseFocus] = useState("");
  const [caseSummary, setCaseSummary] = useState<CaseSummary | null>(null);
  const [packet, setPacket] = useState<CasePacket | null>(null);
  const [selectionReason, setSelectionReason] = useState("");
  const [selectedAnswer, setSelectedAnswer] = useState<BinaryAnswer | "">("");
  const [classificationTruth, setClassificationTruth] = useState<BinaryAnswer | null>(null);
  const [evidenceNote, setEvidenceNote] = useState("");
  const [subskillTaskAnswer, setSubskillTaskAnswer] = useState("");
  const [subskillTaskMatches, setSubskillTaskMatches] = useState<Record<string, string>>({});
  const [subskillTaskValue, setSubskillTaskValue] = useState("");
  const [confidence, setConfidence] = useState(3);
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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [returnTo, setReturnTo] = useState("");
  const [handoffConcept, setHandoffConcept] = useState("");
  const [handoffResolution, setHandoffResolution] = useState<HandoffTargetResolution | null>(null);
  const [campaignPayload, setCampaignPayload] = useState<TrainingCampaignPayload | null>(null);
  const [campaignLength, setCampaignLength] = useState<number>(10);
  const [poolInfo, setPoolInfo] = useState<TrainingPoolInfo | null>(null);
  const [poolLoading, setPoolLoading] = useState(false);
  const [replaceActiveOnStart, setReplaceActiveOnStart] = useState(false);
  const [sessionComplete, setSessionComplete] = useState(false);
  const [confirmAbandon, setConfirmAbandon] = useState(false);
  const abandonTriggerRef = useRef<HTMLButtonElement | null>(null);
  const abandonDialogRef = useRef<HTMLElement | null>(null);
  const keepTrainingRef = useRef<HTMLButtonElement | null>(null);
  const campaignLengthTouchedRef = useRef(false);
  const explicitCampaignLengthRef = useRef(false);

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
        setCampaignLength(intent.suggestedLength ?? 10);
        const initialSubskill = intent.subskill || "recognize";
        setTrainingSubskill(initialSubskill);

        const availableIds = availableConcepts(conceptData.practiceGroups).map((concept) => concept.id);
        const resolution = intent.requestedCaseConcept
          ? resolveHandoffTarget(intent.requestedCaseConcept, availableIds)
          : null;
        if (intent.requestedCaseConcept && !resolution) {
          setReplaceActiveOnStart(Boolean(activeCampaign.campaign));
          setAdaptiveMode(false);
          setHandoffConcept(intent.isHandoff ? intent.receiptConcept : "");
          setTrainingTarget("");
          setEmptyReason(
            `No validated real-ECG case family is available for ${intent.requestedCaseConcept.replaceAll("_", " ")}. Return to the prior activity or choose a different competency; no substitute attempt will be recorded.`,
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
          setSelectionReason("Resumed your saved training set at the same ECG and step.");
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
    if (
      booting
      || preferencesLoading
      || !learningPreferences
      || campaignPayload?.campaign
      || explicitCampaignLengthRef.current
      || campaignLengthTouchedRef.current
    ) return;
    const preferredLength = learningPreferences.defaultSessionLength === 5
      ? 10
      : learningPreferences.defaultSessionLength;
    setCampaignLength(preferredLength);
  }, [booting, campaignPayload?.campaign, learningPreferences, preferencesLoading]);

  useEffect(() => {
    if (!trainingTarget || campaignPayload?.campaign) return;
    let cancelled = false;
    setPoolLoading(true);
    setPoolInfo(null);
    api.trainingPool(trainingTarget, trainingSubskill)
      .then((pool) => {
        if (cancelled) return;
        setPoolInfo(pool);
        if (pool.eligibleDistinct === 0) {
          setEmptyReason("No distinct reviewed real ECGs currently support this concept and skill combination.");
        } else {
          setEmptyReason("Choose a set length, then start when you are ready.");
        }
      })
      .catch((err) => {
        if (!cancelled) setError(readableApiError(err, "Available ECGs could not be counted. Try again."));
      })
      .finally(() => {
        if (!cancelled) setPoolLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [campaignPayload?.campaign, trainingSubskill, trainingTarget]);

  const selectorGroups = useMemo(() => {
    const seen = new Set<string>();
    return groups
      .filter((group) => group.enabled)
      .map((group) => ({
        ...group,
        concepts: group.concepts.filter((concept) => {
          if (!concept.available || seen.has(concept.id)) return false;
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
  const conceptMatches = useMemo(() => {
    const query = conceptQuery.trim().toLocaleLowerCase();
    if (!query) return [];
    return searchableConcepts
      .filter((concept) => (
        concept.label.toLocaleLowerCase().includes(query)
        || concept.id.replaceAll("_", " ").toLocaleLowerCase().includes(query)
        || concept.groupLabel.toLocaleLowerCase().includes(query)
      ))
      .sort((left, right) => (
        Number(right.id === trainingTarget) - Number(left.id === trainingTarget)
        || Number(Boolean(catalog.find((item) => item.id === right.id)?.highYield))
          - Number(Boolean(catalog.find((item) => item.id === left.id)?.highYield))
        || right.reliableCaseCount - left.reliableCaseCount
      ))
      .slice(0, 8);
  }, [catalog, conceptQuery, searchableConcepts, trainingTarget]);
  const targetIsHighYield = catalog.some((concept) => concept.id === trainingTarget && concept.highYield);
  const evidenceConcept = handoffConcept || trainingTarget;
  const classificationTarget = trainingTarget;
  const taskVariant = campaignPayload?.current?.slot.position ?? 0;
  const answerContract = classificationContract(classificationTarget, taskVariant);
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
  const activeSubskillLabel = trainingSkillLabel(trainingSubskill);
  const campaign = campaignPayload?.campaign ?? null;
  const campaignSummary: TrainingCampaignSummary | null = campaignPayload?.summary ?? null;
  const currentSlot = campaignPayload?.current?.slot ?? null;
  const activePhase = currentSlot?.phase;
  const activeRecipe = activePhase ? PHASE_META[activePhase] : {
    label: "Fresh mixed check",
    purpose: "Apply the skill without being told the case role",
  };
  const sessionCorrect = campaignSummary?.correct ?? 0;
  const sessionClassificationCorrect = campaignSummary?.classificationCorrect ?? 0;
  const fullTaskCorrect = campaignSummary?.fullTaskCorrect ?? 0;
  const transferAttemptCount = campaignSummary?.byPhase.transfer.attempted ?? 0;
  const transferCorrect = campaignSummary?.byPhase.transfer.correct ?? 0;
  const independentReceipts = campaignSummary?.independentReceipts ?? 0;
  const committedCount = campaignSummary?.attempted ?? 0;
  const campaignTotal = campaign?.length ?? 0;
  const readyForRapid = campaignTotal > 0
    && trainingSubskill === "recognize"
    && independentReceipts >= 2
    && sessionCorrect / campaignTotal >= 0.8
    && transferAttemptCount > 0
    && transferCorrect / transferAttemptCount >= 2 / 3;
  const suggestedAdaptiveTarget = chooseAdaptiveTarget(catalog, groups, profile, trainingSubskill);
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
    setConfidence(3);
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
    setSelectionReason("");
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

    const current = next.current;
    if (!current) {
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
    setSelectionReason(
      `ECG ${current.slot.position + 1} of ${nextCampaign.length} · Reviewed real ECG · ${current.slot.phase ? PHASE_META[current.slot.phase].label : "Fresh mixed check"} · ${selectionReasonLabel(current.slot.selectionReason)}.`,
    );

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
    setConfidence(response.confidence);
    setHintsUsed(response.hintsUsed);
    setViewerTaskEvidence(response.viewerTaskEvidence ?? null);
    setHintText(response.hintsUsed ? "A visual hint was used before this response was committed." : "");
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
      response.expectedAnswer === "present" ? nextCampaign.conceptId : (current.slot.caseFocus ?? nextCampaign.conceptId),
      current.packet.ptbxl_plus.fiducials.rois ?? [],
      current.packet.waveform.leads,
    );
    setViewerActions(feedbackPlan.actions);
  }

  async function startCampaign(replaceActive = replaceActiveOnStart) {
    if (!trainingTarget || poolInfo?.eligibleDistinct === 0) return;
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
        length: campaignLength,
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
    if (!campaign) return;
    setLoading(true);
    setError(null);
    try {
      await api.abandonTrainingCampaign(campaign.campaignId);
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
    if (!campaign || !suggestedAdaptiveTarget) return;
    setLoading(true);
    setError(null);
    try {
      await api.abandonTrainingCampaign(campaign.campaignId);
      setCampaignPayload(null);
      setReplaceActiveOnStart(false);
      setHandoffConcept("");
      setHandoffResolution(null);
      setAdaptiveMode(true);
      setTrainingTarget(suggestedAdaptiveTarget);
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

  function changeTarget(value: string) {
    if (campaign) return;
    clearWorkspace("Finding fresh ECGs for this skill…");
    setHandoffConcept("");
    setHandoffResolution(null);
    setAdaptiveMode(false);
    setTrainingTarget(value);
  }

  function changeSubskill(value: string) {
    if (!isLearningSubskill(value) || campaign) return;
    clearWorkspace("Rechecking the real-ECG pool for this subskill…");
    setTrainingSubskill(value);
    const target = adaptiveMode ? chooseAdaptiveTarget(catalog, groups, profile, value) : trainingTarget;
    setTrainingTarget(target);
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

  function enableAdaptiveMode() {
    if (campaign) return;
    const target = chooseAdaptiveTarget(catalog, groups, profile, trainingSubskill);
    clearWorkspace("Finding ECGs for the skill that needs the most practice…");
    setAdaptiveMode(true);
    setHandoffConcept("");
    setHandoffResolution(null);
    setTrainingTarget(target);
  }

  function subskillEvidenceIsValid(evidence = viewerTaskEvidence) {
    if (trainingSubskill === "recognize" || trainingSubskill === "calibrate_confidence") return true;
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
    if (["discriminate", "explain_mechanism", "synthesize", "apply_in_context"].includes(trainingSubskill)) {
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
    } else if (["discriminate", "explain_mechanism", "synthesize", "apply_in_context"].includes(trainingSubskill)) {
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
        confidence,
        hintsUsed,
        evidenceNote,
        viewerTaskEvidence,
        subskillTaskAnswer,
        subskillTaskMatches,
        subskillTaskValue: subskillTaskValue.trim() === "" ? null : Number(subskillTaskValue),
        receiptConcept: evidenceConcept,
      });
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
      <div className={`page train-page train-page-setup ${styles.setupPage}`}>
        <section className="panel pad train-campaign-setup train-setup-single" aria-label="Configure training set">
          <header className="train-setup-header">
            <div>
              <p className="eyebrow">Competency training</p>
              <h1>Train one visual skill until it sticks</h1>
              <p className="muted">
                Choose one skill and a number of unique real ECGs. Every tracing in the set is different, and your progress is saved.
              </p>
            </div>
            {returnTo ? <Link className="button subtle" href={returnTo}><ArrowLeft size={16} aria-hidden="true" /> {learningReturnLabel(returnTo)}</Link> : null}
          </header>

          {returnTo ? (
            <p className="selection-note train-setup-handoff">
              This set was launched for <strong>{conceptLabel(evidenceConcept)} · {trainingSkillLabel(trainingSubskill)}</strong>. Your place in the prior activity is preserved.
              {handoffResolution && !handoffResolution.exact ? <> It uses the closest reviewed <strong>{conceptLabel(handoffResolution.caseConcept)}</strong> ECG family because {handoffResolution.rationale}; you still need to complete the selected skill.</> : null}
            </p>
          ) : null}
          {replaceActiveOnStart ? (
            <p className="uncertainty train-setup-handoff" role="status">
              This handoff targets a different competency than your saved set. Starting it will close the saved set; completed ECGs remain in your learning history.
            </p>
          ) : null}
          {error ? (
            <div className="warning train-error mode-recovery-notice" role="alert">
              <span>{error}</span>
              <button className="button subtle small" type="button" onClick={() => setBootRetryKey((value) => value + 1)}>
                <RefreshCw size={15} aria-hidden="true" /> Retry loading
              </button>
            </div>
          ) : null}

          <div className="train-setup-grid">
            <section className="train-setup-competency" aria-label="Choose a competency">
              <h2><Target size={18} aria-hidden="true" /> Choose a competency</h2>
              <div className="train-concept-search">
                <label htmlFor="train-concept-search">Find a concept</label>
                <div className="train-concept-search-input">
                  <Search size={16} aria-hidden="true" />
                  <input
                    id="train-concept-search"
                    type="search"
                    value={conceptQuery}
                    onChange={(event) => setConceptQuery(event.target.value)}
                    placeholder="Search concepts"
                    autoComplete="off"
                    disabled={loading || Boolean(handoffConcept)}
                    aria-describedby="train-concept-search-status"
                  />
                </div>
                <div id="train-concept-search-status" className="sr-only" aria-live="polite">
                  {conceptQuery.trim()
                    ? `${conceptMatches.length} matching concept${conceptMatches.length === 1 ? "" : "s"} shown.`
                    : "Type to find a concept by name or category."}
                </div>
                {conceptQuery.trim() ? (
                  <div className="train-concept-results" aria-label="Matching concepts">
                    {conceptMatches.length ? (
                      <ul>
                        {conceptMatches.map((concept) => (
                          <li key={concept.id}>
                            <button
                              className={concept.id === trainingTarget ? "active" : ""}
                              type="button"
                              onClick={() => {
                                changeTarget(concept.id);
                                setConceptQuery("");
                              }}
                            >
                              <span><strong>{concept.label}</strong><small>{concept.groupLabel}</small></span>
                              <small>{concept.reliableCaseCount.toLocaleString()} ECGs</small>
                            </button>
                          </li>
                        ))}
                      </ul>
                    ) : <p className="muted">No available concept matches “{conceptQuery.trim()}”.</p>}
                  </div>
                ) : null}
              </div>
              <div className="train-setup-fields">
                <div className="field train-target-field">
                  <label htmlFor="train-target">Target concept</label>
                  <select
                    id="train-target"
                    value={trainingTarget}
                    onChange={(event) => changeTarget(event.target.value)}
                    disabled={loading || Boolean(handoffConcept)}
                  >
                    {selectorGroups.map((group) => (
                      <optgroup label={group.label} key={group.id}>
                        {group.concepts.filter((concept) => concept.available).map((concept) => (
                          <option value={concept.id} key={concept.id}>
                            {concept.label} · {concept.reliableCaseCount.toLocaleString()} cases
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                </div>
                <div className="field train-target-field">
                  <label htmlFor="train-subskill">Skill to practice</label>
                  <select id="train-subskill" value={trainingSubskill} onChange={(event) => changeSubskill(event.target.value)} disabled={loading || Boolean(handoffConcept)}>
                    {TRAINING_SUBSKILLS.map((subskill) => <option key={subskill.id} value={subskill.id}>{subskill.label}</option>)}
                  </select>
                </div>
              </div>
              <button className={`button small train-adaptive-button ${adaptiveMode ? "primary" : "subtle"}`} type="button" aria-pressed={adaptiveMode} onClick={enableAdaptiveMode} disabled={loading}>
                <Sparkles size={15} aria-hidden="true" /> {adaptiveMode ? `Recommended · ${suggestedMastery.recommendationLabel === "unassessed skill" ? "not checked yet" : suggestedMastery.recommendationLabel}` : "Use recommended skill"}
              </button>
              {handoffConcept ? (
                <p className="selection-note train-setup-note">
                  This target stays fixed so your result remains connected to the activity that sent you here. Choose <strong>Use recommended skill</strong> to start a separate adaptive set.
                </p>
              ) : null}
              <div className="objective-meta train-mastery-meta">
                <strong>{conceptLabel(evidenceConcept)}</strong>
                <span className="muted">{masteryPresentation.label}</span>
              </div>
              {targetIsHighYield ? <span className="pill train-high-yield">High-yield target</span> : null}
              {masteryPresentation.value === null ? (
                <p className="muted train-setup-note">{masteryPresentation.detail}</p>
              ) : (
                <progress className={`train-mastery-progress ${masteryClass(masteryPresentation.value)}`} value={masteryPresentation.value} max={1} aria-label={`${Math.round(masteryPresentation.value * 100)} percent mastery`} />
              )}
              <p className="muted train-setup-note">
                Practice focus: <strong>{conceptLabel(evidenceConcept)} · {activeSubskillLabel}</strong>.
              </p>
              <p className="selection-note train-setup-note">
                {poolInfo?.independentReceiptsAvailable
                  ? "Some fresh mixed ECGs can update your mastery estimate; practice with hints still shapes what comes next."
                  : trainingSubskill === "measure"
                    ? "This ECG family has no reviewed numeric reference. Your written value is saved as rehearsal only; it will not be marked correct or update measurement mastery."
                  : trainingSubskill === "apply_in_context"
                    ? "This ECG-only lab has no patient vignette. It rehearses which clinical facts are still needed; it does not assess management or application mastery."
                    : "This lab builds the skill; a later mixed challenge checks whether it transfers."}
              </p>
              {handoffResolution && !handoffResolution.exact ? (
                <p className="selection-note train-setup-note">
                  Practice tracing: this decision asks about <strong>{conceptLabel(classificationTarget)}</strong>. Mastery is checked on a directly matched ECG.
                </p>
              ) : null}
            </section>

            <section className="train-campaign-controls" aria-label="Training set size and available ECGs">
              <div className="field">
                <label htmlFor="train-campaign-length">Requested unique ECGs</label>
                <select
                  id="train-campaign-length"
                  value={campaignLength}
                  onChange={(event) => {
                    campaignLengthTouchedRef.current = true;
                    setCampaignLength(Number(event.target.value));
                  }}
                  disabled={loading}
                >
                  {TRAINING_SESSION_LENGTHS.map((length) => <option value={length} key={length}>{length.toLocaleString()}</option>)}
                </select>
              </div>
              <div className="train-pool-readout" aria-live="polite">
                <strong>{poolLoading ? "Counting…" : `${(poolInfo?.eligibleDistinct ?? 0).toLocaleString()} unique ECGs available`}</strong>
                <span className="muted">Reviewed real ECG waveforms only</span>
                {!poolLoading && poolInfo ? <span className="muted">
                  {poolInfo.roleCounts.target.toLocaleString()} pattern present · {poolInfo.roleCounts.mimic.toLocaleString()} close comparisons · {poolInfo.roleCounts.negative.toLocaleString()} other contrasts
                </span> : null}
                {!poolLoading && poolInfo && campaignLength > poolInfo.eligibleDistinct ? (
                  <span className="uncertainty">Your {campaignLength.toLocaleString()} request will be capped at {poolInfo.eligibleDistinct.toLocaleString()}; only unique real ECGs are used—no synthetic or repeated case will fill the gap.</span>
                ) : null}
              </div>
              {!poolLoading && poolInfo?.eligibleDistinct === 0 ? (
                <p className="warning train-empty-reason" role="status">
                  {emptyReason ?? "This exact finding and skill do not currently have a suitable real-ECG set."} Choose another skill or finding to continue.
                </p>
              ) : null}
              <button
                className="button primary train-start-button"
                type="button"
                onClick={() => void startCampaign()}
                disabled={loading || poolLoading || !trainingTarget || !poolInfo?.eligibleDistinct}
              >
                <ShieldCheck size={16} aria-hidden="true" /> {replaceActiveOnStart ? "Replace saved set and start" : "Start training"}
              </button>
            </section>
          </div>
        </section>
      </div>
    );
  }

  const workspacePhase = result ? "feedback" : sessionComplete ? "complete" : "response";
  const debriefPanel = sessionComplete ? (
    <section className="panel pad train-debrief-panel" aria-live="polite">
      <p className="eyebrow">Training set complete</p>
      <h2>{sessionCorrect.toLocaleString()}/{campaign.length.toLocaleString()} {trainingSkillLabel(trainingSubskill).toLowerCase()} tasks met</h2>
      <p className="muted">
        Pattern decision: {sessionClassificationCorrect.toLocaleString()}/{campaign.length.toLocaleString()} correct · both decision and selected skill: {fullTaskCorrect.toLocaleString()}/{campaign.length.toLocaleString()}. {independentReceipts} fresh mixed ECG check{independentReceipts === 1 ? "" : "s"} contributed to your mastery estimate.
      </p>
      <div className="train-debrief-grid">
        {PHASE_SUMMARY.map((item) => {
          const phase = campaignSummary?.byPhase[item.phase] ?? { attempted: 0, correct: 0 };
          return (
            <div key={item.phase}>
              <span>{item.label}</span>
              <strong>{phase.correct.toLocaleString()}/{phase.attempted.toLocaleString()}</strong>
            </div>
          );
        })}
      </div>
      <div className="selection-note train-next-recommendation">
        <strong><Sparkles size={15} aria-hidden="true" /> Recommended next</strong>
        {readyForRapid ? (
          <p>You earned at least two independent recognition receipts, read {transferCorrect}/{transferAttemptCount} fresh mixed ECGs correctly, and reached at least 80% overall. Move to Rapid practice, where the target is no longer named in advance.</p>
        ) : (
          <p>Try another focused set. It will mix the target with close comparisons and fresh ECGs.</p>
        )}
      </div>
      <div className="actions train-debrief-actions">
        <button className="button primary" type="button" onClick={resetCurrentSet} disabled={loading}>
          <RefreshCw size={16} aria-hidden="true" /> Start another set
        </button>
        {readyForRapid ? (
          <Link className="button" href={`/rapid?focus=${encodeURIComponent(evidenceConcept)}&receiptConcept=${encodeURIComponent(evidenceConcept)}&subskill=recognize`}>
            Start mixed Rapid <ArrowRight size={16} aria-hidden="true" />
          </Link>
        ) : null}
        {!handoffConcept && suggestedAdaptiveTarget && suggestedAdaptiveTarget !== trainingTarget ? (
          <button className="button subtle" type="button" onClick={() => void prepareNextWeakConcept()} disabled={loading}>
            Practice another recommended skill
          </button>
        ) : null}
        {returnTo ? <Link className="button subtle" href={returnTo}><ArrowLeft size={16} aria-hidden="true" /> {learningReturnLabel(returnTo)}</Link> : null}
      </div>
    </section>
  ) : null;

  return (
    <div className="page train-page train-page-active">
      <LearningWorkspaceShell className="train-runner" phase={workspacePhase} tutorResetKey={caseSummary?.caseId}>
        <SessionBar className="train-session-bar" tutorAvailable={Boolean(result && caseSummary)} tutorLabel="Open tutor">
          <section className="train-session-summary" aria-label="Focused training set">
            <div className="train-session-identity">
              <span className="eyebrow">{currentSlot ? `Case ${currentSlot.position + 1}` : `${committedCount} cases`} of {campaign.length.toLocaleString()}</span>
              <strong>{activeRecipe.label}</strong>
            </div>
            <progress
              className="train-session-progress-native"
              value={committedCount}
              max={Math.max(1, campaign.length)}
              aria-label={`${committedCount} of ${campaign.length} cases completed`}
            />
            <span className="train-session-count">{committedCount.toLocaleString()}/{campaign.length.toLocaleString()} completed</span>
          </section>
          {returnTo ? <Link className="button subtle small train-return-link" href={returnTo}><ArrowLeft size={15} aria-hidden="true" /> {learningReturnLabel(returnTo)}</Link> : null}
          <button ref={abandonTriggerRef} className="button warn small train-abandon-button" type="button" onClick={() => setConfirmAbandon(true)} disabled={loading || confirmAbandon}>
            <XCircle size={15} aria-hidden="true" /> Leave training set
          </button>
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
              <span>{activeRecipe.label} · {activeSubskillLabel}</span>
              <strong>{answerContract.prompt}</strong>
              {viewerTask ? <small>On trace: {viewerTask.prompt}</small> : null}
            </div>
            <a className="button subtle small" href="#train-response-task">Go to response</a>
          </section>
        ) : null}

        <WorkspaceBody className="train-active-workspace">
          <WaveformPane className="train-viewer-pane" label="Training ECG waveform">
            {caseSummary ? (
              <ECGViewer
                ecgRef={caseSummary.caseId}
                waveformScope={{ kind: "training", campaignId: campaign.campaignId }}
                actions={viewerActions}
                groundedRois={result ? waveformRois : []}
                gradingRois={result ? waveformRois : []}
                onCoordinate={setSelectedPoint}
                medianBeats={packet?.ptbxl_plus.median_beats ?? null}
                task={!result ? viewerTask : undefined}
                onTaskEvidence={setViewerTaskEvidence}
                gradingMode="deferred"
              />
            ) : (
              <div className="panel pad train-empty" role="status" aria-live="polite">{emptyReason ?? "Loading a confidence-gated ECG..."}</div>
            )}
          </WaveformPane>

          <ResponseRail className="train-response-rail" label={result ? "Training feedback" : sessionComplete ? "Set review" : "Training response"} phase={workspacePhase}>
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
                  <p>
                    You chose <strong>{selectedAnswerLabel}</strong>; the reviewed pattern decision is <strong>{groundedAnswerLabel}</strong>. {measurementRehearsal
                      ? "The written number is saved as rehearsal because this case has no validated numeric answer."
                      : classificationCorrect === result.correct
                        ? classificationCorrect ? "Both scoring axes were met." : "Both scoring axes need another look."
                        : "The pattern decision and selected-skill task had different outcomes, shown separately above."}
                  </p>
                  {taskResult?.kind === "numeric_fill_in" ? (
                    <section className="train-task-feedback" aria-label="Measurement answer review">
                      <strong>{taskResult.correct ? "Measurement within range" : "Measurement needs review"}</strong>
                      <p>
                        You entered {taskResult.submittedValue ?? "no value"} {taskResult.unit}. The exact packet measurement is {taskResult.expectedValue} {taskResult.unit}
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
                  <div className="train-carry-forward">
                    <strong>Carry forward</strong>
                    <p>{carryForwardCopy}</p>
                  </div>
                  {!sessionComplete ? (
                    <button className="button primary train-next-button" type="button" onClick={loadNextAdaptiveDrill} disabled={loading}>
                      Next case in set <ArrowRight size={16} aria-hidden="true" />
                    </button>
                  ) : null}
                </section>

                <section className="panel pad train-evidence" aria-label="Answer evidence">
                  <h2><Eye size={18} aria-hidden="true" /> Why this answer</h2>
                  <div className="evidence-grid train-evidence-grid">
                    <div className="evidence-card train-confidence-card">
                      <h3>{conceptLabel(evidenceConcept)} · {groundedAnswerLabel}</h3>
                      {focusConfidence ? (
                        <>
                          <p className="muted">{focusConfidence.tier === "A" ? "Strong" : "Reviewed"} source and waveform support.</p>
                        </>
                      ) : (
                        <p className="muted">
                          {classificationTruth === "absent"
                            ? `The reviewed labels do not support ${conceptLabel(classificationTarget)}. The contrast case is ${conceptLabel(caseFocus)}.`
                            : "This case was scored from its reviewed source labels and waveform evidence."}
                        </p>
                      )}
                    </div>
                  </div>
                  {focusConfidence?.warnings.length ? (
                    <p className="uncertainty train-confidence-warning">Data quality note: localized noise limits fine-detail claims, so rely on the clearest leads.</p>
                  ) : null}
                  {measurementRehearsal ? (
                    <p className="uncertainty train-confidence-warning">
                      Measurement boundary: the note records your method and estimate only. No numeric accuracy or measurement-mastery claim was created.
                    </p>
                  ) : null}
                </section>
                {debriefPanel}
              </>
            ) : sessionComplete ? debriefPanel : packet ? (
              <>
                <section className="panel pad train-drill-panel" id="train-response-task">
                  <div className="train-current-target">
                    <div>
                      <p className="eyebrow">{activeRecipe.label}</p>
                      <h2>{activeSubskillLabel}</h2>
                      <strong className="train-current-concept">{conceptLabel(classificationTarget)}</strong>
                    </div>
                    <span className="muted">{masteryPresentation.label}</span>
                  </div>
                  {masteryPresentation.value === null ? (
                    <p className="muted train-task-prompt">{masteryPresentation.detail}</p>
                  ) : (
                    <progress className={`train-mastery-progress ${masteryClass(masteryPresentation.value)}`} value={masteryPresentation.value} max={1} aria-label={`${Math.round(masteryPresentation.value * 100)} percent mastery`} />
                  )}
                  <p className="muted train-task-prompt">
                    {answerContract.prompt} Choose the best answer after reading the trace.
                  </p>
                  <p className="selection-note train-receipt-boundary">
                    {poolInfo?.independentReceiptsAvailable
                      ? "Fresh mixed ECGs can update your mastery estimate; the other cases build and calibrate the skill."
                      : trainingSubskill === "measure"
                        ? "No validated measurement target exists for this ECG family. Your written value is rehearsal only and cannot verify accuracy or update measurement mastery."
                      : trainingSubskill === "apply_in_context"
                        ? "No patient vignette is present. This rehearses which context is missing; it does not assess a management decision or application mastery."
                        : "This focused task builds the skill; a later mixed challenge checks transfer."}
                  </p>
                  {handoffResolution && !handoffResolution.exact ? (
                    <p className="selection-note train-receipt-boundary">
                      Practice tracing: this decision asks about <strong>{conceptLabel(classificationTarget)}</strong>. Mastery is checked on a directly matched ECG.
                    </p>
                  ) : null}
                  {viewerTask ? <p className="selection-note train-viewer-task"><strong>Trace task:</strong> {viewerTask.prompt} Complete it directly on the waveform; it is checked separately from your classification.</p> : null}
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
                    <div className="panel pad train-subskill-task">
                      <p className="eyebrow">Practice {subskillTask.subskill.replaceAll("_", " ")}</p>
                      <h3>{subskillTask.prompt}</h3>
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
                          <legend>Match each statement to one evidence source</legend>
                          <p id={`training-match-help-${campaign.position}`} className="muted">
                            Use each source once. These native menus work with keyboard, touch, or pointer input.
                          </p>
                          <div className="train-subskill-matching-rows">
                            {subskillTask.rows.map((row, index) => {
                              const selectId = `training-match-${campaign.position}-${row.id}`;
                              const selectedElsewhere = new Set(
                                Object.entries(subskillTaskMatches)
                                  .filter(([rowId]) => rowId !== row.id)
                                  .map(([, choiceId]) => choiceId),
                              );
                              return (
                                <div className="train-subskill-matching-row" key={row.id}>
                                  <label htmlFor={selectId}>
                                    <span>Statement {index + 1}</span>
                                    <strong>{row.clause}</strong>
                                  </label>
                                  <select
                                    id={selectId}
                                    value={subskillTaskMatches[row.id] ?? ""}
                                    onChange={(event) => {
                                      const choiceId = event.target.value;
                                      setSubskillTaskMatches((current) => {
                                        const matches = { ...current };
                                        if (choiceId) matches[row.id] = choiceId;
                                        else delete matches[row.id];
                                        return matches;
                                      });
                                    }}
                                    disabled={loading}
                                  >
                                    <option value="">Choose an evidence source…</option>
                                    {subskillTask.choices.map((choice) => (
                                      <option
                                        key={choice.id}
                                        value={choice.id}
                                        disabled={selectedElsewhere.has(choice.id)}
                                      >
                                        {choice.label}
                                      </option>
                                    ))}
                                  </select>
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
                            Enter one trace-based estimate. The packet value and tolerance stay hidden until commitment.
                          </span>
                        </div>
                      ) : (
                        <p className="selection-note"><strong>Confidence check:</strong> your confidence is compared with whether your committed answer was correct. A reliable pattern takes several ECGs.</p>
                      )}
                      <p className="muted train-subskill-boundary">
                        {subskillTask.kind === "matching"
                          ? "Complete all evidence-source matches. Correct mappings are revealed only after the whole response is committed."
                          : subskillTask.kind === "numeric_fill_in"
                            ? "Enter the measured value and complete the trace calipers; both are checked against this ECG’s reviewed measurements."
                        : trainingSubskill === "synthesize"
                          ? "Complete the structured interpretation choice; free-text length alone does not count."
                          : trainingSubskill === "apply_in_context"
                            ? "Complete the context-boundary choice. There is no patient vignette here, so this cannot verify management or application competence."
                            : trainingSubskill === "explain_mechanism"
                              ? "Choose the causal chain that best connects the ECG pattern to its mechanism. This checks ECG mechanism only; it does not infer symptoms, acuity, cause, or treatment."
                              : "Complete the structured choice above so this skill is graded directly."}
                      </p>
                    </div>
                  ) : null}

                  {trainingSubskill === "measure" && !viewerTask ? (
                    <p className="uncertainty train-viewer-task">
                      <strong>Measurement rehearsal only:</strong> this ECG family has no reviewed numeric reference for this measurement. Record your method and value below, but it will not be marked correct or change your mastery estimate.
                    </p>
                  ) : null}

                  <div className="field train-evidence-field">
                    <label htmlFor="train-evidence-note">Evidence note <span className="muted">{(trainingSubskill === "measure" && !viewerTask) || (trainingSubskill === "localize" && (evidenceConcept.includes("lead_territor") || evidenceConcept.includes("frontal_lead_map"))) ? "(required)" : "(optional)"}</span></label>
                    <textarea
                      id="train-evidence-note"
                      value={evidenceNote}
                      onChange={(event) => setEvidenceNote(event.target.value)}
                      placeholder="Name the lead, waveform, or interval that drove your choice."
                      disabled={loading}
                    />
                  </div>

                  <div className="field train-confidence-field">
                    <label htmlFor="train-confidence">Confidence</label>
                    <select
                      id="train-confidence"
                      value={confidence}
                      onChange={(event) => setConfidence(Number(event.target.value))}
                      disabled={loading}
                    >
                      <option value={1}>1 · Guessing</option>
                      <option value={2}>2 · Unsure</option>
                      <option value={3}>3 · Moderate</option>
                      <option value={4}>4 · Confident</option>
                      <option value={5}>5 · Very confident</option>
                    </select>
                  </div>

                  <div className="actions train-drill-actions">
                    <button className="button warn train-hint-button" type="button" onClick={requestHint} disabled={hintsUsed > 0 || loading}>
                      <Lightbulb size={16} aria-hidden="true" />
                      {hintsUsed ? "Coached hint used" : "Show hint · coached"}
                    </button>
                    <button
                      className="button primary train-commit-button"
                      type="button"
                      onClick={() => void commitAnswer()}
                      disabled={commitGaps.length > 0 || loading}
                      aria-describedby={commitGaps.length ? "training-commit-requirements" : undefined}
                    >
                      <Send size={16} aria-hidden="true" />
                      Commit answer
                    </button>
                  </div>
                  <p className="muted train-hint-boundary">
                    A visual hint changes this ECG to coached practice; it cannot earn an independent mastery receipt.
                  </p>
                  {commitGaps.length ? (
                    <div id="training-commit-requirements" className="train-commit-requirements" role="status" aria-live="polite">
                      <strong>Before you commit</strong>
                      <ul>{commitGaps.map((gap) => <li key={gap}>{gap}</li>)}</ul>
                    </div>
                  ) : null}
                  {hintText ? <p className="uncertainty train-hint-text">{hintText}</p> : null}
                </section>
                <section className="panel pad train-tutor-lock train-tutor-lock-inline">
                  <h2><Brain size={18} aria-hidden="true" /> Tutor after commitment</h2>
                  <p className="muted">Commit first to keep the answer hidden. Ask for help after grading.</p>
                </section>
              </>
            ) : (
              <div className="panel pad train-empty" role="status" aria-live="polite">{emptyReason ?? "Loading the next ECG…"}</div>
            )}
          </ResponseRail>
        </WorkspaceBody>

        <DisclosureArea className="train-disclosure">
          {packet ? (
            <section className="train-provenance-inline" aria-label="ECG source">
              <ShieldCheck size={15} aria-hidden="true" />
              <strong>{result ? sourceLabel(packet.source) : "Reviewed real ECG"}</strong>
              {packet.source === "fixture" ? (
                <span className="warning train-fixture-warning">This practice item is not available.</span>
              ) : (
                <span className="train-real-data-note"><ShieldCheck size={14} aria-hidden="true" /> Real waveform · {result ? "answer revealed" : "answer hidden"}</span>
              )}
              {selectedPoint ? <span className="train-coordinate">Cursor {selectedPoint.lead} · {selectedPoint.timeSec.toFixed(3)} s · {selectedPoint.amplitudeMv.toFixed(3)} mV</span> : null}
            </section>
          ) : null}
          <details className="train-phase-disclosure">
            <summary>How this set is mixed</summary>
            <ol className="train-session-recipe">
              {PHASE_SUMMARY.map((item) => {
                const planned = campaign.phaseCounts[item.phase] ?? 0;
                const completed = campaignSummary?.byPhase[item.phase].attempted ?? 0;
                const complete = planned > 0 && completed >= planned;
                const active = !complete && activePhase === item.phase;
                return (
                  <li className={complete ? "complete" : active ? "active" : ""} key={item.phase}>
                    <span>{complete ? <CheckCircle2 size={16} aria-hidden="true" /> : completed + 1}</span>
                    <div><strong>{item.label}</strong><small>{completed.toLocaleString()} / {planned.toLocaleString()} cases</small></div>
                  </li>
                );
              })}
            </ol>
            {selectionReason ? <p className="train-selection-reason">{selectionReason}</p> : null}
          </details>
        </DisclosureArea>

        <TutorDrawer title="ECG tutor">
          {result && caseSummary ? (
            <TutorChat
              mode="practice"
              roleLabel="Tutor · after your answer"
              ecgRef={caseSummary.caseId}
              threadScope={`training:${campaign.campaignId}`}
              viewerState={viewerState}
              onViewerActions={setViewerActions}
              openingPrompt={`Ask why ${conceptLabel(classificationTarget)} was ${classificationTruth === "present" ? "present" : "absent"}, how ${conceptLabel(caseFocus)} changes the contrast, or ask me to highlight the decisive feature.`}
              resetKey={caseSummary.caseId}
            />
          ) : null}
        </TutorDrawer>
      </LearningWorkspaceShell>
    </div>
  );
}
